#!/usr/bin/env python3
"""
install.py — Instalador inteligente de Nova Personal Assistant
Detecta el sistema operativo e instala las dependencias correctas.

Uso:
  python install.py             # instalación completa (crea .venv)
  python install.py --check     # solo verificar dependencias
  python install.py --uninstall # desinstalar Nova (elimina .venv, lanzadores, PATH)
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
BASE_DIR  = os.path.dirname(os.path.abspath(__file__))

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
        # ("tesseract", "brew install tesseract  # OCR imágenes (opcional)"),
    ],
    "windows": [],
    "linux":   [
        ("espeak-ng", "sudo apt install espeak-ng        # TTS voz"),
        ("mpg123",    "sudo apt install mpg123            # reproducción MP3"),
        ("xclip",     "sudo apt install xclip             # portapapeles"),
        ("scrot",     "sudo apt install scrot             # capturas de pantalla"),
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


# ─── Entorno virtual (.venv) ─────────────────────────────────────────────────

def create_venv() -> str:
    """Crea .venv en el directorio del proyecto y retorna la ruta al Python del venv."""
    venv_dir = os.path.join(BASE_DIR, ".venv")
    if not os.path.exists(venv_dir):
        header("Creando entorno virtual (.venv)")
        try:
            subprocess.run([sys.executable, "-m", "venv", venv_dir], check=True)
            ok(f".venv creado en {venv_dir}")
        except subprocess.CalledProcessError as e:
            warn(f"No se pudo crear .venv: {e} — usando Python del sistema")
            return sys.executable
    else:
        ok(".venv ya existe — reutilizando")

    if PLATFORM == "windows":
        venv_python = os.path.join(venv_dir, "Scripts", "python.exe")
    else:
        venv_python = os.path.join(venv_dir, "bin", "python")

    if not os.path.exists(venv_python):
        warn(f"Python no encontrado en {venv_python} — usando Python del sistema")
        return sys.executable
    return venv_python


# ─── Instalación pip ─────────────────────────────────────────────────────────

def pip_install(packages: list[str], optional: bool = False,
                python_exe: str | None = None) -> bool:
    if not packages:
        return True

    python = python_exe or sys.executable

    # En Windows, PyAudio requiere compilación — intentar wheel precompilado
    if PLATFORM == "windows" and "PyAudio" in packages:
        warn("PyAudio requiere compilación en Windows. Intentando wheel precompilado...")
        packages = [p for p in packages if p != "PyAudio"]
        try:
            subprocess.run(
                [python, "-m", "pip", "install", "--upgrade", "--only-binary", ":all:", "PyAudio"],
                capture_output=True,
            )
        except Exception:
            pass

    cmd = [python, "-m", "pip", "install", "--upgrade", *packages]
    result = subprocess.run(cmd)

    if result.returncode != 0 and optional:
        warn("Algunas dependencias opcionales fallaron (se usarán alternativas)")
        return True
    return result.returncode == 0


# ─── Lanzadores de escritorio ────────────────────────────────────────────────

def _get_desktop() -> str | None:
    """Retorna la ruta al escritorio o None si no se encuentra."""
    home = os.path.expanduser("~")
    for candidate in ["Desktop", "Escritorio", "Bureau", "Schreibtisch"]:
        p = os.path.join(home, candidate)
        if os.path.isdir(p):
            return p
    if PLATFORM == "windows":
        try:
            import ctypes
            buf = ctypes.create_unicode_buffer(260)
            ctypes.windll.shell32.SHGetFolderPathW(0, 0, 0, 0, buf)
            p = buf.value
            if p and os.path.isdir(p):
                return p
        except Exception:
            pass
    return None


def create_desktop_launcher(venv_python: str | None = None) -> None:
    """Crea un acceso directo / lanzador en el escritorio según el OS."""
    desktop = _get_desktop()
    if desktop is None or not os.path.isdir(desktop):
        warn("No se encontró el escritorio — saltando creación de lanzador")
        return

    # Python a usar en los scripts generados
    python_exe = venv_python or sys.executable
    activate_venv_bat = (
        f'if exist "{BASE_DIR}\\.venv\\Scripts\\activate.bat" '
        f'call "{BASE_DIR}\\.venv\\Scripts\\activate.bat"\n'
    )
    activate_venv_sh = (
        f'if [ -f "{BASE_DIR}/.venv/bin/activate" ]; then\n'
        f'    source "{BASE_DIR}/.venv/bin/activate"\n'
        f'fi\n'
    )

    if PLATFORM == "macos":
        # Crear / actualizar launch_nova.sh que activa venv
        sh_path = os.path.join(BASE_DIR, "launch_nova.sh")
        with open(sh_path, "w") as f:
            f.write(
                f'#!/bin/bash\n'
                f'cd "{BASE_DIR}"\n'
                + activate_venv_sh +
                f'export PYTHONPATH="{BASE_DIR}:{BASE_DIR}/src"\n'
                f'"{python_exe}" main.py\n'
            )
        os.chmod(sh_path, 0o755)
        ok(f"launch_nova.sh actualizado")

        app = os.path.join(desktop, "Nova.app")
        try:
            os.makedirs(os.path.join(app, "Contents", "MacOS"), exist_ok=True)
            os.makedirs(os.path.join(app, "Contents", "Resources"), exist_ok=True)

            exe = os.path.join(app, "Contents", "MacOS", "Nova")
            with open(exe, "w") as f:
                f.write(
                    f'#!/bin/bash\n'
                    f'open -a Terminal "{sh_path}"\n'
                )
            os.chmod(exe, 0o755)

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
                    '  <key>CFBundleVersion</key><string>3.2</string>\n'
                    '  <key>CFBundleIconFile</key><string>nova</string>\n'
                    '  <key>CFBundlePackageType</key><string>APPL</string>\n'
                    '</dict></plist>\n'
                )

            # Ícono .icns (desde assets/nova.png si existe iconutil)
            png = os.path.join(BASE_DIR, "assets", "nova.png")
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
                    pass

            ok(f"Lanzador creado: {app}")
        except Exception as e:
            warn(f"No se pudo crear Nova.app en escritorio: {e}")

    elif PLATFORM == "windows":
        ico = os.path.join(BASE_DIR, "assets", "nova.ico")
        bat = os.path.join(BASE_DIR, "launch_nova.bat")
        lnk = os.path.join(desktop, "Nova.lnk")

        with open(bat, "w", encoding="utf-8") as f:
            f.write(
                f'@echo off\n'
                f'cd /d "{BASE_DIR}"\n'
                + activate_venv_bat +
                f'"{python_exe}" main.py\n'
                f'if errorlevel 1 (\n'
                f'    echo.\n'
                f'    echo  Nova cerro con error. Revisa el mensaje de arriba.\n'
                f'    pause\n'
                f')\n'
            )
        ok(f"Wrapper creado: {bat}")

        bat_path  = bat.replace("\\", "\\\\")
        lnk_path  = lnk.replace("\\", "\\\\")
        base_path = BASE_DIR.replace("\\", "\\\\")
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
        # Crear launch_nova.sh con activación de venv
        sh_path = os.path.join(BASE_DIR, "launch_nova.sh")
        with open(sh_path, "w") as f:
            f.write(
                f'#!/bin/bash\n'
                f'cd "{BASE_DIR}"\n'
                + activate_venv_sh +
                f'export PYTHONPATH="{BASE_DIR}:{BASE_DIR}/src"\n'
                f'"{python_exe}" main.py\n'
            )
        os.chmod(sh_path, 0o755)

        launcher = os.path.join(desktop, "nova.desktop")
        png = os.path.join(BASE_DIR, "assets", "nova.png")
        icon_line = f"Icon={png}" if os.path.exists(png) else "Icon=utilities-terminal"
        try:
            with open(launcher, "w") as f:
                f.write(
                    f"[Desktop Entry]\nType=Application\nName=Nova\n"
                    f"Comment=Nova Personal Assistant\n"
                    f"Exec={sh_path}\n"
                    f"Path={BASE_DIR}\n{icon_line}\nTerminal=true\n"
                    f"Categories=Utility;AI;\n"
                )
            os.chmod(launcher, 0o755)
            subprocess.run(["gio", "set", launcher,
                            "metadata::trusted", "true"],
                           capture_output=True)
            ok(f"Lanzador creado: {launcher}")
        except Exception as e:
            warn(f"No se pudo crear lanzador en escritorio: {e}")


# ─── Configuración (.env) ────────────────────────────────────────────────────

def check_env_file() -> bool:
    """Crea .env desde .env.example y pide las API keys interactivamente."""
    import re as _re
    env_path     = os.path.join(BASE_DIR, ".env")
    example_path = os.path.join(BASE_DIR, ".env.example")

    if os.path.exists(env_path):
        ok(".env encontrado")
        return True

    if os.path.exists(example_path):
        shutil.copy(example_path, env_path)
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
    print("  Presioná Enter para saltar cualquier campo.")
    print("  Podés agregarlos después diciendo:")
    print('    "nova, mi api de groq es gsk_xxxx"\n')

    with open(env_path, "r", encoding="utf-8") as _f:
        content = _f.read()

    def _already_set(key: str) -> bool:
        m = _re.search(rf"^{key}=(.+)$", content, _re.MULTILINE)
        if not m:
            return False
        val = m.group(1).strip()
        return bool(val) and "..." not in val and len(val) >= 16

    def _ask_group(hdr: str, note: str, keys: list) -> bool:
        if all(_already_set(k) for k, _ in keys):
            return False
        print(f"\n  ── {hdr} ──")
        if note:
            print(f"  {note}")
        return True

    def _save_key(env_key: str, val: str) -> bool:
        nonlocal content
        if val and "..." not in val and len(val) >= 16:
            if _re.search(rf"^{env_key}=", content, _re.MULTILINE):
                content = _re.sub(
                    rf"^{env_key}=.*$", f"{env_key}={val}",
                    content, flags=_re.MULTILINE
                )
            else:
                content += f"\n{env_key}={val}\n"
            ok(f"{env_key} guardado")
            return True
        info(f"{env_key} omitido — configurable luego desde Nova")
        return False

    any_saved = False

    llm_keys = [
        ("GROQ_API_KEY",       "Groq        (gratis: console.groq.com)"),
        ("OPENROUTER_API_KEY", "OpenRouter  (gratis: openrouter.ai)"),
        ("ANTHROPIC_API_KEY",  "Anthropic   (opcional, de pago)"),
        ("CEREBRAS_API_KEY",   "Cerebras    (gratis: inference.cerebras.ai)"),
        ("MISTRAL_API_KEY",    "Mistral     (free tier: console.mistral.ai)"),
        ("DEEPSEEK_API_KEY",   "DeepSeek    (barato: platform.deepseek.com)"),
    ]
    if _ask_group("LLM Providers", "Al menos uno recomendado. Groq y Cerebras son gratis.", llm_keys):
        for env_key, label in llm_keys:
            if _already_set(env_key):
                continue
            try:
                val = input(f"  {label}\n  {env_key} [Enter para saltar]: ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                val = ""
            if _save_key(env_key, val):
                any_saved = True

    integration_keys = [
        ("TELEGRAM_BOT_TOKEN", "Telegram Bot Token"),
        ("TELEGRAM_CHAT_ID",   "Telegram Chat ID"),
        ("OBSIDIAN_API_KEY",   "Obsidian API Key (plugin Local REST API)"),
        ("GITHUB_TOKEN",       "GitHub Token     (ghp_...)"),
    ]
    if _ask_group("Integraciones", "Todos opcionales — podés configurarlos después.", integration_keys):
        for env_key, label in integration_keys:
            if _already_set(env_key):
                continue
            try:
                val = input(f"  {label}\n  {env_key} [Enter para saltar]: ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                val = ""
            if _save_key(env_key, val):
                any_saved = True

    with open(env_path, "w", encoding="utf-8") as _f:
        _f.write(content)

    print(f"\n  .env en: {env_path}")
    print("─"*60)
    if not any_saved:
        warn("Sin keys — Nova usará Ollama local si está disponible.")
    return True


# ─── Instalación completa ─────────────────────────────────────────────────────

def install_all() -> None:
    header(f"Instalando Nova — plataforma detectada: {PLATFORM.upper()}")

    # 0. Crear entorno virtual
    venv_python = create_venv()

    # 1. Requisitos base
    header("Dependencias base (todas las plataformas)")
    info(f"Instalando {len(BASE_REQUIREMENTS)} paquetes...")
    if pip_install(BASE_REQUIREMENTS, python_exe=venv_python):
        ok("Dependencias base instaladas")
    else:
        err("Algunas dependencias base fallaron — revisá el output")

    # 2. Requisitos de plataforma
    plat_deps = PLATFORM_REQUIREMENTS.get(PLATFORM, [])
    if plat_deps:
        header(f"Dependencias {PLATFORM.upper()}")
        info(f"Instalando {len(plat_deps)} paquetes específicos...")
        if pip_install(plat_deps, optional=True, python_exe=venv_python):
            ok(f"Dependencias {PLATFORM} instaladas")
        else:
            warn(f"Algunas dependencias {PLATFORM} fallaron (pueden ser opcionales)")

    # 2b. Audio opcional
    opt_deps = OPTIONAL_AUDIO.get(PLATFORM, [])
    if opt_deps:
        header("Dependencias opcionales de audio")
        pip_install(opt_deps, optional=True, python_exe=venv_python)

    # 2c. Opcionales generales
    header("Dependencias opcionales (mejoras)")
    pip_install(OPTIONAL_REQUIREMENTS, optional=True, python_exe=venv_python)

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
                [venv_python, "-m", "pip", "install", "--upgrade", "pywin32"],
                capture_output=False,
            )
        except Exception:
            pass

    # 7. Lanzador en el escritorio (apunta a venv python)
    create_desktop_launcher(venv_python=venv_python)

    # ── Resumen final ───────────────────────────────────────────────────────
    print(f"\n{'─'*55}")
    print(f"{BOLD}{GREEN}✓ Nova instalado correctamente.{RESET}")
    print()
    if PLATFORM == "macos":
        print(f"  Hacé doble clic en {BOLD}Nova{RESET} en el Escritorio para iniciar.")
        print(f"  O desde terminal:  {CYAN}./launch_nova.sh{RESET}")
    elif PLATFORM == "windows":
        print(f"  Hacé doble clic en {BOLD}Nova{RESET} en el Escritorio para iniciar.")
        print(f"  O desde terminal:  {CYAN}launch_nova.bat{RESET}")
    else:
        print(f"  Hacé doble clic en {BOLD}Nova{RESET} en el Escritorio para iniciar.")
        print(f"  O desde terminal:  {CYAN}./launch_nova.sh{RESET}")
    print()
    if PLATFORM == "windows":
        input("  Presioná Enter para cerrar el instalador...")
    print()


# ─── Desinstalación ───────────────────────────────────────────────────────────

def uninstall() -> None:
    header("Desinstalando Nova")

    removed_any = False

    # 1. Eliminar entorno virtual
    venv_dir = os.path.join(BASE_DIR, ".venv")
    if os.path.exists(venv_dir):
        try:
            shutil.rmtree(venv_dir)
            ok(".venv eliminado")
            removed_any = True
        except Exception as e:
            warn(f"No se pudo eliminar .venv: {e}")
    else:
        info(".venv no existe — nada que eliminar")

    # 2. Eliminar lanzadores del escritorio
    desktop = _get_desktop()
    if desktop:
        candidates = [
            os.path.join(desktop, "Nova.lnk"),       # Windows
            os.path.join(desktop, "Nova.app"),        # macOS
            os.path.join(desktop, "nova.desktop"),    # Linux
        ]
        for path in candidates:
            if os.path.exists(path):
                try:
                    if os.path.isdir(path):
                        shutil.rmtree(path)
                    else:
                        os.remove(path)
                    ok(f"Eliminado: {path}")
                    removed_any = True
                except Exception as e:
                    warn(f"No se pudo eliminar {path}: {e}")

    # 3. Eliminar scripts de lanzamiento del proyecto
    for launcher in ["launch_nova.bat", "launch_nova.sh"]:
        p = os.path.join(BASE_DIR, launcher)
        if os.path.exists(p):
            try:
                os.remove(p)
                ok(f"Eliminado: {launcher}")
            except Exception as e:
                warn(f"No se pudo eliminar {launcher}: {e}")

    # 4. Eliminar del PATH de Windows (registro)
    if PLATFORM == "windows":
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Environment",
                0, winreg.KEY_READ | winreg.KEY_WRITE
            )
            try:
                path_val, _ = winreg.QueryValueEx(key, "PATH")
                parts = [p for p in path_val.split(";") if BASE_DIR.lower() not in p.lower()]
                new_path = ";".join(parts)
                if new_path != path_val:
                    winreg.SetValueEx(key, "PATH", 0, winreg.REG_EXPAND_SZ, new_path)
                    ok("Eliminado de PATH (registro)")
            except FileNotFoundError:
                pass
            winreg.CloseKey(key)
        except Exception as e:
            warn(f"No se pudo modificar PATH: {e}")

    # 5. Preguntar si eliminar .env
    env_path = os.path.join(BASE_DIR, ".env")
    if os.path.exists(env_path):
        print()
        try:
            resp = input("  ¿Eliminar .env (API keys)? [s/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            resp = "n"
        if resp in ("s", "si", "sí", "y", "yes"):
            try:
                os.remove(env_path)
                ok(".env eliminado")
            except Exception as e:
                warn(f"No se pudo eliminar .env: {e}")
        else:
            info(".env conservado — tus API keys siguen guardadas")

    print()
    if removed_any:
        ok("Nova desinstalado. El código fuente sigue en su lugar.")
        info("Para reinstalar ejecutá: python install.py")
    else:
        info("Nada que eliminar — Nova no estaba instalado.")

    if PLATFORM == "windows":
        input("\n  Presioná Enter para cerrar...")


# ─── Verificación ─────────────────────────────────────────────────────────────

def check_only() -> None:
    header(f"Verificando instalación — {PLATFORM.upper()}")
    check_python_version()
    check_pip()
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

    # Verificar venv
    venv_dir = os.path.join(BASE_DIR, ".venv")
    if os.path.exists(venv_dir):
        ok(f".venv presente en {venv_dir}")
    else:
        warn(".venv no existe — ejecutá python install.py para crearlo")

    print()


# ─── Entry point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Instalador de Nova Personal Assistant")
    parser.add_argument("--check",     action="store_true", help="Solo verificar dependencias")
    parser.add_argument("--uninstall", action="store_true", help="Desinstalar Nova (.venv + lanzadores)")
    args = parser.parse_args()

    if args.uninstall:
        uninstall()
    elif args.check:
        check_only()
    else:
        install_all()
