"""
nova_cerebro.py
───────────────
Conector de Obsidian/Cerebro para Nova — búsqueda dinámica, lectura y escritura.

Estrategia:
  1. File-based (siempre disponible): busca/lee/escribe directamente en ~/Cerebro/
  2. REST API (si Obsidian está corriendo): acceso enriquecido vía plugin Local REST API

API pública:
  cerebro_buscar(query, carpeta=None, max_resultados=5)  → list[dict]
  cerebro_leer(ruta_relativa)                            → str
  cerebro_escribir(ruta_relativa, contenido, modo="w")  → str
  cerebro_listar(carpeta="")                             → list[str]
  cerebro_nueva_nota(titulo, contenido, carpeta="NOVA/Notas") → str
  cerebro_estado()                                       → str
"""

from __future__ import annotations

import os
import re
import ssl
import json
import time
import logging
import urllib.request
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

_VAULT      = Path(os.getenv("CEREBRO_VAULT", "~/Cerebro")).expanduser()
_API_BASE   = os.getenv("OBSIDIAN_BASE_URL", "https://127.0.0.1:27124")
_API_KEY    = os.getenv("OBSIDIAN_API_KEY", "")
_TIMEOUT    = 3
_MAX_LINES  = 200   # máximo de líneas a devolver por nota


# ─────────────────────────────────────────────────────────────────────────────
# Helpers internos
# ─────────────────────────────────────────────────────────────────────────────

def _api_disponible() -> bool:
    """Verifica si la REST API de Obsidian responde."""
    if not _API_KEY:
        return False
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(
            f"{_API_BASE}/",
            headers={"Authorization": f"Bearer {_API_KEY}"},
        )
        with urllib.request.urlopen(req, timeout=_TIMEOUT, context=ctx):
            return True
    except Exception:
        return False


def _api_get(endpoint: str) -> dict | None:
    """GET a la API REST de Obsidian. Retorna dict o None si falla."""
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(
            f"{_API_BASE}{endpoint}",
            headers={"Authorization": f"Bearer {_API_KEY}"},
        )
        with urllib.request.urlopen(req, timeout=_TIMEOUT, context=ctx) as r:
            return json.loads(r.read())
    except Exception as e:
        log.debug("Obsidian API GET %s falló: %s", endpoint, e)
        return None


def _api_put(endpoint: str, content: str) -> bool:
    """PUT texto a la API REST de Obsidian. Retorna True si exitoso."""
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        data = content.encode()
        req = urllib.request.Request(
            f"{_API_BASE}{endpoint}",
            data=data,
            headers={
                "Authorization": f"Bearer {_API_KEY}",
                "Content-Type": "text/markdown",
            },
            method="PUT",
        )
        with urllib.request.urlopen(req, timeout=_TIMEOUT, context=ctx):
            return True
    except Exception as e:
        log.debug("Obsidian API PUT %s falló: %s", endpoint, e)
        return False


def _ruta_absoluta(ruta_relativa: str) -> Path:
    """Convierte ruta relativa al vault en Path absoluta."""
    ruta = ruta_relativa.lstrip("/")
    if not ruta.endswith(".md"):
        ruta += ".md"
    return _VAULT / ruta


def _extracto(texto: str, query: str, ventana: int = 3) -> str:
    """Extrae fragmento relevante del texto alrededor del match del query."""
    lineas = texto.splitlines()
    query_lower = query.lower()
    for i, linea in enumerate(lineas):
        if query_lower in linea.lower():
            inicio = max(0, i - 1)
            fin = min(len(lineas), i + ventana)
            return "\n".join(lineas[inicio:fin])
    return "\n".join(lineas[:5])


# ─────────────────────────────────────────────────────────────────────────────
# API pública
# ─────────────────────────────────────────────────────────────────────────────

def cerebro_buscar(
    query: str,
    carpeta: Optional[str] = None,
    max_resultados: int = 5,
) -> list[dict]:
    """
    Busca texto en el vault Cerebro.

    Retorna lista de dicts:
      {"archivo": "ruta/relativa.md", "titulo": str, "extracto": str, "score": int}

    Prioridad: API REST si disponible, sino file-based grep.
    """
    resultados: list[dict] = []

    # ── Estrategia file-based (siempre) ──────────────────────────────────────
    base = _VAULT / carpeta if carpeta else _VAULT
    if not base.exists():
        log.warning("Carpeta %s no existe", base)
        return resultados

    patron = re.compile(re.escape(query), re.IGNORECASE)
    archivos_md = sorted(base.rglob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)

    for archivo in archivos_md:
        try:
            texto = archivo.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        matches = len(patron.findall(texto))
        if matches == 0:
            continue

        ruta_rel = str(archivo.relative_to(_VAULT))
        titulo = archivo.stem.replace("-", " ").replace("_", " ")

        # Score: más matches = más relevante, archivos recientes primero
        score = matches * 10
        if query.lower() in archivo.name.lower():
            score += 50  # bonus si el query está en el nombre del archivo

        resultados.append({
            "archivo": ruta_rel,
            "titulo": titulo,
            "extracto": _extracto(texto, query),
            "score": score,
            "ruta_absoluta": str(archivo),
        })

        if len(resultados) >= max_resultados * 3:
            break

    # Ordenar por score y limitar
    resultados.sort(key=lambda x: x["score"], reverse=True)
    return resultados[:max_resultados]


