#!/usr/bin/env python3
"""
Nova Personal Assistant - Entry Point
Lanza el HUD PyQt5 (novaesp.py).

Para el REPL conversacional en terminal: `./nova chat`
"""
import sys
import os
import logging

# Silenciar loggers de librerías y de Nova en uso normal.
# Solo warnings/errores reales llegan a consola.
# Activar DEBUG con: NOVA_LOG_LEVEL=DEBUG python main.py
_log_level = getattr(logging, os.getenv("NOVA_LOG_LEVEL", "WARNING").upper(), logging.WARNING)
logging.basicConfig(level=_log_level, format="%(levelname)s %(name)s: %(message)s")
# Silenciar libs ruidosas siempre (excepto WARNING+)
for _noisy in ("httpx", "httpcore", "openai", "groq", "anthropic",
               "qdrant_client", "mem0", "urllib3", "asyncio"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

# Cuando se empaqueta con PyInstaller, sys.executable es el .exe/.app
# El .env debe estar junto al ejecutable, no dentro del bundle
if getattr(sys, "frozen", False):
    _BASE_DIR = os.path.dirname(sys.executable)
else:
    _BASE_DIR = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, os.path.join(_BASE_DIR, "src"))

_ENV_PATH = os.path.join(_BASE_DIR, ".env")


def _show_error(title: str, msg: str) -> None:
    """Muestra el error en consola y en MessageBox (Windows), luego espera Enter."""
    print(f"\n{'─'*60}\n  {title}\n{'─'*60}\n{msg}\n{'─'*60}")
    log_path = os.path.join(_BASE_DIR, "nova_crash.log")
    try:
        with open(log_path, "w", encoding="utf-8") as _f:
            _f.write(f"{title}\n\n{msg}\n")
        print(f"\n  Log guardado en: {log_path}")
    except Exception:
        pass
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                0, f"{msg}\n\nLog: {log_path}", f"Nova — {title}", 0x10
            )
        except Exception:
            pass
        input("\n  Presioná Enter para cerrar...")


if __name__ == "__main__":
    import traceback
    try:
        try:
            from dotenv import load_dotenv
            if os.path.exists(_ENV_PATH):
                load_dotenv(_ENV_PATH)
            else:
                _show_error(
                    "Falta configuración",
                    "No se encontró .env.\n"
                    "Ejecutá el instalador primero:\n"
                    "  python install.py\n"
                    "Luego volvé a abrir Nova."
                )
                sys.exit(1)
        except ImportError:
            pass  # python-dotenv no instalado — continuar igual

        # Arrancar daemon en background — HUD aparece de inmediato sin esperar
        import threading as _threading
        def _start_daemon_bg():
            try:
                from nova.core.nova_client import NovaDaemonClient
                _dc = NovaDaemonClient(auto_start=True)
                if _dc.ensure_daemon(wait=8.0):
                    print("  [Daemon] Listo — puerto", os.getenv("NOVA_DAEMON_PORT", "7899"))
                else:
                    print("  [Daemon] No disponible — usando router local")
            except Exception:
                pass
        _threading.Thread(target=_start_daemon_bg, daemon=True).start()

        from nova.lang.novaesp import main as esp_main
        esp_main()

    except Exception:
        _show_error("Error al iniciar Nova", traceback.format_exc())
        sys.exit(1)
