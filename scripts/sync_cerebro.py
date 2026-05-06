#!/usr/bin/env python3
"""
sync_cerebro.py — Gran Cerebro: sincroniza TODO → Obsidian vault
─────────────────────────────────────────────────────────────────
Fuentes:
  • Proyectos del Desktop (repos git + carpetas con .md)
  • Repos git del sistema (~/ hasta profundidad 4)
  • Memorias de Claude Code (~/.claude, ~/Cerebro/Claude/memoria/)
  • Drop zone (~/Cerebro/Drops/) — exports manuales de Claude.ai, etc.

Uso:
  python3 sync_cerebro.py              # sync todo
  python3 sync_cerebro.py --dry-run   # preview
  python3 sync_cerebro.py --fast      # solo archivos nuevos/modificados
  python3 sync_cerebro.py NOVA      # filtrar por nombre de proyecto
"""

import os
import ssl
import sys
import time
import urllib.parse
import urllib.request
import urllib.error
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ─── Config ──────────────────────────────────────────────────────────────────

OBS_BASE = os.getenv("OBSIDIAN_BASE_URL", "https://127.0.0.1:27124")
OBS_KEY  = os.getenv("OBSIDIAN_API_KEY", "")
HOME     = Path.home()

# Directorios raíz a escanear en busca de repos git y .md
SCAN_ROOTS = [
    HOME / "Desktop",
    HOME / ".claude" / "skills",
    HOME / "Cerebro",
]

# Repos grandes a excluir (demasiado ruido)
SKIP_REPOS = {
    "stable-diffusion-webui", "StableDiffusion", "ComfyUI",
    "node_modules", ".Trash", "Library",
}

# Archivos .md a ignorar por nombre
SKIP_FILES = {"CONTRIBUTING.md", "QUANTIZATION.md", "LICENSE.md"}

# Extensiones adicionales a incluir para el drop zone
DROP_EXTENSIONS = {".md", ".txt"}

MAX_DEPTH = 4   # profundidad máxima de búsqueda en repos
MAX_SIZE  = 200_000  # bytes — no subir archivos > 200KB

# ─── SSL ─────────────────────────────────────────────────────────────────────

_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode    = ssl.CERT_NONE

# ─── Obsidian REST ───────────────────────────────────────────────────────────

def _encode_path(vault_path: str) -> str:
    return "/".join(urllib.parse.quote(seg, safe="") for seg in vault_path.split("/"))


def obs_put(vault_path: str, content: str) -> bool:
    url  = f"{OBS_BASE}/vault/{_encode_path(vault_path)}"
    data = content.encode("utf-8")
    req  = urllib.request.Request(url, data=data, method="PUT")
    req.add_header("Authorization", f"Bearer {OBS_KEY}")
    req.add_header("Content-Type",  "text/markdown; charset=utf-8")
    try:
        with urllib.request.urlopen(req, context=_SSL_CTX, timeout=8) as r:
            return r.status in (200, 201, 204)
    except urllib.error.HTTPError as e:
        print(f"  [!] PUT {vault_path} → HTTP {e.code}")
        return False
    except Exception as e:
        print(f"  [!] PUT {vault_path} → {e}")
        return False


def obs_get(vault_path: str):
    url = f"{OBS_BASE}/vault/{_encode_path(vault_path)}"
    req = urllib.request.Request(url, method="GET")
    req.add_header("Authorization", f"Bearer {OBS_KEY}")
    try:
        with urllib.request.urlopen(req, context=_SSL_CTX, timeout=5) as r:
            return r.read().decode("utf-8")
    except Exception:
        return None

# ─── Helpers ─────────────────────────────────────────────────────────────────

def _read_md(path: Path):
    if path.stat().st_size > MAX_SIZE:
        return None
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None


