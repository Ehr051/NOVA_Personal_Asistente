"""
Nova Plugin — Apple Ecosystem + Spotify
========================================

Integra iMessage, Apple Reminders, Apple Notes y Spotify con Nova
mediante osascript (AppleScript) usando solo subprocess de la stdlib.

Requiere macOS. Si no detecta Darwin, el plugin se registra pero
emite un warning y todas las skills devuelven un mensaje informativo.
"""

from __future__ import annotations

import logging
import platform
import re
import subprocess
from typing import Optional

logger = logging.getLogger("nova.plugin.apple")

PLUGIN_META = {
    "name": "apple_ecosystem",
    "version": "1.0.0",
    "description": "Integración con iMessage, Reminders, Notes y Spotify vía osascript",
    "author": "Nova Team",
}

_IS_MACOS = platform.system() == "Darwin"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _osascript(script: str, timeout: int = 15) -> tuple[bool, str]:
    """Ejecuta un AppleScript y devuelve (success, output|error)."""
    if not _IS_MACOS:
        return False, "osascript solo está disponible en macOS"
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if result.returncode == 0:
            return True, result.stdout.strip()
        err = (result.stderr or result.stdout or "").strip()
        logger.warning("osascript falló: %s", err)
        return False, err
    except subprocess.TimeoutExpired:
        return False, "el comando tardó demasiado y se canceló"
    except FileNotFoundError:
        return False, "osascript no se encontró en el sistema"
    except Exception as exc:  # noqa: BLE001
        logger.exception("Error ejecutando osascript")
        return False, f"error inesperado: {exc}"


def _escape(text: str) -> str:
    """Escapa comillas y backslashes para inyectar en AppleScript."""
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _app_running(app_name: str) -> bool:
    ok, out = _osascript(
        f'tell application "System Events" to (name of processes) contains "{_escape(app_name)}"'
    )
    return ok and out.lower() == "true"


