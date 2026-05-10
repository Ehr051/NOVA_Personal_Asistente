"""nova_skill_bridge.py — Puente entre formatos externos de tools/skills y plugins de Nova.

Convierte schemas de OpenAI/Anthropic, callables Python o skills tipo Hermes en
plugins instalables (`nova_plugin_*.py`) compatibles con `nova_plugin_loader.py`.

Uso CLI:
    python -m nova.tools.nova_skill_bridge install <archivo.json|.py|URL>
    python -m nova.tools.nova_skill_bridge list
    python -m nova.tools.nova_skill_bridge remove <nombre>

Solo usa stdlib.
"""

from __future__ import annotations

import ast
import inspect
import json
import re
import shutil
import sys
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any, Callable, Iterable

# -------------------------------------------------------------------------
# Configuración
# -------------------------------------------------------------------------

DEFAULT_PLUGIN_DIR = Path.home() / ".nova" / "plugins"

# Palabras clave para auto-generar INTENTS desde la descripción
_KEYWORD_HINTS: dict[str, list[str]] = {
    "weather": ["clima", "tiempo", "temperatura"],
    "clima": ["clima", "tiempo", "temperatura"],
    "tiempo": ["clima", "tiempo", "temperatura"],
    "search": ["buscar", "busca", "búsqueda"],
    "buscar": ["buscar", "busca", "búsqueda"],
    "email": ["email", "mail", "correo"],
    "mail": ["email", "mail", "correo"],
    "calendar": ["calendario", "agenda", "evento"],
    "calendario": ["calendario", "agenda", "evento"],
    "translate": ["traducir", "traduce", "traducción"],
    "traducir": ["traducir", "traduce", "traducción"],
    "image": ["imagen", "foto", "picture"],
    "imagen": ["imagen", "foto", "picture"],
    "music": ["música", "canción", "reproducir"],
    "música": ["música", "canción", "reproducir"],
    "note": ["nota", "anotar", "apunte"],
    "nota": ["nota", "anotar", "apunte"],
    "task": ["tarea", "task", "todo"],
    "tarea": ["tarea", "task", "todo"],
    "remind": ["recordar", "recordatorio", "recuérdame"],
    "recordar": ["recordar", "recordatorio", "recuérdame"],
    "file": ["archivo", "fichero", "file"],
    "archivo": ["archivo", "fichero", "file"],
    "code": ["código", "code", "programa"],
    "código": ["código", "code", "programa"],
    "git": ["git", "repositorio", "repo"],
    "deploy": ["deploy", "deployar", "despliegue"],
    "database": ["base de datos", "db", "database"],
    "query": ["consulta", "query", "buscar"],
}

# Mapeo de tipos JSON-schema → arg_type de Nova
_TYPE_MAP = {
    "string": "text",
    "integer": "text",
    "number": "text",
    "boolean": "text",
    "array": "text",
    "object": "text",
}


# -------------------------------------------------------------------------
# Helpers internos
# -------------------------------------------------------------------------

def _safe_name(name: str) -> str:
    """Sanitiza un nombre para usarlo como identificador Python/archivo."""
    s = re.sub(r"[^a-zA-Z0-9_]", "_", name.strip())
    if s and s[0].isdigit():
        s = "_" + s
    return s or "skill"


def _gen_intents_from_description(name: str, description: str) -> list[tuple[str, str]]:
    """Genera lista de (regex, comentario) desde nombre + descripción."""
    text = f"{name} {description}".lower()
    found: list[str] = []
    for key, words in _KEYWORD_HINTS.items():
        if key in text:
            for w in words:
                if w not in found:
                    found.append(w)
            if len(found) >= 6:
                break

    intents: list[tuple[str, str]] = []
    if found:
        group = "|".join(re.escape(w) for w in found[:6])
        intents.append((rf"(?:{group})\s+(?:en\s+|de\s+|sobre\s+|para\s+)?(.+)", "auto-keywords"))
        intents.append((rf"(?:qué|cómo|como)\s+(?:{group})\s+(.+)", "auto-question"))

    # Fallback: usar el nombre del tool como trigger
    safe = name.replace("_", " ")
    intents.append((rf"(?:{re.escape(safe)})\s+(.+)", "auto-name"))
    return intents


