"""
nova_orchestrator.py
─────────────────────
Nova como orquestador real — recibe un objetivo, planifica pasos,
ejecuta herramientas concretas, muestra progreso en vivo y reporta.

Herramientas disponibles para el orquestador:
  shell      Ejecutar comando bash
  leer       Leer archivo
  escribir   Crear/sobreescribir archivo
  editar     Reemplazar bloque en archivo existente
  buscar     Buscar patrón (grep) en archivos
  git        Operaciones git (status, diff, log, add, commit)
  web        Búsqueda web (DuckDuckGo)
  skill      Llamar a un skill de Nova por nombre

Uso:
    from nova.agents.nova_orchestrator import orquestar
    orquestar("creá una función fibonacci con tests")
"""

from __future__ import annotations

import os
import re
import json
import subprocess
import datetime
from pathlib import Path
from typing import Any
from concurrent.futures import ThreadPoolExecutor, as_completed

# ─── ANSI colores ────────────────────────────────────────────────────────────

_C = {
    "reset":  "\033[0m",
    "bold":   "\033[1m",
    "dim":    "\033[2m",
    "cyan":   "\033[96m",
    "blue":   "\033[94m",
    "green":  "\033[92m",
    "yellow": "\033[93m",
    "red":    "\033[91m",
    "white":  "\033[97m",
    "purple": "\033[95m",
}

def _c(color: str, text: str) -> str:
    return f"{_C.get(color,'')}{text}{_C['reset']}"


# ─── Herramientas concretas ───────────────────────────────────────────────────

def _tool_shell(cmd: str, timeout: int = 30) -> tuple[str, str]:
    """Ejecuta un comando bash. Retorna (stdout, stderr)."""
    try:
        r = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        return r.stdout.strip(), r.stderr.strip()
    except subprocess.TimeoutExpired:
        return "", f"timeout después de {timeout}s"
    except Exception as e:
        return "", str(e)


def _tool_leer(ruta: str) -> tuple[str, str]:
    try:
        p = Path(ruta).expanduser()
        if not p.exists():
            return "", f"Archivo no encontrado: {ruta}"
        content = p.read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines()
        # Limitar a 200 líneas para no saturar el contexto
        if len(lines) > 200:
            preview = "\n".join(lines[:200])
            return preview + f"\n... ({len(lines)-200} líneas más)", ""
        return content, ""
    except Exception as e:
        return "", str(e)


def _tool_escribir(ruta: str, contenido: str) -> tuple[str, str]:
    try:
        p = Path(ruta).expanduser()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(contenido, encoding="utf-8")
        lines = contenido.count("\n") + 1
        return f"Escrito: {ruta} ({lines} líneas)", ""
    except Exception as e:
        return "", str(e)


def _tool_editar(ruta: str, viejo: str, nuevo: str) -> tuple[str, str]:
    try:
        p = Path(ruta).expanduser()
        if not p.exists():
            return "", f"Archivo no encontrado: {ruta}"
        original = p.read_text(encoding="utf-8")
        if viejo not in original:
            return "", f"Texto a reemplazar no encontrado en {ruta}"
        updated = original.replace(viejo, nuevo, 1)
        p.write_text(updated, encoding="utf-8")
        return f"Editado: {ruta}", ""
    except Exception as e:
        return "", str(e)


def _tool_buscar(patron: str, directorio: str = ".", extension: str = "") -> tuple[str, str]:
    try:
        ext_filter = f"--include='*{extension}'" if extension else ""
        cmd = f"grep -rn {ext_filter} {json.dumps(patron)} {directorio} 2>/dev/null | head -40"
        out, err = _tool_shell(cmd)
        return out or "(sin coincidencias)", err
    except Exception as e:
        return "", str(e)


def _tool_git(subcmd: str) -> tuple[str, str]:
    safe = {"status", "diff", "log", "show", "branch", "add", "commit", "stash"}
    parts = subcmd.strip().split()
    if parts and parts[0] not in safe:
        return "", f"Subcomando git no permitido: '{parts[0]}'. Permitidos: {', '.join(sorted(safe))}"
    return _tool_shell(f"git {subcmd}")


def _tool_web(query: str) -> tuple[str, str]:
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=4))
        lines = []
        for r in results:
            lines.append(f"• {r['title']}\n  {r['href']}\n  {r['body'][:200]}")
        return "\n\n".join(lines), ""
    except Exception as e:
        return "", f"Búsqueda web no disponible: {e}"


