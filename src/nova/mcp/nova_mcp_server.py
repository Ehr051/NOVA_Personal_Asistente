"""
nova_mcp_server.py
──────────────────
Servidor MCP que expone las skills de Nova a Claude Code y cualquier cliente MCP.

Uso (stdio transport — Claude Code lo lanza automáticamente):
    python -m nova.mcp.nova_mcp_server

Configurar en ~/.claude/claude.json o .claude.json del proyecto:
    {
      "mcpServers": {
        "nova": {
          "command": "python",
          "args": ["-m", "nova.mcp.nova_mcp_server"],
          "cwd": "/ruta/a/NOVA_Personal_Asistente/src"
        }
      }
    }
"""

from __future__ import annotations

import os
import sys
import logging

# Añadir src al path si se ejecuta directamente
_SRC = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from dotenv import load_dotenv
load_dotenv(os.path.join(_SRC, "..", ".env"))

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

log = logging.getLogger("nova_mcp")
logging.basicConfig(level=logging.WARNING)

# ─── Inicializar Nova (router + skills) ──────────────────────────────────────

def _init_nova():
    from nova.core.nova_router import NovaRouter
    from nova.tools.nova_skills import skills as _skills
    from nova.connectors.nova_cerebro import NovaCerebro

    router = NovaRouter()
    _skills.set_router(router)

    cerebro = None
    try:
        cerebro = NovaCerebro()
    except Exception:
        pass

    return router, _skills, cerebro


try:
    _router, _skills, _cerebro = _init_nova()
    _NOVA_READY = True
except Exception as _e:
    log.warning("Nova init parcial: %s", _e)
    _router = None
    _skills = None
    _cerebro = None
    _NOVA_READY = False


# ─── Server MCP ──────────────────────────────────────────────────────────────

server = Server("nova")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="nova_query",
            description=(
                "Envía una consulta en lenguaje natural a Nova. "
                "Nova tiene 100+ skills: código, Blender 3D, sistema, calendario, clima, "
                "traductor, crypto, feriados, búsqueda web, git, y 185 agentes especializados. "
                "Si no hay un skill directo, Nova usa su LLM interno (Groq/Cerebras/Mistral)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Consulta en lenguaje natural (español o inglés)",
                    }
                },
                "required": ["query"],
            },
        ),
        types.Tool(
            name="nova_remember",
            description=(
                "Guarda un hecho en la memoria vectorial de Nova (Mem0 + Qdrant). "
                "Nova lo recordará en futuras conversaciones."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "fact": {
                        "type": "string",
                        "description": "Hecho o preferencia a recordar",
                    }
                },
                "required": ["fact"],
            },
        ),
        types.Tool(
            name="nova_search_cerebro",
            description=(
                "Busca en el Cerebro/Obsidian del usuario — vault personal con notas, "
                "documentos, investigaciones y memoria a largo plazo en ~/Cerebro/."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Término o concepto a buscar en el vault",
                    }
                },
                "required": ["query"],
            },
        ),
        types.Tool(
            name="nova_run_specialist",
            description=(
                "Invoca uno de los 185 agentes especializados de Nova: "
                "Firmware Engineer, Software Architect, AI Engineer, Backend Architect, "
                "Security Auditor, DevOps Engineer, etc. "
                "Útil para tareas técnicas profundas que requieren expertise de dominio."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "description": "Tarea a realizar (ej: 'diseña una API REST para un sistema de sensores IoT')",
                    },
                    "specialist": {
                        "type": "string",
                        "description": "Especialista preferido (opcional, ej: 'Backend Architect', 'AI Engineer')",
                        "default": "",
                    },
                },
                "required": ["task"],
            },
        ),
        types.Tool(
            name="nova_git",
            description=(
                "Operaciones git sobre el proyecto activo de Nova: "
                "status, diff, log, commit (con mensaje generado por IA si no se da), pr."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["status", "diff", "log", "commit", "pr"],
                        "description": "Acción git a ejecutar",
                    },
                    "message": {
                        "type": "string",
                        "description": "Mensaje de commit (solo para action=commit, opcional — se genera con IA si se omite)",
                        "default": "",
                    },
                },
                "required": ["action"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    if not _NOVA_READY:
        return [types.TextContent(type="text", text="Nova no está inicializada correctamente.")]

    try:
        result = await _dispatch_tool(name, arguments)
    except Exception as e:
        result = f"Error ejecutando {name}: {e}"

    return [types.TextContent(type="text", text=str(result))]


async def _dispatch_tool(name: str, args: dict) -> str:
    if name == "nova_query":
        query = args.get("query", "").strip()
        if not query:
            return "Query vacía."
        resp = _skills.dispatch(query)
        if resp:
            return resp
        if _router:
            r = _router.route(
                messages=[{"role": "user", "content": query}],
                force_tier=2,
            )
            return r["response"]
        return "No pude procesar la consulta."

    elif name == "nova_remember":
        fact = args.get("fact", "").strip()
        if not fact:
            return "Hecho vacío."
        try:
            from nova.core.nova_memory import save_turn
            save_turn("user", f"[Recuerda]: {fact}")
            return f"Guardado en memoria: {fact}"
        except Exception as e:
            return f"No pude guardar: {e}"

    elif name == "nova_search_cerebro":
        query = args.get("query", "").strip()
        if not query:
            return "Query vacía."
        if _cerebro:
            try:
                results = _cerebro.buscar(query)
                if not results:
                    return f"No encontré '{query}' en el Cerebro."
                return "\n\n".join(str(r) for r in results[:3])
            except Exception as e:
                return f"Error buscando en Cerebro: {e}"
        return "Cerebro/Obsidian no está disponible."

    elif name == "nova_run_specialist":
        task = args.get("task", "").strip()
        specialist = args.get("specialist", "").strip()
        if not task:
            return "Tarea vacía."
        query = f"actúa como {specialist} y {task}" if specialist else task
        resp = _skills.dispatch(query)
        if resp:
            return resp
        return "No pude invocar el especialista."

    elif name == "nova_git":
        action = args.get("action", "status")
        msg = args.get("message", "")
        from nova.tools.nova_skills import (
            skill_git_status, skill_git_diff, skill_git_log,
            skill_git_commit, skill_git_pr,
        )
        if action == "status":
            return skill_git_status()
        elif action == "diff":
            return skill_git_diff()
        elif action == "log":
            return skill_git_log()
        elif action == "commit":
            return skill_git_commit(msg or "")
        elif action == "pr":
            return skill_git_pr()
        return f"Acción desconocida: {action}"

    return f"Tool desconocida: {name}"


# ─── Entry point ─────────────────────────────────────────────────────────────

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