# ---------------------------------------------------------------------------
# iMessage
# ---------------------------------------------------------------------------
def _parse_destinatario_mensaje(texto: str) -> tuple[Optional[str], Optional[str]]:
    """Parsea 'destinatario: mensaje' o 'mensaje a nombre'."""
    texto = texto.strip()

    # Formato "destinatario: mensaje"
    if ":" in texto:
        dest, _, msg = texto.partition(":")
        dest, msg = dest.strip(), msg.strip()
        if dest and msg:
            return dest, msg

    # Formato "mensaje a nombre" / "diciéndole X a nombre"
    m = re.search(r"^(.+?)\s+a\s+([^\s].*)$", texto)
    if m:
        msg, dest = m.group(1).strip(), m.group(2).strip()
        if dest and msg:
            return dest, msg

    # Formato "nombre <espacio> mensaje" (asumimos primera palabra = contacto)
    parts = texto.split(None, 1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()

    return None, None


def skill_imessage_send(texto: str) -> str:
    if not _IS_MACOS:
        return "Señor, iMessage solo funciona en macOS."

    dest, msg = _parse_destinatario_mensaje(texto)
    if not dest or not msg:
        return (
            "Señor, no pude entender el destinatario y el mensaje. "
            'Probá con "mandá un mensaje a Juan: hola qué tal".'
        )

    script = f'''
    tell application "Messages"
        set targetService to 1st service whose service type = iMessage
        try
            set targetBuddy to buddy "{_escape(dest)}" of targetService
            send "{_escape(msg)}" to targetBuddy
            return "ok"
        on error errMsg
            return "error: " & errMsg
        end try
    end tell
    '''
    ok, out = _osascript(script)
    if ok and out.startswith("ok"):
        return f"Listo, Señor. Mensaje enviado a {dest}."
    return f"Señor, no pude enviar el mensaje: {out}"


def skill_imessage_leer(_: Optional[str] = None) -> str:
    if not _IS_MACOS:
        return "Señor, iMessage solo funciona en macOS."

    script = '''
    tell application "Messages"
        try
            set output to ""
            set chatList to chats
            set maxChats to 5
            if (count of chatList) < maxChats then set maxChats to (count of chatList)
            repeat with i from 1 to maxChats
                set c to item i of chatList
                try
                    set chatName to name of c
                on error
                    set chatName to "(sin nombre)"
                end try
                set output to output & chatName & linefeed
            end repeat
            return output
        on error errMsg
            return "error: " & errMsg
        end try
    end tell
    '''
    ok, out = _osascript(script)
    if not ok:
        return f"Señor, no pude leer los mensajes: {out}"
    if not out:
        return "Señor, no hay mensajes recientes."
    chats = [c for c in out.splitlines() if c.strip()]
    bullets = "\n".join(f"  • {c}" for c in chats[:5])
    return f"Señor, sus chats recientes:\n{bullets}"


# ---------------------------------------------------------------------------
# Reminders
# ---------------------------------------------------------------------------
_HORA_RE = re.compile(r"\ba\s+las?\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", re.IGNORECASE)
_DIA_RE = re.compile(r"\b(hoy|mañana|pasado\s+mañana)\b", re.IGNORECASE)


def _parse_fecha_natural(texto: str) -> tuple[str, Optional[str]]:
    """Devuelve (texto_sin_fecha, applescript_due_date_expr|None)."""
    dia_match = _DIA_RE.search(texto)
    hora_match = _HORA_RE.search(texto)

    if not dia_match and not hora_match:
        return texto.strip(), None

    # Calcular offset de día
    offset_days = 0
    if dia_match:
        d = dia_match.group(1).lower()
        if "hoy" in d:
            offset_days = 0
        elif "pasado" in d:
            offset_days = 2
        elif "mañana" in d:
            offset_days = 1

    hour, minute = 9, 0
    if hora_match:
        hour = int(hora_match.group(1))
        minute = int(hora_match.group(2) or 0)
        ampm = (hora_match.group(3) or "").lower()
        if ampm == "pm" and hour < 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0

    # Limpiar el texto de la mención temporal
    cleaned = texto
    if dia_match:
        cleaned = cleaned.replace(dia_match.group(0), "")
    if hora_match:
        cleaned = cleaned.replace(hora_match.group(0), "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.;-")

    # AppleScript: construir due date
    expr = (
        f"(current date) + ({offset_days} * days)"
        if offset_days
        else "(current date)"
    )
    due_expr = (
        f"set theDate to {expr}\n"
        f"        set hours of theDate to {hour}\n"
        f"        set minutes of theDate to {minute}\n"
        f"        set seconds of theDate to 0"
    )
    return cleaned, due_expr


def skill_reminder_crear(texto: str) -> str:
    if not _IS_MACOS:
        return "Señor, los Recordatorios solo funcionan en macOS."

    nombre, due_expr = _parse_fecha_natural(texto)
    if not nombre:
        return "Señor, no entendí qué quería que recuerde."

    if due_expr:
        script = f'''
        tell application "Reminders"
            try
                {due_expr}
                make new reminder with properties {{name:"{_escape(nombre)}", due date:theDate}}
                return "ok"
            on error errMsg
                return "error: " & errMsg
            end try
        end tell
        '''
        sufijo_msg = " con su hora programada"
    else:
        script = f'''
        tell application "Reminders"
            try
                make new reminder with properties {{name:"{_escape(nombre)}"}}
                return "ok"
            on error errMsg
                return "error: " & errMsg
            end try
        end tell
        '''
        sufijo_msg = ""

    ok, out = _osascript(script)
    if ok and out.startswith("ok"):
        return f'Listo, Señor. Recordatorio "{nombre}" creado{sufijo_msg}.'
    return f"Señor, no pude crear el recordatorio: {out}"


def skill_reminder_listar(_: Optional[str] = None) -> str:
    if not _IS_MACOS:
        return "Señor, los Recordatorios solo funcionan en macOS."

    script = '''
    tell application "Reminders"
        try
            set output to ""
            set pendientes to (name of every reminder whose completed is false)
            repeat with r in pendientes
                set output to output & r & linefeed
            end repeat
            return output
        on error errMsg
            return "error: " & errMsg
        end try
    end tell
    '''
    ok, out = _osascript(script, timeout=20)
    if not ok:
        return f"Señor, no pude leer sus recordatorios: {out}"
    items = [r.strip() for r in out.splitlines() if r.strip()]
    if not items:
        return "Señor, no tiene recordatorios pendientes."
    bullets = "\n".join(f"  • {r}" for r in items[:15])
    extra = f"\n…y {len(items) - 15} más." if len(items) > 15 else ""
    return f"Señor, tiene {len(items)} recordatorio(s) pendiente(s):\n{bullets}{extra}"


# ---------------------------------------------------------------------------
# Notes
# ---------------------------------------------------------------------------
def skill_notes_crear(texto: str) -> str:
    if not _IS_MACOS:
        return "Señor, Notas solo funciona en macOS."

    contenido = texto.strip()
    if not contenido:
        return "Señor, no me indicó qué guardar en la nota."

    # Primera línea = título; resto = cuerpo
    lineas = contenido.splitlines()
    titulo = lineas[0][:80] if lineas else "Nota de Nova"
    body_html = contenido.replace("\n", "<br>")

    script = f'''
    tell application "Notes"
        try
            tell account "iCloud"
                make new note with properties {{name:"{_escape(titulo)}", body:"{_escape(body_html)}"}}
            end tell
            return "ok"
        on error
            try
                make new note with properties {{name:"{_escape(titulo)}", body:"{_escape(body_html)}"}}
                return "ok"
            on error errMsg
                return "error: " & errMsg
            end try
        end try
    end tell
    '''
    ok, out = _osascript(script)
    if ok and out.startswith("ok"):
        return f'Listo, Señor. Nota "{titulo}" guardada.'
    return f"Señor, no pude crear la nota: {out}"


def skill_notes_buscar(texto: str) -> str:
    if not _IS_MACOS:
        return "Señor, Notas solo funciona en macOS."

    query = texto.strip()
    if not query:
        return "Señor, ¿qué nota busca?"

    script = f'''
    tell application "Notes"
        try
            set output to ""
            set matches to (name of every note whose name contains "{_escape(query)}")
            repeat with n in matches
                set output to output & n & linefeed
            end repeat
            return output
        on error errMsg
            return "error: " & errMsg
        end try
    end tell
    '''
    ok, out = _osascript(script, timeout=20)
    if not ok:
        return f"Señor, no pude buscar en Notas: {out}"
    items = [r.strip() for r in out.splitlines() if r.strip()]
    if not items:
        return f'Señor, no encontré notas que contengan "{query}".'
    bullets = "\n".join(f"  • {n}" for n in items[:10])
    return f"Señor, encontré {len(items)} nota(s):\n{bullets}"


# ---------------------------------------------------------------------------
# Spotify
# ---------------------------------------------------------------------------
def _spotify_available() -> bool:
    if not _IS_MACOS:
        return False
    ok, out = _osascript(
        'tell application "System Events" to exists application process "Spotify"'
    )
    if ok and out.lower() == "true":
        return True
    # Intentar levantar la app
    ok, _ = _osascript('tell application "Spotify" to activate')
    return ok


def skill_spotify_play(texto: str) -> str:
    if not _IS_MACOS:
        return "Señor, Spotify se controla solo en macOS desde acá."

    query = texto.strip()
    if not query:
        # Sin query: sólo darle play a lo que esté cargado
        ok, out = _osascript('tell application "Spotify" to play')
        if ok:
            return "Listo, Señor. Reproduciendo."
        return f"Señor, no pude darle play a Spotify: {out}"

    if not _spotify_available():
        return "Señor, Spotify no parece estar instalado o disponible."

    # Spotify desktop no expone búsqueda directa por nombre; usamos URI search
    # El esquema "spotify:search:..." abre la búsqueda. Para autoplay del
    # primer resultado abrimos la URL vía 'open' como fallback.
    script = f'''
    tell application "Spotify"
        try
            activate
            play track "spotify:search:{_escape(query)}"
            return "ok"
        on error errMsg
            return "error: " & errMsg
        end try
    end tell
    '''
    ok, out = _osascript(script)
    if ok and out.startswith("ok"):
        return f'Listo, Señor. Reproduciendo "{query}" en Spotify.'

    # Fallback: abrir URL de búsqueda
    try:
        subprocess.run(
            ["open", f"spotify:search:{query}"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return f'Señor, abrí la búsqueda de "{query}" en Spotify.'
    except Exception as exc:  # noqa: BLE001
        return f"Señor, no pude reproducir en Spotify: {exc}"


def skill_spotify_control(texto: str) -> str:
    if not _IS_MACOS:
        return "Señor, Spotify se controla solo en macOS desde acá."

    t = texto.lower().strip()

    # Volumen
    vol_match = re.search(r"volumen\s+(\d{1,3})", t)
    if vol_match:
        vol = max(0, min(100, int(vol_match.group(1))))
        ok, out = _osascript(f'tell application "Spotify" to set sound volume to {vol}')
        if ok:
            return f"Listo, Señor. Volumen de Spotify al {vol}%."
        return f"Señor, no pude cambiar el volumen: {out}"

    if "pausar" in t or "pausa" in t or "pausá" in t:
        action = "pause"
        msg = "Spotify pausado, Señor."
    elif "siguiente" in t or "próxim" in t or "proxim" in t:
        action = "next track"
        msg = "Pasando al siguiente tema, Señor."
    elif "anterior" in t or "atrás" in t or "atras" in t:
        action = "previous track"
        msg = "Volviendo al tema anterior, Señor."
    elif "reanud" in t or "continu" in t or "play" in t:
        action = "play"
        msg = "Reanudando, Señor."
    elif "qué suena" in t or "que suena" in t or "qué canción" in t or "que cancion" in t:
        return skill_spotify_estado()
    else:
        return "Señor, no entendí qué hacer con Spotify."

    ok, out = _osascript(f'tell application "Spotify" to {action}')
    if ok:
        return msg
    return f"Señor, no pude controlar Spotify: {out}"


def skill_spotify_estado(_: Optional[str] = None) -> str:
    if not _IS_MACOS:
        return "Señor, Spotify se controla solo en macOS desde acá."

    if not _app_running("Spotify"):
        return "Señor, Spotify no está abierto."

    script = '''
    tell application "Spotify"
        try
            if player state is stopped then
                return "stopped"
            end if
            set t to name of current track
            set a to artist of current track
            set al to album of current track
            return t & " ||| " & a & " ||| " & al
        on error errMsg
            return "error: " & errMsg
        end try
    end tell
    '''
    ok, out = _osascript(script)
    if not ok:
        return f"Señor, no pude consultar Spotify: {out}"
    if out == "stopped":
        return "Señor, Spotify está detenido."
    if "|||" in out:
        nombre, artista, album = [p.strip() for p in out.split("|||")]
        return f'Señor, está sonando "{nombre}" de {artista} (álbum: {album}).'
    return f"Señor, no pude interpretar la respuesta de Spotify: {out}"


# ---------------------------------------------------------------------------
# INTENTS y TOOL_CATALOG
# ---------------------------------------------------------------------------
INTENTS = [
    # iMessage ------------------------------------------------------------
    (
        r"(?:mand[aá]|envi[aá]r?|enviame|mandar?)\s+(?:un\s+)?mensaje\s+(?:a\s+)?(.+)",
        skill_imessage_send,
        1,
    ),
    (
        r"(?:escribile|escribirle|decile|dec[ií]rle)\s+(?:a\s+)?(.+)",
        skill_imessage_send,
        1,
    ),
    (
        r"(?:le[eé]r?|mostr[aá]?|ver|mir[aá]?)\s+(?:mis\s+)?mensajes?",
        skill_imessage_leer,
        0,
    ),

    # Reminders -----------------------------------------------------------
    (
        r"(?:record[aá]me|recordarme|record[aá]?|crear?\s+(?:un\s+)?recordatorio)[:\s]+(.+)",
        skill_reminder_crear,
        1,
    ),
    (
        r"(?:agend[aá]?|anot[aá]?)\s+(?:un\s+)?recordatorio[:\s]+(.+)",
        skill_reminder_crear,
        1,
    ),
    (
        r"(?:mis\s+)?recordatorios?(?:\s+pendientes?)?$",
        skill_reminder_listar,
        0,
    ),
    (
        r"(?:list[aá]?|mostr[aá]?|ver)\s+(?:mis\s+)?recordatorios?",
        skill_reminder_listar,
        0,
    ),

    # Notes ---------------------------------------------------------------
    (
        r"(?:cre[aá]?|crear?|guard[aá]?)\s+(?:una?\s+)?nota[:\s]+(.+)",
        skill_notes_crear,
        1,
    ),
    (
        r"(?:guard[aá]?|anot[aá]?)\s+esto\s+en\s+notas?[:\s]+(.+)",
        skill_notes_crear,
        1,
    ),
    (
        r"(?:nueva\s+nota)[:\s]+(.+)",
        skill_notes_crear,
        1,
    ),
    (
        r"(?:busc[aá]?|buscar?)\s+(?:en\s+)?(?:la\s+|las\s+)?notas?\s+(.+)",
        skill_notes_buscar,
        1,
    ),

    # Spotify -------------------------------------------------------------
    (
        r"(?:pon[eé]?|reproduc[ií]?|reproducir|repro|play|pasa)\s+(.+?)(?:\s+en\s+spotify)?$",
        skill_spotify_play,
        1,
    ),
    (
        r"(?:pausar?|pausá|pausa)(?:\s+(?:spotify|m[uú]sica|la\s+m[uú]sica|el\s+tema))?$",
        skill_spotify_control,
        0,
    ),
    (
        r"(?:siguiente|pr[oó]xim[ao])\s+(?:canci[oó]n|tema|pista)",
        skill_spotify_control,
        0,
    ),
    (
        r"(?:anterior|atr[aá]s)\s+(?:canci[oó]n|tema|pista)",
        skill_spotify_control,
        0,
    ),
    (
        r"(?:reanud[aá]?|continu[aá]?)\s+(?:spotify|m[uú]sica|la\s+m[uú]sica)",
        skill_spotify_control,
        0,
    ),
    (
        r"volumen\s+(?:de\s+spotify\s+)?(?:a\s+|al\s+)?\d{1,3}",
        skill_spotify_control,
        0,
    ),
    (
        r"(?:qu[eé]\s+(?:suena|est[aá]\s+sonando)|qu[eé]\s+canci[oó]n\s+(?:es|suena))",
        skill_spotify_estado,
        0,
    ),
]


TOOL_CATALOG = {
    "imessage_send":   ("Enviar mensaje de iMessage a un contacto", skill_imessage_send, "text"),
    "imessage_leer":   ("Leer últimos mensajes de iMessage recibidos", skill_imessage_leer, None),
    "reminder_crear":  ("Crear un recordatorio en Apple Reminders", skill_reminder_crear, "text"),
    "reminder_listar": ("Listar recordatorios pendientes de Apple Reminders", skill_reminder_listar, None),
    "notes_crear":     ("Crear una nota en Apple Notes", skill_notes_crear, "text"),
    "notes_buscar":    ("Buscar notas en Apple Notes", skill_notes_buscar, "text"),
    "spotify_play":    ("Reproducir música en Spotify", skill_spotify_play, "text"),
    "spotify_control": ("Controlar reproducción de Spotify (pausar/siguiente/anterior/volumen)", skill_spotify_control, "text"),
    "spotify_estado":  ("Ver qué canción está sonando en Spotify ahora", skill_spotify_estado, None),
}


# ---------------------------------------------------------------------------
# Registro
# ---------------------------------------------------------------------------
def register(skills_module) -> None:  # noqa: ANN001
    """Registra el plugin en el módulo de skills de Nova."""
    if not _IS_MACOS:
        logger.warning(
            "nova_plugin_apple cargado en plataforma no-macOS (%s); "
            "todas las skills devolverán mensajes informativos.",
            platform.system(),
        )

    # Enlace opcional con skills_module si expone API de registro directa
    for attr, fn in (
        ("imessage_send", skill_imessage_send),
        ("imessage_leer", skill_imessage_leer),
        ("reminder_crear", skill_reminder_crear),
        ("reminder_listar", skill_reminder_listar),
        ("notes_crear", skill_notes_crear),
        ("notes_buscar", skill_notes_buscar),
        ("spotify_play", skill_spotify_play),
        ("spotify_control", skill_spotify_control),
        ("spotify_estado", skill_spotify_estado),
    ):
        if skills_module is not None and not hasattr(skills_module, attr):
            try:
                setattr(skills_module, attr, fn)
            except Exception:  # noqa: BLE001
                logger.debug("No pude exponer %s en skills_module", attr)

    logger.info(
        "Plugin %s v%s registrado (%d intents, %d tools)",
        PLUGIN_META["name"],
        PLUGIN_META["version"],
        len(INTENTS),
        len(TOOL_CATALOG),
    )
