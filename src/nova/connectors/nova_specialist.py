"""
nova_specialist.py — Invocador de agentes especializados para Nova.

Carga los system prompts de ~/.claude/skills/agency-agents/ y los usa
con Groq/OpenRouter (NO Claude API). Permite que Nova actúe como cualquier
agente especializado sin consumir créditos de Claude.
"""

import os
import re
import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# Cargar variables de entorno
try:
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv()
except ImportError:
    pass

# Directorio raíz de los agentes
_AGENTS_DIR = Path(os.getenv("AGENCY_AGENTS_DIR",
                              "~/.claude/skills/agency-agents")).expanduser()

# Caché en memoria: {slug: {"name": str, "description": str, "system": str, "category": str}}
_agent_cache: dict[str, dict] = {}


# ── Carga de agentes ──────────────────────────────────────────────────────────

def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Extrae frontmatter YAML y el cuerpo del .md."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    fm_block = text[3:end].strip()
    body = text[end + 4:].strip()
    fm: dict = {}
    for line in fm_block.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip()
    return fm, body


def _load_agents() -> None:
    """Carga todos los .md de agency-agents en caché."""
    if _agent_cache:
        return
    if not _AGENTS_DIR.exists():
        log.warning("[Specialist] Directorio de agentes no existe: %s", _AGENTS_DIR)
        return

    for md_file in _AGENTS_DIR.rglob("*.md"):
        # Saltar README y archivos de metadatos
        if md_file.stem.upper() in ("README", "CONTRIBUTING", "LICENSE", "CONTRIBUTING_ZH-CN"):
            continue
        try:
            text = md_file.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        fm, body = _parse_frontmatter(text)
        name = fm.get("name", md_file.stem.replace("-", " ").title())
        description = fm.get("description", "")
        category = md_file.parent.name  # engineering, design, etc.

        # Slug = nombre del archivo sin extensión
        slug = md_file.stem  # e.g. "engineering-embedded-firmware-engineer"
        short_slug = re.sub(r"^[a-z]+-", "", slug, count=1)  # "embedded-firmware-engineer"

        _agent_cache[slug] = {
            "name": name,
            "description": description,
            "system": body,
            "category": category,
            "file": str(md_file),
            "slug": slug,
            "short_slug": short_slug,
        }

    log.info("[Specialist] %d agentes cargados desde %s", len(_agent_cache), _AGENTS_DIR)


def list_agents(category: Optional[str] = None) -> list[dict]:
    """Devuelve lista de agentes disponibles, opcionalmente filtrados por categoría."""
    _load_agents()
    agents = list(_agent_cache.values())
    if category:
        agents = [a for a in agents if a["category"] == category]
    return sorted(agents, key=lambda a: a["name"])


def find_agent(query: str) -> Optional[dict]:
    """
    Busca el agente más relevante para la query.
    Intenta coincidencia por slug, nombre, o keywords.
    """
    _load_agents()
    if not _agent_cache:
        return None

    query_lower = query.lower().strip()

    # 1. Coincidencia exacta por slug o short_slug
    for agent in _agent_cache.values():
        if query_lower == agent["slug"] or query_lower == agent["short_slug"]:
            return agent

    # 2. Coincidencia parcial por nombre
    for agent in _agent_cache.values():
        if query_lower in agent["name"].lower():
            return agent

    # 3. Coincidencia en slug
    for agent in _agent_cache.values():
        if query_lower in agent["slug"]:
            return agent

    # 4. Coincidencia por palabras clave en descripción
    words = query_lower.split()
    scored: list[tuple[int, dict]] = []
    for agent in _agent_cache.values():
        score = sum(1 for w in words if w in agent["description"].lower() or w in agent["name"].lower())
        if score > 0:
            scored.append((score, agent))

    if scored:
        scored.sort(key=lambda x: -x[0])
        return scored[0][1]

    return None


# ── Invocación vía Groq / OpenRouter ─────────────────────────────────────────

def _call_groq(system: str, user: str, model: str = "llama-3.3-70b-versatile") -> Optional[str]:
    """Llama a Groq con el system prompt dado (usa SDK oficial para evitar Cloudflare)."""
    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key or api_key == "gsk_...":
        return None
    try:
        from groq import Groq
        client = Groq(api_key=api_key)
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.7,
            max_tokens=2000,
        )
        return (completion.choices[0].message.content or "").strip() or None
    except Exception as e:
        log.warning("[Specialist] Groq error: %s", e)
        return None


def _call_openrouter(system: str, user: str,
                     model: str = "minimax/minimax-m2.5:free") -> Optional[str]:
    """Llama a OpenRouter con el system prompt dado."""
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    if not api_key:
        return None
    try:
        import requests
        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://nova.local",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.7,
                "max_tokens": 2000,
            },
            timeout=60,
        )
        if resp.status_code == 429:
            return None  # rate limited, probar siguiente modelo
        resp.raise_for_status()
        return (resp.json().get("choices", [{}])[0].get("message", {}).get("content") or "").strip() or None
    except Exception as e:
        log.warning("[Specialist] OpenRouter error (%s): %s", model, e)
        return None


def _extract_code_blocks(text: str) -> list[tuple[str, str]]:
    """Extrae bloques de código del markdown. Retorna lista de (lang, code)."""
    return re.findall(r"```(python|bash|sh|shell|zsh|python3)\n(.*?)```", text, re.DOTALL)


def _run_code_block(lang: str, code: str, timeout: int = 30) -> str:
    """Ejecuta un bloque de código Python o bash y retorna el output."""
    import subprocess, tempfile, os

    code = code.strip()
    if lang in ("python", "python3"):
        ext, runner = ".py", ["python3"]
    elif lang in ("bash", "sh", "shell", "zsh"):
        ext, runner = ".sh", ["bash"]
    else:
        return f"(lenguaje '{lang}' no ejecutable automáticamente)"

    with tempfile.NamedTemporaryFile(suffix=ext, mode="w", delete=False, encoding="utf-8") as f:
        f.write(code)
        tmp = f.name

    try:
        result = subprocess.run(
            runner + [tmp],
            capture_output=True, text=True, timeout=timeout,
            cwd=os.path.expanduser("~")
        )
        out = (result.stdout + result.stderr).strip()
        return out[:2000] if out else "(sin output)"
    except subprocess.TimeoutExpired:
        return f"⚠ Timeout ({timeout}s) ejecutando código."
    except Exception as e:
        return f"⚠ Error al ejecutar: {e}"
    finally:
        try:
            os.unlink(tmp)
        except Exception:
            pass


