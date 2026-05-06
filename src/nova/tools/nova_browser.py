"""
nova_browser.py
───────────────
Control de browser para Nova usando Playwright Python.
Disponible como skills de voz y como módulo directo.

Skills expuestas:
  skill_abrir_url(text)      → "abre google.com"
  skill_buscar_web(text)     → "busca en la web cómo hacer X"
  skill_capturar_web(text)   → "captura la página actual"
  skill_leer_pagina(text)    → "lee el contenido de esta página"
  skill_hacer_click(text)    → "clickeá en el botón Aceptar"
  skill_llenar_campo(text)   → "escribí 'hola' en el campo de búsqueda"
"""

from __future__ import annotations

import re
import os
import time
import threading
from typing import Optional

_browser = None
_page = None
_playwright_obj = None
_lock = threading.Lock()
_HAS_PLAYWRIGHT = False

try:
    from playwright.sync_api import sync_playwright, Page, Browser
    _HAS_PLAYWRIGHT = True
except ImportError:
    pass


# ── Browser lifecycle ──────────────────────────────────────────────────────────

def _get_page() -> Optional["Page"]:
    """Retorna la página activa, iniciando el browser si es necesario."""
    global _browser, _page, _playwright_obj

    if not _HAS_PLAYWRIGHT:
        return None

    with _lock:
        if _page is None or _page.is_closed():
            try:
                if _playwright_obj is None:
                    _playwright_obj = sync_playwright().start()
                if _browser is None or not _browser.is_connected():
                    _browser = _playwright_obj.chromium.launch(
                        headless=False,   # visible para que el usuario pueda ver
                        args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
                    )
                _page = _browser.new_page()
                _page.set_viewport_size({"width": 1280, "height": 800})
            except Exception as e:
                print(f"[Browser] Error al iniciar: {e}")
                return None
    return _page


def close_browser():
    """Cierra el browser completamente."""
    global _browser, _page, _playwright_obj
    with _lock:
        try:
            if _page and not _page.is_closed():
                _page.close()
            if _browser and _browser.is_connected():
                _browser.close()
            if _playwright_obj:
                _playwright_obj.stop()
        except Exception:
            pass
        _page = None
        _browser = None
        _playwright_obj = None


# ── Core actions ──────────────────────────────────────────────────────────────

def navegar(url: str, wait: float = 2.0) -> str:
    """Navega a una URL y espera a que cargue."""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    page = _get_page()
    if not page:
        return "Browser no disponible, Señor."
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=15000)
        time.sleep(wait)
        title = page.title()
        return f"Abrí '{title}' ({url}), Señor."
    except Exception as e:
        return f"No pude abrir {url}: {e}"


def leer_pagina(max_chars: int = 2000) -> str:
    """Extrae el texto visible de la página actual."""
    page = _get_page()
    if not page:
        return "Browser no disponible, Señor."
    try:
        # Extraer texto con JS — más limpio que inner_text directo
        text = page.evaluate("""() => {
            const skip = ['script','style','nav','footer','header','aside'];
            function getText(el) {
                if (skip.includes(el.tagName?.toLowerCase())) return '';
                if (el.nodeType === 3) return el.textContent.trim();
                return Array.from(el.childNodes).map(getText).join(' ');
            }
            return getText(document.body);
        }""")
        # Limpiar espacios múltiples
        text = re.sub(r'\s{2,}', ' ', text or '').strip()
        if not text:
            return "La página no tiene texto visible, Señor."
        truncated = len(text) > max_chars
        return text[:max_chars] + ("\n[...truncado]" if truncated else "")
    except Exception as e:
        return f"No pude leer la página: {e}"