def _tool_skill(nombre: str, arg: str = "") -> tuple[str, str]:
    try:
        from nova.tools import nova_skills
        fn = getattr(nova_skills, nombre, None)
        if fn is None:
            return "", f"Skill '{nombre}' no encontrada"
        result = fn(arg) if arg else fn()
        return str(result or ""), ""
    except Exception as e:
        return "", str(e)


_TOOLS = {
    "shell":    _tool_shell,
    "leer":     _tool_leer,
    "escribir": _tool_escribir,
    "editar":   _tool_editar,
    "buscar":   _tool_buscar,
    "git":      _tool_git,
    "web":      _tool_web,
    "skill":    _tool_skill,
}

_TOOLS_DOC = """Herramientas disponibles. Campo opcional "paralelo":true indica que ese paso puede correr simultáneo con los adyacentes que también tengan "paralelo":true.
  {"herramienta":"shell",    "args":{"cmd":"ls src/"}}
  {"herramienta":"leer",     "args":{"ruta":"src/main.py"}}
  {"herramienta":"escribir", "args":{"ruta":"out.py","contenido":"..."}}
  {"herramienta":"editar",   "args":{"ruta":"f.py","viejo":"old","nuevo":"new"}}
  {"herramienta":"buscar",   "args":{"patron":"def foo","directorio":"src","extension":".py"}}
  {"herramienta":"git",      "args":{"subcmd":"status"}}
  {"herramienta":"web",      "args":{"query":"..."}}
  {"herramienta":"skill",    "args":{"nombre":"skill_hora","arg":""}}

Regla "paralelo": marcá como paralelo=true los pasos que son independientes entre sí (no usan el resultado del otro). Ejemplo: buscar en distintos archivos, consultar web + leer docs al mismo tiempo."""


# ─── Display ──────────────────────────────────────────────────────────────────

def _header(objetivo: str) -> None:
    try:
        cols = os.get_terminal_size().columns
    except Exception:
        cols = 72
    bar = "─" * min(cols, 72)
    print(f"\n{_c('purple', bar)}")
    print(f"  {_c('bold', _c('cyan', 'Nova Orchestrator'))}  {_c('dim', '─')}  {_c('white', objetivo[:60])}")
    print(f"{_c('purple', bar)}\n")


def _paso(n: int, total: int, desc: str, estado: str = "running") -> None:
    icons = {"running": _c("yellow", "↻"), "ok": _c("green", "✓"), "err": _c("red", "✗"), "skip": _c("dim", "○")}
    icon = icons.get(estado, "·")
    num = _c("dim", f"[{n}/{total}]")
    print(f"  {icon} {num} {desc}", flush=True)


def _resultado(out: str, err: str, max_lines: int = 6) -> None:
    text = err if err and not out else out
    if not text:
        return
    lines = text.splitlines()[:max_lines]
    for line in lines:
        print(f"    {_c('dim', '│')} {_c('dim', line)}")
    if len(text.splitlines()) > max_lines:
        print(f"    {_c('dim', f'│ ... ({len(text.splitlines())-max_lines} líneas más)')}")


def _footer(hecho: list[dict], duracion: float) -> None:
    try:
        cols = os.get_terminal_size().columns
    except Exception:
        cols = 72
    bar = "─" * min(cols, 72)
    ok  = sum(1 for s in hecho if s.get("ok"))
    err = sum(1 for s in hecho if not s.get("ok"))
    print(f"\n{_c('purple', bar)}")
    print(f"  {_c('green', f'{ok} completados')}  {_c('red', f'{err} fallidos') if err else ''}  "
          f"{_c('dim', f'{duracion:.1f}s')}")
    print(f"{_c('purple', bar)}\n")


# ─── Motor de planificación ──────────────────────────────────────────────────

def _extraer_pasos(raw: str) -> list[dict]:
    """Extrae lista de pasos desde texto LLM — tolerante a JSON roto, Python dicts, markdown."""
    import ast

    # 1. Quitar bloques markdown
    raw = re.sub(r"```(?:json|python)?\n?", "", raw).replace("```", "").strip()

    # 2. Intentar JSON directo
    for attempt in [raw]:
        try:
            data = json.loads(attempt)
            pasos = data.get("pasos", data) if isinstance(data, dict) else data
            if isinstance(pasos, list) and pasos:
                return pasos
        except Exception:
            pass

    # 3. Extraer bloque {...} o [...] más grande
    for pattern in [r'\{[^{}]*"pasos"\s*:\s*\[.*?\]\s*\}',
                    r'\[\s*\{.*?\}\s*\]']:
        m = re.search(pattern, raw, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(0))
                pasos = data.get("pasos", data) if isinstance(data, dict) else data
                if isinstance(pasos, list):
                    return pasos
            except Exception:
                pass

    # 4. Fallback: ast.literal_eval (soporta Python dicts con comillas simples)
    try:
        data = ast.literal_eval(raw)
        pasos = data.get("pasos", data) if isinstance(data, dict) else data
        if isinstance(pasos, list):
            return pasos
    except Exception:
        pass

    return []


