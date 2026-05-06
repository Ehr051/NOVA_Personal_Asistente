#!/usr/bin/env python3
"""
nova-perception-mcp
MCP server that aggregates gesture, face, emotion, and screen data for Nova.
Provides tools via stdio JSON-RPC (MCP specification).
"""

import sys
import json
import threading
import time
import cv2
import numpy as np
from datetime import datetime
from pathlib import Path

# Optional imports with fallbacks
try:
    import mediapipe as mp
    _HAS_MEDIAPIPE = True
except Exception:
    _HAS_MEDIAPIPE = False

try:
    from deepface import DeepFace
    _HAS_DEEPFACE = True
except Exception:
    _HAS_DEEPFACE = False

try:
    import face_recognition
    _HAS_FACE_REC = True
except Exception:
    _HAS_FACE_REC = False

try:
    import pytesseract
    from PIL import ImageGrab
    _HAS_OCR = True
except Exception:
    _HAS_OCR = False

# Gesture detector integration
_GESTOR_AVAILABLE = False
try:
    # Import the existing gesture detector from the repo
    sys.path.append(str(Path(__file__).parent.parent / "perception" / "gesture_detector"))
    from detectorGestos import DetectorGestos
    _GESTOR_AVAILABLE = True
except Exception:
    _GESTOR_AVAILABLE = False

# Shared state for latest data
_latest_data = {
    "gesture": None,
    "face_id": None,
    "emotion": None,
    "screen_text": None,
    "timestamp": None
}
_lock = threading.Lock()


def _vision_analizar_on_demand(
    *,
    camara: bool,
    prompt: str = "",
    guardar: bool = False,
    camara_idx: int = 0,
    warmup_sec: float | None = None,
) -> str:
    """Run the heavier vision model only when explicitly requested."""
    from nova.connectors.nova_vision import vision_analizar

    return vision_analizar(
        camara=camara,
        prompt=prompt,
        guardar=guardar,
        camara_idx=camara_idx,
        warmup_sec=warmup_sec,
    )

def _gesture_worker():
    """Background thread to update gesture data using existing detector."""
    if not (_GESTOR_AVAILABLE and _HAS_MEDIAPIPE):
        return
    try:
        detector = DetectorGestos(modo="pantalla")
        # We'll run a limited loop: capture frame, process, update shared state
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            print("Perception MCP: Could not open camera", file=sys.stderr)
            return
        while True:
            ret, frame = cap.read()
            if not ret:
                continue
            # Process frame for gestures (simplified)
            # In a full implementation we'd run the detector's loop and extract gesture
            # For now, we just set a placeholder
            with _lock:
                _latest_data["gesture"] = "detected"  # placeholder
                _latest_data["timestamp"] = datetime.now().isoformat()
            time.sleep(0.1)
    except Exception as e:
        print(f"Perception MCP gesture worker error: {e}", file=sys.stderr)

def _face_worker():
    """Background thread for face identification."""
    if not _HAS_FACE_REC:
        return
    # Placeholder: would load known faces and compare
    while True:
        with _lock:
            _latest_data["face_id"] = "unknown"  # placeholder
        time.sleep(1)

def _emotion_worker():
    """Background thread for emotion detection."""
    if not _HAS_DEEPFACE:
        return
    while True:
        with _lock:
            _latest_data["emotion"] = "neutral"  # placeholder
        time.sleep(1)

def _screen_worker():
    """Background thread for screen text (OCR)."""
    if not _HAS_OCR:
        return
    while True:
        try:
            img = ImageGrab.grab()
            text = pytesseract.image_to_string(img, lang='spa+eng')
            with _lock:
                _latest_data["screen_text"] = text.strip()[:200]  # limit length
        except Exception:
            with _lock:
                _latest_data["screen_text"] = ""
        time.sleep(2)

