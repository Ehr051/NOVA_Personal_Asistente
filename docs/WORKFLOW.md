# Nova Project Workflow

**Ultima actualizacion:** 2026-05-07  
**Modo de trabajo:** tablero operativo por ciclos cortos. El historico largo queda en `NOVA_ROADMAP.md`; este archivo define que se trabaja ahora, como se valida y cuando se cierra.

## Estado Actual

Nova esta operativo para uso diario: HUD PyQt5, REPL CLI, router LLM, memoria neuronal, Cerebro file-based, skills locales, Blender MCP, orquestador paralelo y dispatcher LLM.

La auditoria de Markdown del 2026-05-06 encontro que la documentacion mezclaba tres cosas: estado real, historial de implementacion y deseos futuros. Desde ahora:

- `STATUS.md`: foto corta del sistema actual.
- `WORKFLOW.md`: cola activa de trabajo y criterios de cierre.
- `NOVA_ROADMAP.md`: direccion tecnica, fases y backlog priorizado.
- `docs/*.md`: guias especificas de setup, arquitectura o integracion.

## Pendientes Activos

| Prioridad | Tema | Estado | Criterio de salida |
|---|---|---|---|
| P0 | Telegram Receive | **Resuelto** | Polling directo con TELEGRAM_BOT_TOKEN + webhook HTTP para n8n. 7 tests green. Arranca en HUD y REPL. |
| P0 | Suite de verificacion local | **Resuelto** | 13 passed, 4 skipped (integración real gated). |
| P1 | Limpieza de documentacion | En curso | README, STATUS, ROADMAP y docs no se contradicen en namespace, memoria, imagenes, CLI y rutas. |
| P1 | Manejo de errores y logging | Pendiente | Skills criticas devuelven errores accionables; logs usan logger donde hoy hay prints dispersos; sin trazas innecesarias en uso normal. |
| P1 | Perception MCP | **Resuelto** | 5 tests green — get_all, safe defaults, error handling, analyze_camera, analyze_screen. |
| P2 | OCR y UI recognition + intake de archivos | Pendiente | MarkItDown convierte cualquier archivo (PDF/DOCX/XLSX/imagen/audio) a MD antes de procesarlo; `nova_vision` extrae texto de pantalla. |
| P2 | Memoria/RAG Obsidian | Pendiente | Mem0+Qdrant = memoria episodica/semantica de largo plazo; Cerebro/Obsidian = base de conocimiento estructurado. `nova_rag_obsidian.py` deprecated → eliminar. |
| P2 | Skills/plugins externos | Pendiente | Definir formato minimo para skill externa, instalacion, listado y desinstalacion sin romper skills nativas. |
| P3 | Modo Polglota | Pendiente | Nova detecta idioma del mensaje entrante (voz o texto) y responde en el mismo idioma. Sin config manual — auto-deteccion. Aplica a REPL, HUD y Telegram. |

## Ciclo Recomendado

1. Elegir un item P0/P1 y abrir una rama o checkpoint logico.
2. Reproducir el estado actual con un comando concreto.
3. Implementar el cambio minimo que cierre el criterio de salida.
4. Ejecutar verificacion automatica o smoke test manual documentado.
5. Actualizar `STATUS.md` si cambia el estado real.
6. Actualizar `NOVA_ROADMAP.md` si se mueve una fase o aparece deuda nueva.
7. Hacer commit logico cuando el arbol quede estable.

## Verificacion Base

Comandos esperados para cada ciclo:

```bash
python3.10 -m py_compile main.py src/nova/tools/nova_skills.py
python3.10 -m py_compile src/nova/perception/mcp_server.py tests/test_perception_mcp.py
python3.10 -m pytest -q
```

Nota de auditoria 2026-05-06: `python3.10 -m pytest -q` pasa con `6 passed, 4 skipped`. Los tests salteados son scripts manuales que tocan escritorio, n8n, GitHub, Ollama o workflows externos; se ejecutan explicitamente con variables `NOVA_RUN_DISPATCHER_TESTS`, `NOVA_RUN_INTEGRATION_TESTS`, `NOVA_RUN_N8N_TESTS` o `NOVA_RUN_LEGACY_TEXT_TESTS`.

## Checklist Por Cambio

- [ ] No revertir cambios existentes del usuario.
- [ ] Mantener imports bajo namespace `nova.*`; no introducir nombres historicos en codigo, docs, CLI ni tests.
- [ ] No agregar nuevas API keys obligatorias para funciones core.
- [ ] Mantener fallback local o mensaje claro cuando falta Ollama, n8n, Obsidian, Blender o permisos de macOS.
- [ ] Agregar o actualizar prueba cuando se toca dispatcher, memoria, router, MCP o skills criticas.
- [ ] Actualizar documentacion solo donde cambia comportamiento real.

## Siguiente Sprint Sugerido

1. P1 Logging: reemplazar prints criticos por `logging.getLogger` en skills y router; errores accionables.
2. P2 Plugin format: definir `nova_plugin_*.py` con `PLUGIN_META` dict + `register(skills_module)`.
3. P2 Memoria: deprecar/eliminar `nova_rag_obsidian.py`; documentar arquitectura dual Mem0+Cerebro.
4. P2 OCR + MarkItDown: intake de archivos en REPL y Telegram; extraccion de texto de pantalla.
5. P3 Modo Polglota: deteccion automatica de idioma + respuesta en mismo idioma (REPL/HUD/Telegram).

## Historico Resumido

- 2026-05-07: Telegram bidireccional (polling directo + webhook n8n), 13 tests green, Inno Setup fix CI, modo polglota al roadmap.
- 2026-05-06: auditoria de Markdown, tablero operativo renovado, pendientes priorizados.
- 2026-05-05: red/bluetooth, pronostico, dispatcher LLM, mem0 via Groq, mejoras de imagen, OpenRouter curado.
- 2026-05-04: REPL completo, HUD redimensionable, Cerebro dinamico, `/reenroll`, orquestador paralelo.
- 2026-04-29: reorganizacion modular, CLI, agentes base, TTS multiidioma, HUD PyQt5.