def _run_blender_script(code: str) -> str:
    """Envía un script Python a Blender via nova_blender."""
    try:
        from nova.connectors.nova_blender import ejecutar_script
        return ejecutar_script(code)
    except ImportError:
        return "(Blender no disponible)"
    except Exception as e:
        return f"(Error Blender: {e})"


_ERROR_MARKERS = (
    "Traceback (most recent call last)",
    "SyntaxError:", "NameError:", "TypeError:", "ValueError:",
    "ImportError:", "ModuleNotFoundError:", "AttributeError:",
    "KeyError:", "IndexError:", "RuntimeError:", "OSError:",
    "Exception:", "Error:",
)


def _has_execution_error(output: str) -> bool:
    """Devuelve True si el output de ejecución contiene un error."""
    if output.startswith("⚠"):
        return True
    return any(m in output for m in _ERROR_MARKERS)


def ejecutar_con_feedback(agent: dict, task: str, max_iter: int = 3) -> str:
    """
    Invoca un agente, ejecuta su código y si falla lo pasa de vuelta
    para auto-corrección. Máximo `max_iter` iteraciones.
    """
    name = agent["name"]
    system = agent["system"]
    hint = "\n\n(Always use fenced markdown code blocks for any code: ```lang\ncode\n```)"
    current_task = task + hint
    last_result = ""

    for iteration in range(1, max_iter + 1):
        # ── Llamar al LLM ────────────────────────────────────────────────────
        resp = _call_groq(system, current_task, model="llama-3.3-70b-versatile")
        if not resp:
            for or_model in _OR_TEXT_MODELS:
                resp = _call_openrouter(system, current_task, model=or_model)
                if resp:
                    break
        if not resp:
            return f"[{name}] Sin conexión al LLM. Verifica API keys."

        # ── Ejecutar bloques de código ───────────────────────────────────────
        blocks = _extract_code_blocks(resp)
        if not blocks:
            return f"[{name}]\n{resp}"

        iter_label = f"(intento {iteration}/{max_iter})" if iteration > 1 else ""
        parts = [f"[{name}]{' ' + iter_label if iter_label else ''}\n{resp}"]
        error_context = ""
        all_ok = True

        for lang, code in blocks:
            code = code.strip()
            if not code:
                continue
            if "import bpy" in code or "bpy.ops" in code or "bpy.data" in code:
                parts.append("\n▶ Enviando script a Blender...")
                out = _run_blender_script(code)
            else:
                parts.append(f"\n▶ Ejecutando ({lang}):")
                out = _run_code_block(lang, code)
            parts.append(out)

            if _has_execution_error(out):
                all_ok = False
                error_context += f"```{lang}\n{code}\n```\nError:\n{out[:800]}\n\n"

        last_result = "\n".join(parts)

        if all_ok:
            log.debug("[Especialista] '%s' completado en %d intento(s)", name, iteration)
            return last_result

        if iteration < max_iter:
            log.info("[Especialista] Error en iter %d/%d — reintentando con feedback", iteration, max_iter)
            current_task = (
                f"El código anterior falló. Corrige el error y devuelve solo el código corregido.\n\n"
                f"Tarea original: {task}\n\n"
                f"Código y error:\n{error_context}"
                + hint
            )
        else:
            last_result += f"\n\n⚠ Auto-corrección agotada ({max_iter} intentos)."

    return last_result


def _process_response(name: str, resp: str, auto_exec: bool = True) -> str:
    """
    Procesa la respuesta del agente:
    - Si contiene Python → ejecuta automáticamente si auto_exec=True
    - Si contiene bash → ejecuta automáticamente
    - Si contiene código Blender → envía a Blender
    - Retorna respuesta + outputs de ejecución
    """
    blocks = _extract_code_blocks(resp)
    if not blocks or not auto_exec:
        return f"[{name}]\n{resp}"

    parts = [f"[{name}]\n{resp}"]
    for lang, code in blocks:
        code = code.strip()
        if not code:
            continue

        # Detectar si es un script de Blender (usa bpy)
        if "import bpy" in code or "bpy.ops" in code or "bpy.data" in code:
            parts.append(f"\n▶ Enviando script a Blender...")
            out = _run_blender_script(code)
            parts.append(f"Blender: {out}")
        else:
            parts.append(f"\n▶ Ejecutando ({lang}):")
            out = _run_code_block(lang, code)
            parts.append(out)

    return "\n".join(parts)


# Modelos OpenRouter gratuitos en orden de preferencia
_OR_TEXT_MODELS = [
    "minimax/minimax-m2.5:free",
    "tencent/hy3-preview:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "google/gemma-4-31b-it:free",
    "google/gemma-4-26b-a4b-it:free",
    "qwen/qwen3-next-80b-a3b-instruct:free",
]

# ── Creación de proyectos / archivos ─────────────────────────────────────────

# Formato de archivo que pedimos al LLM:
#   === FILE: ruta/al/archivo.ext ===
#   contenido
#   === END FILE ===
_FILE_BLOCK_RE = re.compile(
    r"={3}\s*FILE:\s*(.+?)\s*={3}\n(.*?)(?:={3}\s*END FILE\s*={3}|(?=\n={3}\s*FILE:)|\Z)",
    re.DOTALL
)


def _parse_file_blocks(text: str) -> list[tuple[str, str]]:
    """Extrae pares (ruta, contenido) del formato === FILE: ... === del LLM."""
    return [(m.group(1).strip(), m.group(2).rstrip()) for m in _FILE_BLOCK_RE.finditer(text)]


