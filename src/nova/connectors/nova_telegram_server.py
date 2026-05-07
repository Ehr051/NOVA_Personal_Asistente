"""
nova_telegram_server.py
───────────────────────
Telegram bidireccional para Nova.

Dos modos (configurables, ambos pueden correr juntos):

  MODO 1 — Polling directo (default si TELEGRAM_BOT_TOKEN está en .env)
    • Hace long-polling a getUpdates de la Bot API
    • No requiere n8n ni webhook público
    • Solo responde al TELEGRAM_CHAT_ID configurado (seguridad)

  MODO 2 — Webhook HTTP para n8n (opcional)
    • Escucha POST 127.0.0.1:7891/telegram-in
    • n8n actúa de intermediario (Telegram Trigger → Nova → Telegram Send)

Configuración (.env):
    TELEGRAM_BOT_TOKEN=...          # activa el modo polling automáticamente
    TELEGRAM_CHAT_ID=...            # chat autorizado (filtra otros)
    NOVA_TELEGRAM_PORT=7891         # puerto webhook n8n (default: 7891)
    NOVA_TELEGRAM_SERVER=1          # 0 deshabilita ambos modos
    NOVA_TELEGRAM_POLL_ONLY=0       # 1 deshabilita el webhook HTTP
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Callable

logger = logging.getLogger(__name__)

_BOT_TOKEN  = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
_CHAT_ID    = os.getenv("TELEGRAM_CHAT_ID", "").strip()
_PORT       = int(os.getenv("NOVA_TELEGRAM_PORT", "7891"))
_SECRET     = os.getenv("N8N_WEBHOOK_SECRET", "")
_ENABLED    = os.getenv("NOVA_TELEGRAM_SERVER", "1").strip() not in ("0", "false", "no")
_POLL_ONLY  = os.getenv("NOVA_TELEGRAM_POLL_ONLY", "0").strip() not in ("0", "false", "no")

_TG_API = "https://api.telegram.org/bot{token}/{method}"

# Inyectado por repl.py al arrancar
_process_fn: Callable[[str], str] | None = None

_server_instance: HTTPServer | None = None
_server_thread:   threading.Thread | None = None
_poll_thread:     threading.Thread | None = None
_poll_running:    bool = False


# ─── Helpers Telegram API ─────────────────────────────────────────────────────

def _tg_call(method: str, body: dict, timeout: int = 10) -> dict:
    url  = _TG_API.format(token=_BOT_TOKEN, method=method)
    data = json.dumps(body).encode()
    req  = urllib.request.Request(url, data=data,
                                  headers={"Content-Type": "application/json"},
                                  method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": f"HTTP {e.code}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _tg_send(chat_id: str, text: str) -> None:
    if not _BOT_TOKEN:
        return
    # Telegram limita a 4096 chars por mensaje
    for chunk in [text[i:i+4000] for i in range(0, len(text), 4000)]:
        _tg_call("sendMessage", {
            "chat_id":    chat_id,
            "text":       chunk,
            "parse_mode": "Markdown",
        })


def _strip_via(text: str) -> str:
    if "\n\n[via " in text:
        return text.rsplit("\n\n[via ", 1)[0]
    return text


# ─── Modo 1: Long-polling directo ────────────────────────────────────────────

def _poll_loop() -> None:
    """Hace long-polling a getUpdates y procesa mensajes entrantes."""
    global _poll_running
    offset = 0
    logger.info("[TelegramPoll] Iniciado — escuchando mensajes de Telegram")

    while _poll_running:
        try:
            resp = _tg_call(
                "getUpdates",
                {"offset": offset, "timeout": 25, "allowed_updates": ["message"]},
                timeout=35,
            )
        except Exception as e:
            logger.warning("[TelegramPoll] Error getUpdates: %s", e)
            time.sleep(5)
            continue

        if not resp.get("ok"):
            logger.warning("[TelegramPoll] API error: %s", resp.get("error", resp))
            time.sleep(5)
            continue

        for update in resp.get("result", []):
            offset = update["update_id"] + 1
            msg = update.get("message", {})
            text = (msg.get("text") or "").strip()
            chat_id = str(msg.get("chat", {}).get("id", ""))
            from_name = (msg.get("from") or {}).get("username") or \
                        (msg.get("from") or {}).get("first_name", "unknown")

            if not text or not chat_id:
                continue

            # Seguridad: solo responder al chat autorizado
            if _CHAT_ID and chat_id != _CHAT_ID:
                logger.warning("[TelegramPoll] Mensaje de chat no autorizado: %s", chat_id)
                continue

            logger.info("[TelegramPoll] %s: %s", from_name, text[:80])

            if _process_fn is None:
                _tg_send(chat_id, "⚠️ Nova todavía está iniciando, intentá en un momento.")
                continue

            try:
                response = _strip_via(_process_fn(text))
            except Exception as e:
                logger.exception("[TelegramPoll] Error procesando mensaje")
                _tg_send(chat_id, f"⚠️ Error interno: {e}")
                continue

            _tg_send(chat_id, response)


# ─── Modo 2: Webhook HTTP para n8n ───────────────────────────────────────────

def set_processor(fn: Callable[[str], str]) -> None:
    global _process_fn
    _process_fn = fn


class _TelegramHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
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

        if _SECRET:
            if self.headers.get("X-Nova-Secret", "") != _SECRET:
                self._send_json(401, {"error": "Unauthorized"})
                return

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

        logger.info("[TelegramWebhook] %s: %s", from_, text[:80])

        if _process_fn is None:
            self._send_json(503, {"error": "Nova processor not ready"})
            return

        try:
            response = _strip_via(_process_fn(text))
        except Exception as e:
            logger.exception("[TelegramWebhook] Error procesando mensaje")
            self._send_json(500, {"error": str(e)})
            return

        self._send_json(200, {"response": response, "chat_id": chat_id, "from": from_})


# ─── Arranque ─────────────────────────────────────────────────────────────────

def start(process_fn: Callable[[str], str] | None = None) -> bool:
    """
    Arranca ambos modos (polling + webhook HTTP).
    Retorna True si al menos uno arrancó.
    """
    global _server_instance, _server_thread, _poll_thread, _poll_running

    if not _ENABLED:
        return False

    if process_fn is not None:
        set_processor(process_fn)

    started = False

    # Modo 1: polling directo (si hay token)
    if _BOT_TOKEN and _poll_thread is None:
        _poll_running = True
        _poll_thread = threading.Thread(
            target=_poll_loop, daemon=True, name="nova-telegram-poll"
        )
        _poll_thread.start()
        started = True

    # Modo 2: webhook HTTP (si no es poll-only)
    if not _POLL_ONLY and _server_instance is None:
        try:
            _server_instance = HTTPServer(("127.0.0.1", _PORT), _TelegramHandler)
            _server_thread = threading.Thread(
                target=_server_instance.serve_forever,
                daemon=True, name="nova-telegram-webhook"
            )
            _server_thread.start()
            started = True
        except OSError as e:
            logger.warning("[TelegramWebhook] No se pudo abrir puerto %d: %s", _PORT, e)

    return started


def stop() -> None:
    global _server_instance, _server_thread, _poll_running, _poll_thread
    _poll_running = False
    _poll_thread  = None
    if _server_instance:
        _server_instance.shutdown()
        _server_instance = None
        _server_thread   = None


def is_running() -> bool:
    return _poll_thread is not None or _server_instance is not None


def status() -> str:
    parts = []
    if _poll_thread is not None and _poll_thread.is_alive():
        chat_label = f"chat {_CHAT_ID}" if _CHAT_ID else "todos los chats (sin filtro)"
        parts.append(f"Polling activo — escuchando {chat_label}")
    if _server_instance is not None:
        parts.append(f"Webhook HTTP activo en 127.0.0.1:{_PORT}/telegram-in")
    if not parts:
        token_hint = "sin TELEGRAM_BOT_TOKEN" if not _BOT_TOKEN else "detenido"
        return f"Telegram Receive inactivo ({token_hint})"
    return " | ".join(parts)
