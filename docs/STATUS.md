# Nova — Estado del Sistema

**Última actualización:** 2026-05-06 (sesión tarde)

## Estado general

Nova está operativo. REPL CLI completo, HUD redimensionable, Cerebro dinámico, orquestador paralelo, LLM tool dispatcher, skills de red/bluetooth/pronóstico.

## Componentes verificados

| Componente | Estado | Detalle |
|------------|--------|---------|
| HUD principal | ✅ | `src/nova/lang/novaesp.py` — PyQt5, always-on-top, redimensionable |
| Wake word | ✅ | "Nova" activa escucha — `pause_threshold=2.5s`, `phrase_time_limit=18s` |
| STT | ✅ | Reconocimiento ES/EN, speaker verification MFCC |
| TTS | ✅ | macOS nativo: Reed (ES) / Alex (EN) |
| Router LLM | ✅ | Ollama → Groq → OpenRouter (modelos curados), fallback automático |
| LLM Dispatcher | ✅ | `llm_dispatch()` — LLM elige tool cuando regex no matchea |
| Memoria neuronal | ✅ | Mem0 + Qdrant + `qwen3-embedding:4b` (2560 dims) — extracción vía Groq |
| Cerebro (Obsidian) | ✅ | `nova_cerebro.py` — file-based ~/Cerebro/ + REST si Obsidian corre |
| REPL CLI | ✅ | `nova` global, 25+ slash commands en español, autocomplete popup |
| Skills | ✅ | 100+ en `src/nova/tools/nova_skills.py` |
| Orquestador | ✅ | `/tarea` — planifica + ejecuta herramientas + pasos paralelos |
| Detector gestos | ✅ | `src/nova/perception/gesture_detector/` — integrado al repo |
| Red/Bluetooth | ✅ | `skill_scan_red()` — ARP instantáneo, `skill_scan_bluetooth()` — system_profiler |
| Imágenes por voz | ✅ | `nova_image.py` — Pollinations, steps=28, mejora LLM, análisis post-gen |
| Pronóstico 3 días | ✅ | Open-Meteo, sin API key, `get_forecast()` |
| Calendario Google | ✅ | `nova_google.py` — directo sin n8n, con fallback n8n |
| Telegram Send | ✅ | Funciona via n8n webhook |
| Telegram Receive | ⚠️ | Falta workflow de trigger — solo envío implementado |

## Agentes

| Agente | Archivo | Estado |
|--------|---------|--------|
| Morning Digest | `agents/morning_digest.py` | ✅ |
| Code Assistant | `agents/code_assistant.py` | ✅ |
| Orchestrator | `agents/nova_orchestrator.py` | ✅ Paralelo |
| Research | (vía REPL `/agente búsqueda`) | ✅ |

## Lanzamiento

```bash
# HUD principal (voz + escritorio)
python3 main.py

# REPL CLI (solo texto, sin voz)
nova                    # entra al REPL
nova skill "qué hora"   # skill directo
nova agent morning      # briefing
```

## Comandos REPL destacados

| Comando | Descripción |
|---------|-------------|
| `/ayuda` | Lista completa de comandos |
| `/cerebro [query]` | Buscar/leer en vault ~/Cerebro/ |
| `/tarea [objetivo]` | Orquestar tarea con herramientas reales |
| `/agente briefing` | Morning digest |
| `/doctor` | Diagnóstico del sistema |
| `/modelo [proveedor]` | Cambiar proveedor LLM en runtime |
| `/stats` | Estadísticas de uso de modelos |
| `/reenroll` | Re-registrar perfil de voz (3 rondas) |
| `/reiniciar` | Recargar módulos sin cerrar |

## HUD — Controles

| Gesto | Acción |
|-------|--------|
| Scroll ↕ en animación | Cambiar tamaño (65%/80%/100%/120%/140%) |
| Drag borde inferior (panel abierto) | Redimensionar área de log |
| Doble click | Cambiar tema (NEURAL/PLASMA/TORMENTA) |
| Click derecho | Toggle mute |
| Click izquierdo + arrastrar | Mover HUD |

