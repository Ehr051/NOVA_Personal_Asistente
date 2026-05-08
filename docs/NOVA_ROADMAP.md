# Nova — Estado del Proyecto y Roadmap
> **Archivo único de contexto.** Cualquier agente que tome este proyecto lee esto primero.  
> Última actualización: **2026-05-08 (sesión 4)**

---

## Progreso global

```
Voz/STT/TTS      ████████████████████ 100%
Memoria          ████████████████████ 100%  (vault OK, daemon gestiona Qdrant)
Código/Git       ████████████████████ 100%
Docker/Deploy    ████████████████████ 100%
HUD              ████████████████░░░░  80%  (falta modo pantalla completa)
Tests            ████████████░░░░░░░░  60%  (faltan más smoke tests)
LSP semántico    ████████████████████ 100%  (jedi completo)
Logging          ███████████████████░  95%  (~20 prints debug en novaesp.py)
Telegram full    ████████████████████ 100%  (polling + webhook n8n)
OCR/Documentos   ████████████████████ 100%  (markitdown + pytesseract)
Modo políglota   ████████████████████ 100%  (explícito: ES/EN/FR/PT/DE/RU/ZH)
Cross-platform   ████░░░░░░░░░░░░░░░░  20%  (install.py + API key fix listo)
Plugins/Web UI   ░░░░░░░░░░░░░░░░░░░░   0%
Daemon           ████████████████████ 100%  (TCP 7899, REPL + HUD integrados)
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
| Plugin system | — | ❌ pendiente |
| Web UI | — | ❌ pendiente |
| Daemon/multi-sesión | `src/nova/core/nova_daemon.py` + `nova_client.py` | 🔄 60% |

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

### 🔴 Alta prioridad — siguiente

| # | Feature | Qué hay que hacer |
|---|---|---|
| — | **Daemon multi-sesión** | TCP 7899 listo + REPL integrado. Falta: integrar HUD (`novaesp.py`) para que use `NovaDaemonClient` en lugar de instanciar router local. |
| — | **Qdrant SQLite cross-thread** | `__del__` de QdrantClient se llama desde GC thread ≠ creation thread. Workaround en `close()` no basta. Fix real: monkey-patch `QdrantClient.__del__` tras `close()`. |
| — | **Tests suite ampliada** | `python3.10 -m pytest -q` pasa ~13/4skip. Añadir smoke tests para LSP, OCR, Docker, políglota. |

### 🟡 Media prioridad

| # | Feature | Qué hay que hacer |
|---|---|---|
| — | **Logging novaesp.py** | ~20 `print()` de debug/status sin migrar. Los de "Auxiliar:" / "Tú:" son UI intencional — se quedan. |
| — | **Plugin system** | `nova_plugin_*.py` con `PLUGIN_META` dict + `register(skills_module)`. Carga automática al arrancar. Permite añadir skills sin tocar el core. |

### 🟢 Baja prioridad

| # | Feature | Qué hay que hacer |
|---|---|---|
| 10 | **Windows/Linux** | `src/nova/platform/` con `macos.py`, `windows.py`, `linux.py` + `adapter.py`. ~2-3 días. |
| 11b | **Nova Web UI** | REPL web en localhost. Historial, panel de skills, estado de memoria. Complementa voz. |
| 13 | **GitHub público** | README + video demo 2min + badges. (GitHub Actions ya hecho) |

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
| Multi-sesión / daemon | ✅ | ✅ | ✅ | ❌ pendiente |

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
NOVA_DIFF_CONFIRM=0           # 1 = confirmar diffs antes de aplicar
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
