#!/usr/bin/env python3
"""
nova_integracion.py
───────────────────
Integración de nuevas capacidades (visión, mouse inteligente, skills avanzadas)
en el sistema principal de Nova.

Este archivo conecta:
  • nova_vision.py    → Análisis de pantalla
  • nova_mouse.py     → Control de mouse con cursor visual
  • nova_skills_enhanced.py → Skills avanzadas

Con nova_skills.py existente.
"""

from __future__ import annotations

import os
import sys
import time
import subprocess
import threading
from typing import Optional

# Intentar importar los nuevos módulos
try:
    from nova_vision import VisionSystem, get_vision
    from nova_mouse import get_mouse          # SmartMouse removido — no existe en nova_mouse
    from nova_skills_enhanced import (
        get_alarm_manager,
        smart_click_on_text,
        smart_open_and_create,
        vision_dictate,
        vision_screenshot_and_describe,
        design_app_action,
        canvas_create_design,
        quick_capture_to_note,
        focus_mode_on,
        focus_mode_off,
    )
    _HAS_ENHANCED = True
except ImportError as e:
    print(f"[Integración] Módulos mejorados no disponibles: {e}")
    _HAS_ENHANCED = False


class NovaEnhanced:
    """
    Wrapper que provee todas las capacidades mejoradas de Nova.
    Se integra fácilmente con nova_skills.py existente.
    """

    def __init__(self):
        self.vision: Optional[VisionSystem] = None
        self.mouse: Optional[SmartMouse] = None
        self.alarms = None
        self._vision_failed = False
        self._mouse_failed = False
        self._alarms_failed = False

    def _init_with_timeout(self, factory, label: str, timeout: float = 2.5):
        """Inicializa un módulo en hilo daemon y evita bloquear el proceso principal."""
        box = {"value": None, "error": None}

        def _runner():
            try:
                box["value"] = factory()
            except Exception as e:
                box["error"] = e

        t = threading.Thread(target=_runner, daemon=True)
        t.start()
        t.join(timeout)

        if t.is_alive():
            print(f"[Integración] Timeout iniciando {label}; se desactiva para evitar bloqueo.")
            return None
        if box["error"] is not None:
            print(f"[Integración] No se pudo iniciar {label}: {box['error']}")
            return None
        return box["value"]

    def _ensure_vision(self) -> bool:
        if self.vision is None and _HAS_ENHANCED and not self._vision_failed:
            self.vision = self._init_with_timeout(get_vision, "visión", timeout=2.0)
            if self.vision is None:
                self._vision_failed = True
        return self.vision is not None

    def _ensure_mouse(self) -> bool:
        if self.mouse is None and _HAS_ENHANCED and not self._mouse_failed:
            self.mouse = self._init_with_timeout(get_mouse, "mouse inteligente", timeout=2.0)
            if self.mouse is None:
                self._mouse_failed = True
        return self.mouse is not None

    def _ensure_alarms(self) -> bool:
        if self.alarms is None and _HAS_ENHANCED and not self._alarms_failed:
            try:
                self.alarms = get_alarm_manager()
            except Exception as e:
                print(f"[Integración] No se pudo iniciar alarmas: {e}")
                self.alarms = None
                self._alarms_failed = True
        return self.alarms is not None

    # ═══════════════════════════════════════════════════════════════════════════
    # 1. VISIÓN
    # ═══════════════════════════════════════════════════════════════════════════

    def see_screen(self, question: str = "¿Qué ves?") -> dict:
        """
        Captura pantalla y la prepara para análisis.

        Returns:
            Diccionario con path de imagen y contexto.
        """
        if not self._ensure_vision():
            # Fallback
            ts = time.strftime("%Y%m%d_%H%M%S")
            path = f"~/Desktop/nova_capture_{ts}.png"
            subprocess.run(["screencapture", "-x", os.path.expanduser(path)])
            return {
                "screenshot_path": os.path.expanduser(path),
                "message": "Captura tomada (modo básico)"
            }

        # Usar visión avanzada
        info = self.vision.analyze_for_action(question)
        return info

    def capture_region(self, x: int, y: int, width: int, height: int) -> str:
        """Captura una región específica."""
        if self._ensure_vision():
            img = self.vision.capture_region(x, y, width, height)
            return self.vision.last_capture_path or "Región capturada"
        return "Visión no disponible"

    # ═══════════════════════════════════════════════════════════════════════════
    # 2. MOUSE INTELIGENTE
    # ═══════════════════════════════════════════════════════════════════════════

    def move_mouse_smooth(self, x: int, y: int, duration: float = 1.0):
        """Mueve el mouse suavemente a las coordenadas."""
        if self._ensure_mouse():
            self.mouse.move_smooth(x, y, duration)
            return f"Mouse movido a {x}, {y}"
        return "Mouse inteligente no disponible"

    def click_with_feedback(self):
        """Hace click mostrando el cursor de Nova."""
        if self._ensure_mouse():
            self.mouse.click()
            return "Click realizado"
        return "Mouse no disponible"

    def smart_dictate(self, text: str) -> str:
        """Dictado que escribe donde esté el cursor."""
        if _HAS_ENHANCED:
            return vision_dictate(text)
        return "Dictado no disponible"

    # ═══════════════════════════════════════════════════════════════════════════
    # 3. ALARMAS - CORREGIDO: método unificado
    # ═══════════════════════════════════════════════════════════════════════════

    def set_timer(self, minutes: float, message: str, notify_callback=None) -> str:
        """Establece un timer (alias para compatibilidad)."""
        if self._ensure_alarms():
            alarm_id = self.alarms.set_timer(minutes, message, notify_callback)
            return f"Timer establecido para {minutes} minutos: {message}"
        return "Sistema de alarmas no disponible"

    def set_alarm(self, time_str: str, message: str, notify_callback=None) -> str:
        """Establece alarma para hora específica."""
        if self._ensure_alarms():
            alarm_id = self.alarms.set_alarm(time_str, message, notify_callback)
            if isinstance(alarm_id, str) and alarm_id.startswith("error"):
                return f"Error: {alarm_id}"
            return f"Alarma establecida para las {time_str}: {message}"
        return "Sistema de alarmas no disponible"

    # ALIAS para compatibilidad con nova_skills.py
    set_alarm_clock = set_alarm

    def list_alarms(self) -> str:
        """Lista alarmas activas."""
        if self._ensure_alarms():
            alarms = self.alarms.list_alarms()
            if not alarms:
                return "No hay alarmas activas."
            lines = ["Alarmas activas:"]
            for a in alarms:
                lines.append(f"  • {a['type']} {a['trigger_at']}: {a['message']}")
            return "\n".join(lines)
        return "Sistema de alarmas no disponible"

    # ═══════════════════════════════════════════════════════════════════════════
    # 4. APPS Y DISEÑO - CORREGIDO: método design_action agregado
    # ═══════════════════════════════════════════════════════════════════════════

    def open_and_create(self, app_name: str) -> str:
        """Abre app y crea documento nuevo."""
        if _HAS_ENHANCED:
            return smart_open_and_create(app_name, create_new=True)
        return smart_open_and_create(app_name) if 'smart_open_and_create' in globals() else "No disponible"

    # CORREGIDO: Este método faltaba y causaba error
    def design_action(self, app: str, action: str) -> str:
        """Ejecuta acción en app de diseño."""
        if _HAS_ENHANCED:
            return design_app_action(app, action)
        return "Acciones de diseño no disponibles"

    def quick_note(self) -> str:
        """Captura pantalla y guarda como nota."""
        if _HAS_ENHANCED:
            return quick_capture_to_note()
        return "Nota rápida no disponible"

    # ═══════════════════════════════════════════════════════════════════════════
    # 5. HELPERS
    # ═══════════════════════════════════════════════════════════════════════════

    def is_available(self, feature: str) -> bool:
        """Verifica si una feature está disponible."""
        features = {
            "vision": _HAS_ENHANCED and not self._vision_failed,
            "mouse": _HAS_ENHANCED and not self._mouse_failed,
            "alarms": _HAS_ENHANCED and not self._alarms_failed,
            "enhanced": _HAS_ENHANCED,
        }
        return features.get(feature, False)


