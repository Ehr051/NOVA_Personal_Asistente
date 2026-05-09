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
    _session_save()
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
            # Modo agente autónomo: planifica y ejecuta con tool calling nativo
            goal = arg.strip()
            if not goal:
                return (
                    "Uso: /agente <objetivo>\n"
                    "  briefing          Briefing del día\n"
                    "  búsqueda <tema>   Investigación profunda\n"
                    "  código <tarea>    Asistente de código\n"
                    "  orquestador <obj> Razonamiento multi-turno\n"
                    "  <cualquier texto> Agente autónomo con tool calling"
                )
            from nova.tools.nova_skills import skill_agente
            return skill_agente(goal)
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
    fixes_applied: list[str] = []
    has_llm = False

    # ── LLM providers (los que Nova usa por defecto) ───────────────────────
    _ENV_KEYS = {
        "Groq":        ("GROQ_API_KEY",        "console.groq.com — 14.400 req/día gratis"),
        "Cerebras":    ("CEREBRAS_API_KEY",     "cloud.cerebras.ai — 30 req/min gratis"),
        "Mistral":     ("MISTRAL_API_KEY",      "console.mistral.ai — tier gratuito"),
        "OpenRouter":  ("OPENROUTER_API_KEY",   "openrouter.ai — modelos gratuitos"),
    }
    for provider, (env_var, hint) in _ENV_KEYS.items():
        val = os.getenv(env_var, "")
        if val and len(val) > 8:
            lines.append(f"  {ok} {provider:<12} — key configurada")
            has_llm = True
        else:
            lines.append(f"  {warn} {provider:<12} — no configurado  ({env_var} en .env)")

    # Ollama (local, no key)
    _ollama_ok = False
    try:
        import urllib.request
        urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=2)
        lines.append(f"  {ok} Ollama       — conectado")
        has_llm = True
        _ollama_ok = True
    except Exception:
        lines.append(f"  {warn} Ollama       — no responde  (iniciá: ollama serve)")

    if not has_llm:
        lines.append(f"\n  {err} SIN PROVEEDOR LLM — Nova no puede responder. Configurá al menos una key.")

    # ── .env ──────────────────────────────────────────────────────────────
    from pathlib import Path
    _env_path = Path(__file__).resolve().parents[3] / ".env"
    if _env_path.exists():
        lines.append(f"  {ok} .env         — encontrado ({_env_path})")
    else:
        lines.append(f"  {warn} .env         — no encontrado  (crea {_env_path} con tus keys)")
        if fix_mode:
            _stub = "# Nova — API Keys\n# Descomentá y completá las que tengas:\n"
            _stub += "# GROQ_API_KEY=gsk_...\n# CEREBRAS_API_KEY=...\n# MISTRAL_API_KEY=...\n# OPENROUTER_API_KEY=...\n"
            try:
                _env_path.write_text(_stub, encoding="utf-8")
                fixes_applied.append(f"  ✓ Creado .env stub en {_env_path}")
            except Exception as exc:
                fixes_applied.append(f"  ✗ No se pudo crear .env: {exc}")

    # ── Daemon ────────────────────────────────────────────────────────────
    try:
        from nova.core.nova_client import get_client
        _dc = get_client(auto_start=False)
        if _dc.ping():
            lines.append(f"  {ok} Daemon       — corriendo en :{_dc.port}")
        else:
            lines.append(f"  {warn} Daemon       — no corre  (arrancá: python -m nova.core.nova_daemon)")
            if fix_mode:
                _dc2 = get_client(auto_start=True)
                if _dc2.ensure_daemon(wait=4.0):
                    fixes_applied.append("  ✓ Daemon arrancado automáticamente")
                else:
                    fixes_applied.append("  ✗ No se pudo arrancar el daemon")
    except Exception as exc:
        lines.append(f"  {warn} Daemon       — error al verificar: {exc}")

    # ── Memoria neuronal ──────────────────────────────────────────────────
    if _neuro and _neuro is not False:
        lines.append(f"  {ok} Memoria neuronal — activa")
    else:
        lines.append(f"  {err} Memoria neuronal — no disponible")
        if fix_mode and not (_neuro and _neuro is not False):
            try:
                from nova.tools.nova_neuro_memory import NovaNeuroMemory
                globals()["_neuro"] = NovaNeuroMemory()
                fixes_applied.append("  ✓ Memoria neuronal reinicializada")
            except Exception as exc:
                fixes_applied.append(f"  ✗ Memoria no disponible: {exc}")

    # ── Integraciones opcionales ──────────────────────────────────────────
    try:
        import socket as _sock
        with _sock.create_connection(("127.0.0.1", 9876), timeout=1):
            lines.append(f"  {ok} Blender MCP  — conectado en :9876")
    except Exception:
        lines.append(f"  {warn} Blender MCP  — no conectado  (Blender → addon MCP → Start Server)")

    try:
        import urllib.request as _ureq
        _ureq.urlopen("http://localhost:5678/healthz", timeout=2)
        lines.append(f"  {ok} n8n          — operativo en :5678")
    except Exception:
        lines.append(f"  {warn} n8n          — no responde  (opcional)")

    # ── Router (infra interna) ────────────────────────────────────────────
    if _router and _router is not False:
        providers = getattr(_router, "provider_order", [])
        lines.append(f"  {ok} Router LLM  ({', '.join(providers) if providers else 'activo'})")
    else:
        lines.append(f"  {err} Router LLM  — no disponible")
        if fix_mode:
            globals()["_router"] = None
            _lazy_init()
            if _router and _router is not False:
                fixes_applied.append("  ✓ Router reinicializado")

    # ── Resumen fix ───────────────────────────────────────────────────────
    if fix_mode and fixes_applied:
        lines.append("\n[--fix] Acciones aplicadas:")
        lines.extend(fixes_applied)
    elif fix_mode:
        lines.append("\n[--fix] Sin acciones automáticas posibles. Revisá los ✗ y ⚠ manualmente.")

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


