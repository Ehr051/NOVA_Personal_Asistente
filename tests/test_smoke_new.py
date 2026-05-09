"""
Smoke tests para módulos añadidos en sesiones 7 y 8:
  - Platform adapter
  - Plugin loader
  - Web UI server lifecycle
  - Daemon agent_stream protocol (mock)
  - /doctor command
"""
from __future__ import annotations

import json
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


# ─── Platform adapter ────────────────────────────────────────────────────────

def test_platform_adapter_imports():
    from nova.platform import (
        play_audio, speak_tts, open_application, find_installed_apps,
        close_application, take_screenshot, get_system_volume,
        set_system_volume, mute_system, unmute_system, copy_to_clipboard, PLATFORM,
    )
    assert PLATFORM in ("macos", "windows", "linux")
    assert all(callable(f) for f in [
        play_audio, speak_tts, open_application, find_installed_apps,
        close_application, take_screenshot, get_system_volume,
        set_system_volume, mute_system, unmute_system, copy_to_clipboard,
    ])


def test_platform_find_installed_apps_returns_list():
    from nova.platform import find_installed_apps
    apps = find_installed_apps()
    assert isinstance(apps, list)


# ─── Plugin loader ────────────────────────────────────────────────────────────

def test_plugin_loader_loads_from_dir(tmp_path: Path, monkeypatch):
    plugin_file = tmp_path / "nova_plugin_test_smoke.py"
    plugin_file.write_text(
        """
PLUGIN_META = {"name": "SmokePlugin", "version": "0.1", "description": "test"}

def _handler(texto=""):
    return f"smoke:{texto}"

INTENTS = [(r"smoke test (.*)", _handler, 1)]
TOOL_CATALOG = {"smoke_tool": ("Smoke tool", _handler, "text")}
""",
        encoding="utf-8",
    )

    monkeypatch.setenv("NOVA_PLUGINS_DIR", str(tmp_path))

    from nova.tools import nova_plugin_loader
    nova_plugin_loader._LOADED.clear()
    # Also remove cached module so it gets re-loaded
    import sys as _sys
    for key in list(_sys.modules.keys()):
        if "nova_plugin_test_smoke" in key:
            del _sys.modules[key]

    intents: list = []
    catalog: dict = {}
    count = nova_plugin_loader.load_plugins(intents, catalog, skills_module=None)

    assert count >= 1
    assert "smoke_tool" in catalog
    assert any(p.get("name") == "SmokePlugin" for p in nova_plugin_loader.loaded_plugins())


def test_plugin_loader_no_crash_on_bad_plugin(tmp_path: Path):
    bad_file = tmp_path / "nova_plugin_bad_smoke.py"
    bad_file.write_text("raise RuntimeError('plugin fail')", encoding="utf-8")

    from nova.tools.nova_plugin_loader import load_plugins, _LOADED
    _LOADED.clear()

    intents: list = []
    catalog: dict = {}
    # Should NOT raise — bad plugins are caught and logged
    import os
    old = os.environ.get("NOVA_PLUGINS_DIR")
    os.environ["NOVA_PLUGINS_DIR"] = str(tmp_path)
    try:
        load_plugins(intents, catalog)
    finally:
        if old is None:
            os.environ.pop("NOVA_PLUGINS_DIR", None)
        else:
            os.environ["NOVA_PLUGINS_DIR"] = old


# ─── Web UI ───────────────────────────────────────────────────────────────────

def test_web_server_lifecycle():
    from nova.web import nova_web_server as ws
    if ws.is_running():
        ws.stop()
        time.sleep(0.2)

    ws.start(host="127.0.0.1", port=18080, open_browser=False)
    assert ws.is_running()
    assert "18080" in ws.url()

    # /api/status must return JSON
    import urllib.request
    try:
        with urllib.request.urlopen("http://127.0.0.1:18080/api/status", timeout=3) as r:
            data = json.loads(r.read())
        assert data.get("ok") is True
    finally:
        ws.stop()
        assert not ws.is_running()


def test_web_server_not_double_start():
    from nova.web import nova_web_server as ws
    if ws.is_running():
        ws.stop()
        time.sleep(0.2)

    ws.start(host="127.0.0.1", port=18081, open_browser=False)
    try:
        # Second start should be a no-op, not raise
        ws.start(host="127.0.0.1", port=18081, open_browser=False)
        assert ws.is_running()
    finally:
        ws.stop()


# ─── Daemon agent_stream (mock) ───────────────────────────────────────────────

def test_daemon_agent_stream_handler_yields_progress():
    """NovaDaemon._handle_agent_stream yields chunk + done when skill_agente works."""
    from nova.core.nova_daemon import NovaDaemon

    daemon = NovaDaemon()
    daemon._router = MagicMock()

    def _fake_skill_agente(texto, progress_cb=None):
        if progress_cb:
            progress_cb("paso 1")
            progress_cb("paso 2")
        return "resultado final"

    with patch("nova.tools.nova_skills.skill_agente", _fake_skill_agente):
        results = list(daemon._handle_agent_stream({"goal": "haz algo"}))

    chunks = [r["chunk"] for r in results if r.get("chunk")]
    final  = next((r for r in results if r.get("done")), None)

    assert "paso 1" in chunks
    assert "paso 2" in chunks
    assert final is not None
    assert final.get("ok") is True
    assert "resultado final" in final.get("result", "")


def test_daemon_agent_stream_empty_goal():
    from nova.core.nova_daemon import NovaDaemon
    daemon = NovaDaemon()
    daemon._router = MagicMock()
    results = list(daemon._handle_agent_stream({"goal": ""}))
    assert results[0]["ok"] is False
    assert results[0]["done"] is True


# ─── /doctor command ─────────────────────────────────────────────────────────

def test_doctor_runs_without_crash():
    from nova.cli.repl import cmd_doctor
    output = cmd_doctor("")
    assert "Diagnóstico Nova" in output
    assert "Groq" in output
    assert "Ollama" in output


def test_doctor_fix_runs_without_crash():
    from nova.cli.repl import cmd_doctor
    output = cmd_doctor("--fix")
    assert "Diagnóstico Nova" in output
    assert "--fix" in output or "fix" in output.lower()
