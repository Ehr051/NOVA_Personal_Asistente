"""
nova_github.py
──────────────
GitHub para Nova — equivalente Python del MCP server-github.
Usa PyGithub + token personal para leer/escribir repos, issues, PRs.

Config: variable GITHUB_TOKEN en .env o variable de entorno.
Usuario: Ehr051
"""

from __future__ import annotations

import os
import re
from typing import Optional

# Cargar variables de entorno
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


_TOKEN = os.getenv("GITHUB_TOKEN", "")
_USER = "Ehr051"
_gh = None
_HAS_GITHUB = False

try:
    from github import Github, GithubException
    _HAS_GITHUB = True
except ImportError:
    pass


def _client():
    """Retorna cliente GitHub (singleton)."""
    global _gh
    if not _HAS_GITHUB:
        return None
    if _gh is None:
        token = os.getenv("GITHUB_TOKEN", _TOKEN)
        if not token or token == "TU_TOKEN_AQUI":
            return None
        _gh = Github(token)
        # Detectar el usuario real asociado al token
        try:
            global _USER
            _USER = _gh.get_user().login
        except Exception:
            pass
    return _gh


def _no_token() -> str:
    return "No tengo token de GitHub configurado, Señor. Agregá GITHUB_TOKEN al .env."


# ── Repos ─────────────────────────────────────────────────────────────────────

def listar_repos(max_repos: int = 10) -> str:
    """Lista los repos del usuario."""
    gh = _client()
    if not gh:
        return _no_token()
    try:
        user = gh.get_user(_USER)
        repos = list(user.get_repos(sort="updated"))[:max_repos]
        if not repos:
            return "No encontré repos, Señor."
        lineas = [f"Repos de {_USER} ({len(repos)}):"]
        for r in repos:
            privado = "🔒" if r.private else "🌐"
            lineas.append(f"  {privado} {r.name} — {r.description or 'sin descripción'} ⭐{r.stargazers_count}")
        return "\n".join(lineas)
    except GithubException as e:
        return f"Error GitHub: {e.data.get('message', str(e))}"


def ver_repo(nombre: str) -> str:
    """Muestra info detallada de un repo."""
    gh = _client()
    if not gh:
        return _no_token()
    try:
        repo_id = nombre if "/" in nombre else f"{_USER}/{nombre}"
        r = gh.get_repo(repo_id)
        return (
            f"Repo: {r.full_name}\n"
            f"Descripción: {r.description or 'ninguna'}\n"
            f"Lenguaje: {r.language or '?'}\n"
            f"Stars: {r.stargazers_count} | Forks: {r.forks_count}\n"
            f"Default branch: {r.default_branch}\n"
            f"URL: {r.html_url}\n"
            f"Último push: {str(r.pushed_at)[:10]}"
        )
    except GithubException as e:
        msg = e.data.get('message', str(e))
        if e.status == 404:
            return f"No encontré el repo '{nombre}', Señor. ¿Tal vez sea uno de estos?\n{listar_repos(5)}"
        return f"Error de GitHub al buscar '{nombre}': {msg}"


# ── Issues ────────────────────────────────────────────────────────────────────

def listar_issues(repo: str, estado: str = "open", max_issues: int = 8) -> str:
    """Lista issues de un repo."""
    gh = _client()
    if not gh:
        return _no_token()
    try:
        repo_id = repo if "/" in repo else f"{_USER}/{repo}"
        r = gh.get_repo(repo_id)
        issues = list(r.get_issues(state=estado))[:max_issues]
        if not issues:
            return f"No hay issues {estado} en {repo}, Señor."
        lineas = [f"Issues {estado} en {repo} ({len(issues)}):"]
        for i in issues:
            lineas.append(f"  #{i.number} {i.title} (@{i.user.login})")
        return "\n".join(lineas)
    except GithubException as e:
        return f"Error: {e.data.get('message', str(e))}"


def crear_issue(repo: str, titulo: str, cuerpo: str = "") -> str:
    """Crea un issue en un repo."""
    gh = _client()
    if not gh:
        return _no_token()
    try:
        repo_id = repo if "/" in repo else f"{_USER}/{repo}"
        r = gh.get_repo(repo_id)
        issue = r.create_issue(title=titulo, body=cuerpo)
        return f"Issue #{issue.number} creado: '{titulo}' — {issue.html_url}, Señor."
    except GithubException as e:
        return f"No pude crear el issue: {e.data.get('message', str(e))}"


# ── Pull Requests ─────────────────────────────────────────────────────────────

