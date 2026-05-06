"""
nova_subagents.py
─────────────────
Orquestador de subagentes paralelos para Nova.

Arquitectura:
  Nova detecta una tarea compleja → Orchestrator la descompone
  → N SubAgents corren en paralelo (threads) → resultados se sintetizan.

Modelos por rol:
  - llama-3.1-8b-instant  (Groq)  → extracción rápida, tareas simples
  - llama-3.3-70b-versatile (Groq) → razonamiento, síntesis
  - qwen3.5 / hermes3 (Ollama)    → síntesis offline, sin límite

Uso:
    from nova.connectors.nova_subagents import orquestar
    resultado = orquestar("preparame el día")
"""

from __future__ import annotations

import os
import logging
import concurrent.futures
from dataclasses import dataclass, field
from typing import Callable

log = logging.getLogger(__name__)

# ─── Config ───────────────────────────────────────────────────────────────────

_GROQ_BASE   = "https://api.groq.com/openai/v1"
_OLLAMA_BASE = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1")

_MODEL_FAST    = "llama-3.1-8b-instant"       # <1s, ideal para extracción
_MODEL_SMART   = "llama-3.3-70b-versatile"    # razonamiento + síntesis
_MODEL_LOCAL   = "qwen3.5:latest"             # offline fallback
_MODEL_VISION  = "qwen3-vl:latest"            # visión (offline)

_TIMEOUT_FAST  = 15   # segundos por agente rápido
_TIMEOUT_SMART = 30   # síntesis

# ─── Cliente LLM liviano (sin depender del router de Nova) ────────────────────

def _groq_client():
    from openai import OpenAI
    key = os.getenv("GROQ_API_KEY", "").strip()
    if not key or key.startswith("gsk_..."):
        return None
    return OpenAI(base_url=_GROQ_BASE, api_key=key)


def _ollama_client():
    from openai import OpenAI
    return OpenAI(base_url=_OLLAMA_BASE, api_key="ollama")


def _call_llm(prompt: str, system: str = "", model: str = _MODEL_FAST,
              timeout: int = _TIMEOUT_FAST, use_ollama: bool = False) -> str:
    """Llama directamente a Groq o Ollama y devuelve el texto."""
    try:
        client = _ollama_client() if use_ollama else (_groq_client() or _ollama_client())
        if use_ollama and not model.startswith("qwen") and not model.startswith("hermes") and not model.startswith("llama3"):
            model = _MODEL_LOCAL
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=600,
            temperature=0.3,
            timeout=timeout,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        log.warning("LLM call failed [%s]: %s", model, e)
        return ""


# ─── SubAgent ─────────────────────────────────────────────────────────────────

@dataclass
class SubAgent:
    """Un agente especializado en una tarea concreta."""
    name:       str
    task_fn:    Callable[[], str]          # función que ejecuta la tarea
    timeout:    int = _TIMEOUT_FAST


@dataclass
class AgentResult:
    name:    str
    output:  str
    ok:      bool
    error:   str = ""


# ─── Agentes especializados ───────────────────────────────────────────────────

def _agent_emails() -> str:
    """Trae los emails no leídos y los resume brevemente."""
    try:
        from nova.connectors import nova_google as g
        emails = g.gmail.listar_no_leidos(max_results=10)
        if not emails:
            return "Sin emails no leídos."
        items = [f"- {e['de'][:30]}: {e['asunto'][:50]}" for e in emails[:6]]
        return f"{len(emails)} emails no leídos:\n" + "\n".join(items)
    except Exception as e:
        return f"[emails error: {e}]"


def _agent_calendario() -> str:
    """Trae eventos de hoy del calendario."""
    try:
        from nova.connectors import nova_google as g
        eventos = g.calendar.eventos("hoy")
        if not eventos:
            return "Sin eventos hoy."
        items = [f"- {ev['hora']} {ev['titulo']}" for ev in eventos]
        return "Eventos de hoy:\n" + "\n".join(items)
    except Exception as e:
        return f"[calendario error: {e}]"


