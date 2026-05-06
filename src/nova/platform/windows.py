"""
windows.py — Implementaciones Windows.

Deps opcionales (instalar si están disponibles):
  pip install pycaw comtypes pyperclip
"""
from __future__ import annotations
import os
import subprocess
import sys


def play_audio(path: str) -> subprocess.Popen:
    """Reproduce audio con Windows Media Player via PowerShell."""
    script = (
        f"$player = New-Object System.Media.SoundPlayer '{path}'; "
        f"$player.PlaySync()"
    )
    # Para MP3 usamos Windows Media Player directamente
    ext = os.path.splitext(path)[-1].lower()
    if ext in (".mp3", ".ogg", ".flac"):
        return subprocess.Popen(
            ["powershell", "-Command",
             f"Start-Process -FilePath '{path}' -Wait"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    # WAV nativo con SoundPlayer
    return subprocess.Popen(
        ["powershell", "-Command", script],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def speak_tts(text: str, voice: str = None, rate: str = "180") -> subprocess.Popen:
    """
    TTS via PowerShell SAPI (sin deps extra).
    rate en SAPI va de -10 (lento) a 10 (rápido) — mapeamos desde wpm.
    """
    # Escapar comillas simples en el texto
    safe = text.replace("'", "\\'")
    script = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"$s.Rate = 2; "          # velocidad media-alta
        f"$s.Speak('{safe}')"
    )
    return subprocess.Popen(
        ["powershell", "-Command", script],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def open_application(app_name: str) -> bool:
    """
    Abre una aplicación en Windows.
    Intenta: os.startfile → start → path directo.
    """
    # Primero buscar el ejecutable en PATH
    import shutil
    exe = shutil.which(app_name) or shutil.which(app_name + ".exe")
    if exe:
        subprocess.Popen([exe])
        return True
    # Intento con os.startfile (abre con el programa predeterminado)
    try:
        os.startfile(app_name)
        return True
    except Exception:
        pass
    # Intento con cmd start
    r = subprocess.run(
        f'start "" "{app_name}"',
        shell=True, capture_output=True,
    )
    return r.returncode == 0


def find_installed_apps() -> list[str]:
    """Lista aplicaciones instaladas via registro de Windows."""
    apps: list[str] = []
    try:
        import winreg
        keys = [
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
            r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
        ]
        for key_path in keys:
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
                    for i in range(winreg.QueryInfoKey(key)[0]):
                        try:
                            with winreg.OpenKey(key, winreg.EnumKey(key, i)) as subkey:
                                name, _ = winreg.QueryValueEx(subkey, "DisplayName")
                                if name:
                                    apps.append(name)
                        except OSError:
                            pass
            except OSError:
                pass
    except ImportError:
        pass
    # Fallback: leer carpetas de Program Files
    for base in [r"C:\Program Files", r"C:\Program Files (x86)"]:
        if os.path.isdir(base):
            apps.extend(os.listdir(base))
    return sorted(set(apps))


def close_application(app_name: str) -> bool:
    """Cierra un proceso por nombre en Windows."""
    # Normalizar: 'Google Chrome' → 'chrome.exe'
    exe = app_name.lower().replace(" ", "") + ".exe"
    r = subprocess.run(
        ["taskkill", "/IM", exe, "/F"],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        # Intento con el nombre original
        r = subprocess.run(
            ["taskkill", "/IM", app_name, "/F"],
            capture_output=True, text=True,
        )
    return r.returncode == 0


def take_screenshot(path: str) -> bool:
    """Captura pantalla con pyautogui (cross-platform) o PowerShell."""
    try:
        import pyautogui
        pyautogui.screenshot().save(path)
        return os.path.exists(path)
    except Exception:
        pass
    # Fallback PowerShell
    script = (
        "Add-Type -AssemblyName System.Windows.Forms; "
        "$bmp = [System.Drawing.Bitmap]::new("
        "[System.Windows.Forms.Screen]::PrimaryScreen.Bounds.Width,"
        "[System.Windows.Forms.Screen]::PrimaryScreen.Bounds.Height); "
        "$g = [System.Drawing.Graphics]::FromImage($bmp); "
        "$g.CopyFromScreen(0, 0, 0, 0, $bmp.Size); "
        f"$bmp.Save('{path}')"
    )
    r = subprocess.run(["powershell", "-Command", script], capture_output=True)
    return r.returncode == 0 and os.path.exists(path)


def get_system_volume() -> int | None:
    """Obtiene el volumen del sistema via pycaw o PowerShell."""
    try:
        from ctypes import cast, POINTER
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = cast(interface, POINTER(IAudioEndpointVolume))
        return int(volume.GetMasterVolumeLevelScalar() * 100)
    except Exception:
        pass
    # Fallback PowerShell
    r = subprocess.run(
        ["powershell", "-Command",
         "[int]([Math]::Round((Get-AudioDevice -Playback).Volume))"],
        capture_output=True, text=True,
    )
    try:
        return int(r.stdout.strip())
    except ValueError:
        return None


def set_system_volume(level: int) -> bool:
    """Establece el volumen del sistema (0-100)."""
    try:
        from ctypes import cast, POINTER
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = cast(interface, POINTER(IAudioEndpointVolume))
        volume.SetMasterVolumeLevelScalar(level / 100.0, None)
        return True
    except Exception:
        pass
    # Fallback PowerShell (requiere AudioDeviceCmdlets module)
    r = subprocess.run(
        ["powershell", "-Command", f"Set-AudioDevice -Playback -Volume {level}"],
        capture_output=True,
    )
    return r.returncode == 0


def mute_system() -> bool:
    try:
        from ctypes import cast, POINTER
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = cast(interface, POINTER(IAudioEndpointVolume))
        volume.SetMute(1, None)
        return True
    except Exception:
        return False


def unmute_system() -> bool:
    try:
        from ctypes import cast, POINTER
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = cast(interface, POINTER(IAudioEndpointVolume))
        volume.SetMute(0, None)
        return True
    except Exception:
        return False


def copy_to_clipboard(text: str) -> bool:
    """Copia texto al portapapeles."""
    try:
        import pyperclip
        pyperclip.copy(text)
        return True
    except ImportError:
        pass
    # Fallback PowerShell
    safe = text.replace('"', '`"')
    r = subprocess.run(
        ["powershell", "-Command", f'Set-Clipboard -Value "{safe}"'],
        capture_output=True,
    )
    return r.returncode == 0
