#!/usr/bin/env python3
"""
install.py — Instalador inteligente de Nova Personal Assistant
Detecta el sistema operativo e instala las dependencias correctas.

Uso:
  python install.py          # instalación completa
  python install.py --check  # solo verificar dependencias
"""

import sys
import os
import subprocess
import shutil
import argparse

# ─── Colores ANSI ────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def ok(msg):   print(f"{GREEN}  ✓{RESET} {msg}")
def warn(msg): print(f"{YELLOW}  ⚠{RESET} {msg}")
def err(msg):  print(f"{RED}  ✗{RESET} {msg}")
def info(msg): print(f"{CYAN}  →{RESET} {msg}")
def header(msg): print(f"\n{BOLD}{CYAN}{msg}{RESET}")

# ─── Detectar plataforma ─────────────────────────────────────────────────────

def detect_platform() -> str:
    if sys.platform == "darwin":
        return "macos"
    elif sys.platform == "win32":
        return "windows"
    else:
        return "linux"

PLATFORM = detect_platform()

# ─── Requisitos base (todas las plataformas) ─────────────────────────────────

BASE_REQUIREMENTS = [
    "openai>=1.0.0",
    "edge-tts>=6.1.9",
    "SpeechRecognition",
    "python-dotenv",
    "duckduckgo-search",
    "pyautogui",
    "Pillow",
    "requests",
    "numpy",
    "mem0ai",
    "qdrant-client",
    "groq",
    "anthropic",
]

# PyAudio requiere compilación — es opcional, sounddevice es el reemplazo sin compilación
OPTIONAL_AUDIO = {
    "macos":   ["PyAudio"],
    "linux":   ["PyAudio"],
    "windows": [],  # Windows usa sounddevice (WASAPI), PyAudio requiere Visual C++ Build Tools
}

# ─── Requisitos por plataforma ───────────────────────────────────────────────

PLATFORM_REQUIREMENTS = {
    "macos": [
        "rumps",           # menu bar macOS
        "PyQtWebEngine",   # HUD Qt
        "PyQt5",
        "gtts",
    ],
    "windows": [
        "PyQt5",
        "pywin32",         # winreg, COM
        "pycaw",           # control de volumen Windows
        "comtypes",        # pycaw dep
        "pyperclip",       # portapapeles cross-platform
        "sounddevice",     # grabación de audio sin compilación (WASAPI)
    ],
    "linux": [
        "PyQt5",
        "pyperclip",       # portapapeles (requiere xclip/xsel instalado)
        "pygame",          # audio fallback
    ],
}

# ─── Deps de sistema (no-pip) ────────────────────────────────────────────────

SYSTEM_DEPS = {
    "macos":   [],         # macOS ya tiene say, afplay, screencapture, osascript
    "windows": [],         # PowerShell tiene todo lo necesario (SAPI, etc.)
    "linux":   [
        ("espeak-ng", "sudo apt install espeak-ng  # TTS voz"),
        ("mpg123",    "sudo apt install mpg123       # reproducción MP3"),
        ("xclip",     "sudo apt install xclip         # portapapeles"),
        ("scrot",     "sudo apt install scrot          # capturas de pantalla (alternativa: gnome-screenshot)"),
    ],
}

# ─── Checks de versión ───────────────────────────────────────────────────────

def check_python_version() -> bool:
    v = sys.version_info
    if v >= (3, 10):
        ok(f"Python {v.major}.{v.minor}.{v.micro}")
        return True
    err(f"Python {v.major}.{v.minor} — se requiere Python 3.10+")
    return False


def check_pip() -> bool:
    if shutil.which("pip") or shutil.which("pip3"):
        ok("pip disponible")
        return True
    err("pip no encontrado — instalar manualmente")
    return False


def check_ollama() -> bool:
    if shutil.which("ollama"):
        ok("Ollama detectado")
        return True
    warn("Ollama no instalado — Nova funcionará con Groq/OpenRouter (requiere internet)")
    info("Instalar Ollama (para modo local): https://ollama.ai")
    return False


def check_system_deps() -> None:
    deps = SYSTEM_DEPS.get(PLATFORM, [])
    if not deps:
        return
    header("Dependencias de sistema")
    for binary, install_cmd in deps:
        if shutil.which(binary):
            ok(f"{binary} disponible")
        else:
            warn(f"{binary} no encontrado — instalar con: {install_cmd}")


def create_desktop_launcher() -> None:
    """Crea un acceso directo / lanzador en el escritorio según el OS."""
    base = os.path.dirname(os.path.abspath(__file__))
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    if not os.path.isdir(desktop):
        return

    if PLATFORM == "macos":
        script = os.path.join(base, "launch_nova.sh")
        if not os.path.exists(script):
            return
        # Crear un .command doble-clicable en el escritorio
        launcher = os.path.join(desktop, "Nova.command")
        try:
            with open(launcher, "w") as f:
                f.write(f'#!/bin/bash\ncd "{base}"\nbash launch_nova.sh\n')
            os.chmod(launcher, 0o755)
            ok(f"Lanzador creado: {launcher}")
        except Exception as e:
            warn(f"No se pudo crear lanzador en escritorio: {e}")

    elif PLATFORM == "windows":
        # Crear un .bat en el escritorio
        launcher = os.path.join(desktop, "Nova.bat")
        try:
            with open(launcher, "w") as f:
                f.write(f'@echo off\ncd /d "{base}"\npython main.py\npause\n')
            ok(f"Lanzador creado: {launcher}")
        except Exception as e:
            warn(f"No se pudo crear lanzador en escritorio: {e}")

    elif PLATFORM == "linux":
        launcher = os.path.join(desktop, "nova.desktop")
        python = sys.executable
        try:
            with open(launcher, "w") as f:
                f.write(
                    f"[Desktop Entry]\nType=Application\nName=Nova\n"
                    f"Exec={python} {os.path.join(base, 'main.py')}\n"
                    f"Path={base}\nTerminal=true\n"
                )
            os.chmod(launcher, 0o755)
            ok(f"Lanzador creado: {launcher}")
        except Exception as e:
            warn(f"No se pudo crear lanzador en escritorio: {e}")