## Configuración (`.env`)

```env
OLLAMA_BASE_URL=http://127.0.0.1:11434/v1
GROQ_API_KEY=...
OPENROUTER_API_KEY=...
ANTHROPIC_API_KEY=...          # opcional — Claude como alma
OPENAI_API_KEY=...             # opcional — GPT
OBSIDIAN_BASE_URL=https://127.0.0.1:27124
OBSIDIAN_API_KEY=...
CEREBRO_VAULT=~/Cerebro        # ruta al vault de Obsidian
ASSISTANT_NAME=Nova
NOVA_VOICE=Reed
SESSION_BUDGET_USD=0.10
TELEGRAM_BOT_TOKEN=...         # necesario para Telegram
TELEGRAM_CHAT_ID=...           # necesario para Telegram
```

## Memoria neuronal

- Mem0 + Qdrant local en `__DOTNOVA_PATH__/qdrant_db`
- Embedder Ollama (`qwen3-embedding:4b`, gratis, local)
- Métodos: `remember()`, `add_interaction()`, `search_context()`
- Cerebro dinámico: cada turno del REPL inyecta notas relevantes de ~/Cerebro/

## Arquitectura

```
src/nova/
├── agents/          # nova_orchestrator.py (paralelo), morning_digest, code_assistant
├── connectors/      # nova_cerebro.py, nova_blender.py, nova_vision.py, nova_n8n.py
├── core/            # nova_router.py, nova_memory.py
├── lang/            # novaesp.py (HUD principal)
├── perception/      # gesture_detector/ (MediaPipe)
├── tools/           # nova_skills.py (100+ skills), nova_neuro_memory.py
├── utils/           # nova_hud.py (NovaHUD/NovaWindow), nova_launcher.py
└── cli/             # repl.py (REPL con slash commands)
```

> `nova.*` es el namespace actual. No deberian quedar referencias activas al nombre historico anterior.

## Integraciones n8n activas

| Workflow | Estado |
|----------|--------|
| Email | ✅ Activo |
| Gastos | ✅ Activo |
| Calendario | ✅ Activo |
| Telegram Bot | ⚠️ Bug: solo workflow de envío (`nova_telegram_send.json`), falta workflow de recepción (Telegram Trigger → webhook) |

## Historial

- **2026-05-06:** Actualización de documentación, clarificación de arquitectura, mantenimiento de componentes existentes
- **2026-05-05:** Skills red/bluetooth (arp -an, system_profiler), pronóstico 3 días (Open-Meteo), mejora imágenes (LLM prompt + steps=28 + análisis post-gen), llm_dispatch (LLM elige tool cuando regex falla), mem0→Groq (no más 402 OpenRouter), pause_threshold=2.5s, OpenRouter modelos curados, nuevo repo GitHub NOVA-INTEGRATED-CLI-PLUS-VOICE-ASSISTANT
- **2026-05-04:** REPL completo (25 slash commands, autocomplete), HUD redimensionable + métricas, Cerebro dinámico file-based, /reenroll, orquestador paralelo, renombres finales a namespace Nova.
- **2026-05-02:** Restaurado morning_digest.py. Limpieza de repo.
- **2026-04-29:** Reorganización modular, CLI, 3 agentes, TTS multiidioma, PyQt5 HUD.

## Próximos pasos inmediatos

1. **Telegram Receive:** crear workflow n8n con Telegram Trigger → webhook Nova para recibir mensajes.
2. **Perception MCP:** cerrar smoke test initialize/list tools/call tool y documentar las tools disponibles.
3. **Memoria/RAG:** decidir si `nova_rag_obsidian.py` se repara, se elimina o queda deprecated frente a `nova_cerebro.py` + Mem0/Qdrant.
4. **Testing ampliado:** `python3.10 -m pytest -q` ya corre limpio (`6 passed, 4 skipped`); falta sumar mas smoke tests sin efectos laterales.
