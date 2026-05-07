#!/usr/bin/env python3
"""
Nova Personal Assistant - Entry Point
Lanza el HUD PyQt5 (novaesp.py).

Para el REPL conversacional en terminal: `./nova chat`
"""
import sys
import os

# Cuando se empaqueta con PyInstaller, sys.executable es el .exe/.app
# El .env debe estar junto al ejecutable, no dentro del bundle
if getattr(sys, "frozen", False):
    _BASE_DIR = os.path.dirname(sys.executable)
else:
    _BASE_DIR = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, os.path.join(_BASE_DIR, "src"))

_ENV_PATH = os.path.join(_BASE_DIR, ".env")


def _first_run_setup() -> None:
    """Si no hay .env, guía al usuario para crear uno con sus API keys."""
    example = os.path.join(_BASE_DIR, ".env.example")
    if os.path.exists(example):
        import shutil
        shutil.copy(example, _ENV_PATH)

    print("\n" + "─" * 60)
    print("  Nova — Primera configuración")
    print("─" * 60)
    print("  No se encontró .env con tus API keys.")
    print("  Completá al menos una para poder usar Nova.\n")

    keys = {
        "GROQ_API_KEY":       ("Groq (gratis en console.groq.com)", "gsk_"),
        "OPENROUTER_API_KEY": ("OpenRouter (gratis en openrouter.ai)", "sk-or-"),
        "ANTHROPIC_API_KEY":  ("Anthropic / Claude (opcional)", "sk-ant-"),
    }

    values: dict[str, str] = {}
    for env_key, (label, prefix) in keys.items():
        val = input(f"  {label}\n  {env_key}: ").strip()
        if val:
            values[env_key] = val

    if not values:
        print("\n  [!] No ingresaste ninguna key — Nova usará Ollama local si está disponible.")
        print("      Editá .env para agregar keys más tarde.\n")

    # Leer el .env base y reemplazar placeholders
    with open(_ENV_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    for env_key, val in values.items():
        import re
        content = re.sub(rf"^{env_key}=.*$", f"{env_key}={val}", content, flags=re.MULTILINE)

    with open(_ENV_PATH, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"\n  .env guardado en: {_ENV_PATH}")
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
