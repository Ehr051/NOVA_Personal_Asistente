"""
Nova REPL — conversación interactiva en terminal (estilo claude / opencode).

Lanzamiento:
    python3 nova chat

Slash commands (autocompleten con Tab si prompt_toolkit está instalado):
    /help                    Lista de comandos
    /exit, /quit             Salir
    /clear                   Limpia pantalla y contexto de la sesión
    /skills                  Lista de skills locales disponibles
    /skill <texto>           Dispatcha la skill (ej: /skill qué hora es)
    /agent <nombre> [args]   Ejecuta un agente (morning, research, code, orchestrator)
    /recall <query>          Busca en la memoria neuronal
    /remember <hecho>        Guarda un hecho en la memoria neuronal
    /forget <key>            Borra un hecho de la memoria neuronal
    /status                  Estado del sistema (Ollama, n8n, Drive, memoria)

Texto sin `/` → enrutado al LLM (Ollama → Groq → OpenRouter) con skills + memoria.
"""

from __future__ import annotations

import logging
import os
import sys
import subprocess
import datetime
from typing import Callable, Optional

log = logging.getLogger(__name__)

# Carga lazy de los componentes pesados (no bloquear el import del módulo)
_router = None
_skills = None
_neuro  = None
_daemon_client = None   # NovaDaemonClient si el daemon está corriendo


def _try_daemon() -> bool:
    """Intenta conectar al daemon. Retorna True si disponible."""
    global _daemon_client
    try:
        from nova.core.nova_client import NovaDaemonClient
        c = NovaDaemonClient(auto_start=False)
        if c.ping():
            _daemon_client = c
            return True
    except Exception:
        pass
    _daemon_client = None
    return False


def _lazy_init():
    """Inicializa router, skills y memoria una sola vez."""
    global _router, _skills, _neuro

    # Preferir daemon: evita conflicto de Qdrant entre REPL y HUD
    if _try_daemon():
        # Con daemon activo no instanciamos router/memoria locales
        if _skills is None:
            try:
                from nova.tools import nova_skills
                _skills = nova_skills
            except Exception as e:
                print(f"[REPL] Aviso: skills no disponibles ({e})")
                _skills = False
        if _router is None:
            _router = False  # daemon maneja el router
        if _neuro is None:
            _neuro = False   # daemon maneja la memoria
        return

    if _router is None:
        try:
            from nova.core.nova_router import NovaRouter
            _router = NovaRouter()
        except Exception as e:
            print(f"[REPL] Aviso: router LLM no disponible ({e})")
            _router = False

    if _skills is None:
        try:
            from nova.tools import nova_skills
            _skills = nova_skills
            if hasattr(nova_skills, "set_router") and _router and _router is not False:
                nova_skills.set_router(_router)
        except Exception as e:
            print(f"[REPL] Aviso: skills no disponibles ({e})")
            _skills = False

    if _neuro is None:
        try:
            from nova.tools.nova_neuro_memory import neuro_memory
            _neuro = neuro_memory
        except Exception as e:
            print(f"[REPL] Aviso: memoria neuronal no disponible ({e})")
            _neuro = False


# ─── Lectura de input con prompt_toolkit (opcional) ──────────────────────────

def _make_reader() -> Callable[[str], str]:
    """Devuelve una función read(prompt) que lee input del usuario.

    Usa prompt_toolkit si está disponible (autocomplete + history).
    Fallback: input() estándar.
    """
    try:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.completion import Completer, Completion
        from prompt_toolkit.history import FileHistory
        from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
        from prompt_toolkit.styles import Style

        history_file = os.path.expanduser("~/.nova/repl_history")
        os.makedirs(os.path.dirname(history_file), exist_ok=True)

        # Solo comandos principales en español para el popup
        _CMD_META = {
            cmd: desc for cmd, (_, desc) in SLASH_COMMANDS.items()
            if not desc.startswith("→")   # excluir aliases inglés
        }
        _CMD_META.update({
            "/agente briefing":      "Briefing del día",
            "/agente búsqueda":    "Investigación profunda",
            "/agente código":      "Asistente de código",
            "/agente orquestador": "Razonamiento multi-turno",
        })

        class NovaCompleter(Completer):
            def get_completions(self, document, complete_event):
                text = document.text_before_cursor
                if not text.startswith("/"):
                    return
                for cmd, meta in sorted(_CMD_META.items()):
                    if cmd.startswith(text):
                        yield Completion(
                            cmd[len(text):],
                            start_position=0,
                            display=cmd,
                            display_meta=meta,
                        )

        pt_style = Style.from_dict({
            "completion-menu.completion":        "bg:#1e2030 #cdd6f4",
            "completion-menu.completion.current": "bg:#89b4fa #1e2030 bold",
            "completion-menu.meta.completion":    "bg:#1e2030 #6c7086",
            "completion-menu.meta.current":       "bg:#89b4fa #1e2030",
        })

        session = PromptSession(
            history=FileHistory(history_file),
            auto_suggest=AutoSuggestFromHistory(),
            completer=NovaCompleter(),
            complete_while_typing=True,
            style=pt_style,
        )

        def reader(prompt: str) -> str:
            return session.prompt(prompt)
        return reader
    except ImportError:
        def reader(prompt: str) -> str:
            return input(prompt)
        return reader


