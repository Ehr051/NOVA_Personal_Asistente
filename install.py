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
    # LSP semántico
    "jedi>=0.19.0",
    # OCR y documentos (PDF/DOCX/XLSX → Markdown)
    "markitdown>=0.1.0",
]

OPTIONAL_REQUIREMENTS = [
    # Mejor detección de idioma (modo políglota)
    "langdetect",
    # OCR de imágenes (requiere Tesseract instalado a nivel sistema)
    "pytesseract",
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
    "macos":   [
        # tesseract para OCR de imágenes (opcional)
        # ("tesseract", "brew install tesseract  # OCR imágenes (opcional)"),
    ],
    "windows": [],         # PowerShell tiene todo lo necesario (SAPI, etc.)
    "linux":   [
        ("espeak-ng", "sudo apt install espeak-ng        # TTS voz"),
        ("mpg123",    "sudo apt install mpg123            # reproducción MP3"),
        ("xclip",     "sudo apt install xclip             # portapapeles"),
        ("scrot",     "sudo apt install scrot             # capturas de pantalla"),
        # tesseract para OCR de imágenes (opcional)
        # ("tesseract", "sudo apt install tesseract-ocr tesseract-ocr-spa  # OCR"),
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

    # Detectar escritorio en inglés y español (Windows puede ser "Escritorio")
    home = os.path.expanduser("~")
    desktop = None
    for candidate in ["Desktop", "Escritorio", "Bureau", "Schreibtisch"]:
        p = os.path.join(home, candidate)
        if os.path.isdir(p):
            desktop = p
            break
    # Fallback: pedir ruta via WinAPI si estamos en Windows
    if desktop is None and PLATFORM == "windows":
        try:
            import ctypes
            buf = ctypes.create_unicode_buffer(260)
            ctypes.windll.shell32.SHGetFolderPathW(0, 0, 0, 0, buf)
            desktop = buf.value  # CSIDL_DESKTOP
        except Exception:
            pass
    if desktop is None or not os.path.isdir(desktop):
        warn("No se encontró el escritorio — saltando creación de lanzador")
        return

    if PLATFORM == "macos":
        app = os.path.join(desktop, "Nova.app")
        try:
            os.makedirs(os.path.join(app, "Contents", "MacOS"), exist_ok=True)
            os.makedirs(os.path.join(app, "Contents", "Resources"), exist_ok=True)

            # Ejecutable principal
            exe = os.path.join(app, "Contents", "MacOS", "Nova")
            with open(exe, "w") as f:
                f.write(
                    f'#!/bin/bash\n'
                    f'cd "{base}"\n'
                    f'export PATH="$HOME/.pyenv/versions/3.10.6/bin:$PATH"\n'
                    f'export PYTHONPATH="{base}:{base}/src"\n'
                    f'open -a Terminal "{base}/launch_nova.sh"\n'
                )
            os.chmod(exe, 0o755)

            # Info.plist
            with open(os.path.join(app, "Contents", "Info.plist"), "w") as f:
                f.write(
                    '<?xml version="1.0" encoding="UTF-8"?>\n'
                    '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"'
                    ' "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
                    '<plist version="1.0"><dict>\n'
                    '  <key>CFBundleExecutable</key><string>Nova</string>\n'
                    '  <key>CFBundleIdentifier</key><string>com.ehr051.nova</string>\n'
                    '  <key>CFBundleName</key><string>Nova</string>\n'
                    '  <key>CFBundleDisplayName</key><string>Nova</string>\n'
                    '  <key>CFBundleVersion</key><string>3.1</string>\n'
                    '  <key>CFBundleIconFile</key><string>nova</string>\n'
                    '  <key>CFBundlePackageType</key><string>APPL</string>\n'
                    '</dict></plist>\n'
                )

            # Ícono .icns (generado desde assets/nova.png si existe iconutil)
            png = os.path.join(base, "assets", "nova.png")
            if os.path.exists(png) and shutil.which("iconutil"):
                try:
                    import tempfile
                    from PIL import Image
                    iconset = tempfile.mkdtemp(suffix=".iconset")
                    img = Image.open(png).convert("RGBA")
                    for s in [16, 32, 64, 128, 256, 512]:
                        img.resize((s, s), Image.LANCZOS).save(
                            os.path.join(iconset, f"icon_{s}x{s}.png"))
                        img.resize((s*2, s*2), Image.LANCZOS).save(
                            os.path.join(iconset, f"icon_{s}x{s}@2x.png"))
                    icns = os.path.join(app, "Contents", "Resources", "nova.icns")
                    subprocess.run(["iconutil", "-c", "icns", iconset, "-o", icns],
                                   capture_output=True)
                    shutil.rmtree(iconset, ignore_errors=True)
                except Exception:
                    pass  # sin ícono personalizado — Finder usa el genérico

            ok(f"Lanzador creado: {app}")
        except Exception as e:
            warn(f"No se pudo crear Nova.app en escritorio: {e}")

    elif PLATFORM == "windows":
        # Siempre crear launch_nova.bat en el directorio del proyecto.
        # El .bat mantiene la ventana abierta si hay error (pause al final).
        ico  = os.path.join(base, "assets", "nova.ico")
        bat  = os.path.join(base, "launch_nova.bat")
        lnk  = os.path.join(desktop, "Nova.lnk")
        python_exe = sys.executable

        with open(bat, "w", encoding="utf-8") as f:
            f.write(
                f'@echo off\n'
                f'cd /d "{base}"\n'
                f'"{python_exe}" main.py\n'
                f'if errorlevel 1 (\n'
                f'    echo.\n'
                f'    echo  Nova cerro con error. Revisa el mensaje de arriba.\n'
                f'    pause\n'
                f')\n'
            )
        ok(f"Wrapper creado: {bat}")

        # Crear .lnk que apunta al .bat (ventana no desaparece en error)
        bat_path  = bat.replace("\\", "\\\\")
        lnk_path  = lnk.replace("\\", "\\\\")
        base_path = base.replace("\\", "\\\\")
        ico_path  = ico.replace("\\", "\\\\")
        ps_script = (
            f'$ws = New-Object -ComObject WScript.Shell; '
            f'$sc = $ws.CreateShortcut("{lnk_path}"); '
            f'$sc.TargetPath = "cmd.exe"; '
            f'$sc.Arguments = \'/c ""{bat_path}""\'; '
            f'$sc.WorkingDirectory = "{base_path}"; '
            f'$sc.Description = "Nova Personal Assistant"; '
            f'$sc.WindowStyle = 1; '
            + (f'$sc.IconLocation = "{ico_path},0"; ' if os.path.exists(ico) else '') +
            f'$sc.Save()'
        )
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_script],
                capture_output=True, text=True
            )
            if result.returncode == 0 and os.path.exists(lnk):
                ok(f"Lanzador creado: {lnk}")
            else:
                warn(f"Shortcut no disponible — usá {bat} directamente")
        except Exception as e:
            warn(f"No se pudo crear lanzador en escritorio: {e}")

    elif PLATFORM == "linux":
        launcher = os.path.join(desktop, "nova.desktop")
        python   = sys.executable
        png      = os.path.join(base, "assets", "nova.png")
        icon_line = f"Icon={png}" if os.path.exists(png) else "Icon=utilities-terminal"
        try:
            with open(launcher, "w") as f:
                f.write(
                    f"[Desktop Entry]\nType=Application\nName=Nova\n"
                    f"Comment=Nova Personal Assistant\n"
                    f"Exec={python} {os.path.join(base, 'main.py')}\n"
                    f"Path={base}\n{icon_line}\nTerminal=true\n"
                    f"Categories=Utility;AI;\n"
                )
            os.chmod(launcher, 0o755)
            # Marcar como confiable (GNOME/KDE)
            subprocess.run(["gio", "set", launcher,
                            "metadata::trusted", "true"],
                           capture_output=True)
            ok(f"Lanzador creado: {launcher}")
        except Exception as e:
            warn(f"No se pudo crear lanzador en escritorio: {e}")


