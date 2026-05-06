#!/usr/bin/env python3
"""
nova_vision.py
──────────────
Sistema de visión y análisis visual para Nova.

Características:
  • Captura de pantalla completa o región específica
  • Análisis de imagen con modelos locales (Ollama) o cloud
  • OCR (reconocimiento de texto en pantalla)
  • Detección de elementos UI (botones, campos, etc.)
  • Integración con pyautogui para "ver antes de actuar"

Uso:
  from nova_vision import VisionSystem
  vision = VisionSystem()

  # Capturar y analizar pantalla
  analysis = vision.analyze_screen("¿Qué aplicación está activa?")

  # Capturar región específica
  region = vision.capture_region(100, 100, 400, 300)

  # OCR para encontrar texto
  text = vision.find_text_on_screen("Aceptar")
"""

from __future__ import annotations

import os
import io
import base64
import subprocess
import tempfile
from pathlib import Path
from typing import Literal, Optional
from dataclasses import dataclass
from datetime import datetime

import numpy as np
from PIL import Image, ImageGrab, ImageDraw, ImageFont


def ensure_deps():
    """Asegura que las dependencias estén instaladas."""
    try:
        import PIL
        import numpy
    except ImportError:
        print("Instalando dependencias de visión...")
        subprocess.run(["pip", "install", "pillow", "numpy", "-q"], check=False)