# ─── Slash commands ──────────────────────────────────────────────────────────

def cmd_help(_: str) -> Optional[str]:
    lines = ["Comandos disponibles:\n"]
    shown = set()
    for name, (handler, desc) in sorted(SLASH_COMMANDS.items()):
        # Mostrar solo los nombres principales (sin aliases)
        if handler not in shown:
            lines.append(f"  {name:<22} {desc}")
            shown.add(handler)
    lines.append("")
    lines.append("Texto sin '/' → enrutado al LLM con acceso a skills y memoria.")
    return "\n".join(lines)


def cmd_exit(_: str) -> Optional[str]:
    print("Hasta luego, Señor.")
    sys.exit(0)


def cmd_clear(_: str) -> Optional[str]:
    os.system("clear" if os.name != "nt" else "cls")
    _session_state["history"] = []
    return "Pantalla y contexto de sesión limpiados."


def cmd_skills_list(_: str) -> Optional[str]:
    _lazy_init()
    if not _skills:
        return "Skills no disponibles."
    if hasattr(_skills, "capabilities_summary"):
        return _skills.capabilities_summary()
    import inspect
    names = [
        n for n, o in inspect.getmembers(_skills)
        if inspect.isfunction(o) and n.startswith("skill_")
    ]
    return "Skills disponibles:\n" + "\n".join(f"  • {n}" for n in sorted(names))


def cmd_skill(arg: str) -> Optional[str]:
    _lazy_init()
    if not _skills:
        return "Skills no disponibles."
    if not arg.strip():
        return "Uso: /skill <texto> — ej: /skill qué hora es"
    resp = _skills.dispatch(arg)
    return resp or "Ninguna skill coincidió con ese texto."


def cmd_agente(arg: str) -> Optional[str]:
    """Ejecuta un agente por nombre en español o inglés."""
    parts = arg.strip().split(maxsplit=1)
    if not parts:
        return (
            "Uso: /agente <nombre> [args]\n"
            "  briefing          Briefing del día\n"
            "  búsqueda <tema> Investigación profunda\n"
            "  código <tarea>  Asistente de código\n"
            "  orquestador <objetivo>  Razonamiento multi-turno"
        )
    # Aliases español ↔ inglés
    _ALIAS = {
        "briefing": "morning",
        "búsqueda": "research", "busqueda": "research", "investigar": "research",
        "código": "code", "codigo": "code",
        "orquestador": "orchestrator", "orchestrator": "orchestrator",
        # inglés directo también funciona
        "morning": "morning", "research": "research",
        "code": "code",
    }
    name = _ALIAS.get(parts[0].lower(), parts[0].lower())
    rest = parts[1] if len(parts) > 1 else ""

    try:
        if name == "morning":
            from nova.agents.morning_digest import morning_digest
            return morning_digest()
        elif name == "research":
            if not rest:
                return "Uso: /agente búsqueda <tema>"
            from nova.agents.research_agent import research
            return research(rest)
        elif name == "code":
            if not rest:
                return "Uso: /agente código <tarea>"
            from nova.agents.code_assistant import explain_code
            return explain_code(rest)
        elif name == "orchestrator":
            if not rest:
                return "Uso: /agente orquestador <objetivo>"
            from nova.agents.orchestrator_agent import orchestrator_execute
            return orchestrator_execute(rest, max_turns=5)
        else:
            return (
                f"Agente desconocido: '{parts[0]}'. "
                "Opciones: briefing · búsqueda · código · orquestador"
            )
    except Exception as e:
        return f"Error ejecutando agente: {e}"