def _params_from_schema(schema: dict) -> list[tuple[str, str, bool]]:
    """Devuelve lista de (param_name, json_type, required) del JSON-schema."""
    params: list[tuple[str, str, bool]] = []
    if not isinstance(schema, dict):
        return params
    props = schema.get("properties", {}) or {}
    required = set(schema.get("required", []) or [])
    for pname, pspec in props.items():
        ptype = (pspec or {}).get("type", "string") if isinstance(pspec, dict) else "string"
        params.append((pname, ptype, pname in required))
    return params


def _python_default_for(ptype: str) -> str:
    return {
        "integer": "0",
        "number": "0.0",
        "boolean": "False",
        "array": "None",
        "object": "None",
    }.get(ptype, '""')


def _python_annotation_for(ptype: str) -> str:
    return {
        "integer": "int",
        "number": "float",
        "boolean": "bool",
        "array": "list",
        "object": "dict",
        "string": "str",
    }.get(ptype, "str")


def _format_intents_block(handler_fn: str, intents: Iterable[tuple[str, str]]) -> str:
    lines = ["INTENTS = ["]
    for pattern, comment in intents:
        lines.append(f"    (r{pattern!r}, {handler_fn}, 1),  # {comment}")
    lines.append("]")
    return "\n".join(lines)


def _render_handler_with_url(fn_name: str, tool_name: str, params: list[tuple[str, str, bool]]) -> str:
    """Genera un handler que hace POST a un HANDLER_URL configurable."""
    sig_parts = []
    for pname, ptype, required in params:
        ann = _python_annotation_for(ptype)
        if required:
            sig_parts.append(f"{pname}: {ann} = {_python_default_for(ptype)}")
        else:
            sig_parts.append(f"{pname}: {ann} = {_python_default_for(ptype)}")
    sig = ", ".join(sig_parts) if sig_parts else ""

    body_kwargs = "{" + ", ".join(f'"{p}": {p}' for p, _, _ in params) + "}"
    repr_args = ", ".join(f"{p}={{{p}!r}}" for p, _, _ in params) if params else ""

    return f'''def {fn_name}({sig}) -> str:
    """Auto-generated handler for {tool_name}.

    Configurá HANDLER_URL para hacer POST a tu API, o reemplazá esta función.
    """
    HANDLER_URL = None  # ej: "https://tu-api.com/{tool_name}"
    if HANDLER_URL:
        try:
            payload = _json.dumps({body_kwargs}).encode("utf-8")
            req = urllib.request.Request(
                HANDLER_URL,
                data=payload,
                method="POST",
                headers={{"Content-Type": "application/json"}},
            )
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.read().decode("utf-8", errors="replace")
        except Exception as e:
            return f"Error llamando al handler {tool_name}: {{e}}"
    return f"[{tool_name}] {repr_args} — configurá HANDLER_URL o implementá el handler"
'''


def _render_handler_with_url_configured(fn_name: str, tool_name: str, params: list[tuple[str, str, bool]], handler_url: str) -> str:
    sig_parts = []
    for pname, ptype, _ in params:
        ann = _python_annotation_for(ptype)
        sig_parts.append(f"{pname}: {ann} = {_python_default_for(ptype)}")
    sig = ", ".join(sig_parts) if sig_parts else ""
    body_kwargs = "{" + ", ".join(f'"{p}": {p}' for p, _, _ in params) + "}"

    return f'''def {fn_name}({sig}) -> str:
    """Auto-generated handler for {tool_name} (POST a {handler_url})."""
    HANDLER_URL = {handler_url!r}
    try:
        payload = _json.dumps({body_kwargs}).encode("utf-8")
        req = urllib.request.Request(
            HANDLER_URL,
            data=payload,
            method="POST",
            headers={{"Content-Type": "application/json"}},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception as e:
        return f"Error llamando al handler {tool_name}: {{e}}"
'''


# -------------------------------------------------------------------------
# 1. from_openai_schema
# -------------------------------------------------------------------------

