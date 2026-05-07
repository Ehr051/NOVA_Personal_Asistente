"""
Tests del servidor Telegram Receive.
No requieren n8n ni Telegram real — todo en proceso con un puerto efímero.
"""
import json
import sys
import threading
import urllib.request
from http.server import HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC  = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import nova.connectors.nova_telegram_server as tg_server


def _free_port() -> int:
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _start_test_server(process_fn, port: int) -> HTTPServer:
    tg_server.set_processor(process_fn)
    server = HTTPServer(("127.0.0.1", port), tg_server._TelegramHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server


def _post(port: int, body: dict, headers: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(body).encode()
    h = {"Content-Type": "application/json", **(headers or {})}
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/telegram-in",
        data=data, headers=h, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_valid_message_routed_to_processor():
    port = _free_port()
    srv  = _start_test_server(lambda t: f"echo: {t}", port)
    try:
        code, body = _post(port, {"text": "hola", "from": "user1", "chat_id": "123"})
        assert code == 200
        assert body["response"] == "echo: hola"
        assert body["chat_id"] == "123"
        assert body["from"] == "user1"
    finally:
        srv.shutdown()


def test_via_suffix_stripped():
    port = _free_port()
    srv  = _start_test_server(lambda t: f"respuesta\n\n[via groq]", port)
    try:
        code, body = _post(port, {"text": "test", "from": "u", "chat_id": "1"})
        assert code == 200
        assert body["response"] == "respuesta"
        assert "[via" not in body["response"]
    finally:
        srv.shutdown()


def test_empty_text_returns_400():
    port = _free_port()
    srv  = _start_test_server(lambda t: "ok", port)
    try:
        code, body = _post(port, {"text": "", "from": "u", "chat_id": "1"})
        assert code == 400
        assert "error" in body
    finally:
        srv.shutdown()


def test_missing_text_returns_400():
    port = _free_port()
    srv  = _start_test_server(lambda t: "ok", port)
    try:
        code, body = _post(port, {"from": "u", "chat_id": "1"})
        assert code == 400
    finally:
        srv.shutdown()


def test_unknown_path_returns_404():
    port = _free_port()
    srv  = _start_test_server(lambda t: "ok", port)
    try:
        data = json.dumps({"text": "x"}).encode()
        req  = urllib.request.Request(
            f"http://127.0.0.1:{port}/otro-path",
            data=data, headers={"Content-Type": "application/json"}, method="POST"
        )
        try:
            urllib.request.urlopen(req, timeout=5)
            assert False, "Expected 404"
        except urllib.error.HTTPError as e:
            assert e.code == 404
    finally:
        srv.shutdown()


def test_secret_auth_rejects_wrong_token():
    port = _free_port()
    original_secret = tg_server._SECRET
    tg_server._SECRET = "mi-secreto"
    srv = _start_test_server(lambda t: "ok", port)
    try:
        code, body = _post(port, {"text": "hola", "from": "u", "chat_id": "1"},
                           headers={"X-Nova-Secret": "wrong"})
        assert code == 401
    finally:
        tg_server._SECRET = original_secret
        srv.shutdown()


def test_secret_auth_accepts_correct_token():
    port = _free_port()
    original_secret = tg_server._SECRET
    tg_server._SECRET = "mi-secreto"
    srv = _start_test_server(lambda t: "ok", port)
    try:
        code, body = _post(port, {"text": "hola", "from": "u", "chat_id": "1"},
                           headers={"X-Nova-Secret": "mi-secreto"})
        assert code == 200
    finally:
        tg_server._SECRET = original_secret
        srv.shutdown()
