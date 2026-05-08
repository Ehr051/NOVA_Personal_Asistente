"""
novaesp.py — NOVA Agente Total v2.0
──────────────────────────────────────────
• HUD flotante estilo Iron Man (siempre visible en el escritorio)
• Voz masculina en español (Reed macOS nativo)
• Routing inteligente de modelos (OpenClaw/Groq/OpenRouter, 3 tiers)
• Skills del sistema: apps, comandos, volumen, screenshot, archivos y dictado
• Búsqueda web en tiempo real (DuckDuckGo)
• Memoria persistente entre sesiones (SQLite)

Arquitectura de hilos:
  Hilo principal  → tkinter HUD
  Hilo background → loop de escucha / LLM / voz
"""

from dotenv import load_dotenv
load_dotenv()

import sys
import os
# Add project root to sys.path to allow imports from nova package
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import logging
import os
import re
import subprocess
import threading
import time
import atexit
import asyncio
import tempfile

log = logging.getLogger(__name__)

# ─── Audio: audioop removido en Python 3.13 ──────────────────────────────────
try:
    import audioop
    _AUDIOOP_AVAILABLE = True
except ImportError:
    _AUDIOOP_AVAILABLE = False

# sounddevice: preferido en Windows (WASAPI nativo, sin compilación)
# PyAudio: fallback para macOS/Linux
try:
    import sounddevice as _sd
    import numpy as _np_audio
    _SOUNDDEVICE_AVAILABLE = True
    _PYAUDIO_AVAILABLE = False
except ImportError:
    _SOUNDDEVICE_AVAILABLE = False
    try:
        import pyaudio as _pyaudio
        _PYAUDIO_AVAILABLE = True
    except ImportError:
        _pyaudio = None
        _PYAUDIO_AVAILABLE = False

try:
    import edge_tts as _edge_tts
    _EDGE_TTS_AVAILABLE = True
except ImportError:
    _EDGE_TTS_AVAILABLE = False

# ─── Speaker verification (MFCC, sin cargar Whisper) ─────────────────────────

_SPEAKER_PROFILE: "np.ndarray | None" = None
_SPEAKER_THRESHOLD = float(os.getenv("SPEAKER_THRESHOLD", "0.87"))
_SPEAKER_VERIFY = False   # se activa si se carga un perfil

def _load_speaker_profile() -> None:
    """Busca nova_voice_profile.npy en ubicaciones conocidas y lo carga."""
    global _SPEAKER_PROFILE, _SPEAKER_VERIFY
    _me = os.path.dirname(__file__)
    candidates = [
        os.path.join(_me, "..", "..", "..", "nova_voice_profile.npy"),      # raíz proyecto
        os.path.join(_me, "..", "tools", "nova_voice_profile.npy"),           # src/nova/tools/
        os.path.expanduser("~/.nova/nova_voice_profile.npy"),
    ]
    for p in candidates:
        p = os.path.abspath(p)
        if os.path.exists(p):
            try:
                import numpy as np
                _SPEAKER_PROFILE = np.load(p)
                _SPEAKER_VERIFY = True
                log.info("[Speaker] Perfil cargado: %s — verificación ACTIVA (umbral=%.2f)", os.path.basename(p), _SPEAKER_THRESHOLD)
                return
            except Exception as e:
                log.warning("[Speaker] Error cargando perfil: %s", e)
    log.info("[Speaker] Sin perfil de voz — wake word obligatoria (di '%s' para activar)", os.getenv("WAKE_WORD", "nova"))

def _is_my_voice(wav_bytes: bytes) -> bool:
    """Verifica si el audio pertenece al usuario enrollado usando MFCC."""
    if not _SPEAKER_VERIFY or _SPEAKER_PROFILE is None:
        return True   # sin perfil → acepta todo

    # Si Nova está hablando o acaba de hablar, rechazar siempre — es eco
    if _nova_speaking or time.time() < _tts_until:
        return False

    try:
        import numpy as np
        import librosa
        import io
        y, _ = librosa.load(io.BytesIO(wav_bytes), sr=16000, mono=True)
        if len(y) < 16000 * 0.3:
            return False
        mfccs = librosa.feature.mfcc(y=y, sr=16000, n_mfcc=40)
        feats = np.concatenate([mfccs.mean(axis=1), mfccs.std(axis=1)])
        norm  = np.linalg.norm(feats)
        if norm == 0:
            return False
        feats = feats / norm
        sim = float(np.dot(_SPEAKER_PROFILE, feats))
        log.debug("[Speaker] similitud=%.3f umbral=%.2f", sim, _SPEAKER_THRESHOLD)
        return sim >= _SPEAKER_THRESHOLD
    except Exception as e:
        log.warning("[Speaker] Error verificando voz: %s — rechazando por seguridad", e)
        return False   # falla → rechazar (no abrir a cualquier voz)

# ─── Single instance lock ────────────────────────────────────────────────────
_PID_FILE = os.path.expanduser("__DOTNOVA_PATH__/nova.pid")

def _acquire_lock() -> bool:
    os.makedirs(os.path.dirname(_PID_FILE), exist_ok=True)
    if os.path.exists(_PID_FILE):
        try:
            old_pid = int(open(_PID_FILE).read().strip())
            os.kill(old_pid, 0)          # comprueba si el proceso existe
            print(f"[Nova] Ya hay una instancia corriendo (PID {old_pid}). Saliendo.")
            return False
        except (ProcessLookupError, ValueError):
            pass                          # proceso muerto, el lock es stale
    with open(_PID_FILE, "w") as f:
        f.write(str(os.getpid()))
    atexit.register(lambda: os.path.exists(_PID_FILE) and os.remove(_PID_FILE))
    return True

import speech_recognition as sr

from nova.utils.nova_hud import NovaHUD
from nova.core.nova_router import NovaRouter
from nova.tools.nova_neuro_memory import neuro_memory as nova_memory
from nova.tools.nova_skills import skills

# ─── Configuración ───────────────────────────────────────────────────────────

MAX_HISTORY   = 15
EXIT_WORDS    = {"salir", "adiós", "adios", "chau", "exit", "quit", "bye",
                 "apágate", "hasta luego"}
TIER_LABELS   = {1: "FREE", 2: "MID", 3: "PREMIUM"}

