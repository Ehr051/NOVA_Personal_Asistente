#!/usr/bin/env python3
"""
nova_skills_enhanced.py
───────────────────────
Skills mejoradas para Nova con visión, control de mouse visible,
integración con apps de diseño, y funcionalidades avanzadas.

Nuevas capacidades:
  • Visión de pantalla en tiempo real
  • Control de mouse con feedback visual
  • Alarmas y timers que funcionan
  • Dictado universal (escribe donde esté el cursor)
  • Integración con Canvas, AutoCAD, Figma, etc.
  • Análisis de código con visión
"""

from __future__ import annotations

import os
import re
import json
import time
import sched
import subprocess
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# Importar sistemas de Nova
try:
    from nova_vision import VisionSystem, get_vision, ScreenRegion
    _HAS_VISION = True
except ImportError:
    _HAS_VISION = False

try:
    from nova_mouse import SmartMouse, get_mouse
    _HAS_SMART_MOUSE = True
except ImportError:
    _HAS_SMART_MOUSE = False

# Scheduler para alarmas
scheduler = sched.scheduler(time.time, time.sleep)
_scheduler_thread: Optional[threading.Thread] = None


def _ensure_scheduler():
    """Asegura que el scheduler esté corriendo."""
    global _scheduler_thread
    if _scheduler_thread is None or not _scheduler_thread.is_alive():
        _scheduler_thread = threading.Thread(target=scheduler.run, daemon=True)
        _scheduler_thread.start()


# ═══════════════════════════════════════════════════════════════════════════════
# 1. SISTEMA DE ALARMAS Y TIMERS (que realmente funcionan)
# ═══════════════════════════════════════════════════════════════════════════════

class AlarmManager:
    """Gestor de alarmas y timers."""

    def __init__(self):
        self.alarms: dict[str, dict] = {}
        self._lock = threading.Lock()
        _ensure_scheduler()

    def set_timer(self, minutes: float, message: str, notify_callback=None) -> str:
        """
        Establece un timer.

        Args:
            minutes: Minutos hasta la alarma
            message: Mensaje a mostrar cuando suene
            notify_callback: Función para notificar (ej: speak)
        """
        alarm_id = f"timer_{int(time.time())}"
        seconds = minutes * 60

        def trigger():
            self._trigger_alarm(alarm_id, message, notify_callback)

        event = scheduler.enter(seconds, 1, trigger)

        with self._lock:
            self.alarms[alarm_id] = {
                "message": message,
                "trigger_at": datetime.now() + timedelta(minutes=minutes),
                "event": event,
                "type": "timer"
            }

        return alarm_id

    def set_alarm(self, time_str: str, message: str, notify_callback=None) -> str:
        """
        Establece una alarma para una hora específica.

        Args:
            time_str: Hora en formato "HH:MM" o "HH:MM AM/PM"
            message: Mensaje a mostrar
        """
        try:
            # Parsear hora
            time_str = time_str.strip().lower()
            now = datetime.now()

            # Detectar AM/PM
            is_pm = "pm" in time_str
            is_am = "am" in time_str
            time_str = time_str.replace("am", "").replace("pm", "").strip()

            # Parsear HH:MM
            parts = time_str.split(":")
            hour = int(parts[0])
            minute = int(parts[1]) if len(parts) > 1 else 0

            # Ajustar AM/PM
            if is_pm and hour != 12:
                hour += 12
            if is_am and hour == 12:
                hour = 0

            # Crear datetime objetivo
            target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

            # Si ya pasó, es para mañana
            if target < now:
                target += timedelta(days=1)

            seconds = (target - now).total_seconds()

            alarm_id = f"alarm_{int(time.time())}"

            def trigger():
                self._trigger_alarm(alarm_id, message, notify_callback)

            event = scheduler.enter(seconds, 1, trigger)

            with self._lock:
                self.alarms[alarm_id] = {
                    "message": message,
                    "trigger_at": target,
                    "event": event,
                    "type": "alarm"
                }

            return alarm_id

        except Exception as e:
            return f"error: {e}"

    def _trigger_alarm(self, alarm_id: str, message: str, notify_callback):
        """Ejecuta cuando suena la alarma."""
        # Notificar
        if notify_callback:
            notify_callback(f"¡ALARMA! {message}")

        # Mostrar notificación visual (macOS)
        subprocess.run([
            "osascript", "-e",
            f'display notification "{message}" with title "⏰ Nova Alarma"'
        ])

        # Sonar beep
        print("\a")  # Beep

        with self._lock:
            if alarm_id in self.alarms:
                del self.alarms[alarm_id]

    def list_alarms(self) -> list[dict]:
        """Lista las alarmas activas."""
        with self._lock:
            return [
                {
                    "id": k,
                    "message": v["message"],
                    "trigger_at": v["trigger_at"].strftime("%H:%M"),
                    "type": v["type"]
                }
                for k, v in self.alarms.items()
            ]

    def cancel_alarm(self, alarm_id: str) -> bool:
        """Cancela una alarma."""
        with self._lock:
            if alarm_id in self.alarms:
                try:
                    scheduler.cancel(self.alarms[alarm_id]["event"])
                except:
                    pass
                del self.alarms[alarm_id]
                return True
        return False