def _strip_code_fence(content: str) -> str:
    """Elimina fences markdown del contenido si el LLM los incluyó dentro del FILE block."""
    content = content.strip()
    # Detectar si todo el contenido es un único bloque de código
    m = re.match(r"^```[\w]*\n(.*?)```\s*$", content, re.DOTALL)
    if m:
        return m.group(1)
    return content


# ── Tests automáticos ────────────────────────────────────────────────────────

_PY_FUNC_RE  = re.compile(r"^def\s+([a-zA-Z_]\w*)\s*\(", re.MULTILINE)
_PY_CLASS_RE = re.compile(r"^class\s+([a-zA-Z_]\w*)\s*[:(]", re.MULTILINE)

_TEST_AGENT_SYSTEM = """You are an expert Python test engineer.
Given source code, write comprehensive pytest tests that cover:
- Happy path (normal inputs)
- Edge cases (empty, None, zero, large values)
- Error cases (invalid input raises the right exception)

Rules:
- Use pytest fixtures when appropriate
- Mock external calls (HTTP, DB, filesystem) with unittest.mock
- Each test function name must start with test_
- Output ONLY the test file content — no explanation
- Use fenced code block: ```python\\n<code>\\n```
"""

_TEST_SYSTEM_PROMPT = """You are an expert Python test engineer specializing in pytest.
Write comprehensive tests covering happy paths, edge cases, and error conditions.
Use unittest.mock for external dependencies. Output only pytest code."""


def _run_pytest(test_file: Path, base_dir: Path) -> str:
    """Ejecuta pytest en un archivo y retorna un resumen compacto."""
    import subprocess
    try:
        result = subprocess.run(
            ["python", "-m", "pytest", str(test_file), "-v", "--tb=short", "--no-header"],
            capture_output=True, text=True, timeout=60, cwd=base_dir,
        )
        output = (result.stdout + result.stderr).strip()
        # Extraer solo el resumen final (línea con passed/failed)
        lines = output.splitlines()
        summary_lines = [l for l in lines if re.search(r"\d+\s+(passed|failed|error)", l)]
        summary = summary_lines[-1] if summary_lines else output[-300:]
        status = "✓" if result.returncode == 0 else "✗"
        return f"{status} pytest {test_file.name}: {summary}"
    except FileNotFoundError:
        return "(pytest no instalado — ejecuta: pip install pytest)"
    except subprocess.TimeoutExpired:
        return "⚠ pytest timeout (60s)"
    except Exception as e:
        return f"⚠ Error ejecutando pytest: {e}"


def generar_tests(code: str, source_path: Path, base_dir: Path,
                  run: bool = True) -> str:
    """
    Genera tests pytest para el código dado usando el agente code-reviewer.
    Escribe tests/test_<name>.py y opcionalmente ejecuta pytest.
    Retorna resumen de tests generados y resultados.
    """
    _load_agents()
    agent = (_agent_cache.get("engineering-code-reviewer")
             or find_agent("code reviewer")
             or find_agent("backend architect"))
    if not agent:
        return "(agente de tests no disponible)"

    funcs   = _PY_FUNC_RE.findall(code)
    classes = _PY_CLASS_RE.findall(code)
    symbols = funcs + classes
    if not symbols:
        return "(no se encontraron funciones/clases para testear)"

    log.info("[Tests] Generando tests para: %s", ", ".join(symbols[:5]))

    module_name = source_path.stem
    prompt = (
        f"Generate pytest tests for the following Python module `{module_name}.py`.\n"
        f"Functions/classes to test: {', '.join(symbols)}\n\n"
        f"Source code:\n```python\n{code[:6000]}\n```\n\n"
        f"Write tests in a file named `test_{module_name}.py`.\n"
        f"Import the module as: `from {module_name} import *` or with the correct path.\n"
        f"Output ONLY the complete test file inside a fenced ```python block."
    )

    system = _TEST_SYSTEM_PROMPT
    resp = _call_groq(system, prompt, model="llama-3.3-70b-versatile")
    if not resp:
        for m in _OR_TEXT_MODELS:
            resp = _call_openrouter(system, prompt, model=m)
            if resp:
                break
    if not resp:
        return "(sin conexión LLM para generar tests)"

    # Extraer bloque python de la respuesta
    blocks = _extract_code_blocks(resp)
    py_blocks = [(l, c) for l, c in blocks if l in ("python", "python3")]
    if not py_blocks:
        return f"(el agente no generó código de tests válido)\n{resp[:300]}"

    test_code = py_blocks[0][1].strip()

    # Escribir en tests/test_<module>.py
    tests_dir = base_dir / "tests"
    tests_dir.mkdir(exist_ok=True)

    # Crear __init__.py si no existe
    init = tests_dir / "__init__.py"
    if not init.exists():
        init.write_text("", encoding="utf-8")

    test_file = tests_dir / f"test_{module_name}.py"
    print(f"\n── [TEST GEN] {test_file.relative_to(base_dir)} ──────────────────")
    print(test_code[:600] + ("\n[...]" if len(test_code) > 600 else ""))
    test_file.write_text(test_code, encoding="utf-8")

    result_str = f"✓ Tests generados: {test_file.relative_to(base_dir)}"
    if run:
        pytest_result = _run_pytest(test_file, base_dir)
        result_str += f"\n{pytest_result}"

    return result_str


def _color_diff(dest: Path, new_content: str) -> str:
    """
    Genera un diff unificado coloreado entre el contenido actual del archivo
    y el nuevo contenido. Retorna string listo para imprimir en terminal.
    Si el archivo no existe, muestra todo como añadido.
    """
    import difflib

    GREEN  = "\033[92m"
    RED    = "\033[91m"
    CYAN   = "\033[96m"
    RESET  = "\033[0m"

    old_lines = dest.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True) if dest.exists() else []
    new_lines = new_content.splitlines(keepends=True)

    label_a = str(dest) if dest.exists() else "/dev/null"
    diff = list(difflib.unified_diff(old_lines, new_lines,
                                     fromfile=label_a, tofile=str(dest), lineterm=""))
    if not diff:
        return ""

    colored = []
    for line in diff:
        if line.startswith("+++") or line.startswith("---"):
            colored.append(f"{CYAN}{line}{RESET}")
        elif line.startswith("@@"):
            colored.append(f"{CYAN}{line}{RESET}")
        elif line.startswith("+"):
            colored.append(f"{GREEN}{line}{RESET}")
        elif line.startswith("-"):
            colored.append(f"{RED}{line}{RESET}")
        else:
            colored.append(line)
    return "".join(colored)