# ─── Configuración de voz ────────────────────────────────────────────────────
# Voz principal: edge-tts neural (con fallback a macOS say si no hay internet).
# Cambiá EDGE_VOICE en .env para elegir la voz neural.
# Voces recomendadas: es-AR-TomasNeural, es-ES-AlvaroNeural, es-UY-MateoNeural
EDGE_VOICE    = os.getenv("EDGE_VOICE", "es-AR-TomasNeural")
EDGE_RATE     = os.getenv("EDGE_RATE", "+0%")   # ej: "+10%", "-5%"
EDGE_PITCH    = os.getenv("EDGE_PITCH", "+0Hz")  # ej: "+5Hz"

# Voz macOS fallback
NOVA_VOICE  = os.getenv("NOVA_VOICE", "Reed (Español (España))")
VOICE_RATE    = os.getenv("NOVA_VOICE_RATE", "150")

FOLLOWUP_WINDOW_SEC = int(os.getenv("FOLLOWUP_WINDOW_SEC", "33"))
REQUIRE_WAKE_WORD   = os.getenv("REQUIRE_WAKE_WORD", "1").strip() != "0"

# ─── Idioma de sesión (explícito, activado por el usuario) ───────────────────
# El usuario dice "habla en inglés" / "vuelve al español" para cambiar.
# NO se auto-detecta — evita activaciones accidentales por descripciones de APIs.

_SESSION_LANG: str = "es"   # idioma activo en la sesión actual

_LANG_NAMES: dict[str, str] = {
    "es": "español",
    "en": "inglés",
    "fr": "francés",
    "pt": "portugués",
    "de": "alemán",
    "it": "italiano",
    "ru": "ruso",
    "zh": "chino",
    "ja": "japonés",
    "ar": "árabe",
}

# Mapa de palabras clave → código ISO para skill_cambiar_idioma
_LANG_KEYWORDS: dict[str, str] = {
    "español": "es", "castellano": "es", "spanish": "es",
    "inglés": "en", "ingles": "en", "english": "en",
    "francés": "fr", "frances": "fr", "french": "fr",
    "portugués": "pt", "portugues": "pt", "portuguese": "pt",
    "alemán": "de", "aleman": "de", "german": "de", "deutsch": "de",
    "italiano": "it", "italian": "it",
    "ruso": "ru", "russian": "ru",
    "chino": "zh", "chinese": "zh", "mandarín": "zh",
    "japonés": "ja", "japones": "ja", "japanese": "ja",
    "árabe": "ar", "arabe": "ar", "arabic": "ar",
}

# edge-tts voices para idiomas no-español
_LANG_EDGE_VOICES: dict[str, str] = {
    "en": os.getenv("EDGE_VOICE_EN", "en-US-GuyNeural"),
    "fr": os.getenv("EDGE_VOICE_FR", "fr-FR-HenriNeural"),
    "pt": os.getenv("EDGE_VOICE_PT", "pt-BR-AntonioNeural"),
    "de": os.getenv("EDGE_VOICE_DE", "de-DE-ConradNeural"),
    "it": os.getenv("EDGE_VOICE_IT", "it-IT-DiegoNeural"),
    "ru": os.getenv("EDGE_VOICE_RU", "ru-RU-DmitryNeural"),
    "zh": os.getenv("EDGE_VOICE_ZH", "zh-CN-YunxiNeural"),
}

# macOS say voices para idiomas no-español
_LANG_MAC_VOICES: dict[str, str] = {
    "en": os.getenv("NOVA_VOICE_EN", "Samantha"),
    "fr": os.getenv("NOVA_VOICE_FR", "Thomas"),
    "pt": os.getenv("NOVA_VOICE_PT", "Luciana"),
}


def set_session_lang(lang_code: str) -> str:
    """Cambia el idioma de sesión. Retorna mensaje de confirmación."""
    global _SESSION_LANG
    _SESSION_LANG = lang_code
    name = _LANG_NAMES.get(lang_code, lang_code)
    return f"Perfecto, Señor. A partir de ahora hablo en {name}."


# ─── TTS con barge-in ────────────────────────────────────────────────────────

BARGE_IN_THRESHOLD = float(os.getenv("BARGE_IN_THRESHOLD", "600"))
# Segundos de silencio post-TTS antes de volver a escuchar (evita eco acústico)
TTS_COOLDOWN = float(os.getenv("TTS_COOLDOWN", "0.8"))

_say_proc: subprocess.Popen | None = None   # proceso activo (say o afplay)
_tmp_audio: str | None = None               # archivo mp3 temporal de edge-tts
_tts_until: float = 0.0                     # timestamp hasta el que no escuchar (eco post-TTS)
_nova_speaking: bool = False                # True mientras TTS reproduce activamente


def interrupt_speech() -> None:
    """Mata el proceso de audio activo."""
    global _say_proc
    if _say_proc and _say_proc.poll() is None:
        try:
            _say_proc.kill()
        except:
            pass
        _say_proc = None


def _speak_edge(text: str) -> bool:
    """
    Genera audio con edge-tts y lo reproduce con afplay.
    Devuelve True si tuvo éxito, False si hay error de red o edge-tts no está disponible.
    """
    global _say_proc, _tmp_audio
    if not _EDGE_TTS_AVAILABLE:
        return False
    try:
        # Crea archivo temporal
        fd, fpath = tempfile.mkstemp(suffix=".mp3")
        os.close(fd)
        _tmp_audio = fpath

        async def _gen():
            comm = _edge_tts.Communicate(text, EDGE_VOICE,
                                          rate=EDGE_RATE, pitch=EDGE_PITCH)
            await comm.save(fpath)

        # asyncio.run() raises RuntimeError if called from a thread that already
        # has a running event loop.  Detect this and run in a fresh thread instead.
        try:
            asyncio.get_running_loop()
            _loop_running = True
        except RuntimeError:
            _loop_running = False

        if _loop_running:
            # Spin up a dedicated thread with its own event loop.
            import concurrent.futures

            def _run_in_thread():
                asyncio.run(_gen())

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(_run_in_thread)
                future.result(timeout=30)
        else:
            asyncio.run(_gen())

        if not os.path.exists(fpath) or os.path.getsize(fpath) < 100:
            return False

        from nova.platform import play_audio
        _say_proc = play_audio(fpath)
        return True
    except Exception as e:
        print(f"  [edge-tts] error: {e} → fallback a say")
        return False


