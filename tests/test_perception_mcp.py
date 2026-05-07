import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from nova.perception import mcp_server


def test_handle_get_all_returns_current_snapshot():
    with mcp_server._lock:
        original = mcp_server._latest_data.copy()
        mcp_server._latest_data.update(
            {
                "gesture": "pinch",
                "face_id": "user",
                "emotion": "focused",
                "screen_text": "Nova ready",
                "timestamp": "2026-05-06T19:00:00",
            }
        )

    try:
        response = mcp_server.handle_request(
            {"jsonrpc": "2.0", "method": "get_all", "params": {}, "id": 7}
        )
    finally:
        with mcp_server._lock:
            mcp_server._latest_data.clear()
            mcp_server._latest_data.update(original)

    assert response["jsonrpc"] == "2.0"
    assert response["id"] == 7
    assert response["result"]["gesture"] == "pinch"
    assert response["result"]["face_id"] == "user"
    assert response["result"]["emotion"] == "focused"
    assert response["result"]["screen_text"] == "Nova ready"


def test_handle_known_methods_have_safe_defaults():
    cases = {
        "get_gesture": ("gesture", "none"),
        "get_face_id": ("face_id", "unknown"),
        "get_emotion": ("emotion", "neutral"),
        "get_screen_text": ("screen_text", ""),
    }

    for method, (field, default) in cases.items():
        response = mcp_server.handle_request(
            {"jsonrpc": "2.0", "method": method, "params": {}, "id": method}
        )

        assert response["jsonrpc"] == "2.0"
        assert response["id"] == method
        assert field in response["result"]
        assert response["result"][field] is not None
        if mcp_server._latest_data.get(field) is None:
            assert response["result"][field] == default


def test_unknown_method_returns_json_rpc_error():
    response = mcp_server.handle_request(
        {"jsonrpc": "2.0", "method": "missing_tool", "params": {}, "id": 99}
    )

    assert response["jsonrpc"] == "2.0"
    assert response["id"] == 99
    assert response["error"]["code"] == -32601
    assert "Method not found" in response["error"]["message"]


def test_analyze_camera_once_is_on_demand(monkeypatch):
    calls = []

    def fake_vision_analizar_on_demand(**kwargs):
        calls.append(kwargs)
        return "Veo una taza roja sobre la mesa."

    monkeypatch.setattr(
        mcp_server,
        "_vision_analizar_on_demand",
        fake_vision_analizar_on_demand,
    )

    response = mcp_server.handle_request(
        {
            "jsonrpc": "2.0",
            "method": "analyze_camera_once",
            "params": {
                "prompt": "Qué objeto tengo enfrente?",
                "camara_idx": 1,
                "guardar": True,
                "warmup_sec": 2,
            },
            "id": 101,
        }
    )

    assert response["jsonrpc"] == "2.0"
    assert response["id"] == 101
    assert response["result"]["source"] == "camera"
    assert response["result"]["camera_index"] == 1
    assert response["result"]["analysis"] == "Veo una taza roja sobre la mesa."
    assert calls == [
        {
            "camara": True,
            "prompt": "Qué objeto tengo enfrente?",
            "guardar": True,
            "camara_idx": 1,
            "warmup_sec": 2.0,
        }
    ]


def test_analyze_screen_once_is_on_demand(monkeypatch):
    calls = []

    def fake_vision_analizar_on_demand(**kwargs):
        calls.append(kwargs)
        return "Veo un editor con tests abiertos."

    monkeypatch.setattr(
        mcp_server,
        "_vision_analizar_on_demand",
        fake_vision_analizar_on_demand,
    )

    response = mcp_server.handle_request(
        {
            "jsonrpc": "2.0",
            "method": "analyze_screen_once",
            "params": {"prompt": "Hay errores visibles?"},
            "id": 102,
        }
    )

    assert response["jsonrpc"] == "2.0"
    assert response["id"] == 102
    assert response["result"]["source"] == "screen"
    assert response["result"]["analysis"] == "Veo un editor con tests abiertos."
    assert calls == [
        {
            "camara": False,
            "prompt": "Hay errores visibles?",
            "guardar": False,
        }
    ]
