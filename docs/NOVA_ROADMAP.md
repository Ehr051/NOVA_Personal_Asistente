# Nova — Estado del Proyecto y Roadmap
> **Archivo único de contexto.** Cualquier agente que tome este proyecto lee esto primero.  
> Última actualización: **2026-05-13 (sesión 9)**

---

## Progreso global

```
Voz/STT/TTS      ████████████████████ 100%
Memoria          ████████████████████ 100%  (vault OK, daemon gestiona Qdrant)
Código/Git       ████████████████████ 100%
Docker/Deploy    ████████████████████ 100%
HUD              ████████████████░░░░  80%  (falta modo pantalla completa)
Tests            ██████████████████░░  90%  (32 passed · 4 skipped opcionales)
LSP semántico    ████████████████████ 100%  (jedi completo)
Logging          ████████████████████ 100%  (novaesp.py limpio)
Telegram full    ████████████████████ 100%  (polling + webhook n8n)
OCR/Documentos   ████████████████████ 100%  (markitdown + pytesseract)
Modo políglota   ████████████████████ 100%  (explícito: ES/EN/FR/PT/DE/RU/ZH)
Cross-platform   ████████████████████ 100%  (macOS/Windows/Linux platform adapters completos)
Streaming LLM    ████████████████████ 100%  (REPL + daemon, token-by-token)
Tool calling     ████████████████████ 100%  (OpenAI JSON schema, 48 tools, agentic loop)
Plugins/Web UI   ████████████████████ 100%  (plugin loader + Web Dashboard SPA completo)
Daemon           ████████████████████ 100%  (TCP 7899, auto-launch, streaming)
Web Dashboard    ████████████████████ 100%  (SPA — Chat, Skills+MCP, Config, Logs)
```

---

## Arquitectura del sistema

```
┌─────────────────────────────────────────────────────────────────┐
│                          NOVA HUD                               │
│   PyQt5 · always-on-top · scroll=escala · tema NEURAL/PLASMA    │
│   [Animación] [Métricas: modelo/tokens/budget] [📎 adjuntos]    │
└──────────────────┬──────────────────────────────────────────────┘
                   │ voz + texto
┌──────────────────▼──────────────────────────────────────────────┐
│                       novaesp.py                                 │
│  STT (Google SR) · Speaker Verify (MFCC 0.87) · Wake Word       │
│  TTS (macOS Reed / edge-tts) · History manager · _build_msgs    │
└──────────────────┬──────────────────────────────────────────────┘
                   │
       ┌───────────▼───────────┐
       │     nova_skills.py    │  ◄─── 100+ skills, _INTENTS regex
       │   skill dispatch      │       _TOOL_CATALOG, LLM fallback
       └───────────┬───────────┘
                   │
    ┌──────────────┼──────────────┐
    ▼              ▼              ▼
┌───────┐   ┌──────────┐   ┌──────────────────┐
│Router │   │Specialist│   │  Memoria Neuronal │
│  LLM  │   │ (185 ag.)│   │  Mem0 + Qdrant   │
│Ollama │   │ Groq /   │   │  qwen3-emb:4b    │
│Groq   │   │ OpenRtr  │   │  + JSON fallback  │
│OpenRtr│   └──────────┘   └──────────────────┘
└───────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Integraciones                                │
│  Blender MCP · n8n · Telegram · Gmail · Calendar · Drive        │
│  Obsidian/Cerebro · MAIRA gestos · Imágenes (Pollinations)      │
│  Docker · Git · PyAutoGUI · Visión (cámara + pantalla)          │
└─────────────────────────────────────────────────────────────────┘
```

---

## Estado de componentes

