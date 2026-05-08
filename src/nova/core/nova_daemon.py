"""
nova_daemon.py — Proceso central de Nova.

Posee el NovaRouter y NovaNeuroMemory (Qdrant) como singletons.
Escucha en TCP localhost:NOVA_DAEMON_PORT (default 7899).
REPL, HUD y Telegram se conectan como clientes en vez de instanciar
sus propias copias — elimina conflictos de Qdrant cross-thread y
duplicación de instancias de router.

Protocolo: JSON newline-delimited (ndjson)
  Request:  {"type": "ping|chat|skill|remember|search|status|shutdown", ...}
  Response: {"ok": true, "result": "...", "error": null}

Lanzamiento:
  python -m nova.core.nova_daemon          # foreground
  python -m nova.core.nova_daemon --bg     # background (daemon)
"""

from __future__ import annotations

import json
import logging
import os
import signal
import socket
import sys
import threading
import time
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

DAEMON_PORT      = int(os.getenv("NOVA_DAEMON_PORT", "7899"))
DAEMON_HOST      = "127.0.0.1"
_DOTNOVA         = Path.home() / ".nova"
PID_FILE         = _DOTNOVA / "daemon.pid"
SESSION_TIMEOUT  = 3600  # segundos sin actividad para limpiar sesión


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _send(conn: socket.socket, obj: dict) -> None:
    data = json.dumps(obj, ensure_ascii=False) + "\n"
    conn.sendall(data.encode("utf-8"))


def _recv_line(conn: socket.socket, buf: bytearray) -> str | None:
    """Lee una línea JSON del socket. Retorna None si la conexión se cerró."""
    while b"\n" not in buf:
        try:
            chunk = conn.recv(4096)
        except OSError:
            return None
        if not chunk:
            return None
        buf.extend(chunk)
    idx = buf.index(b"\n")
    line = buf[:idx].decode("utf-8", errors="replace")
    del buf[:idx + 1]
    return line


# ─── NovaDaemon ───────────────────────────────────────────────────────────────

