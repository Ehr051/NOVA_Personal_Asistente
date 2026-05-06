"""
nova/platform — Capa de abstracción multiplataforma.

Importa desde adapter.py para obtener las funciones correctas
según el sistema operativo en ejecución.
"""
from .adapter import (
    play_audio,
    speak_tts,
    open_application,
    find_installed_apps,
    close_application,
    take_screenshot,
    get_system_volume,
    set_system_volume,
    mute_system,
    unmute_system,
    copy_to_clipboard,
    PLATFORM,
)

__all__ = [
    "play_audio",
    "speak_tts",
    "open_application",
    "find_installed_apps",
    "close_application",
    "take_screenshot",
    "get_system_volume",
    "set_system_volume",
    "mute_system",
    "unmute_system",
    "copy_to_clipboard",
    "PLATFORM",
]