| Componente | Archivo principal | Estado |
|---|---|:---:|
| HUD PyQt5 | `src/nova/utils/nova_hud.py` | ✅ |
| Motor de voz | `src/nova/lang/novaesp.py` | ✅ |
| Router LLM | `src/nova/core/nova_router.py` | ✅ |
| Skills (100+) | `src/nova/tools/nova_skills.py` | ✅ |
| 185 Agentes | `src/nova/connectors/nova_specialist.py` | ✅ |
| Memoria neuronal | `src/nova/tools/nova_neuro_memory.py` | ✅ |
| Cerebro/Obsidian | `src/nova/connectors/nova_cerebro.py` | ✅ |
| MCP Server | `src/nova/mcp/nova_mcp_server.py` | ✅ |
| Git-aware | skills en `nova_skills.py` | ✅ |
| Feedback loop | `ejecutar_con_feedback()` | ✅ |
| Diff view | `_color_diff()` + `_write_project_files()` | ✅ |
| Web search+docs | `codear_con_docs()` | ✅ |
| Auto tests | `generar_tests()` | ✅ |
| Docker | `dockerizar()` + `deploy_local()` | ✅ |
| Visión | `src/nova/connectors/nova_vision.py` | ✅ |
| Imágenes | `src/nova/tools/nova_image.py` | ✅ |
| Blender 3D | `src/nova/connectors/nova_blender.py` | ✅ |
| Gestos MAIRA | `src/nova/perception/gesture_detector/` | ✅ |
| Orquestador | `src/nova/agents/nova_orchestrator.py` | ✅ |
| REPL CLI | `src/nova/cli/repl.py` | ✅ |
| LSP semántico | `src/nova/connectors/nova_lsp.py` | ✅ |
| Telegram Receive | `src/nova/connectors/nova_telegram_server.py` | ✅ |
| Plugin system | `src/nova/tools/nova_plugin_loader.py` | ✅ |
| Web Dashboard SPA | `src/nova/web/nova_web_server.py` | ✅ (Chat+Agente, Skills+MCPs, Control Center, Logs) |
| Daemon/multi-sesión | `src/nova/core/nova_daemon.py` + `nova_client.py` | ✅ |
| Streaming LLM | `nova_router.route_stream()` + daemon `chat_stream` + `agent_stream` | ✅ |
| .venv + uninstall | `install.py` | ✅ |
| Tool calling nativo | `nova_tools_schemas.py` + `nova_router._call_with_tools()` | ✅ |
| Agentic loop | `nova_router.route_agentic()` Plan→Execute→Verify | ✅ |
| Diff+confirm por defecto | `NOVA_DIFF_CONFIRM` default `"1"` | ✅ |

---

## Roadmap de features

### ✅ Completado

| # | Feature | Estado |
|---|---|---|
| — | **Telegram Receive** | ✅ polling directo + webhook n8n en `nova_telegram_server.py` |
| — | **Logging unificado** | ✅ `nova_voice_stt`, `nova_mouse`, `nova_mcp_client` migrados |
| 5 | **LSP semántico** | ✅ `nova_lsp.py` — jedi: definición, referencias, rename, analyze, diagnose |
| — | **OCR + MarkItDown** | ✅ `nova_ocr.py` — PDF/DOCX/XLSX/imágenes → Markdown, `skill_leer_archivo` |
| — | **Modo políglota** | ✅ `_SESSION_LANG` explícito (usuario activa), ES/EN/FR/PT/DE/RU/ZH, TTS con voz del idioma |
| — | **Memoria/RAG** | ✅ `nova_rag_obsidian.py` → `legacy/`; vault completo en contexto (todas las carpetas) |
| — | **Requirements + CI** | ✅ `requirements.txt` completo, `install.py` cross-platform, GitHub Actions release por tag |

### ✅ Completado (sesión 9)

| # | Feature | Estado |
|---|---|---|
| — | **Web Dashboard SPA completo** | ✅ Refactor total: arquitectura SPA con sidebar de navegación, 4 pestañas: Chat/Agente, Skills+MCPs, Configuración, Logs |
| — | **Animaciones de pensamiento** | ✅ Typing indicator (3 puntos pulsantes estilo iMessage) durante procesamiento LLM |
| — | **Markdown + Highlighting** | ✅ Integrado `marked.js` + `highlight.js`; botones "Copiar" en bloques de código |
| — | **Vista Skills & Plugins** | ✅ Plugins externos con metadatos reales (`PLUGIN_META`). Skills nativas del core en grid |
| — | **Gestión de MCP Servers** | ✅ Lee/escribe `.mcp.json`; modal interactivo para añadir servidores MCP sin tocar archivos |
| — | **Mini-IDE de Plugins** | ✅ Editor de código integrado en el browser; guarda `nova_plugin_*.py` directamente en disco |
| — | **Control Center de Configuración** | ✅ 4 secciones: LLMs/API Keys, Voz+Audio (slider velocidad), Integraciones (Obsidian/Telegram/N8N/GitHub), Sistema |
| — | **API `/api/cerebro`** | ✅ Endpoint que expone el estado real de Obsidian (vault path, notas, API activa/inactiva) |
| — | **Gesture UI Qt estabilizada** | ✅ Thread-safe, auto-arranque, atajos de teclado recuperados, HUD táctico dark |