def _clean_for_speech(text: str) -> str:
    """Elimina markdown y símbolos que el TTS lee literalmente."""
    # Emojis y símbolos Unicode extendidos (bloques U+1F000-U+1FFFF, U+2600-U+27BF, etc.)
    text = re.sub(
        r'[\U0001F000-\U0001FFFF'
        r'\U00002600-\U000027BF'
        r'\U0000FE00-\U0000FE0F'
        r'\U00002300-\U000023FF'
        r'\U00002B00-\U00002BFF'
        r'\U0000E000-\U0000F8FF'
        r'\U000024C2-\U0001F251]+',
        '', text
    )
    # Etiquetas de proveedor [via X] y [SKILL LOCAL] etc.
    text = re.sub(r'\[[^\]]{0,40}\]', '', text)
    # Markdown negrita/cursiva
    text = re.sub(r'\*{1,3}([^*\n]+)\*{1,3}', r'\1', text)
    # Bullets • * - al inicio de línea
    text = re.sub(r'^\s*[•\*\-]\s+', '', text, flags=re.MULTILINE)
    # Numeración de lista "1. "
    text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)
    # Rutas de archivo → solo el nombre de archivo (evita leer "barra diagonal")
    text = re.sub(r'~?/[\w.\-]+(?:/[\w.\-]+)+', lambda m: m.group().rsplit('/', 1)[-1], text)
    # Barras sueltas restantes → espacio
    text = text.replace('/', ' ').replace('\\', ' ')
    # Bullets en medio de línea (•)
    text = re.sub(r'\s*[•]\s*', ', ', text)
    # Caracteres sueltos que el TTS pronuncia: # _ ` ~
    text = re.sub(r'[#_`~]', '', text)
    # Espacios múltiples y líneas vacías extra
    text = re.sub(r'[ \t]{2,}', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def speak(text: str, hud: NovaHUD, lang: str = "es") -> None:
    """
    Reproduce texto con barge-in.
    Intenta edge-tts neural primero; si falla (sin internet, error), usa macOS say.
    lang: ISO 639-1 code — selecciona voz adecuada para idiomas no-español.
    """
    global _say_proc, _tmp_audio, EDGE_VOICE, NOVA_VOICE, _nova_speaking, _tts_until

    interrupt_speech()  # Detener cualquier iteración anterior instantáneamente.

    _nova_speaking = True
    hud.put_state(status="SPEAKING")
    clean = _clean_for_speech(text)
    voice_text = clean if len(clean) <= 1500 else clean[:1500] + "."

    # ── Seleccionar voz según idioma ─────────────────────────────────────────
    _orig_edge  = EDGE_VOICE
    _orig_mac   = NOVA_VOICE
    if lang != "es":
        EDGE_VOICE  = _LANG_EDGE_VOICES.get(lang, EDGE_VOICE)
        NOVA_VOICE  = _LANG_MAC_VOICES.get(lang, NOVA_VOICE)

    # ── Intentar edge-tts ───────────────────────────────────────────────────
    edge_ok = _speak_edge(voice_text)

    # ── Fallback TTS nativo del sistema ─────────────────────────────────────
    if not edge_ok:
        from nova.platform import speak_tts
        _say_proc = speak_tts(voice_text, voice=NOVA_VOICE, rate=VOICE_RATE)

    # Restaurar voces originales
    EDGE_VOICE = _orig_edge
    NOVA_VOICE = _orig_mac

    # ── Barge-in mientras reproduce ──────────────────────────────────────────
    if _say_proc:
        _monitor_barge_in(_say_proc)
        if _say_proc and _say_proc.poll() is None:
            _say_proc.wait()
        _say_proc = None

    # Limpiar archivo temporal de edge-tts
    if _tmp_audio:
        try:
            os.unlink(_tmp_audio)
        except Exception:
            pass
        _tmp_audio = None

    # Cooldown: no escuchar hasta que el eco acústico de la habitación se disipe
    _nova_speaking = False
    _tts_until = time.time() + TTS_COOLDOWN
    hud.put_state(status="IDLE")


def _monitor_barge_in(proc: subprocess.Popen) -> None:
    """
    Abre el micrófono y monitorea energía de audio.
    Si BARGE_IN_THRESHOLD == 0 → desactivado, espera que say termine solo.
    """
    if BARGE_IN_THRESHOLD == 0:
        proc.wait()
        return

    # ── sounddevice (Windows/Linux sin compilación) ───────────────────────────
    if _SOUNDDEVICE_AVAILABLE:
        CHUNK = 1024
        RATE  = 16000
        try:
            # Warmup ~0.45 s
            for _ in range(7):
                if proc.poll() is not None:
                    return
                _sd.rec(CHUNK, samplerate=RATE, channels=1, dtype="int16")
                _sd.wait()
            # Monitoreo activo
            while proc.poll() is None:
                chunk = _sd.rec(CHUNK, samplerate=RATE, channels=1, dtype="int16")
                _sd.wait()
                energy = int(_np_audio.sqrt(_np_audio.mean(chunk.astype("float32") ** 2)))
                if energy > BARGE_IN_THRESHOLD:
                    proc.kill()
                    print("\n  [barge-in] interrumpido por el usuario")
                    return
        except Exception:
            pass
        return

    # ── PyAudio (macOS/Linux con PyAudio instalado) ───────────────────────────
    if _PYAUDIO_AVAILABLE and _AUDIOOP_AVAILABLE:
        pa     = _pyaudio.PyAudio()
        stream = None
        try:
            stream = pa.open(
                format=_pyaudio.paInt16,
                channels=1,
                rate=16000,
                input=True,
                frames_per_buffer=1024,
            )
            for _ in range(7):
                if proc.poll() is not None:
                    return
                stream.read(1024, exception_on_overflow=False)
            while proc.poll() is None:
                data   = stream.read(1024, exception_on_overflow=False)
                energy = audioop.rms(data, 2)
                if energy > BARGE_IN_THRESHOLD:
                    proc.kill()
                    print("\n  [barge-in] interrumpido por el usuario")
                    return
        except Exception:
            pass
        finally:
            if stream:
                stream.stop_stream()
                stream.close()
            pa.terminate()
        return

    # ── Fallback: sin audio, esperar que termine solo ─────────────────────────
    proc.wait()


# ─── Wake word ───────────────────────────────────────────────────────────────

# Leído del .env — cambia WAKE_WORD para renombrar al asistente
_WAKE_BASE  = os.getenv("WAKE_WORD", "nova").lower().strip()
ASSISTANT_NAME = os.getenv("ASSISTANT_NAME", "Auxiliar")

# Google STT a veces transcribe "Nova" como estas variantes
_EXTRA_VARIANTS: dict[str, list[str]] = {
    "nova":   ["novah", "novas", "noba", "bova"],
    # Variantes cortas removidas ("a", "ova") — demasiados falsos positivos
}

WAKE_WORDS: set[str] = {
    _WAKE_BASE,
    _WAKE_BASE + ",",
    _WAKE_BASE + ".",
    f"oye {_WAKE_BASE}",
    f"hey {_WAKE_BASE}",
    f"ey {_WAKE_BASE}",
    _WAKE_BASE[:-1] if len(_WAKE_BASE) > 3 else _WAKE_BASE,
}
# Añadir variantes conocidas para el wake word actual
for _v in _EXTRA_VARIANTS.get(_WAKE_BASE, []):
    WAKE_WORDS.add(_v)
    WAKE_WORDS.add(f"oye {_v}")
    WAKE_WORDS.add(f"hey {_v}")

# Variantes "débiles" — solo activan si van seguidas de un comando conocido
_WEAK_VARIANTS: set[str] = set()

# "no va" es la transcripción más frecuente de "nova" → agregar como débil
if _WAKE_BASE == "nova":
    for _wv in ["no va", "nova,", "no,va"]:
        WAKE_WORDS.add(_wv)
        _WEAK_VARIANTS.add(_wv)

# Palabras de acción que confirman que es un comando real (no diálogo de tele)
_COMMAND_STARTERS = {
    # Acciones del sistema
    "abre", "abrir", "cierra", "cerrar", "inicia", "lanza", "ejecuta",
    "busca", "buscar", "encuentra", "muestra", "lista", "listar",
    "corre", "pon", "sube", "baja", "silencia", "silenciar",
    "captura", "screenshot", "toma", "saca",
    "recuerda", "olvida", "guarda", "anota",
    "piloto", "maneja", "opera", "toma", "hazlo",
    "cambia", "cambiame", "habla", "hablar",
    "reinicia", "reiniciar", "reiniciate", "restart",
    "temporizador", "timer", "alarma", "volumen",
    "salir", "sal", "apágate", "adiós", "adios", "chau",
    # Tema HUD
    "siguiente", "tema", "anterior",
    # Música
    "reproduce", "reproducir", "pausa", "pausar", "música", "musica",
    "canción", "cancion", "pista", "siguiente", "anterior", "play",
    "pause", "skip", "toca", "tocar", "shuffle", "aleatorio",
    # Notas / dictado
    "anota", "apunta", "nota", "notas", "escribe", "redacta", "dicta",
    "inicio", "iniciar", "inicializar", "comenzar", "finalizar",
    # Preguntas
    "qué", "que", "cuál", "cual", "cuándo", "cuando",
    "cómo", "como", "cuánto", "cuanto", "quién", "quien", "dónde", "donde",
    "dime", "di", "cuéntame", "cuentame", "explícame", "explicame",
    # Otras intenciones comunes
    "hay", "puedes", "puedo", "necesito", "quiero", "ayuda",
    "eres", "sabes", "tienes", "qué hora", "hora", "fecha",
}

def _extract_command(text: str) -> str | None:
    """
    Devuelve el comando después del wake word, o None si no hay wake word.
    Las variantes débiles ("a", "ova") solo activan si el comando empieza
    con una palabra de acción reconocida — filtra diálogo de TV.
    """
    lower = text.lower().strip()
    for ww in sorted(WAKE_WORDS, key=len, reverse=True):  # más largo primero
        if lower.startswith(ww):
            cmd = text[len(ww):].strip(" ,.:").strip()
            # Variante débil: primera palabra del comando debe ser acción conocida
            if ww in _WEAK_VARIANTS:
                first_word = cmd.split()[0].lower() if cmd.split() else ""
                if first_word not in _COMMAND_STARTERS:
                    continue
            return cmd
    return None


def _looks_like_direct_command(text: str) -> bool:
    lower = text.lower().strip()
    words = lower.split()
    if not words:
        return False
    first = words[0]
    if first in _COMMAND_STARTERS:
        return True
    if len(words) >= 4 and any(k in lower for k in ("quiero", "necesito", "puedes", "podés", "ayuda")):
        return True
    return False


# ─── STT ─────────────────────────────────────────────────────────────────────

def listen(
    recognizer: sr.Recognizer,
    mic: sr.Microphone,
    hud: NovaHUD,
    context_active: bool = False,
    dictation_mode: bool = False,
) -> str | None:
    """
    Escucha continuamente.
    - Wake word obligatorio por defecto.
    - Tras activación, mantiene una ventana de contexto para follow-ups.
    - En modo dictado, todo texto reconocido se toma como contenido.
    """
    # No escuchar mientras el eco post-TTS pueda contaminar el micrófono
    if time.time() < _tts_until:
        hud.put_state(status="IDLE")
        return None

    hud.put_state(status="LISTENING")
    try:
        with mic as source:
            # timeout=5: si no detecta voz en 5s regresa (no cuelga)
            # phrase_time_limit: máximo tiempo de grabación; default 18s
            _ptl = float(os.getenv("PHRASE_TIME_LIMIT", "18"))
            audio = recognizer.listen(source, timeout=5, phrase_time_limit=_ptl)
    except sr.WaitTimeoutError:
        hud.put_state(status="IDLE")
        return None

    # ── Verificación de hablante (si hay perfil enrollado) ─────────────────────
    if _SPEAKER_VERIFY:
        wav_bytes = audio.get_wav_data()
        if not _is_my_voice(wav_bytes):
            hud.put_state(status="IDLE")
            return None   # voz de otra persona → ignorar sin print

    try:
        # "es" cubre todas las variantes del español (AR, ES, MX…)
        text = recognizer.recognize_google(audio, language="es")
    except sr.UnknownValueError:
        log.debug("[STT] audio capturado pero no reconocido (ruido/silencio)")
        hud.put_state(status="IDLE")
        return None
    except sr.RequestError as e:
        log.warning("[STT] error Google: %s", e)
        hud.put_state(status="IDLE")
        return None

    if dictation_mode:
        hud.put_state(status="THINKING", user_text=text)
        return text.strip()

    # Con perfil de voz verificado → saltamos wake word (ya sabemos que es el usuario)
    if _SPEAKER_VERIFY:
        hud.put_state(status="THINKING", user_text=text)
        return text.strip()

    # Sin perfil de voz: wake word SIEMPRE obligatoria para evitar activaciones por música/TV
    cmd = _extract_command(text)

    if cmd is None:
        # Excepción legítima: estamos en medio de una conversación activa
        if context_active and len(text.strip().split()) >= 2:
            hud.put_state(status="THINKING", user_text=text)
            return text.strip()
        # Sin wake word y sin perfil → ignorar siempre (aunque REQUIRE_WAKE_WORD=0)
        log.debug("[STT] ignorado sin wake word (sin perfil de voz): '%s'", text[:50])
        hud.put_state(status="IDLE")
        return None

    # Wake word detectado
    hud.put_state(status="THINKING", user_text=text)
    if cmd == "":
        return "__wake_only__"   # solo "Nova" sin comando → saludo
    return cmd


# ─── Construcción del contexto para el LLM ───────────────────────────────────

_VAULT_SEARCH_TRIGGERS = re.compile(
    r"(?:recuerda(?:s)?|sabes|tienes?\s+(?:algo|datos?|info)|"
    r"busca\s+en|cerebro|vault|obsidian|notas?|diario|memoria|"
    r"qu[eé]\s+(?:sé|s[eé]|sabes?|tengo|hay)\s+(?:sobre|de)|"
    r"dame\s+(?:info|datos?|contexto)|anota(?:ste)?|apunt[aó]|"
    r"recuerd[ao]|acuerdo|reunión|proyect[oa])",
    re.IGNORECASE,
)


def _vault_context_for(user_text: str) -> str:
    """Busca el vault solo si la consulta parece necesitar contexto de Obsidian."""
    if not _VAULT_SEARCH_TRIGGERS.search(user_text):
        return ""
    # Extraer términos clave (eliminar stop words cortas)
    stop = {"en", "el", "la", "de", "que", "y", "a", "me", "se", "si", "no",
            "lo", "es", "un", "una", "hay", "qué", "sobre", "tengo", "sabes"}
    terms = [w for w in re.findall(r"\b\w{4,}\b", user_text.lower()) if w not in stop]
    if not terms:
        return ""
    query = " ".join(terms[:5])
    try:
        result = nova_memory.vault_search_text(query, top_k=3)
        if result:
            return result
    except Exception:
        pass
    # Fallback file-based: usa nova_cerebro que busca en TODO el vault
    try:
        from nova.connectors.nova_cerebro import cerebro_buscar
        resultados = cerebro_buscar(query, max_resultados=3)
        if resultados:
            lines = [f"[Cerebro: '{query}']"]
            for r in resultados:
                lines.append(f"• {r['titulo']} ({r['archivo']}): {r['extracto'][:150]}")
            return "\n".join(lines)
    except Exception:
        pass
    return ""


def _build_messages(history: list[dict], base_system: str, extra_context: str = "") -> tuple[list[dict], str]:
    """
    Returns (messages, session_lang).
    session_lang es el idioma activo (_SESSION_LANG) — cambia solo cuando el
    usuario lo pide explícitamente con "habla en inglés" / "vuelve al español".
    """
    facts = nova_memory.get_all_facts()
    system = base_system
    system += (
        "\n\n[Skills locales disponibles]\n"
        + skills.capabilities_summary()
        + "\nSi una orden no está clara, haz una sola pregunta de aclaración concreta."
    )
    if facts:
        system += f"\n\n{facts}"

    # Búsqueda dinámica en el Cerebro (Obsidian vault) si es relevante
    _raw_last = next(
        (m["content"] for m in reversed(history) if m.get("role") == "user"), ""
    )
    # Normalizar: si es multimodal (list), extraer solo el texto
    if isinstance(_raw_last, list):
        last_user = " ".join(
            p.get("text", "") for p in _raw_last
            if isinstance(p, dict) and p.get("type") == "text"
        ).strip()
    else:
        last_user = _raw_last or ""
    vault_ctx = _vault_context_for(last_user) if last_user else ""
    if vault_ctx:
        system += f"\n\n{vault_ctx}"

    if extra_context:
        system += f"\n\n[Información en tiempo real]\n{extra_context}"

    # Idioma de sesión: el usuario lo activa explícitamente ("habla en inglés")
    if _SESSION_LANG != "es":
        lang_name = _LANG_NAMES.get(_SESSION_LANG, _SESSION_LANG)
        system += f"\n\nResponde SIEMPRE en {lang_name}. El usuario ha solicitado este idioma."

    msgs = [{"role": "system", "content": system}]
    # Filtrar roles "system" y normalizar content multimodal (imágenes en historial rompen Groq 400)
    for m in history[-(MAX_HISTORY * 2):]:
        if m.get("role") == "system":
            continue
        content = m.get("content", "")
        if isinstance(content, list):
            # Extraer solo partes de texto — descartar image_url para APIs text-only
            parts = [
                p.get("text", "") if isinstance(p, dict) else str(p)
                for p in content
                if not (isinstance(p, dict) and p.get("type") == "image_url")
            ]
            content = " ".join(p for p in parts if p).strip() or "[imagen]"
        elif not isinstance(content, str):
            content = str(content)
        msgs.append({"role": m["role"], "content": content or " "})
    return msgs, _SESSION_LANG


# ─── Loop principal de NOVA (corre en hilo background) ─────────────────────

def _calibrate_recognizer(recognizer: sr.Recognizer, mic: sr.Microphone) -> None:
    """
    Calibra el umbral de energía contra el ruido ambiente actual
    (TV, ventiladores, etc.). Escucha 3 segundos y ajusta automáticamente.
    Luego multiplica por un factor para exigir voces más cercanas.
    """
    print("  [calibrando ruido ambiente... 3 segundos]")
    with mic as source:
        recognizer.adjust_for_ambient_noise(source, duration=3)

    factor = float(os.getenv("NOISE_FILTER_FACTOR", "1.5"))
    recognizer.energy_threshold *= factor
    recognizer.dynamic_energy_threshold = True   # se sigue ajustando mientras escucha
    recognizer.dynamic_energy_adjustment_damping = 0.10  # adapta lento (más estable)
    # Pausa más larga antes de cortar — evita que corte en medio de una oración
    # 2.5s de pausa antes de cortar — evita que corte mid-sentence
    recognizer.pause_threshold = float(os.getenv("PAUSE_THRESHOLD", "2.5"))
    # 1.8s de silencio final antes de cerrar la frase
    recognizer.non_speaking_duration = float(os.getenv("NON_SPEAKING_DURATION", "1.8"))

    print(f"  [umbral inicial: {recognizer.energy_threshold:.0f} (TV x{factor}) — pausa={recognizer.pause_threshold}s]")


def _nova_loop(hud: NovaHUD, stop_event: threading.Event) -> None:
    recognizer = sr.Recognizer()
    mic        = sr.Microphone()

    # Cargar perfil de voz (speaker verification)
    _load_speaker_profile()

    # Calibrar contra el ruido ambiente ANTES de empezar
    _calibrate_recognizer(recognizer, mic)

    try:
        router = NovaRouter()
    except EnvironmentError as e:
        print(f"\n[ERROR] {e}\n")
        stop_event.set()
        return

    # Inyectar Router y Callback de notificaciones en las skills
    skills.set_router(router)
    skills.set_notify_callback(lambda text: speak(text, hud))

    # ── Cargar contexto del Gran Cerebro al sistema ───────────────────────────
    try:
        vault_ctx = nova_memory.load_vault_context()
    except AttributeError:
        vault_ctx = ""
    if vault_ctx:
        router.system_prompt = router.system_prompt + (
            "\n\n[CONTEXTO DEL GRAN CEREBRO — actualizado al arrancar]\n"
            + vault_ctx
        )
        print(f"  [Cerebro] Contexto cargado ({len(vault_ctx)} chars)")
    else:
        print("  [Cerebro] Vault no disponible o vacío — continuando sin contexto.")

    history: list[dict] = nova_memory.get_recent_turns(MAX_HISTORY * 2)
    last_activation_ts = 0.0
    dictation_mode = False
    is_muted = False

    # ── Callback para el input de texto del HUD ───────────────
    def _on_text_input(text: str) -> None:
        nonlocal is_muted, dictation_mode
        interrupt_speech()

        # ── Señales internas del HUD ──────────────────────────
        if text.strip() == "toggle_mute":
            is_muted = not is_muted
            hud.put_state(status="ASLEEP" if is_muted else "IDLE")
            if not is_muted:
                speak("A sus órdenes, Señor.", hud)
            return

        if text.strip() == "wake_up":
            # Click corto en el HUD → despertar si está dormido
            if is_muted:
                is_muted = False
                hud.put_state(status="IDLE")
                speak("A sus órdenes, Señor.", hud)
            return

        if not text.strip():
            return

        # ── Si estaba dormido, despertar primero ──────────────
        if is_muted:
            is_muted = False
            hud.put_state(status="IDLE")

        if text.lower().strip() in ["apagar", "dormir", "suspender", "silenciar"]:
            is_muted = True
            hud.put_state(status="ASLEEP")
            speak("Suspendido.", hud)
            return

        if text.lower().strip() in ["activar", "despertar"]:
            is_muted = False
            hud.put_state(status="IDLE")
            speak("A sus órdenes, Señor.", hud)
            return

        # ── Imagen adjunta desde el HUD (📎 botón) ───────────────────────────
        if text.startswith("__HUD_IMG__:"):
            # Formato: __HUD_IMG__:filename:mime:b64data[::caption]
            try:
                rest = text[len("__HUD_IMG__:"):]
                # Separar fname, mime (máx 2 splits), luego el resto
                header_parts = rest.split(":", 2)
                if len(header_parts) < 3:
                    raise ValueError(f"Formato inválido: {len(header_parts)} partes")
                fname, mime, remainder = header_parts
                # Separar b64 del caption opcional (separados por "::")
                if "::" in remainder:
                    b64, caption = remainder.split("::", 1)
                    caption = caption.strip() or "¿Qué ves en esta imagen?"
                else:
                    b64 = remainder
                    caption = "Describe detalladamente lo que ves en esta imagen."
                hud.put_state(status="THINKING", user_text=f"[imagen: {fname}]")
                data_url = f"data:{mime};base64,{b64}"
                # Construir mensajes directamente — NO pasar por _build_messages
                # que stripea las imágenes para APIs text-only
                msgs = [{"role": "system", "content": router.system_prompt}]
                # Agregar historial reciente solo con texto (para contexto)
                for m in history[-(MAX_HISTORY * 2):]:
                    if m.get("role") == "system":
                        continue
                    c = m.get("content", "")
                    if isinstance(c, list):
                        c = " ".join(p.get("text","") for p in c if isinstance(p,dict) and p.get("type")=="text")
                    msgs.append({"role": m["role"], "content": c or " "})
                # Mensaje final con imagen
                msgs.append({
                    "role": "user",
                    "content": [
                        {"type": "text",      "text": caption},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ]
                })
                result = router.route(msgs)
                resp   = result.get("response", "")
                # Guardar en history como texto (la imagen no se necesita en el historial)
                history.append({"role": "user",      "content": f"[imagen: {fname}] {caption}"})
                history.append({"role": "assistant", "content": resp})
                if resp:
                    speak(resp[:300], hud)
                    hud.put_state(
                        status="SPEAKING", response_text=resp,
                        model_info=result.get("model_info", ""),
                        tokens_used=result.get("tokens_used", 0),
                        provider=result.get("provider", ""),
                        budget_remaining_pct=result.get("budget_remaining_pct", 100.0),
                    )
                else:
                    speak("No pude analizar la imagen. Prueba con otro modelo.", hud)
            except Exception as e:
                log.warning("[HUD] Error procesando imagen adjunta: %s", e)
                speak("Tuve un problema procesando la imagen.", hud)
            return

        log.debug("Tú [texto]: %s", text[:80])
        hud.put_state(status="THINKING")   # user_text ya fue logueado por _on_text_submit
        nova_memory.save_turn("user", text)
        skill_resp = skills.dispatch(text)
        if skill_resp:
            print(f"Auxiliar: {skill_resp}")
            hud.put_state(status="SKILL", response_text=skill_resp, model_info="[SKILL LOCAL]")
            # Guardar en history para que el LLM tenga contexto de lo que se ejecutó
            history.append({"role": "user", "content": text})
            history.append({"role": "assistant", "content": skill_resp})
            nova_memory.save_turn("assistant", skill_resp)
            speak(skill_resp, hud)
            return
        history.append({"role": "user", "content": text})
        # Buscar contexto web si hace falta
        extra = ""
        if skills.needs_web_search(text):
            print("  [búsqueda web...]")
            extra = skills.web_search_for_llm(text)
        try:
            msgs, resp_lang = _build_messages(history, router.system_prompt, extra)
            result = router.route(msgs)
            response = result["response"]
            history.append({"role": "assistant", "content": response})
            nova_memory.save_turn("assistant", response)
            tier   = result.get("tier", "?")
            model  = result.get("model", "?")
            tokens = result.get("tokens_used", 0)
            provider   = result.get("provider", "?")
            budget_pct = result.get("budget_remaining_pct", 100.0)
            model_info = f"Tier {tier} {TIER_LABELS.get(tier,'?')} | {model} | {tokens} tk"
            print(f"Auxiliar: {response}")
            hud.put_state(
                status="SPEAKING", response_text=response, model_info=model_info,
                tokens_used=tokens, provider=provider, budget_remaining_pct=budget_pct,
            )
            speak(response, hud, lang=resp_lang)
        except Exception as e:
            err = f"Error al procesar: {e}"
            print(f"  [ERROR] {err}")
            hud.put_state(status="IDLE", response_text=err)

    hud.set_text_callback(_on_text_input)

    if _SPEAKER_VERIFY:
        greeting = (
            f"Sistema {ASSISTANT_NAME} activado con reconocimiento de voz. "
            f"Solo respondo a usted, Señor. No necesita palabra de activación."
        )
    elif REQUIRE_WAKE_WORD:
        greeting = (
            f"Sistema {ASSISTANT_NAME} activado. "
            f"Di {_WAKE_BASE.capitalize()} para hablar conmigo, Señor. "
            f"mantengo contexto por {FOLLOWUP_WINDOW_SEC} segundos."
        )
    else:
        greeting = (
            f"Sistema {ASSISTANT_NAME} activado en modo manos libres, Señor. "
            f"Puedo responder sin wake word."
        )
    print(f"\n{'═'*56}")
    print(f"  {ASSISTANT_NAME.upper()} v2.0 — Agente Total")
    print(f"  Voz: {NOVA_VOICE}  |  Wake word: '{_WAKE_BASE.capitalize()}'")
    print(f"  Di '{_WAKE_BASE.capitalize()} salir' para terminar.")
    print(f"{'═'*56}\n")
    print(f"Auxiliar: {greeting}")
    hud.put_state(status="SPEAKING", response_text=greeting)
    speak(greeting, hud)

    while not stop_event.is_set():
        if is_muted:
            time.sleep(0.2)
            continue

        context_active = (time.time() - last_activation_ts) <= FOLLOWUP_WINDOW_SEC

        # ── Escuchar ───────────────────────────────────────────
        user_input = listen(
            recognizer,
            mic,
            hud,
            context_active=context_active or dictation_mode,
            dictation_mode=dictation_mode,
        )
        if not user_input:
            continue

        # ── Solo "Nova" sin comando → saludo breve ──────────
        if user_input == "__wake_only__":
            ack = "¿Sí, Señor?"
            print(f"\nAuxiliar: {ack}")
            hud.put_state(status="SPEAKING", user_text="Nova", response_text=ack)
            speak(ack, hud)
            last_activation_ts = time.time()
            continue

        # ── Dictado continuo ──────────────────────────────────
        lower_input = user_input.lower().strip()

        # Regex robusto para DETENER el dictado (tolera artículos, wake words, variantes STT)
        _RE_STOP_DICTATION = re.compile(
            r"(?:fin|detener?|salir?|finalizar?|parar?|terminar?|stop)\s+(?:el\s+)?dictado"
            r"|fin\s+de\s+(?:el\s+)?dictado"
        )
        # Regex robusto para INICIAR el dictado
        _RE_START_DICTATION = re.compile(
            r"(?:modo|activar?|iniciar?|inicio|empezar?|comenzar?|start|dictar)\s+(?:el\s+)?dictado"
            r"|dictado\s+continuo"
        )

        if dictation_mode:
            if _RE_STOP_DICTATION.search(lower_input):
                dictation_mode = False
                done = "Dictado finalizado, Señor."
                print(f"Auxiliar: {done}")
                hud.put_state(status="SPEAKING", response_text=done)
                speak(done, hud)
                last_activation_ts = time.time()
                continue
            # Escribir en la app activa usando clipboard (más rápido y confiable)
            skills.type_in_active_app(user_input + " ")
            print(f"  [DICTADO] {user_input}")
            hud.put_state(status="SKILL", response_text=f"✍ {user_input[:50]}", model_info="[DICTADO]")
            last_activation_ts = time.time()
            continue

        print(f"\nTú:       {user_input}")
        hud.put_state(user_text=user_input)
        last_activation_ts = time.time()

        if _RE_START_DICTATION.search(lower_input):
            dictation_mode = True
            msg = (
                "Dictado iniciado. Habla y escribiré todo en la app activa. "
                "Di 'finalizar dictado' para detenerme."
            )
            print(f"Auxiliar: {msg}")
            hud.put_state(status="SPEAKING", response_text=msg)
            speak(msg, hud)
            continue

        # ── Salir → suspender (no cerrar) ────────────────────────
        if lower_input in EXIT_WORDS:
            is_muted = True
            hud.put_state(status="ASLEEP")
            speak("Suspendido. Haga click o escriba para despertar, Señor.", hud)
            continue

        # ── Cerrar de verdad ──────────────────────────────────
        if lower_input in {"cerrar nova", "apagar nova", "terminar nova",
                            "cerrar completamente", "apagar completamente"}:
            stats    = router.get_session_summary()
            farewell = f"Cerrando. Usé {stats['total_tokens']} tokens. Hasta pronto, Señor."
            print(f"Auxiliar: {farewell}")
            hud.put_state(status="SPEAKING", response_text=farewell)
            speak(farewell, hud)
            stop_event.set()
            # Cerrar Qdrant en este thread para evitar SQLite cross-thread error
            try:
                nova_memory.neuro_memory.close()
            except Exception:
                pass
            break

        if lower_input in {"apágate", "duerme", "silencio", "silenciar", "suspéndete", "modo silencioso"}:
            is_muted = True
            hud.put_state(status="ASLEEP")
            speak("Entrando en modo suspendido, Señor.", hud)
            continue

        hud.put_state(status="THINKING")

        # ── Cambio de tema HUD ────────────────────────────────
        # Temas v6.0: NEURAL, CRISTAL, VÓRTICE, PLASMA, QUANTUM, PULSAR
        _THEME_MAP = {
            "neural": "NEURAL", "neuronas": "NEURAL", "red neuronal": "NEURAL",
            "partículas": "NEURAL", "particulas": "NEURAL",
            "plasma": "PLASMA", "rayos": "PLASMA", "electricidad": "PLASMA",
            "relámpago": "PLASMA", "relampago": "PLASMA", "lightning": "PLASMA",
            "tormenta": "TORMENTA", "truenos": "TORMENTA", "descarga": "TORMENTA", "storm": "TORMENTA",
        }
        _theme_match = re.search(
            r"(?:cambia|pon|usa|activa|tema|cambiar|muéstrame|mostrar)\s+(?:el\s+)?(?:tema\s+)?(?:hud\s+)?"
            r"(neural|neuronas|red neuronal|part[ií]culas|"
            r"plasma|rayos|electricidad|rel[aá]mpago|lightning|"
            r"tormenta|truenos|descarga|storm)",
            user_input.lower()
        )
        if _theme_match or re.search(r"^(?:siguiente tema|cambiar tema|next theme|tema siguiente)$", user_input.lower()):
            if _theme_match:
                key    = _theme_match.group(1).lower()
                t_name = _THEME_MAP.get(key.lower(), "NEURAL")
                hud.put_state(theme=t_name)
                theme_resp = f"Tema {t_name} activado, Señor."
            else:
                hud.put_state(theme="__next__")
                theme_resp = "Cambiando al siguiente tema visual, Señor."
            print(f"  [HUD TEMA] {theme_resp}")
            speak(theme_resp, hud)
            hud.put_state(status="IDLE")
            continue

        # ── Skill local primero ───────────────────────────────
        skill_resp = skills.dispatch(user_input)
        if skill_resp is not None:
            print(f"  [SKILL] {skill_resp[:100]}")
            print(f"Auxiliar: {skill_resp}")
            hud.put_state(
                status="SKILL",
                response_text=skill_resp,
                model_info="[SKILL LOCAL]",
            )
            nova_memory.save_turn("user",      user_input)
            nova_memory.save_turn("assistant", skill_resp)
            history.append({"role": "user",      "content": user_input})
            history.append({"role": "assistant", "content": skill_resp})
            speak(skill_resp, hud)
            continue

        # ── Búsqueda web si hace falta ────────────────────────
        extra = ""
        if skills.needs_web_search(user_input):
            print("  [búsqueda web...]")
            extra = skills.web_search_for_llm(user_input)

        # ── LLM ───────────────────────────────────────────────
        history.append({"role": "user", "content": user_input})
        msgs, resp_lang = _build_messages(history, router.system_prompt, extra)

        try:
            result = router.route(msgs)
        except RuntimeError as e:
            err = "Tuve un problema conectando con los modelos, Señor. Intente de nuevo."
            print(f"  [error: {e}]")
            print(f"Auxiliar: {err}")
            history.pop()
            hud.put_state(status="IDLE", response_text=err)
            speak(err, hud)
            continue

        tier     = result["tier"]
        model    = result["model"]
        tokens   = result["tokens_used"]
        budget   = result["budget_remaining_pct"]
        response = result["response"]

        model_info = (
            f"Tier {tier} {TIER_LABELS[tier]} | {model} | "
            f"{tokens} tk | {budget:.0f}% budget"
        )
        print(f"  ┌ {model_info}")
        print(f"  └ sesión: {result['session_tokens']} tokens")
        print(f"Auxiliar: {response}")

        hud.put_state(
            status="SPEAKING",
            response_text=response,
            model_info=model_info,
        )

        nova_memory.save_turn("user",      user_input)
        nova_memory.save_turn("assistant", response)
        history.append({"role": "assistant", "content": response})

        speak(response, hud, lang=resp_lang)

    # ── Resumen final ─────────────────────────────────────────
    stats = router.get_session_summary()
    print(f"\n{'─'*56}")
    print(
        f"  Sesión terminada | {stats['total_tokens']} tokens | "
        f"${stats['cost_usd']:.4f} | {stats['budget_consumed_pct']:.1f}% presupuesto"
    )
    print(f"{'─'*56}")


# ─── Entry point ─────────────────────────────────────────────────────────────

def main() -> None:
    hud        = NovaHUD()
    stop_event = threading.Event()

    # Compartir stop_event con el HUD para que cierre Qt al salir
    hud.set_stop_event(stop_event)

    # Servidor Telegram Receive en background (polling directo si hay token)
    try:
        from nova.connectors.nova_telegram_server import start as _tg_start
        from nova.cli.repl import _route_to_llm as _tg_process
        _tg_start(process_fn=_tg_process)
    except Exception:
        pass

    # Audio loop en hilo background (daemon → muere si el HUD cierra)
    audio_thread = threading.Thread(
        target=_nova_loop,
        args=(hud, stop_event),
        daemon=True,
    )
    audio_thread.start()

    # HUD en el hilo principal
    hud.start()


if __name__ == "__main__":
    if not _acquire_lock():
        raise SystemExit(0)
    main()
