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
