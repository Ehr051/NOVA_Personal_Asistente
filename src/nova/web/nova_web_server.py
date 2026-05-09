"""
nova_web_server.py
───────────────────
REPL web de Nova en localhost — interfaz de chat en el navegador.

Características:
  • Chat streaming token a token via SSE
  • Modo agente autónomo: muestra plan + tool calls + resultado en tiempo real
  • Panel lateral con skills disponibles y estado del sistema
  • Tema oscuro coherente con la identidad visual de Nova

Lanzamiento:
  python -m nova.web.nova_web_server        # puerto 8080 (default)
  NOVA_WEB_PORT=9090 python -m nova.web.nova_web_server

Desde el REPL:
  /webui           → abre en el navegador
  /webui start     → solo inicia el servidor
  /webui stop      → detiene el servidor

Protocolo:
  GET  /                 → HTML SPA
  GET  /stream?q=...     → SSE: chat streaming (usa daemon o router directo)
  GET  /agent?q=...      → SSE: agentic loop — plan, tool calls, resultado
  GET  /api/status       → JSON estado del sistema
  GET  /api/skills       → JSON lista de skills
  GET  /api/history      → JSON historial de la sesión web
  POST /api/clear        → limpia historial
"""
from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

log = logging.getLogger("nova_web")

NOVA_WEB_PORT = int(os.getenv("NOVA_WEB_PORT", "8080"))
NOVA_WEB_HOST = os.getenv("NOVA_WEB_HOST", "127.0.0.1")

# Añadir src al path si se ejecuta directamente
_SRC = Path(__file__).resolve().parents[2]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# ─── Inicialización lazy de Nova ──────────────────────────────────────────────

_router   = None
_skills   = None
_daemon   = None
_history: list[dict] = []
_init_lock = threading.Lock()


def _init_nova() -> None:
    global _router, _skills, _daemon
    with _init_lock:
        if _router is not None:
            return
        try:
            from dotenv import load_dotenv
            load_dotenv(str(_SRC.parent / ".env"))
        except Exception:
            pass
        try:
            from nova.core.nova_client import NovaDaemonClient
            _daemon = NovaDaemonClient(auto_start=False)
            if not _daemon.ping():
                _daemon = None
        except Exception:
            _daemon = None
        try:
            from nova.core.nova_router import NovaRouter
            from nova.tools.nova_skills import skills as _s
            _router = NovaRouter()
            _s.set_router(_router)
            _skills = _s
        except Exception as e:
            log.warning("Router init parcial: %s", e)


# ─── HTML ─────────────────────────────────────────────────────────────────────