def cmd_reiniciar(_: str) -> Optional[str]:
    """Reinicia Nova en el mismo proceso — recarga módulos para aplicar cambios."""
    print("Reiniciando Nova...", flush=True)
    import importlib
    # Recargar módulos clave sin cerrar el proceso
    mods_to_reload = [
        "nova.tools.nova_skills",
        "nova.core.nova_router",
        "nova.connectors.nova_vision",
        "nova.connectors.nova_blender",
        "nova.agents.nova_orchestrator",
        "nova.tools.nova_neuro_memory",
    ]
    reloaded, failed = [], []
    for mod_name in mods_to_reload:
        if mod_name in sys.modules:
            try:
                importlib.reload(sys.modules[mod_name])
                reloaded.append(mod_name.split(".")[-1])
            except Exception as e:
                failed.append(f"{mod_name.split('.')[-1]}: {e}")
    # Resetear las referencias globales del REPL
    globals()["_router"] = None
    globals()["_skills"] = None
    globals()["_neuro"] = None
    globals()["_ENV_CTX"] = _get_env_context()
    _lazy_init()
    # Reimprimir banner
    _print_banner(_ENV_CTX)
    parts = [f"Recargados: {', '.join(reloaded)}"] if reloaded else []
    if failed:
        parts.append(f"Fallidos: {', '.join(failed)}")
    return "\n".join(parts) if parts else "Nova reiniciada."


def cmd_tarea(arg: str) -> Optional[str]:
    """Orquesta un objetivo complejo con herramientas reales y progreso en vivo."""
    if not arg.strip():
        return (
            "Uso: /tarea <objetivo>\n"
            "  Nova planifica los pasos, ejecuta herramientas reales y reporta.\n"
            "  Ej: /tarea analizá los tests que fallan y arreglalos\n"
            "  Ej: /tarea buscá todos los TODO en el código y creá un resumen\n"
            "  Ej: /tarea investigá sobre WebSockets en Python y resumí"
        )
    try:
        from nova.agents.nova_orchestrator import orquestar
        # orquestar ya imprime el progreso en vivo, retorna el resumen
        resumen = orquestar(arg.strip(), verbose=True)
        return None   # ya imprimió todo
    except Exception as e:
        return f"Error en orquestación: {e}"


def cmd_recordar(arg: str) -> Optional[str]:
    _lazy_init()
    if not _neuro:
        return "Memoria neuronal no disponible."
    if not arg.strip():
        return "Uso: /recordar <query>"
    ctx = _neuro.search_context(arg.strip())
    return ctx or "Sin coincidencias en la memoria."


def cmd_guardar(arg: str) -> Optional[str]:
    _lazy_init()
    if not _neuro:
        return "Memoria neuronal no disponible."
    if not arg.strip():
        return "Uso: /guardar <hecho a recordar>"
    _neuro.remember(arg.strip())
    return "Anotado, Señor."


def cmd_olvidar(arg: str) -> Optional[str]:
    _lazy_init()
    if not _skills or not hasattr(_skills, "skill_forget"):
        return "skill_forget no disponible."
    if not arg.strip():
        return "Uso: /olvidar <clave>"
    return _skills.skill_forget(arg.strip())


def cmd_estado(_: str) -> Optional[str]:
    lines = ["Estado del sistema Nova:"]
    _lazy_init()

    if _router and _router is not False:
        providers = (
            getattr(_router, "provider_order", None)
            or getattr(_router, "providers", None)
            or getattr(_router, "_providers", None)
        )
        providers_str = ", ".join(providers) if isinstance(providers, list) else str(providers) if providers else "N/A"
        lines.append(f"  ✓ Router LLM activo ({providers_str})")
    else:
        lines.append("  ✗ Router LLM no disponible")

    if _neuro and _neuro is not False:
        try:
            facts = _neuro.get_all_facts()
            count = facts.count("\n- ") if isinstance(facts, str) else 0
            lines.append(f"  ✓ Memoria neuronal ({count} entradas aprox.)")
        except Exception as e:
            lines.append(f"  ⚠ Memoria neuronal con error: {e}")
    else:
        lines.append("  ✗ Memoria neuronal no disponible")

    try:
        from nova.connectors import nova_n8n as n8n
        lines.append(f"  → n8n: {n8n.estado_n8n()}")
    except Exception as e:
        lines.append(f"  ⚠ n8n: {e}")

    return "\n".join(lines)


