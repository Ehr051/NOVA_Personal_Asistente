"""
nova_plugin_example.py — Plugin de ejemplo para Nova.

Copiá este archivo a ~/.nova/plugins/ y renombralo nova_plugin_<tuPlugin>.py
para que Nova lo cargue automáticamente al arrancar.

Estructura mínima:
  PLUGIN_META   — metadata del plugin (requerido)
  INTENTS       — patrones de voz/texto (opcional)
  TOOL_CATALOG  — tools para LLM dispatch (opcional)
  register(m)   — hook de inicialización (opcional)
"""

PLUGIN_META = {
    "name":        "Example Plugin",
    "version":     "1.0.0",
    "description": "Plugin de demostración — responde 'nova plugin test'",
    "author":      "tu_nombre",
}

import re


def _skill_plugin_test(texto: str = "") -> str:
    return f"Plugin de ejemplo funcionando. Argumento recibido: '{texto}'"


# Patrones de voz que activan este plugin
INTENTS = [
    (r"(?:nova\s+)?plugin\s+test\s*(.*)", _skill_plugin_test, 1),
]

# Tools disponibles para el LLM dispatcher
TOOL_CATALOG = {
    "plugin_test": ("Test del plugin de ejemplo", _skill_plugin_test, "text"),
}


def register(skills_module):
    """Hook opcional — se llama con el módulo nova_skills como argumento."""
    pass   # Aquí podés acceder a skills_module._router, skills_module._TOOL_CATALOG, etc.
