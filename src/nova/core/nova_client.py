"""
nova_client.py — Cliente thin para comunicarse con el Nova Daemon.

Uso típico:
    from nova.core.nova_client import NovaDaemonClient, get_client

    client = get_client()            # singleton auto-inicializado
    if client.ping():
        response = client.chat("hola", session="main")
    else:
        # daemon no corre — fallback a router directo
        ...

El cliente intenta auto-arrancar el daemon si no está corriendo
(a menos que auto_start=False).
"""

from __future__ import annotations

import json
import logging
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

DAEMON_PORT   = int(os.getenv("NOVA_DAEMON_PORT", "7899"))
DAEMON_HOST   = "127.0.0.1"
CONNECT_TIMEOUT = float(os.getenv("NOVA_DAEMON_CONNECT_TIMEOUT", "2.0"))
REQUEST_TIMEOUT = float(os.getenv("NOVA_DAEMON_REQUEST_TIMEOUT", "120.0"))
_DOTNOVA      = Path.home() / ".nova"


class DaemonUnavailable(Exception):
    pass


class NovaDaemonClient:
    """Cliente TCP para el Nova Daemon. Thread-safe (crea conexión por llamada)."""

    def __init__(self, host: str = DAEMON_HOST, port: int = DAEMON_PORT,
                 auto_start: bool = True) -> None:
        self.host       = host
        self.port       = port
        self.auto_start = auto_start

    # ── Conexión ───────────────────────────────────────────────────────────

    def _connect(self) -> socket.socket:
        conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        conn.settimeout(CONNECT_TIMEOUT)
        try:
            conn.connect((self.host, self.port))
        except (ConnectionRefusedError, OSError):
            conn.close()
            raise DaemonUnavailable(f"Daemon no responde en {self.host}:{self.port}")
        conn.settimeout(REQUEST_TIMEOUT)
        return conn

    def _request(self, obj: dict) -> dict:
        conn = self._connect()
        try:
            data = json.dumps(obj, ensure_ascii=False) + "\n"
            conn.sendall(data.encode("utf-8"))
            buf = b""
            while b"\n" not in buf:
                chunk = conn.recv(65536)
                if not chunk:
                    raise DaemonUnavailable("Conexión cerrada antes de respuesta")
                buf += chunk
            line = buf[:buf.index(b"\n")].decode("utf-8", errors="replace")
            return json.loads(line)
        finally:
            try:
                conn.close()
            except OSError:
                pass

    # ── API pública ────────────────────────────────────────────────────────

    def ping(self) -> bool:
        try:
            r = self._request({"type": "ping"})
            return bool(r.get("ok"))
        except (DaemonUnavailable, OSError):
            return False

    def chat(self, message: str, session: str = "default") -> str:
        r = self._request({"type": "chat", "message": message, "session": session})
        if not r.get("ok"):
            raise DaemonUnavailable(r.get("error", "error desconocido"))
        return r.get("result", "")

    def chat_stream(self, message: str, session: str = "default"):
        """
        Generator: yields text chunks token-by-token desde el daemon.
        El daemon debe soportar type=chat_stream.
        Si el daemon no está disponible, lanza DaemonUnavailable.
        """
        conn = self._connect()
        try:
            data = (json.dumps({"type": "chat_stream", "message": message,
                                "session": session}, ensure_ascii=False) + "\n")
            conn.sendall(data.encode("utf-8"))
            buf = b""
            while True:
                chunk = conn.recv(65536)
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    if not line.strip():
                        continue
                    obj = json.loads(line.decode("utf-8", errors="replace"))
                    if not obj.get("ok") and obj.get("error"):
                        raise DaemonUnavailable(obj["error"])
                    if obj.get("chunk"):
                        yield obj["chunk"]
                    if obj.get("done"):
                        return
        finally:
            try:
                conn.close()
            except OSError:
                pass

    def remember(self, fact: str) -> None:
        self._request({"type": "remember", "fact": fact})

    def search(self, query: str, limit: int = 5) -> str:
        r = self._request({"type": "search", "query": query, "limit": limit})
        return r.get("context", "")

    def status(self) -> dict:
        return self._request({"type": "status"})

    def clear(self, session: str = "default") -> None:
        self._request({"type": "clear", "session": session})

    def shutdown(self) -> None:
        try:
            self._request({"type": "shutdown"})
        except Exception:
            pass

    # ── Auto-arranque del daemon ───────────────────────────────────────────

    def ensure_daemon(self, wait: float = 5.0) -> bool:
        """Arranca el daemon si no está corriendo. Retorna True si quedó disponible."""
        if self.ping():
            return True
        if not self.auto_start:
            return False

        log.info("[Client] Arrancando daemon...")
        daemon_module = "nova.core.nova_daemon"
        try:
            proc = subprocess.Popen(
                [sys.executable, "-m", daemon_module],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            log.debug("[Client] Daemon PID=%d", proc.pid)
        except Exception as e:
            log.warning("[Client] No se pudo arrancar daemon: %s", e)
            return False

        # Esperar hasta `wait` segundos
        deadline = time.time() + wait
        while time.time() < deadline:
            time.sleep(0.3)
            if self.ping():
                log.info("[Client] Daemon listo en %.1fs", time.time() - (deadline - wait))
                return True
        log.warning("[Client] Daemon no respondió en %.1fs", wait)
        return False


# ─── Singleton global ─────────────────────────────────────────────────────────

_client: NovaDaemonClient | None = None


def get_client(auto_start: bool = False) -> NovaDaemonClient:
    """Retorna el cliente singleton. No auto-arranca por defecto."""
    global _client
    if _client is None:
        _client = NovaDaemonClient(auto_start=auto_start)
    return _client


def daemon_available() -> bool:
    """Quick check: ¿está el daemon corriendo ahora?"""
    return get_client().ping()
