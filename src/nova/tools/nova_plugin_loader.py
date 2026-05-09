"""
nova_plugin_loader.py
──────────────────────
Sistema de plugins para Nova — carga skills externas sin tocar el core.

Estructura de un plugin (archivo: nova_plugin_<nombre>.py):

    PLUGIN_META = {
        "name":        "Mi Plugin",
        "version":     "1.0.0",
        "description": "Hace algo útil",
        "author":      "yo",
    }

    # Opcional: intent patterns que se agregan a _INTENTS
    INTENTS = [
        (r"patrón regex (.+)", mi_handler, 1),
    ]

    # Opcional: tools que se agregan a _TOOL_CATALOG
    TOOL_CATALOG = {
        "mi_tool": ("Descripción para LLM", mi_handler, "text"),
    }

    # Opcional: hook de inicialización (recibe el módulo nova_skills)
    def register(skills_module):
        skills_module.set_router(...)   # o cualquier setup

Rutas de búsqueda (en orden):
  1. ~/.nova/plugins/            — plugins del usuario (persisten entre versiones)
  2. <proyecto>/plugins/         — plugins del proyecto activo
  3. <nova_src>/../plugins/      — plugins junto al repo

Uso desde nova_skills.py (al final del módulo):
    from nova.tools.nova_plugin_loader import load_plugins
    load_plugins(_INTENTS, _TOOL_CATALOG, skills_module=sys.modules[__name__])
"""
from __future__ import annotations

import importlib.util
import logging
import os
import sys
from pathlib import Path

log = logging.getLogger(__name__)

_LOADED: list[dict] = []   # lista de PLUGIN_META de plugins cargados


def _plugin_dirs() -> list[Path]:
    dirs: list[Path] = []
    # 1. ~/.nova/plugins/
    dirs.append(Path.home() / ".nova" / "plugins")
    # 2. Junto al repo (NOVA_Personal_Asistente/plugins/)
    src = Path(__file__).resolve().parents[3]   # sube a raíz del proyecto
    dirs.append(src / "plugins")
    # 3. NOVA_PLUGINS_DIR env var personalizado
    env = os.getenv("NOVA_PLUGINS_DIR")
    if env:
        dirs.append(Path(env))
    return dirs


def load_plugins(
    intents: list,
    tool_catalog: dict,
    skills_module=None,
) -> int:
    """
    Carga todos los plugins encontrados en los directorios de búsqueda.
    Modifica `intents` y `tool_catalog` in-place.
    Retorna el número de plugins cargados.
    """
    loaded = 0
    seen: set[str] = set()

    for plugin_dir in _plugin_dirs():
        if not plugin_dir.is_dir():
            continue
        for path in sorted(plugin_dir.glob("nova_plugin_*.py")):
            if path.stem in seen:
                continue
            seen.add(path.stem)
            try:
                _load_one(path, intents, tool_catalog, skills_module)
                loaded += 1
            except Exception as exc:
                log.warning("[Plugin] Error cargando %s: %s", path.name, exc)

    if loaded:
        log.info("[Plugin] %d plugin(s) cargados", loaded)
    return loaded


def _load_one(path: Path, intents: list, tool_catalog: dict, skills_module) -> None:
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod  = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = mod
    spec.loader.exec_module(mod)

    meta = getattr(mod, "PLUGIN_META", {"name": path.stem})
    _LOADED.append(meta)
    name = meta.get("name", path.stem)

    # Registrar INTENTS
    plugin_intents = getattr(mod, "INTENTS", [])
    if plugin_intents:
        intents.extend(plugin_intents)
        log.debug("[Plugin] %s: +%d intents", name, len(plugin_intents))

    # Registrar TOOL_CATALOG
    plugin_tools = getattr(mod, "TOOL_CATALOG", {})
    if plugin_tools:
        tool_catalog.update(plugin_tools)
        log.debug("[Plugin] %s: +%d tools", name, len(plugin_tools))

    # Hook de inicialización
    register_fn = getattr(mod, "register", None)
    if callable(register_fn) and skills_module is not None:
        register_fn(skills_module)

    log.info("[Plugin] Cargado: %s v%s", name, meta.get("version", "?"))


def loaded_plugins() -> list[dict]:
    """Retorna lista de PLUGIN_META de plugins cargados."""
    return list(_LOADED)


def plugin_status() -> str:
    """Resumen para /estado o /skills."""
    if not _LOADED:
        return "Ningún plugin externo cargado."
    lines = [f"Plugins cargados ({len(_LOADED)}):"]
    for p in _LOADED:
        lines.append(f"  • {p.get('name','?')} v{p.get('version','?')} — {p.get('description','')}")
    return "\n".join(lines)