### ✅ Completado (sesión 8)

| # | Feature | Estado |
|---|---|---|
| — | **Web UI** | ✅ `nova_web_server.py`: ThreadingHTTPServer + SPA dark-theme, modos Chat y Agente, SSE streaming real-time. `/webui` en REPL. |
| — | **Plugin system** | ✅ `nova_plugin_loader.py`: carga `nova_plugin_*.py` desde `~/.nova/plugins/`. `INTENTS`, `TOOL_CATALOG`, `register()`. Plantilla en `plugins/`. |
| — | **Daemon `agent_stream`** | ✅ Tipo nuevo en protocolo TCP ndjson: agentic loop streameable desde cualquier cliente socket. |
| — | **Logging novaesp.py** | ✅ `print()` internos de diagnóstico migrados a `log.warning/info/debug`. |

### ✅ Completado (sesión 7)

| # | Feature | Estado |
|---|---|---|
| — | **Tool calling nativo** | ✅ `nova_tools_schemas.py`: auto-genera 48 JSON schemas OpenAI-compatible desde `_TOOL_CATALOG` |
| — | **Agentic loop** | ✅ `route_agentic()`: Plan (LLM genera plan numerado) → Execute (loop tool calls con progress_cb) → Verify (síntesis) |
| — | **`execute_tool()`** | ✅ Ejecuta cualquier tool del catálogo por nombre+args dict; usa `llm_dispatch` como primera opción |
| — | **`skill_agente()`** | ✅ Modo agente autónomo accesible por voz ("modo agente: X") y por REPL (`/agente X`) |
| — | **Diff+confirm por defecto** | ✅ `NOVA_DIFF_CONFIRM` default `"0"` → `"1"`; apagable con env var |

### ✅ Completado (sesión 6)

| # | Feature | Estado |
|---|---|---|
| — | **Daemon auto-launch** | ✅ `main.py` arranca daemon antes del HUD; `NovaDaemonClient(auto_start=True).ensure_daemon(wait=6s)` |
| — | **Streaming LLM — REPL** | ✅ `route_stream()` en router + `chat_stream()` en daemon + client; REPL imprime token a token |
| — | **Fix daemon `_handle_chat`** | ✅ Corregido: `router.chat()` → `router.route()`, `_build_messages` firma incorrecta → construido inline |
| — | **.venv isolation** | ✅ `install.py` crea `.venv/`, launchers activan venv automáticamente |
| — | **`--uninstall`** | ✅ `python install.py --uninstall` elimina `.venv`, lanzadores, PATH Windows |

### 🔴 Alta prioridad — siguiente

| # | Feature | Qué hay que hacer |
|---|---|---|
| — | **Qdrant SQLite cross-thread** | `__del__` de QdrantClient se llama desde GC thread ≠ creation thread. Fix real: monkey-patch `QdrantClient.__del__` tras `close()`. |
| — | **Tests suite ampliada** | `python3.10 -m pytest -q` pasa ~13/4skip. Añadir smoke tests para LSP, OCR, daemon/streaming, políglota. |

### 🟢 Baja prioridad

| # | Feature | Qué hay que hacer |
|---|---|---|
| 13 | **GitHub público** | Video demo 2min + badges de CI/cobertura. (README y GitHub Actions ya hechos) |

---

## Comparativa vs competidores