def _write_project_files(files: list[tuple[str, str]], base_dir: Path) -> list[str]:
    """
    Escribe archivos al disco mostrando diff coloreado antes de cada escritura.
    Con NOVA_DIFF_CONFIRM=1 (y stdin TTY) pide confirmación por archivo.
    Retorna lista de rutas creadas/modificadas.
    """
    import sys
    confirm_mode = os.getenv("NOVA_DIFF_CONFIRM", "0") == "1" and sys.stdin.isatty()
    created = []
    dir_name = base_dir.name

    for rel_path, content in files:
        rel_path = rel_path.lstrip("/").replace("..", "")
        parts = Path(rel_path).parts
        if parts and parts[0] == dir_name:
            rel_path = str(Path(*parts[1:])) if len(parts) > 1 else parts[0]
        dest = base_dir / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)

        new_content = _strip_code_fence(content)
        diff_output = _color_diff(dest, new_content)

        if diff_output:
            action = "NUEVO" if not dest.exists() else "MODIF"
            print(f"\n── [{action}] {rel_path} {'─'*max(0, 50 - len(rel_path))}")
            print(diff_output, end="")
        else:
            print(f"  (sin cambios) {rel_path}")
            continue  # no reescribir si el contenido es idéntico

        if confirm_mode:
            resp = input("\n  ¿Aplicar este cambio? [S/n]: ").strip().lower()
            if resp in ("n", "no"):
                print("  → Omitido.")
                continue

        dest.write_text(new_content, encoding="utf-8")
        created.append(str(dest.relative_to(base_dir)))

    # Generar tests automáticos para archivos Python si NOVA_AUTO_TESTS=1
    if os.getenv("NOVA_AUTO_TESTS", "0") == "1":
        for rel in created:
            p = base_dir / rel
            if p.suffix == ".py" and not p.stem.startswith("test_") and p.parent.name != "tests":
                try:
                    code = p.read_text(encoding="utf-8", errors="replace")
                    if _PY_FUNC_RE.search(code):   # solo si tiene funciones
                        test_res = generar_tests(code, p, base_dir, run=True)
                        log.info("[Tests] %s → %s", rel, test_res[:80])
                        if created:  # añadir el test file a la lista si se creó
                            tf = base_dir / "tests" / f"test_{p.stem}.py"
                            if tf.exists():
                                created.append(str(tf.relative_to(base_dir)))
                except Exception as e:
                    log.warning("[Tests] Error generando tests para %s: %s", rel, e)

    return created


_PROJECT_SYSTEM_SUFFIX = """

## Output Format for File Creation
When creating a project, output EVERY file using EXACTLY this format:

=== FILE: path/to/file.ext ===
file content here
=== END FILE ===

Start immediately with the first file. No introduction before the first === FILE: === marker.
Create ALL necessary files: source code, README.md, configuration files, etc.
"""


def crear_proyecto(
    descripcion: str,
    destino: Optional[str] = None,
    agente_query: str = "software architect",
    git_init: bool = True,
) -> str:
    """
    Crea un proyecto completo en disco a partir de una descripción.
    El agente especializado genera los archivos en formato estructurado
    y Nova los escribe al sistema de archivos.

    Retorna resumen de lo creado.
    """
    _load_agents()

    agent = find_agent(agente_query)
    if not agent:
        return f"No encontré agente para '{agente_query}'."

    # Resolver directorio destino
    if destino:
        base_dir = Path(destino).expanduser().resolve()
    else:
        # Nombre de proyecto desde descripción
        nombre = re.sub(r"[^a-z0-9_-]", "_", descripcion.lower().split()[0])[:20]
        base_dir = Path.home() / "Desktop" / f"proyecto_{nombre}"

    base_dir.mkdir(parents=True, exist_ok=True)

    name = agent["name"]
    system = agent["system"] + _PROJECT_SYSTEM_SUFFIX

    prompt = (
        f"Create a complete project for: {descripcion}\n\n"
        f"Base directory: {base_dir.name}\n"
        f"Output ALL files using the === FILE: path === format. "
        f"Include README.md, source files, and any config needed to run the project."
    )

    # Llamar al LLM
    resp: Optional[str] = None
    groq_models = ["llama-3.3-70b-versatile", "llama-3.1-70b-versatile", "llama-3.1-8b-instant"]
    for gm in groq_models:
        resp = _call_groq(system, prompt, model=gm)
        if resp:
            break

    if not resp:
        or_models = [
            "minimax/minimax-m2.5:free",
            "nvidia/nemotron-3-super-120b-a12b:free",
            "google/gemma-4-31b-it:free",
            "google/gemma-4-26b-a4b-it:free",
        ]
        for om in or_models:
            resp = _call_openrouter(system, prompt, model=om)
            if resp:
                break

    if not resp:
        return "No pude conectarme al LLM para generar el proyecto."

    # Parsear archivos del response
    files = _parse_file_blocks(resp)

    # Si el LLM no usó el formato estructurado, intentar extraer bloques de código con nombres
    if not files:
        # Fallback: buscar "# filename.ext" o "// filename.ext" como marcadores
        alt_blocks = re.findall(r"(?:#+|//)\s*([\w./\-]+\.\w+)\n```\w*\n(.*?)```", resp, re.DOTALL)
        files = [(p, c.strip()) for p, c in alt_blocks]

    if not files:
        # Guardar respuesta raw como markdown si no hay estructura
        raw_file = base_dir / "output.md"
        raw_file.write_text(f"# Proyecto generado por {name}\n\n{resp}", encoding="utf-8")
        files_created = ["output.md (respuesta sin estructura de archivos)"]
    else:
        files_created = _write_project_files(files, base_dir)

    # git init opcional
    git_msg = ""
    if git_init and files_created and files_created[0] != "output.md (respuesta sin estructura de archivos)":
        import subprocess
        try:
            subprocess.run(["git", "init"], cwd=base_dir, capture_output=True)
            subprocess.run(["git", "add", "."], cwd=base_dir, capture_output=True)
            subprocess.run(
                ["git", "commit", "-m", f"initial: {descripcion[:50]}"],
                cwd=base_dir, capture_output=True,
                env={**os.environ, "GIT_AUTHOR_NAME": "Nova", "GIT_AUTHOR_EMAIL": "nova@nova.local",
                     "GIT_COMMITTER_NAME": "Nova", "GIT_COMMITTER_EMAIL": "nova@nova.local"}
            )
            git_msg = "\n✓ git init + primer commit"
        except Exception as e:
            git_msg = f"\n(git: {e})"

    summary = (
        f"[{name}] Proyecto creado en: {base_dir}\n"
        f"Archivos ({len(files_created)}):\n"
        + "\n".join(f"  • {f}" for f in files_created)
        + git_msg
    )
    return summary