_HTML = r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Nova</title>
<style>
  :root {
    --bg: #0a0e1a; --panel: #0f1525; --border: #1a2540;
    --accent: #14c8ff; --accent2: #7c3aed; --text: #e2e8f0;
    --muted: #64748b; --tool: #22c55e; --plan: #f59e0b;
    --err: #ef4444; --radius: 12px; --font: 'Inter', system-ui, sans-serif;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: var(--bg); color: var(--text); font-family: var(--font);
         display: flex; height: 100vh; overflow: hidden; }

  /* Sidebar */
  #sidebar { width: 260px; background: var(--panel); border-right: 1px solid var(--border);
             display: flex; flex-direction: column; overflow: hidden; flex-shrink: 0; }
  #sidebar h1 { padding: 20px 16px 8px; font-size: 22px; font-weight: 700;
                background: linear-gradient(90deg, var(--accent), var(--accent2));
                -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
  #sidebar .subtitle { padding: 0 16px 16px; font-size: 11px; color: var(--muted); }
  #status-box { margin: 0 12px 12px; padding: 10px 12px; background: #0a0e1a;
                border: 1px solid var(--border); border-radius: var(--radius); font-size: 12px; }
  #status-box .row { display: flex; justify-content: space-between; margin-bottom: 4px; }
  #status-box .label { color: var(--muted); }
  #status-box .val { color: var(--accent); font-weight: 600; }
  #skills-list { flex: 1; overflow-y: auto; padding: 0 12px 12px; }
  #skills-list h3 { font-size: 11px; text-transform: uppercase; letter-spacing: .08em;
                    color: var(--muted); margin-bottom: 8px; padding-top: 4px; }
  .skill-item { padding: 6px 10px; border-radius: 8px; font-size: 12px; cursor: pointer;
                color: var(--muted); transition: all .15s; white-space: nowrap;
                overflow: hidden; text-overflow: ellipsis; }
  .skill-item:hover { background: var(--border); color: var(--text); }
  .skill-item span { margin-right: 6px; }
  #sidebar::-webkit-scrollbar, #skills-list::-webkit-scrollbar { width: 4px; }
  #skills-list::-webkit-scrollbar-thumb { background: var(--border); border-radius: 4px; }

  /* Main */
  #main { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
  #messages { flex: 1; overflow-y: auto; padding: 24px 32px; display: flex;
              flex-direction: column; gap: 16px; }
  #messages::-webkit-scrollbar { width: 6px; }
  #messages::-webkit-scrollbar-thumb { background: var(--border); border-radius: 4px; }

  .msg { max-width: 72%; padding: 12px 16px; border-radius: var(--radius); line-height: 1.6;
         font-size: 14px; word-wrap: break-word; white-space: pre-wrap; }
  .msg.user { align-self: flex-end; background: var(--accent2);
              border-bottom-right-radius: 4px; color: #fff; }
  .msg.nova  { align-self: flex-start; background: var(--panel);
               border: 1px solid var(--border); border-bottom-left-radius: 4px; }
  .msg.nova .who { font-size: 11px; font-weight: 700; color: var(--accent);
                   margin-bottom: 6px; letter-spacing: .06em; }
  .msg.system { align-self: center; background: transparent; color: var(--muted);
                font-size: 12px; font-style: italic; padding: 4px 0; }

  /* Agent progress */
  .msg.agent { align-self: flex-start; background: #0a1020;
               border: 1px solid #1e3a5f; border-bottom-left-radius: 4px;
               max-width: 82%; font-family: monospace; font-size: 13px; }
  .msg.agent .who { font-size: 11px; font-weight: 700; color: var(--plan);
                    margin-bottom: 8px; letter-spacing: .06em; }
  .plan-line  { color: var(--plan); }
  .tool-line  { color: var(--tool); }
  .result-line { color: var(--muted); padding-left: 16px; }
  .final-line { color: var(--text); border-top: 1px solid var(--border);
                margin-top: 10px; padding-top: 10px; }

  /* Input area */
  #input-area { padding: 16px 32px 20px; border-top: 1px solid var(--border);
                background: var(--panel); display: flex; flex-direction: column; gap: 10px; }
  #mode-row { display: flex; gap: 8px; align-items: center; }
  .mode-btn { padding: 5px 14px; border-radius: 20px; font-size: 12px; font-weight: 600;
              border: 1px solid var(--border); cursor: pointer; transition: all .15s;
              background: transparent; color: var(--muted); }
  .mode-btn.active { background: var(--accent); border-color: var(--accent); color: #000; }
  .mode-btn.active.agent-mode { background: var(--plan); border-color: var(--plan); }
  #char-count { margin-left: auto; font-size: 11px; color: var(--muted); }
  #input-row { display: flex; gap: 10px; align-items: flex-end; }
  #input { flex: 1; background: #0a0e1a; border: 1px solid var(--border);
           border-radius: var(--radius); padding: 12px 16px; color: var(--text);
           font-family: var(--font); font-size: 14px; resize: none; min-height: 48px;
           max-height: 140px; outline: none; transition: border-color .15s; line-height: 1.5; }
  #input:focus { border-color: var(--accent); }
  #send { background: var(--accent); color: #000; border: none; border-radius: var(--radius);
          width: 48px; height: 48px; cursor: pointer; font-size: 18px; flex-shrink: 0;
          transition: opacity .15s; display: flex; align-items: center; justify-content: center; }
  #send:disabled { opacity: .35; cursor: not-allowed; }
  #send.agent-mode { background: var(--plan); }

  /* Cursor blink */
  .cursor { display: inline-block; width: 2px; height: 1em; background: var(--accent);
            animation: blink .7s infinite; vertical-align: text-bottom; margin-left: 1px; }
  @keyframes blink { 0%,100%{opacity:1} 50%{opacity:0} }

  /* Scrollbar global */
  ::-webkit-scrollbar { width: 6px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 4px; }
</style>
</head>
<body>

<div id="sidebar">
  <h1>Nova</h1>
  <div class="subtitle">Asistente Personal Inteligente</div>
  <div id="status-box">
    <div class="row"><span class="label">Estado</span><span class="val" id="s-status">—</span></div>
    <div class="row"><span class="label">Proveedor</span><span class="val" id="s-provider">—</span></div>
    <div class="row"><span class="label">Plugins</span><span class="val" id="s-plugins">—</span></div>
  </div>
  <div id="skills-list">
    <h3>Skills</h3>
    <div id="skills-inner"></div>
  </div>