_MODO_ACTUAL: str = "normal"
_MODOS_DIR = os.path.expanduser("~/.nova/modos")

# Modos built-in universales (sin perfiles personales hardcodeados)
_MODOS_BUILTIN: dict[str, dict] = {
    "normal": {
        "desc":  "Modo estándar — balanceado",
        "temp":  0.7,
        "tier":  None,
        "extra": "",
    },
    "codigo": {
        "desc":  "Modo código — preciso, bajo temperatura, modelos fuertes",
        "temp":  0.1,
        "tier":  2,
        "extra": "Sos un experto en programación. Priorizá código correcto, eficiente y seguro. Sin relleno.",
    },
    "creativo": {
        "desc":  "Modo creativo — alta temperatura, respuestas imaginativas",
        "temp":  1.1,
        "tier":  None,
        "extra": "Sos un asistente creativo. Explorá ideas originales, metáforas y perspectivas inesperadas.",
    },
    "rapido": {
        "desc":  "Modo rápido — modelos pequeños, mínima latencia",
        "temp":  0.5,
        "tier":  0,
        "extra": "Respuestas muy concisas — una oración o menos si es posible.",
    },
}

# _MODOS es la vista combinada (built-in + custom cargados al inicio)
_MODOS: dict[str, dict] = dict(_MODOS_BUILTIN)


def _load_custom_modos() -> None:
    """Carga perfiles JSON de ~/.nova/modos/ y los fusiona con _MODOS."""
    import json as _j
    from pathlib import Path
    modos_dir = Path(_MODOS_DIR)
    if not modos_dir.exists():
        return
    for f in modos_dir.glob("*.json"):
        try:
            data = _j.loads(f.read_text(encoding="utf-8"))
            name = f.stem.lower()
            _MODOS[name] = {
                "desc":  data.get("desc", data.get("descripcion", f"Modo personalizado: {name}")),
                "temp":  data.get("temp", data.get("temperatura", 0.7)),
                "tier":  data.get("tier", None),
                "extra": data.get("extra", data.get("system_extra", "")),
                "_custom": True,
            }
        except Exception:
            pass


_load_custom_modos()

# ─── WIZARD STATE ──────────────────────────────────────────────────────────────
# Holds active interactive wizard session.  Empty dict = no wizard running.
# Supported wizard types: "modo_nuevo"
_WIZARD_STATE: dict = {}


def _wizard_handle(line: str) -> str:
    """
    Process one line of input for the active wizard.
    Returns text to print.  Clears _WIZARD_STATE when wizard finishes.
    """
    import json as _j
    from pathlib import Path
    global _WIZARD_STATE

    wtype = _WIZARD_STATE.get("type")
    step  = _WIZARD_STATE.get("step", 0)
    data  = _WIZARD_STATE.setdefault("data", {})

    c = _ANSI

    if wtype == "modo_nuevo":
        name = _WIZARD_STATE["name"]

        if step == 0:
            # Received: description
            data["desc"] = line.strip() or f"Modo personalizado {name}"
            _WIZARD_STATE["step"] = 1
            return (
                f"{c['dim']}  Temperatura (0.0 creativo → 1.0 determinista, Enter para 0.7):{c['reset']}"
            )

        if step == 1:
            # Received: temperature
            raw = line.strip()
            try:
                temp = float(raw) if raw else 0.7
                temp = max(0.0, min(1.0, temp))
            except ValueError:
                temp = 0.7
            data["temp"] = temp
            _WIZARD_STATE["step"] = 2
            return (
                f"{c['dim']}  Instrucciones de sistema (Enter para dejar vacío):{c['reset']}"
            )

        if step == 2:
            # Received: system instructions
            data["extra"] = line.strip()
            _WIZARD_STATE["step"] = 3

        if step >= 2:
            # Build and save
            nuevo = {
                "desc":  data.get("desc", f"Modo {name}"),
                "temp":  data.get("temp", 0.7),
                "tier":  None,
                "extra": data.get("extra", ""),
            }
            modos_dir = Path(_MODOS_DIR)
            modos_dir.mkdir(parents=True, exist_ok=True)
            path = modos_dir / f"{name}.json"
            path.write_text(_j.dumps(nuevo, ensure_ascii=False, indent=2), encoding="utf-8")
            _MODOS[name] = {**nuevo, "_custom": True}
            _WIZARD_STATE.clear()
            return (
                f"\n  Modo '{name}' creado en {path}\n"
                f"  Activar con: /modo {name}\n"
                f"  Editá el JSON para ajustar en cualquier momento."
            )

    # Unknown wizard type — bail out
    _WIZARD_STATE.clear()
    return "Wizard cancelado."