def invoke_specialist(agent: dict, task: str, auto_exec: bool = True) -> str:
    """
    Invoca un agente especializado. Si auto_exec=True y la respuesta contiene
    código ejecutable, usa el loop de feedback (hasta 3 correcciones automáticas).
    """
    if auto_exec:
        return ejecutar_con_feedback(agent, task)

    # Sin ejecución: solo obtener respuesta de texto
    name = agent["name"]
    system = agent["system"]
    hint = "\n\n(Always use fenced markdown code blocks for any code: ```lang\ncode\n```)"
    resp = _call_groq(system, task + hint, model="llama-3.3-70b-versatile")
    if resp:
        return f"[{name}]\n{resp}"
    for or_model in _OR_TEXT_MODELS:
        resp = _call_openrouter(system, task + hint, model=or_model)
        if resp:
            return f"[{name}]\n{resp}"
    return f"[{name}] No pude conectarme al LLM. Verifica GROQ_API_KEY u OPENROUTER_API_KEY."


# ── Web search para coding ───────────────────────────────────────────────────

_DOC_SEARCH_RE = re.compile(
    r"(?:c[oó]mo\s+(?:se\s+)?(?:implementa[r]?|usa[r]?|hago?|creo?|configuro?)|"
    r"qu[eé]\s+es|diferencia\s+entre|ejemplo\s+de|tutorial\s+de|"
    r"best\s+practice|buena\s+pr[aá]ctica|documentaci[oó]n|docs?\s+de)",
    re.IGNORECASE,
)

_CODE_KEYWORDS = re.compile(
    r"\b(?:fastapi|django|flask|react|vue|angular|nextjs|pytorch|tensorflow|"
    r"langchain|openai|anthropic|sqlalchemy|pydantic|celery|redis|postgres|"
    r"mongodb|docker|kubernetes|terraform|github\s*actions|pytest|asyncio|"
    r"aiohttp|httpx|requests|pandas|numpy|sklearn|huggingface|transformers|"
    r"n8n|supabase|prisma|graphql|grpc|websocket|jwt|oauth|stripe|twilio)\b",
    re.IGNORECASE,
)


def _fetch_url_text(url: str, max_chars: int = 3000) -> str:
    """Descarga una URL y extrae texto limpio sin dependencias extra."""
    import urllib.request, urllib.error, html, re as _re
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 Nova/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        # Quitar scripts, estilos, tags
        raw = _re.sub(r"<(script|style)[^>]*>.*?</\1>", "", raw, flags=_re.DOTALL | _re.IGNORECASE)
        raw = _re.sub(r"<[^>]+>", " ", raw)
        raw = html.unescape(raw)
        raw = _re.sub(r"\s{2,}", " ", raw).strip()
        return raw[:max_chars]
    except Exception as e:
        log.debug("[DocSearch] No pude fetchear %s: %s", url, e)
        return ""


def _search_and_fetch_docs(question: str, max_snippets: int = 2) -> str:
    """
    Busca en DDG y fetchea el texto de las URLs más relevantes.
    Retorna contexto de documentación listo para inyectar en el prompt del LLM.
    """
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        return ""

    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(question + " documentation example", max_results=4))
    except Exception as e:
        log.debug("[DocSearch] DDG falló: %s", e)
        return ""

    if not results:
        return ""

    # Priorizar URLs de docs oficiales
    _DOC_DOMAINS = ("docs.", "documentation.", "github.com", "readthedocs.io",
                    "pypi.org", "npmjs.com", "developer.", "learn.microsoft",
                    "developers.google", ".dev", "fastapi.tiangolo.com")
    results.sort(key=lambda r: (
        0 if any(d in r.get("href", "") for d in _DOC_DOMAINS) else 1
    ))

    context_parts = []
    fetched = 0
    for r in results:
        if fetched >= max_snippets:
            break
        url = r.get("href", "")
        title = r.get("title", url)
        snippet = r.get("body", "")

        # Primero el snippet de DDG (siempre disponible)
        part = f"### {title}\nURL: {url}\n{snippet}"

        # Intentar fetchear texto completo solo para URLs de docs
        if any(d in url for d in _DOC_DOMAINS):
            full = _fetch_url_text(url, max_chars=2000)
            if full:
                part += f"\n\nContenido:\n{full[:2000]}"

        context_parts.append(part)
        fetched += 1

    if not context_parts:
        return ""

    return "## Documentación real encontrada en la web:\n\n" + "\n\n---\n\n".join(context_parts)