@dataclass
class ScreenRegion:
    """Representa una región de la pantalla."""
    x: int
    y: int
    width: int
    height: int

    @property
    def center(self) -> tuple[int, int]:
        return (self.x + self.width // 2, self.y + self.height // 2)

    @property
    def bbox(self) -> tuple[int, int, int, int]:
        return (self.x, self.y, self.x + self.width, self.y + self.height)


@dataclass
class DetectedElement:
    """Elemento detectado en la pantalla."""
    type: str  # 'button', 'text', 'icon', 'input', etc.
    text: Optional[str]
    region: ScreenRegion
    confidence: float


class VisionSystem:
    """
    Sistema de visión para Nova.
    Permite capturar, analizar e interactuar con la pantalla.
    """

    def __init__(self, debug: bool = False):
        self.debug = debug
        self.last_capture: Optional[Image.Image] = None
        self.last_capture_path: Optional[str] = None
        self.screenshots_dir = Path.home() / "Desktop" / "Nova_Screenshots"
        self.screenshots_dir.mkdir(exist_ok=True)

    def capture_fullscreen(self, save: bool = True) -> Image.Image:
        """
        Captura la pantalla completa.

        Returns:
            PIL Image de la captura
        """
        screenshot = ImageGrab.grab()
        self.last_capture = screenshot

        if save:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = self.screenshots_dir / f"nova_capture_{timestamp}.png"
            screenshot.save(path)
            self.last_capture_path = str(path)
            if self.debug:
                print(f"[Vision] Captura guardada en: {path}")

        return screenshot

    def capture_region(self, x: int, y: int, width: int, height: int) -> Image.Image:
        """
        Captura una región específica de la pantalla.

        Args:
            x, y: Coordenadas superior izquierda
            width, height: Dimensiones

        Returns:
            PIL Image de la región
        """
        screenshot = ImageGrab.grab(bbox=(x, y, x + width, y + height))
        return screenshot

    def capture_active_window(self) -> Optional[Image.Image]:
        """
        Intenta capturar solo la ventana activa (macOS).
        Requiere permisos de accesibilidad.
        """
        try:
            # Usar screencapture con flag de ventana
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                temp_path = f.name

            result = subprocess.run(
                ["screencapture", "-w", temp_path],
                capture_output=True,
                text=True
            )

            if result.returncode == 0 and os.path.exists(temp_path):
                img = Image.open(temp_path)
                os.unlink(temp_path)
                return img
        except Exception as e:
            if self.debug:
                print(f"[Vision] Error capturando ventana activa: {e}")

        # Fallback a pantalla completa
        return self.capture_fullscreen()

    def highlight_region(self, image: Image.Image, region: ScreenRegion,
                         color: str = "red", width: int = 3) -> Image.Image:
        """
        Dibuja un rectángulo resaltando una región en la imagen.

        Returns:
            Nueva imagen con el resaltado
        """
        img_copy = image.copy()
        draw = ImageDraw.Draw(img_copy)

        # Dibujar rectángulo
        draw.rectangle(region.bbox, outline=color, width=width)

        # Dibujar centro
        cx, cy = region.center
        r = 5
        draw.ellipse([cx-r, cy-r, cx+r, cy+r], fill=color)

        return img_copy

    def save_annotated_capture(self, regions: list[ScreenRegion],
                               labels: Optional[list[str]] = None) -> str:
        """
        Guarda una captura con regiones resaltadas.
        Útil para debugging y para "mostrar" a Nova qué ve.

        Args:
            regions: Lista de regiones a resaltar
            labels: Opcional, etiquetas para cada región

        Returns:
            Path al archivo guardado
        """
        if self.last_capture is None:
            self.capture_fullscreen(save=False)

        img = self.last_capture.copy()
        draw = ImageDraw.Draw(img)

        colors = ["red", "green", "blue", "yellow", "purple", "orange"]

        for i, region in enumerate(regions):
            color = colors[i % len(colors)]
            img = self.highlight_region(img, region, color)

            # Añadir etiqueta si se proporciona
            if labels and i < len(labels):
                try:
                    font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 14)
                except:
                    font = ImageFont.load_default()

                # Dibujar fondo para texto
                text = labels[i]
                bbox = draw.textbbox((region.x, region.y - 20), text, font=font)
                draw.rectangle(bbox, fill=color)
                draw.text((region.x, region.y - 20), text, fill="white", font=font)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self.screenshots_dir / f"nova_annotated_{timestamp}.png"
        img.save(path)

        return str(path)

    def image_to_base64(self, image: Image.Image, format: str = "PNG") -> str:
        """Convierte imagen PIL a string base64."""
        buffer = io.BytesIO()
        image.save(buffer, format=format)
        return base64.b64encode(buffer.getvalue()).decode()

    def find_template(self, template_path: str, threshold: float = 0.8) -> Optional[ScreenRegion]:
        """
        Busca una imagen template en la pantalla (template matching).
        Útil para encontrar botones/iconos específicos.

        Args:
            template_path: Path a la imagen a buscar
            threshold: Umbral de coincidencia (0-1)

        Returns:
            ScreenRegion si encuentra, None si no
        """
        try:
            import cv2
        except ImportError:
            subprocess.run(["pip", "install", "opencv-python", "-q"], check=False)
            import cv2

        # Capturar pantalla
        screenshot = self.capture_fullscreen(save=False)
        screenshot_cv = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)

        # Cargar template
        template = cv2.imread(template_path)
        if template is None:
            return None

        # Template matching
        result = cv2.matchTemplate(screenshot_cv, template, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

        if max_val >= threshold:
            h, w = template.shape[:2]
            return ScreenRegion(max_loc[0], max_loc[1], w, h)

        return None

    def get_screen_size(self) -> tuple[int, int]:
        """Retorna el tamaño de la pantalla (width, height)."""
        screenshot = ImageGrab.grab()
        return screenshot.size

    def analyze_for_action(self, action_description: str) -> dict:
        """
        Analiza la pantalla para determinar cómo realizar una acción.

        Args:
            action_description: Descripción de lo que se quiere hacer

        Returns:
            Diccionario con análisis y recomendaciones
        """
        # Capturar pantalla
        screenshot = self.capture_fullscreen()

        # Guardar para análisis
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self.screenshots_dir / f"nova_analysis_{timestamp}.png"
        screenshot.save(path)

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
            "screenshot_path": str(path),
            "active_application": active_app,
            "screen_size": screenshot.size,
            "action": action_description,
            "timestamp": timestamp
        }


# Instancia global para uso rápido
_vision_instance: Optional[VisionSystem] = None


def get_vision() -> VisionSystem:
    """Retorna la instancia global de VisionSystem."""
    global _vision_instance
    if _vision_instance is None:
        _vision_instance = VisionSystem()
    return _vision_instance


if __name__ == "__main__":
    # Test
    print("Probando sistema de visión...")
    vision = VisionSystem(debug=True)

    # Capturar pantalla
    img = vision.capture_fullscreen()
    print(f"Captura: {img.size}")

    # Capturar región
    region = ScreenRegion(100, 100, 300, 200)
    annotated = vision.save_annotated_capture([region], ["Área de prueba"])
    print(f"Imagen anotada guardada en: {annotated}")
