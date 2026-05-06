"""
nova_image.py
─────────────
Generación de imágenes para Nova via Pollinations.ai (gratis, sin API key).
Modelos disponibles: flux (default), flux-realism, flux-anime, flux-3d, turbo

Uso:
    from nova.connectors.nova_image import generar_imagen
    path = generar_imagen("un castillo en la niebla al amanecer")
"""

from __future__ import annotations

import os
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime
from pathlib import Path

# ─── Config ───────────────────────────────────────────────────────────────────

_BASE_URL  = "https://image.pollinations.ai/prompt"
_OUTPUT_DIR = Path.home() / "Desktop" / "Nova_Imagenes"
_TIMEOUT   = 60  # segundos (la generación puede tardar)

_MODELS = {
    "foto":     "flux-realism",
    "anime":    "flux-anime",
    "3d":       "flux-3d",
    "rapido":   "turbo",
    "default":  "flux",
}

# Mejoras automáticas de prompt según estilo
_STYLE_ENHANCERS = {
    "foto":  ", photorealistic, high detail, professional photography, 8k",
    "anime": ", anime style, vibrant colors, detailed illustration",
    "3d":    ", 3D render, octane render, detailed, volumetric lighting",
    "rapido": "",
    "default": ", high quality, detailed",
}


# ─── Core ─────────────────────────────────────────────────────────────────────

_STEPS = {
    "foto":    28,
    "anime":   28,
    "3d":      28,
    "rapido":   4,
    "default": 28,
}


def generar_imagen(
    prompt: str,
    estilo: str = "default",
    ancho: int = 1024,
    alto: int = 1024,
    seed: int | None = None,
    steps: int | None = None,
) -> str | None:
    """
    Genera una imagen a partir de un prompt en español o inglés.
    Devuelve la ruta al archivo guardado, o None si falló.
    """
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    modelo      = _MODELS.get(estilo, _MODELS["default"])
    enhancer    = _STYLE_ENHANCERS.get(estilo, "")
    full_prompt = prompt + enhancer
    n_steps     = steps if steps is not None else _STEPS.get(estilo, 28)

    params: dict = {
        "width":  ancho,
        "height": alto,
        "model":  modelo,
        "nologo": "true",
        "steps":  n_steps,
    }
    if seed is not None:
        params["seed"] = seed

    url = f"{_BASE_URL}/{urllib.parse.quote(full_prompt)}?{urllib.parse.urlencode(params)}"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Nova/1.0"})
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            if resp.status != 200:
                return None
            data = resp.read()

        ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
        name = _safe_filename(prompt[:40])
        path = _OUTPUT_DIR / f"{ts}_{name}.jpg"
        path.write_bytes(data)
        return str(path)

    except Exception as e:
        return None


def abrir_imagen(path: str) -> None:
    """Abre la imagen con la app por defecto del sistema."""
    import subprocess
    subprocess.Popen(["open", path])


def _safe_filename(text: str) -> str:
    import re
    return re.sub(r"[^a-zA-Z0-9_áéíóúñ\s]", "", text).strip().replace(" ", "_")[:40]
