"""
nova_memory.py
────────────────
Memoria persistente de NOVA.

Almacenamiento dual:
  • SQLite  → ~/.nova/memory.db  (búsqueda rápida)
  • Obsidian vault → ~/Cerebro/NOVA/Memoria/ (cerebro compartido)

Tablas SQLite:
  facts         — hechos y preferencias del usuario (clave-valor)
  conversations — historial completo de conversaciones
"""

import os
import json
import sqlite3
import ssl
import urllib.request
import urllib.error
from datetime import datetime

DB_PATH = os.path.expanduser("~/.nova/memory.db")

# ─── Obsidian REST API ────────────────────────────────────────────────────────
_OBS_BASE = os.getenv("OBSIDIAN_BASE_URL", "http://127.0.0.1:27123")
_OBS_KEY  = os.getenv("OBSIDIAN_API_KEY", "")

# SSL context solo se usa si la URL es HTTPS (cert auto-firmado)
_SSL_CTX  = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode    = ssl.CERT_NONE

_OBS_IS_HTTPS = _OBS_BASE.startswith("https")


def _conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.executescript("""
        CREATE TABLE IF NOT EXISTS facts (
            key        TEXT PRIMARY KEY,
            value      TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS conversations (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            role       TEXT NOT NULL,
            content    TEXT NOT NULL,
            timestamp  TEXT NOT NULL
        );
    """)
    return con


# ─── Obsidian REST API helpers ────────────────────────────────────────────────

def _obs_request(method: str, path: str, body: str | None = None,
                 content_type: str = "text/markdown") -> str:
    """Hace una petición a la Obsidian REST API. Silencia errores."""
    if not _OBS_KEY:
        return ""
    try:
        url  = f"{_OBS_BASE}/vault/{path}"
        data = body.encode("utf-8") if body else None
        req  = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"Bearer {_OBS_KEY}")
        req.add_header("Content-Type", content_type)
        ctx = _SSL_CTX if _OBS_IS_HTTPS else None
        with urllib.request.urlopen(req, context=ctx, timeout=4) as r:
            return r.read().decode("utf-8")
    except Exception:
        return ""


def _obs_api(method: str, endpoint: str, body=None,
             content_type: str = "application/json") -> str:
    """Petición a endpoints no-vault de la Obsidian REST API (ej: /search/)."""
    if not _OBS_KEY:
        return ""
    try:
        url  = f"{_OBS_BASE}{endpoint}"
        if isinstance(body, str):
            data = body.encode("utf-8")
        elif isinstance(body, bytes):
            data = body
        else:
            data = None
        req  = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"Bearer {_OBS_KEY}")
        req.add_header("Content-Type", content_type)
        ctx = _SSL_CTX if _OBS_IS_HTTPS else None
        with urllib.request.urlopen(req, context=ctx, timeout=6) as r:
            return r.read().decode("utf-8")
    except Exception:
        return ""


def _sync_facts_to_vault() -> None:
    """Sincroniza todos los facts al vault via REST API."""
    try:
        with _conn() as con:
            rows = con.execute(
                "SELECT key, value, updated_at FROM facts ORDER BY key"
            ).fetchall()
        lines = [
            "# NOVA — Memoria del Usuario",
            f"*Sincronizado: {datetime.now().strftime('%Y-%m-%d %H:%M')}*",
            "",
            "| Clave | Valor | Actualizado |",
            "|---|---|---|",
        ]
        for key, val, updated in rows:
            lines.append(f"| {key} | {val} | {updated[:16]} |")
        _obs_request("PUT", "NOVA/Memoria/facts.md", "\n".join(lines) + "\n")
    except Exception:
        pass


def vault_append_note(folder: str, filename: str, content: str) -> str:
    """Agrega texto a una nota del vault (append via PATCH)."""
    note_path = f"{folder}/{filename}.md"
    ts = datetime.now().strftime("%H:%M")
    existing = _obs_request("GET", note_path)
    if existing:
        new_content = existing.rstrip() + f"\n- {ts} — {content}\n"
    else:
        new_content = f"# {filename}\n\n- {ts} — {content}\n"
    _obs_request("PUT", note_path, new_content)
    return note_path


