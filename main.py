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


def _first_run_setup() -> None:
    """Si no hay .env, crea uno desde .env.example y pide las keys opcionales."""
    example = os.path.join(_BASE_DIR, ".env.example")
    if os.path.exists(example):
        import shutil
        shutil.copy(example, _ENV_PATH)

    print("\n" + "─" * 60)
    print("  Nova — Primera configuración")
    print("─" * 60)
    print("  No se encontró .env. Ingresá tus API keys o presioná")
    print("  ENTER para saltar — podés configurarlas más tarde.\n")

    keys = {
        "GROQ_API_KEY":       "Groq  (gratis: console.groq.com)",
        "OPENROUTER_API_KEY": "OpenRouter (gratis: openrouter.ai)",
        "ANTHROPIC_API_KEY":  "Anthropic/Claude (opcional)",
    }

    values: dict[str, str] = {}
    for env_key, label in keys.items():
        try:
            val = input(f"  {label}\n  {env_key} [Enter para saltar]: ").strip()
        except (EOFError, KeyboardInterrupt):
            val = ""
        if val and "..." not in val and len(val) >= 20:
            values[env_key] = val

    if not values:
        print("\n  Sin keys — Nova arrancará con Ollama local si está disponible.")
        print("  Para agregar keys después, escribí en Nova:")
        print('    "nova, mi api de groq es gsk_xxxx"')
    else:
        import re
        with open(_ENV_PATH, "r", encoding="utf-8") as f:
            content = f.read()
        for env_key, val in values.items():
            content = re.sub(rf"^{env_key}=.*$", f"{env_key}={val}", content, flags=re.MULTILINE)
        with open(_ENV_PATH, "w", encoding="utf-8") as f:
            f.write(content)

    print(f"\n  .env en: {_ENV_PATH}")
    print("─" * 60 + "\n")


if __name__ == "__main__":
    # Cargar .env desde la ubicación correcta (junto al ejecutable)
    try:
        from dotenv import load_dotenv
        if os.path.exists(_ENV_PATH):
            load_dotenv(_ENV_PATH)
        else:
            _first_run_setup()
            load_dotenv(_ENV_PATH)
    except ImportError:
        pass

    from nova.lang.novaesp import main as esp_main
    esp_main()