def codear_con_docs(pregunta: str, agente_query: str = "backend architect") -> str:
    """
    Busca documentación real en la web y luego genera código con un especialista.
    Evita que el LLM invente APIs — siempre basado en docs reales.
    """
    _load_agents()
    agent = find_agent(agente_query) or find_agent("ai engineer") or find_agent("software architect")
    if not agent:
        return "No encontré agente disponible."

    log.info("[DocSearch] Buscando docs para: %s", pregunta[:60])
    docs_context = _search_and_fetch_docs(pregunta)

    if docs_context:
        task = (
            f"{docs_context}\n\n"
            f"---\n\n"
            f"Usando la documentación real de arriba, responde y genera código para:\n{pregunta}\n\n"
            f"IMPORTANTE: Solo usa APIs y patrones que aparezcan en la documentación provista. "
            f"No inventes imports ni funciones que no estén en los docs."
        )
        log.info("[DocSearch] Docs encontradas — pasando contexto al especialista")
    else:
        log.info("[DocSearch] Sin docs — invocando especialista directamente")
        task = pregunta

    return ejecutar_con_feedback(agent, task)


# ── Interfaz de skill ─────────────────────────────────────────────────────────

# Palabras que identifican una invocación de especialista
_TRIGGER_WORDS = [
    "actúa como", "actua como", "habla como", "consulta al",
    "pregunta al", "necesito un", "como experto en", "modo experto",
    "especialista en", "como si fueras", "como agente de",
]

# Mapeo de keywords de dominio → slug de agente preferido
_DOMAIN_MAP = {
    "firmware": "engineering-embedded-firmware-engineer",
    "esp32": "engineering-embedded-firmware-engineer",
    "stm32": "engineering-embedded-firmware-engineer",
    "freertos": "engineering-embedded-firmware-engineer",
    "drone": "engineering-embedded-firmware-engineer",
    "arquitecto": "engineering-software-architect",
    "architect": "engineering-software-architect",
    "sistema": "engineering-software-architect",
    "backend": "engineering-backend-architect",
    "api": "engineering-backend-architect",
    "ia": "engineering-ai-engineer",
    "ml": "engineering-ai-engineer",
    "machine learning": "engineering-ai-engineer",
    "datos": "engineering-data-engineer",
    "seguridad": "engineering-security-engineer",
    "security": "engineering-security-engineer",
    "devops": "engineering-devops-automator",
    "ui": "design-ui-designer",
    "ux": "design-ux-architect",
    "imagen": "design-image-prompt-engineer",
    "prompt": "design-image-prompt-engineer",
    "civil": "specialized-civil-engineer",
    "estructura": "specialized-civil-engineer",
    "workflow": "specialized-workflow-architect",
    "documento": "specialized-document-generator",
}


def skill_especialista(texto: str, auto_exec: bool = True) -> Optional[str]:
    """
    Detecta si el usuario quiere un agente especializado y lo invoca.

    Patrones:
    - "actúa como [agente] y [tarea]"
    - "consulta al [agente] sobre [tarea]"
    - "como experto en [dominio], [tarea]"
    - "/agente [nombre] [tarea]"
    """
    _load_agents()
    texto_lower = texto.lower()

    # Patrón explícito: "actúa como X y [tarea]" / "actúa como X, [tarea]" / "actúa como X: [tarea]"
    m = re.search(
        r"(?:actúa como|actua como|habla como|modo)\s+(?:el\s+|un\s+|una\s+)?(.+?)"
        r"(?:\s+y\s+|\s*[,:]\s+)(.+)$",
        texto_lower, re.IGNORECASE
    )
    if m:
        agent_query = m.group(1).strip()
        task = m.group(2).strip() or texto
        agent = find_agent(agent_query)
        if agent:
            return invoke_specialist(agent, task, auto_exec)

    # Patrón sin separador explícito: "actúa como [agente conocido] [tarea sin separador]"
    m2 = re.search(
        r"(?:actúa como|actua como|habla como)\s+(?:el\s+|un\s+|una\s+)?(.{5,40})",
        texto_lower, re.IGNORECASE
    )
    if m2:
        candidate = m2.group(1).strip()
        agent = find_agent(candidate)
        if agent:
            return invoke_specialist(agent, texto, auto_exec)

    # Patrón: "consulta al [agente] sobre/para [tarea]"
    m = re.search(
        r"(?:consulta(?:r)?|pregunta(?:r)?)\s+(?:al|a la|al)\s+(.+?)"
        r"\s+(?:sobre|para|acerca de|con respecto a)\s+(.+)$",
        texto_lower, re.IGNORECASE
    )
    if m:
        agent_query = m.group(1).strip()
        task = m.group(2).strip()
        agent = find_agent(agent_query)
        if agent:
            return invoke_specialist(agent, task, auto_exec)

    # Patrón: "como experto en [dominio], [tarea]"
    m = re.search(
        r"como\s+experto\s+en\s+(.+?)\s*,\s*(.+)$",
        texto_lower, re.IGNORECASE
    )
    if m:
        domain = m.group(1).strip()
        task = m.group(2).strip()
        agent = find_agent(domain)
        if agent:
            return invoke_specialist(agent, task, auto_exec)

    # Patrón: "/agente [nombre], [tarea]" o "/agente [nombre]: [tarea]"
    m = re.match(r"/?agente\s+(.+?)(?:\s*[,:]\s+)(.+)$", texto_lower)
    if not m:
        m_full = re.match(r"/?agente\s+(\w[\w\s-]{3,30})", texto_lower)
        if m_full:
            agent_query = m_full.group(1).strip()
            agent = find_agent(agent_query)
            if agent:
                return invoke_specialist(agent, texto, auto_exec)
    if m:
        agent_query = m.group(1).strip()
        task = m.group(2).strip() or texto
        agent = find_agent(agent_query)
        if agent:
            return invoke_specialist(agent, task, auto_exec)

    # Detección por dominio implícito — solo si hay trigger word
    if any(tw in texto_lower for tw in _TRIGGER_WORDS):
        for keyword, slug in _DOMAIN_MAP.items():
            if keyword in texto_lower and slug in _agent_cache:
                agent = _agent_cache[slug]
                return invoke_specialist(agent, texto, auto_exec)

    return None


# ── Extracción de contexto inteligente ───────────────────────────────────────

