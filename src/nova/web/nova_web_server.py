"""
nova_web_server.py
───────────────────
REPL web de Nova en localhost — interfaz de chat y Dashboard de Configuración.
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

_SRC = Path(__file__).resolve().parents[2]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

ENV_PATH = _SRC.parent / ".env"
PLUGINS_DIR = _SRC.parent / "plugins"
MCP_CONFIG_PATH = _SRC.parent / ".mcp.json"

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
            load_dotenv(str(ENV_PATH))
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

_HTML = r'''<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>NOVA Dashboard</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono&display=swap" rel="stylesheet">
<!-- Markdown & Highlighting -->
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/atom-one-dark.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>
<style>
  :root {
    --bg-base: #1e1e24; --bg-panel: #25252b; --bg-msg: #2d2d34;
    --border: #3b3b44; --accent: #10a37f; --accent-hover: #0d8a6a;
    --text-primary: #ececf1; --text-muted: #8e8ea0;
    --plan-color: #f59e0b; --tool-color: #3b82f6; --error-color: #ef4444;
    --plugin-color: #9b51e0; --mcp-color: #ef4444;
    --font-main: 'Inter', system-ui, sans-serif; --font-mono: 'JetBrains Mono', monospace;
  }
  
  * { box-sizing: border-box; margin: 0; padding: 0; }
  
  body { background: var(--bg-base); color: var(--text-primary); font-family: var(--font-main); display: flex; height: 100vh; overflow: hidden; }

  /* Sidebar */
  #sidebar { width: 260px; background: var(--bg-panel); border-right: 1px solid var(--border); display: flex; flex-direction: column; z-index: 10; }
  .brand { padding: 24px 20px 10px; font-size: 24px; font-weight: 700; letter-spacing: 1px; display: flex; align-items: center; gap: 10px; }
  .subtitle { padding: 0 20px 20px; font-size: 12px; color: var(--text-muted); }
  
  .nav-menu { flex: 1; padding: 10px; display: flex; flex-direction: column; gap: 4px; }
  .nav-item { padding: 12px 16px; border-radius: 8px; cursor: pointer; color: var(--text-muted); font-size: 14px; font-weight: 500; transition: all 0.2s; display: flex; align-items: center; gap: 10px; }
  .nav-item:hover { background: rgba(255,255,255,0.05); color: var(--text-primary); }
  .nav-item.active { background: rgba(16, 163, 127, 0.15); color: var(--accent); }

  /* Main Area */
  #main { flex: 1; display: flex; flex-direction: column; overflow: hidden; position: relative; background: var(--bg-base); }
  .view { display: none; flex-direction: column; height: 100%; width: 100%; }
  .view.active { display: flex; }

  /* Chat View */
  #messages { flex: 1; overflow-y: auto; padding: 40px 15%; display: flex; flex-direction: column; gap: 24px; scroll-behavior: smooth; }
  
  .msg { padding: 0; line-height: 1.6; font-size: 15px; width: 100%; display: flex; gap: 16px; }
  .msg-avatar { width: 30px; height: 30px; border-radius: 4px; display: flex; align-items: center; justify-content: center; font-size: 14px; font-weight: bold; flex-shrink: 0; }
  .msg.user .msg-avatar { background: #5536d6; color: white; }
  .msg.nova .msg-avatar { background: var(--accent); color: white; }
  .msg.agent .msg-avatar { background: var(--plan-color); color: white; }
  
  .msg-content { flex: 1; overflow: hidden; }
  .msg.user .msg-content { font-weight: 500; }
  .msg.system { justify-content: center; color: var(--text-muted); font-size: 13px; text-align: center; font-style: italic; }

  /* Agentic Loop Styling */
  .agent-block { background: var(--bg-msg); border: 1px solid var(--border); border-radius: 8px; padding: 16px; font-family: var(--font-mono); font-size: 13px; color: var(--text-muted); }
  .plan-line { color: var(--plan-color); margin-bottom: 8px; font-weight: 600; font-family: var(--font-main); }
  .tool-line { color: var(--tool-color); margin-top: 4px; }
  .result-line { margin-left: 12px; font-style: italic; }
  .final-line { margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--border); color: var(--text-primary); font-family: var(--font-main); font-size: 14px; }

  /* Markdown Styles */
  .markdown-body pre { background: #0d1117; padding: 12px; border-radius: 6px; overflow-x: auto; margin: 10px 0; position: relative; }
  .markdown-body code { font-family: var(--font-mono); font-size: 13px; }
  .markdown-body p code { background: rgba(255,255,255,0.1); padding: 2px 4px; border-radius: 4px; }
  .markdown-body ul, .markdown-body ol { margin-left: 20px; margin-bottom: 10px; }
  .markdown-body table { border-collapse: collapse; width: 100%; margin: 10px 0; }
  .markdown-body th, .markdown-body td { border: 1px solid var(--border); padding: 8px; text-align: left; }
  
  .copy-btn { position: absolute; top: 8px; right: 8px; background: rgba(255,255,255,0.1); border: none; color: white; padding: 4px 8px; border-radius: 4px; cursor: pointer; font-size: 11px; }
  .copy-btn:hover { background: rgba(255,255,255,0.2); }

  /* Typing Indicator */
  .typing-indicator { display: flex; gap: 4px; align-items: center; height: 24px; }
  .typing-indicator span { width: 6px; height: 6px; background-color: var(--accent); border-radius: 50%; animation: typing 1.4s infinite ease-in-out both; }
  .typing-indicator span:nth-child(1) { animation-delay: -0.32s; }
  .typing-indicator span:nth-child(2) { animation-delay: -0.16s; }
  @keyframes typing { 0%, 80%, 100% { transform: scale(0); opacity: 0.5; } 40% { transform: scale(1); opacity: 1; } }

  /* Input Area */
  #input-area { padding: 20px 15% 30px; background: var(--bg-base); border-top: 1px solid transparent; display: flex; flex-direction: column; gap: 12px; }
  .input-wrapper { display: flex; align-items: flex-end; background: var(--bg-msg); border: 1px solid var(--border); border-radius: 12px; padding: 12px 16px; transition: border-color 0.2s; box-shadow: 0 4px 15px rgba(0,0,0,0.1); }
  .input-wrapper:focus-within { border-color: var(--accent); }
  
  #input { flex: 1; background: transparent; border: none; color: var(--text-primary); font-family: var(--font-main); font-size: 15px; resize: none; max-height: 200px; outline: none; line-height: 1.5; padding-right: 12px; }
  
  #send { background: var(--text-primary); color: var(--bg-base); border: none; border-radius: 8px; width: 32px; height: 32px; cursor: pointer; display: flex; align-items: center; justify-content: center; transition: opacity 0.2s; font-weight: bold; }
  #send:hover { opacity: 0.8; }
  #send:disabled { opacity: 0.3; cursor: not-allowed; }

  .mode-toggles { display: flex; gap: 10px; margin-bottom: 8px; }
  .mode-badge { font-size: 12px; color: var(--text-muted); cursor: pointer; user-select: none; transition: color 0.2s; }
  .mode-badge.active { color: var(--accent); font-weight: 600; }
  .mode-badge.active.agent { color: var(--plan-color); }

  /* Settings & Skills Views */
  .dashboard-view { padding: 40px 10%; overflow-y: auto; }
  .dashboard-title { font-size: 24px; font-weight: 600; margin-bottom: 20px; border-bottom: 1px solid var(--border); padding-bottom: 15px; display: flex; justify-content: space-between; align-items: center; }
  
  .section-title { font-size: 18px; font-weight: 600; margin: 30px 0 15px; color: var(--text-primary); display: flex; justify-content: space-between; align-items: center; }
  .card-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 20px; }
  .card { background: var(--bg-panel); border: 1px solid var(--border); border-radius: 12px; padding: 20px; }
  .card-title { font-size: 16px; font-weight: 600; margin-bottom: 10px; color: var(--accent); display: flex; justify-content: space-between; align-items: center;}
  .card-title.plugin { color: var(--plugin-color); }
  .card-title.mcp { color: var(--mcp-color); }
  .card-meta { font-size: 11px; color: var(--text-muted); font-family: var(--font-mono); margin-bottom: 10px; }
  .card-desc { font-size: 13px; color: var(--text-primary); line-height: 1.5; }
  
  .form-group { margin-bottom: 20px; }
  .form-group label { display: block; margin-bottom: 8px; font-size: 14px; color: var(--text-muted); }
  .form-group input, .form-group select { width: 100%; background: var(--bg-base); border: 1px solid var(--border); color: white; padding: 10px 12px; border-radius: 6px; font-family: var(--font-mono); font-size: 14px; outline: none; }
  .form-group input:focus { border-color: var(--accent); }
  
  .btn { background: var(--bg-msg); border: 1px solid var(--border); color: white; padding: 8px 16px; border-radius: 6px; cursor: pointer; font-size: 13px; font-weight: 500; transition: all 0.2s; }
  .btn-primary { background: var(--accent); border-color: var(--accent); }
  .btn-small { padding: 4px 10px; font-size: 12px; }
  .btn:hover { filter: brightness(1.2); }

  /* Modals */
  .modal-overlay { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.8); backdrop-filter: blur(5px); display: flex; justify-content: center; align-items: center; z-index: 100; opacity: 0; pointer-events: none; transition: opacity 0.3s; }
  .modal-overlay.active { opacity: 1; pointer-events: all; }
  .modal { background: var(--bg-panel); border: 1px solid var(--border); border-radius: 12px; width: 90%; max-width: 900px; max-height: 90vh; display: flex; flex-direction: column; box-shadow: 0 10px 40px rgba(0,0,0,0.5); }
  .modal-header { padding: 20px; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; font-size: 18px; font-weight: 600;}
  .modal-body { padding: 20px; flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 15px; }
  .modal-footer { padding: 20px; border-top: 1px solid var(--border); display: flex; justify-content: flex-end; gap: 10px; }
  .code-editor { font-family: var(--font-mono); font-size: 13px; background: #1e1e24; color: #ececf1; border: 1px solid var(--border); border-radius: 8px; padding: 15px; width: 100%; height: 350px; resize: none; outline: none; }
  .code-editor:focus { border-color: var(--plugin-color); }

  /* Scrollbar */
  ::-webkit-scrollbar { width: 8px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 4px; }
  
  .toast { position: fixed; bottom: 20px; right: 20px; background: var(--accent); color: white; padding: 12px 24px; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.2); transition: opacity 0.3s; opacity: 0; pointer-events: none; z-index: 1000; }
</style>
</head>
<body>

<div id="sidebar">
  <div class="brand">NOVA</div>
  <div class="subtitle">Command Center</div>
  
  <div class="nav-menu">
    <div class="nav-item active" onclick="switchTab('chat')">💬 Chat & Agente</div>
    <div class="nav-item" onclick="switchTab('skills')">🧩 Skills & MCPs</div>
    <div class="nav-item" onclick="switchTab('config')">⚙️ Configuración</div>
    <div class="nav-item" onclick="switchTab('logs')">📝 Logs & Memoria</div>
  </div>
</div>

<div id="main">
  <!-- CHAT VIEW -->
  <div id="view-chat" class="view active">
    <div id="messages">
      <div class="msg system">NOVA AI Backend Inicializado — Todo listo.</div>
    </div>
    
    <div id="input-area">
      <div class="mode-toggles">
        <span class="mode-badge active" id="badge-chat" onclick="setMode('chat')">Modo Chat</span>
        <span style="color: var(--border)">|</span>
        <span class="mode-badge" id="badge-agent" onclick="setMode('agent')">Modo Autónomo (Agente)</span>
      </div>
      <div class="input-wrapper">
        <textarea id="input" rows="1" placeholder="¿En qué te puedo ayudar hoy? (Shift+Enter para nueva línea)"></textarea>
        <button id="send" onclick="sendMsg()">↑</button>
      </div>
    </div>
  </div>

  <!-- SKILLS VIEW -->
  <div id="view-skills" class="view dashboard-view">
    <div class="dashboard-title">
      <span>🧩 Catálogo de Skills & Plugins</span>
    </div>

    <!-- MCP Section -->
    <div class="section-title">
      <span>🔌 Servidores MCP (Model Context Protocol)</span>
      <button class="btn btn-primary btn-small" onclick="openMcpModal()" style="background: var(--mcp-color); border-color: var(--mcp-color);">+ Añadir Servidor MCP</button>
    </div>
    <div class="card-grid" id="mcp-grid">
      <!-- Llenado dinamicamente -->
    </div>
    
    <!-- Plugins Section -->
    <div class="section-title">
      <span>📦 Plugins Externos (Cargados)</span>
      <button class="btn btn-primary btn-small" onclick="openPluginModal()" style="background: var(--plugin-color); border-color: var(--plugin-color);">✨ Crear Nuevo Plugin</button>
    </div>
    <div class="card-grid" id="plugins-grid">
      <!-- Llenado dinamicamente -->
    </div>

    <!-- Core Skills Section -->
    <div class="section-title">🛠️ Skills Nativas del Core</div>
    <div class="card-grid" id="skills-grid">
      <!-- Llenado dinamicamente -->
    </div>
  </div>

  <!-- CONFIG VIEW -->
  <div id="view-config" class="view dashboard-view">
    <div class="dashboard-title">⚙️ Configuración del Sistema</div>
    <div style="max-width: 600px;">
      <div class="card">
        <div class="card-title">Ajustes de Entorno (.env)</div>
        <div class="card-desc" style="margin-bottom: 20px;">Los cambios aquí se aplicarán al archivo local y tendrán efecto inmediato para nuevas operaciones.</div>
        
        <div class="form-group">
          <label>Voz del Sistema (NOVA_VOICE)</label>
          <div style="display: flex; gap: 10px;">
            <input type="text" id="env_voice" placeholder="Ej: Reed, Monica, edge-tts...">
            <button class="btn btn-primary" onclick="saveEnv('NOVA_VOICE', 'env_voice')">Guardar</button>
          </div>
        </div>
        
        <div class="form-group">
          <label>URL Ollama Local (OLLAMA_BASE_URL)</label>
          <div style="display: flex; gap: 10px;">
            <input type="text" id="env_ollama" placeholder="http://127.0.0.1:11434/v1">
            <button class="btn btn-primary" onclick="saveEnv('OLLAMA_BASE_URL', 'env_ollama')">Guardar</button>
          </div>
        </div>
        
        <div class="form-group">
          <label>Presupuesto Sesión (SESSION_BUDGET_USD)</label>
          <div style="display: flex; gap: 10px;">
            <input type="text" id="env_budget" placeholder="0.10">
            <button class="btn btn-primary" onclick="saveEnv('SESSION_BUDGET_USD', 'env_budget')">Guardar</button>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- LOGS VIEW -->
  <div id="view-logs" class="view dashboard-view">
    <div class="dashboard-title">📝 System Status & Memory</div>
    <div class="card">
      <div class="card-title">Diagnóstico</div>
      <div id="status-content" class="markdown-body" style="color: var(--text-muted); font-family: var(--font-mono); font-size: 13px;">
        Cargando métricas...
      </div>
    </div>
  </div>
</div>

<!-- Modal IDE para Plugins -->
<div class="modal-overlay" id="plugin-modal">
  <div class="modal">
    <div class="modal-header">
      <span>✨ Mini-IDE: Programar Nuevo Plugin</span>
      <button class="btn" onclick="closeModal('plugin-modal')" style="background:transparent; border:none; color:white; font-size:20px; cursor:pointer;">×</button>
    </div>
    <div class="modal-body">
      <div class="form-group">
        <label>Nombre interno del plugin (sin espacios ni .py, ej: mis_graficos):</label>
        <input type="text" id="plugin-name" placeholder="nombre_del_plugin">
      </div>
      <div class="form-group" style="flex:1;">
        <label>Código del Plugin (Python):</label>
        <textarea id="plugin-code" class="code-editor">
PLUGIN_META = {
    "name": "Mi Nueva Herramienta",
    "version": "1.0.0",
    "description": "Descripción general para el usuario.",
    "author": "Usuario de Nova",
}

def ejecutar_mi_accion(args: str) -> str:
    """Implementa la lógica real aquí."""
    return f"¡Herramienta ejecutada exitosamente con args: {args}!"

TOOL_CATALOG = {
    "mi_nueva_accion": (
        "Descripción detallada para que el LLM sepa exactamente cuándo invocarla.",
        ejecutar_mi_accion,
        "text" # Tipo de argumento: 'text', 'location', 'None'
    ),
}
</textarea>
      </div>
    </div>
    <div class="modal-footer">
      <button class="btn" onclick="closeModal('plugin-modal')">Cancelar</button>
      <button class="btn btn-primary" onclick="savePlugin()" style="background: var(--plugin-color); border-color: var(--plugin-color);">Guardar y Escribir en Disco</button>
    </div>
  </div>
</div>

<!-- Modal para MCP -->
<div class="modal-overlay" id="mcp-modal">
  <div class="modal" style="max-width: 600px;">
    <div class="modal-header">
      <span>🔌 Añadir Servidor MCP</span>
      <button class="btn" onclick="closeModal('mcp-modal')" style="background:transparent; border:none; color:white; font-size:20px; cursor:pointer;">×</button>
    </div>
    <div class="modal-body">
      <div class="form-group">
        <label>ID del Servidor (ej: fetch-mcp):</label>
        <input type="text" id="mcp-id" placeholder="identificador-unico">
      </div>
      <div class="form-group">
        <label>Comando (ej: python, npx, node):</label>
        <input type="text" id="mcp-cmd" placeholder="python">
      </div>
      <div class="form-group">
        <label>Argumentos (separados por coma, ej: -m,fetch_mcp):</label>
        <input type="text" id="mcp-args" placeholder="-m, my_module">
      </div>
      <div class="form-group">
        <label>Descripción:</label>
        <input type="text" id="mcp-desc" placeholder="Herramienta para buscar información">
      </div>
    </div>
    <div class="modal-footer">
      <button class="btn" onclick="closeModal('mcp-modal')">Cancelar</button>
      <button class="btn btn-primary" onclick="saveMcp()" style="background: var(--mcp-color); border-color: var(--mcp-color);">Guardar Servidor</button>
    </div>
  </div>
</div>

<div class="toast" id="toast">Guardado correctamente</div>

<script>
// Configure Marked.js
marked.setOptions({
  highlight: function(code, lang) {
    const language = hljs.getLanguage(lang) ? lang : 'plaintext';
    return hljs.highlight(code, { language }).value;
  },
  breaks: true
});

let mode = 'chat';
let busy = false;
let currentTypingIndicator = null;

function showToast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.style.opacity = 1;
  setTimeout(() => t.style.opacity = 0, 3000);
}

function openPluginModal() { document.getElementById('plugin-modal').classList.add('active'); }
function openMcpModal() { document.getElementById('mcp-modal').classList.add('active'); }
function closeModal(id) { document.getElementById(id).classList.remove('active'); }

async function savePlugin() {
  const name = document.getElementById('plugin-name').value.trim();
  const code = document.getElementById('plugin-code').value;
  if(!name) { alert("El nombre del plugin es obligatorio"); return; }
  
  try {
    const r = await fetch('/api/plugins', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, code })
    });
    if(r.ok) {
      showToast('Plugin guardado! (Reinicia Nova para cargar)');
      closeModal('plugin-modal');
      loadPlugins();
    } else {
      const err = await r.json();
      alert("Error: " + err.error);
    }
  } catch(e) { alert("Error de conexión"); }
}

async function saveMcp() {
  const id = document.getElementById('mcp-id').value.trim();
  const cmd = document.getElementById('mcp-cmd').value.trim();
  const args = document.getElementById('mcp-args').value.split(',').map(s => s.trim()).filter(s => s);
  const desc = document.getElementById('mcp-desc').value.trim();
  
  if(!id || !cmd) { alert("ID y Comando son obligatorios"); return; }
  
  try {
    const r = await fetch('/api/mcp', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id, cmd, args, desc })
    });
    if(r.ok) {
      showToast('Servidor MCP añadido con éxito');
      closeModal('mcp-modal');
      loadPlugins();
    } else {
      const err = await r.json();
      alert("Error: " + err.error);
    }
  } catch(e) { alert("Error de conexión"); }
}

function switchTab(tabId) {
  document.querySelectorAll('.nav-item').forEach(e => e.classList.remove('active'));
  document.querySelectorAll('.view').forEach(e => e.classList.remove('active'));
  
  event.currentTarget.classList.add('active');
  document.getElementById('view-' + tabId).classList.add('active');
  
  if(tabId === 'config') loadConfig();
  if(tabId === 'skills') loadPlugins();
  if(tabId === 'logs') loadStatus();
}

function setMode(m) {
  mode = m;
  document.getElementById('badge-chat').classList.toggle('active', m === 'chat');
  document.getElementById('badge-agent').classList.toggle('active', m === 'agent');
  document.getElementById('badge-agent').classList.toggle('agent', m === 'agent');
  
  document.getElementById('input').placeholder = m === 'agent' 
    ? 'Especifica el objetivo autónomo del Agente...' 
    : '¿En qué te puedo ayudar hoy? (Shift+Enter para nueva línea)';
}

const inp = document.getElementById('input');
inp.addEventListener('input', () => {
  inp.style.height = 'auto';
  inp.style.height = Math.min(inp.scrollHeight, 200) + 'px';
});

inp.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { 
    e.preventDefault(); 
    sendMsg(); 
  }
});

function scrollBottom() {
  const el = document.getElementById('messages');
  el.scrollTop = el.scrollHeight;
}

function addMessageFrame(who, cls) {
  const msgs = document.getElementById('messages');
  const div = document.createElement('div');
  div.className = 'msg ' + cls;
  
  const avatar = document.createElement('div');
  avatar.className = 'msg-avatar';
  avatar.textContent = who === 'user' ? 'U' : (cls === 'agent' ? '⚙️' : 'N');
  
  const content = document.createElement('div');
  content.className = 'msg-content markdown-body';
  
  div.appendChild(avatar);
  div.appendChild(content);
  msgs.appendChild(div);
  scrollBottom();
  
  return content;
}

function addTypingIndicator() {
  const container = addMessageFrame('nova', 'nova');
  container.innerHTML = '<div class="typing-indicator"><span></span><span></span><span></span></div>';
  currentTypingIndicator = container.parentElement;
}

function removeTypingIndicator() {
  if (currentTypingIndicator) {
    currentTypingIndicator.remove();
    currentTypingIndicator = null;
  }
}

function addCopyButtons(container) {
  container.querySelectorAll('pre').forEach(pre => {
    if(pre.querySelector('.copy-btn')) return;
    const btn = document.createElement('button');
    btn.className = 'copy-btn';
    btn.textContent = 'Copiar';
    btn.onclick = () => {
      navigator.clipboard.writeText(pre.innerText.replace('Copiar\n',''));
      btn.textContent = 'Copiado!';
      setTimeout(() => btn.textContent = 'Copiar', 2000);
    };
    pre.appendChild(btn);
  });
}

function setBusy(b) {
  busy = b;
  document.getElementById('send').disabled = b;
  inp.disabled = b;
}

function sendMsg() {
  if (busy) return;
  const q = inp.value.trim();
  if (!q) return;
  inp.value = ''; inp.style.height = 'auto';

  const userContainer = addMessageFrame('user', 'user');
  userContainer.textContent = q;
  setBusy(true);
  addTypingIndicator();

  if (mode === 'agent') streamAgent(q);
  else streamChat(q);
}

function streamChat(q) {
  let content = null;
  let rawText = '';
  
  const url = '/stream?q=' + encodeURIComponent(q);
  const es = new EventSource(url);
  
  es.onmessage = e => {
    if (!content) {
      removeTypingIndicator();
      content = addMessageFrame('nova', 'nova');
    }
    
    if (e.data === '[DONE]') {
      es.close(); setBusy(false); 
      content.innerHTML = marked.parse(rawText);
      addCopyButtons(content);
      return;
    }
    if (e.data.startsWith('[ERR]')) {
      content.innerHTML = `<span style="color:red">${e.data.slice(5)}</span>`;
      es.close(); setBusy(false); return;
    }
    rawText += e.data;
    content.innerHTML = marked.parse(rawText + ' ▍');
    scrollBottom();
  };
  es.onerror = () => { es.close(); setBusy(false); removeTypingIndicator(); };
}

function streamAgent(q) {
  let content = null;
  
  const url = '/agent?q=' + encodeURIComponent(q);
  const es = new EventSource(url);
  let buf = '';
  
  es.onmessage = e => {
    if (!content) {
      removeTypingIndicator();
      content = addMessageFrame('agent', 'agent');
      content.className = 'msg-content agent-block';
    }

    if (e.data === '[DONE]') {
      if (buf) renderAgentLine(content, buf);
      es.close(); setBusy(false); return;
    }
    if (e.data.startsWith('[ERR]')) {
      renderAgentLine(content, '❌ ' + e.data.slice(5));
      es.close(); setBusy(false); return;
    }
    buf += e.data;
    const lines = buf.split('\n');
    buf = lines.pop(); 
    for (const l of lines) {
      if (l.trim()) renderAgentLine(content, l);
    }
    scrollBottom();
  };
  es.onerror = () => { es.close(); setBusy(false); removeTypingIndicator(); };
}

function renderAgentLine(body, line) {
  const span = document.createElement('div');
  if (line.startsWith('📋')) span.className = 'plan-line';
  else if (line.startsWith('  ⚙️') || line.startsWith('⚙️')) span.className = 'tool-line';
  else if (line.startsWith('     →') || line.startsWith('   →')) span.className = 'result-line';
  else if (line.startsWith('✅') || line.startsWith('🔄')) span.className = 'final-line';
  
  span.innerHTML = marked.parseInline(line);
  body.appendChild(span);
}

// Backend APIs
async function loadConfig() {
  try {
    const r = await fetch('/api/config');
    const d = await r.json();
    document.getElementById('env_voice').value = d.NOVA_VOICE || '';
    document.getElementById('env_ollama').value = d.OLLAMA_BASE_URL || '';
    document.getElementById('env_budget').value = d.SESSION_BUDGET_USD || '';
  } catch(e) {}
}

async function saveEnv(key, inputId) {
  const val = document.getElementById(inputId).value;
  try {
    const r = await fetch('/api/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key, value: val })
    });
    if(r.ok) showToast('Configuración guardada (' + key + ')');
  } catch(e) { alert('Error guardando config'); }
}

async function loadPlugins() {
  try {
    const r = await fetch('/api/plugins');
    const data = await r.json();
    
    // MCP Grid
    const mcpGrid = document.getElementById('mcp-grid');
    mcpGrid.innerHTML = '';
    if(!data.mcps || Object.keys(data.mcps).length === 0) {
      mcpGrid.innerHTML = '<div style="color: var(--text-muted); font-size: 13px;">No hay servidores MCP configurados.</div>';
    } else {
      for (const [id, details] of Object.entries(data.mcps)) {
        mcpGrid.innerHTML += `
          <div class="card">
            <div class="card-title mcp">🔌 ${id}</div>
            <div class="card-meta">Cmd: ${details.command} ${details.args ? details.args.join(' ') : ''}</div>
            <div class="card-desc">${details.description || 'Servidor MCP sin descripción.'}</div>
          </div>
        `;
      }
    }

    // Plugins Grid
    const pGrid = document.getElementById('plugins-grid');
    pGrid.innerHTML = '';
    if(data.plugins.length === 0) {
      pGrid.innerHTML = '<div style="color: var(--text-muted); font-size: 13px;">No hay plugins externos cargados.</div>';
    } else {
      data.plugins.forEach(p => {
        pGrid.innerHTML += `
          <div class="card">
            <div class="card-title plugin">📦 ${p.name || 'Desconocido'}</div>
            <div class="card-meta">Versión: ${p.version || '1.0.0'} | Autor: ${p.author || 'Anónimo'}</div>
            <div class="card-desc">${p.description || 'Sin descripción.'}</div>
          </div>
        `;
      });
    }

    // Skills Grid
    const sGrid = document.getElementById('skills-grid');
    sGrid.innerHTML = '';
    for (const [k, v] of Object.entries(data.skills)) {
      sGrid.innerHTML += `
        <div class="card">
          <div class="card-title">⚡ ${k.replace(/_/g, ' ')}</div>
          <div class="card-desc">${v}</div>
        </div>
      `;
    }
  } catch(e) {}
}

async function loadStatus() {
  try {
    const r = await fetch('/api/status');
    const d = await r.json();
    document.getElementById('status-content').innerHTML = `
      <p><b>Daemon Online:</b> ${d.daemon ? 'Sí' : 'No'}</p>
      <p><b>Router Online:</b> ${d.router ? 'Sí' : 'No'}</p>
      <p><b>Proveedores Activos:</b> ${d.providers || 'Ninguno'}</p>
      <p><b>Plugins Cargados:</b> ${d.plugins}</p>
      <p><b>Directorio Root:</b> ${d.root_dir}</p>
    `;
  } catch(e) {}
}

// Initial load
loadStatus();
</script>
</body>
</html>'''

# ─── Request handler ──────────────────────────────────────────────────────────

class NovaWebHandler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        log.debug(fmt, *args)

    def _send_headers(self, content_type: str, status: int = 200, extra: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache")
        if extra:
            for k, v in extra.items():
                self.send_header(k, v)
        self.end_headers()

    def _sse_headers(self) -> None:
        self._send_headers("text/event-stream; charset=utf-8", extra={"X-Accel-Buffering": "no", "Connection": "keep-alive"})

    def _write_sse(self, data: str) -> bool:
        try:
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
            from nova.tools.nova_plugin_loader import loaded_plugins
            data = {
                "ok":        True,
                "daemon":    _daemon is not None,
                "router":    _router is not None and _router is not False,
                "providers": _router._active_provider if _router and _router is not False else "not_initialized",
                "plugins": len(loaded_plugins()),
                "root_dir": str(_SRC)
            }
            self._send_headers("application/json")
            self.wfile.write(json.dumps(data).encode())

        elif path == "/api/plugins":
            _init_nova()
            from nova.tools.nova_plugin_loader import loaded_plugins
            
            skills_dict = {}
            try:
                from nova.tools.nova_skills import _TOOL_CATALOG
                skills_dict = {k: v[0] for k, v in list(_TOOL_CATALOG.items())[:100]}
            except Exception:
                pass
                
            mcp_data = {}
            if MCP_CONFIG_PATH.exists():
                try:
                    with open(MCP_CONFIG_PATH, "r", encoding="utf-8") as f:
                        mcp_config = json.load(f)
                        mcp_data = mcp_config.get("mcpServers", {})
                except Exception:
                    pass

            data = {
                "plugins": loaded_plugins(),
                "skills": skills_dict,
                "mcps": mcp_data
            }
            self._send_headers("application/json")
            self.wfile.write(json.dumps(data, ensure_ascii=False).encode())
            
        elif path == "/api/config":
            # Leer el archivo .env
            env_vars = {}
            if ENV_PATH.exists():
                with open(ENV_PATH, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            env_vars[k.strip()] = v.strip().strip("'\"")
            self._send_headers("application/json")
            self.wfile.write(json.dumps(env_vars).encode())

        else:
            self._send_headers("text/plain", 404)
            self.wfile.write(b"Not found")

    def do_POST(self):
        if self.path == "/api/config":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length).decode("utf-8"))
                key = body.get("key")
                val = body.get("value")
                
                if key and val is not None:
                    # Sobrescribir en archivo
                    lines = []
                    found = False
                    if ENV_PATH.exists():
                        with open(ENV_PATH, "r", encoding="utf-8") as f:
                            lines = f.readlines()
                    
                    for i, line in enumerate(lines):
                        if line.startswith(key + "="):
                            lines[i] = f"{key}={val}\n"
                            found = True
                            break
                    if not found:
                        lines.append(f"{key}={val}\n")
                        
                    with open(ENV_PATH, "w", encoding="utf-8") as f:
                        f.writelines(lines)
                        
                    os.environ[key] = val
                    
                self._send_headers("application/json")
                self.wfile.write(b'{"ok":true}')
            except Exception as e:
                self._send_headers("application/json", 500)
                self.wfile.write(json.dumps({"error": str(e)}).encode())
                
        elif self.path == "/api/plugins":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length).decode("utf-8"))
                name = body.get("name", "").strip().replace(" ", "_")
                code = body.get("code", "")
                
                if not name:
                    self._send_headers("application/json", 400)
                    self.wfile.write(b'{"error":"El nombre es obligatorio"}')
                    return
                
                if not PLUGINS_DIR.exists():
                    PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
                
                plugin_file = PLUGINS_DIR / f"nova_plugin_{name}.py"
                
                with open(plugin_file, "w", encoding="utf-8") as f:
                    f.write(code)
                    
                self._send_headers("application/json")
                self.wfile.write(json.dumps({"ok": True, "file": str(plugin_file)}).encode())
                
            except Exception as e:
                self._send_headers("application/json", 500)
                self.wfile.write(json.dumps({"error": str(e)}).encode())
                
        elif self.path == "/api/mcp":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length).decode("utf-8"))
                mcp_id = body.get("id", "").strip()
                cmd = body.get("cmd", "").strip()
                args = body.get("args", [])
                desc = body.get("desc", "").strip()
                
                if not mcp_id or not cmd:
                    self._send_headers("application/json", 400)
                    self.wfile.write(b'{"error":"ID y Comando son obligatorios"}')
                    return
                
                mcp_config = {"mcpServers": {}}
                if MCP_CONFIG_PATH.exists():
                    with open(MCP_CONFIG_PATH, "r", encoding="utf-8") as f:
                        mcp_config = json.load(f)
                
                if "mcpServers" not in mcp_config:
                    mcp_config["mcpServers"] = {}
                    
                mcp_config["mcpServers"][mcp_id] = {
                    "command": cmd,
                    "args": args,
                    "description": desc
                }
                
                with open(MCP_CONFIG_PATH, "w", encoding="utf-8") as f:
                    json.dump(mcp_config, f, indent=2, ensure_ascii=False)
                    
                self._send_headers("application/json")
                self.wfile.write(json.dumps({"ok": True}).encode())
                
            except Exception as e:
                self._send_headers("application/json", 500)
                self.wfile.write(json.dumps({"error": str(e)}).encode())

        else:
            self._send_headers("text/plain", 404)
            self.wfile.write(b"Not found")

    # ── Chat streaming ────────────────────────────────────────────────────────
    def _stream_chat(self, q: str) -> None:
        _history.append({"role": "user", "content": q})
        chunks = []
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

        if _daemon:
            try:
                for chunk in _daemon.chat_stream(q, session="web"):
                    if not self._write_sse(chunk): return
                    chunks.append(chunk)
                _history.append({"role": "assistant", "content": "".join(chunks)})
                self._write_sse("[DONE]")
                return
            except Exception as e:
                log.debug("Daemon stream falló: %s", e)

        if _router:
            try:
                for chunk in _router.route_stream([{"role": "user", "content": q}]):
                    if not self._write_sse(chunk): return
                    chunks.append(chunk)
                _history.append({"role": "assistant", "content": "".join(chunks)})
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

        _DONE = object()
        q = _queue.Queue()

        def _worker():
            def _cb(msg: str) -> None:
                q.put(msg)
            try:
                from nova.tools.nova_skills import skill_agente
                final = skill_agente(goal, progress_cb=_cb)
                q.put(f"\n✅ **Resultado Final:**\n\n{final}")
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
                break

        self._write_sse("[DONE]")
        t.join(timeout=2)

# ─── Server lifecycle ─────────────────────────────────────────────────────────

_server_instance = None
_server_thread = None

def start(host: str = NOVA_WEB_HOST, port: int = NOVA_WEB_PORT, open_browser: bool = False) -> bool:
    global _server_instance, _server_thread
    if _server_instance is not None:
        return True
    try:
        _server_instance = ThreadingHTTPServer((host, port), NovaWebHandler)
        _server_thread = threading.Thread(target=_server_instance.serve_forever, daemon=True, name="nova-web")
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
        _server_thread = None
        log.info("[Web] Servidor detenido")

def is_running() -> bool:
    return _server_instance is not None

def url() -> str:
    if _server_instance is not None:
        host, port = _server_instance.server_address
        return f"http://{host}:{port}"
    return f"http://{NOVA_WEB_HOST}:{NOVA_WEB_PORT}"

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    _init_nova()
    port = NOVA_WEB_PORT
    print(f"\n  Nova Web Dashboard → http://127.0.0.1:{port}")
    print("  Ctrl+C para detener\n")
    srv = ThreadingHTTPServer((NOVA_WEB_HOST, port), NovaWebHandler)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n  Detenido.")
