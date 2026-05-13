import subprocess
import os

def _run_cmd(cmd: list[str], cwd: str | None = None) -> str:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, timeout=5)
        if result.returncode != 0:
            return result.stderr.strip()
        return result.stdout.strip()
    except Exception as e:
        return f"Error: {e}"

def is_git_repo(path: str | None = None) -> bool:
    """Returns True if path (default: CWD) is inside a git repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            capture_output=True, text=True, cwd=path, timeout=2
        )
        return result.returncode == 0 and result.stdout.strip() == "true"
    except Exception:
        return False

def git_status() -> str:
    """Returns short git status of CWD repo."""
    if not is_git_repo():
        return ""
    return _run_cmd(["git", "status", "-s"])

def git_diff(staged: bool = False) -> str:
    """Returns git diff (unstaged by default, pass staged=True for --cached)."""
    if not is_git_repo():
        return ""
    cmd = ["git", "diff"]
    if staged:
        cmd.append("--cached")
    diff_out = _run_cmd(cmd)
    if len(diff_out) > 4000:
        return diff_out[:4000] + "\n... [truncated]"
    return diff_out

def git_log(n: int = 5) -> str:
    """Returns last N commits: hash + date + message."""
    if not is_git_repo():
        return ""
    return _run_cmd(["git", "log", f"-n", str(n), "--format=%h %ad %s", "--date=short"])

def git_branch() -> str:
    """Returns current branch name."""
    if not is_git_repo():
        return ""
    return _run_cmd(["git", "branch", "--show-current"])

def git_suggest_commit() -> str:
    """
    Reads git diff --cached (staged changes) and calls nova router to
    suggest a conventional commit message. Falls back to a generic message
    if router not available.
    """
    if not is_git_repo():
        return ""
        
    diff = git_diff(staged=True)
    if not diff:
        diff = git_diff(staged=False)
        if not diff:
            return "No hay cambios para generar un commit."
            
    prompt = f"Genera un mensaje de commit convencional (Conventional Commits) para estos cambios. Solo devuelve el mensaje final, sin explicaciones:\n\n{diff}"
    
    try:
        from nova.tools.nova_skills import _router
        if _router:
            resp = _router.route([{"role": "user", "content": prompt}])
            return resp.get("response", "feat: actualizacion general")
    except Exception:
        pass
        
    return "feat: actualizacion general (IA no disponible)"

def git_context_for_prompt() -> str:
    """
    Returns a compact git context string suitable for injecting into LLM prompts.
    Format:
      Branch: main | Status: 3 changed | Last commit: abc1234 fix: something
    Returns "" if not in a git repo.
    """
    if not is_git_repo():
        return ""
        
    branch = git_branch()
    status_out = git_status()
    changed_files = len([line for line in status_out.splitlines() if line.strip()])
    last_commit = _run_cmd(["git", "log", "-1", "--format=%h %s"])
    
    return f"Branch: {branch} | Status: {changed_files} changed | Last commit: {last_commit}"
