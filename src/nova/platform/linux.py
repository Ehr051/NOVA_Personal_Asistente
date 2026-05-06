"""
linux.py — Implementaciones Linux.

TTS: espeak-ng (sudo apt install espeak-ng)
Audio: mpg123, aplay, o paplay (según lo que haya instalado)
Apps: xdg-open, which
Volume: amixer, pactl (PulseAudio)
Clipboard: xclip o xsel
Screenshot: gnome-screenshot, import (ImageMagick), o pyautogui
"""
from __future__ import annotations
import os
import shutil
import subprocess


def play_audio(path: str) -> subprocess.Popen | None:
    """Reproduce audio con el primer reproductor disponible."""
    players = ["mpg123", "mpg321", "aplay", "paplay", "ffplay", "cvlc"]
    for player in players:
        if shutil.which(player):
            flags = ["-q"] if player in ("mpg123", "mpg321", "ffplay") else []
            return subprocess.Popen(
                [player, *flags, path],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
    # Fallback pyautogui / pygame
    try:
        import pygame
        pygame.mixer.init()
        pygame.mixer.music.load(path)
        pygame.mixer.music.play()
        return None
    except Exception:
        return None


def speak_tts(text: str, voice: str = None, rate: str = "180") -> subprocess.Popen | None:
    """
    TTS con espeak-ng (preferido) o festival.
    rate ~150 palabras/min → espeak speed ~180
    """
    if shutil.which("espeak-ng"):
        return subprocess.Popen(
            ["espeak-ng", "-v", "es", "-s", str(rate), text],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    if shutil.which("espeak"):
        return subprocess.Popen(
            ["espeak", "-v", "es", text],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    if shutil.which("festival"):
        proc = subprocess.Popen(
            ["festival", "--tts"],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        proc.stdin.write(text.encode())
        proc.stdin.close()
        return proc
    return None


def open_application(app_name: str) -> bool:
    """Abre una aplicación con xdg-open o buscándola en PATH."""
    # Buscar ejecutable directo
    exe = shutil.which(app_name.lower()) or shutil.which(app_name.lower().replace(" ", "-"))
    if exe:
        subprocess.Popen([exe], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    # xdg-open como fallback
    if shutil.which("xdg-open"):
        r = subprocess.run(
            ["xdg-open", app_name],
            capture_output=True, timeout=5,
        )
        return r.returncode == 0
    return False


def find_installed_apps() -> list[str]:
    """Lista aplicaciones disponibles en PATH + /usr/share/applications."""
    apps: list[str] = []
    # Aplicaciones con .desktop file (GNOME/KDE)
    desktop_dirs = [
        "/usr/share/applications",
        "/usr/local/share/applications",
        os.path.expanduser("~/.local/share/applications"),
    ]
    for d in desktop_dirs:
        if os.path.isdir(d):
            for f in os.listdir(d):
                if f.endswith(".desktop"):
                    apps.append(f[:-8])  # sin ".desktop"
    return sorted(set(apps))


def close_application(app_name: str) -> bool:
    """Cierra un proceso por nombre con pkill."""
    r = subprocess.run(
        ["pkill", "-f", app_name],
        capture_output=True,
    )
    return r.returncode == 0


def take_screenshot(path: str) -> bool:
    """Captura pantalla con gnome-screenshot, import, o pyautogui."""
    if shutil.which("gnome-screenshot"):
        r = subprocess.run(
            ["gnome-screenshot", "-f", path],
            capture_output=True,
        )
        if r.returncode == 0 and os.path.exists(path):
            return True
    if shutil.which("import"):
        r = subprocess.run(
            ["import", "-window", "root", path],
            capture_output=True,
        )
        if r.returncode == 0 and os.path.exists(path):
            return True
    if shutil.which("scrot"):
        r = subprocess.run(["scrot", path], capture_output=True)
        if r.returncode == 0 and os.path.exists(path):
            return True
    # Fallback pyautogui
    try:
        import pyautogui
        pyautogui.screenshot().save(path)
        return os.path.exists(path)
    except Exception:
        return False


def get_system_volume() -> int | None:
    """Obtiene el volumen via pactl (PulseAudio) o amixer."""
    if shutil.which("pactl"):
        r = subprocess.run(
            ["pactl", "get-sink-volume", "@DEFAULT_SINK@"],
            capture_output=True, text=True,
        )
        import re
        m = re.search(r"(\d+)%", r.stdout)
        if m:
            return int(m.group(1))
    if shutil.which("amixer"):
        r = subprocess.run(
            ["amixer", "get", "Master"],
            capture_output=True, text=True,
        )
        import re
        m = re.search(r"\[(\d+)%\]", r.stdout)
        if m:
            return int(m.group(1))
    return None


def set_system_volume(level: int) -> bool:
    """Establece el volumen del sistema (0-100)."""
    if shutil.which("pactl"):
        r = subprocess.run(
            ["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{level}%"],
            capture_output=True,
        )
        return r.returncode == 0
    if shutil.which("amixer"):
        r = subprocess.run(
            ["amixer", "set", "Master", f"{level}%"],
            capture_output=True,
        )
        return r.returncode == 0
    return False


def mute_system() -> bool:
    if shutil.which("pactl"):
        r = subprocess.run(
            ["pactl", "set-sink-mute", "@DEFAULT_SINK@", "1"],
            capture_output=True,
        )
        return r.returncode == 0
    if shutil.which("amixer"):
        r = subprocess.run(["amixer", "set", "Master", "mute"], capture_output=True)
        return r.returncode == 0
    return False


def unmute_system() -> bool:
    if shutil.which("pactl"):
        r = subprocess.run(
            ["pactl", "set-sink-mute", "@DEFAULT_SINK@", "0"],
            capture_output=True,
        )
        return r.returncode == 0
    if shutil.which("amixer"):
        r = subprocess.run(["amixer", "set", "Master", "unmute"], capture_output=True)
        return r.returncode == 0
    return False


def copy_to_clipboard(text: str) -> bool:
    """Copia al portapapeles con xclip o xsel."""
    for cmd in [["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"]]:
        if shutil.which(cmd[0]):
            try:
                proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
                proc.communicate(text.encode())
                return proc.returncode == 0
            except Exception:
                pass
    try:
        import pyperclip
        pyperclip.copy(text)
        return True
    except Exception:
        return False
