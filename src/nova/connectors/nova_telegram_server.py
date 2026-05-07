"""
nova_telegram_server.py
───────────────────────
Servidor HTTP liviano que recibe mensajes de Telegram via n8n
y los procesa como input de Nova (skills + LLM).

Flujo:
    Telegram → n8n Telegram Trigger
             → POST /telegram-in  (este servidor)
             → Nova procesa
             → {"response": "..."} a n8n
             → n8n Telegram.sendMessage → usuario

Configuración (.env):
    NOVA_TELEGRAM_PORT=7891          # puerto del servidor (default: 7891)
    N8N_WEBHOOK_SECRET=...           # si usás auth en n8n, misma key
    NOVA_TELEGRAM_SERVER=1           # poner en 0 para deshabilitar
"""

from __future__ import annotations

import json
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Callable

logger = logging.getLogger(__name__)

_PORT    = int(os.getenv("NOVA_TELEGRAM_PORT", "7891"))
_SECRET  = os.getenv("N8N_WEBHOOK_SECRET", "")
_ENABLED = os.getenv("NOVA_TELEGRAM_SERVER", "1").strip() not in ("0", "false", "no")

# Inyectado por repl.py al arrancar
_process_fn: Callable[[str], str] | None = None

_server_instance: HTTPServer | None = None
_server_thread:   threading.Thread | None = None


def set_processor(fn: Callable[[str], str]) -> None:
    """Registra la función que procesa texto y devuelve respuesta de Nova."""
    global _process_fn
    _process_fn = fn


class _TelegramHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # silenciar log de acceso HTTP
        pass

    def _send_json(self, code: int, body: dict) -> None:
        data = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        if self.path not in ("/telegram-in", "/telegram-in/"):
            self._send_json(404, {"error": "Not found"})
            return

        # Autenticación opcional
        if _SECRET:
            token = self.headers.get("X-Nova-Secret", "")
            if token != _SECRET:
                self._send_json(401, {"error": "Unauthorized"})
                return

        # Leer body
        length = int(self.headers.get("Content-Length", 0))
        try:
            payload = json.loads(self.rfile.read(length).decode())
        except Exception:
            self._send_json(400, {"error": "Invalid JSON"})
            return

        text    = (payload.get("text") or "").strip()
        from_   = payload.get("from", "unknown")
        chat_id = payload.get("chat_id", "")

        if not text:
            self._send_json(400, {"error": "Empty text"})
            return

        logger.info("[Telegram→Nova] %s: %s", from_, text[:80])

        if _process_fn is None:
            self._send_json(503, {"error": "Nova processor not ready"})
            return

        try:
            response = _process_fn(text)
        except Exception as e:
            logger.exception("[Telegram→Nova] Error procesando mensaje")
            self._send_json(500, {"error": str(e)})
            return

        # Quitar el sufijo "[via provider]" del REPL antes de devolver a Telegram
        if "\n\n[via " in response:
            response = response.rsplit("\n\n[via ", 1)[0]

        self._send_json(200, {
            "response": response,
            "chat_id":  chat_id,
            "from":     from_,
        })


def start(process_fn: Callable[[str], str] | None = None) -> bool:
    """
    Arranca el servidor en un daemon thread.
    Retorna True si arrancó, False si ya estaba corriendo o está deshabilitado.
    """
    global _server_instance, _server_thread

    if not _ENABLED:
        logger.info("[TelegramServer] Deshabilitado (NOVA_TELEGRAM_SERVER=0)")
        return False

    if _server_instance is not None:
        return False

    if process_fn is not None:
        set_processor(process_fn)

    try:
        _server_instance = HTTPServer(("127.0.0.1", _PORT), _TelegramHandler)
    except OSError as e:
        logger.warning("[TelegramServer] No se pudo abrir puerto %d: %s", _PORT, e)
        return False

    _server_thread = threading.Thread(
        target=_server_instance.serve_forever,
        daemon=True,
        name="nova-telegram-server",
    )
    _server_thread.start()
    logger.info("[TelegramServer] Escuchando en 127.0.0.1:%d/telegram-in", _PORT)
    return True


def stop() -> None:
    global _server_instance, _server_thread
    if _server_instance:
        _server_instance.shutdown()
        _server_instance = None
        _server_thread = None


def is_running() -> bool:
    return _server_instance is not None


def status() -> str:
    if is_running():
        return f"Telegram Receive activo en 127.0.0.1:{_PORT}/telegram-in"
    return "Telegram Receive inactivo"