def cmd_stats(_: str) -> Optional[str]:
    """Muestra estadísticas de uso de modelos LLM."""
    import json as _json
    from pathlib import Path as _Path
    stats_path = _Path(__file__).parents[3] / "model_stats.json"
    if not stats_path.exists():
        return "Sin estadísticas todavía. Usá Nova un rato y volvé."
    try:
        data = _json.loads(stats_path.read_text())
        lines = ["Estadísticas de modelos:\n"]
        for proveedor, info in sorted(data.items()):
            if not isinstance(info, dict):
                continue
            ok    = info.get("success", 0)
            fail  = info.get("failure", 0)
            total = ok + fail
            if total == 0:
                continue
            pct   = int(ok / total * 100) if total else 0
            lat   = info.get("avg_latency", 0)
            bar_w = 20
            filled = int(bar_w * pct / 100)
            bar = "█" * filled + "░" * (bar_w - filled)
            lines.append(f"  {proveedor:<14} [{bar}] {pct:3}%  "
                          f"{ok}ok / {fail}fail  lat:{lat:.1f}s")
        if len(lines) == 1:
            return "Sin datos suficientes todavía."
        return "\n".join(lines)
    except Exception as e:
        return f"Error leyendo estadísticas: {e}"


def cmd_doctor(arg: str) -> Optional[str]:
    """Diagnóstico del sistema. --fix intenta reparar automáticamente."""
    fix_mode = "--fix" in arg
    lines = ["Diagnóstico Nova:\n"]
    _lazy_init()
    ok = "✓"; warn = "⚠"; err = "✗"

    # Router LLM
    if _router and _router is not False:
        providers = getattr(_router, "provider_order", [])
        lines.append(f"  {ok} Router LLM  ({', '.join(providers) if providers else 'activo'})")
    else:
        lines.append(f"  {err} Router LLM  — no disponible")
        if fix_mode:
            lines.append("     → intentando reiniciar router...")
            globals()["_router"] = None
            _lazy_init()

    # Ollama
    try:
        import urllib.request
        urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=2)
        lines.append(f"  {ok} Ollama       — conectado")
    except Exception:
        lines.append(f"  {err} Ollama       — no responde  (iniciá con: ollama serve)")

    # Groq key
    import os
    groq_key = os.getenv("GROQ_API_KEY", "")
    if groq_key and not groq_key.startswith("gsk_..."):
        lines.append(f"  {ok} Groq API key — configurada")
    else:
        lines.append(f"  {warn} Groq API key — no encontrada  (agregá GROQ_API_KEY en .env)")

    # Anthropic / Claude
    anthro_key = os.getenv("ANTHROPIC_API_KEY", "")
    if anthro_key:
        lines.append(f"  {ok} Claude (Anthropic) — key configurada")
    else:
        lines.append(f"  {warn} Claude (Anthropic) — no configurado  (ANTHROPIC_API_KEY en .env)")

    # OpenAI
    oai_key = os.getenv("OPENAI_API_KEY", "")
    if oai_key:
        lines.append(f"  {ok} OpenAI — key configurada")
    else:
        lines.append(f"  {warn} OpenAI — no configurado  (OPENAI_API_KEY en .env)")

    # Blender
    try:
        import socket
        with socket.create_connection(("127.0.0.1", 9876), timeout=1):
            lines.append(f"  {ok} Blender MCP  — conectado en :9876")
    except Exception:
        lines.append(f"  {warn} Blender MCP  — no conectado  (abrí Blender → addon MCP → Start Server)")

    # n8n
    try:
        import urllib.request
        urllib.request.urlopen("http://localhost:5678/healthz", timeout=2)
        lines.append(f"  {ok} n8n          — operativo en :5678")
    except Exception:
        lines.append(f"  {warn} n8n          — no responde")

    # Memoria neuronal
    if _neuro and _neuro is not False:
        lines.append(f"  {ok} Memoria neuronal — activa")
    else:
        lines.append(f"  {err} Memoria neuronal — no disponible")

    if fix_mode:
        lines.append("\n[--fix] Diagnóstico completado. Revisá los ✗ y ⚠ manualmente si persisten.")
    return "\n".join(lines)