def _planificar(objetivo: str, contexto_env: str, router) -> list[dict]:
    """Pide al LLM un plan de pasos en JSON."""
    system = f"""Sos Nova, asistente IA con acceso a herramientas reales del sistema.
Respondés SOLO con un objeto JSON válido, sin texto extra, sin markdown.

{_TOOLS_DOC}

Contexto del entorno:
{contexto_env}

Formato EXACTO de respuesta (sin nada más):
{{"pasos":[{{"herramienta":"shell","args":{{"cmd":"ls"}},"descripcion":"Ver archivos"}}]}}

Reglas:
- SOLO JSON, sin texto antes ni después
- Usar comillas dobles siempre (JSON estándar)
- Máximo 8 pasos
- Para buscar TODOs en código: herramienta=buscar, args={{patron:"TODO",directorio:"."}}
- Para crear/guardar resultados: herramienta=escribir, args={{ruta:"ruta/archivo.md",contenido:"..."}}"""

    messages = [
        {"role": "system", "content": system},
        {"role": "user",   "content": f"Objetivo: {objetivo}"},
    ]
    try:
        result = router.route(messages=messages, max_tokens=1200)
        raw = result.get("response", "")
        pasos = _extraer_pasos(raw)
        if pasos:
            return pasos
        # Último recurso: construir plan básico inferido del objetivo
        return _plan_basico(objetivo)
    except Exception as e:
        return _plan_basico(objetivo)


def _plan_basico(objetivo: str) -> list[dict]:
    """Plan de fallback cuando el LLM no genera JSON válido."""
    obj_lower = objetivo.lower()
    # Detectar intención básica
    if any(w in obj_lower for w in ["todo", "pendiente", "fixme", "hack"]):
        patron = "TODO|FIXME|HACK|XXX"
        return [
            {"herramienta": "buscar",   "args": {"patron": patron, "directorio": "."},
             "descripcion": f"Buscar {patron} en el código"},
            {"herramienta": "escribir", "args": {"ruta": "docs/pendientes.md", "contenido": "# Pendientes\n\n(resultado de la búsqueda)"},
             "descripcion": "Crear resumen en docs/pendientes.md"},
        ]
    if any(w in obj_lower for w in ["test", "pytest", "prueba"]):
        return [{"herramienta": "shell", "args": {"cmd": "python -m pytest -v 2>&1 | tail -30"},
                 "descripcion": "Ejecutar tests"}]
    if any(w in obj_lower for w in ["git", "commit", "diff", "cambio"]):
        return [{"herramienta": "git", "args": {"subcmd": "status"},
                 "descripcion": "Estado del repositorio"},
                {"herramienta": "git", "args": {"subcmd": "diff --stat"},
                 "descripcion": "Archivos modificados"}]
    # Genérico: shell ls + web
    return [{"herramienta": "shell", "args": {"cmd": "ls -la"},
             "descripcion": "Ver estructura del directorio"},
            {"herramienta": "web",   "args": {"query": objetivo[:80]},
             "descripcion": "Buscar información relevante"}]


def _ejecutar_paso(paso: dict) -> tuple[str, str]:
    """Ejecuta un paso del plan. Retorna (output, error)."""
    herr = paso.get("herramienta", "")
    args = paso.get("args", {})
    fn = _TOOLS.get(herr)
    if fn is None:
        return "", f"Herramienta desconocida: '{herr}'"
    try:
        return fn(**args)
    except TypeError as e:
        return "", f"Args inválidos para '{herr}': {e}"


def _agrupar_pasos(pasos: list[dict]) -> list[list[dict]]:
    """
    Agrupa los pasos en lotes de ejecución.
    Pasos consecutivos con "paralelo":true se agrupan juntos.
    Pasos sin "paralelo" (o False) forman un lote de uno solo.
    """
    grupos: list[list[dict]] = []
    lote_actual: list[dict] = []
    for paso in pasos:
        if paso.get("paralelo"):
            lote_actual.append(paso)
        else:
            if lote_actual:
                grupos.append(lote_actual)
                lote_actual = []
            grupos.append([paso])
    if lote_actual:
        grupos.append(lote_actual)
    return grupos