def from_openai_schema(schema: dict | list, handler_url: str | None = None) -> str:
    """Genera el contenido de un plugin de Nova desde un schema OpenAI/Anthropic.

    Soporta:
      - Un único schema con `{"type": "function", "function": {...}}`
      - Un único schema "plano" `{"name": ..., "description": ..., "parameters": {...}}`
      - Una lista de schemas → genera un plugin único con todas las tools
    """
    schemas = schema if isinstance(schema, list) else [schema]
    functions: list[dict] = []
    for sch in schemas:
        if not isinstance(sch, dict):
            continue
        if sch.get("type") == "function" and "function" in sch:
            functions.append(sch["function"])
        elif "name" in sch:
            functions.append(sch)
        elif "function" in sch and isinstance(sch["function"], dict):
            functions.append(sch["function"])

    if not functions:
        raise ValueError("No se encontró ninguna function definition válida en el schema")

    plugin_name = _safe_name(functions[0].get("name", "skill"))
    today = date.today().isoformat()

    header = f'''# nova_plugin_{plugin_name}.py — Auto-generado por nova_skill_bridge
# Schema: OpenAI · {", ".join(f.get("name", "?") for f in functions)}
# Instalado: {today}

from __future__ import annotations

import json as _json
import urllib.request

PLUGIN_META = {{
    "name": {plugin_name!r},
    "version": "1.0.0",
    "description": {(functions[0].get("description") or plugin_name)!r},
    "author": "bridge/openai",
    "schema_format": "openai",
}}
'''

    handlers_src: list[str] = []
    intents_entries: list[tuple[str, str]] = []
    catalog_entries: list[tuple[str, str, str]] = []  # (tool_name, description, fn_name)

    for fn in functions:
        tool_name = fn.get("name", "tool")
        safe = _safe_name(tool_name)
        fn_name = f"_handler_{safe}"
        description = fn.get("description", "") or f"Tool {tool_name}"
        params = _params_from_schema(fn.get("parameters", {}) or {})

        if handler_url:
            handlers_src.append(_render_handler_with_url_configured(fn_name, tool_name, params, handler_url))
        else:
            handlers_src.append(_render_handler_with_url(fn_name, tool_name, params))

        # Generar intents para esta tool
        gen_intents = _gen_intents_from_description(tool_name, description)
        for pattern, comment in gen_intents:
            intents_entries.append((pattern, f"{comment} → {tool_name}"))
            # Almacenamos el handler como string para inyección formateada después
        # Almacenar info para el TOOL_CATALOG
        catalog_entries.append((tool_name, description, fn_name))

    # Render INTENTS — necesitamos atar cada intent a su handler. Lo rehacemos.
    intents_lines = ["INTENTS = ["]
    for fn in functions:
        tool_name = fn.get("name", "tool")
        safe = _safe_name(tool_name)
        fn_name = f"_handler_{safe}"
        description = fn.get("description", "") or f"Tool {tool_name}"
        for pattern, comment in _gen_intents_from_description(tool_name, description):
            intents_lines.append(f"    (r{pattern!r}, {fn_name}, 1),  # {comment}")
    intents_lines.append("]")
    intents_block = "\n".join(intents_lines)

    catalog_lines = ["TOOL_CATALOG = {"]
    for tool_name, description, fn_name in catalog_entries:
        catalog_lines.append(f"    {tool_name!r}: ({description!r}, {fn_name}, \"text\"),")
    catalog_lines.append("}")
    catalog_block = "\n".join(catalog_lines)

    register_block = '''
def register(skills_module):
    """Hook opcional llamado por nova_plugin_loader al cargar el plugin."""
    return True
'''

    parts = [header, "\n".join(handlers_src), intents_block, catalog_block, register_block]
    return "\n\n".join(parts).rstrip() + "\n"


# -------------------------------------------------------------------------
# 2. from_callable
# -------------------------------------------------------------------------