def cmd_cerebro(arg: str) -> Optional[str]:
    """Busca en el vault Cerebro. Sin arg muestra estado."""
    try:
        from nova.connectors.nova_cerebro import (
            cerebro_buscar, cerebro_estado, cerebro_listar, cerebro_leer
        )
    except ImportError:
        return "Conector Cerebro no disponible."

    arg = arg.strip()
    if not arg:
        return cerebro_estado()

    # /cerebro listar [carpeta]
    if arg.startswith("listar") or arg.startswith("ls"):
        carpeta = arg.split(None, 1)[1] if len(arg.split(None, 1)) > 1 else ""
        archivos = cerebro_listar(carpeta)
        if not archivos:
            return f"No hay archivos en '{carpeta or '/'}'"
        return "\n".join(f"  {a}" for a in archivos[:30])

    # /cerebro leer <ruta>
    if arg.startswith("leer ") or arg.startswith("ver "):
        ruta = arg.split(None, 1)[1]
        return cerebro_leer(ruta)

    # Default: buscar
    hits = cerebro_buscar(arg, max_resultados=5)
    if not hits:
        return f"No encontré '{arg}' en el Cerebro."
    lines = [f"Resultados para '{arg}' ({len(hits)}):"]
    for h in hits:
        lines.append(f"\n  📄 {h['titulo']}  [{h['archivo']}]")
        lines.append(f"  {h['extracto'][:250]}")
    return "\n".join(lines)


def cmd_reenroll(_: str) -> Optional[str]:
    """Registro guiado de voz del usuario (3 rondas, ~2 min)."""
    try:
        from nova.tools.nova_voice_stt import NovaVoiceSTT
    except ImportError:
        return "Módulo de voz no disponible (falta librosa/soundfile)."
    print("\n  Para salir antes de tiempo presioná Ctrl+C en cualquier momento.\n")
    try:
        stt = NovaVoiceSTT()
        stt.enroll_speaker(rounds=3)
        return "Perfil de voz guardado. La verificación de hablante está activa."
    except KeyboardInterrupt:
        return "Re-enroll cancelado."
    except Exception as e:
        return f"Error durante el registro: {e}"


def cmd_modelo(arg: str) -> Optional[str]:
    """Cambia el modelo/proveedor activo. Sin args muestra los disponibles."""
    _lazy_init()
    if not _router or _router is False:
        return "Router no disponible."

    if not arg.strip():
        # Mostrar proveedores y modelos disponibles
        providers = getattr(_router, "provider_order", [])
        lines = ["Proveedores disponibles:\n"]
        _MODELOS = {
            "ollama":     "Modelos locales — privado, gratuito  (requiere: ollama serve)",
            "groq":       "Llama 3.3 70B — ultra rápido, gratuito  (requiere: GROQ_API_KEY)",
            "openrouter": "100+ modelos — Gemma, Mistral, etc.  (requiere: OPENROUTER_API_KEY)",
            "anthropic":  "Claude Haiku/Sonnet/Opus — máxima calidad  (requiere: ANTHROPIC_API_KEY)",
            "openai":     "GPT-4o / GPT-4o-mini  (requiere: OPENAI_API_KEY)",
        }
        for p in _MODELOS:
            marca = "→" if providers and p == providers[0] else " "
            lines.append(f"  {marca} {p:<12} {_MODELOS[p]}")
        lines.append(f"\nOrden actual: {' → '.join(providers) if providers else 'N/A'}")
        lines.append("Uso: /modelo <proveedor>  para poner ese proveedor primero")
        lines.append("     /modelo claude        atajo para Anthropic primero")
        lines.append("     /modelo local         atajo para solo Ollama")
        return "\n".join(lines)

    # Atajos
    _ATAJOS = {
        "claude":    ["anthropic", "groq", "openrouter", "ollama"],
        "gpt":       ["openai", "groq", "openrouter", "ollama"],
        "local":     ["ollama"],
        "gratis":    ["ollama", "groq", "openrouter"],
        "rapido":    ["groq", "ollama", "openrouter"],
        "mejor":     ["anthropic", "openai", "groq", "openrouter", "ollama"],
    }
    nombre = arg.strip().lower()
    nuevo_orden = _ATAJOS.get(nombre)
    if not nuevo_orden:
        # Si es un proveedor directo, ponerlo primero
        todos = getattr(_router, "provider_order", [])
        if nombre in todos:
            nuevo_orden = [nombre] + [p for p in todos if p != nombre]
        else:
            return f"Proveedor desconocido: '{nombre}'. Usá /modelo para ver opciones."

    if hasattr(_router, "provider_order"):
        _router.provider_order = nuevo_orden
        return f"Modelo cambiado. Orden: {' → '.join(nuevo_orden)}"
    return "No se pudo cambiar el orden de proveedores en este router."