def check_env_file() -> bool:
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    example_path = os.path.join(os.path.dirname(__file__), ".env.example")
    if os.path.exists(env_path):
        ok(".env encontrado")
        return True
    if os.path.exists(example_path):
        warn(".env no encontrado — copiando .env.example")
        import shutil as _sh
        _sh.copy(example_path, env_path)
        warn("Editá .env y agrega tus API keys (GROQ_API_KEY, OPENROUTER_API_KEY)")
        return True
    warn(".env no encontrado y no hay .env.example — creá uno manualmente")
    return False

# ─── Instalación ─────────────────────────────────────────────────────────────

def pip_install(packages: list[str], optional: bool = False) -> bool:
    if not packages:
        return True

    # En Windows, PyAudio requiere compilación — intentar wheel precompilado
    if PLATFORM == "windows" and "PyAudio" in packages:
        warn("PyAudio requiere compilación en Windows. Intentando wheel precompilado...")
        packages = [p for p in packages if p != "PyAudio"]
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "--upgrade", "--only-binary", ":all:", "PyAudio"],
                capture_output=True,
            )
            if result.returncode != 0:
                warn("No se pudo instalar PyAudio precompilado — se usará sounddevice.")
        except Exception:
            pass

    cmd = [sys.executable, "-m", "pip", "install", "--upgrade", *packages]
    result = subprocess.run(cmd)

    if result.returncode != 0 and optional:
        warn("Algunas dependencias opcionales fallaron (se usarán alternativas)")
        return True
    return result.returncode == 0


def install_all() -> None:
    header(f"Instalando Nova — plataforma detectada: {PLATFORM.upper()}")

    # 1. Requisitos base
    header("Dependencias base (todas las plataformas)")
    info(f"Instalando {len(BASE_REQUIREMENTS)} paquetes...")
    if pip_install(BASE_REQUIREMENTS):
        ok("Dependencias base instaladas")
    else:
        err("Algunas dependencias base fallaron — revisá el output")

    # 2. Requisitos de plataforma
    plat_deps = PLATFORM_REQUIREMENTS.get(PLATFORM, [])
    if plat_deps:
        header(f"Dependencias {PLATFORM.upper()}")
        info(f"Instalando {len(plat_deps)} paquetes específicos...")
        if pip_install(plat_deps, optional=True):
            ok(f"Dependencias {PLATFORM} instaladas")
        else:
            warn(f"Algunas dependencias {PLATFORM} fallaron (pueden ser opcionales)")

    # 2b. Dependencias opcionales (PyAudio como fallback de audio)
    opt_deps = OPTIONAL_AUDIO.get(PLATFORM, [])
    if opt_deps:
        header("Dependencias opcionales de audio")
        info(f"Intentando instalar {len(opt_deps)} paquetes opcionales...")
        pip_install(opt_deps, optional=True)

    # 3. Deps de sistema
    check_system_deps()

    # 4. .env
    header("Configuración")
    check_env_file()

    # 5. Ollama (opcional)
    header("Dependencias opcionales")
    check_ollama()

    # 6. Post-install pywin32 en Windows
    if PLATFORM == "windows":
        try:
            info("Ejecutando post-install de pywin32...")
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "--upgrade", "pywin32"],
                capture_output=False,
            )
        except Exception:
            pass

    # ── Crear lanzador en el escritorio ─────────────────────────────────────
    create_desktop_launcher()

    # ── Resumen final ───────────────────────────────────────────────────────
    print(f"\n{'─'*55}")
    print(f"{BOLD}Nova listo para usar.{RESET}")
    print()
    print("Siguientes pasos:")
    if PLATFORM == "macos":
        print("  1. Editá .env y configurá tus API keys")
        print("  2. chmod +x launch_nova.sh")
        print("  3. ./launch_nova.sh   (o hacer doble clic en el lanzador de Nova en el escritorio)")
    elif PLATFORM == "windows":
        print("  1. Editá .env y configurá tus API keys")
        print("  2. python main.py      (o hacer doble clic en el lanzador de Nova en el escritorio)")
    else:
        print("  1. Editá .env y configurá tus API keys")
        print("  2. python main.py      (o hacer doble clic en el lanzador de Nova en el escritorio)")
    print()


def check_only() -> None:
    header(f"Verificando instalación — {PLATFORM.upper()}")
    ok_py = check_python_version()
    ok_pip = check_pip()
    check_ollama()
    check_system_deps()
    check_env_file()

    # Verificar imports críticos
    header("Módulos Python")
    critical = ["openai", "speech_recognition", "dotenv", "edge_tts"]
    for mod in critical:
        try:
            __import__(mod)
            ok(mod)
        except ImportError:
            err(f"{mod} — ejecutá: python install.py")

    print()


# ─── Entry point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Instalador de Nova Personal Assistant")
    parser.add_argument("--check", action="store_true", help="Solo verificar dependencias")
    args = parser.parse_args()

    if args.check:
        check_only()
    else:
        install_all()