def from_callable(fn: Callable, name: str | None = None, description: str | None = None) -> str:
    """Envuelve un callable Python como plugin de Nova."""
    tool_name = name or getattr(fn, "__name__", "skill")
    safe = _safe_name(tool_name)
    desc = description or (inspect.getdoc(fn) or "").strip().split("\n")[0] or f"Tool {tool_name}"

    sig = inspect.signature(fn)
    params: list[tuple[str, str, bool]] = []
    for pname, p in sig.parameters.items():
        if pname == "self":
            continue
        ptype = "string"
        ann = p.annotation
        if ann is int:
            ptype = "integer"
        elif ann is float:
            ptype = "number"
        elif ann is bool:
            ptype = "boolean"
        elif ann is list:
            ptype = "array"
        elif ann is dict:
            ptype = "object"
        required = p.default is inspect.Parameter.empty
        params.append((pname, ptype, required))

    # Detectar arg_type apropiado para el primer parámetro
    first_arg_type = "text"
    if params:
        pname0 = params[0][0].lower()
        if "location" in pname0 or "place" in pname0 or "lugar" in pname0 or "ciudad" in pname0:
            first_arg_type = "location"
        elif "filename" in pname0 or "path" in pname0 or "archivo" in pname0:
            first_arg_type = "text"

    today = date.today().isoformat()
    fn_handler = f"_handler_{safe}"

    sig_parts = []
    call_args = []
    for pname, ptype, required in params:
        ann = _python_annotation_for(ptype)
        sig_parts.append(f"{pname}: {ann} = {_python_default_for(ptype)}")
        call_args.append(pname)
    sig_str = ", ".join(sig_parts)
    call_str = ", ".join(f"{a}={a}" for a in call_args)

    # Ojo: no podemos serializar el callable original. Generamos un stub que
    # avisa que hay que importar la función real. Si el llamador querría
    # ejecutar la función real necesita un handler URL o reemplazar el cuerpo.
    repr_args = ", ".join(f"{a}={{{a}!r}}" for a in call_args) if call_args else ""

    handler_src = f'''def {fn_handler}({sig_str}) -> str:
    """Wrapper auto-generado para {tool_name}.

    El callable original no se serializa: implementá la llamada real aquí
    (importá la función desde su módulo y llamala con los argumentos).
    """
    try:
        # TODO: importá la función original y llamala. Ejemplo:
        # from your_module import {tool_name}
        # result = {tool_name}({call_str})
        # return str(result)
        return f"[{tool_name}] {repr_args} — implementá el wrapper"
    except Exception as e:
        return f"Error en {tool_name}: {{e}}"
'''

    intents_lines = ["INTENTS = ["]
    for pattern, comment in _gen_intents_from_description(tool_name, desc):
        intents_lines.append(f"    (r{pattern!r}, {fn_handler}, 1),  # {comment}")
    intents_lines.append("]")

    content = f'''# nova_plugin_{safe}.py — Auto-generado por nova_skill_bridge
# Source: callable · {tool_name}
# Instalado: {today}

from __future__ import annotations

PLUGIN_META = {{
    "name": {safe!r},
    "version": "1.0.0",
    "description": {desc!r},
    "author": "bridge/callable",
    "schema_format": "callable",
}}


{handler_src}

{chr(10).join(intents_lines)}

TOOL_CATALOG = {{
    {tool_name!r}: ({desc!r}, {fn_handler}, {first_arg_type!r}),
}}


def register(skills_module):
    return True
'''
    return content


# -------------------------------------------------------------------------
# 3. install_plugin
# -------------------------------------------------------------------------

def install_plugin(content: str, plugin_name: str, target_dir: Path | None = None) -> Path:
    """Escribe el plugin en el directorio de plugins de Nova."""
    target = Path(target_dir) if target_dir else DEFAULT_PLUGIN_DIR
    target.mkdir(parents=True, exist_ok=True)
    safe = _safe_name(plugin_name)
    path = target / f"nova_plugin_{safe}.py"
    path.write_text(content, encoding="utf-8")
    return path


# -------------------------------------------------------------------------
# 4. install_from_file
# -------------------------------------------------------------------------

def _detect_hermes_format(data: Any) -> bool:
    """Heurística: ¿es un formato Hermes?"""
    if isinstance(data, dict):
        return "skills" in data or "hermes" in data or data.get("format") == "hermes"
    return False


def _normalize_schemas(data: Any) -> list[dict]:
    """Normaliza distintos formatos JSON a una lista de schemas tipo OpenAI."""
    if isinstance(data, list):
        return [d for d in data if isinstance(d, dict)]
    if isinstance(data, dict):
        if "tools" in data and isinstance(data["tools"], list):
            return data["tools"]
        if "functions" in data and isinstance(data["functions"], list):
            return data["functions"]
        if "skills" in data and isinstance(data["skills"], list):
            return data["skills"]
        if "name" in data or "function" in data:
            return [data]
    return []


