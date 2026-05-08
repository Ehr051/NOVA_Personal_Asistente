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


if __name__ == "__main__":
    # Cargar .env desde la ubicación correcta (junto al ejecutable)
    try:
        from dotenv import load_dotenv
        if os.path.exists(_ENV_PATH):
            load_dotenv(_ENV_PATH)
        else:
            print("\n" + "─" * 60)
            print("  Nova — Falta configuración")
            print("─" * 60)
            print("  No se encontró .env.")
            print("  Ejecutá el instalador primero:\n")
            print("    python install.py\n")
            print("  Luego volvé a abrir Nova.")
            print("─" * 60)
            if sys.platform == "win32":
                input("\n  Presioná Enter para cerrar...")
            sys.exit(1)
    except ImportError:
        pass  # python-dotenv no instalado — continuar igual

    from nova.lang.novaesp import main as esp_main
    esp_main()
