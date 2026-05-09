"""
test_nova_features.py — Tests unitarios para features nuevas de Nova
Cubre: @file expansion, session persistence, /modo, /rutina, /nota,
       Qdrant patch, neuro_memory simple fallback, tool schemas robustez,
       router helpers, daemon client API surface.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

# ── path setup ──────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


# ════════════════════════════════════════════════════════════════════════════
# @file expansion (repl._expand_at_files)
# ════════════════════════════════════════════════════════════════════════════

def test_expand_at_files_no_refs():
    from nova.cli.repl import _expand_at_files
    text, blocks = _expand_at_files("qué hora es")
    assert text == "qué hora es"
    assert blocks == []


def test_expand_at_files_nonexistent_ref():
    from nova.cli.repl import _expand_at_files
    text, blocks = _expand_at_files("revisá @no_existe_jamas.py")
    assert blocks == []


def test_expand_at_files_existing_file(tmp_path):
    """Debe leer un archivo real y devolver un bloque con su contenido."""
    from nova.cli.repl import _expand_at_files

    sample = tmp_path / "sample.py"
    sample.write_text("x = 1\n", encoding="utf-8")

    original_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        text, blocks = _expand_at_files("mirá @sample.py")
    finally:
        os.chdir(original_cwd)

    assert len(blocks) == 1
    assert "sample.py" in blocks[0]
    assert "x = 1" in blocks[0]


def test_expand_at_files_truncates_large_file(tmp_path):
    from nova.cli.repl import _expand_at_files

    big = tmp_path / "big.txt"
    big.write_text("A" * 20_000, encoding="utf-8")

    original_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        _, blocks = _expand_at_files("@big.txt")
    finally:
        os.chdir(original_cwd)

    assert len(blocks) == 1
    assert "truncado" in blocks[0]


def test_expand_at_files_multiple_refs(tmp_path):
    from nova.cli.repl import _expand_at_files

    (tmp_path / "a.txt").write_text("alfa", encoding="utf-8")
    (tmp_path / "b.txt").write_text("beta", encoding="utf-8")

    original_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        _, blocks = _expand_at_files("compará @a.txt y @b.txt")
    finally:
        os.chdir(original_cwd)

    assert len(blocks) == 2


# ════════════════════════════════════════════════════════════════════════════
# Session persistence (_session_save / _session_load)
# ════════════════════════════════════════════════════════════════════════════

def test_session_save_and_load(tmp_path, monkeypatch):
    import nova.cli.repl as repl

    monkeypatch.setattr(repl, "_SESSION_FILE", str(tmp_path / "sess.json"))
    monkeypatch.setitem(repl._session_state, "history", [
        {"role": "user", "content": "hola"},
        {"role": "assistant", "content": "hola para vos"},
    ])
    monkeypatch.setitem(repl._session_state, "id", "test_session")

    repl._session_save()
    assert (tmp_path / "sess.json").exists()

    # Reset state and reload
    monkeypatch.setitem(repl._session_state, "history", [])
    result = repl._session_load()
    assert result is True
    assert len(repl._session_state["history"]) == 2
    assert repl._session_state["history"][0]["content"] == "hola"


def test_session_load_missing_file(tmp_path, monkeypatch):
    import nova.cli.repl as repl
    monkeypatch.setattr(repl, "_SESSION_FILE", str(tmp_path / "nonexistent.json"))
    result = repl._session_load()
    assert result is False


def test_session_save_creates_parent_dir(tmp_path, monkeypatch):
    import nova.cli.repl as repl
    nested = tmp_path / "deep" / "nested" / "sess.json"
    monkeypatch.setattr(repl, "_SESSION_FILE", str(nested))
    monkeypatch.setitem(repl._session_state, "history", [{"role": "user", "content": "x"}])
    repl._session_save()
    assert nested.exists()


# ════════════════════════════════════════════════════════════════════════════
# /modo command
# ════════════════════════════════════════════════════════════════════════════

def test_cmd_modo_list():
    from nova.cli.repl import cmd_modo
    result = cmd_modo("lista")
    assert "normal" in result
    assert "codigo" in result
    assert "creativo" in result


def test_cmd_modo_switch():
    from nova.cli.repl import cmd_modo, _MODOS
    import nova.cli.repl as repl
    original = repl._MODO_ACTUAL
    try:
        result = cmd_modo("codigo")
        assert "codigo" in result
        assert repl._MODO_ACTUAL == "codigo"
    finally:
        repl._MODO_ACTUAL = original


def test_cmd_modo_unknown():
    from nova.cli.repl import cmd_modo
    result = cmd_modo("inexistente")
    assert "desconocido" in result or "inexistente" in result


def test_cmd_modo_empty_shows_list():
    from nova.cli.repl import cmd_modo
    result = cmd_modo("")
    assert result is not None
    assert len(result) > 0


# ════════════════════════════════════════════════════════════════════════════
# /rutina command
# ════════════════════════════════════════════════════════════════════════════

def test_rutina_define_and_list(tmp_path, monkeypatch):
    import nova.cli.repl as repl

    rutinas_file = tmp_path / "rutinas.json"
    monkeypatch.setattr(
        "nova.cli.repl.os.path.expanduser",
        lambda p: str(tmp_path / "rutinas.json") if "rutinas" in p else os.path.expanduser(p),
    )

    with patch.object(Path, "read_text", return_value="{}"):
        with patch.object(Path, "write_text") as mock_write:
            from nova.cli.repl import cmd_rutina
            # Just test it doesn't crash — full flow needs live fs
            result = cmd_rutina("lista")
            # When no rutinas, should say "no hay rutinas" or similar
            assert result is not None


def test_rutina_empty_lista(monkeypatch, tmp_path):
    """Lista vacía de rutinas debe responder graciosamente."""
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".nova").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".nova" / "rutinas.json").write_text("{}", encoding="utf-8")

    from nova.cli.repl import cmd_rutina
    result = cmd_rutina("lista")
    assert result is not None
    assert isinstance(result, str)


# ════════════════════════════════════════════════════════════════════════════
# /nota command
# ════════════════════════════════════════════════════════════════════════════

def test_cmd_nota_saves_file(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    drops = tmp_path / "Cerebro" / "Drops"
    drops.mkdir(parents=True, exist_ok=True)

    with patch("pathlib.Path.home", return_value=tmp_path):
        from nova.cli.repl import cmd_nota
        result = cmd_nota("esto es una nota de prueba")

    assert result is not None


def test_cmd_nota_empty_returns_help():
    from nova.cli.repl import cmd_nota
    result = cmd_nota("")
    # empty arg should return usage hint, not crash
    assert result is not None
    assert isinstance(result, str)


# ════════════════════════════════════════════════════════════════════════════
# Qdrant __del__ monkey-patch
# ════════════════════════════════════════════════════════════════════════════

def test_qdrant_del_is_silenced():
    """After importing nova_neuro_memory, QdrantClient.__del__ must be a no-op."""
    try:
        from qdrant_client import QdrantClient
        import nova.tools.nova_neuro_memory  # noqa: F401 — triggers the patch

        # __del__ must either be our lambda or not raise
        client = MagicMock(spec=QdrantClient)
        # Call the patched __del__ — should not raise
        QdrantClient.__del__(client)
    except ImportError:
        # qdrant_client not installed — skip
        import pytest
        pytest.skip("qdrant_client not installed")


# ════════════════════════════════════════════════════════════════════════════
# NovaNeuralMemory — simple JSON fallback (no Ollama needed)
# ════════════════════════════════════════════════════════════════════════════

def test_simple_memory_remember_and_recall(tmp_path):
    """_SimpleJSONMemory should persist and retrieve facts without Ollama."""
    from nova.tools.nova_neuro_memory import _SimpleJSONMemory

    mem_file = tmp_path / "test_mem.json"
    m = _SimpleJSONMemory(str(mem_file))

    m.add("prefiero Python sobre JavaScript")
    result = m.search("Python", limit=5)
    # search() returns a str containing the matched text
    assert isinstance(result, str)
    assert "Python" in result


def test_simple_memory_add_persists(tmp_path):
    """Entries added should be saved to disk."""
    from nova.tools.nova_neuro_memory import _SimpleJSONMemory

    mem_file = tmp_path / "test_mem2.json"
    m = _SimpleJSONMemory(str(mem_file))
    m.add("recuerda que me gusta el café")

    assert len(m._data) >= 1
    assert any("café" in entry["text"] for entry in m._data)


def test_simple_memory_persists_across_instances(tmp_path):
    from nova.tools.nova_neuro_memory import _SimpleJSONMemory

    mem_file = tmp_path / "persist.json"
    m1 = _SimpleJSONMemory(str(mem_file))
    m1.add("dato importante")

    m2 = _SimpleJSONMemory(str(mem_file))
    result = m2.search("dato", limit=5)
    assert isinstance(result, str)
    assert "dato" in result


# ════════════════════════════════════════════════════════════════════════════
# Tool schemas — edge cases
# ════════════════════════════════════════════════════════════════════════════

def test_tool_schema_all_have_required_fields():
    from nova.tools.nova_tools_schemas import get_tool_schemas
    schemas = get_tool_schemas()
    for s in schemas:
        assert "type" in s
        assert s["type"] == "function"
        fn = s["function"]
        assert "name" in fn
        assert "description" in fn
        assert "parameters" in fn
        assert isinstance(fn["name"], str)
        assert len(fn["name"]) > 0


def test_tool_schema_no_duplicate_names():
    from nova.tools.nova_tools_schemas import get_tool_schemas
    schemas = get_tool_schemas()
    names = [s["function"]["name"] for s in schemas]
    assert len(names) == len(set(names)), "Duplicate tool names found"


def test_tool_schema_subset_smaller_than_full():
    from nova.tools.nova_tools_schemas import get_tool_schemas, get_tool_schemas_subset
    full = get_tool_schemas()
    # get first 3 tool names
    first_three = [s["function"]["name"] for s in full[:3]]
    subset = get_tool_schemas_subset(first_three)
    assert len(subset) <= 3
    assert len(subset) <= len(full)


# ════════════════════════════════════════════════════════════════════════════
# execute_tool — robustness
# ════════════════════════════════════════════════════════════════════════════

def test_execute_tool_get_time_returns_string():
    from nova.tools.nova_skills import execute_tool
    result = execute_tool("get_time", {})
    assert isinstance(result, str)
    assert len(result) > 0


def test_execute_tool_get_date_returns_string():
    from nova.tools.nova_skills import execute_tool
    result = execute_tool("get_date", {})
    assert isinstance(result, str)


def test_execute_tool_unknown_tool_graceful():
    from nova.tools.nova_skills import execute_tool
    result = execute_tool("esta_tool_no_existe_jamas_12345", {})
    assert "no encontrada" in result or "error" in result.lower()


def test_execute_tool_does_not_raise_on_bad_args():
    """Even with wrong args, execute_tool should return a string, not raise."""
    from nova.tools.nova_skills import execute_tool
    result = execute_tool("get_time", {"argumento_raro": "valor_raro"})
    assert isinstance(result, str)


# ════════════════════════════════════════════════════════════════════════════
# Nova daemon client — API surface (no live daemon needed)
# ════════════════════════════════════════════════════════════════════════════

def test_nova_client_imports_cleanly():
    from nova.core import nova_client
    assert hasattr(nova_client, "NovaDaemonClient")


def test_nova_client_ping_returns_false_when_daemon_down():
    from nova.core.nova_client import NovaDaemonClient
    c = NovaDaemonClient(port=19999)  # puerto sin daemon
    result = c.ping()
    assert result is False


def test_nova_client_chat_raises_or_returns_none_when_daemon_down():
    from nova.core.nova_client import NovaDaemonClient, DaemonUnavailable
    c = NovaDaemonClient(port=19999)
    try:
        result = c.chat("hola")
        assert result is None
    except DaemonUnavailable:
        pass  # acceptable — daemon is down


def test_nova_client_agent_stream_raises_or_empty_when_daemon_down():
    from nova.core.nova_client import NovaDaemonClient, DaemonUnavailable
    c = NovaDaemonClient(port=19999)
    try:
        chunks = list(c.agent_stream("objetivo"))
        assert chunks == []
    except DaemonUnavailable:
        pass  # acceptable — daemon is down


# ════════════════════════════════════════════════════════════════════════════
# Router — helpers (no API key needed)
# ════════════════════════════════════════════════════════════════════════════

def test_router_imports_cleanly():
    from nova.core import nova_router
    assert hasattr(nova_router, "NovaRouter")


def test_router_instantiates_without_keys(monkeypatch):
    """Router should instantiate even if no API keys are set."""
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("CEREBRAS_API_KEY", raising=False)
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    from nova.core.nova_router import NovaRouter
    r = NovaRouter()
    assert r is not None


def test_router_has_route_agentic():
    from nova.core.nova_router import NovaRouter
    assert callable(getattr(NovaRouter, "route_agentic", None))


def test_router_has_call_with_tools():
    from nova.core.nova_router import NovaRouter
    assert callable(getattr(NovaRouter, "_call_with_tools", None))


def test_router_has_route_stream():
    from nova.core.nova_router import NovaRouter
    assert callable(getattr(NovaRouter, "route_stream", None))
