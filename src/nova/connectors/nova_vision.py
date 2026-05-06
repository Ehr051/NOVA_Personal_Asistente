"""
nova_vision.py
──────────────
Sistema de visión e interacción gestual para Nova.

Dos modos:
  1. GestureDetector  — cámara + MediaPipe, detecta gestos de mano en tiempo real
  2. vision_analizar  — qwen3-vl analiza imagen (pantalla o cámara) y describe lo que ve

Gestos reconocidos:
  ✋ Palma abierta    → activar Nova (wake word visual)
  ✊ Puño cerrado     → detener / silenciar
  👆 Un dedo          → confirmar / "sí"
  ✌️ Dos dedos        → cancelar / "no"
  👍 Pulgar arriba    → aprobar
  👎 Pulgar abajo     → rechazar
  🤏 Pinch (juntar)   → acercar / zoom in
  🖐 Mano abierta move→ rotar objeto 3D (tracking de posición)

Uso:
    from nova.connectors.nova_vision import GestureDetector, vision_analizar

    # Análisis de imagen
    desc = vision_analizar()           # captura pantalla y describe
    desc = vision_analizar(camara=True) # captura desde cámara

    # Detector en background
    det = GestureDetector(callback=mi_funcion)
    det.start()
    det.stop()
"""

from __future__ import annotations

import os
import io
import base64
import logging
import threading
import time
from pathlib import Path
from typing import Callable

log = logging.getLogger(__name__)

_OLLAMA_BASE  = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1")
_VISION_MODEL = "llava:7b"          # 4.7GB — en CPU puede tardar 2-3 min
_VISION_TIMEOUT = 240               # timeout generoso: GPU 4GB = corre en CPU parcialmente
_CAPTURE_DIR  = Path.home() / "Desktop" / "Nova_Vision"


# ═══════════════════════════════════════════════════════════════
# 1. ANÁLISIS DE IMAGEN CON LLM (qwen3-vl)
# ═══════════════════════════════════════════════════════════════

def _capturar_pantalla() -> bytes:
    """Captura la pantalla completa y devuelve bytes JPEG."""
    import pyautogui
    from PIL import Image
    img = pyautogui.screenshot()
    buf = io.BytesIO()
    img.convert("RGB").resize((1280, 720)).save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _capturar_camara(camara_idx: int = 0, warmup_sec: float | None = None) -> bytes | None:
    """Abre la cámara bajo demanda, espera a que estabilice y devuelve el mejor frame JPEG."""
    import cv2
    import numpy as np

    if warmup_sec is None:
        try:
            warmup_sec = float(os.getenv("NOVA_CAMERA_WARMUP_SEC", "2.0"))
        except ValueError:
            warmup_sec = 2.0
    warmup_sec = max(0.0, min(warmup_sec, 5.0))

    cap = cv2.VideoCapture(camara_idx)
    if not cap.isOpened():
        return None
    try:
        # Algunos backends respetan estas props; si no, no pasa nada.
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

        deadline = time.time() + warmup_sec
        best_frame = None
        best_score = -1.0

        while True:
            ret, frame = cap.read()
            if ret and frame is not None:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
                brightness = float(np.mean(gray))
                # Penaliza frames casi negros/blancos y prioriza nitidez.
                exposure_penalty = abs(brightness - 118.0) * 0.2
                score = sharpness - exposure_penalty
                if score > best_score:
                    best_score = score
                    best_frame = frame

            if time.time() >= deadline:
                break
            time.sleep(0.05)

        if best_frame is None:
            return None
        _, buf = cv2.imencode(".jpg", best_frame, [cv2.IMWRITE_JPEG_QUALITY, 88])
        return buf.tobytes()
    finally:
        cap.release()


_OR_VISION_MODELS = [
    "google/gemma-4-31b-it:free",
    "nvidia/nemotron-nano-12b-v2-vl:free",
    "google/gemma-3-27b-it:free",
]