def cmd_telegram(_: str) -> Optional[str]:
    """Muestra estado del servidor Telegram Receive."""
    try:
        from nova.connectors.nova_telegram_server import status
        return status()
    except ImportError:
        return "Módulo nova_telegram_server no disponible."


# Comandos principales en español + aliases en inglés
SLASH_COMMANDS: dict[str, tuple[Callable[[str], Optional[str]], str]] = {
    # ── Principales (español) ──────────────────────────────────────────────────
    "/ayuda":     (cmd_help,        "Lista de comandos"),
    "/salir":     (cmd_exit,        "Cerrar Nova"),
    "/limpiar":   (cmd_clear,       "Limpiar pantalla y contexto"),
    "/skills":    (cmd_skills_list, "Listar skills disponibles"),
    "/skill":     (cmd_skill,       "Ejecutar skill: /skill qué hora es"),
    "/agente":    (cmd_agente,      "Agentes: briefing · búsqueda · código · orquestador"),
    "/recordar":  (cmd_recordar,    "Buscar en memoria neuronal"),
    "/guardar":   (cmd_guardar,     "Guardar hecho en memoria"),
    "/olvidar":   (cmd_olvidar,     "Borrar hecho de memoria"),
    "/estado":    (cmd_estado,      "Estado del sistema"),
    "/doctor":    (cmd_doctor,      "Diagnóstico del sistema  (--fix para reparar)"),
    "/modelo":    (cmd_modelo,      "Ver o cambiar proveedor: /modelo claude | local | gratis"),
    "/tarea":     (cmd_tarea,       "Orquestar tarea compleja con herramientas reales"),
    "/stats":     (cmd_stats,       "Estadísticas de uso de modelos LLM"),
    "/reiniciar": (cmd_reiniciar,   "Recargar módulos sin cerrar (aplica cambios de código)"),
    "/restart":   (cmd_reiniciar,   "→ /reiniciar"),
    "/cerebro":   (cmd_cerebro,     "Buscar/listar en el vault Cerebro: /cerebro MAIRA"),
    "/reenroll":  (cmd_reenroll,    "Registrar perfil de voz (3 rondas guiadas, ~2 min)"),
    "/telegram":  (cmd_telegram,    "Estado del servidor Telegram Receive"),
    # ── Aliases inglés (para compatibilidad) ──────────────────────────────────
    "/help":      (cmd_help,        "→ /ayuda"),
    "/exit":      (cmd_exit,        "→ /salir"),
    "/quit":      (cmd_exit,        "→ /salir"),
    "/clear":     (cmd_clear,       "→ /limpiar"),
    "/agent":     (cmd_agente,      "→ /agente"),
    "/recall":    (cmd_recordar,    "→ /recordar"),
    "/remember":  (cmd_guardar,     "→ /guardar"),
    "/forget":    (cmd_olvidar,     "→ /olvidar"),
    "/status":    (cmd_estado,      "→ /estado"),
}


# ─── Estado de sesión ────────────────────────────────────────────────────────

_session_state: dict = {"history": [], "id": "repl"}


def _dispatch_slash(line: str) -> Optional[str]:
    """Si la línea empieza con `/`, la dispatcha al handler. Devuelve None si no es slash."""
    if not line.startswith("/"):
        return None
    parts = line.strip().split(maxsplit=1)
    cmd = parts[0]
    arg = parts[1] if len(parts) > 1 else ""
    entry = SLASH_COMMANDS.get(cmd)
    if not entry:
        return f"Comando desconocido: {cmd}. Probá /help."
    handler, _ = entry
    try:
        return handler(arg)
    except SystemExit:
        raise
    except Exception as e:
        return f"Error ejecutando {cmd}: {e}"


