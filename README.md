# Nova: Asistente Personal Inteligente

Nova es un asistente personal avanzado con capacidades de voz, visión, automatización y agentes especializados. Funciona en **macOS, Windows y Linux**.

## ✨ Características Principales

- **Control por Voz**: Reconocimiento de voz con enrollado de speaker personalizado (coherencia 0.997)
- **Visión por Computadora**: Analiza cámara y pantalla vía Ollama local o OpenRouter (fallback automático)
- **Agentes Especializados**: 185 agentes integrados — Firmware Engineer, Software Architect, AI Engineer, Backend Architect y más — ejecutados con proveedores gratuitos sin consumir créditos de Claude
- **Creación de Proyectos**: Genera proyectos completos con archivos reales en disco y `git init` por voz
- **Modelado 3D con Blender**: Genera scripts Python, envía al addon MCP y auto-evalúa con visión comparando contra referencia de cámara
- **Memoria Neuronal Persistente**: Mem0 + Qdrant + embeddings locales `qwen3-embedding:4b` en Ollama
- **Cerebro/Obsidian**: Búsqueda y escritura en el vault completo `~/Cerebro/` via REST API
- **Automatización del Sistema**: Google Calendar, Gmail, Drive, n8n, Telegram, volumen, apps, mouse/teclado
- **Generación de Imágenes**: Expansión de prompt por LLM + Pollinations/Flux sin API key
- **Skills sin API key**: Traducción, cotizaciones crypto, tipo de cambio, feriados por país

## 🚀 Instalación

```bash
git clone https://github.com/Ehr051/NOVA-INTEGRATED-CLI-PLUS-VOICE-ASSISTANT.git
cd NOVA-INTEGRATED-CLI-PLUS-VOICE-ASSISTANT
python install.py        # detecta tu OS e instala las dependencias correctas
cp .env.example .env
# Editar .env con tus API keys
```

**macOS:**
```bash
./launch_nova.sh
```

**Windows / Linux:**
```bash
python main.py
```

### Verificar instalación

```bash
python install.py --check
```

## 📋 Requisitos del Sistema

| Sistema | Versión mínima |
|---------|---------------|
| macOS   | 12.0+ (Monterey) |
| Windows | 10+ (64-bit) |
| Linux   | Ubuntu 20.04+ / Debian 11+ |

- Python 3.10+
- 8GB+ RAM recomendado
- Ollama corriendo localmente (para embeddings y visión offline — **opcional**, Nova funciona con Groq/Cerebras si no está disponible)
- Blender + addon BlenderMCP (opcional, para modelado 3D)
- Permisos de accesibilidad y micrófono

### Dependencias de sistema (Linux)

```bash
sudo apt install espeak-ng mpg123 xclip scrot
```

## 🔧 Configuración `.env`

```env
# ── Proveedores de IA (gratuitos) ─────────────────────────────────────────────
GROQ_API_KEY=tu_clave_aqui            # https://console.groq.com  (gratuito)
CEREBRAS_API_KEY=tu_clave_aqui        # https://cloud.cerebras.ai (gratuito)
MISTRAL_API_KEY=tu_clave_aqui         # https://console.mistral.ai (gratuito)
CODESTRAL_API_KEY=tu_clave_aqui       # https://codestral.mistral.ai (gratuito, coding)
OPENROUTER_API_KEY=tu_clave_aqui      # https://openrouter.ai  (fallback, visión)

# ── Proveedores de IA (pagados, desactivados por defecto) ─────────────────────
# DEEPSEEK_API_KEY=tu_clave_aqui      # descomentar + agregar "deepseek" al orden

# ── Orden de fallback ─────────────────────────────────────────────────────────
ROUTER_PROVIDER_ORDER=ollama,groq,cerebras,mistral,openrouter

# ── Ollama (local) ────────────────────────────────────────────────────────────
OLLAMA_BASE_URL=http://127.0.0.1:11434/v1

# ── Obsidian Cerebro ──────────────────────────────────────────────────────────
OBSIDIAN_BASE_URL=https://127.0.0.1:27124
OBSIDIAN_API_KEY=tu_clave_aqui

# ── Voz ───────────────────────────────────────────────────────────────────────
ASSISTANT_NAME=Nova
WAKE_WORD=nova
REQUIRE_WAKE_WORD=1
FOLLOWUP_WINDOW_SEC=22

# macOS (say -v):
NOVA_VOICE=Reed (Español (España))
NOVA_VOICE_RATE=175

# Windows (SAPI — ignorado en macOS/Linux):
# EDGE_VOICE=es-ES-AlvaroNeural

# ── Presupuesto ───────────────────────────────────────────────────────────────
SESSION_BUDGET_USD=0.10
MAX_HISTORY=5

# ── Integraciones ─────────────────────────────────────────────────────────────
GITHUB_TOKEN=tu_token
TELEGRAM_BOT_TOKEN=tu_token
TELEGRAM_CHAT_ID=tu_chat_id
```

### Tabla de proveedores de LLM gratuitos

| Provider | Env var | Tier 1 (rápido) | Tier 3 (razonamiento) | Límite |
|----------|---------|-----------------|----------------------|--------|
| **Groq** | `GROQ_API_KEY` | llama-3.1-8b | llama-3.3-70b | 14,400 req/día |
| **Cerebras** | `CEREBRAS_API_KEY` | llama3.1-8b | llama-3.3-70b | 30 req/min |
| **Mistral** | `MISTRAL_API_KEY` | mistral-small | mistral-large | — |
| **Codestral** | `CODESTRAL_API_KEY` | codestral-latest | codestral-latest | ideal para código |
| **OpenRouter** | `OPENROUTER_API_KEY` | llama-3.1-8b | llama-3.3-70b | varía por modelo |
| **Ollama** | `OLLAMA_BASE_URL` | local | local | sin límite |
| DeepSeek *(desactivado)* | `DEEPSEEK_API_KEY` | v4-flash | v4-pro | **pagado** |