def _llamar_vision_openrouter(imagen_bytes: bytes, prompt: str) -> str | None:
    """Fallback a OpenRouter cuando Ollama no está disponible."""
    import urllib.request, json as _json
    or_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not or_key or or_key.startswith("sk-or-v1-..."):
        return None
    b64 = base64.b64encode(imagen_bytes).decode()
    for model in _OR_VISION_MODELS:
        payload = {
            "model": model,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                ],
            }],
            "max_tokens": 400,
            "temperature": 0.2,
        }
        data = _json.dumps(payload).encode()
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {or_key}",
                "HTTP-Referer": "https://github.com/nova-assistant",
                "X-Title": "NOVA Personal Assistant",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                resp = _json.loads(r.read())
                text = (resp.get("choices", [{}])[0].get("message", {}).get("content") or "").strip()
                if text and text.strip():
                    log.info("Vision OK via OpenRouter/%s", model)
                    return text.strip()
        except Exception as e:
            log.warning("Vision OpenRouter/%s falló: %s", model, e)
    return None


def _llamar_vision(imagen_bytes: bytes, prompt: str, model: str = _VISION_MODEL) -> str:
    """Envía imagen + prompt al modelo de visión. Ollama primero, OpenRouter como fallback."""
    import urllib.request, json
    b64 = base64.b64encode(imagen_bytes).decode()
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": prompt,
                "images": [b64],
            }
        ],
        "stream": False,
        "options": {"temperature": 0.2, "num_predict": 400},
    }
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        "http://127.0.0.1:11434/api/chat",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    ollama_error = None
    try:
        with urllib.request.urlopen(req, timeout=_VISION_TIMEOUT) as r:
            resp = json.loads(r.read())
            return resp.get("message", {}).get("content", "").strip()
    except Exception as e:
        log.warning("Vision LLM falló con %s: %s", model, e)
        ollama_error = e
        # Intentar qwen3-vl si llava falló (solo si Ollama responde)
        if model == "llava:7b" and "Connection refused" not in str(e):
            try:
                return _llamar_vision(imagen_bytes, prompt, "qwen3-vl:latest")
            except Exception:
                pass

    # Ollama no disponible → fallback a OpenRouter
    result = _llamar_vision_openrouter(imagen_bytes, prompt)
    if result:
        return result
    return f"[vision no disponible: {ollama_error}]"


def vision_analizar(
    camara: bool = False,
    prompt: str = "",
    guardar: bool = False,
    camara_idx: int = 0,
    warmup_sec: float | None = None,
) -> str:
    """
    Captura pantalla o cámara y la analiza con qwen3-vl.

    camara=False → captura la pantalla actual
    camara=True  → captura desde cámara web
    prompt       → pregunta específica (default: descripción general)
    guardar      → guarda la imagen capturada en ~/Desktop/Nova_Vision/
    """
    if camara:
        imagen = _capturar_camara(camara_idx, warmup_sec=warmup_sec)
        if imagen is None:
            return "No pude acceder a la cámara, Señor."
        fuente = "cámara"
    else:
        imagen = _capturar_pantalla()
        fuente = "pantalla"

    if guardar:
        _CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        out = _CAPTURE_DIR / f"{ts}_{fuente}.jpg"
        out.write_bytes(imagen)

    if not prompt:
        prompt = (
            "Describí en español qué ves en esta imagen de forma detallada. "
            "Si hay texto, código, objetos, personas o interfaz gráfica, mencionalo. "
            "Sé específico y técnico."
        )

    return _llamar_vision(imagen, prompt)


def vision_analizar_archivo(path: str, prompt: str = "") -> str:
    """Analiza una imagen guardada en disco."""
    try:
        imagen = Path(path).read_bytes()
    except Exception as e:
        return f"No pude leer la imagen: {e}"
    if not prompt:
        prompt = (
            "Describí en español qué muestra esta imagen en 1-2 oraciones concisas. "
            "Mencioná el sujeto principal, estilo visual, colores dominantes y composición."
        )
    return _llamar_vision(imagen, prompt)


def vision_identificar_objeto(camara_idx: int = 0) -> str:
    """Captura la cámara e identifica el objeto principal que aparece."""
    imagen = _capturar_camara(camara_idx)
    if imagen is None:
        return "No pude acceder a la cámara, Señor."
    prompt = (
        "Identificá el objeto principal en esta imagen. "
        "Describí: nombre del objeto, material aparente, dimensiones estimadas, "
        "forma geométrica básica (cubo, cilindro, esfera, irregular...), "
        "y sus partes o componentes visibles. "
        "Respondé en español, formato estructurado."
    )
    return _llamar_vision(imagen, prompt)


