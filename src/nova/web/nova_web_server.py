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
<title>NOVA | Command Center</title>
<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&family=JetBrains+Mono&display=swap" rel="stylesheet">
<style>
  :root {
    --bg-base: #050508;
    --glass-bg: rgba(15, 18, 28, 0.65);
    --glass-border: rgba(255, 255, 255, 0.08);
    --accent-cyan: #00f2fe;
    --accent-blue: #4facfe;
    --accent-purple: #9b51e0;
    --text-primary: #f8fafc;
    --text-muted: #94a3b8;
    --tool-color: #10b981;
    --plan-color: #f59e0b;
    --err-color: #ef4444;
    --radius: 16px;
    --font-main: 'Outfit', sans-serif;
    --font-mono: 'JetBrains Mono', monospace;
  }
  
  * { box-sizing: border-box; margin: 0; padding: 0; }
  
  body {
    background: var(--bg-base);
    color: var(--text-primary);
    font-family: var(--font-main);
    display: flex;
    height: 100vh;
    overflow: hidden;
    position: relative;
  }

  body::before {
    content: ''; position: absolute;
    top: -50%; left: -50%; width: 200%; height: 200%;
    background: radial-gradient(circle at 50% 50%, rgba(79, 172, 254, 0.12) 0%, rgba(0, 0, 0, 0) 50%),
                radial-gradient(circle at 80% 20%, rgba(155, 81, 224, 0.12) 0%, rgba(0, 0, 0, 0) 40%);
    z-index: -1; animation: pulseGlow 15s ease-in-out infinite alternate;
  }
  @keyframes pulseGlow {
    0% { transform: scale(1) translate(0, 0); }
    100% { transform: scale(1.1) translate(-2%, 2%); }
  }

  #sidebar {
    width: 280px; background: var(--glass-bg); backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
    border-right: 1px solid var(--glass-border); display: flex; flex-direction: column; flex-shrink: 0;
    box-shadow: 5px 0 30px rgba(0,0,0,0.5); z-index: 10;
  }
  #sidebar h1 {
    padding: 30px 20px 5px; font-size: 28px; font-weight: 700; letter-spacing: 1px;
    background: linear-gradient(135deg, var(--accent-cyan), var(--accent-blue));
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  }
  #sidebar .subtitle { padding: 0 20px 25px; font-size: 12px; color: var(--text-muted); font-weight: 300; letter-spacing: 0.5px; }
  
  #status-box {
    margin: 0 20px 20px; padding: 15px; background: rgba(0, 0, 0, 0.3); border: 1px solid var(--glass-border);
    border-radius: var(--radius); font-size: 12px; box-shadow: inset 0 2px 10px rgba(0,0,0,0.2);
  }
  #status-box .row { display: flex; justify-content: space-between; margin-bottom: 8px; }
  #status-box .row:last-child { margin-bottom: 0; }
  #status-box .label { color: var(--text-muted); font-weight: 400; }
  #status-box .val { color: var(--accent-cyan); font-weight: 600; text-shadow: 0 0 5px rgba(0,242,254,0.4); }
  
  #skills-list { flex: 1; overflow-y: auto; padding: 0 20px 20px; }
  #skills-list h3 { font-size: 11px; text-transform: uppercase; letter-spacing: 1.5px; color: var(--text-muted); margin-bottom: 12px; }
  .skill-item {
    padding: 10px 14px; margin-bottom: 8px; border-radius: 10px; font-size: 13px; cursor: pointer;
    background: rgba(255, 255, 255, 0.03); border: 1px solid transparent; color: var(--text-primary);
    transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  .skill-item:hover {
    background: rgba(255, 255, 255, 0.08); border: 1px solid rgba(255, 255, 255, 0.15);
    transform: translateX(4px); box-shadow: 0 4px 12px rgba(0,0,0,0.2);
  }
  .skill-item span { color: var(--accent-purple); margin-right: 8px; font-weight: bold; }

  #main { flex: 1; display: flex; flex-direction: column; overflow: hidden; position: relative; }
  #messages { flex: 1; overflow-y: auto; padding: 40px; display: flex; flex-direction: column; gap: 24px; scroll-behavior: smooth; }
  
  .msg {
    max-width: 75%; padding: 16px 20px; border-radius: 20px; line-height: 1.6; font-size: 15px;
    word-wrap: break-word; white-space: pre-wrap; box-shadow: 0 4px 15px rgba(0,0,0,0.1);
    animation: slideUp 0.3s ease-out forwards; opacity: 0; transform: translateY(10px);
  }
  @keyframes slideUp { to { opacity: 1; transform: translateY(0); } }
  
  .msg.user { align-self: flex-end; background: linear-gradient(135deg, var(--accent-blue), var(--accent-purple)); border-bottom-right-radius: 4px; color: #fff; }
  .msg.nova { align-self: flex-start; background: var(--glass-bg); backdrop-filter: blur(10px); border: 1px solid var(--glass-border); border-bottom-left-radius: 4px; }
  .msg.nova .who { font-size: 11px; font-weight: 700; color: var(--accent-cyan); margin-bottom: 8px; letter-spacing: 1px; text-transform: uppercase; }
  
  .msg.system { align-self: center; background: transparent; color: var(--text-muted); font-size: 13px; font-weight: 300; padding: 8px 16px; border-radius: 20px; border: 1px solid rgba(255,255,255,0.05); box-shadow: none; }

  .msg.agent { align-self: flex-start; background: rgba(10, 15, 25, 0.8); backdrop-filter: blur(12px); border: 1px solid rgba(79, 172, 254, 0.3); border-bottom-left-radius: 4px; max-width: 85%; font-family: var(--font-mono); font-size: 13px; box-shadow: 0 0 20px rgba(79, 172, 254, 0.05); }
  .msg.agent .who { font-family: var(--font-main); font-size: 11px; font-weight: 700; color: var(--plan-color); margin-bottom: 12px; letter-spacing: 1px; display: flex; align-items: center; gap: 6px; }
  .plan-line { color: var(--plan-color); font-weight: 600; margin-bottom: 4px; }
  .tool-line { color: var(--tool-color); margin-left: 8px; }
  .result-line { color: var(--text-muted); margin-left: 16px; font-style: italic; }
  .final-line { color: #fff; border-top: 1px solid var(--glass-border); margin-top: 12px; padding-top: 12px; font-family: var(--font-main); font-weight: 400; }

  #input-area { padding: 20px 40px 30px; background: rgba(10, 13, 20, 0.8); backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px); border-top: 1px solid var(--glass-border); display: flex; flex-direction: column; gap: 12px; z-index: 10; }
  #mode-row { display: flex; gap: 12px; align-items: center; }
  .mode-btn { padding: 6px 16px; border-radius: 20px; font-size: 13px; font-weight: 600; font-family: var(--font-main); border: 1px solid rgba(255,255,255,0.1); cursor: pointer; transition: all 0.3s ease; background: rgba(255,255,255,0.02); color: var(--text-muted); }
  .mode-btn:hover { background: rgba(255,255,255,0.08); color: #fff; }
  .mode-btn.active { background: rgba(0, 242, 254, 0.15); border-color: var(--accent-cyan); color: var(--accent-cyan); box-shadow: 0 0 15px rgba(0, 242, 254, 0.2); }
  .mode-btn.active.agent-mode { background: rgba(245, 158, 11, 0.15); border-color: var(--plan-color); color: var(--plan-color); box-shadow: 0 0 15px rgba(245, 158, 11, 0.2); }
  #char-count { margin-left: auto; font-size: 12px; color: var(--text-muted); font-family: var(--font-mono); }
  
  #input-row { display: flex; gap: 16px; align-items: flex-end; }
  #input { flex: 1; background: rgba(0, 0, 0, 0.4); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 20px; padding: 16px 20px; color: #fff; font-family: var(--font-main); font-size: 15px; resize: none; min-height: 54px; max-height: 150px; outline: none; transition: all 0.3s ease; line-height: 1.5; box-shadow: inset 0 2px 5px rgba(0,0,0,0.2); }
  #input:focus { border-color: var(--accent-cyan); box-shadow: 0 0 0 2px rgba(0, 242, 254, 0.1), inset 0 2px 5px rgba(0,0,0,0.2); }
  #send { background: linear-gradient(135deg, var(--accent-cyan), var(--accent-blue)); color: #000; border: none; border-radius: 50%; width: 54px; height: 54px; cursor: pointer; font-size: 20px; flex-shrink: 0; transition: transform 0.2s, opacity 0.2s, box-shadow 0.2s; display: flex; align-items: center; justify-content: center; box-shadow: 0 4px 15px rgba(0, 242, 254, 0.4); }
  #send:hover { transform: scale(1.05); }
  #send:active { transform: scale(0.95); }
  #send:disabled { opacity: 0.4; cursor: not-allowed; transform: none; box-shadow: none; }
  #send.agent-mode { background: linear-gradient(135deg, #f6d365, #fda085); box-shadow: 0 4px 15px rgba(245, 158, 11, 0.4); }

  .cursor { display: inline-block; width: 3px; height: 1.1em; background: var(--accent-cyan); animation: blink 0.8s infinite; vertical-align: middle; margin-left: 4px; border-radius: 2px; }
  @keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0; } }

  ::-webkit-scrollbar { width: 8px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 8px; border: 2px solid var(--bg-base); }
  ::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.2); }