def _sintetizar(objetivo: str, registro: list[dict], router) -> str:
    """LLM genera un resumen de lo que se hizo."""
    resumen_pasos = []
    for s in registro:
        estado = "✓" if s["ok"] else "✗"
        resumen_pasos.append(
            f"{estado} {s['descripcion']}\n   Resultado: {s['output'][:200]}"
            + (f"\n   Error: {s['error']}" if s['error'] else "")
        )

    messages = [{
        "role": "user",
        "content": (
            f"Objetivo: {objetivo}\n\n"
            f"Pasos ejecutados:\n" + "\n\n".join(resumen_pasos) +
            "\n\nResumí qué se logró, qué quedó pendiente (si algo), y el estado final. "
            "Sé directo y conciso."
        )
    }]
    try:
        result = router.route(messages=messages, max_tokens=400)
        return result.get("response", "Orquestación completada.")
    except Exception:
        ok = sum(1 for s in registro if s["ok"])
        return f"Completado: {ok}/{len(registro)} pasos exitosos."


# ─── Punto de entrada público ────────────────────────────────────────────────

def orquestar(objetivo: str, verbose: bool = True) -> str:
    """
    Orquesta un objetivo en múltiples pasos con herramientas reales.
    Muestra progreso en vivo. Retorna el resumen final.
    """
    from nova.core.nova_router import NovaRouter

    router = NovaRouter()

    # Contexto del entorno para el planificador
    cwd = os.getcwd()
    env_lines = [f"Directorio: {cwd}"]
    try:
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            stderr=subprocess.DEVNULL, text=True
        ).strip()
        env_lines.append(f"Git rama: {branch}")
    except Exception:
        pass
    env_lines.append(f"Fecha: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")
    contexto_env = "\n".join(env_lines)

    t0 = __import__("time").time()

    if verbose:
        _header(objetivo)
        print(f"  {_c('dim', '●')} Planificando...", flush=True)

    pasos = _planificar(objetivo, contexto_env, router)

    if not pasos:
        return "No pude generar un plan para ese objetivo."

    if verbose:
        print(f"  {_c('green', '✓')} Plan: {len(pasos)} paso{'s' if len(pasos)!=1 else ''}\n")

    registro: list[dict] = []
    grupos = _agrupar_pasos(pasos)
    paso_global = 0

    for grupo in grupos:
        es_paralelo = len(grupo) > 1

        if es_paralelo and verbose:
            print(f"  {_c('purple', '⟳')} Ejecutando {len(grupo)} pasos en paralelo...", flush=True)

        # Ejecutar: paralelo con ThreadPoolExecutor, secuencial normal
        if es_paralelo:
            resultados_grupo: dict[int, tuple[str, str]] = {}
            with ThreadPoolExecutor(max_workers=min(len(grupo), 4)) as pool:
                futuros = {pool.submit(_ejecutar_paso, p): idx
                           for idx, p in enumerate(grupo)}
                for fut in as_completed(futuros):
                    idx = futuros[fut]
                    try:
                        resultados_grupo[idx] = fut.result()
                    except Exception as e:
                        resultados_grupo[idx] = ("", str(e))
        else:
            resultados_grupo = {0: (None, None)}  # placeholder, se ejecuta abajo

        for idx, paso in enumerate(grupo):
            paso_global += 1
            desc = paso.get("descripcion", paso.get("herramienta", "paso"))
            herr = paso.get("herramienta", "?")
            prefijo = _c("purple", "⟳ ") if es_paralelo else ""

            if not es_paralelo:
                if verbose:
                    _paso(paso_global, len(pasos), f"{prefijo}{desc}  {_c('dim', f'({herr})')}", "running")
                out, err = _ejecutar_paso(paso)
            else:
                out, err = resultados_grupo[idx]

            ok = not bool(err) or bool(out)
            registro.append({"descripcion": desc, "herramienta": herr,
                              "output": out or "", "error": err or "", "ok": ok})

            if verbose:
                if not es_paralelo:
                    print(f"\033[1A\033[2K", end="")
                _paso(paso_global, len(pasos), f"{prefijo}{desc}  {_c('dim', f'({herr})')}", "ok" if ok else "err")
                _resultado(out or "", err or "")

    duracion = __import__("time").time() - t0

    if verbose:
        _footer(registro, duracion)
        print(f"  {_c('bold', 'Resumen:')}")

    resumen = _sintetizar(objetivo, registro, router)

    if verbose:
        for line in resumen.splitlines():
            print(f"  {line}")
        print()

    return resumen


# Alias para compatibilidad con código existente
def orchestrator_execute(goal: str, max_turns: int = 5) -> str:
    return orquestar(goal)