def install_from_file(path: str | Path) -> str:
    """Instala un plugin desde un archivo .json o .py."""
    p = Path(path).expanduser()
    if not p.exists():
        return f"Archivo no encontrado: {p}"

    suffix = p.suffix.lower()
    if suffix == ".json":
        try:
            raw = p.read_text(encoding="utf-8")
            data = json.loads(raw)
        except Exception as e:
            return f"Error leyendo JSON: {e}"

        if _detect_hermes_format(data):
            schemas = _normalize_schemas(data)
        else:
            schemas = _normalize_schemas(data)

        if not schemas:
            return f"No se encontraron schemas en {p}"

        try:
            content = from_openai_schema(schemas)
        except Exception as e:
            return f"Error generando plugin: {e}"

        first_name = "skill"
        if isinstance(schemas[0], dict):
            f0 = schemas[0].get("function", schemas[0])
            first_name = f0.get("name", "skill") if isinstance(f0, dict) else "skill"

        installed = install_plugin(content, first_name)
        return f"Instalado: {installed}"

    if suffix == ".py":
        try:
            text = p.read_text(encoding="utf-8")
        except Exception as e:
            return f"Error leyendo .py: {e}"

        if "PLUGIN_META" not in text:
            return f"El archivo {p} no parece un plugin Nova (falta PLUGIN_META)"

        # Intentar inferir el nombre del plugin
        name_match = re.search(r'"name"\s*:\s*"([^"]+)"', text)
        plugin_name = name_match.group(1) if name_match else p.stem.replace("nova_plugin_", "")
        installed = install_plugin(text, plugin_name)
        return f"Instalado: {installed}"

    return f"Extensión no soportada: {suffix}"


# -------------------------------------------------------------------------
# 5. install_from_url
# -------------------------------------------------------------------------