</style>
</head>
<body>

<div id="sidebar">
  <h1>NOVA</h1>
  <div class="subtitle">Personal Assistant Core</div>
  <div id="status-box">
    <div class="row"><span class="label">Estado</span><span class="val" id="s-status">—</span></div>
    <div class="row"><span class="label">Proveedor</span><span class="val" id="s-provider">—</span></div>
    <div class="row"><span class="label">Plugins</span><span class="val" id="s-plugins">—</span></div>
  </div>
  <div id="skills-list">
    <h3>Catálogo de Skills</h3>
    <div id="skills-inner"></div>
  </div>
</div>

<div id="main">
  <div id="messages">
    <div class="msg system">Nova Web Interface (Premium UI) — Sesión iniciada</div>
  </div>
  <div id="input-area">
    <div id="mode-row">
      <button class="mode-btn active" id="btn-chat" onclick="setMode('chat')">💬 Modo Chat</button>
      <button class="mode-btn" id="btn-agent" onclick="setMode('agent')">🤖 Modo Autónomo</button>
      <span id="char-count"></span>
    </div>
    <div id="input-row">
      <textarea id="input" placeholder="Ingresa tu directiva..." rows="1"></textarea>
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
    m === 'agent' ? 'Establece el objetivo autónomo...' : 'Ingresa tu directiva...';
}