## 🎯 Uso Básico

Activa por voz con "Nova" o escribe en la terminal REPL:

```
nova> abre Safari y ve a youtube.com
nova> qué hora es
nova> pon un timer de 25 minutos
nova> qué ves con la cámara
nova> busca en el cerebro agency-agents
nova> agenda una reunión con Juan mañana a las 15:00
```

### Skills sin API key

```
nova> traduce "hello world" al español
nova> cuánto vale bitcoin ahora
nova> cuál es el tipo de cambio euro a dólar
nova> qué feriados tiene Argentina este año
nova> feriados de Chile en 2026
```

## 🤖 Agentes Especializados

Nova integra 185 agentes especializados ejecutados con proveedores gratuitos:

```
nova> actúa como firmware engineer y diseña tasks FreeRTOS para drone con IMU, GPS y telemetría
nova> consulta al software architect sobre arquitectura de telemetría en tiempo real
nova> como experto en backend, qué patrón uso para la API de sensores
nova> lista agentes disponibles engineering
```

## 📁 Creación y Edición de Proyectos

```
nova> crea un proyecto Python para monitorear CPU y guardar logs en CSV
nova> crea repo de firmware ESP32 para drone en ~/Desktop/drone-fw
nova> abre proyecto ~/Desktop/drone-fw
nova> lee src/main.c
nova> modifica src/main.c para agregar timeout en I2C
nova> estructura del proyecto
nova> dime el contenido de esa carpeta
nova> dime el contenido de la carpeta src
```

## 🎨 Modelado 3D en Blender

```
nova> modela un tornillo hexagonal M6 en Blender
nova> mira lo que tengo en la mano y recréalo en 3D
nova> actúa como blender y crea un engranaje recto de 20 dientes
```

## 🧠 Sistema de Memoria (NovaNeuroMemory)

```
nova> recuerda que prefiero Python sobre JavaScript
nova> qué sabes sobre mis preferencias de programación
```

Flujo interno:
```
texto → embedding qwen3-embedding:4b (2560 dims) → Qdrant local (__DOTNOVA_PATH__/qdrant_db)
query → embedding → cosine similarity → contexto inyectado al LLM
```

## ⌨️ Comandos de Sistema

```bash
/reiniciar     # Recarga módulos en caliente (sin reiniciar Nova)
/reenroll      # Re-enrollar perfil de voz del speaker
/silencio      # Alternar modo silencioso (sin TTS)
/estado        # Ver estado de todos los módulos
/memoria       # Ver memorias guardadas
/ayuda         # Lista completa de comandos
```

## 🖥️ Notas por Plataforma

### macOS
- TTS: voz del sistema vía `say -v` (configurable con `NOVA_VOICE`)
- Audio: `afplay` para reproducción
- Screenshots: `screencapture -x`
- Volumen: osascript
- Portapapeles: `pbcopy`/`pbpaste`

### Windows
- TTS: PowerShell SAPI (`System.Speech.Synthesis.SpeechSynthesizer`) — automático, no requiere instalación extra
- Audio: PowerShell `SoundPlayer` (WAV) — MP3 requiere `playsound`
- Screenshots: `pyautogui` o PowerShell
- Volumen: `pycaw` (instalado automáticamente con `install.py`)
- Portapapeles: `pyperclip` o PowerShell
- **Nota**: el archivo `.bat` para iniciar es `launch_nova.bat` (si existe) o `python main.py` directamente

### Linux
- TTS: `espeak-ng` (requiere `sudo apt install espeak-ng`)
- Audio: `mpg123` o `paplay`
- Screenshots: `gnome-screenshot` o `scrot`
- Volumen: `pactl` / `amixer`
- Portapapeles: `xclip` o `xsel`

## 🧩 Arquitectura

```
src/nova/
├── cli/
│   └── repl.py               # REPL principal + comandos /
├── connectors/
│   ├── nova_blender.py        # Blender MCP socket + auto-evaluación con visión
│   ├── nova_cerebro.py        # Obsidian vault (file-based + REST API)
│   ├── nova_specialist.py     # 185 agentes especializados
│   ├── nova_vision.py         # Visión: Ollama + OpenRouter fallback
│   └── blender_examples/      # Scripts de referencia aprobados
├── core/
│   └── nova_router.py       # Router principal: Ollama→Groq→Cerebras→Mistral→OpenRouter
├── lang/
│   └── novaesp.py             # HUD principal + loop de conversación
├── platform/
│   ├── adapter.py             # Detecta OS y despacha al módulo correcto
│   ├── macos.py               # Implementaciones macOS (say, afplay, osascript...)
│   ├── windows.py             # Implementaciones Windows (SAPI, pycaw, winreg...)
│   └── linux.py               # Implementaciones Linux (espeak-ng, pactl, xclip...)
└── tools/
    ├── nova_skills.py       # 100+ skills: dispatch regex + LLM fallback
    └── nova_neuro_memory.py   # Mem0 + Qdrant + embeddings locales
```

## 📚 Recursos

- [STATUS.md](STATUS.md) — Estado actual del sistema
- [MEMORIA_NEURONAL.md](MEMORIA_NEURONAL.md) — Detalles del sistema de memoria vectorial

---

*Última actualización: 2026-05-06*