def buscar_google(query: str) -> str:
    """Busca en Google y retorna los primeros resultados."""
    url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
    page = _get_page()
    if not page:
        return "Browser no disponible, Señor."
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=15000)
        time.sleep(1.5)
        # Extraer títulos y snippets de resultados
        results = page.evaluate("""() => {
            const out = [];
            document.querySelectorAll('h3').forEach(h => {
                const title = h.innerText.trim();
                const parent = h.closest('[data-hveid]') || h.parentElement;
                const snippet = parent?.querySelector('div[style*=\\"webkit-line-clamp\\"]')?.innerText
                             || parent?.querySelector('span')?.innerText || '';
                if (title) out.push({ title, snippet: snippet.substring(0, 150) });
            });
            return out.slice(0, 5);
        }""")
        if not results:
            return f"Busqué '{query}' pero no encontré resultados claros, Señor."
        lines = [f"Resultados para '{query}':"]
        for r in results:
            lines.append(f"• {r['title']}: {r['snippet']}")
        return "\n".join(lines)
    except Exception as e:
        return f"No pude buscar en Google: {e}"


def capturar_pantalla(path: str = "") -> str:
    """Toma screenshot de la página actual."""
    page = _get_page()
    if not page:
        return "Browser no disponible, Señor."
    if not path:
        ts = time.strftime("%Y%m%d_%H%M%S")
        path = os.path.expanduser(f"~/Desktop/nova_web_{ts}.png")
    try:
        page.screenshot(path=path, full_page=False)
        return f"Captura guardada en {path}, Señor."
    except Exception as e:
        return f"No pude capturar: {e}"


def _vision_click(target_description: str) -> str:
    """
    Visual click: takes a screenshot, asks the vision model for the pixel
    coordinates of the described element, then clicks at those coordinates
    using pyautogui.  This is the correct path for clicking on-screen
    elements that are NOT inside a Playwright-controlled browser page.

    Returns a human-readable result string.
    """
    import subprocess, tempfile, os as _os
    try:
        import pyautogui as _pag
    except ImportError:
        return "pyautogui no disponible para click visual, Señor."

    # 1. Take a screenshot using screencapture (avoids PIL/CoreGraphics crash)
    fd, img_path = tempfile.mkstemp(suffix=".png")
    _os.close(fd)
    result = subprocess.run(["screencapture", "-x", img_path], capture_output=True)
    if result.returncode != 0 or not _os.path.exists(img_path):
        return "No pude tomar la captura de pantalla para localizar el elemento, Señor."

    # 2. Ask vision model for coordinates
    try:
        # Lazy import to avoid circular dependency
        import nova_skills as _js
        router = _js._router
    except Exception:
        router = None

    if router is None:
        _os.unlink(img_path)
        return "El módulo de visión no está inicializado, Señor."

    vision_prompt = (
        f"Find the UI element described as: '{target_description}'\n"
        "Respond with ONLY the pixel coordinates in this exact format: X,Y\n"
        "Example: 542,318\n"
        "If you cannot find the element, respond: NOT_FOUND"
    )

    try:
        answer = router.vision_query(vision_prompt, img_path).strip()
    except Exception as exc:
        _os.unlink(img_path)
        return f"Error de visión al localizar '{target_description}': {exc}"
    finally:
        try:
            _os.unlink(img_path)
        except Exception:
            pass

    # 3. Parse coordinates
    if "NOT_FOUND" in answer.upper() or "no" in answer.lower()[:20]:
        return f"No encontré '{target_description}' en pantalla, Señor."

    coord_match = re.search(r'(\d+)\s*[,x]\s*(\d+)', answer)
    if not coord_match:
        return f"No pude interpretar las coordenadas de '{target_description}' (respuesta: {answer[:80]}), Señor."

    x, y = int(coord_match.group(1)), int(coord_match.group(2))

    # 4. Sanity check — coordinates must be within screen bounds
    try:
        screen_w, screen_h = _pag.size()
        if not (0 <= x <= screen_w and 0 <= y <= screen_h):
            return f"Coordenadas fuera de pantalla ({x},{y}), Señor."
    except Exception:
        pass

    # 5. Move and click using pyautogui (pixel-level, OS-native)
    try:
        _pag.moveTo(x, y, duration=0.4)
        time.sleep(0.1)
        _pag.click(x, y)
        return f"Click visual en '{target_description}' en ({x},{y}), Señor."
    except Exception as exc:
        return f"No pude hacer click en ({x},{y}): {exc}"