| Feature | Claude Code | Cursor | Copilot | **Nova** |
|---|:---:|:---:|:---:|:---:|
| Voz con speaker ID | ✗ | ✗ | ✗ | ✅ |
| Visión cámara | ✗ | ✗ | ✗ | ✅ |
| 185 agentes especializados | ✗ | ✗ | ✗ | ✅ |
| Planificador de misiones | ✗ | ✗ | ✗ | ✅ |
| Blender 3D | ✗ | ✗ | ✗ | ✅ |
| Control por gestos | ✗ | ✗ | ✗ | ✅ |
| Memoria vectorial persistente | parcial | ✗ | ✗ | ✅ |
| Vault Obsidian | ✗ | ✗ | ✗ | ✅ |
| Automatización del sistema | ✗ | ✗ | ✗ | ✅ |
| 100% local posible | ✗ | ✗ | ✗ | ✅ Ollama |
| Gratis | ✗ | ✗ | ✗ | ✅ |
| Docker awareness | ✗ | ✗ | ✗ | ✅ |
| Git-aware | ✅ | ✅ | parcial | ✅ |
| MCP server | ✅ | ✗ | ✗ | ✅ |
| Auto tests | ✅ | parcial | parcial | ✅ |
| Web search mientras codea | parcial | parcial | ✗ | ✅ |
| Feedback loop ejecución | ✅ | ✗ | ✗ | ✅ |
| LSP semántico | ✅ | ✅ | ✅ | ✅ |
| Multi-sesión / daemon | ✅ | ✅ | ✅ | ✅ auto-launch + streaming |
| Tool calling nativo | ✅ | parcial | ✗ | ✅ 48 tools, agentic loop |
| Web UI browser | ✅ | ✅ | ✅ | ✅ SSE streaming, Chat + Agente |
| Plugin system | ✅ | ✅ | ✅ | ✅ `~/.nova/plugins/` sin tocar core |

---

## Cómo lanzar

```bash
# HUD principal (voz + escritorio)
python3 main.py

# REPL CLI (solo texto)
nova
nova skill "qué hora"
nova agent morning

# Verificación base
python3.10 -m py_compile main.py src/nova/tools/nova_skills.py
python3.10 -m pytest -q
# Esperado: ~13 passed, ~4 skipped
```

### Variables `.env` clave