def _agent_clima() -> str:
    """Consulta el clima actual de Buenos Aires."""
    try:
        import urllib.request, urllib.parse, re
        url = "https://wttr.in/Buenos+Aires?format=3"
        req = urllib.request.Request(url, headers={"User-Agent": "curl/7.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            return r.read().decode().strip()
    except Exception as e:
        return f"[clima no disponible]"


def _agent_dolar() -> str:
    """Cotización del dólar blue."""
    try:
        import urllib.request, json
        url = "https://dolarapi.com/v1/dolares/blue"
        req = urllib.request.Request(url, headers={"User-Agent": "Nova/1.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read())
        compra = data.get("compra", "?")
        venta  = data.get("venta", "?")
        return f"Dólar blue: compra ${compra} / venta ${venta}"
    except Exception:
        return "[dólar no disponible]"


def _agent_noticias() -> str:
    """Titulares principales de Argentina."""
    try:
        import urllib.request, re
        url = "https://www.infobae.com/"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            html = r.read().decode("utf-8", errors="replace")
        # Extraer h2/h3 con texto
        titulares = re.findall(r'<h[23][^>]*>([^<]{20,120})</h[23]>', html)
        titulares = [t.strip() for t in titulares if len(t.strip()) > 20][:5]
        if not titulares:
            return "[noticias no disponibles]"
        return "Titulares:\n" + "\n".join(f"- {t}" for t in titulares)
    except Exception as e:
        return f"[noticias error: {e}]"


def _agent_drive_reciente() -> str:
    """Lista los archivos más recientes en Drive."""
    try:
        from nova.connectors import nova_google as g
        archivos = g.drive.listar(max_results=5)
        if not archivos:
            return "Drive vacío o sin acceso."
        items = [f"- {a['name']}" for a in archivos]
        return "Archivos recientes en Drive:\n" + "\n".join(items)
    except Exception as e:
        return f"[drive error: {e}]"


def _agent_sintetizar(partes: dict[str, str], pedido_original: str) -> str:
    """Sintetiza todos los resultados en una respuesta oral para Nova."""
    contexto = "\n\n".join(f"[{k.upper()}]\n{v}" for k, v in partes.items() if v)
    system = (
        "Sos Nova, un asistente personal AI. "
        "Sintetizá la siguiente información en un resumen breve y natural para hablar en voz alta. "
        "Usa tono directo, sin emojis, sin títulos. Máximo 5 oraciones. "
        "Si algo no está disponible, mencionalo brevemente."
    )
    prompt = f"El usuario preguntó: '{pedido_original}'\n\nDatos recolectados:\n{contexto}"

    # Intentar Groq primero, fallback Ollama
    resultado = _call_llm(prompt, system=system, model=_MODEL_SMART, timeout=_TIMEOUT_SMART)
    if not resultado:
        resultado = _call_llm(prompt, system=system, model=_MODEL_LOCAL,
                              timeout=_TIMEOUT_SMART, use_ollama=True)
    return resultado or "No pude sintetizar la información, Señor."


# ─── Configuraciones de orquestación ─────────────────────────────────────────

# Cada configuración: lista de (nombre, función) a ejecutar en paralelo
_ORCHESTRATIONS: dict[str, list[tuple[str, Callable]]] = {
    "resumen_dia": [
        ("emails",     _agent_emails),
        ("calendario", _agent_calendario),
        ("clima",      _agent_clima),
        ("dolar",      _agent_dolar),
    ],
    "briefing_completo": [
        ("emails",     _agent_emails),
        ("calendario", _agent_calendario),
        ("clima",      _agent_clima),
        ("dolar",      _agent_dolar),
        ("noticias",   _agent_noticias),
        ("drive",      _agent_drive_reciente),
    ],
    "estado_financiero": [
        ("dolar",      _agent_dolar),
        ("emails",     _agent_emails),
    ],
    "agenda": [
        ("calendario", _agent_calendario),
        ("emails",     _agent_emails),
    ],
}

# ─── Detección de intención de orquestación ───────────────────────────────────

import re as _re

_ORQUESTACION_PATTERNS: list[tuple[str, str]] = [
    # pedido → clave en _ORCHESTRATIONS
    (r"(?:prepara(?:me)?|dame|muéstrame|resumen(?: del)?)\s+(?:el\s+)?día", "resumen_dia"),
    (r"(?:briefing|morning\s+brief|resumen\s+completo|todo\s+de\s+hoy)", "briefing_completo"),
    (r"(?:cómo\s+está|estado\s+(?:del\s+)?(?:mercado|finanza|dólar|plata))", "estado_financiero"),
    (r"(?:qué\s+(?:tengo|hay)\s+(?:hoy|mañana|esta\s+semana).*y.*(?:email|mail|correo)|"
     r"(?:email|mail|correo).*y.*(?:agenda|calendario|eventos))", "agenda"),
]


def _detectar_orquestacion(texto: str) -> str | None:
    t = texto.lower().strip()
    for pattern, key in _ORQUESTACION_PATTERNS:
        if _re.search(pattern, t):
            return key
    return None


# ─── Orquestador principal ────────────────────────────────────────────────────

def orquestar(texto: str, orquestacion: str | None = None) -> str:
    """
    Punto de entrada principal.
    Detecta qué agentes lanzar, los corre en paralelo y sintetiza.
    """
    if orquestacion is None:
        orquestacion = _detectar_orquestacion(texto)

    if orquestacion not in _ORCHESTRATIONS:
        return ""  # no aplica orquestación, que lo maneje Nova normal

    agentes = _ORCHESTRATIONS[orquestacion]
    log.info("Orquestando '%s' con %d agentes en paralelo", orquestacion, len(agentes))

    resultados: dict[str, str] = {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(agentes)) as pool:
        futures = {pool.submit(fn): name for name, fn in agentes}
        for future in concurrent.futures.as_completed(futures, timeout=20):
            name = futures[future]
            try:
                resultados[name] = future.result(timeout=1)
                log.info("Agente '%s' completado", name)
            except Exception as e:
                resultados[name] = f"[{name} no disponible]"
                log.warning("Agente '%s' falló: %s", name, e)

    return _agent_sintetizar(resultados, texto)


def orquestar_paralelo(tareas: list[tuple[str, Callable]]) -> dict[str, str]:
    """
    Versión genérica: recibe lista de (nombre, función) y devuelve dict de resultados.
    Útil para orquestaciones ad-hoc desde skills.
    """
    resultados: dict[str, str] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(len(tareas), 1)) as pool:
        futures = {pool.submit(fn): name for name, fn in tareas}
        for future in concurrent.futures.as_completed(futures, timeout=25):
            name = futures[future]
            try:
                resultados[name] = future.result(timeout=1)
            except Exception as e:
                resultados[name] = f"[{name} no disponible: {e}]"
    return resultados


# ═══════════════════════════════════════════════════════════════
# AGENTES DE ANÁLISIS — archivos, código, repositorios
# ═══════════════════════════════════════════════════════════════

def _resumir_texto(nombre: str, contenido: str, instruccion: str = "") -> str:
    """Usa LLM para resumir un bloque de texto (archivo, código, etc.)."""
    max_chars = 6000
    if len(contenido) > max_chars:
        contenido = contenido[:max_chars] + "\n[... truncado]"
    system = (
        "Sos un asistente de análisis de código y documentos. "
        "Respondé siempre en español, de forma concisa y técnica. "
        "Máximo 8 líneas."
    )
    extra = f" Instrucción adicional: {instruccion}" if instruccion else ""
    prompt = f"Analizá este archivo llamado '{nombre}':{extra}\n\n{contenido}"
    resultado = _call_llm(prompt, system=system, model=_MODEL_FAST, timeout=20)
    if not resultado:
        resultado = _call_llm(prompt, system=system, model=_MODEL_LOCAL,
                              timeout=20, use_ollama=True)
    return resultado or "[sin análisis]"


def analizar_archivo(path: str, instruccion: str = "") -> str:
    """
    Lee y analiza un archivo con un subagente LLM.
    Devuelve un resumen del contenido.
    """
    import pathlib
    p = pathlib.Path(path).expanduser()
    if not p.exists():
        return f"[archivo no encontrado: {path}]"

    try:
        contenido = p.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"[error leyendo {p.name}: {e}]"

    return _resumir_texto(p.name, contenido, instruccion)


def analizar_archivos(paths: list[str], instruccion: str = "") -> str:
    """
    Analiza múltiples archivos en paralelo y sintetiza un resumen conjunto.
    paths: lista de rutas absolutas o relativas al home
    """
    if not paths:
        return "No se especificaron archivos."

    tareas = [(p, lambda p=p: analizar_archivo(p, instruccion)) for p in paths]
    resultados = orquestar_paralelo(tareas)

    # Síntesis final
    system = (
        "Sos un asistente técnico. Te doy resúmenes individuales de archivos. "
        "Hacé un resumen conjunto: qué hace este código/proyecto, cómo se relacionan los archivos, "
        "puntos importantes. Respondé en español, máximo 10 líneas."
    )
    contexto = "\n\n".join(f"[{k}]\n{v}" for k, v in resultados.items())
    prompt = f"Archivos analizados:\n{contexto}"
    if instruccion:
        prompt += f"\n\nInstrucción especial: {instruccion}"

    sintesis = _call_llm(prompt, system=system, model=_MODEL_SMART, timeout=30)
    if not sintesis:
        sintesis = _call_llm(prompt, system=system, model=_MODEL_LOCAL,
                             timeout=30, use_ollama=True)
    return sintesis or "\n\n".join(f"**{k}**: {v}" for k, v in resultados.items())


def analizar_repo(path: str = ".", instruccion: str = "") -> str:
    """
    Analiza un repositorio git: estructura, commits recientes, archivos clave.
    Corre múltiples subagentes en paralelo.
    """
    import pathlib, subprocess

    base = pathlib.Path(path).expanduser().resolve()
    if not base.exists():
        return f"Repositorio no encontrado: {path}"

    def _git_info() -> str:
        try:
            log_out = subprocess.check_output(
                ["git", "log", "--oneline", "-10"],
                cwd=base, stderr=subprocess.DEVNULL, text=True
            )
            branch = subprocess.check_output(
                ["git", "branch", "--show-current"],
                cwd=base, stderr=subprocess.DEVNULL, text=True
            ).strip()
            status = subprocess.check_output(
                ["git", "status", "--short"],
                cwd=base, stderr=subprocess.DEVNULL, text=True
            )
            return f"Rama: {branch}\n\nÚltimos commits:\n{log_out}\nCambios pendientes:\n{status or '(limpio)'}"
        except Exception as e:
            return f"[git no disponible: {e}]"

    def _estructura() -> str:
        try:
            items = []
            for p in sorted(base.rglob("*")):
                if any(x in p.parts for x in [".git", "__pycache__", "node_modules", ".venv", "venv"]):
                    continue
                rel = p.relative_to(base)
                depth = len(rel.parts)
                if depth > 3:
                    continue
                prefix = "  " * (depth - 1)
                items.append(f"{prefix}{'📁' if p.is_dir() else '📄'} {p.name}")
            return "\n".join(items[:60])
        except Exception as e:
            return f"[estructura no disponible: {e}]"

    def _archivos_clave() -> str:
        # Lee README + archivos principales (main, __init__, config, etc.)
        candidatos = ["README.md", "README.rst", "main.py", "app.py", "index.py",
                      "pyproject.toml", "package.json", "requirements.txt"]
        textos = []
        for nombre in candidatos:
            p = base / nombre
            if p.exists():
                try:
                    contenido = p.read_text(encoding="utf-8", errors="replace")[:2000]
                    textos.append(f"--- {nombre} ---\n{contenido}")
                except Exception:
                    pass
        return "\n\n".join(textos) if textos else "[sin archivos clave encontrados]"

    # Correr los 3 agentes en paralelo
    resultados = orquestar_paralelo([
        ("git",       _git_info),
        ("estructura", _estructura),
        ("archivos",  _archivos_clave),
    ])

    # Síntesis
    system = (
        "Sos un code reviewer experto. Analizá el repositorio y explicá: "
        "qué hace el proyecto, su estructura, estado actual (commits, cambios), "
        "y puntos relevantes. Respondé en español, tono técnico directo, máximo 12 líneas."
    )
    contexto = "\n\n".join(f"[{k.upper()}]\n{v}" for k, v in resultados.items())
    prompt = f"Repositorio en: {base}\n\n{contexto}"
    if instruccion:
        prompt += f"\n\nEnfocate en: {instruccion}"

    sintesis = _call_llm(prompt, system=system, model=_MODEL_SMART, timeout=35)
    if not sintesis:
        sintesis = _call_llm(prompt, system=system, model=_MODEL_LOCAL,
                             timeout=35, use_ollama=True)
    return sintesis or f"Repositorio analizado. Git:\n{resultados.get('git','')}"


# ─── Descomposición dinámica de tareas ───────────────────────────────────────

def descomponer_y_ejecutar(pedido: str, contexto_extra: str = "") -> str:
    """
    LLM descompone el pedido en subtareas, las ejecuta en paralelo y sintetiza.
    Para pedidos libres que Nova no puede mapear a una orquestación fija.

    Subtareas soportadas: analizar_archivo(path), buscar_web(query),
    leer_drive(query), consultar_emails(query)
    """
    system = """Sos un planificador de tareas para un agente AI.
Dado un pedido, descomponelo en subtareas paralelas ejecutables.
Respondé SOLO con JSON, sin explicación:
{
  "subtareas": [
    {"tipo": "analizar_archivo", "param": "/ruta/al/archivo"},
    {"tipo": "buscar_web",       "param": "query de búsqueda"},
    {"tipo": "leer_drive",       "param": "nombre de archivo en Drive"},
    {"tipo": "consultar_emails", "param": "query de búsqueda de emails"}
  ]
}
Usá solo los tipos listados. Máximo 6 subtareas."""

    prompt = f"Pedido: {pedido}"
    if contexto_extra:
        prompt += f"\nContexto: {contexto_extra}"

    raw = _call_llm(prompt, system=system, model=_MODEL_SMART, timeout=20)
    if not raw:
        return ""

    import json
    try:
        data = json.loads(raw[raw.find("{"):raw.rfind("}") + 1])
        subtareas = data.get("subtareas", [])
    except Exception:
        return ""

    if not subtareas:
        return ""

    # Construir tareas ejecutables
    tareas: list[tuple[str, Callable]] = []
    for st in subtareas:
        tipo  = st.get("tipo", "")
        param = st.get("param", "")
        if tipo == "analizar_archivo" and param:
            tareas.append((f"archivo:{param}", lambda p=param: analizar_archivo(p)))
        elif tipo == "buscar_web" and param:
            from nova.tools.nova_skills import web_search
            tareas.append((f"web:{param[:30]}", lambda q=param: web_search(q)))
        elif tipo == "leer_drive" and param:
            from nova.connectors import nova_google as g
            tareas.append((f"drive:{param[:30]}", lambda q=param: str(g.drive.buscar(q)[:3])))
        elif tipo == "consultar_emails" and param:
            from nova.connectors import nova_google as g
            tareas.append((f"email:{param[:30]}", lambda q=param: str(g.gmail.buscar(q)[:3])))

    if not tareas:
        return ""

    resultados = orquestar_paralelo(tareas)
    return _agent_sintetizar(resultados, pedido)