# Instancia global
_nova_enhanced: Optional[NovaEnhanced] = None


def get_nova_enhanced() -> NovaEnhanced:
    """Retorna la instancia global de NovaEnhanced."""
    global _nova_enhanced
    if _nova_enhanced is None:
        _nova_enhanced = NovaEnhanced()
    return _nova_enhanced


# ═══════════════════════════════════════════════════════════════════════════════
# Funciones de conveniencia para integrar en nova_skills.py
# ═══════════════════════════════════════════════════════════════════════════════

def skill_set_timer(text: str) -> str:
    """
    Skill: Establece un timer.
    Formatos:
      - "timer 5 minutos café"
      - "recordatorio en 10 minutos"
    """
    import re
    match = re.search(r'(\d+(?:\.\d+)?)\s*(minutos?|mins?|m|segundos?|segs?|s)', text, re.I)
    if not match:
        return "No entendí el tiempo. Usa: 'timer 5 minutos café'"

    amount = float(match.group(1))
    unit   = match.group(2).lower()
    secs   = int(amount * 60) if unit.startswith("m") else int(amount)

    message = re.sub(r'^.*?(?:minutos?|mins?|segundos?|segs?)\s*', '', text, flags=re.I).strip()
    if not message:
        message = "Timer"

    # Intentar enhanced, fallback a set_timer básico
    nova = get_nova_enhanced()
    result = nova.set_timer(amount if unit.startswith("m") else amount / 60, message)
    if "no disponible" in result.lower():
        import nova_skills as _js
        return _js.set_timer(secs, message)
    return result


