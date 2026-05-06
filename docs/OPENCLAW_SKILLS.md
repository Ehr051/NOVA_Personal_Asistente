# OpenClaw Skills vs Nova Skills

## 🤔 El Problema

OpenClaw tiene **31+ herramientas** (skills) disponibles en ClawHub:
- apple-reminders, blogwatcher, discord, spotify-player, etc.

Pero aparecen como **"Needs Setup"** porque cada herramienta requiere:
1. **API keys** específicas (ej: token de Discord, Spotify, etc.)
2. **Software adicional** instalado (ej: BlueBubbles, Spotify CLI)
3. **Configuración individual** en OpenClaw

## 🔄 Diferencia: OpenClaw vs Nova

| Aspecto | OpenClaw | Nova (NOVA) |
|---------|----------|---------------|
| **Propósito** | Gateway de IA + herramientas | Asistente personal voz/acciones |
| **Skills** | 31+ externas (apis/cli) | Nativas (sistema/archivos/web) |
| **Configuración** | Cada skill requiere setup | Todo integrado en `nova_skills.py` |
| **Dependencias** | APIs externas, tokens, clis | pyautogui, sqlite, requests |

## ✅ Qué Tiene Nova Nativo (Sin OpenClaw)

Nova tiene **skills propias** en `nova_skills.py`:

### Sistema
- ✅ Abrir/cerrar apps (`open_app`, `close_app`)
- ✅ Ejecutar comandos (`run_command`)
- ✅ Screenshot, volumen, brightness
- ✅ Listar procesos, kill process

### Archivos
- ✅ Crear/editar/leer archivos
- ✅ Buscar archivos
- ✅ Abrir en VS Code, carpeta

### Web
- ✅ Buscar en DuckDuckGo
- ✅ Abrir URLs

### Memoria
- ✅ Recordar/recall/olvidar facts
- ✅ Diario de voz

### n8n (si configurado)
- ✅ Gastos
- ✅ Calendario
- ✅ Eventos
- ✅ Crear archivos

## 🔧 Opciones Para Usar Las Skills de OpenClaw

### Opción 1: Configurar OpenClaw (Recomendado si ya lo usas)

Cada skill requiere su propio setup. Ejemplo para **spotify-player**:

```bash
# 1. Instalar spotify_player CLI
brew install spotify-player

# 2. Configurar credenciales de Spotify Developer
#    https://developer.spotify.com/dashboard

# 3. En OpenClaw, habilitar la skill e ingresar credenciales
```

Ejemplo para **discord**:
```bash
# 1. Crear bot en Discord Developer Portal
# 2. Obtener token del bot
# 3. Configurar en OpenClaw
```

### Opción 2: Usar Alternativas Nativas de Nova

Muchas funciones de OpenClaw skills las puede hacer Nova directamente:

| OpenClaw Skill | Alternativa Nova |
|----------------|------------------|
| apple-reminders | Comando: `" Nova, ejecuta 'osascript ...'"` |
| spotify-player | `" Nova, abre Spotify"` + AppleScript |
| discord | `" Nova, abre Discord"` (app nativa) |
| notione | `" Nova, abre Notion"` |
| slack | `" Nova, abre Slack"` |
| screenshot | `" Nova, captura pantalla"` (skill nativo) |
| xurl (Twitter) | `" Nova, abre Chrome en twitter.com"` |

### Opción 3: Integrar OpenClaw Skills en Nova

Modificar `nova_skills.py` para llamar a OpenClaw skills vía API:

```python
def skill_spotify(command: str) -> str:
    """Controla Spotify via OpenClaw skill."""
    # Llamar a OpenClaw /skills/spotify-player/execute
    # Requiere que la skill esté configurada en OpenClaw
    pass
```

### Opción 4: MCP (Model Context Protocol)

Si OpenClaw soporta MCP, podría exponer skills como herramientas MCP:

```python
# Nova usaría los tools MCP de OpenClaw
"""
Ejecuta la herramienta spotify-player con acción "play"
"""
```

## 🛠️ Diagnóstico Rápido

```bash
# Verificar OpenClaw
python3 diagnostico_openclaw.py

# Verificar Nova skills
python3 -c "import nova_skills as s; print('Skills disponibles:', len(s.SKILL_PATTERNS))"
```

## 📊 Estado Actual

Para saber qué está disponible **ahora**:

| Funcionalidad | Estado | Cómo usar |
|---------------|--------|-----------|
| Abrir apps | ✅ Nativo | `" Nova, abre Safari"` |
| Buscar web | ✅ Nativo | `" Nova, busca Python"` |
| Screenshot | ✅ Nativo | `" Nova, captura pantalla"` |
| Spotify | ⚠️ Limitado | `" Nova, abre Spotify"` (solo app) |
| Discord | ⚠️ Limitado | `" Nova, abre Discord"` (solo app) |
| Reminders | ⚠️ Limitado | Vía AppleScript |
| Notion | ⚠️ Limitado | `" Nova, abre Notion"` |
| iMessage | ❌ Requiere BlueBubbles | No disponible nativamente |
| Sonos | ❌ Requiere CLI | No disponible nativamente |

## 🎯 Recomendación

Si necesitas **control profundo** de Spotify, Discord, etc.:

1. **Configura las skills en OpenClaw** siguiendo su documentación
2. O **crea wrappers en `nova_skills.py`** que usen AppleScript para apps de macOS

Ejemplo AppleScript para Spotify:
```python
def spotify_play():
    subprocess.run([
        "osascript", "-e",
        'tell application "Spotify" to play'
    ])
```

## 🔗 Recursos OpenClaw

- Documentación OpenClaw: (busca en tu instalación local)
- ClawHub: Lista de skills disponibles
- Configuración de cada skill: Generalmente requiere `~/.config/openclaw/skills/`