def cmd_modo(arg: str) -> Optional[str]:
    """
    Cambia el modo de operación o gestiona modos personalizados.

    /modo                         — modo actual y lista
    /modo <nombre>                — cambiar al modo indicado
    /modo nuevo <nombre> [desc]   — crear modo personalizado (interactivo)
    /modo borrar <nombre>         — eliminar modo custom
    /modo exportar <nombre>       — mostrar JSON del modo para compartir
    """
    import json as _j
    from pathlib import Path
    global _MODO_ACTUAL

    parts = arg.strip().split(maxsplit=1)
    sub   = parts[0].lower() if parts else ""
    rest  = parts[1].strip() if len(parts) > 1 else ""

    # ── lista / vacío ────────────────────────────────────────────────────────
    if not sub or sub in ("lista", "list", "?"):
        lines = [f"Modo actual: {_MODO_ACTUAL}\n"]
        builtin_names = set(_MODOS_BUILTIN)
        custom = {k: v for k, v in _MODOS.items() if k not in builtin_names}
        lines.append("Modos built-in:")
        for k, v in _MODOS_BUILTIN.items():
            mark = " ◀" if k == _MODO_ACTUAL else ""
            lines.append(f"  {k:<14} — {v['desc']}{mark}")
        if custom:
            lines.append("\nModos personalizados (~/.nova/modos/):")
            for k, v in custom.items():
                mark = " ◀" if k == _MODO_ACTUAL else ""
                lines.append(f"  {k:<14} — {v['desc']}{mark}")
        lines.append("\nCrear modo: /modo nuevo <nombre>")
        return "\n".join(lines)

    # ── nuevo (wizard) ───────────────────────────────────────────────────────
    if sub == "nuevo":
        name = rest.split()[0].lower() if rest else ""
        if not name:
            return "Uso: /modo nuevo <nombre>"
        if name in _MODOS_BUILTIN:
            return f"'{name}' es un modo built-in y no se puede sobreescribir."

        # Start interactive wizard
        c = _ANSI
        _WIZARD_STATE.clear()
        _WIZARD_STATE.update({"type": "modo_nuevo", "name": name, "step": 0, "data": {}})
        return (
            f"Creando modo '{name}' — respondé las siguientes preguntas (Enter para defaults):\n"
            f"{c['dim']}  Descripción corta (ej: 'Respuestas técnicas concisas'):{c['reset']}"
        )

    # ── borrar ───────────────────────────────────────────────────────────────
    if sub in ("borrar", "delete", "eliminar"):
        name = rest.strip().lower()
        if not name:
            return "Uso: /modo borrar <nombre>"
        if name in _MODOS_BUILTIN:
            return f"'{name}' es un modo built-in y no se puede borrar."
        path = Path(_MODOS_DIR) / f"{name}.json"
        if not path.exists():
            return f"Modo '{name}' no encontrado en ~/.nova/modos/"
        path.unlink()
        _MODOS.pop(name, None)
        if _MODO_ACTUAL == name:
            _MODO_ACTUAL = "normal"
        return f"Modo '{name}' eliminado."

    # ── exportar ─────────────────────────────────────────────────────────────
    if sub in ("exportar", "export"):
        name = rest.strip().lower()
        if not name:
            name = _MODO_ACTUAL
        if name not in _MODOS:
            return f"Modo '{name}' no encontrado."
        cfg = {k: v for k, v in _MODOS[name].items() if not k.startswith("_")}
        return f"# Modo '{name}' — guardá esto en ~/.nova/modos/{name}.json\n{_j.dumps(cfg, ensure_ascii=False, indent=2)}"

    # ── cambiar modo ─────────────────────────────────────────────────────────
    modo = sub  # sub ya es el nombre en minúsculas
    if modo not in _MODOS:
        # Intentar recargar custom por si se agregó desde afuera
        _load_custom_modos()
    if modo not in _MODOS:
        custom_names = [k for k in _MODOS if k not in _MODOS_BUILTIN]
        hint = f"  Custom: {', '.join(custom_names)}" if custom_names else ""
        return (
            f"Modo '{modo}' desconocido.\n"
            f"Built-in: {', '.join(_MODOS_BUILTIN)}\n{hint}\n"
            f"Crear uno: /modo nuevo {modo}"
        )
    _MODO_ACTUAL = modo
    cfg = _MODOS[modo]
    if _router and _router is not False and cfg["temp"] is not None:
        _router._default_temperature = cfg["temp"]
    tag = " [custom]" if cfg.get("_custom") else ""
    return f"Modo cambiado a '{modo}'{tag} — {cfg['desc']}"