</div>

<div id="main">
  <div id="messages">
    <div class="msg system">Nova Web UI — escribí tu consulta o activá el modo Agente</div>
  </div>
  <div id="input-area">
    <div id="mode-row">
      <button class="mode-btn active" id="btn-chat" onclick="setMode('chat')">💬 Chat</button>
      <button class="mode-btn" id="btn-agent" onclick="setMode('agent')">🤖 Agente</button>
      <span id="char-count"></span>
    </div>
    <div id="input-row">
      <textarea id="input" placeholder="Preguntá algo…" rows="1"></textarea>
      <button id="send" onclick="sendMsg()">↑</button>
    </div>
  </div>
</div>

<script>
let mode = 'chat';
let busy = false;

function setMode(m) {
  mode = m;
  document.getElementById('btn-chat').classList.toggle('active', m === 'chat');
  document.getElementById('btn-agent').classList.toggle('active', m === 'agent');
  document.getElementById('btn-agent').classList.toggle('agent-mode', m === 'agent');
  document.getElementById('send').classList.toggle('agent-mode', m === 'agent');
  document.getElementById('input').placeholder =
    m === 'agent' ? 'Describí el objetivo del agente…' : 'Preguntá algo…';
}

function autoResize(el) {
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 140) + 'px';
}

const inp = document.getElementById('input');
inp.addEventListener('input', () => {
  autoResize(inp);
  const n = inp.value.length;
  document.getElementById('char-count').textContent = n > 0 ? n + ' chars' : '';
});
inp.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMsg(); }
});

function scrollBottom() {
  const el = document.getElementById('messages');
  el.scrollTop = el.scrollHeight;
}

function addMsg(cls, content, who = '') {
  const msgs = document.getElementById('messages');
  const div = document.createElement('div');
  div.className = 'msg ' + cls;
  if (who) div.innerHTML = `<div class="who">${who}</div>`;
  const body = document.createElement('div');
  body.className = 'body';
  body.textContent = content;
  div.appendChild(body);
  msgs.appendChild(div);
  scrollBottom();
  return body;
}

function addAgentMsg() {
  const msgs = document.getElementById('messages');
  const div = document.createElement('div');
  div.className = 'msg agent';
  div.innerHTML = '<div class="who">⚙️ AGENTE</div>';
  const body = document.createElement('div');
  body.className = 'body';
  div.appendChild(body);
  msgs.appendChild(div);
  scrollBottom();
  return body;
}

function renderAgentLine(body, line) {
  const span = document.createElement('div');
  if (line.startsWith('📋')) {
    span.className = 'plan-line';
  } else if (line.startsWith('  ⚙️') || line.startsWith('⚙️')) {
    span.className = 'tool-line';
  } else if (line.startsWith('     →') || line.startsWith('   →')) {
    span.className = 'result-line';
  } else if (line.startsWith('✅') || line.startsWith('🔄')) {
    span.className = 'final-line';
  }
  span.textContent = line;
  body.appendChild(span);
  scrollBottom();
}

function setBusy(b) {
  busy = b;
  document.getElementById('send').disabled = b;
  document.getElementById('input').disabled = b;
}

function sendMsg() {
  if (busy) return;
  const q = inp.value.trim();
  if (!q) return;
  inp.value = ''; autoResize(inp);
  document.getElementById('char-count').textContent = '';

  addMsg('user', q);
  setBusy(true);

  if (mode === 'agent') {
    streamAgent(q);
  } else {
    streamChat(q);
  }
}

function streamChat(q) {
  const body = addMsg('nova', '', 'NOVA');
  const cursor = document.createElement('span');
  cursor.className = 'cursor'; body.appendChild(cursor);

  const url = '/stream?q=' + encodeURIComponent(q);
  const es = new EventSource(url);
  es.onmessage = e => {
    if (e.data === '[DONE]') {
      cursor.remove(); es.close(); setBusy(false); return;
    }
    if (e.data.startsWith('[ERR]')) {
      body.textContent = e.data.slice(5);
      es.close(); setBusy(false); return;
    }
    body.insertBefore(document.createTextNode(e.data), cursor);
    scrollBottom();
  };
  es.onerror = () => { cursor.remove(); es.close(); setBusy(false); };
}

