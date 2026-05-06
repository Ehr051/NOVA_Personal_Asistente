"""
adapter.py — Selecciona el módulo correcto según sys.platform.
"""
import sys

PLATFORM: str  # "macos" | "windows" | "linux"

if sys.platform == "darwin":
    PLATFORM = "macos"
    from .macos import (
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
    )
elif sys.platform == "win32":
    PLATFORM = "windows"
    from .windows import (
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
    )
else:
    PLATFORM = "linux"
    from .linux import (
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
    )