def install_from_url(url: str) -> str:
    """Descarga el archivo (JSON o Python) y lo instala."""
    try:
        # Soporte para GitHub: convertir blob/ → raw/
        if "github.com" in url and "/blob/" in url:
            url = url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")

        req = urllib.request.Request(url, headers={"User-Agent": "nova-skill-bridge/1.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            data = r.read()
    except Exception as e:
        return f"Error descargando {url}: {e}"

    # Detectar extensión por URL o por contenido
    suffix = ".json" if url.lower().endswith(".json") else (".py" if url.lower().endswith(".py") else None)
    if suffix is None:
        try:
            json.loads(data.decode("utf-8"))
            suffix = ".json"
        except Exception:
            suffix = ".py"

    tmp = DEFAULT_PLUGIN_DIR / "_tmp_download"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp_file = tmp.with_suffix(suffix)
    tmp_file.write_bytes(data)
    try:
        return install_from_file(tmp_file)
    finally:
        try:
            tmp_file.unlink()
        except Exception:
            pass


# -------------------------------------------------------------------------
# 6. list_installed
# -------------------------------------------------------------------------

def _extract_plugin_meta(text: str) -> dict:
    """Extrae el dict PLUGIN_META de un archivo de plugin (sin ejecutarlo)."""
    try:
        tree = ast.parse(text)
    except Exception:
        return {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "PLUGIN_META":
                    try:
                        return ast.literal_eval(node.value)
                    except Exception:
                        return {}
    return {}


def list_installed() -> list[dict]:
    """Lista todos los plugins instalados con su metadata."""
    out: list[dict] = []
    if not DEFAULT_PLUGIN_DIR.exists():
        return out
    for p in sorted(DEFAULT_PLUGIN_DIR.glob("nova_plugin_*.py")):
        try:
            text = p.read_text(encoding="utf-8")
        except Exception:
            continue
        meta = _extract_plugin_meta(text)
        if not meta:
            meta = {"name": p.stem.replace("nova_plugin_", "")}
        meta["__path__"] = str(p)
        out.append(meta)
    return out


# -------------------------------------------------------------------------
# 7. remove_plugin
# -------------------------------------------------------------------------

def remove_plugin(name: str) -> bool:
    """Elimina un plugin por nombre."""
    safe = _safe_name(name)
    candidates = [
        DEFAULT_PLUGIN_DIR / f"nova_plugin_{safe}.py",
        DEFAULT_PLUGIN_DIR / f"{safe}.py",
        DEFAULT_PLUGIN_DIR / f"nova_plugin_{name}.py",
    ]
    removed = False
    for c in candidates:
        if c.exists():
            try:
                c.unlink()
                removed = True
            except Exception:
                pass
    return removed


# -------------------------------------------------------------------------
# 8. from_hermes_skill
# -------------------------------------------------------------------------

def from_hermes_skill(skill_path: str | Path) -> str:
    """Lee un skill estilo Hermes (módulo Python con funciones públicas) y genera un plugin."""
    p = Path(skill_path).expanduser()
    if not p.exists():
        raise FileNotFoundError(f"Skill no encontrado: {p}")
    text = p.read_text(encoding="utf-8")

    try:
        tree = ast.parse(text)
    except SyntaxError as e:
        raise ValueError(f"No es un archivo Python válido: {e}") from e

    public_funcs: list[tuple[str, str, list[tuple[str, str, bool]]]] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("_"):
                continue
            doc = ast.get_docstring(node) or f"Función {node.name}"
            doc_first = doc.strip().split("\n")[0]
            params: list[tuple[str, str, bool]] = []
            args = node.args
            defaults = list(args.defaults)
            n_args = len(args.args)
            n_def = len(defaults)
            for i, a in enumerate(args.args):
                if a.arg == "self":
                    continue
                # required si no tiene default
                required = i < (n_args - n_def)
                ptype = "string"
                if a.annotation is not None:
                    try:
                        ann_src = ast.unparse(a.annotation) if hasattr(ast, "unparse") else ""
                    except Exception:
                        ann_src = ""
                    if ann_src in ("int",):
                        ptype = "integer"
                    elif ann_src in ("float",):
                        ptype = "number"
                    elif ann_src in ("bool",):
                        ptype = "boolean"
                    elif ann_src in ("list", "List"):
                        ptype = "array"
                    elif ann_src in ("dict", "Dict"):
                        ptype = "object"
                params.append((a.arg, ptype, required))
            public_funcs.append((node.name, doc_first, params))

    if not public_funcs:
        raise ValueError(f"No se encontraron funciones públicas en {p}")

    # Construir schemas tipo OpenAI y reusar from_openai_schema
    schemas = []
    for fname, doc, params in public_funcs:
        properties = {pname: {"type": ptype} for pname, ptype, _ in params}
        required = [pname for pname, _, req in params if req]
        schemas.append({
            "name": fname,
            "description": doc,
            "parameters": {"type": "object", "properties": properties, "required": required},
        })

    content = from_openai_schema(schemas)
    # Reemplazar el author para indicar el origen
    content = content.replace('"author": "bridge/openai"', '"author": "bridge/hermes"')
    content = content.replace('"schema_format": "openai"', '"schema_format": "hermes"')
    return content


# -------------------------------------------------------------------------
# CLI
# -------------------------------------------------------------------------

def _main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Nova Skill Bridge")
    sub = parser.add_subparsers(dest="cmd")

    p_install = sub.add_parser("install", help="Instalar skill desde archivo o URL")
    p_install.add_argument("source", help="Archivo .json/.py o URL")

    sub.add_parser("list", help="Listar skills instalados")

    p_remove = sub.add_parser("remove", help="Remover skill instalado")
    p_remove.add_argument("name", help="Nombre del skill")

    args = parser.parse_args()

    if args.cmd == "install":
        if args.source.startswith(("http://", "https://")):
            print(install_from_url(args.source))
        else:
            print(install_from_file(args.source))
        return 0

    if args.cmd == "list":
        plugins = list_installed()
        if not plugins:
            print("(sin plugins instalados)")
            return 0
        for pl in plugins:
            print(f"  {pl.get('name','?')} v{pl.get('version','?')} — {pl.get('description','')}")
        return 0

    if args.cmd == "remove":
        print("Removido" if remove_plugin(args.name) else "No encontrado")
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(_main())