def _collect_md(base: Path, max_depth: int = MAX_DEPTH) -> list[Path]:
    result = []
    for root, dirs, files in os.walk(base):
        depth = len(Path(root).relative_to(base).parts)
        if depth >= max_depth:
            dirs.clear()
            continue
        dirs[:] = [d for d in dirs
                   if d not in (".git", "node_modules", "__pycache__", ".venv",
                                ".tox", "dist", "build", ".mypy_cache")]
        for fname in files:
            if fname.endswith(".md") and fname not in SKIP_FILES:
                result.append(Path(root) / fname)
    return result


def _upload_files(files: list[Path], base: Path, vault_prefix: str,
                  dry_run: bool = False) -> int:
    uploaded = 0
    for md_file in files:
        rel        = md_file.relative_to(base)
        vault_path = f"{vault_prefix}/{rel}".replace("\\", "/")

        if dry_run:
            print(f"  [dry] {vault_path}")
            uploaded += 1
            continue

        content = _read_md(md_file)
        if content is None:
            continue

        if obs_put(vault_path, content):
            print(f"  ✓  {vault_path}")
            uploaded += 1

    return uploaded

# ─── Fuentes de sincronización ───────────────────────────────────────────────

def sync_git_repos(filter_arg=None, dry_run: bool = False
                   ) -> tuple:
    """Encuentra todos los repos git accesibles y sube sus .md."""
    seen: set[Path] = set()
    results: list[tuple[str, int]] = []
    total = 0

    for root_dir in SCAN_ROOTS:
        if not root_dir.exists():
            continue
        # Buscar .git dirs
        for git_dir in sorted(root_dir.rglob(".git")):
            repo = git_dir.parent
            if repo in seen:
                continue
            if any(skip in repo.parts for skip in SKIP_REPOS):
                continue
            if filter_arg and filter_arg.lower() not in repo.name.lower():
                continue
            seen.add(repo)

            files = _collect_md(repo)
            if not files:
                continue

            # Prefijo en el vault: Proyectos/<nombre-repo>
            vault_prefix = f"Proyectos/{repo.name}"
            print(f"→ {repo.name}  ({len(files)} md)  [{repo}]")
            n = _upload_files(files, repo, vault_prefix, dry_run)
            total += n
            results.append((repo.name, n))

    return total, results


def sync_claude_memoria(dry_run: bool = False) -> int:
    """Sube memorias de Claude Code al vault bajo Claude/memoria/."""
    mem_dir = HOME / "Cerebro" / "Claude" / "memoria"
    if not mem_dir.exists():
        return 0
    files = list(mem_dir.glob("*.md"))
    if not files:
        return 0
    print(f"→ Claude/memoria  ({len(files)} archivos)")
    return _upload_files(files, mem_dir, "Claude/memoria", dry_run)


def sync_claude_skills(dry_run: bool = False) -> int:
    """Sube README de los skills de Claude Code al vault."""
    skills_dir = HOME / ".claude" / "skills"
    if not skills_dir.exists():
        return 0
    files = _collect_md(skills_dir, max_depth=2)
    if not files:
        return 0
    print(f"→ Claude/skills  ({len(files)} archivos)")
    return _upload_files(files, skills_dir, "Claude/skills", dry_run)


def sync_openclaw_memoria(dry_run: bool = False) -> int:
    """Sube las memorias de la IA OpenClaw al vault."""
    mem_dir = HOME / ".openclaw" / "memory"
    if not mem_dir.exists():
        return 0
    files = list(mem_dir.glob("*.md")) + list(mem_dir.glob("*.json")) + list(mem_dir.glob("*.txt"))
    if not files:
        return 0
    print(f"→ OpenClaw/memoria  ({len(files)} archivos)")
    return _upload_files(files, mem_dir, "OpenClaw/memoria", dry_run)


