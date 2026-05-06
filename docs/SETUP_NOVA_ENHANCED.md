# Nova Enhanced - Setup e Instalación

Sistema completo de visión, control de mouse visible, alarmas funcionales e integración con apps de diseño.

> Estado 2026-05-06: guía vigente para capacidades enhanced, pero las rutas actuales viven bajo `src/nova/...`. Las referencias antiguas a archivos en la raíz se conservan solo como contexto histórico.

## 🎯 Qué incluye

| Módulo | Función |
|--------|---------|
| `src/nova/tools/nova_vision.py` | Captura y análisis de pantalla |
| `src/nova/tools/nova_mouse.py` | Control de mouse con **cursor celeste eléctrico** propio |
| `src/nova/tools/nova_skills_enhanced.py` | Alarmas, timers, dictado, integración diseño |
| `src/nova/connectors/nova_integracion.py` | Conexión con el sistema existente |

---

## 📦 Instalación

### 1. Instalar dependencias

```bash
cd /Users/mac/Desktop/NOVA_Personal_Asistente

# Dependencias de visión
pip3 install pillow numpy

# Para OCR (opcional, para extraer texto)
pip3 install pytesseract

# OpenCV para template matching (opcional)
pip3 install opencv-python
```

### 2. Permisos de macOS

Nova necesita permisos para:
- **Accesibilidad** → Controlar el mouse/teclado
- **Grabación de pantalla** → Ver la pantalla
- **Automatización** → Controlar apps

```bash
# Abrir preferencias de sistema
open "x-apple.systempreferences:com.apple.preference.security"
```

Ve a:
1. **Seguridad y Privacidad → Privacidad → Accesibilidad**
   - Agrega Terminal y Python
2. **Seguridad y Privacidad → Privacidad → Grabación de pantalla**
   - Agrega Terminal y Python

---

## 🚀 Uso

### Cursor de Nova - Celeste Eléctrico

Cuando Nova mueve el mouse, verás:
- 🔷 **Cursor cyan brillante** (#00F5FF) - El cursor de Nova
- ⬜ **Tu cursor blanco** - Tu cursor normal
- ✨ **Trail degradado** - Rastro de movimiento
- 💬 **Mensajes en pantalla** - Qué está haciendo

### Comandos de voz nuevos

| Dices | Nova hace |
|-------|-----------|
| "Nova, timer 5 minutos café" | Alarma en 5 minutos |
| "Nova, alarma 14:30 reunión" | Alarma a las 2:30 PM |
| "Nova, mueve el mouse al centro" | Cursor va al centro |
| "Nova, haz click" | Click con efecto visual |
| "Nova, dicta 'hola mundo'" | Escribe donde esté el cursor |
| "Nova, qué ves en pantalla" | Captura y analiza |
| "Nova, en Figma crea un frame" | Ejecuta shortcut Cmd+Opt+G |
| "Nova, abre Word y crea documento" | Abre Word + Cmd+N |

---

## 🎨 Apps de Diseño Soportadas

| App | Acciones disponibles |
|-----|---------------------|
| **Figma** | new_frame, new_component, zoom_in, zoom_out, export |
| **Sketch** | new_artboard, new_symbol, export |
| **Photoshop** | new_layer, duplicate, export |
| **Illustrator** | new_layer, new_artboard, export |

---

## 🔧 Integración en `src/nova/tools/nova_skills.py`

Para usar estas skills, agrega o verifica la integración en `src/nova/tools/nova_skills.py`:

```python
# Importar skills mejoradas
try:
    from nova_integracion import (
        skill_set_timer,
        skill_set_alarm,
        skill_see_screen,
        skill_move_mouse,
        skill_click,
        ENHANCED_SKILLS,
    )
    # Agregar al dispatcher
    SKILL_PATTERNS.extend(ENHANCED_SKILLS)
    print("  [Skills] Módulos mejorados cargados")
except ImportError:
    pass
```

---

## 🐛 Troubleshooting

### "No veo el cursor de Nova"
- Verifica que tkinter esté instalado: `python3 -c "import tkinter"`
- Tkinter viene con Python en macOS, pero si no:
  ```bash
  brew install python-tk
  ```

### "El mouse no se mueve"
- Ve a Preferencias del Sistema → Seguridad → Accesibilidad
- Agrega Terminal (o tu app de Python)

### "No puede ver la pantalla"
- Ve a Preferencias del Sistema → Seguridad → Grabación de pantalla
- Agrega Terminal/Python

### "Las alarmas no suenan"
- El scheduler corre en un hilo separado
- Asegúrate de que el script principal no termine
- Las alarmas usan notificaciones de macOS (`display notification`)

---

## 📁 Estructura de archivos

```
NOVA_Personal_Asistente/
├── src/nova/tools/nova_vision.py              # Sistema de visión
├── src/nova/tools/nova_mouse.py               # Mouse con cursor celeste
├── src/nova/tools/nova_skills_enhanced.py     # Skills avanzadas
├── src/nova/connectors/nova_integracion.py    # Integración
├── src/nova/tools/nova_skills.py              # Skills existentes
├── SETUP_NOVA_ENHANCED.md      # Este archivo
└── Cerebro/                    # Memoria en Obsidian
    └── Nova_Screenshots/       # Capturas de pantalla
```

---

## 💡 Ejemplos de uso

### Ejemplo 1: Workflow de diseño
```
Usuario: "Nova, abre Figma"
Nova: Abre Figma...

Usuario: "Nova, en Figma crea un frame nuevo"
Nova: Presiona Cmd+Alt+G

Usuario: "Nova, qué ves en pantalla"
Nova: Toma captura, la guarda en ~/Desktop/Nova_Screenshots/
```

### Ejemplo 2: Pomodoro
```
Usuario: "Nova, timer 25 minutos trabajo"
Nova: Timer establecido
...
[25 minutos después]
Nova: ¡ALARMA! trabajo
```

### Ejemplo 3: Dictado universal
```
Usuario: "Nova, dicta 'Reunión con el equipo mañana a las 10'"
Nova: Escribe ese texto donde esté el cursor
(Cursor de Nova aparece, escribe, mensaje de confirmación)
```

---

## 🔮 Próximas mejoras

- [ ] OCR para extraer texto de la pantalla
- [ ] Reconocimiento de elementos UI (botones, campos)
- [ ] Integración con más apps (Blender, AutoCAD, etc.)
- [ ] Gestos del mouse (drag, swipe)
- [ ] Modo "manos libres" completo

---

## 📝 Notas

- El cursor de Nova es **independiente** de tu cursor
- Nova puede mover el mouse mientras tú también lo usas
- El cursor celeste aparece solo cuando Nova toma control
- Se desvanece automáticamente después de la acción