```env
GROQ_API_KEY=gsk_...          # LLM primario (gratis tier)
OPENROUTER_API_KEY=sk-or-...  # LLM fallback (muchos modelos free)
OLLAMA_BASE_URL=http://127.0.0.1:11434/v1   # LLM local
CEREBRO_VAULT=~/Cerebro       # Vault Obsidian
ASSISTANT_NAME=Nova
NOVA_VOICE=Reed               # macOS TTS
NOVA_DIFF_CONFIRM=1           # 1 = confirmar diffs antes de aplicar (default ON desde v3.8)
NOVA_AUTO_TESTS=0             # 1 = pytest automático al escribir .py
SESSION_BUDGET_USD=0.10
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

---

## Reglas para agentes que continúen este proyecto

1. **Namespace:** siempre `nova.*` — no usar el nombre histórico anterior en código, docs, CLI ni tests.
2. **No romper:** no revertir cambios existentes del usuario sin confirmación explícita.
3. **Fallback obligatorio:** cualquier feature que dependa de Ollama/n8n/Obsidian/Blender debe funcionar en modo degradado sin ellos.
4. **Tests:** agregar o actualizar prueba cuando se toca dispatcher, memoria, router, MCP o skills críticas.
5. **Este archivo:** actualizar la sección "Log de sesiones" con lo que se hizo antes de cada commit.
6. **Commits atómicos:** mensajes que expliquen el "por qué", no solo el "qué".

---

## HUD — controles

| Acción | Efecto |
|---|---|
| Scroll ↕ sobre la animación | Cambiar tamaño: 65% / 80% / 100% / 120% / 140% |
| Doble click en animación | Cambiar tema: NEURAL → PLASMA → TORMENTA |
| Click derecho | Toggle mute |
| Click izquierdo + arrastrar | Mover HUD |
| Drag borde inferior (panel abierto) | Redimensionar área de log |
| Botón 📎 | Adjuntar archivo (texto / PDF / imagen) al próximo mensaje |

---

## Log de sesiones

### 2026-05-08 (sesión 7)
- ✅ **Tool calling nativo** — `nova_tools_schemas.py`: auto-genera 48 JSON schemas OpenAI-compat desde `_TOOL_CATALOG`; `route_with_tools_simple()` para dispatch rápido; `llm_dispatch()` intenta tool calling antes de text-matching
- ✅ **Agentic loop** — `route_agentic()` en router: Phase 1 genera plan numerado visible al usuario, Phase 2 loop de tool calls con `progress_cb`, Phase 3 síntesis si se agota `max_iter`
- ✅ **`execute_tool(name, kwargs)`** — ejecuta cualquier tool del catálogo con args dict; maneja `arg_type=None/text/location/custom`
- ✅ **`skill_agente()`** + intents de voz — "modo agente: X" / "autónomamente X" activan el loop; `/agente X` en REPL rutea a agentic loop si no hay sub-agente nombrado
- ✅ **Diff+confirm por defecto** — `NOVA_DIFF_CONFIRM` default `"0"` → `"1"` en `nova_specialist.py`; apagable con env var
- Commit: `3acbfe5`

### 2026-05-08 (sesión 6)
- ✅ **Daemon auto-launch** — `main.py` arranca daemon antes del HUD; `NovaDaemonClient(auto_start=True).ensure_daemon(wait=6s)`
- ✅ **Streaming LLM — REPL** — `route_stream()` en router + `chat_stream()` en daemon + client; REPL imprime token a token
- ✅ **Fix daemon `_handle_chat`** — Corregido: `router.chat()` → `router.route()`, `_build_messages` firma incorrecta → construido inline
- ✅ **.venv isolation** — `install.py` crea `.venv/`, launchers activan venv automáticamente
- ✅ **`--uninstall`** — `python install.py --uninstall` elimina `.venv`, lanzadores, PATH Windows
- Commits: `9784b6d`, otros

### 2026-05-08 (sesión 5)
- ✅ **Timeout LLM** — `_API_TIMEOUT=10s` con `timeout=` directo en OpenAI clients; fallback rápido si proveedor no responde en tiempo
- ✅ **Cámara** — patrón "que ves en mi camara" / "qué ves en mi cámara" no matcheaba; agregado `en\s+(?:mi\s+)?` al regex de `skill_ver_camara`
- ✅ **Crash silencioso Windows** — `main.py` captura todas las excepciones, muestra MessageBox + escribe `nova_crash.log` junto al `.exe`
- ✅ **nova.spec** — 20+ hiddenimports agregados: `nova_client`, `nova_daemon`, `nova_hud`, `PyQt5.QtWebEngine`, `qdrant_client.http`, etc.
- ✅ **Installer completo** — wizard Inno Setup con 2 páginas: LLM Providers (6 campos) + Integraciones (4 campos); `DisableDirPage=no`
- ✅ **install.py** — pregunta 10 keys organizadas en 2 grupos; detecta escritorio en ES/EN/FR/DE; mensaje final claro
- ✅ **Modelos dinámicos** — `add_custom_provider()` en router + `skill_agregar_modelo()` + `skill_listar_modelos()`; formato `CUSTOM_PROVIDERS=Name|url|key|model`
- ✅ **ICO multi-resolución** — 6 tamaños (16/32/48/64/128/256), `IconLocation` con `,0`
- ✅ **Daemon HUD** — `novaesp.py` usa `NovaDaemonClient` cuando el daemon está activo; sin Qdrant propio
- Commits: `6d3bd36`, `11fba8a`, `348acf5`, `ba4151b`, `4d7207a`, `38a17dd`

### 2026-05-07 (sesión 2)
- ✅ **OCR + MarkItDown** — `nova_ocr.py`: PDF/DOCX/XLSX/imágenes → Markdown, `skill_leer_archivo` en nova_skills.py
- ✅ **Modo políglota** — `_detect_lang()` heurística EN/FR/PT, system prompt dinámico, speak() selecciona voz por idioma
- ✅ **Vault completo** — `load_vault_context()` modo file-based escanea TODO ~/Cerebro/ (no solo NOVA/); `_vault_context_for()` con fallback a `cerebro_buscar()`
- ✅ **Memoria/RAG** — `nova_rag_obsidian.py` movido a `legacy/` con nota de deprecación
- ✅ **requirements.txt** completo + `install.py` con jedi/markitdown/langdetect/pytesseract cross-platform
- ✅ **GitHub Actions** — `release.yml`: release automático + changelog cuando se pushea tag v*
- Commits: `041960a`, `a039971`

### 2026-05-07 (sesión actual — continuación)
- ✅ **#5 LSP** — `nova_lsp.py` con jedi: `find_symbol_in_project`, `analyze_file`, `find_definition`, `find_references`, `rename_symbol`, `diagnose_file`, `get_signature`
- ✅ Skills LSP en `nova_skills.py`: `skill_lsp_definicion`, `skill_lsp_referencias`, `skill_lsp_analizar`, `skill_lsp_diagnostico`, `skill_lsp_renombrar`
- ✅ Logging: `nova_voice_stt.py`, `nova_mouse.py`, `nova_mcp_client.py` migrados de print() a logging
- ✅ Verificado: Telegram Receive ya implementado en `nova_telegram_server.py` (polling + webhook)
- Commit: `38929b8`

### 2026-05-07 (sesión actual)
- ✅ **#9 Docker** — `_detect_stack()`, `dockerizar()`, `deploy_local()` en `nova_specialist.py`
- ✅ **HUD métricas** — `_last_tokens` persistente; skill calls no resetean el contador
- ✅ **HUD resize** — `wheelEvent` override + `_install_view_filter` en child Chromium con retry
- ✅ **Consolidación docs** — `Cerebro/JARVIS → Cerebro/NOVA`; 3 archivos → este único
- Commits: `e923bb7`, `a20be24`, `d240643`

### 2026-05-07 (sesión extendida — items #4 al #8 + HUD)
- ✅ **#4** `ejecutar_con_feedback()` — REPL de agente con auto-corrección (max 3 iter)
- ✅ **#6** `_color_diff()` — diff ANSI antes de escribir archivos
- ✅ **#7** `codear_con_docs()` — DDG + docs reales como contexto al LLM
- ✅ **#8** `generar_tests()` — pytest via code-reviewer agent, `NOVA_AUTO_TESTS=1`
- ✅ **HUD** barra modelo/tokens/provider/budget + botón 📎 adjuntos
- ✅ **mem0 fix** — upsert directo, bypass pipeline LLM → resuelve 413 rate limit Groq
- ✅ **speaker fix** — threshold 0.87, wake word siempre obligatoria sin perfil
- ✅ **SQLite thread fix** — `save_turn()` desactiva `self.m` en hilos background
- ✅ **imagen fix** — protocol `__HUD_IMG__:name:mime:b64[::caption]`
- Commits: `fe3c94c`, `fc5ab5c`, `ee57424`, `cf27169`

### 2026-05-06
- ✅ `_clean_for_speech`: strip emojis, rutas→nombre, slashes→espacio
- ✅ `_build_messages`: normaliza content multimodal → resuelve Error 400 Groq historial con imágenes
- ✅ `_INTENTS`: patrón `skill_abrir_proyecto` requiere keyword "proyecto"
- ✅ `skill_listar_carpeta_activa`: lista directorio real, evita alucinaciones
- Commit: `27cb0a3`

### 2026-05-05
- ✅ `planear_mejoras_proyecto()`, `formatear_misiones()`, orquestador paralelo
- ✅ Skills red/bluetooth, pronóstico 3 días, dispatcher LLM, mem0→Groq
- ✅ MAIRA: MediaPipe.js client-side, gesture_service.py
- Commits: `e407e40`, `7969c25`

### 2026-04-29 → 2026-05-04
- ✅ REPL completo (25 slash commands), HUD redimensionable
- ✅ Cerebro dinámico file-based, `/reenroll`, orquestador paralelo
- ✅ Reorganización modular final al namespace `nova.*`

---

*Documento vivo — actualizar antes de cada commit.*