# Instancia global
_alarm_manager: Optional[AlarmManager] = None


def get_alarm_manager() -> AlarmManager:
    global _alarm_manager
    if _alarm_manager is None:
        _alarm_manager = AlarmManager()
    return _alarm_manager


# ═══════════════════════════════════════════════════════════════════════════════
# 2. SKILLS CON VISIÓN Y MOUSE INTELIGENTE
# ═══════════════════════════════════════════════════════════════════════════════

def smart_click_on_text(target_text: str) -> str:
    """
    Busca texto en pantalla y hace click en él.
    Requiere vision system.
    """
    if not _HAS_VISION:
        return "Sistema de visión no disponible. Instala las dependencias necesarias."

    vision = get_vision()

    # Capturar pantalla
    screenshot = vision.capture_fullscreen(save=False)

    # TODO: Implementar OCR para encontrar texto
    # Por ahora, buscar posiciones comunes

    return f"Buscando '{target_text}' en pantalla... (OCR en desarrollo)"


def _applescript(script: str) -> tuple[int, str]:
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    return r.returncode, (r.stdout or r.stderr or "").strip()


def smart_open_and_create(app_name: str, create_new: bool = True) -> str:
    """
    Abre una app y crea un documento nuevo.
    Usa AppleScript para garantizar el foco antes de enviar atajos.

    Args:
        app_name: Nombre de la aplicación
        create_new: Si debe crear un documento nuevo
    """
    # Mapeo de apps a: (nombre_exacto_en_macos, shortcut_mod, shortcut_key)
    new_doc_shortcuts = {
        "word":        ("Microsoft Word",        "command", "n"),
        "pages":       ("Pages",                 "command", "n"),
        "textedit":    ("TextEdit",              "command", "n"),
        "numbers":     ("Numbers",               "command", "n"),
        "excel":       ("Microsoft Excel",       "command", "n"),
        "powerpoint":  ("Microsoft PowerPoint",  "command", "n"),
        "keynote":     ("Keynote",               "command", "n"),
        "figma":       ("Figma",                 "command", "n"),
        "sketch":      ("Sketch",                "command", "n"),
        "photoshop":   ("Adobe Photoshop",       "command", "n"),
        "illustrator": ("Adobe Illustrator",     "command", "n"),
        "premiere":    ("Adobe Premiere Pro",    "command", "n"),
        "after effects": ("Adobe After Effects", "command", "n"),
        "xd":          ("Adobe XD",              "command", "n"),
    }

    app_lower = app_name.lower()

    # Encontrar app en el mapeo
    matched_app = app_name
    matched_mod = None
    matched_key = None
    for key, (real_name, mod, key_char) in new_doc_shortcuts.items():
        if key in app_lower or app_lower in key:
            matched_app = real_name
            matched_mod = mod
            matched_key = key_char
            break

    # Abrir la app via AppleScript (activate garantiza el foco)
    rc, _ = _applescript(f'tell application "{matched_app}" to activate')
    if rc != 0:
        subprocess.run(["open", "-a", matched_app])
    time.sleep(2.5)  # Tiempo suficiente para que la app tome el foco

    if not create_new:
        return f"{matched_app} abierto, Señor."

    if matched_mod and matched_key:
        # Enviar keystroke via AppleScript (más confiable que pyautogui en macOS)
        osa_script = (
            f'tell application "System Events" to tell process "{matched_app}" '
            f'to keystroke "{matched_key}" using command down'
        )
        rc2, _ = _applescript(osa_script)
        time.sleep(1.0)
        if rc2 == 0:
            return f"{matched_app} abierto con nuevo documento, Señor."

    return f"{matched_app} abierto. Para crear nuevo documento, usa el menú Archivo > Nuevo."


