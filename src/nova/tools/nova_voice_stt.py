import os
import logging
# Fix: evita el crash de OpenMP en macOS.
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import sys
import time
import tempfile
import numpy as np
import librosa
from pathlib import Path

log = logging.getLogger(__name__)

from faster_whisper import WhisperModel
import speech_recognition as sr


# ─────────────────────────────────────────────
#  Configuración global
# ─────────────────────────────────────────────
# Buscar perfil en tools/, raíz del proyecto y __DOTNOVA_PATH__/
_profile_candidates = [
    Path(__file__).parent / "nova_voice_profile.npy",
    Path(__file__).parent.parent.parent.parent / "nova_voice_profile.npy",
    Path.home() / ".nova" / "nova_voice_profile.npy",
]
PROFILE_PATH = next((p for p in _profile_candidates if p.exists()),
                    _profile_candidates[0])   # default para --enroll
TEMP_WAV          = Path(__file__).parent / "temp_buffer.wav"
DEFAULT_THRESHOLD = 0.82   # similitud coseno mínima para aceptar la voz
SAMPLE_RATE       = 16000
N_MFCC            = 40     # coeficientes MFCC


# ─────────────────────────────────────────────
#  Helpers de audio
# ─────────────────────────────────────────────

def _extract_features(wav_path: str) -> np.ndarray | None:
    """
    Extrae un vector de características MFCC de un archivo WAV.
    Retorna None si el audio es demasiado corto o hay un error.
    """
    try:
        y, _ = librosa.load(wav_path, sr=SAMPLE_RATE, mono=True)
        if len(y) < SAMPLE_RATE * 0.3:   # menos de 0.3 s → ignorar
            return None
        mfccs  = librosa.feature.mfcc(y=y, sr=SAMPLE_RATE, n_mfcc=N_MFCC)
        # Media + desviación estándar → vector de 80 dimensiones robusto
        feats  = np.concatenate([mfccs.mean(axis=1), mfccs.std(axis=1)])
        norm   = np.linalg.norm(feats)
        return feats / norm if norm > 0 else feats
    except Exception as e:
        log.warning("[STT] Error extrayendo features: %s", e)
        return None


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b))   # ya normalizados en _extract_features


# ─────────────────────────────────────────────
#  Clase principal
# ─────────────────────────────────────────────