def start_background_workers():
    """Start all background data collection threads."""
    if _GESTOR_AVAILABLE and _HAS_MEDIAPIPE:
        t = threading.Thread(target=_gesture_worker, daemon=True)
        t.start()
    if _HAS_FACE_REC:
        t = threading.Thread(target=_face_worker, daemon=True)
        t.start()
    if _HAS_DEEPFACE:
        t = threading.Thread(target=_emotion_worker, daemon=True)
        t.start()
    if _HAS_OCR:
        t = threading.Thread(target=_screen_worker, daemon=True)
        t.start()

def handle_request(request):
    """Handle a JSON-RPC request and return response."""
    try:
        method = request.get("method")
        params = request.get("params", {})
        req_id = request.get("id")
        
        if method == "get_gesture":
            with _lock:
                gesture = _latest_data.get("gesture")
            result = {"gesture": gesture or "none"}
        elif method == "get_face_id":
            with _lock:
                face_id = _latest_data.get("face_id")
            result = {"face_id": face_id or "unknown"}
        elif method == "get_emotion":
            with _lock:
                emotion = _latest_data.get("emotion")
            result = {"emotion": emotion or "neutral"}
        elif method == "get_screen_text":
            with _lock:
                screen_text = _latest_data.get("screen_text")
            result = {"screen_text": screen_text or ""}
        elif method == "get_all":
            with _lock:
                data = _latest_data.copy()
            result = data
        elif method in ("analyze_camera_once", "analyze_camera"):
            prompt = str(params.get("prompt") or "").strip()
            guardar = bool(params.get("guardar", False))
            try:
                camara_idx = int(params.get("camara_idx", 0))
            except (TypeError, ValueError):
                camara_idx = 0
            try:
                warmup_sec = float(params.get("warmup_sec", 2.0))
            except (TypeError, ValueError):
                warmup_sec = 2.0
            if not prompt:
                prompt = (
                    "Analizá lo que ves por la cámara en español. "
                    "Describí objetos principales, personas si aparecen, texto visible, "
                    "posición relativa y cualquier detalle útil para responder al usuario."
                )
            analysis = _vision_analizar_on_demand(
                camara=True,
                prompt=prompt,
                guardar=guardar,
                camara_idx=camara_idx,
                warmup_sec=warmup_sec,
            )
            result = {
                "source": "camera",
                "camera_index": camara_idx,
                "analysis": analysis,
                "timestamp": datetime.now().isoformat(),
            }
        elif method in ("analyze_screen_once", "analyze_screen"):
            prompt = str(params.get("prompt") or "").strip()
            guardar = bool(params.get("guardar", False))
            if not prompt:
                prompt = (
                    "Analizá la pantalla actual en español. Describí apps abiertas, "
                    "texto visible, elementos de UI y cualquier error o acción probable."
                )
            analysis = _vision_analizar_on_demand(
                camara=False,
                prompt=prompt,
                guardar=guardar,
            )
            result = {
                "source": "screen",
                "analysis": analysis,
                "timestamp": datetime.now().isoformat(),
            }
        else:
            return {
                "jsonrpc": "2.0",
                "error": {"code": -32601, "message": f"Method not found: {method}"},
                "id": req_id
            }
        
        return {
            "jsonrpc": "2.0",
            "result": result,
            "id": req_id
        }
    except Exception as e:
        return {
            "jsonrpc": "2.0",
            "error": {"code": -32603, "message": str(e)},
            "id": request.get("id") if isinstance(request, dict) else None
        }

def main():
    """Main MCP server loop: read JSON-RPC requests from stdin, write responses to stdout."""
    # Start background data collection
    start_background_workers()
    
    # Simple line-based JSON-RPC over stdin/stdout
    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break
            line = line.strip()
            if not line:
                continue
            request = json.loads(line)
            response = handle_request(request)
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()
        except json.JSONDecodeError:
            # Ignore invalid JSON lines
            continue
        except Exception as e:
            # Send error response if possible
            err_resp = {
                "jsonrpc": "2.0",
                "error": {"code": -32603, "message": str(e)},
                "id": None
            }
            try:
                sys.stdout.write(json.dumps(err_resp) + "\n")
                sys.stdout.flush()
            except Exception:
                break

if __name__ == "__main__":
    main()