def _route_to_llm(text: str) -> str:
    """Envía el texto al LLM con contexto de skills y memoria."""
    _lazy_init()

    history = _session_state["history"]

    # 1. Probar primero las skills locales (matcheo regex — sin latencia de red)
    if _skills:
        skill_resp = _skills.dispatch(text)
        if skill_resp:
            history.append({"role": "user", "content": text})
            history.append({"role": "assistant", "content": skill_resp})
            return skill_resp

    # 2. Usar daemon si está disponible (evita conflicto Qdrant/Router con HUD)
    if _daemon_client is not None:
        try:
            session_id = _session_state.get("id", "repl")
            chunks: list[str] = []
            print()
            for chunk in _daemon_client.chat_stream(text, session=session_id):
                print(chunk, end="", flush=True)
                chunks.append(chunk)
            print()
            response = "".join(chunks)
            history.append({"role": "user", "content": text})
            history.append({"role": "assistant", "content": response})
            return ""  # ya impreso token a token
        except Exception as e:
            log.warning("[REPL] Daemon falló, usando router local: %s", e)
            # Fall through to direct router below

    # 2b. Si regex falló, dejar que el LLM elija la tool (llm_dispatch)
    if _skills and _router:
        try:
            last_assistant = next(
                (m["content"] for m in reversed(history) if m.get("role") == "assistant"), ""
            )
            text_ctx = text
            if last_assistant and any(
                w in text.lower()
                for w in ["eso", "esto", "lo anterior", "lo que viste", "lo describiste",
                           "lo que describiste", "lo que mencionaste", "esa"]
            ):
                text_ctx = f"{text}\n[Contexto previo: {last_assistant[:400]}]"
            tool_resp = _skills.llm_dispatch(text_ctx)
            if tool_resp:
                history.append({"role": "user", "content": text})
                history.append({"role": "assistant", "content": tool_resp})
                return tool_resp
        except Exception:
            pass

    # 3. Fallback al router LLM local (conversacional)
    if not _router or _router is False:
        return "Router LLM no disponible. Probá las skills con /skills."

    history.append({"role": "user", "content": text})

    # Inyectar contexto de memoria neuronal si hay
    extra_ctx = ""
    if _neuro and _neuro is not False:
        try:
            extra_ctx = _neuro.search_context(text) or ""
        except Exception:
            pass

    # Inyectar notas relevantes del Cerebro (búsqueda file-based)
    cerebro_ctx = ""
    try:
        from nova.connectors.nova_cerebro import cerebro_buscar
        # Solo busca si el texto tiene suficiente sustancia (> 4 palabras)
        if len(text.split()) > 4:
            hits = cerebro_buscar(text, max_resultados=2)
            if hits:
                lines = ["[Cerebro — notas relevantes:]"]
                for h in hits:
                    lines.append(f"• {h['titulo']}: {h['extracto'][:300]}")
                cerebro_ctx = "\n".join(lines)
    except Exception:
        pass

    # System prompt con contexto del entorno (CWD, repo, rama)
    sys_parts = [_system_context_block()]
    if extra_ctx:
        sys_parts.append(extra_ctx)
    if cerebro_ctx:
        sys_parts.append(cerebro_ctx)
    system_msg = {"role": "system", "content": "\n\n".join(p for p in sys_parts if p)}

    messages = [system_msg] + list(history)

    try:
        # Streaming: imprime tokens a medida que llegan
        response_chunks: list[str] = []
        print()
        for chunk in _router.route_stream(messages):
            print(chunk, end="", flush=True)
            response_chunks.append(chunk)
        print()
        response = "".join(response_chunks)
        provider = getattr(_router, "_last_provider", "?")
        history.append({"role": "assistant", "content": response})

        # Guardar interacción en memoria neuronal
        if _neuro and _neuro is not False:
            try:
                _neuro.add_interaction(text, response)
            except Exception:
                pass

        print(f"  [via {provider}]")
        return ""  # ya impreso token a token
    except Exception as e:
        return f"Error LLM: {e}"


# ─── Contexto del entorno ────────────────────────────────────────────────────