def cerebro_leer(ruta_relativa: str) -> str:
    """
    Lee el contenido de una nota del vault.

    ruta_relativa: ej. "NOVA/Notas/mi_nota" o "NOVA/Notas/mi_nota.md"
    Retorna contenido (max _MAX_LINES líneas) o mensaje de error.
    """
    # Intentar primero con la API si está disponible
    if _api_disponible():
        data = _api_get(f"/vault/{ruta_relativa.lstrip('/')}")
        if data and "content" in data:
            return data["content"]

    # File-based fallback
    ruta = _ruta_absoluta(ruta_relativa)
    if not ruta.exists():
        # Buscar sin .md
        ruta_sin_ext = _VAULT / ruta_relativa.lstrip("/")
        if ruta_sin_ext.exists():
            ruta = ruta_sin_ext
        else:
            return f"No encontré la nota: {ruta_relativa}"

    try:
        texto = ruta.read_text(encoding="utf-8", errors="replace")
        lineas = texto.splitlines()
        if len(lineas) > _MAX_LINES:
            return "\n".join(lineas[:_MAX_LINES]) + f"\n\n[... {len(lineas) - _MAX_LINES} líneas más ...]"
        return texto
    except Exception as e:
        return f"Error leyendo {ruta_relativa}: {e}"


def cerebro_escribir(
    ruta_relativa: str,
    contenido: str,
    modo: str = "w",
) -> str:
    """
    Escribe/actualiza una nota en el vault.

    modo: "w" = sobreescribir, "a" = agregar al final
    Retorna mensaje de éxito o error.
    """
    ruta = _ruta_absoluta(ruta_relativa)
    ruta.parent.mkdir(parents=True, exist_ok=True)

    # Intentar API primero
    if _api_disponible() and modo == "w":
        endpoint = f"/vault/{ruta_relativa.lstrip('/')}"
        if not endpoint.endswith(".md"):
            endpoint += ".md"
        if _api_put(endpoint, contenido):
            return f"Nota guardada en Obsidian: {ruta_relativa}"

    # File-based fallback
    try:
        open_mode = "a" if modo == "a" else "w"
        if modo == "a" and ruta.exists():
            contenido = "\n" + contenido
        with open(ruta, open_mode, encoding="utf-8") as f:
            f.write(contenido)
        return f"Nota guardada en: {ruta.relative_to(_VAULT)}"
    except Exception as e:
        return f"Error escribiendo nota: {e}"


def cerebro_listar(carpeta: str = "") -> list[str]:
    """
    Lista notas markdown en una carpeta del vault.

    carpeta: ruta relativa al vault (vacío = raíz)
    Retorna lista de rutas relativas.
    """
    base = _VAULT / carpeta if carpeta else _VAULT
    if not base.exists():
        return []
    archivos = sorted(base.rglob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    return [str(a.relative_to(_VAULT)) for a in archivos]


def cerebro_nueva_nota(
    titulo: str,
    contenido: str,
    carpeta: str = "NOVA/Notas",
) -> str:
    """
    Crea una nueva nota en el vault con fecha/hora en el nombre.

    titulo: nombre de la nota (sin .md)
    contenido: cuerpo de la nota en Markdown
    carpeta: ruta relativa al vault donde crear la nota
    """
    ts = time.strftime("%Y-%m-%d")
    nombre_seguro = re.sub(r'[^\w\s\-_]', '', titulo).strip().replace(" ", "_")
    ruta = f"{carpeta}/{ts}_{nombre_seguro}"

    frontmatter = f"---\ntitulo: {titulo}\nfecha: {ts}\nfuente: Nova\n---\n\n"
    return cerebro_escribir(ruta, frontmatter + contenido)


def cerebro_estado() -> str:
    """Retorna estado del conector: vault path, cantidad de notas, API activa."""
    notas = list(_VAULT.rglob("*.md")) if _VAULT.exists() else []
    api = _api_disponible()
    lineas = [
        f"🧠 Cerebro: {_VAULT}",
        f"📄 Notas: {len(notas)} archivos .md",
        f"🔌 REST API: {'activa ✓' if api else 'inactiva (modo archivo)'}",
    ]
    if notas:
        carpetas = {p.parent.relative_to(_VAULT) for p in notas}
        lineas.append(f"📁 Carpetas: {', '.join(str(c) for c in sorted(carpetas) if str(c) != '.')}")
    return "\n".join(lineas)