function streamAgent(q) {
  const body = addAgentMsg();
  const url = '/agent?q=' + encodeURIComponent(q);
  const es = new EventSource(url);
  let buf = '';
  es.onmessage = e => {
    if (e.data === '[DONE]') {
      if (buf) renderAgentLine(body, buf);
      es.close(); setBusy(false); return;
    }
    if (e.data.startsWith('[ERR]')) {
      renderAgentLine(body, '❌ ' + e.data.slice(5));
      es.close(); setBusy(false); return;
    }
    // Accumulate into lines
    buf += e.data;
    const lines = buf.split('\n');
    buf = lines.pop(); // incomplete last line stays in buf
    for (const l of lines) {
      if (l.trim()) renderAgentLine(body, l);
    }
    scrollBottom();
  };
  es.onerror = () => { es.close(); setBusy(false); };
}

// Load status + skills on boot
async function loadStatus() {
  try {
    const r = await fetch('/api/status');
    const d = await r.json();
    document.getElementById('s-status').textContent =
      d.daemon ? 'daemon ✓' : (d.router ? 'router ✓' : '✗');
    document.getElementById('s-provider').textContent =
      d.providers || '—';
    document.getElementById('s-plugins').textContent =
      (d.plugins || 0) + ' cargados';
  } catch(e) {}
}

async function loadSkills() {
  try {
    const r = await fetch('/api/skills');
    const d = await r.json();
    const el = document.getElementById('skills-inner');
    el.innerHTML = '';
    for (const [k, v] of Object.entries(d)) {
      const div = document.createElement('div');
      div.className = 'skill-item';
      div.title = v;
      div.innerHTML = `<span>▸</span>${k}`;
      div.onclick = () => {
        inp.value = k.replace(/_/g,' ');
        inp.focus();
      };
      el.appendChild(div);
    }
  } catch(e) {}
}