def listar_prs(repo: str, estado: str = "open") -> str:
    """Lista pull requests de un repo."""
    gh = _client()
    if not gh:
        return _no_token()
    try:
        repo_id = repo if "/" in repo else f"{_USER}/{repo}"
        r = gh.get_repo(repo_id)
        prs = list(r.get_pulls(state=estado))[:8]
        if not prs:
            return f"No hay PRs {estado} en {repo}, Señor."
        lineas = [f"PRs {estado} en {repo}:"]
        for pr in prs:
            lineas.append(f"  #{pr.number} {pr.title} ({pr.head.ref} → {pr.base.ref})")
        return "\n".join(lineas)
    except GithubException as e:
        return f"Error: {e.data.get('message', str(e))}"


# ── Commits ───────────────────────────────────────────────────────────────────

def ultimos_commits(repo: str, rama: str = "", max_commits: int = 5) -> str:
    """Muestra los últimos commits de un repo."""
    gh = _client()
    if not gh:
        return _no_token()
    try:
        repo_id = repo if "/" in repo else f"{_USER}/{repo}"
        r = gh.get_repo(repo_id)
        kwargs = {"sha": rama} if rama else {}
        commits = list(r.get_commits(**kwargs))[:max_commits]
        if not commits:
            return f"No encontré commits en {repo}, Señor."
        lineas = [f"Últimos commits en {repo}:"]
        for c in commits:
            msg = c.commit.message.split("\n")[0][:70]
            fecha = str(c.commit.author.date)[:10]
            lineas.append(f"  {c.sha[:7]} [{fecha}] {msg}")
        return "\n".join(lineas)
    except GithubException as e:
        return f"Error: {e.data.get('message', str(e))}"


# ── Skills de voz ─────────────────────────────────────────────────────────────

def skill_github_repos(text: str = "") -> str:
    """Skill: lista mis repos de GitHub."""
    return listar_repos()


def skill_github_repo_info(text: str) -> str:
    """Skill: info de un repo específico. Ej: 'info del repo NOVA'"""
    nombre = re.sub(r'^.*?(?:repo|repositorio)\s+', '', text, flags=re.I).strip()
    if not nombre:
        return listar_repos()
    # Alias común para el repo del usuario
    if nombre.lower() == "nova":
        nombre = "NOVA-OpenAI-Voice-Assistant"
    return ver_repo(nombre)


def skill_github_issues(text: str) -> str:
    """Skill: ver issues de un repo. Ej: 'issues del repo NOVA'"""
    repo = re.sub(r'^.*?(?:issues?|problemas?|tickets?)\s+(?:de[l]?\s+(?:repo\s+)?)?', '', text, flags=re.I).strip()
    estado = "closed" if "cerrado" in text.lower() else "open"
    if not repo:
        return "¿De qué repo quiere ver los issues, Señor?"
    return listar_issues(repo, estado)


def skill_github_prs(text: str) -> str:
    """Skill: ver PRs de un repo. Ej: 'PRs del repo NOVA'"""
    repo = re.sub(r'^.*?(?:pr|pull\s*request)\s+(?:de[l]?\s+(?:repo\s+)?)?', '', text, flags=re.I).strip()
    if not repo:
        return "¿De qué repo quiere ver los PRs, Señor?"
    return listar_prs(repo)


def skill_github_commits(text: str) -> str:
    """Skill: ver commits. Ej: 'últimos commits del repo NOVA'"""
    repo = re.sub(r'^.*?(?:commits?)\s+(?:de[l]?\s+(?:repo\s+)?)?', '', text, flags=re.I).strip()
    if not repo:
        return "¿De qué repo quiere ver los commits, Señor?"
    # Alias común
    if repo.lower() == "nova":
        repo = "NOVA-OpenAI-Voice-Assistant"
    return ultimos_commits(repo)


def skill_github_crear_issue(text: str) -> str:
    """Skill: crea un issue. Ej: 'crea un issue en NOVA: bug en el login'"""
    m = re.search(r'(?:issue|ticket)\s+en\s+(\S+)[:\s]+(.+)', text, re.I)
    if not m:
        return "Formato: 'crea un issue en [repo]: [título]', Señor."
    return crear_issue(m.group(1), m.group(2).strip())


# ── Estado ────────────────────────────────────────────────────────────────────

def estado_github() -> str:
    """Verifica conexión a GitHub."""
    gh = _client()
    if not gh:
        return _no_token()
    try:
        user = gh.get_user(_USER)
        return f"GitHub conectado: @{user.login} — {user.public_repos} repos públicos, Señor."
    except Exception as e:
        return f"Error conectando a GitHub: {e}"


if __name__ == "__main__":
    print(estado_github())
    print(listar_repos())