def sync_drop_zone(dry_run: bool = False) -> int:
    """
    Sube archivos del Drop Zone al vault bajo Claude/conversaciones/.
    El Drop Zone es ~/Cerebro/Drops/ — el usuario puede pegar exports
    de Claude.ai, capturas, notas, etc.
    """
    drop_dir = HOME / "Cerebro" / "Drops"
    drop_dir.mkdir(parents=True, exist_ok=True)

    files = [
        f for f in drop_dir.rglob("*")
        if f.suffix.lower() in DROP_EXTENSIONS and f.is_file()
    ]
    if not files:
        return 0

    print(f"→ Drop Zone  ({len(files)} archivos)")
    return _upload_files(files, drop_dir, "Claude/conversaciones", dry_run)


def build_index(repos: list[tuple[str, int]]) -> None:
    """Crea/actualiza Proyectos/_INDEX.md en el vault."""
    import datetime
    lines = [
        "# Gran Cerebro — Índice de Proyectos",
        "",
        f"_Última sync: {datetime.date.today()}_",
        "",
        "| Proyecto | Archivos .md |",
        "|----------|-------------|",
    ]
    for name, count in sorted(repos, key=lambda x: x[0].lower()):
        lines.append(f"| [[Proyectos/{name}/README|{name}]] | {count} |")
    if obs_put("Proyectos/_INDEX.md", "\n".join(lines)):
        print(f"  ✓  Proyectos/_INDEX.md (índice)")


def write_vault_briefing(repos: list[tuple[str, int]]) -> None:
    """
    Genera NOVA/Briefing.md — nota de contexto que Nova carga al arrancar.
    Contiene resumen de proyectos + memorias clave.
    """
    import datetime
    names = [r[0] for r in sorted(repos, key=lambda x: x[0].lower())]
    lines = [
        "# Briefing — Gran Cerebro",
        f"_Generado: {datetime.date.today()}_",
        "",
        "## Proyectos activos",
        "",
    ]
    for name in names:
        lines.append(f"- **{name}** → [[Proyectos/{name}/README]]")
    lines += [
        "",
        "## Memoria de Claude Code",
        "→ [[Claude/memoria/MEMORY]]",
        "",
        "## Memoria de OpenClaw",
        "→ [[OpenClaw/memoria/]]",
        "",
        "## Drop Zone (exports Claude.ai)",
        "→ Carpeta local: `~/Cerebro/Drops/`",
        "→ Vault: [[Claude/conversaciones/]]",
        "",
        "## Cómo actualizar",
        '- Decirle a Nova: *"sincroniza el cerebro"*',
        "- O: `python3 sync_cerebro.py`",
    ]
    if obs_put("NOVA/Briefing.md", "\n".join(lines)):
        print(f"  ✓  NOVA/Briefing.md (briefing de Nova)")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    dry_run    = "--dry-run" in sys.argv
    filter_arg = next((a for a in sys.argv[1:] if not a.startswith("--")), None)

    if not OBS_KEY:
        print("ERROR: OBSIDIAN_API_KEY no configurada en .env")
        sys.exit(1)

    t0 = time.time()
    label = "[DRY RUN] " if dry_run else ""
    print(f"{label}Gran Cerebro — sincronizando todo → Obsidian vault\n")

    # Memorias de IAs
    n_claude  = sync_claude_memoria(dry_run)
    n_skills  = sync_claude_skills(dry_run)
    n_openclaw= sync_openclaw_memoria(dry_run)
    n_drops   = sync_drop_zone(dry_run)

    # Repos git
    n_repos, repo_list = sync_git_repos(filter_arg, dry_run)

    # Índice + briefing
    if not dry_run and repo_list:
        build_index(repo_list)
        write_vault_briefing(repo_list)

    total   = n_claude + n_skills + n_openclaw + n_drops + n_repos
    elapsed = round(time.time() - t0, 1)
    print(f"\n{label}Listo en {elapsed}s: {total} archivos "
          f"({n_repos} proyectos · {n_claude} memorias Claude · "
          f"{n_openclaw} memorias OpenClaw · {n_skills} skills · {n_drops} drops)")


if __name__ == "__main__":
    main()
