"""
test_tool_calling.py
─────────────────────
Smoke tests para las features de tool calling nativo (v3.8):
  - nova_tools_schemas: generación de schemas
  - nova_skills: execute_tool
  - nova_router: route_with_tools_simple (sin API — mockea el client)
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
SRC  = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


# ── 1. Schema generation ───────────────────────────────────────────────────────

def test_get_tool_schemas_returns_list():
    from nova.tools.nova_tools_schemas import get_tool_schemas
    schemas = get_tool_schemas()
    assert isinstance(schemas, list)
    assert len(schemas) > 10, "esperamos al menos 10 schemas"


def test_get_tool_schemas_structure():
    from nova.tools.nova_tools_schemas import get_tool_schemas
    schemas = get_tool_schemas()
    for s in schemas[:5]:
        assert s["type"] == "function"
        fn = s["function"]
        assert "name"        in fn
        assert "description" in fn
        assert "parameters"  in fn
        assert fn["parameters"]["type"] == "object"


def test_get_tool_schemas_subset():
    from nova.tools.nova_tools_schemas import get_tool_schemas_subset
    sub = get_tool_schemas_subset(["skill_hora", "get_weather", "crypto"])
    names = [s["function"]["name"] for s in sub]
    assert "skill_hora"  in names
    assert "get_weather" in names
    assert "crypto"      in names
    assert len(sub) == 3


# ── 2. execute_tool ───────────────────────────────────────────────────────────

def test_execute_tool_no_args():
    from nova.tools.nova_skills import execute_tool
    result = execute_tool("skill_hora", {})
    assert isinstance(result, str)
    assert len(result) > 0


def test_execute_tool_with_text_arg():
    from nova.tools.nova_skills import execute_tool
    result = execute_tool("traducir", {"texto": "hello"})
    assert isinstance(result, str)


def test_execute_tool_unknown():
    from nova.tools.nova_skills import execute_tool
    result = execute_tool("herramienta_inexistente_xyz", {})
    assert "no encontrada" in result.lower()


def test_execute_tool_location():
    from nova.tools.nova_skills import execute_tool
    # get_weather hace red — mockeamos para que no falle si no hay internet
    with patch("nova.tools.nova_skills.get_weather", return_value="Soleado 22°C"):
        result = execute_tool("get_weather", {"location": "Buenos Aires"})
    assert isinstance(result, str)


# ── 3. route_with_tools_simple (mock del client) ──────────────────────────────

def test_route_with_tools_simple_returns_dict():
    """Verifica estructura del retorno con un mock que simula tool_calls."""
    from nova.core.nova_router import NovaRouter
    from nova.tools.nova_tools_schemas import get_tool_schemas

    schemas = get_tool_schemas()

    # Mock de la respuesta del LLM con una tool call
    mock_tc = MagicMock()
    mock_tc.id = "call_test_123"
    mock_tc.function.name = "skill_hora"
    mock_tc.function.arguments = "{}"

    mock_msg = MagicMock()
    mock_msg.content = ""
    mock_msg.tool_calls = [mock_tc]

    mock_choice = MagicMock()
    mock_choice.message = mock_msg

    mock_usage = MagicMock()
    mock_usage.total_tokens = 42

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.usage   = mock_usage

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response

    router = NovaRouter.__new__(NovaRouter)
    router._ollama_client   = mock_client
    router._ollama_ready    = True
    router._ollama_models   = {1: ["llama3.2:3b"], 2: ["llama3.2:3b"], 3: ["llama3.2:3b"]}
    router._groq_client     = None
    router._cerebras_client = None
    router._mistral_client  = None
    router._codestral_client = None
    router._deepseek_client  = None
    router._or_client        = None
    router._custom_clients   = []
    router.provider_order    = ["ollama"]
    router.tracker           = MagicMock()
    router.tracker.remaining_pct.return_value = 100.0

    msgs = [{"role": "user", "content": "qué hora es"}]
    result = router.route_with_tools_simple(msgs, schemas[:5], force_tier=1)

    assert isinstance(result, dict)
    assert "tool_calls" in result
    assert "text"       in result
    assert "tokens"     in result
    assert len(result["tool_calls"]) == 1
    assert result["tool_calls"][0]["function"]["name"] == "skill_hora"
    assert result["tokens"] == 42


# ── 4. skill_agente (mock router) ─────────────────────────────────────────────

def test_skill_agente_no_router():
    """Sin router disponible, skill_agente retorna mensaje de error limpio."""
    with patch("nova.tools.nova_skills._router", None):
        from nova.tools.nova_skills import skill_agente
        result = skill_agente("qué hora es")
    assert "no disponible" in result.lower() or "router" in result.lower()