def hacer_click(texto: str) -> str:
    """
    Hace click en el elemento que contenga el texto dado.

    Strategy:
      1. If a Playwright browser page is open and active → use DOM locator
         (correct for in-browser UI elements like buttons/links).
      2. Otherwise → use vision + pyautogui coordinate click
         (correct for desktop apps, system UI, anything outside the browser).
    """
    page = _get_page()
    if page and not page.is_closed():
        # In-browser DOM click via Playwright
        try:
            page.get_by_text(texto, exact=False).first.click(timeout=5000)
            time.sleep(0.5)
            return f"Click en '{texto}', Señor."
        except Exception as e:
            # Browser locator failed — fall through to vision click
            print(f"[Browser] DOM click falló para '{texto}': {e} → intentando click visual")

    # Vision-based coordinate click (desktop / fallback)
    return _vision_click(texto)


def llenar_campo(selector_hint: str, valor: str) -> str:
    """Busca un input y escribe el valor."""
    page = _get_page()
    if not page:
        return "Browser no disponible, Señor."
    try:
        # Intentar placeholder, label, o aria-label
        loc = (page.get_by_placeholder(selector_hint, exact=False)
               .or_(page.get_by_label(selector_hint, exact=False))).first
        loc.fill(valor, timeout=5000)
        return f"Escribí '{valor}' en el campo '{selector_hint}', Señor."
    except Exception as e:
        return f"No pude escribir en el campo: {e}"


# ── Skills de voz ─────────────────────────────────────────────────────────────

def skill_abrir_url(text: str) -> str:
    """Skill: abre una URL o sitio web."""
    # Extraer URL del texto
    url_match = re.search(r'((?:https?://)?[\w\-]+(?:\.[\w\-]+)+(?:/\S*)?)', text)
    if url_match:
        return navegar(url_match.group(1))
    # Intentar interpretar el nombre del sitio
    sitios = {
        "google": "google.com", "youtube": "youtube.com",
        "gmail": "mail.google.com", "github": "github.com",
        "twitter": "twitter.com", "x": "x.com",
        "linkedin": "linkedin.com", "instagram": "instagram.com",
    }
    lower = text.lower()
    for nombre, url in sitios.items():
        if nombre in lower:
            return navegar(url)
    return "No entendí qué sitio abrir, Señor. Decí por ejemplo 'abre google.com'."


def skill_buscar_web(text: str) -> str:
    """Skill: busca algo en Google usando el browser."""
    # Extraer query
    query = re.sub(r'^.*?(?:busca|buscá|googleá|investiga)\s+(?:en\s+(?:la\s+web|internet|google)\s+)?', '', text, flags=re.I).strip()
    if not query:
        return "¿Qué quiere que busque, Señor?"
    return buscar_google(query)


def skill_leer_pagina(text: str = "") -> str:
    """Skill: lee el contenido de la página actual."""
    return leer_pagina()


def skill_capturar_web(text: str = "") -> str:
    """Skill: captura screenshot de la página actual."""
    return capturar_pantalla()


def skill_cerrar_browser(text: str = "") -> str:
    """Skill: cierra el browser."""
    close_browser()
    return "Browser cerrado, Señor."


def skill_hacer_click_voz(text: str) -> str:
    """Skill: clickea en un elemento por texto."""
    target = re.sub(r'^.*?(?:click|clickeá|presioná|tocá)\s+(?:en\s+)?(?:el\s+|la\s+|los\s+|las\s+)?(?:botón\s+|enlace\s+|link\s+)?', '', text, flags=re.I).strip().strip('"\'')
    if not target:
        return "¿En qué quiere que haga click, Señor?"
    return hacer_click(target)


# ── Test ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Test browser Nova...")
    print(navegar("example.com"))
    print(leer_pagina(500))
    close_browser()