loadStatus();
loadSkills();
setInterval(loadStatus, 10000);
</script>
</body>
</html>"""


# ─── Request handler ──────────────────────────────────────────────────────────

class NovaWebHandler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        log.debug(fmt, *args)

    def _send_headers(self, content_type: str, status: int = 200,
                      extra: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache")
        if extra:
            for k, v in extra.items():
                self.send_header(k, v)
        self.end_headers()

    def _sse_headers(self) -> None:
        self._send_headers(
            "text/event-stream; charset=utf-8",
            extra={"X-Accel-Buffering": "no", "Connection": "keep-alive"},
        )

    def _write_sse(self, data: str) -> bool:
        try:
            # Each SSE data field can't have newlines — encode them
            for line in data.split("\n"):
                self.wfile.write(f"data: {line}\n".encode())
            self.wfile.write(b"\n")
            self.wfile.flush()
            return True
        except (BrokenPipeError, ConnectionResetError):
            return False

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path   = parsed.path
        params = dict(urllib.parse.parse_qsl(parsed.query))

        if path == "/":
            self._send_headers("text/html; charset=utf-8")
            self.wfile.write(_HTML.encode())

        elif path == "/stream":
            _init_nova()
            q = params.get("q", "").strip()
            self._sse_headers()
            if not q:
                self._write_sse("[ERR]Query vacía")
                self._write_sse("[DONE]")
                return
            self._stream_chat(q)

        elif path == "/agent":
            _init_nova()
            q = params.get("q", "").strip()
            self._sse_headers()
            if not q:
                self._write_sse("[ERR]Objetivo vacío")
                self._write_sse("[DONE]")
                return
            self._stream_agent(q)

        elif path == "/api/status":
            _init_nova()
            from nova.tools.nova_plugin_loader import loaded_plugins
            data = {
                "daemon":    _daemon is not None,
                "router":    _router is not None,
                "providers": (
                    _router._active_provider if _router and _router is not False else
                    ("daemon" if _daemon else "none")
                ),
                "plugins": len(loaded_plugins()),
            }
            self._send_headers("application/json")
            self.wfile.write(json.dumps(data).encode())

        elif path == "/api/skills":
            _init_nova()
            skills_dict: dict[str, str] = {}
            try:
                from nova.tools.nova_skills import _TOOL_CATALOG
                skills_dict = {k: v[0] for k, v in list(_TOOL_CATALOG.items())[:60]}
            except Exception:
                pass
            self._send_headers("application/json")
            self.wfile.write(json.dumps(skills_dict, ensure_ascii=False).encode())

        elif path == "/api/history":
            self._send_headers("application/json")
            self.wfile.write(json.dumps(_history[-40:], ensure_ascii=False).encode())

        else:
            self._send_headers("text/plain", 404)
            self.wfile.write(b"Not found")

    def do_POST(self):
        if self.path == "/api/clear":
            _history.clear()
            self._send_headers("application/json")
            self.wfile.write(b'{"ok":true}')
        else:
            self._send_headers("text/plain", 404)
            self.wfile.write(b"Not found")

    def do_OPTIONS(self):
        self._send_headers("text/plain",
                           extra={"Allow": "GET, POST, OPTIONS"})

    # ── Chat streaming ────────────────────────────────────────────────────────

    def _stream_chat(self, q: str) -> None:
        _history.append({"role": "user", "content": q})
        chunks: list[str] = []

        # Intentar skills primero
        try:
            if _skills:
                skill_resp = _skills.dispatch(q)
                if skill_resp is not None:
                    _history.append({"role": "assistant", "content": skill_resp})
                    self._write_sse(skill_resp)
                    self._write_sse("[DONE]")
                    return
        except Exception:
            pass

        # Daemon streaming
        if _daemon:
            try:
                for chunk in _daemon.chat_stream(q, session="web"):
                    if not self._write_sse(chunk):
                        return
                    chunks.append(chunk)
                response = "".join(chunks)
                _history.append({"role": "assistant", "content": response})
                self._write_sse("[DONE]")
                return
            except Exception as e:
                log.debug("Daemon stream falló: %s", e)

        # Router directo
        if _router:
            try:
                for chunk in _router.route_stream(
                    [{"role": "user", "content": q}]
                ):
                    if not self._write_sse(chunk):
                        return
                    chunks.append(chunk)
                response = "".join(chunks)
                _history.append({"role": "assistant", "content": response})
            except Exception as e:
                self._write_sse(f"[ERR]{e}")

        self._write_sse("[DONE]")

    # ── Agent streaming ───────────────────────────────────────────────────────

    def _stream_agent(self, goal: str) -> None:
        _history.append({"role": "user", "content": f"[agente] {goal}"})

        if not _router:
            self._write_sse("[ERR]Router no disponible")
            self._write_sse("[DONE]")
            return

        result_holder: list[str] = []

        def _cb(msg: str) -> None:
            self._write_sse(msg)

        try:
            from nova.tools.nova_skills import skill_agente
            final = skill_agente(goal, progress_cb=_cb)
            result_holder.append(final)
        except Exception as e:
            self._write_sse(f"[ERR]{e}")
            self._write_sse("[DONE]")
            return

        final = result_holder[0] if result_holder else ""
        self._write_sse(f"\n✅ Resultado:\n{final}")
        _history.append({"role": "assistant", "content": final})
        self._write_sse("[DONE]")


# ─── Server lifecycle ─────────────────────────────────────────────────────────

_server_instance: ThreadingHTTPServer | None = None
_server_thread:   threading.Thread     | None = None


def start(host: str = NOVA_WEB_HOST, port: int = NOVA_WEB_PORT,
          open_browser: bool = False) -> bool:
    """Inicia el servidor en un hilo daemon. Retorna True si arrancó."""
    global _server_instance, _server_thread
    if _server_instance is not None:
        return True
    try:
        _server_instance = ThreadingHTTPServer((host, port), NovaWebHandler)
        _server_thread = threading.Thread(
            target=_server_instance.serve_forever,
            daemon=True,
            name="nova-web",
        )
        _server_thread.start()
        log.info("[Web] Servidor en http://%s:%d", host, port)
        if open_browser:
            import webbrowser
            webbrowser.open(f"http://{host}:{port}")
        return True
    except OSError as e:
        log.error("[Web] No se pudo iniciar: %s", e)
        _server_instance = None
        return False


def stop() -> None:
    global _server_instance, _server_thread
    if _server_instance:
        _server_instance.shutdown()
        _server_instance = None
        _server_thread   = None
        log.info("[Web] Servidor detenido")


def is_running() -> bool:
    return _server_instance is not None


def url() -> str:
    return f"http://{NOVA_WEB_HOST}:{NOVA_WEB_PORT}"


# ─── Entry point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")
    _init_nova()
    port = NOVA_WEB_PORT
    print(f"\n  Nova Web UI → http://127.0.0.1:{port}")
    print("  Ctrl+C para detener\n")
    srv = ThreadingHTTPServer((NOVA_WEB_HOST, port), NovaWebHandler)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n  Detenido.")