def _skeleton_python(text: str) -> str:
    """Extrae solo firmas de clase/función + docstrings de un archivo Python."""
    lines = text.splitlines()
    out = []
    in_docstring = False
    docstring_char = None
    skip_body = False
    indent_level = 0

    for line in lines:
        stripped = line.lstrip()
        # Detectar inicio de función/clase
        if re.match(r"^(class |def |async def )", stripped):
            out.append(line)
            skip_body = True
            in_docstring = False
            indent_level = len(line) - len(stripped)
            continue

        if skip_body:
            # Primera línea después de la firma: puede ser docstring o cuerpo
            if stripped.startswith('"""') or stripped.startswith("'''"):
                docstring_char = stripped[:3]
                in_docstring = True
                skip_body = False
                out.append(line)
                if stripped.count(docstring_char) >= 2 and len(stripped) > 6:
                    in_docstring = False  # docstring en una sola línea
                continue
            else:
                out.append(" " * (indent_level + 4) + "...")
                skip_body = False
                continue

        if in_docstring:
            out.append(line)
            if docstring_char and docstring_char in stripped and stripped != docstring_char:
                in_docstring = False
            continue

        # Imports y constantes del módulo (top-level)
        if not line.startswith(" ") and not line.startswith("\t"):
            if stripped.startswith(("import ", "from ", "#", "@", "_", "LOG", "log")):
                out.append(line)

    return "\n".join(out)


def _read_file_smart(path: Path, max_full: int = 150) -> str:
    """Lee un archivo completo si es pequeño, o extrae skeleton si es grande."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        line_count = text.count("\n")
        if line_count <= max_full:
            return text
        # Archivo grande: skeleton si es Python, primeras + últimas líneas si no
        if path.suffix == ".py":
            skeleton = _skeleton_python(text)
            return f"[SKELETON — {line_count} lines total]\n{skeleton}"
        else:
            lines = text.splitlines()
            head = "\n".join(lines[:60])
            tail = "\n".join(lines[-20:])
            return f"[TRUNCATED — {line_count} lines]\n{head}\n...\n{tail}"
    except Exception:
        return ""


def _build_project_context(base_dir: Path, tarea: dict) -> str:
    """
    Construye contexto inteligente para un agente específico.
    - Archivos mencionados explícitamente en la tarea → contenido completo
    - Archivos del mismo tipo que la tarea → skeleton
    - README siempre incluido si existe
    - Config/requirements → completo (suelen ser cortos)
    """
    archivos = sorted(
        (f for f in base_dir.rglob("*") if f.is_file() and ".git" not in f.parts),
        key=lambda f: f.stat().st_size  # los más pequeños primero
    )
    tarea_lower = (tarea.get("tarea", "") + " " + tarea.get("label", "")).lower()

    # Detectar archivos mencionados explícitamente
    mencionados = set()
    for f in archivos:
        if f.name.lower() in tarea_lower or f.stem.lower() in tarea_lower:
            mencionados.add(f)

    context_parts = []
    token_budget = 6000  # chars aproximados

    # 1. README siempre primero si existe
    for readme in ["README.md", "readme.md"]:
        rp = base_dir / readme
        if rp.exists():
            content = rp.read_text(encoding="utf-8", errors="replace")
            context_parts.append(f"\n=== {readme} ===\n{content[:1500]}\n")
            token_budget -= 1500
            break

    # 2. Config/requirements completos
    config_names = {"requirements.txt", "package.json", "pyproject.toml",
                    "setup.py", "config.json", ".env.example", "tsconfig.json"}
    for f in archivos:
        if f.name in config_names and token_budget > 0:
            txt = f.read_text(encoding="utf-8", errors="replace")
            snippet = txt[:800]
            context_parts.append(f"\n=== {f.relative_to(base_dir)} ===\n{snippet}\n")
            token_budget -= len(snippet)

    # 3. Archivos mencionados → contenido completo
    for f in mencionados:
        if token_budget <= 0:
            break
        txt = f.read_text(encoding="utf-8", errors="replace")
        rel = str(f.relative_to(base_dir))
        context_parts.append(f"\n=== {rel} [FULL] ===\n{txt}\n")
        token_budget -= len(txt)

    # 4. Resto de archivos → smart (skeleton o truncado)
    for f in archivos:
        if f in mencionados or token_budget <= 0:
            continue
        if f.name in config_names:
            continue
        rel = str(f.relative_to(base_dir))
        if any(rel.endswith(readme) for readme in ["README.md", "readme.md"]):
            continue
        smart = _read_file_smart(f)
        if smart:
            context_parts.append(f"\n=== {rel} ===\n{smart}\n")
            token_budget -= len(smart)

    return "".join(context_parts)


# ── Planificador de misiones ──────────────────────────────────────────────────

_MISSION_PLANNER_PROMPT = """You are a senior software architect analyzing a project to propose improvement missions.

Analyze the project structure and files, then propose 3-5 specific improvement missions.
For each mission, assign the best specialist agent from this list: {agent_list}

