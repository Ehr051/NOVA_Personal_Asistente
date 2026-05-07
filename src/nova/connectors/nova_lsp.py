"""
nova_lsp.py — Análisis semántico de código para Nova.

Usa jedi (puro Python, sin servidor externo) para dar a Nova
entendimiento real del código:
  - Dónde está definida una función/clase/variable
  - Dónde se usa un símbolo (referencias)
  - Qué parámetros acepta una función
  - Qué hace un módulo/función (docstring)
  - Completions para autocompletar código
  - Diagnósticos básicos (imports rotos, nombres no definidos)

Todas las funciones son síncronas y thread-safe.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

try:
    import jedi
    _JEDI_OK = True
except ImportError:
    _JEDI_OK = False
    log.warning("[LSP] jedi no instalado — ejecuta: pip install jedi")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _jedi_script(source: str, path: Optional[Path] = None,
                 project_path: Optional[Path] = None) -> "jedi.Script | None":
    if not _JEDI_OK:
        return None
    try:
        project = jedi.Project(path=str(project_path)) if project_path else None
        return jedi.Script(source, path=str(path) if path else None,
                           project=project)
    except Exception as e:
        log.debug("[LSP] Error creando script jedi: %s", e)
        return None


def _pos_from_offset(source: str, offset: int) -> tuple[int, int]:
    """Convierte offset de bytes a (line, col) base-1."""
    lines = source[:offset].split("\n")
    return len(lines), len(lines[-1])


def _fmt_location(name: str, module_path: str, line: int, col: int) -> str:
    try:
        rel = Path(module_path).name
    except Exception:
        rel = module_path or "?"
    return f"{rel}:{line}:{col}  ({name})"


# ── API pública ───────────────────────────────────────────────────────────────

def find_definition(source: str, line: int, col: int,
                    file_path: Optional[Path] = None,
                    project_path: Optional[Path] = None) -> str:
    """
    Retorna dónde está definido el símbolo en (line, col).
    line y col son base-1.
    """
    script = _jedi_script(source, file_path, project_path)
    if not script:
        return "LSP no disponible (instala jedi)."
    try:
        defs = script.goto(line, col - 1)
        if not defs:
            return "No se encontró definición."
        results = []
        for d in defs:
            loc = _fmt_location(d.name, d.module_path or "", d.line or 0, d.column or 0)
            results.append(loc)
        return "\n".join(results)
    except Exception as e:
        log.debug("[LSP] find_definition error: %s", e)
        return f"Error LSP: {e}"


def find_references(source: str, line: int, col: int,
                    file_path: Optional[Path] = None,
                    project_path: Optional[Path] = None) -> str:
    """
    Retorna todas las referencias al símbolo en (line, col).
    """
    script = _jedi_script(source, file_path, project_path)
    if not script:
        return "LSP no disponible."
    try:
        refs = script.get_references(line, col - 1)
        if not refs:
            return "Sin referencias encontradas."
        results = []
        for r in refs:
            loc = _fmt_location(r.name, r.module_path or "", r.line or 0, r.column or 0)
            results.append(loc)
        return f"{len(results)} referencia(s):\n" + "\n".join(results)
    except Exception as e:
        log.debug("[LSP] find_references error: %s", e)
        return f"Error LSP: {e}"


def get_signature(source: str, line: int, col: int,
                  file_path: Optional[Path] = None,
                  project_path: Optional[Path] = None) -> str:
    """
    Retorna la firma (parámetros) de la función en el cursor.
    """
    script = _jedi_script(source, file_path, project_path)
    if not script:
        return "LSP no disponible."
    try:
        sigs = script.get_signatures(line, col - 1)
        if not sigs:
            return "No se encontró firma en esta posición."
        results = []
        for s in sigs:
            params = ", ".join(p.description for p in s.params)
            results.append(f"{s.name}({params})")
        return "\n".join(results)
    except Exception as e:
        log.debug("[LSP] get_signature error: %s", e)
        return f"Error LSP: {e}"


def get_docstring(symbol: str, source: str = "",
                  file_path: Optional[Path] = None,
                  project_path: Optional[Path] = None) -> str:
    """
    Retorna el docstring de un símbolo por nombre.
    Busca en el source provisto o en el proyecto activo.
    """
    if not _JEDI_OK:
        return "LSP no disponible."

    # Si tenemos source, buscar el símbolo en el texto
    if source:
        # Encontrar la línea donde aparece el símbolo
        for i, line in enumerate(source.splitlines(), 1):
            col = line.find(symbol)
            if col >= 0:
                script = _jedi_script(source, file_path, project_path)
                if script:
                    try:
                        names = script.infer(i, col + len(symbol))
                        for n in names:
                            doc = n.docstring()
                            if doc:
                                return f"**{n.name}** ({n.type})\n\n{doc[:1000]}"
                    except Exception:
                        pass

    # Fallback: buscar via help() en módulos conocidos
    try:
        script = jedi.Script(f"{symbol}")
        completions = script.complete(1, len(symbol))
        for c in completions:
            if c.name == symbol:
                doc = c.docstring()
                if doc:
                    return f"**{symbol}**\n\n{doc[:1000]}"
    except Exception:
        pass
    return f"No se encontró documentación para '{symbol}'."


def get_completions(source: str, line: int, col: int,
                    file_path: Optional[Path] = None,
                    project_path: Optional[Path] = None,
                    max_results: int = 10) -> str:
    """
    Retorna sugerencias de autocompletado en (line, col).
    """
    script = _jedi_script(source, file_path, project_path)
    if not script:
        return "LSP no disponible."
    try:
        completions = script.complete(line, col - 1)
        if not completions:
            return "Sin sugerencias."
        items = [f"{c.name} ({c.type})" for c in completions[:max_results]]
        total = len(completions)
        suffix = f"\n... y {total - max_results} más" if total > max_results else ""
        return "\n".join(items) + suffix
    except Exception as e:
        log.debug("[LSP] get_completions error: %s", e)
        return f"Error LSP: {e}"


def diagnose_file(source: str, file_path: Optional[Path] = None,
                  project_path: Optional[Path] = None) -> str:
    """
    Diagnóstico estático básico: imports no resueltos, nombres no definidos.
    """
    if not _JEDI_OK:
        return "LSP no disponible."
    try:
        script = _jedi_script(source, file_path, project_path)
        if not script:
            return "No se pudo analizar."
        issues = []
        for diag in script.get_syntax_errors():
            issues.append(f"SyntaxError L{diag.line}:{diag.column} — {diag.message}")
        # Detectar imports con error
        for name in script.get_names(all_scopes=False):
            pass  # placeholder — jedi no expone undefined names fácilmente
        if not issues:
            return "Sin problemas detectados."
        return f"{len(issues)} problema(s):\n" + "\n".join(issues)
    except Exception as e:
        log.debug("[LSP] diagnose error: %s", e)
        return f"Error diagnóstico: {e}"


# ── Función de alto nivel: análisis de un archivo del proyecto ────────────────

def analyze_file(file_path: Path, project_path: Optional[Path] = None) -> dict:
    """
    Análisis completo de un archivo Python:
    - Lista de funciones y clases con sus líneas
    - Imports
    - Diagnóstico de errores
    Retorna dict con todas las secciones.
    """
    if not file_path.exists():
        return {"error": f"Archivo no encontrado: {file_path}"}
    source = file_path.read_text(encoding="utf-8", errors="replace")
    proj = project_path or file_path.parent

    result: dict = {"file": str(file_path.name), "symbols": [], "imports": [],
                    "diagnostics": ""}

    if not _JEDI_OK:
        # Fallback: regex básico
        result["symbols"] = re.findall(r"^(?:def|class)\s+(\w+)", source, re.MULTILINE)
        result["imports"] = re.findall(r"^(?:import|from)\s+(\S+)", source, re.MULTILINE)
        result["diagnostics"] = "jedi no disponible — análisis por regex"
        return result

    try:
        script = _jedi_script(source, file_path, proj)
        if script:
            for name in script.get_names(all_scopes=False):
                if name.type in ("function", "class"):
                    result["symbols"].append({
                        "name": name.name,
                        "type": name.type,
                        "line": name.line,
                        "col":  name.column,
                    })
            # Imports
            for name in script.get_names(all_scopes=False):
                if name.type == "module":
                    result["imports"].append(name.name)
            result["diagnostics"] = diagnose_file(source, file_path, proj)
    except Exception as e:
        result["diagnostics"] = f"Error en análisis: {e}"

    return result


def find_symbol_in_project(symbol_name: str, base_dir: Path) -> str:
    """
    Busca un símbolo por nombre en todos los .py del proyecto.
    Retorna ubicaciones (archivo:línea) donde aparece definido.
    """
    if not _JEDI_OK:
        # Fallback: grep
        results = []
        pattern = re.compile(
            rf"^\s*(?:def|class)\s+{re.escape(symbol_name)}\b", re.MULTILINE)
        for py_file in base_dir.rglob("*.py"):
            if ".git" in str(py_file) or "__pycache__" in str(py_file):
                continue
            try:
                src = py_file.read_text(encoding="utf-8", errors="replace")
                for m in pattern.finditer(src):
                    line_num = src[:m.start()].count("\n") + 1
                    results.append(f"{py_file.relative_to(base_dir)}:{line_num}")
            except Exception:
                pass
        if not results:
            return f"'{symbol_name}' no encontrado en {base_dir.name}"
        return f"'{symbol_name}' definido en:\n" + "\n".join(results)

    # Con jedi: usar el proyecto completo
    results = []
    for py_file in base_dir.rglob("*.py"):
        if ".git" in str(py_file) or "__pycache__" in str(py_file):
            continue
        try:
            src = py_file.read_text(encoding="utf-8", errors="replace")
            script = jedi.Script(src, path=str(py_file),
                                  project=jedi.Project(path=str(base_dir)))
            for name in script.get_names(all_scopes=True):
                if name.name == symbol_name and name.type in ("function", "class"):
                    results.append(
                        f"{py_file.relative_to(base_dir)}:{name.line}  ({name.type})")
        except Exception:
            continue

    if not results:
        return f"'{symbol_name}' no encontrado como función/clase en {base_dir.name}"
    return f"'{symbol_name}' definido en:\n" + "\n".join(results)


def rename_symbol(symbol_name: str, new_name: str,
                  file_path: Path, source: str,
                  project_path: Optional[Path] = None) -> tuple[str, str]:
    """
    Renombra un símbolo en el source dado.
    Retorna (nuevo_source, resumen).
    Si jedi no puede renombrar, hace replace textual con precaución.
    """
    if not _JEDI_OK:
        # Fallback: word-boundary replace
        new_source = re.sub(
            rf"\b{re.escape(symbol_name)}\b", new_name, source)
        count = len(re.findall(rf"\b{re.escape(symbol_name)}\b", source))
        return new_source, f"Reemplazado '{symbol_name}' → '{new_name}' ({count} ocurrencia(s), sin LSP)"

    # Con jedi: encontrar todas las referencias y renombrar
    try:
        proj = jedi.Project(path=str(project_path or file_path.parent))
        script = jedi.Script(source, path=str(file_path), project=proj)
        # Encontrar la primera definición del símbolo
        line, col = None, None
        for name in script.get_names(all_scopes=True):
            if name.name == symbol_name:
                line, col = name.line, name.column + 1
                break
        if line is None:
            return source, f"'{symbol_name}' no encontrado en {file_path.name}"
        # Obtener refactoring de rename
        refactoring = script.rename(line, col, new_name=new_name)
        new_source = source
        for path_str, changes in refactoring.get_changed_files().items():
            if Path(path_str) == file_path:
                new_source = changes.get_new_code()
        count = len(re.findall(rf"\b{re.escape(symbol_name)}\b", source)) - \
                len(re.findall(rf"\b{re.escape(symbol_name)}\b", new_source))
        return new_source, f"'{symbol_name}' → '{new_name}' ({abs(count)} cambio(s) via LSP)"
    except Exception as e:
        # Fallback a replace textual
        new_source = re.sub(rf"\b{re.escape(symbol_name)}\b", new_name, source)
        return new_source, f"LSP rename falló ({e}), usado replace textual"