def skill_set_alarm(text: str) -> str:
    """
    Skill: Establece alarma para hora específica.
    Formatos:
      - "alarma 14:30 reunión"
      - "despertador 7:00 AM"
    """
    nova = get_nova_enhanced()

    import re
    match = re.search(r'(\d{1,2}):(\d{2})\s*(am|pm)?', text, re.I)
    if not match:
        return "No entendí la hora. Usa: 'alarma 14:30' o 'despertador 7:00 AM'"

    hour = match.group(1)
    minute = match.group(2)
    ampm = match.group(3) or ""
    time_str = f"{hour}:{minute} {ampm}".strip()

    message = re.sub(r'^.*?\d{1,2}:\d{2}\s*(?:am|pm)?\s*', '', text, flags=re.I).strip()
    if not message:
        message = "Alarma"

    return nova.set_alarm(time_str, message)


def skill_see_screen(question: str = "") -> str:
    """Skill: Nova ve y analiza la pantalla actual (análisis inmediato, sin dos pasos)."""
    # Importación diferida para evitar ciclo: nova_skills → nova_integracion → nova_skills
    import nova_skills as _js
    prompt = question.strip() if question.strip() else "Describe detalladamente qué ves en esta pantalla: apps abiertas, contenido visible, colores, texto principal."
    img_path = _js._take_screenshot_path()
    if not img_path:
        return "No pude tomar la captura de pantalla, Señor."
    if not _js._router:
        return f"Captura tomada en {img_path}, pero el módulo de visión no está disponible."
    return _js._router.vision_query(prompt, img_path)


