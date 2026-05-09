# Nova — Asistente Personal Inteligente

Nova es un asistente personal avanzado con control por voz, visión, memoria neuronal, automatización y agentes especializados. Funciona en **macOS, Windows y Linux**. Respuestas en streaming token a token, daemon multi-sesión, y completamente offline con Ollama.

---

## Descargar e instalar

### Opción 1 — Instalador (recomendado)

Ir a [**Releases**](https://github.com/Ehr051/NOVA_Personal_Asistente/releases/latest) y descargar según tu sistema:

| Sistema | Archivo | Qué hace |
|---------|---------|----------|
| Windows | `Nova-Setup.exe` | Instalador completo — crea acceso directo en escritorio y comando `nova` en consola |
| Windows (portable) | `Nova-Windows.zip` | Sin instalación, descomprimí y ejecutá |
| macOS | `Nova-macOS.zip` | Descomprimí y ejecutá |
| Linux | `Nova-Linux.tar.gz` | Descomprimí y ejecutá |

El wizard te pide las API keys durante la instalación. Podés dejar cualquier campo vacío y configurarlo después diciendo _"nova, mi api de groq es gsk_xxxx"_.

### Opción 2 — Desde el código fuente

```bash
git clone https://github.com/Ehr051/NOVA_Personal_Asistente.git
cd NOVA_Personal_Asistente
python install.py        # crea .venv, instala deps, pide API keys, crea lanzador en Escritorio
```

**macOS / Linux:**
```bash
./launch_nova.sh         # activa .venv automáticamente
```
**Windows:**
```bash
launch_nova.bat          # activa .venv automáticamente
# o desde cualquier consola:
nova
```

### Desinstalar

```bash
python install.py --uninstall   # elimina .venv, lanzadores del escritorio, PATH en Windows
```

---

## API Keys necesarias

Nova funciona con proveedores gratuitos — no requiere OpenAI ni Anthropic:

| Provider | Variable | Límite gratuito | Link |
|----------|----------|-----------------|------|
| **Groq** | `GROQ_API_KEY` | 14.400 req/día | [console.groq.com](https://console.groq.com) |
| **Cerebras** | `CEREBRAS_API_KEY` | 30 req/min | [cloud.cerebras.ai](https://cloud.cerebras.ai) |
| **Mistral** | `MISTRAL_API_KEY` | tier gratuito | [console.mistral.ai](https://console.mistral.ai) |
| **OpenRouter** | `OPENROUTER_API_KEY` | modelos gratuitos | [openrouter.ai](https://openrouter.ai) |
| **Ollama** | — | sin límite (local) | [ollama.com](https://ollama.com) |

Con al menos una key Nova ya funciona. Ollama es opcional pero habilita modo completamente offline.

---

## Características

- **Control por voz** — wake word "Nova", barge-in para interrumpir, enrollado de speaker personalizado
- **Streaming token a token** — el REPL imprime la respuesta en tiempo real, como ChatGPT
- **Daemon multi-sesión** — proceso central TCP (puerto 7899) que arranca automáticamente; REPL y HUD se conectan como clientes, eliminando conflictos de Qdrant
- **Visión** — analiza cámara y pantalla vía Ollama local o OpenRouter como fallback
- **Agente autónomo** — `route_agentic()`: planifica, ejecuta tools en loop (Plan→Execute→Verify) y muestra el proceso en tiempo real, como Devin/Claude Code
- **185 agentes especializados** — Firmware Engineer, Software Architect, AI Engineer, Backend Architect y más, ejecutados con proveedores gratuitos
- **Modelado 3D en Blender** — genera scripts Python, los envía al addon MCP y auto-evalúa el resultado con visión
- **Memoria neuronal persistente** — Mem0 + Qdrant + embeddings locales
- **Cerebro/Obsidian** — búsqueda y escritura en vault `~/Cerebro/` via REST API
- **Automatización** — Google Calendar, Gmail, Drive, n8n, Telegram, volumen, apps, mouse/teclado
- **Skills sin API key** — traducción, crypto, tipo de cambio, feriados
- **Cross-platform** — macOS, Windows 10+, Linux
- **`.venv` aislado** — `install.py` crea un entorno virtual dedicado; los paquetes de Nova no afectan el sistema

---

## Uso básico

```
nova> qué hora es
nova> abre Safari y ve a youtube.com
nova> qué ves con la cámara
nova> busca en el cerebro agency-agents
nova> agenda una reunión con Juan mañana a las 15:00
nova> traduce "hello world" al español
nova> cuánto vale bitcoin ahora
nova> modela un tornillo hexagonal M6 en Blender
nova> recuerda que prefiero Python sobre JavaScript
nova> /agente buscá el precio de bitcoin y guardalo en una nota del Cerebro
nova> modo agente: analizá el repositorio y proponé 3 mejoras
```

### Comandos del sistema

```
/estado        Ver estado de todos los módulos
/skills        Listar skills disponibles
/memoria       Ver memorias guardadas
/silencio      Alternar modo silencioso (sin TTS)
/reiniciar     Recargar módulos en caliente
/ayuda         Lista completa de comandos
```

---

## Requisitos

- Python 3.10+ (solo si instalás desde código fuente)
- 8 GB RAM recomendado
- Micrófono y permisos de accesibilidad
- Ollama (opcional — para embeddings y visión offline)
- Blender + addon BlenderMCP (opcional — para modelado 3D)

---

## Arquitectura

```
src/nova/
├── cli/repl.py                  REPL principal (streaming token a token, /agente agentic loop)
├── core/
│   ├── nova_router.py           Router: Ollama → Groq → Cerebras → Mistral → OpenRouter
│   │                            + route_agentic() (Plan→Execute→Verify) + _call_with_tools()
│   ├── nova_daemon.py           Daemon TCP (puerto 7899) — singleton router + Qdrant
│   └── nova_client.py           Cliente thin: chat(), chat_stream(), ping(), ensure_daemon()
├── lang/novaesp.py              HUD + loop de voz
├── platform/                   Adaptadores por OS (macOS / Windows / Linux)
├── connectors/
│   ├── nova_blender.py          Blender MCP + auto-evaluación con visión
│   ├── nova_specialist.py       185 agentes especializados (diff+confirm ON by default)
│   └── nova_vision.py           Visión: cámara y pantalla
└── tools/
    ├── nova_skills.py           100+ skills · execute_tool() · skill_agente()
    ├── nova_tools_schemas.py    Auto-genera 48 JSON schemas OpenAI-compatible desde _TOOL_CATALOG
    └── nova_neuro_memory.py     Mem0 + Qdrant + embeddings locales
```

### Variables de entorno opcionales

| Variable | Default | Descripción |
|---|---|---|
| `NOVA_API_TIMEOUT` | `10` | Timeout en segundos por proveedor LLM |
| `NOVA_DAEMON_PORT` | `7899` | Puerto TCP del daemon |
| `NOVA_LOG_LEVEL` | `WARNING` | Nivel de log (`DEBUG`, `INFO`, `WARNING`) |
| `MAX_HISTORY` | `20` | Turnos de historial en memoria por sesión |
| `NOVA_DIFF_CONFIRM` | `1` | Mostrar diff y pedir confirmación antes de escribir archivos (`0` para desactivar) |

---

*Versión 3.8 — [Ver releases](https://github.com/Ehr051/NOVA_Personal_Asistente/releases)*