def vision_para_cad(camara_idx: int = 0, software: str = "Blender") -> str:
    """
    Identifica un objeto en cámara y genera instrucciones para recrearlo en CAD/3D.
    software: 'Blender' | 'AutoCAD' | 'FreeCAD'
    """
    imagen = _capturar_camara(camara_idx)
    if imagen is None:
        return "No pude acceder a la cámara, Señor."
    prompt = (
        f"Analizá el objeto principal en esta imagen para recrearlo en {software}. "
        "Describí: "
        "1) Geometría base (primitivas: cubo, cilindro, esfera, toro, etc.) "
        "2) Dimensiones relativas (alto/ancho/profundidad aproximados) "
        "3) Operaciones booleanas necesarias (cortes, agujeros, uniones) "
        "4) Partes separadas si las hay "
        "5) Material y acabado superficial aparente. "
        "Sé técnico y específico para que un modelador 3D pueda recrearlo."
    )
    return _llamar_vision(imagen, prompt)


# ═══════════════════════════════════════════════════════════════
# 2. DETECTOR DE GESTOS — puente al detector existente
# ═══════════════════════════════════════════════════════════════
# Usa el detector completo en ~/Desktop/Detector-de-gestos/detectorGestos.py
# que ya tiene cursor, click, doble click, zoom, calibración, modo mesa/pantalla.

# Buscar el detector: primero dentro del repo, fallback al Desktop legacy
_DETECTOR_REPO   = Path(__file__).parents[1] / "perception" / "gesture_detector"
_DETECTOR_LEGACY = Path.home() / "Desktop" / "Detector-de-gestos"
_DETECTOR_PATH   = _DETECTOR_REPO if (_DETECTOR_REPO / "detectorGestos.py").exists() else _DETECTOR_LEGACY
# Python del virtualenv del detector (legacy) o el del repo si existe
_DETECTOR_PYTHON = _DETECTOR_LEGACY / "detector_gestos_env" / "bin" / "python3"


def _detector_python() -> str:
    """Retorna el intérprete correcto para correr el detector."""
    if _DETECTOR_PYTHON.exists():
        return str(_DETECTOR_PYTHON)
    import sys
    return sys.executable


def iniciar_detector(modo: str = "pantalla", camara: int = 0) -> str:
    """
    Inicia el detector de gestos usando su virtualenv propio.
    modo: 'pantalla' | 'mesa'
    camara: índice de cámara (0, 1, 2...)
    """
    import subprocess
    detector_py = _DETECTOR_PATH / "detectorGestos.py"
    if not detector_py.exists():
        return f"No encontré el detector en {detector_py}, Señor."

    python = _detector_python()
    cmd = [python, str(detector_py), f"--modo={modo}", f"--camara={camara}"]

    try:
        # stdout/stderr a DEVNULL — el detector tiene su propia ventana y logs
        subprocess.Popen(
            cmd,
            cwd=str(_DETECTOR_PATH),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return f"Detector de gestos iniciado en modo {modo} (cámara {camara}), Señor."
    except Exception as e:
        return f"No pude iniciar el detector: {e}"


def detener_detector() -> str:
    """Detiene todos los procesos del detector de gestos."""
    import subprocess
    try:
        subprocess.run(
            ["pkill", "-f", "detectorGestos.py"],
            capture_output=True
        )
        return "Detector de gestos detenido, Señor."
    except Exception as e:
        return f"No pude detener el detector: {e}"


def estado_detector() -> str:
    """Verifica si el detector de gestos está corriendo."""
    import subprocess
    result = subprocess.run(
        ["pgrep", "-f", "detectorGestos.py"],
        capture_output=True, text=True
    )
    if result.stdout.strip():
        return "Detector de gestos activo, Señor."
    return "Detector de gestos inactivo."


def crear_callback_nova(nova_instance=None) -> None:
    """Placeholder — el detector existente maneja su propio loop. Ver detectorGestos.py."""
    return None