def _get_env_context() -> dict:
    """Recopila CWD, git branch y nombre del repo para el sistema."""
    ctx: dict = {"cwd": os.getcwd()}
    try:
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            stderr=subprocess.DEVNULL, text=True
        ).strip()
        repo_name = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            stderr=subprocess.DEVNULL, text=True
        ).strip()
        ctx["branch"] = branch
        ctx["repo"] = os.path.basename(repo_name)
        ctx["repo_root"] = repo_name
    except Exception:
        ctx["branch"] = None
        ctx["repo"] = None
        ctx["repo_root"] = None
    return ctx


_ENV_CTX: dict = {}   # se llena la primera vez que corre


def _system_context_block() -> str:
    """Devuelve el bloque de contexto del entorno para inyectar en el LLM."""
    ctx = _ENV_CTX
    lines = [
        f"Directorio de trabajo actual: {ctx.get('cwd', os.getcwd())}",
    ]
    if ctx.get("repo"):
        lines.append(f"Repositorio git: {ctx['repo']} (rama: {ctx.get('branch', '?')})")
        lines.append(f"Raíz del repo: {ctx.get('repo_root', '')}")
    lines.append(f"Fecha/hora: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")
    return "\n".join(lines)


# ─── Loop principal ──────────────────────────────────────────────────────────

_ANSI = {
    "reset":  "\033[0m",
    "bold":   "\033[1m",
    "cyan":   "\033[96m",
    "blue":   "\033[94m",
    "yellow": "\033[93m",
    "green":  "\033[92m",
    "dim":    "\033[2m",
    "white":  "\033[97m",
}


def _print_banner(ctx: dict) -> None:
    c = _ANSI
    branch = ctx.get("branch")
    repo   = ctx.get("repo")
    now    = datetime.datetime.now().strftime("%Y-%m-%d  %H:%M")
    cwd    = ctx.get("cwd", os.getcwd())

    # Detect terminal width
    try:
        cols = os.get_terminal_size().columns
    except Exception:
        cols = 80
    bar = "─" * min(cols, 72)

    print(f"\n{c['cyan']}{c['bold']}")
    print(r"  ███╗   ██╗ ██████╗ ██╗   ██╗ █████╗")
    print(r"  ████╗  ██║██╔═══██╗██║   ██║██╔══██╗")
    print(r"  ██╔██╗ ██║██║   ██║██║   ██║███████║")
    print(r"  ██║╚██╗██║██║   ██║╚██╗ ██╔╝██╔══██║")
    print(r"  ██║ ╚████║╚██████╔╝ ╚████╔╝ ██║  ██║")
    print(r"  ╚═╝  ╚═══╝ ╚═════╝   ╚═══╝  ╚═╝  ╚═╝")
    print(f"{c['reset']}")
    print(f"{c['dim']}{bar}{c['reset']}")
    print(f"  {c['white']}{c['bold']}Nova Personal AI{c['reset']}  {c['dim']}v3.1{c['reset']}  "
          f"{c['dim']}·{c['reset']}  {c['dim']}{now}{c['reset']}")

    if repo and branch:
        print(f"  {c['blue']}󰊢{c['reset']} {c['yellow']}{repo}{c['reset']}{c['dim']}  ·  rama: {c['reset']}"
              f"{c['green']}{branch}{c['reset']}")
    print(f"  {c['dim']}dir: {cwd}{c['reset']}")
    print(f"{c['dim']}{bar}{c['reset']}")
    print(f"  {c['dim']}Tab: autocomplete  ·  /ayuda: comandos  ·  /salir: cerrar{c['reset']}\n")


def run() -> int:
    """Bucle principal del REPL. Retorna exit code."""
    global _ENV_CTX
    _ENV_CTX = _get_env_context()
    _print_banner(_ENV_CTX)

    # Arrancar servidor Telegram Receive en background
    _lazy_init()
    try:
        from nova.connectors.nova_telegram_server import start as _tg_start
        _tg_start(process_fn=_route_to_llm)
    except Exception:
        pass

    read = _make_reader()

    while True:
        try:
            line = read("nova> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n👋 Hasta luego, Señor.")
            return 0

        if not line:
            continue

        # Slash command o LLM
        slash = _dispatch_slash(line)
        if slash is not None:
            if slash:
                print(slash)
            continue

        response = _route_to_llm(line)
        if response:  # empty → ya fue impreso token a token (streaming)
            print(response)


# Alias so `from nova.cli.repl import main` also works
main = run

if __name__ == "__main__":
    sys.exit(run())