def vault_create_note(folder: str, filename: str, content: str) -> str:
    """Crea o sobreescribe una nota en el vault."""
    note_path = f"{folder}/{filename}.md"
    _obs_request("PUT", note_path, content)
    return note_path


def vault_read_note(folder: str, filename: str) -> str:
    """Lee una nota del vault. Devuelve '' si no existe."""
    return _obs_request("GET", f"{folder}/{filename}.md")


def vault_read_path(path: str) -> str:
    """Lee una nota por path completo relativo al vault (ej: 'NOVA/Notas/algo.md')."""
    return _obs_request("GET", path)


def vault_list_dir(path: str = "") -> list[str]:
    """Lista archivos en un directorio del vault. Retorna lista de nombres."""
    import json as _json
    # Path de directorio debe terminar en / para la REST API
    dir_path = path.rstrip("/") + "/" if path else ""
    raw = _obs_request("GET", dir_path)
    if not raw:
        return []
    try:
        data = _json.loads(raw)
        return data.get("files", [])
    except Exception:
        return []


def vault_search(query: str, top_k: int = 5) -> list[dict]:
    """
    Busca texto en todo el vault via Obsidian REST API /search/simple/.
    Retorna lista de dicts: {filename, score, context_snippet}.
    Nota: el score es negativo (más negativo = mejor match).
    """
    import json as _json
    import urllib.parse
    if not query.strip():
        return []
    q = urllib.parse.quote(query)
    raw = _obs_api("POST", f"/search/simple/?query={q}&contextLength=200",
                   body=b"")
    if not raw:
        return []
    try:
        results = _json.loads(raw)
        # Ordenar por score más bajo (mejor match)
        results.sort(key=lambda x: x.get("score", 0))
        out = []
        for item in results[:top_k]:
            filename = item.get("filename", "")
            score    = item.get("score", 0)
            matches  = item.get("matches", [])
            snippet  = ""
            for m in matches[:2]:
                ctx = m.get("context", "")
                if isinstance(ctx, str) and ctx.strip():
                    snippet += ctx[:200] + " "
            out.append({"filename": filename, "score": score,
                        "snippet": snippet.strip()})
        return out
    except Exception:
        return []


def vault_search_text(query: str, top_k: int = 3) -> str:
    """Busca en el vault y devuelve texto legible para inyectar en el prompt."""
    results = vault_search(query, top_k=top_k)
    if not results:
        return ""
    lines = [f"[Búsqueda en Cerebro: '{query}']"]
    for r in results:
        lines.append(f"• {r['filename']}: {r['snippet']}")
    return "\n".join(lines)


# ─── Facts (memoria de usuario) ──────────────────────────────────────────────

def remember(key: str, value: str) -> str:
    """Guarda o actualiza un hecho sobre el usuario (SQLite + vault)."""
    now = datetime.now().isoformat()
    with _conn() as con:
        con.execute(
            """
            INSERT INTO facts (key, value, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value,
                                           updated_at = excluded.updated_at
            """,
            (key.strip().lower(), value.strip(), now, now),
        )
    _sync_facts_to_vault()
    return f"Anotado, Señor: {key} → {value}"


def recall(query: str) -> str:
    """Busca hechos relevantes a la consulta."""
    q = f"%{query.lower()}%"
    with _conn() as con:
        rows = con.execute(
            "SELECT key, value FROM facts WHERE key LIKE ? OR value LIKE ?",
            (q, q),
        ).fetchall()
    if not rows:
        return f"No tengo datos sobre '{query}', Señor."
    return "\n".join(f"  • {k}: {v}" for k, v in rows)


def get_all_facts() -> str:
    """Devuelve todos los hechos guardados como texto para inyectar en el prompt."""
    with _conn() as con:
        rows = con.execute("SELECT key, value FROM facts").fetchall()
    if not rows:
        return ""
    lines = ["[Datos que sé sobre el usuario]"]
    lines += [f"  • {k}: {v}" for k, v in rows]
    return "\n".join(lines)


def forget(key: str) -> str:
    """Elimina un hecho de la memoria."""
    with _conn() as con:
        con.execute("DELETE FROM facts WHERE key = ?", (key.strip().lower(),))
    _sync_facts_to_vault()
    return f"Eliminado de mi memoria: {key}, Señor."