def skill_move_mouse(text: str) -> str:
    """
    Skill: Mueve el mouse a una posición.
    Ej: "mueve el mouse al centro", "mouse a 500 300"
    """
    nova = get_nova_enhanced()

    import re

    # Usar pyautogui directamente — evita nova_mouse que puede crashear en versiones de macOS
    try:
        import pyautogui as _pag
        lower = text.lower()
        w, h = _pag.size()
        cx, cy = _pag.position()

        if "centro" in lower:
            _pag.moveTo(w // 2, h // 2, duration=0.8)
            return "Mouse movido al centro, Señor."
        if "arriba" in lower:
            _pag.moveTo(cx, max(0, cy - 200), duration=0.5)
            return "Mouse movido hacia arriba, Señor."
        if "abajo" in lower:
            _pag.moveTo(cx, min(h, cy + 200), duration=0.5)
            return "Mouse movido hacia abajo, Señor."
        if "izquierda" in lower:
            _pag.moveTo(max(0, cx - 200), cy, duration=0.5)
            return "Mouse movido a la izquierda, Señor."
        if "derecha" in lower:
            _pag.moveTo(min(w, cx + 200), cy, duration=0.5)
            return "Mouse movido a la derecha, Señor."

        # Coordenadas numéricas
        coord = re.search(r'(\d+)\s+(\d+)', text)
        if coord:
            _pag.moveTo(int(coord.group(1)), int(coord.group(2)), duration=0.8)
            return f"Mouse movido a {coord.group(1)}, {coord.group(2)}, Señor."

        return "No entendí la posición. Decí: 'mouse al centro', 'mouse arriba', o 'mouse 500 300', Señor."
    except Exception as e:
        return f"No pude mover el mouse, Señor. {e}"


def skill_click(text: str = "") -> str:
    """Skill: Hace click con cursor visible. Fallback a pyautogui si enhanced no disponible."""
    nova = get_nova_enhanced()
    result = nova.click_with_feedback()
    if "no disponible" in result.lower():
        # Fallback directo a pyautogui
        try:
            import pyautogui
            pyautogui.click()
            return "Click realizado, Señor."
        except Exception as e:
            return f"No pude hacer click: {e}"
    return result


def skill_design_app(text: str) -> str:
    """
    Skill: Controla apps de diseño.
    Ej: "en Figma crea un frame", "en Photoshop exporta"
    """
    import re

    # Detectar app
    apps = ["figma", "sketch", "photoshop", "illustrator", "xd"]
    app = None
    for a in apps:
        if a in text.lower():
            app = a
            break

    if not app:
        return "No reconocí la app de diseño. Opciones: Figma, Sketch, Photoshop, Illustrator, XD"

    # Detectar acción
    actions = {
        "frame|nuevo frame|new frame": "new_frame",
        "component|componente": "new_component",
        "zoom": "zoom_in",
        "export|exportar": "export",
        "artboard": "new_artboard",
        "layer|capa": "new_layer",
    }

    action = None
    for pattern, act in actions.items():
        if re.search(pattern, text, re.I):
            action = act
            break

    if not action:
        return f"¿Qué acción quieres hacer en {app}?"

    nova = get_nova_enhanced()
    return nova.design_action(app, action)


# Lista de skills para registro automático
ENHANCED_SKILLS = [
    (r'(?:timer|alarma|recordatorio)\s+(?:en\s+)?(\d+)\s*(?:minutos?|mins?|m)', skill_set_timer, 1),
    (r'(?:alarma|despertador)\s+(?:a\s+)?las?\s+\d{1,2}:\d{2}', skill_set_alarm, 0),
    (r'(?:qué ves|ver pantalla|analiza pantalla)', skill_see_screen, 0),
    (r'(?:mueve|mover)\s+(?:el\s+)?(?:mouse|cursor)', skill_move_mouse, 0),
    (r'(?:haz|hacer)\s+click', skill_click, 0),
    (r'en\s+(?:Figma|Sketch|Photoshop|Illustrator|XD)', skill_design_app, 0),
]


if __name__ == "__main__":
    print("Nova Enhanced Integration cargado.")
    nova = get_nova_enhanced()
    print(f"Disponible:")
    print(f"  - Visión: {nova.is_available('vision')}")
    print(f"  - Mouse: {nova.is_available('mouse')}")
    print(f"  - Alarmas: {nova.is_available('alarms')}")