Respond ONLY with a JSON array, no prose:
[
  {{
    "label": "Short mission name",
    "agente": "exact agent name from the list",
    "tarea": "Detailed technical description of what to improve and how",
    "prioridad": "alta|media|baja",
    "archivos": ["list", "of", "affected", "files"]
  }}
]"""


def planear_mejoras_proyecto(base_dir: Path, foco: str = "") -> list[dict]:
    """
    Analiza el proyecto y propone misiones de mejora específicas.
    Devuelve lista de misiones que el usuario puede aprobar/ejecutar.

    foco: hint opcional del usuario ("mejorar UI", "optimizar rendimiento", etc.)
    """
    _load_agents()
    if not base_dir.exists():
        return []

    # Construir contexto del proyecto para el planificador
    archivos = [str(f.relative_to(base_dir)) for f in base_dir.rglob("*")
                if f.is_file() and ".git" not in f.parts]
    estructura = "\n".join(archivos[:40])

    # Leer contenido con skeleton inteligente
    contexto = ""
    budget = 8000
    for af in archivos[:15]:
        fp = base_dir / af
        smart = _read_file_smart(fp, max_full=80)
        if smart and budget > 0:
            rel = af
            contexto += f"\n=== {rel} ===\n{smart[:min(budget, 2000)]}\n"
            budget -= len(smart)

    # Lista de agentes disponibles para el planificador
    agents_sample = [
        "ai engineer", "code reviewer", "technical writer", "frontend developer",
        "backend architect", "embedded firmware engineer", "software architect",
        "mobile developer", "ui designer", "data engineer", "security engineer",
        "performance engineer", "database optimizer",
    ]

    system = _MISSION_PLANNER_PROMPT.format(agent_list=", ".join(agents_sample))
    user_prompt = (
        f"Project: {base_dir.name}\n"
        f"Files:\n{estructura}\n"
        f"Code context:\n{contexto}\n"
    )
    if foco:
        user_prompt += f"\nUser focus: {foco}\n"
    user_prompt += "\nPropose improvement missions as JSON array."

    resp = None
    for gm in ["llama-3.3-70b-versatile"]:
        resp = _call_groq(system, user_prompt, model=gm)
        if resp:
            break
    if not resp:
        for om in _OR_TEXT_MODELS:
            resp = _call_openrouter(system, user_prompt, model=om)
            if resp:
                break

    if not resp:
        return []

    # Extraer JSON de la respuesta
    try:
        # Buscar array JSON en la respuesta
        m = re.search(r"\[.*\]", resp, re.DOTALL)
        if m:
            misiones = json.loads(m.group(0))
            return misiones if isinstance(misiones, list) else []
    except Exception as e:
        log.warning(f"Error parsing mission JSON: {e}\nRaw: {resp[:300]}")
    return []


def formatear_misiones(misiones: list[dict]) -> str:
    """Formatea la lista de misiones para presentar al usuario."""
    if not misiones:
        return "No se pudieron generar misiones."
    lines = ["Misiones propuestas:\n"]
    for i, m in enumerate(misiones, 1):
        prioridad = m.get("prioridad", "media").upper()
        label = m.get("label", f"Misión {i}")
        agente = m.get("agente", "?")
        tarea = m.get("tarea", "")
        archivos = m.get("archivos", [])
        af_str = ", ".join(archivos) if archivos else "varios archivos"
        lines.append(
            f"  [{i}] {label} [{prioridad}]\n"
            f"      Agente: {agente}\n"
            f"      Tarea:  {tarea[:120]}{'...' if len(tarea) > 120 else ''}\n"
            f"      Archivos: {af_str}\n"
        )
    lines.append('Di "ejecutar misiones 1,2,3" o "ejecutar todas las misiones"')
    return "\n".join(lines)


# ── Multi-agente paralelo ─────────────────────────────────────────────────────

def mejorar_proyecto_paralelo(
    base_dir: Path,
    tareas: list[dict],   # [{"agente": str, "tarea": str, "label": str}]
    max_workers: int = 4,
) -> str:
    """
    Lanza varios agentes en paralelo con contexto inteligente por agente.
    Cada agente recibe: skeleton de todos los archivos + contenido completo
    de los archivos que va a modificar.
    """
    _load_agents()
    if not base_dir.exists():
        return f"Directorio no existe: {base_dir}"

    archivos = [str(f.relative_to(base_dir)) for f in base_dir.rglob("*")
                if f.is_file() and ".git" not in f.parts]
    estructura = "\n".join(archivos[:40])

    resultados: list[str] = []
    archivos_escritos: list[str] = []

    def _run_tarea(tarea: dict) -> tuple[str, list[str]]:
        label = tarea.get("label", tarea["agente"])
        agent = find_agent(tarea["agente"])
        if not agent:
            return f"[{label}] Agente '{tarea['agente']}' no encontrado", []

        # Contexto inteligente: skeleton + archivos relevantes completos
        contexto_archivos = _build_project_context(base_dir, tarea)

        system = agent["system"] + _PROJECT_SYSTEM_SUFFIX
        prompt = (
            f"Project: {base_dir.name}\n"
            f"File structure:\n{estructura}\n"
            f"{contexto_archivos}\n"
            f"Your mission ({label}): {tarea['tarea']}\n"
            f"Output ONLY the files you create or modify using === FILE: path === format."
        )

        resp = None
        for gm in ["llama-3.3-70b-versatile", "llama-3.1-70b-versatile"]:
            resp = _call_groq(system, prompt, model=gm)
            if resp:
                break
        if not resp:
            for om in _OR_TEXT_MODELS:
                resp = _call_openrouter(system, prompt, model=om)
                if resp:
                    break

        if not resp:
            return f"[{label}] Sin respuesta del LLM", []

        files = _parse_file_blocks(resp)
        if not files:
            return f"[{label}] No generó archivos estructurados", []

        created = _write_project_files(files, base_dir)
        return f"[{label}] ✓ {len(created)} archivo(s): {', '.join(created)}", created

    # Ejecutar en paralelo
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_run_tarea, t): t for t in tareas}
        for future in as_completed(futures):
            msg, files = future.result()
            resultados.append(msg)
            archivos_escritos.extend(files)

    # git commit con todo lo generado
    if archivos_escritos:
        import subprocess
        subprocess.run(["git", "add", "."], cwd=base_dir, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", f"feat: multi-agent improvements ({len(tareas)} agents)"],
            cwd=base_dir, capture_output=True,
            env={**os.environ, "GIT_AUTHOR_NAME": "Nova", "GIT_AUTHOR_EMAIL": "nova@nova.local",
                 "GIT_COMMITTER_NAME": "Nova", "GIT_COMMITTER_EMAIL": "nova@nova.local"}
        )

    return (
        f"Multi-agente completado en {base_dir.name}:\n"
        + "\n".join(resultados)
    )


def list_agents_formatted(category: Optional[str] = None) -> str:
    """Devuelve lista de agentes en formato legible para Nova."""
    agents = list_agents(category)
    if not agents:
        return "No hay agentes disponibles."
    cats: dict[str, list] = {}
    for a in agents:
        cats.setdefault(a["category"], []).append(a)
    lines = ["Agentes especializados disponibles:"]
    for cat, group in sorted(cats.items()):
        lines.append(f"\n**{cat.upper()}**")
        for a in group:
            desc = a["description"][:80] + "..." if len(a["description"]) > 80 else a["description"]
            lines.append(f"  • {a['name']}: {desc}")
    return "\n".join(lines)