class NovaVoiceSTT:
    def __init__(
        self,
        model_size="base",
        device="cpu",
        compute_type="int8",
        similarity_threshold=DEFAULT_THRESHOLD,
    ):
        """
        STT con verificación de hablante via MFCC (sin descargas de modelos).

        - Si existe 'nova_voice_profile.npy', solo transcribe tu voz.
        - Sin perfil: acepta cualquier voz (modo abierto).
        - Ejecutar con --enroll para crear/actualizar el perfil.
        """
        log.info("[STT] Cargando modelo Whisper...")
        self.model = WhisperModel(model_size, device=device, compute_type=compute_type)

        self.recognizer = sr.Recognizer()
        self.recognizer.energy_threshold        = 300
        self.recognizer.dynamic_energy_threshold = True
        self.recognizer.pause_threshold         = 0.8

        self.threshold    = similarity_threshold
        self.voice_profile = None

        if PROFILE_PATH.exists():
            self.voice_profile = np.load(str(PROFILE_PATH))
            log.info("[STT] Perfil cargado — verificación ACTIVA (umbral=%s)", self.threshold)
        else:
            log.warning("[STT] Sin perfil de voz. Ejecutá --enroll para registrarte.")
            log.warning("[STT] Sin perfil — se acepta cualquier voz.")

        log.info("[STT] Listo.")

    # ─────────────────────────────────────────
    #  Registro de voz
    # ─────────────────────────────────────────

    def enroll_speaker(self, rounds: int = 3, output_path: "str | Path | None" = None):
        """
        Enroll en múltiples rondas con frases guiadas.
        Promedia los vectores MFCC para un perfil robusto y representativo.
        output_path: ruta donde guardar el .npy (default: PROFILE_PATH global)
        """
        from pathlib import Path as _Path
        _save_path = _Path(output_path) if output_path else PROFILE_PATH
        GUIDED_ROUNDS = [
            {
                "titulo": "RONDA 1 — Comandos típicos",
                "duracion": 30,
                "instruccion": (
                    "Lee estas frases en voz normal, como si le hablaras a Nova:\n"
                    "  • Nova, abre Safari\n"
                    "  • Nova, qué hora es\n"
                    "  • Nova, pon música\n"
                    "  • Nova, busca las noticias de hoy\n"
                    "  • Nova, captura de pantalla\n"
                    "  • Nova, recuerda que tengo reunión el jueves\n"
                    "  • Nova, sube el volumen"
                ),
            },
            {
                "titulo": "RONDA 2 — Preguntas y frases largas",
                "duracion": 30,
                "instruccion": (
                    "Ahora lee estas frases más largas y naturales:\n"
                    "  • Nova, ¿cuál es el precio del dólar hoy?\n"
                    "  • Nova, dame un resumen de las noticias más importantes\n"
                    "  • Nova, abre el archivo de notas del escritorio\n"
                    "  • Nova, ejecuta el comando para listar los archivos\n"
                    "  • Nova, crea un archivo llamado ideas con el contenido: reunión pendiente"
                ),
            },
            {
                "titulo": "RONDA 3 — Tono conversacional",
                "duracion": 25,
                "instruccion": (
                    "Ahora habla de forma más natural, como si charlaras:\n"
                    "  • Nova, ¿qué tengo en el calendario esta semana?\n"
                    "  • Necesito que me ayudes a redactar un email\n"
                    "  • ¿Podés buscar información sobre Python asyncio?\n"
                    "  • Nova, pon el volumen al cincuenta por ciento\n"
                    "  • Cerrá Spotify y abrí YouTube"
                ),
            },
        ]

        print("\n" + "═" * 56)
        print("  🎙️  REGISTRO DE VOZ — Nova Speaker Enrollment")
        print("  Se harán 3 rondas cortas con frases guiadas.")
        print("  Esto toma ~2 minutos y da un perfil mucho más preciso.")
        print("═" * 56)

        feature_vectors = []
        tmp_paths = []

        for i, ronda in enumerate(GUIDED_ROUNDS, 1):
            print(f"\n{'─' * 56}")
            print(f"  {ronda['titulo']} ({ronda['duracion']} segundos)")
            print(f"{'─' * 56}")
            print(ronda["instruccion"])
            print(f"\n  Empezando en:")
            for c in [5, 4, 3, 2, 1]:
                print(f"    {c}...")
                time.sleep(1)
            print(f"  ▶ GRABANDO ({ronda['duracion']}s) — hablá ahora\n")

            with sr.Microphone(sample_rate=SAMPLE_RATE) as source:
                self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
                audio = self.recognizer.record(source, duration=ronda["duracion"])

            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp.write(audio.get_wav_data())
                tmp_paths.append(tmp.name)

            feats = _extract_features(tmp_paths[-1])
            if feats is None:
                print(f"  ⚠ Ronda {i}: audio demasiado corto o con error — se omite.")
            else:
                feature_vectors.append(feats)
                print(f"  ✓ Ronda {i} procesada (similitud interna: ok)")

            if i < len(GUIDED_ROUNDS):
                print(f"\n  Descansá 3 segundos antes de la próxima ronda...")
                time.sleep(3)

        # Limpiar archivos temporales
        for p in tmp_paths:
            try:
                os.unlink(p)
            except Exception:
                pass

        if not feature_vectors:
            print("\n❌ Ninguna ronda produjo audio válido. Intentá de nuevo en un lugar silencioso.")
            return

        # Promediar todos los vectores → perfil más robusto
        profile = np.mean(feature_vectors, axis=0)
        norm = np.linalg.norm(profile)
        if norm > 0:
            profile = profile / norm

        # Verificar coherencia entre rondas
        if len(feature_vectors) >= 2:
            sims = []
            for a in feature_vectors:
                for b in feature_vectors:
                    if a is not b:
                        sims.append(float(np.dot(a, b)))
            coherencia = np.mean(sims)
            print(f"\n  Coherencia entre rondas: {coherencia:.3f}")
            if coherencia < 0.70:
                print("  ⚠ Coherencia baja — puede haber mucho ruido ambiente.")
                print("    El perfil se guardó igual, pero considerá re-enrollar en silencio.")
            else:
                print("  ✅ Perfil de alta calidad.")

        _save_path.parent.mkdir(parents=True, exist_ok=True)
        np.save(str(_save_path), profile)
        self.voice_profile = profile
        print(f"\n✅ Perfil guardado en: {_save_path}")
        print(f"   Rondas usadas: {len(feature_vectors)}/{len(GUIDED_ROUNDS)}")
        print(f"   Verificación de hablante ACTIVA (umbral={self.threshold}).")
        print(f"\n   Podés ajustar la sensibilidad en .env: SPEAKER_THRESHOLD=0.80\n")

    # ─────────────────────────────────────────
    #  Verificación de hablante
    # ─────────────────────────────────────────

    def _is_my_voice(self, wav_path: str) -> bool:
        """True si el audio pertenece al usuario registrado."""
        if self.voice_profile is None:
            return True   # Sin perfil → acepta todo

        features = _extract_features(wav_path)
        if features is None:
            return False

        sim = _cosine_similarity(self.voice_profile, features)
        # Descomenta para depurar:
        # print(f"    [similitud={sim:.3f}]")
        return sim >= self.threshold

    def set_threshold(self, value: float):
        """Ajusta sensibilidad: 0.75=permisivo · 0.82=normal · 0.90=estricto"""
        self.threshold = max(0.0, min(1.0, value))
        print(f"[Nova STT] Umbral actualizado → {self.threshold}")

    # ─────────────────────────────────────────
    #  Escucha y transcripción
    # ─────────────────────────────────────────

    def listen_and_transcribe(self, source, timeout=None) -> str:
        """Escucha, verifica hablante y transcribe. Devuelve "" si la voz no coincide."""
        try:
            audio = self.recognizer.listen(source, timeout=timeout)

            with open(str(TEMP_WAV), "wb") as f:
                f.write(audio.get_wav_data())

            if not self._is_my_voice(str(TEMP_WAV)):
                return ""   # Voz no reconocida → ignorar silenciosamente

            segments, _ = self.model.transcribe(
                str(TEMP_WAV), beam_size=5, language="es"
            )
            return " ".join(seg.text for seg in segments).strip()

        except sr.WaitTimeoutError:
            return ""
        except Exception as e:
            print(f"[Nova STT] Error: {e}")
            return ""

    # ─────────────────────────────────────────
    #  Dictado continuo
    # ─────────────────────────────────────────

    def continuous_dictation(self, stop_phrase: str = "fin del dictado") -> str:
        """Mantiene el mic abierto. Solo procesa la voz del usuario registrado."""
        if self.voice_profile is not None:
            print("🔒 Verificación de hablante ACTIVA — solo tu voz será procesada.")
        print(f"\n🎤 --- MODO DICTADO --- (Decí '{stop_phrase}' para terminar)\n")

        buffer = []
        with sr.Microphone() as source:
            self.recognizer.adjust_for_ambient_noise(source, duration=1)
            while True:
                text = self.listen_and_transcribe(source)
                if not text:
                    continue
                print(f"👉 {text}")
                cleaned = text.lower().replace(".", "").replace(",", "").strip()
                if stop_phrase in cleaned:
                    print("\n🛑 --- DICTADO FINALIZADO ---")
                    final = text.lower().replace(stop_phrase, "").strip()
                    if final:
                        buffer.append(final)
                    break
                buffer.append(text)

        return " ".join(buffer)


# ─────────────────────────────────────────────────────
#  Entry point
# ─────────────────────────────────────────────────────
if __name__ == "__main__":
    if "--enroll" in sys.argv:
        stt = NovaVoiceSTT()
        stt.enroll_speaker(duration=20)
    else:
        stt = NovaVoiceSTT()
        resultado = stt.continuous_dictation()
        print("\n[Resultado Final]:", resultado)
