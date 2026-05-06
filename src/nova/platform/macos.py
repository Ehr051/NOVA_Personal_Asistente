"""
macos.py — Implementaciones macOS usando comandos nativos del sistema.
"""
from __future__ import annotations
import os
import subprocess
import unicodedata


def play_audio(path: str) -> subprocess.Popen:
    """Reproduce un archivo de audio con afplay."""
    return subprocess.Popen(["afplay", path])


def speak_tts(text: str, voice: str = "Reed (Enhanced)", rate: str = "185") -> subprocess.Popen:
    """Usa macOS 'say' como TTS de fallback."""
    return subprocess.Popen(["say", "-v", voice, "-r", rate, text])


def open_application(app_name: str) -> bool:
    """Abre una aplicación con 'open -a'. Devuelve True si tuvo éxito."""
    r = subprocess.run(["open", "-a", app_name], capture_output=True, text=True)
    return r.returncode == 0


def find_installed_apps() -> list[str]:
    """Lista aplicaciones instaladas en /Applications y ~/Applications."""
    apps: list[str] = []
    for base in ["/Applications", os.path.expanduser("~/Applications")]:
        if os.path.isdir(base):
            for entry in os.listdir(base):
                if entry.endswith(".app"):
                    apps.append(entry[:-4])  # sin ".app"
    return sorted(set(apps))


def close_application(app_name: str) -> bool:
    """Cierra una aplicación via osascript."""
    r = subprocess.run(
        ["osascript", "-e", f'quit app "{app_name}"'],
        capture_output=True, text=True,
    )
    return r.returncode == 0


def take_screenshot(path: str) -> bool:
    """Captura la pantalla completa en el path dado."""
    r = subprocess.run(["screencapture", "-x", path], capture_output=True)
    return r.returncode == 0 and os.path.exists(path)


def get_system_volume() -> int | None:
    """Devuelve el volumen del sistema (0-100) o None si falla."""
    r = subprocess.run(
        ["osascript", "-e", "output volume of (get volume settings)"],
        capture_output=True, text=True,
    )
    try:
        return int(r.stdout.strip())
    except ValueError:
        return None


def set_system_volume(level: int) -> bool:
    """Establece el volumen del sistema (0-100)."""
    r = subprocess.run(
        ["osascript", "-e", f"set volume output volume {level}"],
        capture_output=True,
    )
    return r.returncode == 0


def mute_system() -> bool:
    r = subprocess.run(
        ["osascript", "-e", "set volume with output muted"],
        capture_output=True,
    )
    return r.returncode == 0


def unmute_system() -> bool:
    r = subprocess.run(
        ["osascript", "-e", "set volume without output muted"],
        capture_output=True,
    )
    return r.returncode == 0


def copy_to_clipboard(text: str) -> bool:
    """Copia texto al portapapeles usando pbcopy."""
    try:
        proc = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
        proc.communicate(text.encode())
        return proc.returncode == 0
    except Exception:
        return False
