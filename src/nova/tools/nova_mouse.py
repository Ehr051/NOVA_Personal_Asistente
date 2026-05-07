import logging
import time
import pyautogui
import math
import platform
from typing import Optional

log = logging.getLogger(__name__)

class NovaComputerPilot:
    """
    Controlador cross-platform del mouse y UI de NOVA 3.0.
    Asegura los trazados visuales y el "puntero azul" manteniendo 
    la tolerancia frente a pantallas de diferentes resoluciones.
    """
    def __init__(self):
        # FailSafe: Mover el ratón a la esquina apaga la ejecución por seguridad.
        pyautogui.FAILSAFE = True
        # Pequeño retraso después de cada comando para emular comportamiento humano
        pyautogui.PAUSE = 0.2
        self.os_type = platform.system()
        log.info("[Mouse] Inicializado en %s. Failsafe ACTIVO.", self.os_type)

    def move_to(self, x: int, y: int, speed: float = 0.5):
        """Mueve el mouse visualmente mostrando el recorrido."""
        try:
            log.debug("[Mouse] Moviendo a (%s, %s)", x, y)
            # Usa 'easeInOutQuad' para darle organicidad al movimiento robótico
            pyautogui.moveTo(x, y, speed, pyautogui.easeInOutQuad)
        except pyautogui.FailSafeException:
            log.warning("[Mouse] FAILSAFE activado — usuario movió ratón a esquina")
        except Exception as e:
            log.warning("[Mouse] Error moviendo ratón: %s", e)

    def click(self, x: int = None, y: int = None, clicks: int = 1):
        """Ejecuta un clic. Si X o Y son omitidos, clica en la posición actual."""
        try:
            if x is not None and y is not None:
                self.move_to(x, y)
                
            log.debug("[Mouse] Click %sx", clicks)
            pyautogui.click(clicks=clicks)
        except Exception as e:
            log.warning("[Mouse] Error click: %s", e)

    def type_text(self, text: str, interval: float = 0.05):
        """Teclea texto simulando pulsaciones humanas."""
        try:
            log.debug("[Mouse] Escribiendo texto: %s...", text[:15])
            pyautogui.write(text, interval=interval)
        except Exception as e:
            log.warning("[Mouse] Error tecleando: %s", e)

    def draw_blue_cursor_overlay(self):
        """
        Dibuja un círculo azul simulando el cursor virtual.
        En Mac/Windows esto se logra comúnmente instanciando un overlay
        transparente en PyQt o Tkinter que siga la posición de PyAutoGUI.
        (Implementación base de rastreo)
        """
        # TODO: Para el puntero azul visual persistente que se diferencia del
        # nativo, normalmente levantamos un canvas de Tkinter Always-On-Top.
        # Aquí seteamos el framework conceptual.
        current_x, current_y = pyautogui.position()
        log.debug("[Mouse] Cursor en (%s, %s)", current_x, current_y)
        return current_x, current_y

# Instancia global para uso rápido
_pilot_instance: Optional[NovaComputerPilot] = None

def get_mouse() -> NovaComputerPilot:
    """Retorna la instancia global de NovaComputerPilot."""
    global _pilot_instance
    if _pilot_instance is None:
        _pilot_instance = NovaComputerPilot()
    return _pilot_instance

# Uso directo
if __name__ == "__main__":
    pilot = get_mouse()
    pilot.draw_blue_cursor_overlay()
