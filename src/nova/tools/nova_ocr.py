"""
nova_ocr.py
───────────
Conversión de documentos y extracción de texto para Nova.
Soporta: PDF, DOCX, XLSX, PPTX, HTML, imágenes, TXT, MD, CSV.
"""

from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)

try:
    from markitdown import MarkItDown
    _HAS_MARKITDOWN = True
except ImportError:
    _HAS_MARKITDOWN = False

try:
    import pytesseract
    from PIL import Image as _PILImage
    _HAS_TESSERACT = True
except ImportError:
    _HAS_TESSERACT = False


_PLAIN_EXTENSIONS = {".txt", ".md", ".csv"}
_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"}
_MARKITDOWN_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".pptx", ".html", ".htm"}


def convert_to_markdown(file_path: str | Path) -> tuple[str, str]:
    """Convert any supported file to Markdown. Returns (markdown_text, summary_line)."""
    path = Path(file_path)
    ext = path.suffix.lower()

    if not path.exists():
        return "", f"Archivo no encontrado: {path}"

    if ext in _PLAIN_EXTENSIONS:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            summary = f"{path.name} ({len(text.splitlines())} líneas)"
            return text, summary
        except Exception as e:
            log.error("Error leyendo texto plano %s: %s", path, e)
            return "", str(e)

    if ext in _IMAGE_EXTENSIONS:
        text = extract_text_from_image(path)
        summary = f"{path.name} — texto extraído por OCR ({len(text)} chars)"
        return text, summary

    if ext in _MARKITDOWN_EXTENSIONS:
        if _HAS_MARKITDOWN:
            try:
                md = MarkItDown()
                result = md.convert(str(path))
                text = result.text_content if hasattr(result, "text_content") else str(result)
                summary = f"{path.name} convertido a Markdown ({len(text)} chars)"
                return text, summary
            except Exception as e:
                log.error("MarkItDown falló en %s: %s", path, e)
                return "", f"Error convirtiendo {path.name}: {e}"
        else:
            return "", "MarkItDown no está instalado. Ejecutá: pip install markitdown"

    # Extensión desconocida — intentar como texto plano
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        summary = f"{path.name} leído como texto ({len(text.splitlines())} líneas)"
        return text, summary
    except Exception as e:
        return "", f"Extensión no soportada ({ext}) y lectura de texto falló: {e}"


def extract_text_from_image(image_path: str | Path) -> str:
    """Extract text from image using pytesseract if available, else markitdown."""
    path = Path(image_path)

    if _HAS_TESSERACT:
        try:
            img = _PILImage.open(path)
            return pytesseract.image_to_string(img, lang="spa+eng")
        except Exception as e:
            log.warning("pytesseract falló en %s: %s — intentando markitdown", path, e)

    if _HAS_MARKITDOWN:
        try:
            md = MarkItDown()
            result = md.convert(str(path))
            return result.text_content if hasattr(result, "text_content") else str(result)
        except Exception as e:
            log.error("MarkItDown falló en imagen %s: %s", path, e)
            return f"[Error extrayendo texto: {e}]"

    return "[Sin motor OCR disponible. Instalá pytesseract o markitdown.]"


def read_file_as_context(file_path: str | Path, max_chars: int = 8000) -> str:
    """High-level: read any file and return it as context string for LLM."""
    path = Path(file_path)
    text, summary = convert_to_markdown(path)

    if not text:
        return f"No se pudo leer el archivo: {summary}"

    header = f"── Archivo: {path.name} ──\n{summary}\n\n"

    if len(text) > max_chars:
        truncated = text[:max_chars]
        footer = f"\n\n[... truncado — {len(text) - max_chars} chars adicionales no mostrados]"
        return header + truncated + footer

    return header + text