# ─── Conversation history ─────────────────────────────────────────────────────

def save_turn(role: str, content: str) -> None:
    """Guarda un turno de conversación en SQLite."""
    with _conn() as con:
        con.execute(
            "INSERT INTO conversations (role, content, timestamp) VALUES (?, ?, ?)",
            (role, content, datetime.now().isoformat()),
        )


def get_recent_turns(limit: int = 20) -> list[dict]:
    """Devuelve los últimos N turnos en formato Chat API."""
    with _conn() as con:
        rows = con.execute(
            "SELECT role, content FROM conversations ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [{"role": r, "content": c} for r, c in reversed(rows)]


def clear_history() -> str:
    """Borra el historial de conversaciones (mantiene los facts)."""
    with _conn() as con:
        con.execute("DELETE FROM conversations")
    return "Historial de conversación borrado, Señor."


# ─── Diario de voz ───────────────────────────────────────────────────────────

def diary_append(text: str) -> str:
    """Agrega una entrada al diario de hoy en el vault."""
    today = datetime.now().strftime("%Y-%m-%d")
    path = vault_append_note("Diario", today, text)
    return f"Entrada agregada al diario, Señor. ({path})"


# ─── Contexto del vault para el sistema ──────────────────────────────────────

def load_vault_context() -> str:
    """
    Carga el contexto del Gran Cerebro para enriquecer el system prompt.

    Con API activa: lee NOVA/Briefing.md + facts + Claude/memoria/MEMORY.md
    Sin API (file-based): escanea TODO el vault, lista carpetas y últimas notas
                          modificadas de cada sección (no solo NOVA/).
    """
    sections: list[str] = []

    if _OBS_KEY:
        # ── Modo API ─────────────────────────────────────────────────────────
        briefing = _obs_request("GET", "NOVA/Briefing.md")
        if briefing:
            lines = [l for l in briefing.splitlines()
                     if l.startswith("- **") or l.startswith("## Proyectos")]
            if lines:
                sections.append("PROYECTOS ACTIVOS:\n" + "\n".join(lines[:20]))

        facts = get_all_facts()
        if facts:
            sections.append(facts)

        memory_index = _obs_request("GET", "Claude/memoria/MEMORY.md")
        if memory_index:
            relevant = [l for l in memory_index.splitlines()
                        if l.startswith("- [") or l.startswith("#")]
            if relevant:
                sections.append("MEMORIA CLAUDE CODE:\n" + "\n".join(relevant[:10]))

    else:
        # ── Modo file-based: todo el vault ────────────────────────────────────
        vault = os.path.expanduser(os.getenv("CEREBRO_VAULT", "~/Cerebro"))
        from pathlib import Path as _Path
        vault_path = _Path(vault)
        if not vault_path.exists():
            return ""

        # Carpetas de primer nivel con cantidad de notas
        carpetas: dict[str, list] = {}
        for md in vault_path.rglob("*.md"):
            top = md.relative_to(vault_path).parts[0] if len(md.relative_to(vault_path).parts) > 1 else "."
            carpetas.setdefault(top, []).append(md)

        resumen_carpetas = []
        for carpeta, archivos in sorted(carpetas.items()):
            resumen_carpetas.append(f"  {carpeta}/ ({len(archivos)} notas)")
        sections.append("VAULT CEREBRO — ESTRUCTURA:\n" + "\n".join(resumen_carpetas))

        # Últimas 8 notas modificadas en TODO el vault (no solo NOVA/)
        todos = sorted(vault_path.rglob("*.md"),
                       key=lambda p: p.stat().st_mtime, reverse=True)
        recientes = []
        for f in todos[:8]:
            rel = str(f.relative_to(vault_path))
            try:
                primeras = f.read_text(encoding="utf-8", errors="replace").splitlines()
                extracto = next((l.strip() for l in primeras[1:] if l.strip()), "")[:80]
            except Exception:
                extracto = ""
            recientes.append(f"  {rel}: {extracto}")
        if recientes:
            sections.append("NOTAS RECIENTES (todo el vault):\n" + "\n".join(recientes))

        # Facts del usuario (siempre disponibles desde SQLite)
        facts = get_all_facts()
        if facts:
            sections.append(facts)

    return "\n\n".join(sections)
