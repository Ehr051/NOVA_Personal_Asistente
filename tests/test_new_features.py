"""
test_new_features.py — Tests para los 4 features de sesión 9:
  1. Rate limit retry (_parse_retry_after)
  2. Web UI agent SSE threaded
  3. --json oneshot CLI
  4. /checkpoint
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


# ════════════════════════════════════════════════════════════════════════════
# 1. _parse_retry_after
# ════════════════════════════════════════════════════════════════════════════

def test_parse_retry_after_not_rate_limit():
    from nova.core.nova_router import _parse_retry_after
    exc = ValueError("some other error")
    assert _parse_retry_after(exc) is None


def test_parse_retry_after_429_no_header():
    from nova.core.nova_router import _parse_retry_after
    exc = Exception("429 Too Many Requests")
    result = _parse_retry_after(exc)
    assert result == 5.0  # default conservador


def test_parse_retry_after_try_again_in():
    from nova.core.nova_router import _parse_retry_after
    exc = Exception("Rate limit exceeded. Please try again in 2.5s")
    result = _parse_retry_after(exc)
    assert result == 2.5


def test_parse_retry_after_retry_after_pattern():
    from nova.core.nova_router import _parse_retry_after
    exc = Exception("rate limit hit. retry after 10s")
    result = _parse_retry_after(exc)
    assert result == 10.0


def test_parse_retry_after_with_header(monkeypatch):
    from nova.core.nova_router import _parse_retry_after

    exc = Exception("429 rate limit")
    exc.response = MagicMock()
    exc.response.headers = {"retry-after": "7"}

    result = _parse_retry_after(exc)
    assert result == 7.0


def test_parse_retry_after_max_wait_constant():
    from nova.core.nova_router import _RATE_LIMIT_MAX_WAIT
    assert _RATE_LIMIT_MAX_WAIT > 0
    assert _RATE_LIMIT_MAX_WAIT <= 60


# ════════════════════════════════════════════════════════════════════════════
# 2. Web UI agent SSE — threaded (non-blocking)
# ════════════════════════════════════════════════════════════════════════════

def test_web_server_agent_endpoint_exists():
    """El web server debe registrar /agent como endpoint SSE."""
    from nova.web import nova_web_server
    assert hasattr(nova_web_server, "start")
    assert hasattr(nova_web_server, "stop")


def test_stream_agent_uses_queue_thread(monkeypatch):
    """_stream_agent debe correr en thread separado y enviar SSE via queue."""
    import queue
    import threading
    from nova.web.nova_web_server import NovaWebHandler

    chunks_sent: list[str] = []
    progress_cbs: list = []

    def fake_skill_agente(texto, progress_cb=None):
        if progress_cb:
            progress_cbs.append(progress_cb)
            progress_cb("📋 Plan:\n1. Paso uno\n")
            progress_cb("⚙️  get_time({})")
            progress_cb("   → 12:00")
        return "Resultado final de prueba."

    # Crear handler simulado sin socket real
    handler = NovaWebHandler.__new__(NovaWebHandler)
    handler.wfile = MagicMock()
    handler.wfile.write = MagicMock(return_value=None)
    handler.wfile.flush = MagicMock()

    def fake_write_sse(data: str) -> bool:
        chunks_sent.append(data)
        return True

    handler._write_sse = fake_write_sse

    import nova.web.nova_web_server as _ws
    monkeypatch.setattr(_ws, "_router", MagicMock())

    with patch("nova.tools.nova_skills.skill_agente", fake_skill_agente):
        # Run in a thread to avoid blocking
        t = threading.Thread(target=handler._stream_agent, args=("test objetivo",))
        t.start()
        t.join(timeout=5)

    assert any("[DONE]" in c for c in chunks_sent), f"[DONE] not found in: {chunks_sent}"
    assert any("Resultado final" in c for c in chunks_sent)
    assert len(progress_cbs) == 1  # progress_cb was called


# ════════════════════════════════════════════════════════════════════════════
# 3. --json oneshot CLI
# ════════════════════════════════════════════════════════════════════════════

def _load_nova_cli():
    """Load the nova CLI script (no .py extension) via runpy."""
    import runpy
    return runpy.run_path(str(ROOT / "nova"), run_name="nova_cli")


def _make_tty_stdin():
    """Return a mock stdin that reports isatty()=True (no pipe data)."""
    import io
    m = MagicMock()
    m.isatty.return_value = True
    m.read.return_value = ""
    return m


def test_cmd_ask_oneshot_json_skill(capsys):
    """Cuando la skill resuelve localmente, --json devuelve JSON válido."""
    ns = _load_nova_cli()
    cmd_ask_oneshot = ns["cmd_ask_oneshot"]

    def fake_dispatch(q):
        return "Son las 12:00"

    with patch("nova.tools.nova_skills.dispatch", fake_dispatch), \
         patch("sys.stdin", _make_tty_stdin()):
        cmd_ask_oneshot("qué hora es", json_output=True)

    captured = capsys.readouterr()
    assert captured.out.strip(), "No JSON output produced"
    data = json.loads(captured.out.strip())
    assert data.get("ok") is True
    assert "response" in data
    assert data.get("source") == "skill"


def test_cmd_ask_oneshot_json_error(capsys):
    """Con --json y sin providers, devuelve {"ok": false, "error": ...}."""
    ns = _load_nova_cli()
    cmd_ask_oneshot = ns["cmd_ask_oneshot"]

    with patch("nova.tools.nova_skills.dispatch", side_effect=Exception("no skills")), \
         patch("nova.core.nova_client.NovaDaemonClient.ping", return_value=False), \
         patch("nova.core.nova_router.NovaRouter.route",
               side_effect=Exception("no providers")), \
         patch("nova.core.nova_router.NovaRouter.route_stream",
               side_effect=Exception("no stream")), \
         patch("sys.stdin", _make_tty_stdin()):
        cmd_ask_oneshot("pregunta", json_output=True)

    captured = capsys.readouterr()
    assert captured.out.strip(), "No JSON output produced"
    data = json.loads(captured.out.strip())
    assert data.get("ok") is False
    assert "error" in data


def test_cmd_ask_oneshot_json_has_elapsed_field(capsys):
    """El output JSON debe incluir campo elapsed."""
    ns = _load_nova_cli()
    cmd_ask_oneshot = ns["cmd_ask_oneshot"]

    def fake_dispatch(q):
        return "respuesta rápida"

    with patch("nova.tools.nova_skills.dispatch", fake_dispatch), \
         patch("sys.stdin", _make_tty_stdin()):
        cmd_ask_oneshot("algo", json_output=True)

    captured = capsys.readouterr()
    assert captured.out.strip()
    data = json.loads(captured.out.strip())
    assert "elapsed" in data
    assert isinstance(data["elapsed"], (int, float))


# ════════════════════════════════════════════════════════════════════════════
# 4. /checkpoint
# ════════════════════════════════════════════════════════════════════════════

def test_checkpoint_lista_empty(tmp_path, monkeypatch):
    import nova.cli.repl as repl
    monkeypatch.setattr(repl, "_CHECKPOINTS_DIR", str(tmp_path / "ckpts"))
    result = repl.cmd_checkpoint("")
    assert "No hay checkpoints" in result or result is not None


def test_checkpoint_guardar_and_lista(tmp_path, monkeypatch):
    import nova.cli.repl as repl
    monkeypatch.setattr(repl, "_CHECKPOINTS_DIR", str(tmp_path / "ckpts"))
    monkeypatch.setitem(repl._session_state, "history", [
        {"role": "user", "content": "hola"},
        {"role": "assistant", "content": "hola para vos"},
    ])

    result = repl.cmd_checkpoint("guardar test_ck")
    assert "test_ck" in result
    assert "guardada" in result.lower() or "guardado" in result.lower()

    ck_file = Path(tmp_path / "ckpts" / "test_ck.json")
    assert ck_file.exists()

    result_list = repl.cmd_checkpoint("lista")
    assert "test_ck" in result_list


def test_checkpoint_cargar(tmp_path, monkeypatch):
    import nova.cli.repl as repl
    monkeypatch.setattr(repl, "_CHECKPOINTS_DIR", str(tmp_path / "ckpts"))

    # Save a checkpoint manually
    ck_dir = Path(tmp_path / "ckpts")
    ck_dir.mkdir(parents=True)
    data = {
        "id": "mi_sesion",
        "history": [
            {"role": "user", "content": "recuerda esto"},
            {"role": "assistant", "content": "recordado"},
        ],
    }
    (ck_dir / "mi_sesion.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8"
    )

    # Load it
    monkeypatch.setitem(repl._session_state, "history", [])
    result = repl.cmd_checkpoint("cargar mi_sesion")
    assert "mi_sesion" in result
    assert "restaurada" in result.lower() or "restaurado" in result.lower()
    assert len(repl._session_state["history"]) == 2


def test_checkpoint_cargar_nonexistent(tmp_path, monkeypatch):
    import nova.cli.repl as repl
    monkeypatch.setattr(repl, "_CHECKPOINTS_DIR", str(tmp_path / "ckpts"))
    (tmp_path / "ckpts").mkdir(parents=True)
    result = repl.cmd_checkpoint("cargar noexiste")
    assert "no encontrado" in result.lower() or "not found" in result.lower()


def test_checkpoint_borrar(tmp_path, monkeypatch):
    import nova.cli.repl as repl
    monkeypatch.setattr(repl, "_CHECKPOINTS_DIR", str(tmp_path / "ckpts"))

    ck_dir = Path(tmp_path / "ckpts")
    ck_dir.mkdir(parents=True)
    ck_file = ck_dir / "para_borrar.json"
    ck_file.write_text('{"id":"para_borrar","history":[]}', encoding="utf-8")

    result = repl.cmd_checkpoint("borrar para_borrar")
    assert not ck_file.exists()
    assert "eliminado" in result.lower() or "borrado" in result.lower()


def test_checkpoint_unknown_subcommand(tmp_path, monkeypatch):
    import nova.cli.repl as repl
    monkeypatch.setattr(repl, "_CHECKPOINTS_DIR", str(tmp_path / "ckpts"))
    result = repl.cmd_checkpoint("comando_raro")
    assert result is not None
    assert "desconocido" in result.lower() or "uso" in result.lower()


def test_checkpoint_in_slash_commands():
    from nova.cli.repl import SLASH_COMMANDS
    assert "/checkpoint" in SLASH_COMMANDS
    assert "/ckpt" in SLASH_COMMANDS


# ════════════════════════════════════════════════════════════════════════════
# 5. Modos custom
# ════════════════════════════════════════════════════════════════════════════

def test_modo_lista_shows_builtin():
    from nova.cli.repl import cmd_modo, _MODOS_BUILTIN
    result = cmd_modo("")
    for name in _MODOS_BUILTIN:
        assert name in result


def test_modo_builtin_militar_removed():
    from nova.cli.repl import _MODOS_BUILTIN
    assert "militar" not in _MODOS_BUILTIN


def test_modo_nuevo_creates_file(tmp_path, monkeypatch):
    """Wizard flow: cmd_modo starts it, _wizard_handle completes it."""
    import nova.cli.repl as repl
    monkeypatch.setattr(repl, "_MODOS_DIR", str(tmp_path / "modos"))

    # Step 0 — start wizard
    result = repl.cmd_modo("nuevo testmode")
    assert "testmode" in result
    assert repl._WIZARD_STATE.get("type") == "modo_nuevo"

    # Step 0 — description
    repl._wizard_handle("Modo de prueba para testing")
    # Step 1 — temperature
    repl._wizard_handle("0.5")
    # Step 2 — system instructions (completes wizard)
    final = repl._wizard_handle("Instrucciones de testing")
    assert "testmode" in final
    assert (tmp_path / "modos" / "testmode.json").exists()
    assert "testmode" in repl._MODOS
    assert not repl._WIZARD_STATE  # wizard must be cleared


def test_modo_nuevo_cant_overwrite_builtin(tmp_path, monkeypatch):
    import nova.cli.repl as repl
    monkeypatch.setattr(repl, "_MODOS_DIR", str(tmp_path / "modos"))
    result = repl.cmd_modo("nuevo codigo intento de sobrescribir")
    assert "built-in" in result.lower()


def test_modo_borrar_custom(tmp_path, monkeypatch):
    import json
    import nova.cli.repl as repl
    monkeypatch.setattr(repl, "_MODOS_DIR", str(tmp_path / "modos"))
    # Create manually
    mdir = tmp_path / "modos"
    mdir.mkdir()
    cfg = {"desc": "test", "temp": 0.5, "tier": None, "extra": ""}
    (mdir / "paraborrrar.json").write_text(json.dumps(cfg), encoding="utf-8")
    repl._MODOS["paraborrrar"] = {**cfg, "_custom": True}
    result = repl.cmd_modo("borrar paraborrrar")
    assert "eliminado" in result.lower()
    assert "paraborrrar" not in repl._MODOS


def test_modo_borrar_builtin_rejected(tmp_path, monkeypatch):
    import nova.cli.repl as repl
    monkeypatch.setattr(repl, "_MODOS_DIR", str(tmp_path / "modos"))
    result = repl.cmd_modo("borrar normal")
    assert "built-in" in result.lower()


def test_modo_exportar(tmp_path, monkeypatch):
    import nova.cli.repl as repl
    monkeypatch.setattr(repl, "_MODOS_DIR", str(tmp_path / "modos"))
    result = repl.cmd_modo("exportar codigo")
    assert "codigo" in result
    assert '"temp"' in result or "temp" in result


def test_modo_custom_loaded_from_dir(tmp_path, monkeypatch):
    import json
    import nova.cli.repl as repl
    mdir = tmp_path / "modos"
    mdir.mkdir()
    cfg = {"desc": "Mi modo personal", "temp": 0.4, "tier": 2, "extra": "Instrucciones custom"}
    (mdir / "personal.json").write_text(json.dumps(cfg), encoding="utf-8")
    monkeypatch.setattr(repl, "_MODOS_DIR", str(mdir))
    repl._load_custom_modos()
    assert "personal" in repl._MODOS
    assert repl._MODOS["personal"]["desc"] == "Mi modo personal"


def test_nova_version():
    """nova --version debe mostrar un número de versión."""
    import subprocess
    result = subprocess.run(
        [sys.executable, str(ROOT / "nova"), "--version"],
        capture_output=True, text=True
    )
    assert result.returncode == 0
    assert "nova" in result.stdout.lower() or "3." in result.stdout


# ════════════════════════════════════════════════════════════════════════════
# 6. User profile + onboarding
# ════════════════════════════════════════════════════════════════════════════

def test_user_profile_save_load(tmp_path, monkeypatch):
    import nova.core.nova_user_profile as up
    monkeypatch.setattr(up, "USERS_DIR", tmp_path / "users")
    profile = up.UserProfile(address="Señora", notes="Ingeniera de software")
    profile.save()
    loaded = up.UserProfile.load()
    assert loaded is not None
    assert loaded.address == "Señora"
    assert loaded.notes == "Ingeniera de software"


def test_user_profile_exists(tmp_path, monkeypatch):
    import nova.core.nova_user_profile as up
    monkeypatch.setattr(up, "USERS_DIR", tmp_path / "users")
    assert not up.UserProfile.exists()
    up.UserProfile(address="Señor").save()
    assert up.UserProfile.exists()


def test_user_profile_load_or_default(tmp_path, monkeypatch):
    import nova.core.nova_user_profile as up
    monkeypatch.setattr(up, "USERS_DIR", tmp_path / "users")
    profile = up.UserProfile.load_or_default()
    assert profile.address == "Señor"  # default when no file


def test_system_prompt_fragment_senora(tmp_path, monkeypatch):
    import nova.core.nova_user_profile as up
    monkeypatch.setattr(up, "USERS_DIR", tmp_path / "users")
    profile = up.UserProfile(address="Señora", name="María", notes="Médica")
    frag = profile.system_prompt_fragment()
    assert "Señora" in frag
    assert "María" in frag
    assert "Médica" in frag


def test_system_prompt_fragment_custom_name(tmp_path, monkeypatch):
    import nova.core.nova_user_profile as up
    monkeypatch.setattr(up, "USERS_DIR", tmp_path / "users")
    profile = up.UserProfile(address="Comandante")
    frag = profile.system_prompt_fragment()
    assert "Comandante" in frag


def test_build_system_prompt_reads_profile(tmp_path, monkeypatch):
    import nova.core.nova_user_profile as up
    import nova.core.nova_router as router
    monkeypatch.setattr(up, "USERS_DIR", tmp_path / "users")
    up.UserProfile(address="Señora").save()
    prompt = router._build_system_prompt()
    assert "Señora" in prompt
    assert "Señor'" not in prompt  # old default gone


def test_cmd_perfil_view(tmp_path, monkeypatch):
    import nova.core.nova_user_profile as up
    import nova.cli.repl as repl
    monkeypatch.setattr(up, "USERS_DIR", tmp_path / "users")
    up.UserProfile(address="Señora", notes="Doctora").save()
    result = repl.cmd_perfil("")
    assert "Señora" in result
    assert "Doctora" in result


def test_cmd_perfil_tratamiento(tmp_path, monkeypatch):
    import nova.core.nova_user_profile as up
    import nova.cli.repl as repl
    monkeypatch.setattr(up, "USERS_DIR", tmp_path / "users")
    up.UserProfile(address="Señor").save()
    result = repl.cmd_perfil("tratamiento Comandante")
    assert "Comandante" in result
    loaded = up.UserProfile.load()
    assert loaded.address == "Comandante"


def test_cmd_perfil_in_slash_commands():
    from nova.cli.repl import SLASH_COMMANDS
    assert "/perfil" in SLASH_COMMANDS
    assert "/profile" in SLASH_COMMANDS


def test_onboarding_creates_profile(tmp_path, monkeypatch):
    """_run_onboarding crea el perfil con las respuestas del usuario."""
    import nova.core.nova_user_profile as up
    import nova.cli.repl as repl
    monkeypatch.setattr(up, "USERS_DIR", tmp_path / "users")

    responses = iter(["Señora", "Desarrolladora Python"])

    def fake_read(prompt=""):
        return next(responses)

    repl._run_onboarding(fake_read)
    profile = up.UserProfile.load()
    assert profile is not None
    assert profile.address == "Señora"
    assert "Python" in profile.notes


def test_onboarding_enter_defaults_to_senor(tmp_path, monkeypatch):
    import nova.core.nova_user_profile as up
    import nova.cli.repl as repl
    monkeypatch.setattr(up, "USERS_DIR", tmp_path / "users")

    responses = iter(["", ""])  # Enter on both → defaults

    def fake_read(prompt=""):
        return next(responses)

    repl._run_onboarding(fake_read)
    profile = up.UserProfile.load()
    assert profile.address == "Señor"


# ════════════════════════════════════════════════════════════════════════════
# 7. Multi-usuario
# ════════════════════════════════════════════════════════════════════════════

def test_set_active_user_persists(tmp_path, monkeypatch):
    import nova.core.nova_user_profile as up
    monkeypatch.setattr(up, "USERS_DIR", tmp_path / "users")
    monkeypatch.setattr(up, "_ACTIVE_USER_FILE", tmp_path / "active_user")
    up.UserProfile(id="default", address="Señor").save()
    up.UserProfile(id="maria", address="Señora").save()
    up.set_active_user("maria")
    assert up.get_active_user_id() == "maria"
    assert (tmp_path / "active_user").read_text() == "maria"


def test_get_active_profile_returns_correct_user(tmp_path, monkeypatch):
    import nova.core.nova_user_profile as up
    monkeypatch.setattr(up, "USERS_DIR", tmp_path / "users")
    monkeypatch.setattr(up, "_ACTIVE_USER_FILE", tmp_path / "active_user")
    up.UserProfile(id="default", address="Señor").save()
    up.UserProfile(id="pedro", address="Doctor").save()
    up.set_active_user("pedro")
    profile = up.get_active_profile()
    assert profile.address == "Doctor"


def test_cmd_usuario_lista(tmp_path, monkeypatch):
    import nova.core.nova_user_profile as up
    import nova.cli.repl as repl
    monkeypatch.setattr(up, "USERS_DIR", tmp_path / "users")
    monkeypatch.setattr(up, "_ACTIVE_USER_FILE", tmp_path / "active_user")
    up.UserProfile(id="default", address="Señor").save()
    up.UserProfile(id="ana", address="Señora").save()
    up._active_user_id = "default"
    result = repl.cmd_usuario("")
    assert "default" in result
    assert "ana" in result


def test_cmd_usuario_cambiar(tmp_path, monkeypatch):
    import nova.core.nova_user_profile as up
    import nova.cli.repl as repl
    monkeypatch.setattr(up, "USERS_DIR", tmp_path / "users")
    monkeypatch.setattr(up, "_ACTIVE_USER_FILE", tmp_path / "active_user")
    up.UserProfile(id="default", address="Señor").save()
    up.UserProfile(id="ana", address="Señora").save()
    up._active_user_id = "default"
    result = repl.cmd_usuario("cambiar ana")
    assert "ana" in result
    assert up.get_active_user_id() == "ana"


def test_cmd_usuario_cambiar_nonexistent(tmp_path, monkeypatch):
    import nova.core.nova_user_profile as up
    import nova.cli.repl as repl
    monkeypatch.setattr(up, "USERS_DIR", tmp_path / "users")
    up.UserProfile(id="default", address="Señor").save()
    result = repl.cmd_usuario("cambiar noexiste")
    assert "no encontrado" in result.lower()


def test_cmd_usuario_nuevo_wizard(tmp_path, monkeypatch):
    import nova.core.nova_user_profile as up
    import nova.cli.repl as repl
    monkeypatch.setattr(up, "USERS_DIR", tmp_path / "users")

    # Start wizard
    result = repl.cmd_usuario("nuevo carlos")
    assert "carlos" in result
    assert repl._WIZARD_STATE.get("type") == "usuario_nuevo"

    # Step 0 — address
    repl._wizard_handle("Doctor")
    # Step 1 — notes (completes wizard)
    final = repl._wizard_handle("Médico especialista")
    assert "carlos" in final
    p = up.UserProfile.load("carlos")
    assert p is not None
    assert p.address == "Doctor"
    assert "Médico" in p.notes
    assert not repl._WIZARD_STATE


def test_cmd_usuario_borrar(tmp_path, monkeypatch):
    import shutil
    import nova.core.nova_user_profile as up
    import nova.cli.repl as repl
    monkeypatch.setattr(up, "USERS_DIR", tmp_path / "users")
    monkeypatch.setattr(up, "_ACTIVE_USER_FILE", tmp_path / "active_user")
    up.UserProfile(id="default", address="Señor").save()
    up.UserProfile(id="temp", address="Señora").save()
    up._active_user_id = "default"
    result = repl.cmd_usuario("borrar temp")
    assert "eliminado" in result.lower()
    assert not up.UserProfile.exists("temp")


def test_cmd_usuario_borrar_default_rejected(tmp_path, monkeypatch):
    import nova.core.nova_user_profile as up
    import nova.cli.repl as repl
    monkeypatch.setattr(up, "USERS_DIR", tmp_path / "users")
    result = repl.cmd_usuario("borrar default")
    assert "no se puede" in result.lower()


def test_cmd_usuario_in_slash_commands():
    from nova.cli.repl import SLASH_COMMANDS
    assert "/usuario" in SLASH_COMMANDS
    assert "/user" in SLASH_COMMANDS


def test_list_users_multi(tmp_path, monkeypatch):
    import nova.core.nova_user_profile as up
    monkeypatch.setattr(up, "USERS_DIR", tmp_path / "users")
    up.UserProfile(id="default").save()
    up.UserProfile(id="user2").save()
    up.UserProfile(id="user3").save()
    users = up.UserProfile.list_users()
    assert set(users) == {"default", "user2", "user3"}