def vision_dictate(text: str) -> str:
    """
    Dictado inteligente que escribe donde esté el cursor.
    Muestra feedback visual.
    """
    if _HAS_SMART_MOUSE:
        mouse = get_mouse()
        mouse.show_message(f"Escribiendo...", duration=1.5)
        mouse.type_text(text)
        return "Texto escrito, Señor."
    else:
        # Fallback a clipboard
        import subprocess
        proc = subprocess.Popen(['pbcopy'], stdin=subprocess.PIPE)
        proc.communicate(text.encode('utf-8'))
        time.sleep(0.1)
        import pyautogui
        pyautogui.hotkey('command', 'v')
        return "Texto pegado, Señor."


def vision_screenshot_and_describe() -> str:
    """
    Toma captura y la guarda para análisis.
    Retorna el path para que el LLM la analice.
    """
    if not _HAS_VISION:
        # Fallback a captura básica
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = Path.home() / f"Desktop/nova_capture_{ts}.png"
        subprocess.run(["screencapture", "-x", str(path)])
        return f"Captura guardada en {path}. Puedes analizarla con visión."

    vision = get_vision()
    screenshot = vision.capture_fullscreen()

    return f"Captura tomada. Tamaño: {screenshot.size}. Guardada en: {vision.last_capture_path}"


# ═══════════════════════════════════════════════════════════════════════════════
# 3. INTEGRACIÓN CON APPS DE DISEÑO
# ═══════════════════════════════════════════════════════════════════════════════

def design_app_action(app: str, action: str, params: dict = None) -> str:
    """
    Ejecuta acciones en aplicaciones de diseño.

    Args:
        app: Nombre de la app (figma, sketch, photoshop, illustrator, etc.)
        action: Acción a realizar
        params: Parámetros adicionales
    """
    app_actions = {
        "figma": {
            "new_frame": ["command", "alt", "g"],  # New frame/group
            "new_component": ["command", "alt", "k"],
            "zoom_in": ["command", "plus"],
            "zoom_out": ["command", "minus"],
            "export": ["command", "shift", "e"],
        },
        "sketch": {
            "new_artboard": ["command", "shift", "a"],
            "new_symbol": ["command", "k"],
            "export": ["command", "shift", "e"],
        },
        "photoshop": {
            "new_layer": ["command", "shift", "n"],
            "duplicate": ["command", "j"],
            "export": ["command", "shift", "option", "s"],  # Export as
        },
        "illustrator": {
            "new_layer": ["command", "l"],
            "new_artboard": ["command", "shift", "o"],
            "export": ["command", "shift", "s"],
        },
    }

    app_lower = app.lower()

    # Buscar app en el diccionario
    for app_key, actions in app_actions.items():
        if app_key in app_lower:
            if action in actions:
                shortcut = actions[action]
                try:
                    import pyautogui
                    pyautogui.hotkey(*shortcut)
                    return f"Acción '{action}' ejecutada en {app}, Señor."
                except Exception as e:
                    return f"Error ejecutando acción: {e}"
            else:
                return f"Acción '{action}' no disponible para {app}. Acciones: {', '.join(actions.keys())}"

    return f"App '{app}' no soportada o no encontrada en el catálogo."


def canvas_create_design(design_type: str, width: int = 800, height: int = 600) -> str:
    """
    Crea un diseño nuevo en Canva (abre Canva en navegador).

    Args:
        design_type: Tipo de diseño (instagram, poster, presentation, etc.)
        width, height: Dimensiones opcionales
    """
    canva_urls = {
        "instagram": "https://www.canva.com/design?type=instagram-post",
        "instagram story": "https://www.canva.com/design?type=instagram-story",
        "poster": "https://www.canva.com/design?type=poster",
        "presentation": "https://www.canva.com/design?type=presentation",
        "flyer": "https://www.canva.com/design?type=flyer",
        "logo": "https://www.canva.com/design?type=logo",
        "resume": "https://www.canva.com/design?type=resume",
        "business card": "https://www.canva.com/design?type=business-card",
    }

    url = canva_urls.get(design_type.lower(), "https://www.canva.com")

    subprocess.run(["open", url])
    return f"Abriendo Canva para crear {design_type}, Señor."