class NovaDaemon:
    """Servidor TCP que posee el router y la memoria como singletons."""

    def __init__(self) -> None:
        self._router   = None
        self._memory   = None
        self._sessions: dict[str, list[dict]] = {}   # session_id → history
        self._session_ts: dict[str, float] = {}
        self._lock     = threading.Lock()
        self._running  = False
        self._server   = None

    # ── Inicialización lazy ────────────────────────────────────────────────

    def _init_router(self) -> None:
        if self._router is not None:
            return
        try:
            from nova.core.nova_router import NovaRouter
            self._router = NovaRouter()
            log.info("[Daemon] Router inicializado — proveedores: %s", self._router._active_provider)
        except Exception as e:
            log.error("[Daemon] Error init router: %s", e)
            self._router = False

    def _init_memory(self) -> None:
        if self._memory is not None:
            return
        try:
            from nova.tools.nova_neuro_memory import NovaNeuroMemory
            self._memory = NovaNeuroMemory()
            log.info("[Daemon] Memoria inicializada")
        except Exception as e:
            log.warning("[Daemon] Memoria no disponible: %s", e)
            self._memory = False

    # ── Sesiones ───────────────────────────────────────────────────────────

    def _get_history(self, session_id: str) -> list[dict]:
        with self._lock:
            self._session_ts[session_id] = time.time()
            return self._sessions.setdefault(session_id, [])

    def _trim_sessions(self) -> None:
        now = time.time()
        with self._lock:
            expired = [sid for sid, ts in self._session_ts.items()
                       if now - ts > SESSION_TIMEOUT]
            for sid in expired:
                self._sessions.pop(sid, None)
                self._session_ts.pop(sid, None)
        if expired:
            log.debug("[Daemon] Sesiones expiradas limpiadas: %d", len(expired))

    # ── Handlers de mensajes ───────────────────────────────────────────────

    def _handle_ping(self, _req: dict) -> dict:
        providers = (self._router._active_provider
                     if self._router and self._router is not False else "none")
        return {"ok": True, "version": "3.1", "providers": providers}

    def _build_msgs(self, message: str, history: list[dict], mem_ctx: str) -> list[dict]:
        """Construye la lista de mensajes para el LLM."""
        system = self._router.system_prompt
        if mem_ctx:
            system += f"\n\n[Memoria relevante]\n{mem_ctx}"
        msgs: list[dict] = [{"role": "system", "content": system}]
        for m in history[-20:]:
            if m.get("role") in ("user", "assistant") and m.get("content"):
                msgs.append({"role": m["role"], "content": str(m["content"])})
        msgs.append({"role": "user", "content": message})
        return msgs

    def _run_skill(self, message: str) -> str | None:
        try:
            from nova.tools.nova_skills import dispatch
            return dispatch(message)
        except Exception:
            return None

    def _mem_ctx(self, message: str) -> str:
        if not (self._memory and self._memory is not False):
            return ""
        try:
            return self._memory.search_context(message, limit=4) or ""
        except Exception:
            return ""

    def _save_turn(self, history: list[dict], message: str, response: str) -> None:
        with self._lock:
            history.append({"role": "user", "content": message})
            history.append({"role": "assistant", "content": response})
            max_h = int(os.getenv("MAX_HISTORY", "20")) * 2
            if len(history) > max_h:
                del history[:-max_h]
        if self._memory and self._memory is not False:
            try:
                self._memory.save_turn("user", message)
                self._memory.save_turn("assistant", response)
            except Exception:
                pass

    def _handle_chat(self, req: dict) -> dict:
        self._init_router()
        self._init_memory()
        if not self._router:
            return {"ok": False, "error": "Router no disponible"}

        session_id = req.get("session", "default")
        message    = req.get("message", "")
        history    = self._get_history(session_id)

        skill_result = self._run_skill(message)
        if skill_result is not None:
            return {"ok": True, "result": skill_result, "skill": True}

        msgs = self._build_msgs(message, history, self._mem_ctx(message))
        try:
            result   = self._router.route(msgs)
            response = result.get("response", "Sin respuesta.")
        except Exception as e:
            return {"ok": False, "error": str(e)}

        self._save_turn(history, message, response)
        return {"ok": True, "result": response, "skill": False}

    def _handle_chat_stream(self, req: dict):
        """Generator: yields ndjson dicts (chunks + final done)."""
        self._init_router()
        self._init_memory()
        if not self._router:
            yield {"ok": False, "done": True, "error": "Router no disponible"}
            return

        session_id = req.get("session", "default")
        message    = req.get("message", "")
        history    = self._get_history(session_id)

        skill_result = self._run_skill(message)
        if skill_result is not None:
            yield {"ok": True, "done": True, "result": skill_result, "skill": True}
            return

        msgs = self._build_msgs(message, history, self._mem_ctx(message))
        chunks: list[str] = []
        try:
            for chunk in self._router.route_stream(msgs):
                chunks.append(chunk)
                yield {"ok": True, "chunk": chunk}
        except Exception as e:
            yield {"ok": False, "done": True, "error": str(e)}
            return

        response = "".join(chunks)
        self._save_turn(history, message, response)
        yield {"ok": True, "done": True, "result": response, "skill": False}

    def _handle_remember(self, req: dict) -> dict:
        self._init_memory()
        fact = req.get("fact", "").strip()
        if not fact:
            return {"ok": False, "error": "fact vacío"}
        if self._memory and self._memory is not False:
            try:
                self._memory.remember(fact)
                return {"ok": True}
            except Exception as e:
                return {"ok": False, "error": str(e)}
        return {"ok": False, "error": "Memoria no disponible"}

    def _handle_search(self, req: dict) -> dict:
        self._init_memory()
        query = req.get("query", "")
        limit = int(req.get("limit", 5))
        if self._memory and self._memory is not False:
            try:
                ctx = self._memory.search_context(query, limit=limit)
                return {"ok": True, "context": ctx}
            except Exception as e:
                return {"ok": False, "error": str(e)}
        return {"ok": True, "context": ""}

    def _handle_status(self, _req: dict) -> dict:
        providers = (self._router._active_provider
                     if self._router and self._router is not False else "ninguno")
        sessions  = len(self._sessions)
        mem_ok    = bool(self._memory and self._memory is not False)
        return {"ok": True, "providers": providers, "sessions": sessions, "memory": mem_ok}

    def _handle_clear(self, req: dict) -> dict:
        session_id = req.get("session", "default")
        with self._lock:
            self._sessions.pop(session_id, None)
            self._session_ts.pop(session_id, None)
        return {"ok": True}

    def _handle_shutdown(self, _req: dict) -> dict:
        threading.Thread(target=self.stop, daemon=True).start()
        return {"ok": True, "msg": "Daemon apagándose..."}

    _HANDLERS = {
        "ping":     _handle_ping,
        "chat":     _handle_chat,
        "remember": _handle_remember,
        "search":   _handle_search,
        "status":   _handle_status,
        "clear":    _handle_clear,
        "shutdown": _handle_shutdown,
    }

    # ── Manejo de clientes ─────────────────────────────────────────────────

    def _handle_client(self, conn: socket.socket, addr: tuple) -> None:
        log.debug("[Daemon] Cliente conectado: %s", addr)
        buf = bytearray()
        try:
            while self._running:
                line = _recv_line(conn, buf)
                if line is None:
                    break
                try:
                    req = json.loads(line)
                except json.JSONDecodeError as e:
                    _send(conn, {"ok": False, "error": f"JSON inválido: {e}"})
                    continue

                msg_type = req.get("type", "")

                # chat_stream: protocolo multi-línea (N chunks + done)
                if msg_type == "chat_stream":
                    try:
                        for obj in self._handle_chat_stream(req):
                            _send(conn, obj)
                    except Exception as e:
                        log.exception("[Daemon] Error en chat_stream")
                        _send(conn, {"ok": False, "done": True, "error": str(e)})
                    continue

                handler = self._HANDLERS.get(msg_type)
                if handler is None:
                    _send(conn, {"ok": False, "error": f"Tipo desconocido: {msg_type}"})
                    continue

                try:
                    result = handler(self, req)
                except Exception as e:
                    log.exception("[Daemon] Error en handler %s", msg_type)
                    result = {"ok": False, "error": str(e)}

                _send(conn, result)
        except Exception as e:
            log.debug("[Daemon] Error con cliente %s: %s", addr, e)
        finally:
            try:
                conn.close()
            except OSError:
                pass
        log.debug("[Daemon] Cliente desconectado: %s", addr)

    # ── Servidor ───────────────────────────────────────────────────────────

    def start(self) -> None:
        _DOTNOVA.mkdir(parents=True, exist_ok=True)

        # Inicializar componentes al arranque (no lazy aquí para detectar errores pronto)
        self._init_router()
        self._init_memory()

        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self._server.bind((DAEMON_HOST, DAEMON_PORT))
        except OSError as e:
            log.error("[Daemon] No se pudo bind %s:%d — %s", DAEMON_HOST, DAEMON_PORT, e)
            sys.exit(1)
        self._server.listen(16)
        self._running = True

        # Escribir PID
        PID_FILE.write_text(str(os.getpid()), encoding="utf-8")
        log.info("[Daemon] Escuchando en %s:%d (pid=%d)", DAEMON_HOST, DAEMON_PORT, os.getpid())
        print(f"[Nova Daemon] Puerto {DAEMON_PORT} — listo. PID={os.getpid()}")

        # Limpieza de sesiones cada 5 minutos
        def _session_gc():
            while self._running:
                time.sleep(300)
                self._trim_sessions()

        threading.Thread(target=_session_gc, daemon=True, name="session-gc").start()

        self._server.settimeout(1.0)
        while self._running:
            try:
                conn, addr = self._server.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            t = threading.Thread(target=self._handle_client,
                                 args=(conn, addr), daemon=True,
                                 name=f"client-{addr[1]}")
            t.start()

        log.info("[Daemon] Loop terminado")

    def stop(self) -> None:
        self._running = False
        try:
            self._server.close()
        except Exception:
            pass
        if PID_FILE.exists():
            try:
                PID_FILE.unlink()
            except OSError:
                pass
        # Cerrar memoria (Qdrant)
        if self._memory and hasattr(self._memory, "close"):
            try:
                self._memory.close()
            except Exception:
                pass
        log.info("[Daemon] Apagado completo")


# ─── Entry point ──────────────────────────────────────────────────────────────

def _daemonize() -> None:
    """Fork al background (Unix). En Windows simplemente no hace nada."""
    if sys.platform == "win32":
        return
    if os.fork() > 0:
        sys.exit(0)
    os.setsid()
    if os.fork() > 0:
        sys.exit(0)
    sys.stdin.close()


def main() -> None:
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    parser = argparse.ArgumentParser(description="Nova Daemon")
    parser.add_argument("--bg", action="store_true", help="Correr en background (Unix)")
    args = parser.parse_args()

    if args.bg:
        _daemonize()

    daemon = NovaDaemon()

    def _sig(sig, _frame):
        print(f"\n[Daemon] Señal {sig} recibida — apagando...")
        daemon.stop()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _sig)
    signal.signal(signal.SIGINT, _sig)

    try:
        daemon.start()
    except KeyboardInterrupt:
        daemon.stop()


if __name__ == "__main__":
    main()
