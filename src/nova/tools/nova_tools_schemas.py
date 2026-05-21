"""
nova_tools_schemas.py
─────────────────────
Genera JSON schemas compatibles con OpenAI function calling desde _TOOL_CATALOG.

Uso:
    from nova.tools.nova_tools_schemas import get_tool_schemas
    schemas = get_tool_schemas()   # lista de dicts OpenAI-compatible
"""
from __future__ import annotations

_ARG_SCHEMAS: dict[str | None, dict] = {
    None: {
        "type": "object",
        "properties": {},
        "required": [],
    },
    "text": {
        "type": "object",
        "properties": {
            "texto": {
                "type": "string",
                "description": "Argumento o texto de la acción",
            }
        },
        "required": ["texto"],
    },
    "location": {
        "type": "object",
        "properties": {
            "location": {
                "type": "string",
                "description": "Ciudad o ubicación geográfica",
            }
        },
        "required": ["location"],
    },
}


def get_tool_schemas(catalog: dict | None = None) -> list[dict]:
    """Convierte _TOOL_CATALOG en una lista de OpenAI function schemas."""
    if catalog is None:
        from nova.tools.nova_skills import _TOOL_CATALOG
        catalog = _TOOL_CATALOG

    schemas: list[dict] = []
    for name, entry in catalog.items():
        desc     = entry[0]
        arg_type = entry[2] if len(entry) > 2 else None
        params   = _ARG_SCHEMAS.get(arg_type, _ARG_SCHEMAS[None])
        schemas.append({
            "type": "function",
            "function": {
                "name":        name,
                "description": str(desc),
                "parameters":  params,
            },
        })
    return schemas


def get_tool_schemas_subset(names: list[str]) -> list[dict]:
    """Retorna schemas solo para las tools indicadas por nombre."""
    from nova.tools.nova_skills import _TOOL_CATALOG
    sub = {k: v for k, v in _TOOL_CATALOG.items() if k in names}
    return get_tool_schemas(sub)


_TOOL_CATEGORIES = {
    "home_assistant": ["ha_", "luces", "luz", "aspiradora", "vacuum", "dispositivo", "escena", "encender", "apagar", "atenuar"],
    "system": ["abrir", "cerrar", "volumen", "brillo", "bateria", "cpu", "memoria", "portapapeles", "tecla", "escribir", "screenshot", "pantalla", "app"],
    "web": ["buscar", "navegar", "url", "noticias", "clima", "tiempo", "internet"],
    "media": ["reproducir", "pausar", "spotify", "musica", "youtube", "camara", "foto", "video"],
    "dev": ["git", "docker", "python", "script", "codigo", "lsp", "workspace", "terminal", "bash", "comando"]
}

def get_filtered_tool_schemas(prompt: str) -> list[dict]:
    """
    Filtra los schemas de herramientas según el prompt para ahorrar tokens.
    Mantiene siempre herramientas core, y añade módulos pesados solo si hay keywords.
    """
    from nova.tools.nova_skills import _TOOL_CATALOG
    prompt_lower = prompt.lower()
    
    active_keys = set(["hora_actual", "fecha_actual", "crear_recordatorio"])
    active_categories = set()
    
    for cat, keywords in _TOOL_CATEGORIES.items():
        if any(kw in prompt_lower for kw in keywords):
            active_categories.add(cat)
            
    # Si no se detectó ninguna categoría fuerte, devolver todas (fallback conservador)
    if not active_categories:
        return get_tool_schemas()

    for tool_name in _TOOL_CATALOG.keys():
        if "ha_" in tool_name and "home_assistant" in active_categories:
            active_keys.add(tool_name)
        elif tool_name in ["abrir_app", "cerrar_app", "controlar_volumen", "controlar_brillo", "leer_portapapeles", "simular_tecla", "escribir_texto", "tomar_screenshot"] and "system" in active_categories:
            active_keys.add(tool_name)
        elif tool_name in ["buscar_web", "clima_actual", "leer_noticias"] and "web" in active_categories:
            active_keys.add(tool_name)
        elif tool_name in ["reproducir_musica", "pausar_musica", "tomar_foto", "grabar_audio"] and "media" in active_categories:
            active_keys.add(tool_name)
        elif tool_name in ["ejecutar_script", "git_status", "docker_ps", "skill_lsp_workspace", "ejecutar_comando"] and "dev" in active_categories:
            active_keys.add(tool_name)
            
    return get_tool_schemas_subset(list(active_keys))