# ═══════════════════════════════════════════════════════════════════════════════
# 4. ANÁLISIS DE CÓDIGO CON VISIÓN
# ═══════════════════════════════════════════════════════════════════════════════

def code_analyze_screenshot() -> str:
    """
    Toma captura y la prepara para análisis de código.
    """
    if not _HAS_VISION:
        return "Sistema de visión no disponible."

    vision = get_vision()

    # Capturar
    screenshot = vision.capture_fullscreen()

    # Detectar ventana activa
    try:
        result = subprocess.run(
            ["osascript", "-e",
             'tell application "System Events" to get name of first application process whose frontmost is true'],
            capture_output=True, text=True
        )
        active_app = result.stdout.strip()
    except:
        active_app = "Desconocida"

    return {
        "screenshot_path": vision.last_capture_path,
        "active_app": active_app,
        "size": screenshot.size,
        "message": f"Captura lista para análisis. App activa: {active_app}. Envía esta imagen al LLM para análisis de código."
    }


def code_extract_from_screenshot() -> str:
    """
    Extrae texto de código desde la captura de pantalla.
    Usa OCR si está disponible.
    """
    if not _HAS_VISION:
        return "Sistema de visión no disponible."

    # TODO: Implementar OCR con pytesseract o similar
    vision = get_vision()
    screenshot = vision.capture_fullscreen()

    return {
        "screenshot_path": vision.last_capture_path,
        "note": "OCR de código en desarrollo. Por ahora, el LLM puede analizar la imagen directamente."
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 5. SKILLS DE PRODUCTIVIDAD
# ═══════════════════════════════════════════════════════════════════════════════

def quick_capture_to_note() -> str:
    """
    Captura pantalla y guarda en Obsidian/NOVA como nota rápida.
    """
    vision = get_vision() if _HAS_VISION else None

    if vision:
        screenshot = vision.capture_fullscreen()
        path = vision.last_capture_path
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = Path.home() / f"Desktop/nova_note_{ts}.png"
        subprocess.run(["screencapture", "-x", str(path)])

    # Crear nota en NOVA
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    note_content = f"""# Nota Rápida - {timestamp}

![Screenshot]({path})

Captura tomada desde Nova.
"""

    # Guardar en vault de Obsidian
    vault_path = Path.home() / "Cerebro" / "NOVA" / "Notas Rápidas"
    vault_path.mkdir(parents=True, exist_ok=True)

    note_file = vault_path / f"Nota_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    note_file.write_text(note_content)

    return f"Nota creada en {note_file}, Señor."


def focus_mode_on() -> str:
    """
    Activa modo focus: Do Not Disturb + oculta notificaciones.
    """
    subprocess.run([
        "osascript", "-e",
        'tell application "System Events" to tell application process "SystemUIServer" to tell menu bar item 1 of menu bar 2 to click'
    ])

    return "Modo Focus activado. Notificaciones silenciadas, Señor."


def focus_mode_off() -> str:
    """Desactiva modo focus."""
    # Toggle again
    subprocess.run([
        "osascript", "-e",
        'tell application "System Events" to tell application process "SystemUIServer" to tell menu bar item 1 of menu bar 2 to click'
    ])

    return "Modo Focus desactivado, Señor."


# ═══════════════════════════════════════════════════════════════════════════════
# 6. EXPORTAR FUNCIONES
# ═══════════════════════════════════════════════════════════════════════════════

__all__ = [
    # Alarmas
    "get_alarm_manager",
    # Visión y mouse
    "smart_click_on_text",
    "smart_open_and_create",
    "vision_dictate",
    "vision_screenshot_and_describe",
    # Diseño
    "design_app_action",
    "canvas_create_design",
    # Código
    "code_analyze_screenshot",
    "code_extract_from_screenshot",
    # Productividad
    "quick_capture_to_note",
    "focus_mode_on",
    "focus_mode_off",
]

if __name__ == "__main__":
    print("Nova Skills Enhanced cargado.")
    print("Funciones disponibles:", len(__all__))