function autoResize(el) {
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 150) + 'px';
}

const inp = document.getElementById('input');
inp.addEventListener('input', () => {
  autoResize(inp);
  const n = inp.value.length;
  document.getElementById('char-count').textContent = n > 0 ? n + ' caracteres' : '';
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
  div.innerHTML = '<div class="who">🤖 AGENTE AUTÓNOMO</div>';
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
  const body = addMsg('nova', '', 'NOVA AI');
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
    buf += e.data;
    const lines = buf.split('\n');
    buf = lines.pop(); 
    for (const l of lines) {
      if (l.trim()) renderAgentLine(body, l);
    }
    scrollBottom();
  };
  es.onerror = () => { es.close(); setBusy(false); };
}

async function loadStatus() {
  try {
    const r = await fetch('/api/status');
    const d = await r.json();
    document.getElementById('s-status').textContent = d.daemon ? 'Online' : (d.router ? 'Router' : 'Offline');
    document.getElementById('s-provider').textContent = d.providers || '—';
    document.getElementById('s-plugins').textContent = (d.plugins || 0) + ' Cargados';
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
      div.innerHTML = `<span>⚡</span>${k}`;
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
            # No llama _init_nova() — responde instantáneamente con lo que esté listo
            from nova.tools.nova_plugin_loader import loaded_plugins
            data = {
                "ok":        True,
                "daemon":    _daemon is not None,
                "router":    _router is not None and _router is not False,
                "providers": (
                    _router._active_provider
                    if _router and _router is not False
                    else ("daemon" if _daemon else "not_initialized")
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
        import queue as _queue
        _history.append({"role": "user", "content": f"[agente] {goal}"})

        if not _router:
            self._write_sse("[ERR]Router no disponible")
            self._write_sse("[DONE]")
            return

        # Run skill_agente in a worker thread so SSE can flush without blocking.
        # Worker puts progress strings into the queue; sentinel None signals done.
        _DONE = object()
        q: _queue.Queue = _queue.Queue()

        def _worker():
            def _cb(msg: str) -> None:
                q.put(msg)
            try:
                from nova.tools.nova_skills import skill_agente
                final = skill_agente(goal, progress_cb=_cb)
                q.put(f"\n✅ Resultado:\n{final}")
                _history.append({"role": "assistant", "content": final})
            except Exception as e:
                q.put(f"[ERR]{e}")
            finally:
                q.put(_DONE)

        t = threading.Thread(target=_worker, daemon=True)
        t.start()

        while True:
            try:
                item = q.get(timeout=60)
            except _queue.Empty:
                self._write_sse("[ERR]Timeout del agente")
                break
            if item is _DONE:
                break
            if not self._write_sse(str(item)):
                break  # client disconnected

        self._write_sse("[DONE]")
        t.join(timeout=2)


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
    if _server_instance is not None:
        host, port = _server_instance.server_address
        return f"http://{host}:{port}"
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