def cmd_rutina(arg: str) -> Optional[str]:
    """
    Macros de comandos guardados.
    /rutina definir <nombre> <cmd1> ; <cmd2> ; ...   — crear/actualizar rutina
    /rutina <nombre>                                  — ejecutar rutina
    /rutina lista                                     — listar rutinas
    /rutina borrar <nombre>                           — eliminar rutina
    """
    import json as _j
    from pathlib import Path

    _rutinas_file = Path(os.path.expanduser("~/.nova/rutinas.json"))

    def _load() -> dict:
        try:
            return _j.loads(_rutinas_file.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save(data: dict) -> None:
        _rutinas_file.parent.mkdir(parents=True, exist_ok=True)
        _rutinas_file.write_text(_j.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    parts  = arg.strip().split(maxsplit=1)
    sub    = parts[0].lower() if parts else ""
    rest   = parts[1] if len(parts) > 1 else ""

    if sub in ("lista", "list", "ls", ""):
        rutinas = _load()
        if not rutinas:
            return "No hay rutinas definidas. Definí una con: /rutina definir <nombre> <cmd1> ; <cmd2>"
        lines = ["Rutinas:\n"]
        for name, cmds in sorted(rutinas.items()):
            lines.append(f"  {name}: {' ; '.join(cmds)}")
        return "\n".join(lines)

    if sub in ("definir", "define", "set", "crear"):
        # /rutina definir mañana /estado ; /skills ; /cerebro MAIRA
        subparts = rest.split(maxsplit=1)
        if len(subparts) < 2:
            return "Uso: /rutina definir <nombre> <cmd1> ; <cmd2> ; ..."
        rname = subparts[0].lower()
        cmds  = [c.strip() for c in subparts[1].split(";") if c.strip()]
        if not cmds:
            return "No se encontraron comandos. Separalos con ';'."
        rutinas = _load()
        rutinas[rname] = cmds
        _save(rutinas)
        return f"Rutina '{rname}' guardada ({len(cmds)} paso(s)): {' → '.join(cmds)}"

    if sub in ("borrar", "delete", "rm", "eliminar"):
        rname = rest.strip().lower()
        rutinas = _load()
        if rname not in rutinas:
            return f"Rutina '{rname}' no encontrada."
        del rutinas[rname]
        _save(rutinas)
        return f"Rutina '{rname}' eliminada."

    # Ejecutar rutina por nombre
    rname   = sub
    rutinas = _load()
    if rname not in rutinas:
        return (f"Rutina '{rname}' no encontrada. "
                f"Rutinas disponibles: {', '.join(sorted(rutinas)) or 'ninguna'}")
    cmds = rutinas[rname]
    results: list[str] = []
    for cmd in cmds:
        out = _dispatch_slash(cmd) if cmd.startswith("/") else _route_to_llm(cmd)
        if out:
            results.append(f"[{cmd}]\n{out}")
    return "\n\n".join(results) if results else f"Rutina '{rname}' ejecutada ({len(cmds)} pasos)."


def cmd_comparar(arg: str) -> Optional[str]:
    """Envía la misma pregunta a múltiples proveedores y compara respuestas."""
    _lazy_init()
    if not _router or _router is False:
        return "Router no disponible."
    if not arg.strip():
        return "Uso: /comparar <pregunta>"

    import concurrent.futures
    import datetime as _dt

    providers = getattr(_router, "provider_order", [])[:4]  # máx 4
    if not providers:
        return "No hay proveedores disponibles."

    messages = [
        {"role": "system", "content": "Respondé de forma concisa y directa."},
        {"role": "user", "content": arg.strip()},
    ]

    def _query(provider: str) -> tuple[str, str, float]:
        t0 = _dt.datetime.now()
        try:
            # Usar un router temporal con provider_order restringido
            import copy as _copy
            r2 = _copy.copy(_router)
            r2.provider_order = [provider]
            chunks: list[str] = []
            for chunk in r2.route_stream(messages, max_tokens=300, temperature=0.7):
                chunks.append(chunk)
            elapsed = (_dt.datetime.now() - t0).total_seconds()
            return provider, "".join(chunks).strip(), elapsed
        except Exception as exc:
            return provider, f"[Error: {exc}]", 0.0

    print(f"\nComparando {len(providers)} proveedor(es)...\n")
    results: list[tuple[str, str, float]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(providers)) as ex:
        futures = {ex.submit(_query, p): p for p in providers}
        for fut in concurrent.futures.as_completed(futures):
            results.append(fut.result())

    results.sort(key=lambda x: x[2])  # ordenar por velocidad
    lines: list[str] = []
    for provider, resp, elapsed in results:
        lines.append(f"── {provider} ({elapsed:.1f}s) ──")
        lines.append(resp)
        lines.append("")
    return "\n".join(lines)


def cmd_nota(arg: str) -> Optional[str]:
    """Captura rápida al vault Cerebro. /nota <texto> o /nota @titulo texto"""
    from pathlib import Path
    import datetime as _dt

    text = arg.strip()
    if not text:
        return "Uso: /nota <texto>  o  /nota @titulo texto"

    # Parsear título opcional (@titulo al inicio)
    titulo = None
    if text.startswith("@"):
        parts = text.split(maxsplit=1)
        titulo = parts[0][1:] or None
        text   = parts[1] if len(parts) > 1 else text

    ts = _dt.datetime.now()
    if titulo is None:
        titulo = ts.strftime("nota_%Y%m%d_%H%M%S")

    # Destinos: Drops/ primero, luego Notas/
    drops_dir = Path.home() / "Cerebro" / "Drops"
    notas_dir = Path.home() / "Cerebro" / "Notas"

    target_dir = drops_dir if drops_dir.is_dir() else notas_dir
    if not target_dir.is_dir():
        target_dir.mkdir(parents=True, exist_ok=True)

    safe_title = "".join(c if c.isalnum() or c in " _-" else "_" for c in titulo).strip()
    fpath = target_dir / f"{safe_title}.md"

    # Si el archivo ya existe, agregar al final
    if fpath.exists():
        existing = fpath.read_text(encoding="utf-8")
        content = existing + f"\n\n---\n*{ts.strftime('%Y-%m-%d %H:%M')}*\n\n{text}\n"
    else:
        content = f"# {titulo}\n*{ts.strftime('%Y-%m-%d %H:%M')}*\n\n{text}\n"

    fpath.write_text(content, encoding="utf-8")
    return f"Nota guardada → {fpath}"


def cmd_exportar(arg: str) -> Optional[str]:
    """Exporta la sesión actual a un archivo Markdown o JSON."""
    history = _session_state.get("history", [])
    if not history:
        return "No hay conversación que exportar."

    from pathlib import Path
    import datetime as _dt

    fmt   = "json" if "json" in arg.lower() else "md"
    ts    = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = arg.strip() if (arg.strip() and not arg.strip().startswith("-")) else f"nova_sesion_{ts}.{fmt}"
    fpath = Path(fname) if Path(fname).is_absolute() else Path.cwd() / fname

    if fmt == "json":
        import json as _json
        fpath.write_text(_json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        lines = [f"# Sesión Nova — {_dt.datetime.now().strftime('%Y-%m-%d %H:%M')}\n"]
        for turn in history:
            role = "**Nova**" if turn["role"] == "assistant" else "**Tú**"
            lines.append(f"{role}: {turn['content']}\n")
        fpath.write_text("\n".join(lines), encoding="utf-8")

    return f"Sesión exportada → {fpath}"


def cmd_historial(arg: str) -> Optional[str]:
    """Muestra el historial de la sesión actual."""
    history = _session_state.get("history", [])
    if not history:
        return "No hay historial en esta sesión."
    limit = 10
    try:
        limit = int(arg.strip())
    except (ValueError, TypeError):
        pass
    lines = []
    for turn in history[-limit * 2:]:
        role  = "Tú  " if turn["role"] == "user" else "Nova"
        body  = turn["content"].replace("\n", " ")
        lines.append(f"  {role}: {body[:120]}{'…' if len(body) > 120 else ''}")
    return f"Historial (últimas {limit} rondas):\n" + "\n".join(lines)


def cmd_telegram(_: str) -> Optional[str]:
    """Muestra estado del servidor Telegram Receive."""
    try:
        from nova.connectors.nova_telegram_server import status
        return status()
    except ImportError:
        return "Módulo nova_telegram_server no disponible."


def cmd_webui(arg: str) -> Optional[str]:
    """Interfaz web Nova: /webui [start|stop|status]"""
    try:
        from nova.web import nova_web_server as _ws
    except ImportError as exc:
        return f"Módulo nova_web_server no disponible: {exc}"

    sub = arg.strip().lower()
    if sub in ("stop", "detener", "parar"):
        if _ws.is_running():
            _ws.stop()
            return "Servidor web detenido."
        return "El servidor web no está corriendo."

    if sub in ("status", "estado"):
        if _ws.is_running():
            return f"Servidor web activo en {_ws.url()}"
        return "Servidor web detenido."

    # start (default)
    if _ws.is_running():
        import webbrowser
        webbrowser.open(_ws.url())
        return f"Web UI ya activa en {_ws.url()} — abriendo navegador."
    _ws.start(open_browser=(sub != "noopen"))
    return f"Web UI iniciada en {_ws.url()} — abriendo navegador."


# Comandos principales en español + aliases en inglés
_CHECKPOINTS_DIR = os.path.expanduser("~/.nova/checkpoints")


def cmd_checkpoint(arg: str) -> Optional[str]:
    """
    Guarda o restaura sesiones con nombre.

    /checkpoint                  — listar checkpoints guardados
    /checkpoint guardar <nombre> — guardar sesión actual con ese nombre
    /checkpoint cargar <nombre>  — restaurar sesión guardada
    /checkpoint borrar <nombre>  — eliminar checkpoint
    """
    import json as _j
    from pathlib import Path

    ck_dir = Path(_CHECKPOINTS_DIR)
    ck_dir.mkdir(parents=True, exist_ok=True)

    parts = arg.strip().split(maxsplit=1)
    sub   = parts[0].lower() if parts else ""
    name  = parts[1].strip() if len(parts) > 1 else ""

    if sub in ("", "lista", "list", "ls"):
        files = sorted(ck_dir.glob("*.json"))
        if not files:
            return "No hay checkpoints guardados. Usá: /checkpoint guardar <nombre>"
        lines = ["Checkpoints guardados:\n"]
        for f in files:
            try:
                data = _j.loads(f.read_text(encoding="utf-8"))
                n_turns = len(data.get("history", [])) // 2
                lines.append(f"  {f.stem:<20} {n_turns} turnos")
            except Exception:
                lines.append(f"  {f.stem}")
        return "\n".join(lines)

    if sub in ("guardar", "save", "crear"):
        if not name:
            return "Uso: /checkpoint guardar <nombre>"
        hist = _session_state.get("history", [])
        if not hist:
            return "No hay historial para guardar."
        data = {"id": name, "history": hist}
        path = ck_dir / f"{name}.json"
        path.write_text(_j.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return f"Sesión guardada como '{name}' ({len(hist)//2} turnos)."

    if sub in ("cargar", "load", "restaurar"):
        if not name:
            return "Uso: /checkpoint cargar <nombre>"
        path = ck_dir / f"{name}.json"
        if not path.exists():
            available = [f.stem for f in ck_dir.glob("*.json")]
            hint = f" Disponibles: {', '.join(available)}" if available else ""
            return f"Checkpoint '{name}' no encontrado.{hint}"
        try:
            data = _j.loads(path.read_text(encoding="utf-8"))
            hist = data.get("history", [])
            if not hist:
                return f"Checkpoint '{name}' está vacío."
            _session_state["history"] = hist
            _session_state["id"] = name
            return f"Sesión '{name}' restaurada ({len(hist)//2} turnos)."
        except Exception as e:
            return f"Error al cargar '{name}': {e}"

    if sub in ("borrar", "delete", "eliminar"):
        if not name:
            return "Uso: /checkpoint borrar <nombre>"
        path = ck_dir / f"{name}.json"
        if not path.exists():
            return f"Checkpoint '{name}' no encontrado."
        path.unlink()
        return f"Checkpoint '{name}' eliminado."

    return (
        f"Subcomando '{sub}' desconocido.\n"
        "Uso: /checkpoint [lista|guardar <nombre>|cargar <nombre>|borrar <nombre>]"
    )


# ─── PERFIL DE USUARIO ────────────────────────────────────────────────────────

def cmd_perfil(arg: str) -> Optional[str]:
    """
    Ver y editar el perfil de usuario de Nova.

    /perfil                           — ver perfil actual
    /perfil tratamiento <Señor|...>   — cambiar cómo Nova te llama
    /perfil nombre <nombre>           — guardar tu nombre
    /perfil notas <texto>             — agregar contexto libre
    /perfil notas                     — borrar notas
    """
    from nova.core.nova_user_profile import UserProfile
    profile = UserProfile.load_or_default()

    parts = arg.strip().split(maxsplit=1)
    sub = parts[0].lower() if parts else ""
    val = parts[1].strip() if len(parts) > 1 else ""

    if not sub:
        c = _ANSI
        lines = [f"Perfil de usuario ({profile.id}):"]
        lines.append(f"  Tratamiento : {profile.address}")
        if profile.name:
            lines.append(f"  Nombre      : {profile.name}")
        if profile.notes:
            lines.append(f"  Notas       : {profile.notes}")
        lines.append(f"  Voz enrollada: {'Sí' if profile.voice_enrolled else 'No'}")
        lines.append(f"\n{c['dim']}Cambiar: /perfil tratamiento Señora  |  /perfil notas texto libre{c['reset']}")
        return "\n".join(lines)

    if sub in ("tratamiento", "address", "llamarme"):
        if not val:
            return "Uso: /perfil tratamiento <Señor|Señora|nombre>"
        profile.address = val
        profile.save()
        _apply_profile_to_router(profile)
        return f"Ahora Nova te llamará '{val}'."

    if sub in ("nombre", "name"):
        profile.name = val
        profile.save()
        _apply_profile_to_router(profile)
        return f"Nombre actualizado a '{val}'." if val else "Nombre borrado."

    if sub in ("notas", "notes", "contexto"):
        profile.notes = val
        profile.save()
        _apply_profile_to_router(profile)
        return "Notas actualizadas." if val else "Notas borradas."

    return "Uso: /perfil | /perfil tratamiento <texto> | /perfil nombre <texto> | /perfil notas <texto>"


def _apply_profile_to_router(profile: object) -> None:
    """Actualiza el system prompt del router activo con el perfil dado."""
    global _router
    if _router and _router is not False:
        try:
            from nova.core.nova_router import _build_system_prompt
            _router.system_prompt = _build_system_prompt()
        except Exception:
            pass


def _run_onboarding(read_fn) -> None:
    """
    Wizard de bienvenida para la primera vez que se usa Nova.
    Hace 2 preguntas y guarda ~/.nova/users/default/profile.json.
    """
    from nova.core.nova_user_profile import UserProfile
    c = _ANSI

    print(f"\n{c['bold']}  Hola, soy Nova, tu asistente personal.{c['reset']}")
    print(f"  Solo necesito saber una cosa antes de empezar.\n")

    # Pregunta 1 — tratamiento
    print(f"  ¿Cómo preferís que me dirija a vos?")
    print(f"  {c['dim']}Opciones: Señor / Señora / tu nombre / o cualquier otra forma (Enter → Señor){c['reset']}")
    raw = read_fn("  → ").strip()

    if not raw:
        address = "Señor"
    elif raw.lower() in ("señor", "senor", "sr", "sr."):
        address = "Señor"
    elif raw.lower() in ("señora", "senora", "sra", "sra."):
        address = "Señora"
    else:
        address = raw

    # Pregunta 2 — contexto opcional
    print(f"\n  ¿Hay algo que deba saber sobre vos para ayudarte mejor?")
    print(f"  {c['dim']}Ej: 'Soy desarrollador Python' — Enter para saltar{c['reset']}")
    notes = read_fn("  → ").strip()

    profile = UserProfile(address=address, notes=notes)
    profile.save()

    print(f"\n  Perfecto, {address}. Podés cambiar esto en cualquier momento con /perfil")
    print()


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
    "/webui":     (cmd_webui,       "Interfaz web: /webui [start|stop|status]"),
    "/nota":      (cmd_nota,        "Captura rápida al Cerebro: /nota [@titulo] texto"),
    "/comparar":  (cmd_comparar,    "Compara respuestas de múltiples LLMs: /comparar <pregunta>"),
    "/exportar":  (cmd_exportar,    "Exportar sesión: /exportar [archivo.md|archivo.json]"),
    "/historial": (cmd_historial,   "Ver historial de la sesión: /historial [N turnos]"),
    "/rutina":    (cmd_rutina,      "Macros: /rutina definir <nombre> <cmd> ; <cmd>  ·  /rutina <nombre>"),
    "/modo":       (cmd_modo,        "Modos: /modo <nombre> · /modo nuevo <nombre> · /modo borrar <nombre>"),
    "/mode":       (cmd_modo,        "→ /modo"),
    "/checkpoint": (cmd_checkpoint,  "Sesiones con nombre: /checkpoint [guardar|cargar|borrar|lista] <nombre>"),
    "/ckpt":       (cmd_checkpoint,  "→ /checkpoint"),
    "/perfil":     (cmd_perfil,      "Perfil: /perfil · /perfil tratamiento Señora · /perfil notas <texto>"),
    "/profile":    (cmd_perfil,      "→ /perfil"),
    "/export":    (cmd_exportar,    "→ /exportar"),
    "/history":   (cmd_historial,   "→ /historial"),
    "/routine":   (cmd_rutina,      "→ /rutina"),
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


# ─── Estado de sesión + persistencia ─────────────────────────────────────────

_session_state: dict = {"history": [], "id": "repl"}

_SESSION_FILE = os.path.expanduser("~/.nova/session_last.json")
_SESSION_AUTOSAVE_EVERY = 3   # guardar cada N turnos (user+assistant = 1 turno)


def _session_save() -> None:
    """Guarda el historial actual en disco (silencioso si falla)."""
    try:
        import json as _j
        from pathlib import Path
        Path(_SESSION_FILE).parent.mkdir(parents=True, exist_ok=True)
        data = {
            "id":      _session_state.get("id", "repl"),
            "history": _session_state.get("history", []),
        }
        Path(_SESSION_FILE).write_text(_j.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def _session_load() -> bool:
    """Carga la última sesión desde disco. Retorna True si se restauró algo."""
    try:
        import json as _j
        from pathlib import Path
        text = Path(_SESSION_FILE).read_text(encoding="utf-8")
        data = _j.loads(text)
        hist = data.get("history", [])
        if hist:
            _session_state["history"] = hist
            _session_state["id"] = data.get("id", "repl")
            return True
    except Exception:
        pass
    return False


def _expand_at_files(text: str) -> tuple[str, list[str]]:
    """
    Expande referencias @archivo en el texto.
    Retorna (texto_expandido, lista_de_bloques_de_contexto).

    Ejemplos:
      "revisá @src/nova/router.py"
      "compará @package.json y @requirements.txt"
      "@Dockerfile explica cada línea"
    """
    import re
    from pathlib import Path

    at_pattern = re.compile(r"@([\w./\-]+[\w./\-])")
    matches = at_pattern.findall(text)
    if not matches:
        return text, []

    file_blocks: list[str] = []
    cwd = Path(os.getcwd())

    for ref in matches:
        # Buscar relativo a CWD, luego al directorio del proyecto Nova
        candidates = [
            cwd / ref,
            Path(__file__).resolve().parents[3] / ref,
        ]
        found: Optional[Path] = None
        for candidate in candidates:
            if candidate.is_file():
                found = candidate
                break
        if found is None:
            continue
        try:
            content = found.read_text(encoding="utf-8", errors="replace")
            # Truncar archivos muy largos (max 8000 chars ~ 2000 tokens)
            if len(content) > 8000:
                content = content[:8000] + f"\n\n[… truncado en 8000 chars de {len(content)} total]"
            lang = found.suffix.lstrip(".") or "text"
            file_blocks.append(
                f"### Archivo: {found.name} ({found})\n```{lang}\n{content}\n```"
            )
        except Exception:
            continue

    if not file_blocks:
        return text, []

    return text, file_blocks


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

    # Expandir @archivo antes de todo
    text, _at_file_blocks = _expand_at_files(text)
    if _at_file_blocks:
        c = _ANSI
        print(f"  {c['dim']}[Leyendo {len(_at_file_blocks)} archivo(s)]{c['reset']}")

    # 1. Probar primero las skills locales (matcheo regex — sin latencia de red)
    # Solo si no hay @archivos (no tiene sentido pasar código al regex de skills)
    if _skills and not _at_file_blocks:
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

    # System prompt con contexto del entorno (CWD, repo, rama) + modo activo
    sys_parts = [_system_context_block()]
    modo_extra = _MODOS.get(_MODO_ACTUAL, {}).get("extra", "")
    if modo_extra:
        sys_parts.insert(0, modo_extra)
    if extra_ctx:
        sys_parts.append(extra_ctx)
    if cerebro_ctx:
        sys_parts.append(cerebro_ctx)
    if _at_file_blocks:
        sys_parts.append("[Archivos de contexto]\n\n" + "\n\n".join(_at_file_blocks))
    system_msg = {"role": "system", "content": "\n\n".join(p for p in sys_parts if p)}

    messages = [system_msg] + list(history)

    try:
        # Streaming: imprime tokens a medida que llegan
        response_chunks: list[str] = []
        t0 = datetime.datetime.now()
        _modo_cfg   = _MODOS.get(_MODO_ACTUAL, {})
        _force_tier = _modo_cfg.get("tier")
        _stream_kw  = {"force_tier": _force_tier} if _force_tier is not None else {}
        print()
        for chunk in _router.route_stream(messages, **_stream_kw):
            print(chunk, end="", flush=True)
            response_chunks.append(chunk)
        print()
        elapsed = (datetime.datetime.now() - t0).total_seconds()
        response = "".join(response_chunks)
        provider = getattr(_router, "_last_provider", "?")
        history.append({"role": "assistant", "content": response})

        # Guardar interacción en memoria neuronal
        if _neuro and _neuro is not False:
            try:
                _neuro.add_interaction(text, response)
            except Exception:
                pass

        # Auto-save de sesión cada N turnos
        if len(history) % (_SESSION_AUTOSAVE_EVERY * 2) == 0:
            _session_save()

        tok_approx = len(response.split())
        print(f"  [via {provider} · ~{tok_approx} tok · {elapsed:.1f}s]")
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
    try:
        from nova import __version__ as _ver
    except Exception:
        _ver = "3.9"
    print(f"  {c['white']}{c['bold']}Nova Personal AI{c['reset']}  {c['dim']}v{_ver}{c['reset']}  "
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

    read = _make_reader()

    # Onboarding primera vez (antes de lazy_init para que el router lea el perfil)
    try:
        from nova.core.nova_user_profile import UserProfile
        if not UserProfile.exists():
            _run_onboarding(read)
    except Exception:
        pass

    # Arrancar servidor Telegram Receive en background
    _lazy_init()
    try:
        from nova.connectors.nova_telegram_server import start as _tg_start
        _tg_start(process_fn=_route_to_llm)
    except Exception:
        pass

    # Restaurar última sesión (silencioso si no hay)
    if _session_load():
        n = len(_session_state["history"]) // 2
        c = _ANSI
        print(f"  {c['dim']}Sesión restaurada — {n} turno(s) en contexto  (/historial para ver · /limpiar para resetear){c['reset']}\n")

    while True:
        try:
            line = read("nova> ").strip()
        except (EOFError, KeyboardInterrupt):
            _session_save()
            print("\nHasta luego, Señor.")
            return 0

        if not line:
            continue

        # Active wizard takes priority over normal dispatch
        if _WIZARD_STATE:
            result = _wizard_handle(line)
            if result:
                print(result)
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