def check_env_file() -> bool:
    """Crea .env desde .env.example y pide las API keys interactivamente."""
    import re as _re
    base = os.path.dirname(os.path.abspath(__file__))
    env_path     = os.path.join(base, ".env")
    example_path = os.path.join(base, ".env.example")

    if os.path.exists(env_path):
        ok(".env encontrado")
        return True

    if os.path.exists(example_path):
        import shutil as _sh
        _sh.copy(example_path, env_path)
    else:
        warn(".env.example no encontrado — creando .env mínimo")
        with open(env_path, "w", encoding="utf-8") as _f:
            _f.write(
                "GROQ_API_KEY=\nOPENROUTER_API_KEY=\nANTHROPIC_API_KEY=\n"
                "OLLAMA_BASE_URL=http://127.0.0.1:11434/v1\n"
                "ASSISTANT_NAME=Nova\nNOVA_VOICE=Reed\n"
            )

    print(f"\n{'─'*60}")
    print("  Nova — Configuración de API Keys")
    print("─"*60)
    print("  Presioná ENTER para saltar cualquier key.")
    print("  Podés agregarlas después diciendo:")
    print('    "nova, mi api de groq es gsk_xxxx"\n')

    keys = [
        ("GROQ_API_KEY",       "Groq        (gratis: console.groq.com)"),
        ("OPENROUTER_API_KEY", "OpenRouter  (gratis: openrouter.ai)"),
        ("ANTHROPIC_API_KEY",  "Anthropic   (opcional, de pago)"),
    ]

    with open(env_path, "r", encoding="utf-8") as _f:
        content = _f.read()

    any_saved = False
    for env_key, label in keys:
        try:
            val = input(f"  {label}\n  {env_key} [Enter para saltar]: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            val = ""
        if val and "..." not in val and len(val) >= 16:
            content = _re.sub(
                rf"^{env_key}=.*$", f"{env_key}={val}",
                content, flags=_re.MULTILINE
            )
            if f"{env_key}=" not in content:
                content += f"\n{env_key}={val}\n"
            ok(f"{env_key} guardado")
            any_saved = True
        else:
            info(f"{env_key} omitido — configurable luego desde Nova")

    with open(env_path, "w", encoding="utf-8") as _f:
        _f.write(content)

    print(f"\n  .env en: {env_path}")
    print("─"*60)
    if not any_saved:
        warn("Sin keys — Nova usará Ollama local si está disponible.")
    return True

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

    # 2c. Dependencias opcionales generales (LSP mejorado, OCR, políglota)
    header("Dependencias opcionales (mejoras)")
    info(f"Intentando instalar {len(OPTIONAL_REQUIREMENTS)} paquetes opcionales...")
    pip_install(OPTIONAL_REQUIREMENTS, optional=True)

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
    print(f"{BOLD}{GREEN}✓ Nova instalado correctamente.{RESET}")
    print()
    if PLATFORM == "macos":
        print(f"  Hacé doble clic en {BOLD}Nova{RESET} en el Escritorio para iniciar.")
        print(f"  O desde terminal:  {CYAN}./launch_nova.sh{RESET}")
    elif PLATFORM == "windows":
        print(f"  Hacé doble clic en {BOLD}Nova{RESET} en el Escritorio para iniciar.")
        print(f"  O desde terminal:  {CYAN}python main.py{RESET}")
    else:
        print(f"  Hacé doble clic en {BOLD}Nova{RESET} en el Escritorio para iniciar.")
        print(f"  O desde terminal:  {CYAN}python main.py{RESET}")
    print()
    if PLATFORM == "windows":
        input("  Presioná Enter para cerrar el instalador...")
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
