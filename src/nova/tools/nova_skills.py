"""
nova_skills.py
────────────────
Todas las habilidades/skills de NOVA.

Categorías:
  1. Sistema  — abrir apps, ejecutar comandos, listar procesos, screenshot, volumen
  2. Archivos — listar, buscar, abrir, leer, crear y editar archivos/código
  3. Web      — búsqueda DuckDuckGo con resultados reales
  4. Tiempo   — hora, fecha, temporizadores
  5. Memoria  — recordar / olvidar (delega a nova_memory)
  6. n8n      — gastos, calendario, eventos, archivos (via webhooks de n8n)
  7. Dispatcher — detecta intención y ejecuta el skill adecuado
"""

from __future__ import annotations

import os
import re
import glob
import logging
import subprocess
from pathlib import Path
import datetime
import threading

log = logging.getLogger(__name__)

# Dependencias opcionales
try:
    from ddgs import DDGS
    _HAS_DDG = True
except ImportError:
    _HAS_DDG = False

import nova.core.nova_memory as mem
import pyautogui
# PyAutoGUI safety: mover el mouse a la esquina superior izquierda detiene el script
pyautogui.FAILSAFE = True

# n8n integration (importación diferida para no fallar si falta config)
try:
    from nova.connectors import nova_n8n as n8n
    _HAS_N8N = True
except ImportError:
    _HAS_N8N = False

# Google directo (sin n8n)
try:
    from nova.connectors import nova_google as _goog
    _HAS_GOOGLE = True
except Exception:
    _HAS_GOOGLE = False

# Generación de imágenes
try:
    from nova.connectors.nova_image import generar_imagen as _generar_imagen, abrir_imagen as _abrir_imagen
    _HAS_IMAGE = True
except Exception:
    _HAS_IMAGE = False

# Visión + Gestos
try:
    from nova.connectors.nova_vision import (
        vision_analizar as _vision_analizar,
        vision_analizar_archivo as _vision_analizar_archivo,
        vision_identificar_objeto as _vision_identificar_objeto,
        vision_para_cad as _vision_para_cad,
        iniciar_detector as _iniciar_detector,
        detener_detector as _detener_detector,
        estado_detector as _estado_detector,
        crear_callback_nova as _crear_callback_nova,
    )
    _HAS_VISION = True
except Exception:
    _HAS_VISION = False

# Subagentes / orquestador
try:
    from nova.connectors.nova_subagents import (
        orquestar as _orquestar,
        _detectar_orquestacion,
        analizar_archivo as _analizar_archivo,
        analizar_archivos as _analizar_archivos,
        analizar_repo as _analizar_repo,
        descomponer_y_ejecutar as _descomponer_y_ejecutar,
    )
    _HAS_SUBAGENTS = True
except Exception:
    _HAS_SUBAGENTS = False

# Blender 3D
try:
    from nova.connectors.nova_blender import (
        generar_objeto_desde_descripcion as _blender_generar,
        ejecutar_en_blender as _blender_ejecutar,
        abrir_blender as _blender_abrir,
        estado_blender as _blender_estado,
        generar_desde_vision_cad as _blender_desde_vision,
        aprobar_ultimo_script as _blender_aprobar,
    )
    _HAS_BLENDER = True
except Exception:
    _HAS_BLENDER = False

# Nova GitHub
try:
    from nova_github import (
        skill_github_repos as _skill_github_repos,
        skill_github_repo_info as _skill_github_repo_info,
        skill_github_issues as _skill_github_issues,
        skill_github_prs as _skill_github_prs,
        skill_github_commits as _skill_github_commits,
        skill_github_crear_issue as _skill_github_crear_issue,
        estado_github as _estado_github,
    )
    _HAS_GITHUB = True
except ImportError:
    _HAS_GITHUB = False

# Nova Browser (Playwright)
try:
    from nova_browser import (
        skill_abrir_url as _skill_abrir_url,
        skill_buscar_web as _skill_buscar_web_browser,
        skill_leer_pagina as _skill_leer_pagina,
        skill_capturar_web as _skill_capturar_web,
        skill_cerrar_browser as _skill_cerrar_browser,
        skill_hacer_click_voz as _skill_hacer_click_voz,
    )
    _HAS_BROWSER = True
except ImportError:
    _HAS_BROWSER = False

# Nova components integration
try:
    from nova.core.nova_router import NovaRouter
    from nova.tools.nova_neuro_memory import neuro_memory
    _NOVA_COMPONENTS_AVAILABLE = True
except ImportError:
    _NOVA_COMPONENTS_AVAILABLE = False

# Cerebro / Obsidian
try:
    from nova.connectors.nova_cerebro import (
        cerebro_buscar as _cerebro_buscar,
        cerebro_leer as _cerebro_leer,
        cerebro_escribir as _cerebro_escribir,
        cerebro_listar as _cerebro_listar,
        cerebro_nueva_nota as _cerebro_nueva_nota,
        cerebro_estado as _cerebro_estado,
    )
    _HAS_CEREBRO = True
except Exception:
    _HAS_CEREBRO = False

# Nova Enhanced (opcional)
try:
    from nova_integracion import (
        skill_set_timer as _enh_skill_set_timer,
        skill_set_alarm as _enh_skill_set_alarm,
        skill_see_screen as _enh_skill_see_screen,
        skill_move_mouse as _enh_skill_move_mouse,
        skill_click as _enh_skill_click,
        skill_design_app as _enh_skill_design_app,
        get_nova_enhanced as _get_nova_enhanced,
    )
    _HAS_NOVA_ENHANCED = True
except ImportError:
    _HAS_NOVA_ENHANCED = False


# ══════════════════════════════════════════════════════════════
# 1. SISTEMA
# ══════════════════════════════════════════════════════════════

def _app_paths() -> list[str]:
    paths = (
        glob.glob("/Applications/*.app")
        + glob.glob("/Applications/**/*.app")
        + glob.glob(os.path.expanduser("~/Applications/*.app"))
        + glob.glob("/System/Applications/*.app")
    )
    return sorted(set(paths))


def get_installed_apps() -> list[str]:
    from nova.platform import find_installed_apps, PLATFORM
    if PLATFORM != "macos":
        return find_installed_apps()
    return sorted(
        set(os.path.basename(p).replace(".app", "") for p in _app_paths())
    )


# Aliases de nombres en español → nombre real de la app
_OPEN_APP_ALIASES: dict[str, str] = {
    "música": "Music", "musica": "Music", "apple music": "Music",
    "fotos": "Photos", "notas": "Notes",
    "calendario": "Calendar", "recordatorios": "Reminders",
    "mensajes": "Messages", "correo": "Mail",
    "configuración": "System Settings", "preferencias": "System Settings",
    "finder": "Finder", "terminal": "Terminal",
    "chrome": "Google Chrome", "google chrome": "Google Chrome",
    "navegador": "Google Chrome", "el navegador": "Google Chrome",
    "internet": "Google Chrome",
    "excel": "Microsoft Excel", "word": "Microsoft Word",
    "powerpoint": "Microsoft PowerPoint",
    "vscode": "Visual Studio Code", "code": "Visual Studio Code",
    "blender": "Blender",
}

def open_app(app_name: str) -> str:
    """Abre una aplicación por nombre o alias"""
    from nova.platform import open_application
    import unicodedata
    app_name = app_name.strip().rstrip(" ,.:")

    # Separar comandos compuestos: "Chrome y busca YouTube" → abrir Chrome + acción
    _compound = re.search(
        r'\s+y\s+(busca[r]?|navega[r]?|ve\s+a|entr[aá]\s+a|abr[ií]\s+|ir\s+a'
        r'|nuevo\s+(?:archivo|documento|doc)|archivo\s+nuevo|documento\s+nuevo'
        r'|crea[r]?\s+(?:un\s+)?(?:archivo|documento|doc)(?:\s+nuevo)?)\s*(.*)$',
        app_name, re.IGNORECASE
    )
    _pending_action: str | None = None
    if _compound:
        # Extraer solo la acción (sin el " y " inicial): "y navega a X" → "navega a X"
        raw_pending = app_name[_compound.start():].strip()
        _pending_action = re.sub(r"^\s*y\s+", "", raw_pending, flags=re.IGNORECASE).strip()
        app_name = app_name[:_compound.start()].strip()
    # Alias en español
    alias = _OPEN_APP_ALIASES.get(app_name.lower())
    if alias:
        app_name = alias
    # Intento directo
    if open_application(app_name):
        result = f"Abriendo {app_name}, Señor."
        if _pending_action:
            import time as _t; _t.sleep(1.5)
            # Caso especial: "nuevo documento/archivo" en la app recién abierta
            if re.search(r"nuevo\s*(?:archivo|documento|doc)|archivo\s*nuevo|documento\s*nuevo"
                         r"|crea[r]?\s+(?:un\s+)?(?:archivo|documento|doc)", _pending_action, re.I):
                action_result = new_document_in_app(app_name)
            else:
                action_result = dispatch(_pending_action)
            result += f" {action_result}" if action_result else ""
        return result.strip()
    # Fuzzy match (case-insensitive, sin acentos)
    apps = get_installed_apps()
    needle = app_name.lower()
    matches = [a for a in apps if needle in a.lower()]
    if not matches:
        needle_n = unicodedata.normalize("NFD", needle).encode("ascii", "ignore").decode()
        matches = [a for a in apps
                   if needle_n in unicodedata.normalize("NFD", a.lower()).encode("ascii", "ignore").decode()]
    if matches:
        open_application(matches[0])
        result = f"Abriendo {matches[0]}, Señor."
        if _pending_action:
            import time as _t; _t.sleep(1.5)
            if re.search(r"nuevo\s*(?:archivo|documento|doc)|archivo\s*nuevo|documento\s*nuevo"
                         r"|crea[r]?\s+(?:un\s+)?(?:archivo|documento|doc)", _pending_action, re.I):
                action_result = new_document_in_app(matches[0])
            else:
                action_result = dispatch(_pending_action)
            result += f" {action_result}" if action_result else ""
        return result
    return (
        f"No encontré ninguna aplicación con el nombre '{app_name}', Señor. "
        f"¿Quizás quisiste decir alguna de estas? {', '.join(apps[:8])}"
    )


def close_app(app_name: str) -> str:
    from nova.platform import close_application
    if close_application(app_name):
        return f"Cerré {app_name}, Señor."
    return f"No pude cerrar '{app_name}', Señor."


def list_apps() -> str:
    apps = get_installed_apps()
    return "Aplicaciones instaladas:\n" + ", ".join(apps)


def run_command(command: str) -> str:
    """Ejecuta un comando de terminal y devuelve el resultado."""
    command = command.strip()
    try:
        r = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=os.path.expanduser("~"),
        )
        output = (r.stdout or r.stderr or "(sin salida)").strip()
        # Limitar a 600 chars para no saturar el TTS
        if len(output) > 600:
            output = output[:600] + "\n... (salida truncada)"
        return output
    except subprocess.TimeoutExpired:
        return "El comando tardó demasiado y lo cancelé, Señor."
    except Exception as e:
        return f"Error ejecutando el comando: {e}"


def take_screenshot() -> str:
    from nova.platform import take_screenshot as _plat_screenshot
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.expanduser(f"~/Desktop/nova_{ts}.png")
    if _plat_screenshot(path):
        return f"Captura guardada en: {path}"
    return "Error al tomar la captura de pantalla, Señor."


def get_volume() -> str:
    """Obtiene el volumen actual del sistema"""
    from nova.platform import get_system_volume
    vol = get_system_volume()
    if vol is not None:
        return f"El volumen está al {vol}%, Señor."
    return "No pude obtener el volumen del sistema, Señor."


def get_weather(location: str = "Buenos Aires") -> str:
    """Obtiene el clima actual para una ubicación específica usando un servicio conciso"""
    try:
        # Primero intentar con wttr.in que da información concisa
        import urllib.request
        import urllib.parse
        
        # Codificar la ubicación para la URL
        encoded_location = urllib.parse.quote(location)
        # Formato más detallado: ubicación: condición +temperatura ←viento humedad precipitación
        url = f"https://wttr.in/{encoded_location}?format=%l:+%C+%t+%w+%h+%p"
        
        req = urllib.request.Request(url, headers={'User-Agent': 'curl/7.68.0'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            weather_info = resp.read().decode().strip()
            
        # wttr.in retorna formato: "location: +condition temperature ←wind humidity precipitation"
        if weather_info and ':' in weather_info:
            # Traducir al español básico
            condition_map = {
                'Sunny': 'soleado',
                'Clear': 'despejado',
                'Partly cloudy': 'parcialmente nublado',
                'Cloudy': 'nublado',
                'Overcast': 'encubierto',
                'Mist': 'neblina',
                'Patchy rain possible': 'lluvia posible',
                'Patchy snow possible': 'nieve posible',
                'Patchy sleet possible': 'aguanieve posible',
                'Patchy freezing drizzle possible': 'llovizna helada posible',
                'Thundery outbreaks possible': 'tormentas posibles',
                'Blizzard': 'ventisca',
                'Fog': 'niebla',
                'Freezing fog': 'niebla helada',
                'Patchy light drizzle': 'llovizna ligera',
                'Light drizzle': 'llovizna ligera',
                'Freezing drizzle': 'llovizna helada',
                'Heavy freezing drizzle': 'llovizna helada intensa',
                'Light rain': 'lluvia ligera',
                'Moderate rain at times': 'lluvia moderada ocasional',
                'Moderate rain': 'lluvia moderada',
                'Heavy rain at times': 'lluvia intensa ocasional',
                'Heavy rain': 'lluvia intensa',
                'Light freezing rain': 'lluvia helada ligera',
                'Moderate or heavy freezing rain': 'lluvia helada moderada o intensa',
                'Light rain shower': 'chubasco de lluvia ligera',
                'Moderate or heavy rain shower': 'chubasco de lluvia moderado o intenso',
                'Torrential rain shower': 'chubasco de lluvia torrencial',
                'Light sleet': 'aguanieve ligera',
                'Moderate or heavy sleet': 'aguanieve moderado o intenso',
                'Light snow': 'nieve ligera',
                'Moderate snow': 'nieve moderada',
                'Heavy snow': 'nieve intensa',
                'Ice pellets': 'granizo',
                'Light rain shower': 'chubasco de lluvia ligera',
                'Moderate or heavy rain shower': 'chubasco de lluvia moderado o intenso',
                'Torrential rain shower': 'chubasco de lluvia torrencial',
                'Light snow showers': 'chubascos de nieve ligeros',
                'Moderate or heavy snow showers': 'chubascos de nieve moderados o intensos',
                'Light showers of ice pellets': 'chubascos de granizo ligeros',
                'Moderate or heavy showers of ice pellets': 'chubascos de granizo moderados o intensos',
                'Patchy light rain with thunder': 'lluvia ligera con tormentas',
                'Moderate or heavy rain with thunder': 'lluvia moderada o intensa con tormentas',
                'Patchy light snow with thunder': 'nieve ligera con tormentas',
                'Moderate or heavy snow with thunder': 'nieve moderada o intensa con tormentas',
                'Thunder': 'trueno'
            }
            
            # Separar los componentes
            parts = weather_info.split(': ')
            if len(parts) >= 2:
                location_part = parts[0]
                weather_part = parts[1]
                
                # Traducir condición
                translated_parts = []
                for eng, esp in condition_map.items():
                    if eng in weather_part:
                        weather_part = weather_part.replace(eng, esp)
                        break
                
                # Formatear en español
                result = f"{location_part}: {weather_part}"
                # Limpiar símbolos especiales
                result = result.replace('←', ' viento ').replace('+', '').replace('mm', ' mm de precipitación')
                return result
            else:
                return weather_info
        else:
            # Si wttr.in falla, usar web_search como fallback
            search_results = web_search(f"clima hoy {location} temperatura ahora", max_results=1)
            return search_results
    except Exception as e:
        # Si todo falla, intentar con un enfoque más simple
        try:
            search_results = web_search(f"clima {location} ahora", max_results=1)
            return search_results
        except:
            return f"No pude obtener el clima para {location}, Señor."


def get_forecast(location: str = "Buenos Aires", days: int = 3) -> str:
    """Pronóstico extendido usando Open-Meteo (gratis, sin API key)."""
    try:
        import urllib.request, urllib.parse, json
        geo_url = f"https://nominatim.openstreetmap.org/search?q={urllib.parse.quote(location)}&format=json&limit=1"
        req = urllib.request.Request(geo_url, headers={"User-Agent": "Nova-Assistant/3.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            geo = json.loads(r.read())[0]
        lat, lon = geo["lat"], geo["lon"]

        params = urllib.parse.urlencode({
            "latitude": lat, "longitude": lon,
            "daily": "weathercode,temperature_2m_max,temperature_2m_min,precipitation_sum,windspeed_10m_max",
            "timezone": "America/Argentina/Buenos_Aires",
            "forecast_days": days,
        })
        fc_url = f"https://api.open-meteo.com/v1/forecast?{params}"
        with urllib.request.urlopen(fc_url, timeout=8) as r:
            data = json.loads(r.read())

        wmo = {0:"despejado",1:"mayormente despejado",2:"parcialmente nublado",3:"nublado",
               45:"neblina",48:"neblina helada",51:"llovizna ligera",53:"llovizna moderada",
               55:"llovizna intensa",61:"lluvia ligera",63:"lluvia moderada",65:"lluvia intensa",
               71:"nieve ligera",73:"nieve moderada",75:"nieve intensa",
               80:"chubascos",81:"chubascos moderados",82:"chubascos intensos",
               95:"tormenta",96:"tormenta con granizo",99:"tormenta con granizo intenso"}

        daily = data["daily"]
        lines = [f"Pronóstico {days} días para {location}:"]
        for i in range(min(days, len(daily["time"]))):
            fecha = daily["time"][i]
            code  = daily["weathercode"][i]
            tmax  = daily["temperature_2m_max"][i]
            tmin  = daily["temperature_2m_min"][i]
            prec  = daily["precipitation_sum"][i]
            wind  = daily["windspeed_10m_max"][i]
            cond  = wmo.get(code, f"código {code}")
            lines.append(f"  {fecha}: {cond}, {tmin}°–{tmax}°C, lluvia {prec}mm, viento {wind}km/h")
        return "\n".join(lines)
    except Exception as e:
        return f"No pude obtener el pronóstico para {location}: {e}"


def set_volume(level: int) -> str:
    from nova.platform import set_system_volume
    level = max(0, min(100, level))
    set_system_volume(level)
    return f"Volumen ajustado a {level}%, Señor."


def mute_volume() -> str:
    from nova.platform import mute_system
    mute_system()
    return "Audio silenciado, Señor."


def unmute_volume() -> str:
    from nova.platform import unmute_system
    unmute_system()
    return "Audio activado, Señor."


def get_battery() -> str:
    r = subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True)
    lines = r.stdout.strip().splitlines()
    for line in lines:
        if "%" in line:
            return f"Batería: {line.strip()}"
    return "No pude obtener el estado de la batería, Señor."


def get_running_apps() -> str:
    r = subprocess.run(
        ["osascript", "-e",
         'tell application "System Events" to get name of (processes where background only is false)'],
        capture_output=True, text=True,
    )
    apps = r.stdout.strip()
    return f"Aplicaciones activas: {apps}"


def get_active_window_context() -> str:
    """Detecta qué aplicación y ventana tiene el foco actual."""
    script = (
        'tell application "System Events" to tell (first application process whose frontmost is true) '
        'to return {name, name of window 1}'
    )
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if r.returncode == 0:
        parts = r.stdout.strip().split(", ")
        app = parts[0] if len(parts) > 0 else "Desconocida"
        win = parts[1] if len(parts) > 1 else "Escritorio"
        return f"En este momento estás operando en {app}, específicamente en la ventana '{win}', Señor."
    return "No pude identificar la aplicación activa en este momento, Señor."

def lock_screen() -> str:
    subprocess.run([
        "osascript", "-e",
        'tell application "System Events" to keystroke "q" using {control down, command down}'
    ])
    return "Bloqueando pantalla, Señor."


# ══════════════════════════════════════════════════════════════
# 1e. SKILLS WEB — Traducción, Crypto, Forex, Feriados
# ══════════════════════════════════════════════════════════════

def skill_traducir(texto: str) -> str:
    """
    Traduce texto usando MyMemory API (gratuita, sin key, 5000 palabras/día).
    Formato: 'traduce [texto] al [idioma]' o 'cómo se dice [texto] en [idioma]'
    """
    import urllib.request, urllib.parse, json as _json

    # Detectar idioma destino
    _LANG_MAP = {
        "inglés": "en", "ingles": "en", "english": "en",
        "francés": "fr", "frances": "fr", "french": "fr",
        "alemán": "de", "aleman": "de", "german": "de",
        "italiano": "it", "italian": "it",
        "portugués": "pt", "portugues": "pt",
        "chino": "zh", "chinese": "zh",
        "japonés": "ja", "japones": "ja",
        "árabe": "ar", "arabe": "ar",
        "ruso": "ru", "russian": "ru",
        "español": "es", "spanish": "es",
    }
    target_lang = "en"  # default
    texto_limpio = texto.strip()
    for kw, code in _LANG_MAP.items():
        if kw in texto_limpio.lower():
            target_lang = code
            # Limpiar el idioma del texto a traducir
            texto_limpio = re.sub(
                rf"\s*(?:al?|en)\s+{re.escape(kw)}\s*$", "", texto_limpio,
                flags=re.I
            ).strip()
            break
    # Limpiar prefijos de comando
    texto_limpio = re.sub(
        r"^(?:traduc[ei]r?|cómo\s+se\s+dice|como\s+se\s+dice|qué\s+significa|que\s+significa)\s+",
        "", texto_limpio, flags=re.I
    ).strip().strip('"\'')

    if not texto_limpio:
        return "Indicá el texto a traducir, Señor."

    try:
        params = urllib.parse.urlencode({
            "q": texto_limpio,
            "langpair": f"es|{target_lang}",
        })
        url = f"https://api.mymemory.translated.net/get?{params}"
        req = urllib.request.Request(url, headers={"User-Agent": "Nova/2.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            data = _json.loads(r.read().decode())
        translation = data["responseData"]["translatedText"]
        return f'"{texto_limpio}" en {target_lang.upper()}: {translation}'
    except Exception as e:
        return f"No pude traducir en este momento, Señor. ({e})"


def skill_crypto(texto: str) -> str:
    """
    Precios de criptomonedas en tiempo real via CoinGecko (sin API key).
    Ej: 'precio de bitcoin', 'cuánto vale ethereum', 'crypto btc'
    """
    import urllib.request, json as _json

    _COIN_MAP = {
        "bitcoin": "bitcoin", "btc": "bitcoin",
        "ethereum": "ethereum", "eth": "ethereum",
        "solana": "solana", "sol": "solana",
        "cardano": "cardano", "ada": "cardano",
        "dogecoin": "dogecoin", "doge": "dogecoin",
        "polkadot": "polkadot", "dot": "polkadot",
        "chainlink": "chainlink", "link": "chainlink",
        "litecoin": "litecoin", "ltc": "litecoin",
        "ripple": "ripple", "xrp": "ripple",
        "bnb": "binancecoin", "binance": "binancecoin",
        "usdt": "tether", "tether": "tether",
        "usdc": "usd-coin",
        "avax": "avalanche-2", "avalanche": "avalanche-2",
        "matic": "matic-network", "polygon": "matic-network",
    }

    low = texto.lower()
    coin_id = None
    for alias, cid in _COIN_MAP.items():
        if alias in low:
            coin_id = cid
            break

    if not coin_id:
        # Intentar buscar el nombre directamente
        name = re.sub(
            r"^(?:precio\s+de|cuánto\s+vale|cuanto\s+vale|crypto|cripto)\s+",
            "", low, flags=re.I
        ).strip()
        coin_id = name if name else "bitcoin"

    try:
        url = (
            f"https://api.coingecko.com/api/v3/simple/price"
            f"?ids={coin_id}&vs_currencies=usd,ars&include_24hr_change=true"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "Nova/2.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            data = _json.loads(r.read().decode())
        if coin_id not in data:
            return f"No encontré información para '{coin_id}', Señor."
        info = data[coin_id]
        usd   = info.get("usd", 0)
        ars   = info.get("ars", 0)
        chg   = info.get("usd_24h_change", 0)
        arrow = "↑" if chg >= 0 else "↓"
        return (
            f"{coin_id.title()}: USD ${usd:,.2f} | ARS ${ars:,.0f} | "
            f"{arrow} {abs(chg):.2f}% (24hs)"
        )
    except Exception as e:
        return f"No pude obtener el precio de {coin_id}, Señor. ({e})"


def skill_forex(texto: str) -> str:
    """
    Tipo de cambio entre divisas via Frankfurter API (ECB, sin key).
    Ej: 'cuánto son 100 dólares en euros', 'tipo de cambio EUR USD'
    """
    import urllib.request, json as _json

    _CURRENCY_NAMES = {
        "dólar": "USD", "dolar": "USD", "usd": "USD", "dollar": "USD",
        "euro": "EUR", "eur": "EUR",
        "libra": "GBP", "gbp": "GBP",
        "yen": "JPY", "jpy": "JPY",
        "franco": "CHF", "chf": "CHF",
        "real": "BRL", "brl": "BRL",
        "peso argentino": "ARS", "ars": "ARS",
        "peso mexicano": "MXN", "mxn": "MXN",
        "yuan": "CNY", "cny": "CNY",
        "rublo": "RUB", "rub": "RUB",
    }

    low = texto.lower()
    # Detectar monto
    amount_m = re.search(r"(\d+(?:[.,]\d+)?)", low)
    amount = float(amount_m.group(1).replace(",", ".")) if amount_m else 1.0

    # Detectar monedas
    found = []
    for name, code in _CURRENCY_NAMES.items():
        if name in low and code not in found:
            found.append(code)
        if len(found) == 2:
            break

    base = found[0] if found else "USD"
    target = found[1] if len(found) > 1 else "EUR"

    try:
        url = f"https://api.frankfurter.app/latest?base={base}&symbols={target}"
        req = urllib.request.Request(url, headers={"User-Agent": "Nova/2.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            data = _json.loads(r.read().decode())
        rate = data["rates"].get(target)
        if rate is None:
            return f"No encontré la tasa {base}/{target}, Señor."
        result = amount * rate
        return f"{amount:,.2f} {base} = {result:,.4f} {target} (tasa: {rate})"
    except Exception as e:
        return f"No pude obtener el tipo de cambio, Señor. ({e})"


def skill_feriados(texto: str) -> str:
    """
    Lista feriados nacionales via Nager.Date API (sin key).
    Ej: 'feriados de argentina', 'próximos feriados'
    """
    import urllib.request, json as _json
    from datetime import date

    _COUNTRY_MAP = {
        "argentina": "AR", "ar": "AR",
        "españa": "ES", "spain": "ES", "es": "ES",
        "mexico": "MX", "méxico": "MX", "mx": "MX",
        "estados unidos": "US", "eeuu": "US", "usa": "US", "us": "US",
        "brasil": "BR", "brazil": "BR", "br": "BR",
        "chile": "CL", "cl": "CL",
        "colombia": "CO", "co": "CO",
        "uruguay": "UY", "uy": "UY",
    }

    low = texto.lower()
    country = "AR"  # default Argentina
    for name, code in _COUNTRY_MAP.items():
        if name in low:
            country = code
            break

    year = date.today().year
    year_m = re.search(r"\b(20\d{2})\b", low)
    if year_m:
        year = int(year_m.group(1))

    try:
        url = f"https://date.nager.at/api/v3/PublicHolidays/{year}/{country}"
        req = urllib.request.Request(url, headers={"User-Agent": "Nova/2.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            holidays = _json.loads(r.read().decode())

        today = date.today()
        upcoming = [
            h for h in holidays
            if date.fromisoformat(h["date"]) >= today
        ][:6]

        if not upcoming:
            return f"No hay feriados próximos en {country} para {year}, Señor."

        lines = [f"Próximos feriados {country} {year}:"]
        for h in upcoming:
            lines.append(f"  {h['date']} — {h['localName']}")
        return "\n".join(lines)
    except Exception as e:
        return f"No pude obtener los feriados, Señor. ({e})"


# ══════════════════════════════════════════════════════════════
# 1f. AUTOMATIZACIÓN DE MOUSE Y TECLADO (PyAutoGUI)
# ══════════════════════════════════════════════════════════════

def mouse_move(x: int, y: int) -> str:
    """Mueve el mouse a coordenadas específicas."""
    pyautogui.moveTo(x, y, duration=0.25)
    return f"Mouse movido a {x}, {y}, Señor."

def mouse_click(x: int | None = None, y: int | None = None, clicks: int = 1) -> str:
    """Hace click en la posición actual o en una específica."""
    if x is not None and y is not None:
        pyautogui.click(x, y, clicks=clicks)
        return f"Click realizado en {x}, {y}, Señor."
    pyautogui.click(clicks=clicks)
    return "Click realizado, Señor."

def mouse_scroll(amount: int) -> str:
    """Scroll vertical."""
    pyautogui.scroll(amount)
    return "Scroll realizado, Señor."

def type_text(text: str) -> str:
    """Escribe texto simulando pulsaciones de teclas."""
    pyautogui.write(text, interval=0.05)
    return "Texto escrito, Señor."

def press_key(key: str) -> str:
    """Presiona una tecla especial (enter, tab, esc, etc)."""
    pyautogui.press(key)
    return f"Tecla {key} presionada, Señor."

def get_mouse_pos() -> str:
    """Devuelve la posición actual del mouse."""
    x, y = pyautogui.position()
    return f"El mouse está en x={x}, y={y}, Señor."


# ══════════════════════════════════════════════════════════════
# 1b. MÚSICA — Apple Music / Spotify
# ══════════════════════════════════════════════════════════════

def _osascript(script: str) -> tuple[int, str]:
    """Ejecuta AppleScript y devuelve (returncode, stdout)."""
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    return r.returncode, (r.stdout or r.stderr or "").strip()


def music_play() -> str:
    rc, _ = _osascript('tell application "Music" to play')
    if rc == 0:
        return "Reproduciendo música, Señor."
    return "No pude iniciar la música. ¿Está abierta la app Música?"


def music_pause() -> str:
    rc, _ = _osascript('tell application "Music" to pause')
    return "Música pausada, Señor." if rc == 0 else "No pude pausar la música, Señor."


def music_next() -> str:
    rc, _ = _osascript('tell application "Music" to next track')
    return "Siguiente canción, Señor." if rc == 0 else "No pude cambiar la canción, Señor."


def music_prev() -> str:
    rc, _ = _osascript('tell application "Music" to previous track')
    return "Canción anterior, Señor." if rc == 0 else "No pude ir a la canción anterior, Señor."


def music_current_track() -> str:
    script = (
        'tell application "Music"\n'
        '  if player state is playing then\n'
        '    return (name of current track) & " — " & (artist of current track)\n'
        '  else if player state is paused then\n'
        '    return "Pausado: " & (name of current track) & " — " & (artist of current track)\n'
        '  else\n'
        '    return "Sin reproducción activa"\n'
        '  end if\n'
        'end tell'
    )
    rc, out = _osascript(script)
    if rc == 0 and out:
        return f"Suena: {out}, Señor."
    return "No hay música sonando en este momento, Señor."


def music_play_query(query: str) -> str:
    """Busca y reproduce una canción o artista en Apple Music."""
    safe_q = query.replace('"', "'")
    # Intenta por nombre de canción primero
    script_name = (
        'tell application "Music"\n'
        '  activate\n'
        f'  set found to (every track of library playlist 1 whose name contains "{safe_q}")\n'
        '  if length of found > 0 then\n'
        '    play item 1 of found\n'
        '    return "ok:" & (name of item 1 of found) & " — " & (artist of item 1 of found)\n'
        '  else\n'
        '    return "notfound"\n'
        '  end if\n'
        'end tell'
    )
    rc, out = _osascript(script_name)
    if rc == 0 and out.startswith("ok:"):
        info = out[3:]
        return f"Reproduciendo {info}, Señor."
    # Busca por artista
    script_artist = (
        'tell application "Music"\n'
        '  activate\n'
        f'  set found to (every track of library playlist 1 whose artist contains "{safe_q}")\n'
        '  if length of found > 0 then\n'
        '    play item 1 of found\n'
        '    return "ok:" & (artist of item 1 of found)\n'
        '  else\n'
        '    return "notfound"\n'
        '  end if\n'
        'end tell'
    )
    rc2, out2 = _osascript(script_artist)
    if rc2 == 0 and out2.startswith("ok:"):
        return f"Reproduciendo música de {out2[3:]}, Señor."
    return (
        f"No encontré '{query}' en tu biblioteca, Señor. "
        "Asegúrate de que Apple Música esté abierta y la canción en tu biblioteca."
    )


def music_volume(level: int) -> str:
    level = max(0, min(100, level))
    rc, _ = _osascript(f'tell application "Music" to set sound volume to {level}')
    return f"Volumen de música al {level}%, Señor." if rc == 0 else "No pude ajustar el volumen de música, Señor."


def music_shuffle_on() -> str:
    rc, _ = _osascript('tell application "Music" to set shuffle enabled to true')
    return "Modo aleatorio activado, Señor." if rc == 0 else "No pude activar el modo aleatorio, Señor."


def music_shuffle_off() -> str:
    rc, _ = _osascript('tell application "Music" to set shuffle enabled to false')
    return "Modo aleatorio desactivado, Señor." if rc == 0 else "No pude desactivar el modo aleatorio, Señor."


# ══════════════════════════════════════════════════════════════
# 1c. NOTAS — Apple Notes
# ══════════════════════════════════════════════════════════════

def notes_create(title: str, body: str = "") -> str:
    """Crea una nueva nota en Apple Notes con título y cuerpo opcionales."""
    safe_title = title.replace('"', "'").replace('\\', '\\\\')
    safe_body  = body.replace('"', "'").replace('\\', '\\\\')
    script = (
        'tell application "Notes"\n'
        '  activate\n'
        f'  set newNote to make new note at default account with properties '
        f'{{name:"{safe_title}", body:"{safe_title}\\n\\n{safe_body}"}}\n'
        '  return "ok"\n'
        'end tell'
    )
    rc, out = _osascript(script)
    if rc == 0:
        return f"Nota '{title}' creada en Apple Notas, Señor."
    return f"No pude crear la nota: {out}"


def notes_append(keyword: str, content: str) -> str:
    """Añade contenido a la primera nota que contenga 'keyword' en el título."""
    safe_kw   = keyword.replace('"', "'")
    safe_body = content.replace('"', "'").replace('\\', '\\\\')
    script = (
        'tell application "Notes"\n'
        '  activate\n'
        f'  set found to (every note whose name contains "{safe_kw}")\n'
        '  if length of found > 0 then\n'
        '    set theNote to item 1 of found\n'
        '    set body of theNote to (body of theNote) & "\\n" & '
        f'"{safe_body}"\n'
        '    return "ok"\n'
        '  else\n'
        '    return "notfound"\n'
        '  end if\n'
        'end tell'
    )
    rc, out = _osascript(script)
    if rc == 0 and out == "ok":
        return f"Contenido añadido a la nota '{keyword}', Señor."
    if out == "notfound":
        return f"No encontré ninguna nota llamada '{keyword}'. ¿Quieres que cree una nueva?"
    return f"No pude actualizar la nota: {out}"


def notes_list() -> str:
    """Lista las últimas 10 notas."""
    script = (
        'tell application "Notes"\n'
        '  set allNotes to name of every note\n'
        '  set result to ""\n'
        '  repeat with i from 1 to (count allNotes)\n'
        '    if i > 10 then exit repeat\n'
        '    set result to result & item i of allNotes & "\\n"\n'
        '  end repeat\n'
        '  return result\n'
        'end tell'
    )
    rc, out = _osascript(script)
    if rc == 0 and out:
        return "Tus notas recientes:\n" + out.strip()
    return "No pude listar las notas, Señor."


# ══════════════════════════════════════════════════════════════
# 1d. DICTADO — Escribir texto en app activa o específica
# ══════════════════════════════════════════════════════════════

def _type_via_clipboard(text: str) -> None:
    """Pega texto usando el portapapeles (más rápido que keystroke por letra)."""
    from nova.platform import copy_to_clipboard, PLATFORM
    copy_to_clipboard(text)
    import time; time.sleep(0.15)
    if PLATFORM == "macos":
        _osascript('tell application "System Events" to keystroke "v" using command down')
    else:
        import pyautogui
        pyautogui.hotkey("ctrl", "v")


def type_in_active_app(text: str) -> str:
    """Escribe texto en la app que tenga el foco en este momento."""
    _type_via_clipboard(text)
    return f"Texto escrito, Señor."


def dictate_to_app(app_name: str, text: str) -> str:
    """Activa una app y escribe texto en ella."""
    safe_app = app_name.strip().strip('"')
    # Activar la app
    rc, _ = _osascript(f'tell application "{safe_app}" to activate')
    if rc != 0:
        # Intentar abrirla
        open_app(safe_app)
    import time; time.sleep(0.8)  # esperar a que tome el foco
    _type_via_clipboard(text)
    return f"Texto dictado en {safe_app}, Señor."


def pages_new_doc_with_text(text: str) -> str:
    """Crea un nuevo documento en Pages y escribe el texto dictado."""
    # Abrir Pages y crear documento nuevo
    script_open = (
        'tell application "Pages"\n'
        '  activate\n'
        '  make new document\n'
        'end tell'
    )
    rc, _ = _osascript(script_open)
    if rc != 0:
        return "No pude abrir Pages, Señor. ¿Está instalado?"
    import time; time.sleep(1.2)
    _type_via_clipboard(text)
    return f"Documento nuevo creado en Pages con tu texto, Señor."


def new_document_in_app(app_name: str) -> str:
    """Abre una app y crea un nuevo documento/ventana con Cmd+N."""
    _APP_ALIASES = {
        "word": "Microsoft Word", "microsoft word": "Microsoft Word",
        "excel": "Microsoft Excel", "microsoft excel": "Microsoft Excel",
        "powerpoint": "Microsoft PowerPoint", "ppt": "Microsoft PowerPoint",
        "pages": "Pages", "numbers": "Numbers", "keynote": "Keynote",
        "chrome": "Google Chrome", "google chrome": "Google Chrome",
        "safari": "Safari", "firefox": "Firefox",
        "finder": "Finder", "notes": "Notes", "notas": "Notes",
        "textedit": "TextEdit", "sublime": "Sublime Text",
        "vscode": "Visual Studio Code", "code": "Visual Studio Code",
        "autocad": "AutoCAD", "illustrator": "Adobe Illustrator",
        "photoshop": "Adobe Photoshop", "acrobat": "Adobe Acrobat",
    }
    matched = _APP_ALIASES.get(app_name.lower().strip())
    if not matched:
        # Búsqueda fuzzy
        for alias, real in _APP_ALIASES.items():
            if alias in app_name.lower():
                matched = real
                break
        if not matched:
            matched = app_name  # usar tal cual

    # Abrir la app y mandarle Cmd+N
    rc, _ = _osascript(f'tell application "{matched}" to activate')
    import time; time.sleep(2.0)
    _osascript(f'tell application "System Events" to tell process "{matched}" to keystroke "n" using command down')
    time.sleep(0.8)
    return f"Nuevo documento abierto en {matched}, Señor."


def word_new_doc_with_text(text: str) -> str:
    """Crea un nuevo documento en Word y escribe el texto dictado."""
    # Intentar via AppleScript nativo primero (más fiable que hotkey)
    script_open = (
        'tell application "Microsoft Word"\n'
        '  activate\n'
        '  set newDoc to make new document\n'
        '  tell newDoc\n'
        '    tell its text object to set content to ""\n'
        '  end tell\n'
        'end tell'
    )
    rc, _ = _osascript(script_open)
    if rc != 0:
        # Fallback: abrir Word y enviar Cmd+N con tiempo suficiente
        subprocess.run(["open", "-a", "Microsoft Word"])
        import time; time.sleep(3.0)
        rc2, _ = _osascript('tell application "Microsoft Word" to activate')
        import time; time.sleep(0.8)
        _osascript('tell application "System Events" to keystroke "n" using command down')
        import time; time.sleep(1.5)
        if rc2 != 0:
            return pages_new_doc_with_text(text)
    import time; time.sleep(1.5)
    _type_via_clipboard(text)
    return "Documento nuevo creado en Word con tu texto, Señor."


# ══════════════════════════════════════════════════════════════
# 2. ARCHIVOS
# ══════════════════════════════════════════════════════════════

def list_directory(path: str = "~") -> str:
    """Lista el contenido de un directorio"""
    path = os.path.expanduser(path)
    try:
        items = os.listdir(path)
        files = sorted(items)
        text = f"Contenido de {path}:\n" + "\n".join(f"  • {f}" for f in files[:30])
        if len(files) > 30:
            text += f"\n  ... y {len(files) - 30} archivos más."
        return text
    except Exception as e:
        return f"No pude listar '{path}': {e}"


def find_file(name: str, base: str = "~") -> str:
    base = os.path.expanduser(base)
    results = []
    for root, dirs, files in os.walk(base):
        # Skip hidden/system folders
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in
                   ("Library", "node_modules", "__pycache__")]
        for f in files:
            if name.lower() in f.lower():
                results.append(os.path.join(root, f))
        if len(results) >= 10:
            break
    if not results:
        return f"No encontré ningún archivo con '{name}', Señor."
    return "Archivos encontrados:\n" + "\n".join(f"  • {p}" for p in results[:10])


def open_file(path: str) -> str:
    path = os.path.expanduser(path)
    r = subprocess.run(["open", path], capture_output=True, text=True)
    if r.returncode == 0:
        return f"Abriendo {path}, Señor."
    return f"No pude abrir '{path}', Señor."


def _resolve_user_path(raw_path: str) -> str:
    clean = raw_path.strip().strip('"').strip("'")
    return os.path.abspath(os.path.expanduser(clean))


def _parse_path_and_content(payload: str) -> tuple[str | None, str]:
    """
    Formatos aceptados:
      - "ruta con contenido ..."
      - "'ruta con espacios.txt' con contenido ..."
      - "ruta: contenido ..."
    """
    data = payload.strip()
    if not data:
        return None, ""

    path = ""
    tail = ""
    if data[0] in {"'", '"'}:
        q = data[0]
        end = data.find(q, 1)
        if end > 0:
            path = data[1:end].strip()
            tail = data[end + 1 :].strip()
    if not path:
        parts = data.split(maxsplit=1)
        path = parts[0].strip()
        tail = parts[1].strip() if len(parts) > 1 else ""

    tail = re.sub(
        r"^(?:con(?:\s+contenido)?|contenido|que diga|que dice|:|-)\s*",
        "",
        tail,
        flags=re.I,
    )
    return (path or None), tail


def read_text_file(path: str) -> str:
    full = _resolve_user_path(path)
    if not os.path.exists(full):
        return f"No encuentro el archivo {full}, Señor."
    try:
        with open(full, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except Exception as e:
        return f"No pude leer {full}: {e}"
    if len(content) > 1500:
        content = content[:1500] + "\n... (archivo truncado)"
    return f"Contenido de {full}:\n{content}"


def write_text_file(payload: str) -> str:
    path, content = _parse_path_and_content(payload)
    if not path:
        return "Indícame ruta y contenido. Ejemplo: crea archivo notas.txt con hola mundo."
    if not content:
        return "Necesito el contenido para escribir en el archivo, Señor."

    full = _resolve_user_path(path)
    try:
        os.makedirs(os.path.dirname(full) or ".", exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Archivo guardado en {full}, Señor."
    except Exception as e:
        return f"No pude escribir {full}: {e}"


def append_text_file(payload: str) -> str:
    path, content = _parse_path_and_content(payload)
    if not path or not content:
        return "Formato: añade al archivo <ruta> con <texto>."
    full = _resolve_user_path(path)
    try:
        os.makedirs(os.path.dirname(full) or ".", exist_ok=True)
        with open(full, "a", encoding="utf-8") as f:
            if os.path.getsize(full) > 0:
                f.write("\n")
            f.write(content)
        return f"Texto añadido en {full}, Señor."
    except Exception as e:
        return f"No pude añadir contenido en {full}: {e}"


def replace_in_text_file(payload: str) -> str:
    """
    Formato:
      reemplaza en archivo ruta | texto_viejo | texto_nuevo
    """
    parts = [p.strip() for p in payload.split("|")]
    if len(parts) != 3:
        return (
            "Formato inválido. Usa: reemplaza en archivo ruta | texto_viejo | texto_nuevo."
        )
    path, old, new = parts
    full = _resolve_user_path(path)
    if not os.path.exists(full):
        return f"No encuentro el archivo {full}, Señor."
    try:
        with open(full, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        if old not in content:
            return "No encontré el texto a reemplazar en ese archivo, Señor."
        updated = content.replace(old, new)
        with open(full, "w", encoding="utf-8") as f:
            f.write(updated)
        return f"Reemplacé el texto en {full}, Señor."
    except Exception as e:
        return f"No pude editar {full}: {e}"


def edit_file(path: str) -> str:
    full = _resolve_user_path(path)
    try:
        os.makedirs(os.path.dirname(full) or ".", exist_ok=True)
        if not os.path.exists(full):
            with open(full, "w", encoding="utf-8") as f:
                f.write("")
        r = subprocess.run(["open", "-e", full], capture_output=True, text=True)
        if r.returncode == 0:
            return f"Editor abierto para {full}, Señor."
        return f"No pude abrir el editor para {full}, Señor."
    except Exception as e:
        return f"No pude preparar el archivo {full}: {e}"


# ══════════════════════════════════════════════════════════════
# 3. WEB SEARCH
# ══════════════════════════════════════════════════════════════

def web_search(query: str, max_results: int = 3) -> str:
    if not _HAS_DDG:
        return "[búsqueda no disponible — ejecuta: pip install duckduckgo-search]"
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        if not results:
            return f"No encontré resultados para '{query}', Señor."
        lines = [f"Resultados de búsqueda para '{query}':"]
        for r in results:
            # Usar title como fuente y body como snippet/titular
            # Formato: "Fuente: snippet"
            lines.append(f"  • {r['title']}: {r['body'][:120]}")
        return "\n".join(lines)
    except Exception as e:
        return f"Error en búsqueda web: {e}"


def web_search_for_llm(query: str) -> str:
    return web_search(query, max_results=3)


def get_news(topic: str = "tecnología", max_results: int = 3) -> str:
    """Obtiene noticias recientes sobre un tema específico"""
    try:
        # Fuentes preferidas (site: operator)
        preferred_sources = "site:tn.com.ar OR site:dw.com OR site:bbc.com OR site:news.google.com OR site:rt.com"
        news_info = web_search(f"últimas noticias {topic} hoy ({preferred_sources})", max_results=max_results)
        # Si falla, fallback general
        if news_info.startswith("Error en búsqueda web"):
            news_info = web_search(f"últimas noticias {topic} hoy", max_results=max_results)
        # Procesar para extraer titulares (snippet) 
        if news_info.startswith("Resultados de búsqueda"):
            lines = news_info.split('\n')
            if len(lines) > 1:
                results = lines[1:]
                headlines = []
                for line in results[:max_results]:
                    line = line.strip()
                    if line.startswith('•'):
                        # Quitar bullet
                        line = line[1:].strip()
                        # Separar fuente (antes del primer ':') de snippet (después)
                        if ':' in line:
                            parts = line.split(':', 1)
                            snippet = parts[1].strip()
                            # Limpiar " - Fuente" al final del snippet
                            if ' - ' in snippet:
                                snippet = snippet.rsplit(' - ', 1)[0].strip()
                            # Limitar longitud
                            headline = snippet[:100] + ("..." if len(snippet) > 100 else "")
                        else:
                            headline = line[:100] + ("..." if len(line) > 100 else "")
                        headlines.append(f"• {headline}")
                if headlines:
                    return f"Últimas noticias sobre {topic}:\n" + "\n".join(headlines)
                else:
                    return f"No encontré titulares recientes sobre {topic}, Señor."
            else:
                return news_info
        else:
            return news_info
    except Exception as e:
        return f"Error obteniendo noticias sobre {topic}: {e}"


# ══════════════════════════════════════════════════════════════
# 3b. VOZ
# ══════════════════════════════════════════════════════════════

_MALE_VOICES = [
    "Reed (Español (España))",
    "Reed (Español (México))",
    "Rocko (Español (España))",
    "Rocko (Español (México))",
    "Eddy (Español (España))",
    "Eddy (Español (México))",
    "Grandpa (Español (España))",
    "Grandpa (Español (México))",
]

_FEMALE_VOICES = [
    "Mónica",
    "Paulina",
    "Shelley (Español (España))",
    "Sandy (Español (España))",
]

def list_voices() -> str:
    lines = ["Voces masculinas disponibles:"]
    lines += [f"  {i+1}. {v}" for i, v in enumerate(_MALE_VOICES)]
    lines += ["\nVoces femeninas:"]
    lines += [f"  {i+1}. {v}" for i, v in enumerate(_FEMALE_VOICES)]
    lines += ["\nUsa: 'cambia la voz a Reed' o 'cambia la voz a Rocko'"]
    return "\n".join(lines)

def set_voice_speed(rate: int) -> str:
    """Escribe la nueva velocidad en el .env en tiempo de ejecución."""
    _update_env("NOVA_VOICE_RATE", str(rate))
    return f"Velocidad cambiada a {rate} palabras por minuto, Señor. Reinicia para aplicar."

def set_voice(name: str) -> str:
    """Cambia la voz por nombre (parcial)."""
    all_voices = _MALE_VOICES + _FEMALE_VOICES
    matches = [v for v in all_voices if name.lower() in v.lower()]
    if not matches:
        return f"No encontré la voz '{name}'. Usa 'voces disponibles' para ver la lista."
    chosen = matches[0]
    _update_env("NOVA_VOICE", chosen)
    # Probar la voz ahora mismo
    subprocess.run(["say", "-v", chosen, "-r", "150", "Voz actualizada, Señor."])
    return f"Voz cambiada a {chosen}, Señor. Reinicia para que sea permanente."

def detect_language(text: str) -> str:
    """
    Detecta si el texto está principalmente en español o inglés.
    Retorna 'es' para español, 'en' para inglés, o 'unknown' si no se puede determinar.
    """
    if not text or not text.strip():
        return 'unknown'
    
    # Convertir a minúsculas para comparación
    text_lower = text.lower().strip()
    
    # Dividir el texto en palabras (solo letras y números)
    import re
    words = re.findall(r'\b\w+\b', text_lower)
    
    # Palabras comunes en español
    spanish_indicators = [
        'el', 'la', 'los', 'las', 'un', 'una', 'unos', 'unas',
        'y', 'o', 'pero', 'porque', 'que', 'como', 'cuando',
        'donde', 'quien', 'qué', 'cómo', 'cuándo', 'dónde',
        'es', 'son', 'está', 'están', 'tener', 'tiene', 'tienen',
        'hacer', 'hace', 'hacen', 'poder', 'puede', 'pueden',
        'querer', 'quiere', 'quieren', 'deber', 'debe', 'deben',
        'saber', 'sabe', 'saben', 'ver', 've', 'ven', 'dar',
        'da', 'dan', 'ir', 'va', 'van', 'ser', 'fue', 'fueron',
        'para', 'por', 'con', 'sin', 'sobre', 'bajo', 'entre',
        'desde', 'hasta', 'mientras', 'aunque', 'pues', 'luego',
        'entonces', 'así', 'también', 'tampoco', 'siempre',
        'nunca', 'ya', 'todavía', 'aún', 'quizás', 'probablemente'
    ]
    
    # Palabras comunes en inglés
    english_indicators = [
        'the', 'a', 'an', 'and', 'or', 'but', 'because', 'that',
        'how', 'when', 'where', 'who', 'what', 'how', 'when',
        'is', 'are', 'was', 'were', 'be', 'been', 'being',
        'have', 'has', 'had', 'do', 'does', 'did', 'can',
        'could', 'will', 'would', 'should', 'may', 'might',
        'must', 'shall', 'want', 'wants', 'wanted', 'need',
        'needs', 'needed', 'see', 'sees', 'saw', 'seeing',
        'give', 'gives', 'gave', 'giving', 'go', 'goes',
        'went', 'going', 'for', 'with', 'without', 'about',
        'above', 'below', 'between', 'through', 'during',
        'before', 'after', 'while', 'although', 'because',
        'so', 'then', 'thus', 'therefore', 'however',
        'nevertheless', 'always', 'never', 'yet', 'still',
        'already', 'perhaps', 'probably', 'maybe'
    ]
    
    # Contar coincidencias exactas de palabras
    spanish_count = sum(1 for word in words if word in spanish_indicators)
    english_count = sum(1 for word in words if word in english_indicators)
    
    # Determinar el idioma basado en qué tiene más coincidencias
    if spanish_count > english_count:
        return 'es'
    elif english_count > spanish_count:
        return 'en'
    else:
        # Si hay empate o ninguna coincidencia, asumir español por defecto
        # (ya que el usuario primarily usa español)
        return 'es'

def get_voice_for_language(language_code: str) -> str:
    """
    Obtiene una voz apropiada para el idioma especificado.
    """
    if language_code == 'es':
        # Voz en español por defecto
        return os.getenv("NOVA_VOICE", "Reed (Español (España))")
    elif language_code == 'en':
        # Voz en inglés - usando voces masculinas en inglés como ejemplo
        english_voices = [
            "Alex (English (United States))",
            "Daniel (English (United Kingdom))",
            "Fred (English (United States))",
            "Victoria (English (United States))"
        ]
        # Devolver la primera voz inglesa disponible o la primera de la lista
        for voice in english_voices:
            if voice in _MALE_VOICES or voice in _FEMALE_VOICES:
                return voice
        # Si ninguna coincide, devolver la primera de la lista
        return english_voices[0] if english_voices else _MALE_VOICES[0] if _MALE_VOICES else "Alex"
    else:
        # Por defecto, voz en español
        return os.getenv("NOVA_VOICE", "Reed (Español (España))")

def speak_with_language_detection(text: str) -> str:
    """
    Habla el texto detectando automáticamente el idioma y seleccionando la voz apropiada.
    """
    if not _NOVA_COMPONENTS_AVAILABLE:
        return "Servicio de voz no disponible"
    
    try:
        # Detectar idioma
        lang = detect_language(text)
        
        # Obtener voz apropiada
        voice = get_voice_for_language(lang)
        
        # Usar el comando say para reproducir el texto
        # Primero, cambiar a la voz apropiada
        current_voice = os.getenv("NOVA_VOICE", "Reed (Español (España))")
        if voice != current_voice:
            set_voice(voice)
        
        # Reproducir el texto
        subprocess.run(["say", "-r", "150", text], check=True)
        
        # Restaurar la voz original si cambió
        if voice != current_voice:
            set_voice(current_voice)
            
        return f"Texto hablado en {lang} con voz {voice}"
    except Exception as e:
        return f"Error al hablar: {e}"

def _restart_nova() -> str:
    """Reinicia el proceso de NOVA cargando el .env fresco."""
    import sys
    import threading
    def _do_restart():
        import time; time.sleep(1)
        os.execv(sys.executable, [sys.executable] + sys.argv)
    threading.Thread(target=_do_restart, daemon=True).start()
    return "Reiniciando en un momento, Señor."

def _update_env(key: str, value: str) -> None:
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    try:
        with open(env_path, "r") as f:
            lines = f.readlines()
        updated = False
        for i, line in enumerate(lines):
            if line.startswith(f"{key}="):
                lines[i] = f"{key}={value}\n"
                updated = True
                break
        if not updated:
            lines.append(f"{key}={value}\n")
        with open(env_path, "w") as f:
            f.writelines(lines)
    except Exception:
        pass  # no fatal si falla escribir .env


def get_system_status() -> str:
    """Lee el .env y devuelve el estado actual de los parámetros críticos."""
    name     = os.getenv("ASSISTANT_NAME", "Auxiliar")
    voice    = os.getenv("NOVA_VOICE", "Reed")
    rate     = os.getenv("NOVA_VOICE_RATE", "150")
    barge_in = os.getenv("BARGE_IN_THRESHOLD", "600")
    noise    = os.getenv("NOISE_FILTER_FACTOR", "1.5")

    status = (
        f"Estado del Sistema {name}:\n"
        f"  • Voz: {voice} (velocidad: {rate})\n"
        f"  • Barge-in (interrupción): {'Desactivado' if barge_in == '0' else f'Umbral {barge_in}'}\n"
        f"  • Filtro de ruido: x{noise}\n"
        "Todo normal por aquí, Señor."
    )
    return status


# ══════════════════════════════════════════════════════════════
# 4. TIEMPO
# ══════════════════════════════════════════════════════════════

_DIAS   = ["lunes","martes","miércoles","jueves","viernes","sábado","domingo"]
_MESES  = ["enero","febrero","marzo","abril","mayo","junio",
           "julio","agosto","septiembre","octubre","noviembre","diciembre"]

def get_time() -> str:
    """Obtiene la hora actual en formato HH:MM"""
    now = datetime.datetime.now()
    return f"Son las {now.strftime('%H:%M')}, Señor."


def get_date() -> str:
    """Obtiene la fecha actual en formato legible"""
    now = datetime.datetime.now()
    return (
        f"Hoy es {_DIAS[now.weekday()]}, "
        f"{now.day} de {_MESES[now.month - 1]} de {now.year}, Señor."
    )


_active_timers: dict[str, threading.Timer] = {}
_notify_cb = None
_router = None

def set_notify_callback(cb):
    global _notify_cb
    _notify_cb = cb

def set_router(r):
    global _router
    _router = r

def _take_screenshot_path() -> str:
    """Toma screenshot y retorna el path del archivo, o vacío si falla."""
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.expanduser(f"~/Desktop/nova_{ts}.png")
    r = subprocess.run(["screencapture", "-x", path], capture_output=True)
    return path if r.returncode == 0 else ""


def analyze_screen(prompt: str = "Describe lo que ves en esta pantalla con detalle.") -> str:
    """Captura pantalla y la envía al LLM para análisis."""
    if not _router:
        return "El módulo de visión no está inicializado, Señor."

    img_path = _take_screenshot_path()
    if not img_path:
        return "No pude tomar la captura de pantalla, Señor."

    return _router.vision_query(prompt, img_path)

def computer_pilot_mode(goal: str) -> str:
    """Modo Agente Autónomo (Computer Use): Evalúa la pantalla iterativamente en tiempo real y maneja el mouse de forma independiente."""
    if not _router:
        return "El módulo de router no está inicializado."
    
    import time
    log.info("[AUTOPILOTO] Misión: %s", goal)
    
    sys_override = (
        "You are an autonomous computer operator with vision. "
        f"USER GOAL: {goal}\n"
        "Analyze the provided screenshot to find the exact coordinates of UI elements needed to achieve the goal. "
        "Output ONLY ONE action per turn in exactly this format:\n"
        "CLICK X,Y\n"
        "TYPE text_to_type\n"
        "PRESS key_name\n"
        "SCROLL amount\n"
        "DONE\n"
        "Do NOT output markdown, explanations, or backticks. Respond with nothing else but the exact command."
    )
    
    for step in range(8):
        # Tomar foto
        clean_path = _take_screenshot_path()
        if not clean_path:
            return "No pude tomar la captura de pantalla, Señor."
        
        # Consultar al cerebro visual
        reply = _router.vision_query("What next?", clean_path, system_override=sys_override).strip()
        log.debug("[AUTOPILOTO] Decisión: %s", reply[:120])
        
        # Ejecutar acción
        if reply.startswith("CLICK"):
            coords = reply.replace("CLICK", "").strip().split(",")
            if len(coords) == 2:
                try:
                    mouse_click(int(coords[0].strip()), int(coords[1].strip()))
                except:
                    pass
        elif reply.startswith("TYPE"):
            text = reply.replace("TYPE", "").strip()
            type_text(text)
        elif reply.startswith("PRESS"):
            key = reply.replace("PRESS", "").strip()
            press_key(key)
        elif reply.startswith("SCROLL"):
            try:
                amt = reply.replace("SCROLL", "").strip()
                mouse_scroll(int(amt))
            except:
                pass
        elif reply.startswith("DONE") or reply.startswith("Obj") or reply.startswith("Hecho"):
            return f"Objetivo de piloto automático completado, Señor. ({step+1} pasos)"
            
        time.sleep(2) # Pausa de seguridad
        
    return "Límite de pasos del autopiloto alcanzado sin confirmar el final, Señor."

def set_timer(seconds: int, label: str = "Temporizador") -> str:
    def _ring():
        log.info("[AUTOPILOTO] Tiempo cumplido: %s", label)
        _active_timers.pop(label, None)
        if _notify_cb:
            _notify_cb(f"Señor, el tiempo del {label} ha terminado.")

    if label in _active_timers:
        _active_timers[label].cancel()

    t = threading.Timer(seconds, _ring)
    t.daemon = True
    t.start()
    _active_timers[label] = t

    mins, secs = divmod(seconds, 60)
    if mins:
        return f"Temporizador de {mins} minutos activado, Señor."
    return f"Temporizador de {secs} segundos activado, Señor."


# ══════════════════════════════════════════════════════════════
# 5. MEMORIA (delega a nova_memory)
# ══════════════════════════════════════════════════════════════

def skill_remember(text: str) -> str:
    """Extrae clave-valor del texto y guarda en memoria."""
    # Patrones: "recuerda que mi nombre es Juan", "recuerda: color favorito = azul"
    match = re.search(r"(?:que\s+)?(.+?)\s+(?:es|son|=)\s+(.+)", text, re.I)
    if match:
        return mem.remember(match.group(1).strip(), match.group(2).strip())
    # Sin estructura clara → guardar todo como nota
    return mem.remember(f"nota_{datetime.datetime.now().strftime('%H%M%S')}", text)


def skill_recall(query: str) -> str:
    return mem.recall(query)


def skill_forget(key: str) -> str:
    return mem.forget(key)


# ══════════════════════════════════════════════════════════════
# 6. n8n — Gastos, Calendario, Eventos, Archivos
# ══════════════════════════════════════════════════════════════

def skill_gastos(periodo: str = "semana") -> str:
    if not _HAS_N8N:
        return "Módulo n8n no disponible, Señor."
    # Normalizar periodo
    lower = periodo.lower()
    if any(w in lower for w in ["hoy", "today", "día"]):
        p = "hoy"
    elif any(w in lower for w in ["mes", "month"]):
        p = "mes"
    else:
        p = "semana"
    return n8n.consultar_gastos(p)


def skill_calendario(fecha: str = "hoy") -> str:
    lower = fecha.lower()
    if any(w in lower for w in ["mañana", "tomorrow"]):
        f = "mañana"
    elif any(w in lower for w in ["semana", "week"]):
        f = "semana"
    else:
        f = "hoy"

    if _HAS_GOOGLE:
        try:
            eventos = _goog.calendar.eventos(f)
            if not eventos:
                return f"No hay eventos para {f}, Señor."
            lines = [f"Eventos ({f}):"]
            for e in eventos:
                hora = e.get("hora", "todo el día")
                lines.append(f"  • {hora} — {e['titulo']}")
            return "\n".join(lines)
        except Exception as ex:
            pass

    if _HAS_N8N:
        return n8n.consultar_calendario(f)
    return "Calendario no disponible, Señor."


def skill_crear_evento(texto: str) -> str:
    """
    Parsea texto del tipo: 'reunión con Pedro el viernes a las 15:00'
    y crea el evento en Google Calendar.
    """
    if not _HAS_N8N:
        return "Módulo n8n no disponible, Señor."

    # Extraer hora (HH:MM o HH)
    hora_match = re.search(r"(\d{1,2})[:\s]?(\d{2})?\s*(?:hs?|horas?)?", texto)
    hora = "09:00"
    if hora_match:
        h = hora_match.group(1).zfill(2)
        m = hora_match.group(2) or "00"
        hora = f"{h}:{m}"

    # Extraer fecha relativa
    lower = texto.lower()
    if "mañana" in lower or "tomorrow" in lower:
        fecha = "mañana"
    elif "lunes" in lower:
        fecha = "lunes"
    elif "martes" in lower:
        fecha = "martes"
    elif "miércoles" in lower or "miercoles" in lower:
        fecha = "miércoles"
    elif "jueves" in lower:
        fecha = "jueves"
    elif "viernes" in lower:
        fecha = "viernes"
    elif "sábado" in lower or "sabado" in lower:
        fecha = "sábado"
    elif "domingo" in lower:
        fecha = "domingo"
    else:
        fecha = "hoy"

    # Título = texto sin hora ni fecha
    titulo = re.sub(
        r"(\d{1,2})[:\s]?\d{0,2}\s*(?:hs?|horas?)?|"
        r"\b(?:mañana|tomorrow|lunes|martes|miércoles|miercoles|jueves|viernes|sábado|sabado|domingo)\b|"
        r"\b(?:a las|el|la|una|un)\b",
        "", texto, flags=re.I
    ).strip(" .,") or texto

    return n8n.crear_evento(titulo, fecha, hora)


def skill_crear_archivo(texto: str) -> str:
    """
    Crea un archivo con nombre y contenido dados en Google Drive.
    Ejemplo: 'crea un archivo notas.txt con hola mundo'
    """
    if not _HAS_N8N:
        return "Módulo n8n no disponible, Señor."
    # Intentar extraer nombre y contenido
    match = re.search(
        r"(?:archivo|file|documento|doc)\s+(\S+\.?\w*)\s+(?:con|con contenido|que diga|with)?\s*(.+)",
        texto, re.I
    )
    if match:
        nombre    = match.group(1)
        contenido = match.group(2).strip()
    else:
        nombre    = f"nota_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        contenido = texto
    # Usa el endpoint unificado /webhook/nova/drive (drive_crear)
    return n8n.drive_crear(nombre, contenido)


def skill_estado_n8n() -> str:
    if not _HAS_N8N:
        return "Módulo n8n no cargado, Señor."
    return n8n.estado_n8n()


# ══════════════════════════════════════════════════════════════
# 7. Red local y Bluetooth
# ══════════════════════════════════════════════════════════════

def skill_scan_red(subnet: str = "") -> str:
    """Descubre dispositivos activos en la red local usando ARP."""
    import subprocess, re
    try:
        # -n evita resolución DNS → instantáneo en vez de 5+ segundos
        result = subprocess.run(
            ["/usr/sbin/arp", "-an"], capture_output=True, text=True, timeout=3
        )
        lines = result.stdout.splitlines()
        dispositivos = []
        for line in lines:
            # Formato: ? (192.168.1.1) at 50:c7:bf:2b:8e:62 on en0 ...
            m = re.search(r"\((\d+\.\d+\.\d+\.\d+)\)\s+at\s+([0-9a-f:]{11,17})", line, re.I)
            if m:
                ip, mac = m.groups()
                # Filtrar multicast/broadcast y entradas incompletas
                if "incomplete" in line or ip.startswith("224.") or ip.startswith("239.") or ip == "255.255.255.255":
                    continue
                # Inferir tipo por MAC OUI conocidos
                tipo = _oui_hint(mac)
                dispositivos.append((ip, mac, tipo))

        if not dispositivos:
            return "Caché ARP vacía. Intentá hacer ping a la red primero, Señor."

        # Ordenar por IP
        dispositivos.sort(key=lambda x: tuple(int(p) for p in x[0].split(".")))
        lines_out = [f"Dispositivos en la red ({len(dispositivos)} encontrados):"]
        for ip, mac, tipo in dispositivos:
            tipo_str = f"  [{tipo}]" if tipo else ""
            lines_out.append(f"  {ip:<16}  {mac}{tipo_str}")
        return "\n".join(lines_out)
    except Exception as e:
        return f"Error escaneando la red: {e}"


def _oui_hint(mac: str) -> str:
    """Pista rápida de fabricante por los primeros 3 bytes del MAC."""
    oui = mac.replace("-", ":").upper()[:8]
    _OUI = {
        "50:C7:BF": "Router/TP-Link", "DC:A9:04": "Apple",
        "C0:17:54": "Apple",          "F8:FF:C2": "Apple",
        "00:50:F2": "Microsoft",      "B0:BE:76": "Samsung",
        "1C:36:BB": "Apple",          "48:22:D2": "Compulab",
        "0C:A6:94": "Philips",        "3E:EB:19": "Random/IoT",
        "9E:F2:E3": "Random/IoT",     "8A:1F:B2": "Random/IoT",
    }
    return _OUI.get(oui, "")


def skill_scan_bluetooth() -> str:
    """Lista dispositivos Bluetooth pareados/visibles (macOS nativo, sin deps)."""
    import subprocess
    try:
        result = subprocess.run(
            ["system_profiler", "SPBluetoothDataType"],
            capture_output=True, text=True, timeout=10
        )
        output = result.stdout
    except Exception as e:
        return f"Error accediendo a Bluetooth: {e}"

    # Secciones que NO son dispositivos de usuario
    _SKIP = {"bluetooth", "bluetooth controller", "not connected", "connected",
             "recently connected", "services", "features", "settings", "apple"}

    dispositivos = []
    current: dict = {}
    seccion_conectado: bool = False

    for raw_line in output.splitlines():
        indent = len(raw_line) - len(raw_line.lstrip())
        line = raw_line.strip()
        if not line:
            continue

        if line.endswith(":"):
            nombre = line[:-1].strip()
            nombre_l = nombre.lower()

            # Detectar si cambia la sección de conexión
            if nombre_l == "connected":
                seccion_conectado = True
                continue
            if nombre_l in ("not connected", "recently connected"):
                seccion_conectado = False
                continue
            if nombre_l in _SKIP:
                continue

            # Dispositivos reales están a indentación ≥ 10
            if indent >= 10:
                if current.get("nombre"):
                    dispositivos.append(current.copy())
                current = {"nombre": nombre, "conectado": seccion_conectado}
        elif "Address:" in line and current.get("nombre"):
            current["mac"] = line.split("Address:")[-1].strip()
        elif "Minor Type:" in line and current.get("nombre"):
            current["tipo"] = line.split("Minor Type:")[-1].strip()

    if current.get("nombre"):
        dispositivos.append(current)

    if not dispositivos:
        return "No se encontraron dispositivos Bluetooth pareados, Señor."

    lines_out = [f"Dispositivos Bluetooth ({len(dispositivos)}):"]
    for d in dispositivos:
        estado = "🔵" if d.get("conectado") else "⚪"
        tipo = f" [{d['tipo']}]" if d.get("tipo") else ""
        mac = f"  {d['mac']}" if d.get("mac") else ""
        lines_out.append(f"  {estado}  {d['nombre']}{tipo}{mac}")
    return "\n".join(lines_out)


# ══════════════════════════════════════════════════════════════
# 7. OBSIDIAN — cerebro compartido
# ══════════════════════════════════════════════════════════════

import nova.core.nova_memory as _mem_obs  # alias para evitar circular

def obsidian_anota(text: str) -> str:
    """Agrega una entrada al diario de hoy en el vault."""
    return _mem_obs.diary_append(text)


def obsidian_nota_nueva(args: str) -> str:
    """
    Crea una nota en el vault.
    Formato esperado: '[carpeta/]título: contenido'
    """
    if ":" in args:
        titulo, contenido = args.split(":", 1)
        titulo    = titulo.strip()
        contenido = contenido.strip()
    else:
        titulo    = args.strip()
        contenido = ""
    if "/" in titulo:
        carpeta, titulo = titulo.rsplit("/", 1)
    else:
        carpeta = "NOVA/Notas"
    if _HAS_CEREBRO:
        resultado = _cerebro_nueva_nota(titulo, f"# {titulo}\n\n{contenido}\n", carpeta)
        return f"Nota '{titulo}' creada, Señor. {resultado}"
    _mem_obs.vault_create_note(carpeta, titulo, f"# {titulo}\n\n{contenido}\n")
    return f"Nota '{titulo}' creada en {carpeta}, Señor."


def obsidian_lee_nota(args: str) -> str:
    """Lee una nota del vault."""
    args = args.strip()
    if _HAS_CEREBRO:
        # Busca primero como ruta exacta, luego por nombre
        contenido = _cerebro_leer(args)
        if not contenido.startswith("No encontré") and not contenido.startswith("Error"):
            return contenido[:800]
        # Intentar búsqueda por nombre
        resultados = _cerebro_buscar(args, max_resultados=1)
        if resultados:
            ruta = resultados[0].get("ruta_absoluta", "")
            if ruta:
                from pathlib import Path as _Path
                try:
                    texto = _Path(ruta).read_text(encoding="utf-8", errors="replace")
                    return texto[:800]
                except Exception:
                    pass
    parts = args.split("/", 1)
    if len(parts) == 2:
        carpeta, titulo = parts
    else:
        carpeta = "NOVA/Notas"
        titulo  = parts[0]
    contenido = _mem_obs.vault_read_note(carpeta, titulo)
    if not contenido:
        return f"No encontré la nota '{titulo}' en {carpeta}, Señor."
    return contenido[:800]


def obsidian_busca(query: str) -> str:
    """Busca texto en todo el vault de Obsidian."""
    query = query.strip()
    if not query:
        return "¿Qué quiere que busque en el Cerebro, Señor?"

    # Primero intenta file-based (siempre disponible)
    if _HAS_CEREBRO:
        results = _cerebro_buscar(query, max_resultados=4)
        if results:
            lines = [f"Encontré {len(results)} resultado(s) para '{query}':"]
            for r in results:
                nombre = r["titulo"]
                lines.append(f"• {nombre}: {r['extracto'][:200]}")
            return "\n".join(lines)

    # Fallback a REST API si Obsidian está corriendo
    results = _mem_obs.vault_search(query, top_k=4)
    if not results:
        return f"No encontré resultados para '{query}' en el Cerebro, Señor."
    lines = [f"Encontré {len(results)} resultado(s) para '{query}':"]
    for r in results:
        name = r["filename"].split("/")[-1].replace(".md", "")
        lines.append(f"• {name}: {r['snippet'][:150]}")
    return "\n".join(lines)


def obsidian_lista_dir(path: str = "") -> str:
    """Lista archivos de un directorio del vault."""
    if _HAS_CEREBRO:
        archivos = _cerebro_listar(path.strip() or "")
        if archivos:
            nombres = [a.split("/")[-1].replace(".md", "") for a in archivos[:20]]
            return f"Archivos en el Cerebro ({len(archivos)}): " + ", ".join(nombres)
        return f"No encontré archivos en {'/' if not path else path}, Señor."
    files = _mem_obs.vault_list_dir(path.strip() or "")
    if not files:
        return f"No encontré archivos en {'/' if not path else path}, Señor."
    names = [f.split("/")[-1] for f in files[:20]]
    return f"Archivos en el Cerebro ({len(files)}): " + ", ".join(names)


def skill_cerebro_estado(_=None) -> str:
    """Muestra estado del vault Cerebro: rutas, cantidad de notas, API."""
    if _HAS_CEREBRO:
        return _cerebro_estado()
    return "Conector Cerebro no disponible, Señor."


def skill_cerebro_que_se(query: str) -> str:
    """
    Busca en el Cerebro y devuelve un resumen de lo que Nova sabe sobre el tema.
    Si encuentra notas, devuelve título + extracto de cada una.
    """
    query = query.strip()
    if not query:
        return "¿Sobre qué quiere que busque, Señor?"
    if _HAS_CEREBRO:
        resultados = _cerebro_buscar(query, max_resultados=3)
        if not resultados:
            return f"No tengo notas sobre '{query}' en el Cerebro, Señor."
        lines = [f"Lo que sé sobre '{query}':"]
        for r in resultados:
            lines.append(f"\n📄 {r['titulo']}")
            lines.append(r["extracto"])
        return "\n".join(lines)
    return obsidian_busca(query)


def sincroniza_cerebro(_=None) -> str:
    """Sincroniza proyectos del Desktop y memorias de Claude → Obsidian vault."""
    import subprocess, sys, os
    script = os.path.join(os.path.dirname(__file__), "sync_cerebro.py")
    try:
        result = subprocess.run(
            [sys.executable, script],
            capture_output=True, text=True, timeout=120
        )
        # Extraer línea "Listo: ..." del output
        for line in reversed(result.stdout.splitlines()):
            if "Listo:" in line:
                return f"Cerebro actualizado: {line.split('Listo:')[1].strip()}"
        return "Sincronización completada, Señor."
    except subprocess.TimeoutExpired:
        return "La sincronización tardó demasiado. Verifique la conexión con Obsidian."
    except Exception as e:
        return f"Error al sincronizar: {e}"


def skill_telegram(mensaje: str) -> str:
    if not _HAS_N8N: return "n8n no disponible."
    return n8n.enviar_telegram(mensaje)

def skill_push(args: str) -> str:
    if not _HAS_N8N: return "n8n no disponible."
    if ":" in args:
        t, m = args.split(":", 1)
        return n8n.enviar_push(t.strip(), m.strip())
    return n8n.enviar_push("Aviso de NOVA", args)


# ══════════════════════════════════════════════════════════════
# 7c. AGENTES ESPECIALIZADOS — agency-agents integration
# ══════════════════════════════════════════════════════════════

try:
    from nova.connectors.nova_specialist import (
        skill_especialista as _skill_especialista,
        list_agents_formatted as _list_agents_formatted,
        find_agent as _find_agent,
        invoke_specialist as _invoke_specialist,
        crear_proyecto as _crear_proyecto,
        mejorar_proyecto_paralelo as _mejorar_paralelo,
        planear_mejoras_proyecto as _planear_mejoras,
        formatear_misiones as _formatear_misiones,
        codear_con_docs as _codear_con_docs,
        _DOC_SEARCH_RE as _SPEC_DOC_RE,
        _CODE_KEYWORDS as _SPEC_CODE_KW,
        generar_tests as _generar_tests,
        dockerizar as _dockerizar,
        deploy_local as _deploy_local,
    )
    _HAS_SPECIALIST = True
except ImportError:
    _HAS_SPECIALIST = False

# ── LSP imports ───────────────────────────────────────────────────────────────
try:
    from nova.connectors.nova_lsp import (
        find_definition        as _lsp_definition,
        find_references        as _lsp_references,
        get_signature          as _lsp_signature,
        get_docstring          as _lsp_docstring,
        get_completions        as _lsp_completions,
        diagnose_file          as _lsp_diagnose,
        analyze_file           as _lsp_analyze,
        find_symbol_in_project as _lsp_find_symbol,
        rename_symbol          as _lsp_rename,
    )
    _HAS_LSP = True
except ImportError:
    _HAS_LSP = False

try:
    from nova.tools.nova_ocr import read_file_as_context as _ocr_read
    _HAS_OCR = True
except ImportError:
    _HAS_OCR = False

def skill_especialista(texto: str) -> str:
    """Invoca un agente especializado (firmware, arquitecto, IA, etc.) via Groq/OpenRouter.
    Si la respuesta contiene código Python o bash, lo ejecuta automáticamente.
    Prefijá con 'solo consejo:' para obtener solo texto sin ejecución.
    """
    if not _HAS_SPECIALIST:
        return "Módulo de especialistas no disponible."
    # Guard: si la petición es sobre generar una imagen, redirigir
    _img_keywords = ("imagen", "foto", "ilustración", "ilustracion", "cuadro",
                     "dibujo", "pintura", "render", "genera una imagen", "crea una imagen")
    if any(kw in texto.lower() for kw in _img_keywords):
        return skill_imagen(texto)
    # Detectar si el usuario quiere solo consejo (sin ejecutar)
    auto_exec = True
    if texto.lower().startswith(("solo consejo", "sin ejecutar", "solo explica")):
        auto_exec = False
        texto = re.sub(r"^(solo consejo|sin ejecutar|solo explica)\s*[:\-]?\s*", "", texto, flags=re.IGNORECASE)

    # Pasar auto_exec al skill
    from nova.connectors.nova_specialist import (
        skill_especialista as _dispatch,
        find_agent, invoke_specialist
    )
    # Intentar dispatch por patrones
    result = _dispatch(texto)
    if result is not None:
        return result
    # Fallback: buscar agente por contexto y ejecutar con auto_exec correcto
    agent = find_agent(texto.split()[0] if texto else "")
    if agent:
        return invoke_specialist(agent, texto, auto_exec=auto_exec)
    return "No identifiqué qué especialista necesita. Pruebe: 'actúa como firmware engineer y [tarea]'"

def skill_listar_agentes(texto: str = "") -> str:
    """Lista los agentes especializados disponibles."""
    if not _HAS_SPECIALIST:
        return "Módulo de especialistas no disponible."
    cat = texto.strip().lower() if texto.strip() else None
    return _list_agents_formatted(cat)


def skill_crear_proyecto(texto: str) -> str:
    """
    Crea un proyecto completo en disco con archivos reales.
    Patrones:
    - "crea un proyecto Python para [descripción] en ~/Desktop/mi_proyecto"
    - "crea repo de firmware ESP32 para drone"
    - "genera un proyecto Node.js de API REST"
    """
    if not _HAS_SPECIALIST:
        return "Módulo de especialistas no disponible."

    texto_lower = texto.lower()

    # Detectar destino explícito: "en ~/..." o "en /..." o "en [nombre]"
    destino = None
    m_dest = re.search(r"\ben\s+(~?/[\w/.\-]+|~/[\w/.\-]+)", texto)
    if m_dest:
        destino = m_dest.group(1)
        texto = texto[:m_dest.start()].strip()

    # Detectar qué agente usar según el stack tecnológico
    agente = "software architect"
    if any(w in texto_lower for w in ["esp32", "firmware", "freertos", "stm32", "arduino", "rtos", "embebido"]):
        agente = "embedded firmware engineer"
    elif any(w in texto_lower for w in ["fastapi", "django", "flask", "backend", "api rest", "servidor"]):
        agente = "backend architect"
    elif any(w in texto_lower for w in ["react", "vue", "frontend", "web app", "interfaz"]):
        agente = "frontend developer"
    elif any(w in texto_lower for w in ["python", "script", "automatizacion", "automatización", "ml", "ia"]):
        agente = "ai engineer"
    elif any(w in texto_lower for w in ["node", "typescript", "javascript", "express"]):
        agente = "backend architect"

    # Limpiar prefijos comunes del texto
    desc = re.sub(
        r"^(?:crea(?:r)?|genera(?:r)?|arma(?:r)?|inicializ[ae](?:r)?)\s+"
        r"(?:un\s+|una\s+)?(?:proyecto|repositorio|repo|app|aplicacion|aplicación)?\s*"
        r"(?:de\s+|para\s+|en\s+)?",
        "", texto, flags=re.IGNORECASE
    ).strip() or texto

    return _crear_proyecto(desc, destino=destino, agente_query=agente)


# ── Estado de proyecto activo ─────────────────────────────────
# Nova recuerda el último proyecto abierto para poder trabajar en él
_proyecto_activo: dict = {}   # {"path": Path, "name": str}
_misiones_pendientes: list[dict] = []   # misiones propuestas esperando aprobación


def _resolver_proyecto(texto: str) -> Path | None:
    """Resuelve una ruta de proyecto desde texto o devuelve el activo."""
    texto = texto.strip()
    if not texto and _proyecto_activo:
        return _proyecto_activo["path"]
    if not texto:
        return None
    # Intentar como ruta directa
    p = Path(texto).expanduser()
    if p.exists():
        return p
    # Buscar en ~/Desktop y ~/Documents
    for base in [Path.home() / "Desktop", Path.home() / "Documents"]:
        candidate = base / texto
        if candidate.exists():
            return candidate
    return None


def skill_abrir_proyecto(texto: str) -> str:
    """
    Abre un proyecto existente y lo establece como activo.
    Nova lo recordará para las próximas ediciones.
    """
    path = _resolver_proyecto(texto)
    if not path:
        return f"No encontré el proyecto '{texto}'. Usa la ruta completa o asegúrate de que existe."

    _proyecto_activo["path"] = path
    _proyecto_activo["name"] = path.name

    # Listar estructura
    archivos = []
    for f in sorted(path.rglob("*")):
        if f.is_file() and ".git" not in f.parts:
            archivos.append(str(f.relative_to(path)))

    estructura = "\n".join(f"  {a}" for a in archivos[:30])
    extra = f"\n  ... y {len(archivos)-30} más" if len(archivos) > 30 else ""
    return f"Proyecto activo: {path}\n{len(archivos)} archivos:\n{estructura}{extra}"


def skill_listar_carpeta_activa(texto: str = "") -> str:
    """Lista el contenido real de la carpeta/proyecto activo (o un subdirectorio)."""
    if not _proyecto_activo:
        # Si el usuario menciona una carpeta específica, intenta listarla directamente
        ruta = texto.strip()
        if ruta:
            return list_directory(ruta)
        return "No hay proyecto activo. Abrí un proyecto o indicá una ruta, Señor."

    base = _proyecto_activo["path"]
    # Si el texto menciona una subcarpeta, navegar a ella
    sub = texto.strip().lstrip("/")
    if sub:
        target = base / sub
        if target.is_dir():
            return list_directory(str(target))
        return f"No encontré la subcarpeta '{sub}' en el proyecto, Señor."
    return list_directory(str(base))


def skill_leer_archivo_proyecto(texto: str) -> str:
    """
    Lee un archivo del proyecto activo.
    Ej: 'lee src/monitor.py'
    """
    if not _proyecto_activo:
        return "No hay proyecto activo. Usa 'abre proyecto [ruta]' primero."

    base = _proyecto_activo["path"]
    nombre = texto.strip().lstrip("/")
    target = base / nombre

    if not target.exists():
        # Buscar por nombre parcial
        matches = [f for f in base.rglob("*") if f.is_file() and nombre in f.name]
        if not matches:
            return f"No encontré '{nombre}' en el proyecto."
        target = matches[0]

    try:
        contenido = target.read_text(encoding="utf-8", errors="replace")
        rel = str(target.relative_to(base))
        lines = contenido.splitlines()
        preview = "\n".join(f"{i+1:4}: {l}" for i, l in enumerate(lines[:60]))
        extra = f"\n... ({len(lines)-60} líneas más)" if len(lines) > 60 else ""
        return f"📄 {rel} ({len(lines)} líneas):\n```\n{preview}{extra}\n```"
    except Exception as e:
        return f"Error leyendo archivo: {e}"


def skill_leer_archivo(args: str) -> str:
    """Lee cualquier archivo (PDF, DOCX, XLSX, imagen, etc.) y devuelve su contenido como contexto."""
    if not _HAS_OCR:
        return (
            "Módulo OCR no disponible. Instalá: pip install markitdown\n"
            "Opcionalmente para OCR de imágenes: pip install pytesseract pillow"
        )

    raw = args.strip().strip("'\"")
    path = Path(raw)

    if not path.exists():
        path = Path.cwd() / raw

    if not path.exists():
        return f"No encontré el archivo: {raw}"

    return _ocr_read(path)



def skill_configurar_apikey(texto: str) -> str:
    """Guarda una API key en el .env desde el chat. Recarga el router inmediatamente."""
    import re, os
    from pathlib import Path

    _KEY_MAP = {
        "groq":        "GROQ_API_KEY",
        "openrouter":  "OPENROUTER_API_KEY",
        "anthropic":   "ANTHROPIC_API_KEY",
        "claude":      "ANTHROPIC_API_KEY",
        "openai":      "OPENAI_API_KEY",
        "deepseek":    "DEEPSEEK_API_KEY",
        "mistral":     "MISTRAL_API_KEY",
        "cerebras":    "CEREBRAS_API_KEY",
        "github":      "GITHUB_TOKEN",
        "telegram":    "TELEGRAM_BOT_TOKEN",
    }

    texto_lower = texto.lower()
    env_key = None
    for kw, ek in _KEY_MAP.items():
        if kw in texto_lower:
            env_key = ek
            break

    if not env_key:
        providers = ", ".join(_KEY_MAP.keys())
        return f"No reconocí el proveedor. Podés decir: 'mi api de groq es gsk_xxx', 'mi api de openrouter es sk-or-xxx'. Proveedores: {providers}."

    # Extraer el valor de la key del texto
    # Patrones: "es gsk_xxx", "key: gsk_xxx", ": gsk_xxx", "= gsk_xxx"
    m = re.search(r"(?:es|key|token|:|\s|=)\s*([A-Za-z0-9_\-]{15,})", texto)
    if not m:
        return f"No pude extraer el valor. Decí por ejemplo: 'mi api de groq es gsk_xxxxx'"

    value = m.group(1).strip()
    if len(value) < 15 or "..." in value:
        return f"La key parece inválida: '{value}'. Asegurate de pegar el valor completo."

    # Escribir en .env
    env_path = Path(__file__).parents[3] / ".env"
    if not env_path.exists():
        # crear .env mínimo si no existe
        env_path.write_text(f"{env_key}={value}\n", encoding="utf-8")
    else:
        content = env_path.read_text(encoding="utf-8")
        pattern = rf"^{re.escape(env_key)}=.*$"
        if re.search(pattern, content, re.MULTILINE):
            content = re.sub(pattern, f"{env_key}={value}", content, flags=re.MULTILINE)
        else:
            content += f"\n{env_key}={value}\n"
        env_path.write_text(content, encoding="utf-8")

    # Recargar en os.environ y reinicializar router
    os.environ[env_key] = value
    try:
        from dotenv import load_dotenv
        load_dotenv(env_path, override=True)
    except Exception:
        pass

    # Reinicializar el router con las nuevas keys
    try:
        from nova.core import nova_router as _nr
        _nr.router.__init__()
        providers_active = _nr.router._active_provider
        return f"Key de {env_key} guardada y router recargado. Proveedores activos: {providers_active}"
    except Exception as e:
        return f"Key guardada en .env. Reiniciá Nova para activarla. ({e})"


def skill_cambiar_idioma(texto: str) -> str:
    """Cambia el idioma de la sesión. El usuario lo activa explícitamente."""
    try:
        from nova.lang.novaesp import set_session_lang, _LANG_KEYWORDS, _LANG_NAMES
    except ImportError:
        return "Módulo de idioma no disponible."

    texto_lower = texto.lower().strip()
    for keyword, code in _LANG_KEYWORDS.items():
        if keyword in texto_lower:
            return set_session_lang(code)

    nombres = ", ".join(f"{v} ({k})" for k, v in _LANG_NAMES.items() if k != "es")
    return f"No reconocí el idioma. Podés pedir: {nombres}. O 'vuelve al español'."


def skill_editar_proyecto(texto: str) -> str:
    """
    Edita o crea un archivo del proyecto activo usando un agente especializado.
    Ej: 'modifica src/monitor.py para agregar alertas por email cuando CPU > 90%'
    Ej: 'crea tests/test_monitor.py con pytest'
    """
    if not _HAS_SPECIALIST:
        return "Módulo de especialistas no disponible."
    if not _proyecto_activo:
        return "No hay proyecto activo. Usa 'abre proyecto [ruta]' primero."

    base = _proyecto_activo["path"]

    # Detectar si es un archivo específico
    m = re.match(r"(?:modifica(?:r)?|edita(?:r)?|actualiza(?:r)?|crea(?:r)?)\s+([\w./\-]+\.\w+)\s+(?:para\s+|con\s+)?(.+)", texto, re.IGNORECASE)
    if not m:
        # Sin archivo específico: tarea general sobre el proyecto
        archivo_rel = None
        tarea = texto
    else:
        archivo_rel = m.group(1).strip()
        tarea = m.group(2).strip()

    # Leer contexto del archivo si existe
    contexto_actual = ""
    if archivo_rel:
        target = base / archivo_rel
        if target.exists():
            contenido = target.read_text(encoding="utf-8", errors="replace")
            contexto_actual = f"\nCurrent content of {archivo_rel}:\n```\n{contenido[:2000]}\n```\n"

    # Leer estructura del proyecto como contexto
    archivos_proyecto = [str(f.relative_to(base)) for f in base.rglob("*") if f.is_file() and ".git" not in f.parts]
    estructura = "\n".join(archivos_proyecto[:20])

    # Elegir agente según extensión
    agente = "software architect"
    if archivo_rel:
        ext = Path(archivo_rel).suffix.lower()
        if ext in (".c", ".h", ".cpp"):
            agente = "embedded firmware engineer"
        elif ext in (".py",):
            agente = "ai engineer"
        elif ext in (".js", ".ts", ".jsx", ".tsx"):
            agente = "frontend developer"

    agent = _find_agent(agente)
    if not agent:
        return f"No encontré agente '{agente}'."

    from nova.connectors.nova_specialist import (
        _PROJECT_SYSTEM_SUFFIX, _parse_file_blocks, _write_project_files,
        _call_openrouter, _call_groq, _OR_TEXT_MODELS,
    )

    system = agent["system"] + _PROJECT_SYSTEM_SUFFIX
    prompt = (
        f"Project: {base.name}\n"
        f"Files in project:\n{estructura}\n"
        f"{contexto_actual}"
        f"\nTask: {tarea}\n"
        f"{'Output the modified/created file using === FILE: path === format.' if archivo_rel else 'Output ALL modified or new files using === FILE: path === format.'}"
    )

    resp = None
    for gm in ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]:
        resp = _call_groq(system, prompt + "\n\n(Use fenced code blocks inside === FILE: === markers)", model=gm)
        if resp:
            break
    if not resp:
        or_models = ["minimax/minimax-m2.5:free", "nvidia/nemotron-3-super-120b-a12b:free", "google/gemma-4-31b-it:free"]
        for om in or_models:
            resp = _call_openrouter(system, prompt + "\n\n(Use fenced code blocks inside === FILE: === markers)", model=om)
            if resp:
                break

    if not resp:
        return "No pude conectarme al LLM."

    files = _parse_file_blocks(resp)
    if not files:
        return f"El agente respondió pero no generó archivos en el formato esperado:\n{resp[:500]}"

    created = _write_project_files(files, base)
    return f"✓ Archivos actualizados en {base.name}:\n" + "\n".join(f"  • {f}" for f in created)


def skill_generar_tests(texto: str) -> str:
    """
    Genera tests pytest para un archivo del proyecto activo.
    Ej: 'genera tests para src/monitor.py'
    Ej: 'testea el archivo utils.py'
    """
    if not _HAS_SPECIALIST:
        return "Módulo de especialistas no disponible."
    if not _proyecto_activo:
        return "No hay proyecto activo. Usa 'abre proyecto [ruta]' primero."

    base = _proyecto_activo["path"]

    # Detectar archivo objetivo
    m = re.search(r"([\w./\-]+\.py)", texto)
    if m:
        target = base / m.group(1).strip()
        if not target.exists():
            # Buscar sin prefijo de directorio
            matches = list(base.rglob(m.group(1).strip()))
            target = matches[0] if matches else None
    else:
        # Sin archivo específico: testear todos los .py modificados recientemente
        import subprocess
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            cwd=base, capture_output=True, text=True
        )
        py_files = [base / f.strip() for f in result.stdout.splitlines()
                    if f.strip().endswith(".py") and not "test_" in f]
        target = py_files[0] if py_files else None

    if not target or not target.exists():
        return f"No encontré archivo Python para testear en {base.name}."

    code = target.read_text(encoding="utf-8", errors="replace")
    result = _generar_tests(code, target, base, run=True)
    return f"Tests para {target.relative_to(base)}:\n{result}"


def skill_lsp_definicion(texto: str) -> str:
    """
    Busca dónde está definida una función, clase o variable.
    Ej: 'dónde está definida la función ejecutar_con_feedback'
    Ej: 'definición de NovaHUD'
    """
    if not _HAS_LSP:
        return "LSP no disponible. Instala jedi: pip install jedi"
    m = re.search(r"(?:función|clase|variable|def|class)?\s+['\"]?(\w+)['\"]?", texto, re.IGNORECASE)
    symbol = m.group(1) if m else texto.strip().split()[-1]
    base = _proyecto_activo["path"] if _proyecto_activo else Path.cwd()
    return _lsp_find_symbol(symbol, base)


def skill_lsp_referencias(texto: str) -> str:
    """
    Busca dónde se usa un símbolo en el proyecto.
    Ej: 'dónde se usa speak'
    Ej: 'referencias a skill_git_commit'
    """
    if not _HAS_LSP:
        return "LSP no disponible."
    m = re.search(r"(?:usa[n]?|referencia[s]?|llam[a-z]+)\s+(?:a\s+)?['\"]?(\w+)['\"]?", texto, re.IGNORECASE)
    if not m:
        m = re.search(r"\b(\w+)\b\s*$", texto)
    symbol = m.group(1) if m else texto.strip().split()[-1]
    base = _proyecto_activo["path"] if _proyecto_activo else Path.cwd()
    return _lsp_find_symbol(symbol, base)


def skill_lsp_analizar(texto: str) -> str:
    """
    Analiza un archivo Python del proyecto: funciones, clases, imports, errores.
    Ej: 'analiza nova_skills.py'
    Ej: 'qué funciones tiene nova_specialist.py'
    """
    if not _HAS_LSP:
        return "LSP no disponible."
    m = re.search(r"([\w./\-]+\.py)", texto)
    if not m:
        return "Indicá el archivo Python a analizar. Ej: 'analiza nova_router.py'"
    base = _proyecto_activo["path"] if _proyecto_activo else Path.cwd()
    fname = m.group(1).strip()
    candidates = [base / fname] + list(base.rglob(fname))
    target = next((p for p in candidates if p.exists()), None)
    if not target:
        return f"No encontré '{fname}' en el proyecto."
    result = _lsp_analyze(target, base)
    if "error" in result:
        return result["error"]
    symbols = result.get("symbols", [])
    imports = result.get("imports", [])
    diag    = result.get("diagnostics", "")
    lines = [f"**{result['file']}**"]
    if symbols:
        funcs   = [s["name"] if isinstance(s, dict) else s for s in symbols
                   if not isinstance(s, dict) or s.get("type") == "function"]
        classes = [s["name"] if isinstance(s, dict) else "" for s in symbols
                   if isinstance(s, dict) and s.get("type") == "class"]
        if classes:
            lines.append(f"Clases ({len(classes)}): {', '.join(filter(None, classes))}")
        if funcs:
            lines.append(f"Funciones ({len(funcs)}): {', '.join(funcs[:15])}" +
                         (f" y {len(funcs)-15} más" if len(funcs) > 15 else ""))
    if imports:
        lines.append(f"Imports: {', '.join(imports[:8])}")
    lines.append(f"Diagnóstico: {diag}")
    return "\n".join(lines)


def skill_lsp_diagnostico(texto: str) -> str:
    """
    Diagnóstico de errores de sintaxis en un archivo Python.
    Ej: 'hay errores en nova_router.py'
    Ej: 'diagnostica el archivo main.py'
    """
    if not _HAS_LSP:
        return "LSP no disponible."
    m = re.search(r"([\w./\-]+\.py)", texto)
    if not m:
        return "Indicá el archivo a diagnosticar."
    base = _proyecto_activo["path"] if _proyecto_activo else Path.cwd()
    fname = m.group(1).strip()
    candidates = [base / fname] + list(base.rglob(fname))
    target = next((p for p in candidates if p.exists()), None)
    if not target:
        return f"No encontré '{fname}'."
    source = target.read_text(encoding="utf-8", errors="replace")
    return _lsp_diagnose(source, target, base)


def skill_lsp_renombrar(texto: str) -> str:
    """
    Renombra un símbolo en un archivo Python de forma segura (todas las ocurrencias).
    Ej: 'renombra función old_name a new_name en archivo.py'
    Ej: 'renombra speak por hablar en novaesp.py'
    """
    if not _HAS_LSP:
        return "LSP no disponible."
    # Detectar: renombra X por/a Y en archivo.py
    m = re.search(
        r"renombr[a-z]+\s+(?:\w+\s+)?['\"]?(\w+)['\"]?\s+(?:por|a|as|→|->)\s+['\"]?(\w+)['\"]?"
        r"(?:\s+en\s+([\w./\-]+\.py))?",
        texto, re.IGNORECASE
    )
    if not m:
        return ("Formato: 'renombra [función] X por Y en archivo.py'\n"
                "Ej: 'renombra speak por hablar en novaesp.py'")
    old_name, new_name, fname = m.group(1), m.group(2), m.group(3)
    if not fname:
        return f"Indicá el archivo donde renombrar '{old_name}' → '{new_name}'."
    base = _proyecto_activo["path"] if _proyecto_activo else Path.cwd()
    candidates = [base / fname] + list(base.rglob(fname))
    target = next((p for p in candidates if p.exists()), None)
    if not target:
        return f"No encontré '{fname}'."
    source = target.read_text(encoding="utf-8", errors="replace")
    new_source, summary = _lsp_rename(old_name, new_name, target, source, base)
    if new_source != source:
        target.write_text(new_source, encoding="utf-8")
        return f"✓ {summary}\nArchivo actualizado: {target.relative_to(base)}"
    return f"Sin cambios. {summary}"


def skill_dockerizar(texto: str) -> str:
    """
    Genera Dockerfile + docker-compose.yml para el proyecto activo.
    Detecta el stack automáticamente (Python, Node, Go, etc.).
    Ej: 'dockeriza este proyecto'
    Ej: 'genera el dockerfile del proyecto'
    """
    if not _HAS_SPECIALIST:
        return "Módulo de especialistas no disponible."

    # Resolver directorio objetivo
    m = re.search(r"(~/|/|\./)[\w./\- ]+", texto)
    if m:
        base_str = m.group(0).strip()
    elif _proyecto_activo:
        base_str = str(_proyecto_activo["path"])
    else:
        return "No hay proyecto activo. Usa 'abre proyecto [ruta]' primero o indica la ruta."

    return _dockerizar(base_str)


def skill_deploy_local(texto: str) -> str:
    """
    Levanta el proyecto en un contenedor local usando docker-compose.
    Ej: 'levanta el proyecto en docker'
    Ej: 'deploy local del proyecto'
    """
    if not _HAS_SPECIALIST:
        return "Módulo de especialistas no disponible."

    m = re.search(r"(~/|/|\./)[\w./\- ]+", texto)
    if m:
        base_str = m.group(0).strip()
    elif _proyecto_activo:
        base_str = str(_proyecto_activo["path"])
    else:
        return "No hay proyecto activo. Usa 'abre proyecto [ruta]' primero."

    return _deploy_local(base_str)


def skill_codear_con_docs(texto: str) -> str:
    """
    Busca documentación real en la web y genera código con un especialista.
    Ej: '¿cómo implemento rate limiting en FastAPI?'
    Ej: 'ejemplo de autenticación JWT con Django'
    """
    if not _HAS_SPECIALIST:
        return "Módulo de especialistas no disponible."

    # Detectar agente más apropiado según el framework mencionado
    lower = texto.lower()
    agente = "backend architect"
    if any(k in lower for k in ("react", "vue", "angular", "nextjs", "css", "html", "frontend")):
        agente = "frontend developer"
    elif any(k in lower for k in ("pytorch", "tensorflow", "sklearn", "pandas", "numpy", "ml", "modelo")):
        agente = "ai engineer"
    elif any(k in lower for k in ("docker", "kubernetes", "terraform", "ci", "cd", "devops")):
        agente = "devops automator"
    elif any(k in lower for k in ("esp32", "arduino", "freertos", "firmware", "embedded")):
        agente = "embedded firmware engineer"

    return _codear_con_docs(texto, agente_query=agente)


def skill_mejorar_proyecto(texto: str = "") -> str:
    """
    Lanza múltiples agentes en paralelo para mejorar el proyecto activo.
    Cada agente trabaja en un aspecto distinto simultáneamente.
    Uso: 'mejora el proyecto' o 'mejora el proyecto: agrega UI, corrige bugs, documenta'
    """
    if not _HAS_SPECIALIST:
        return "Módulo de especialistas no disponible."

    base = _resolver_proyecto(texto if texto and ("/" in texto or "~" in texto) else "")
    if not base:
        return "No hay proyecto activo. Usa 'abre proyecto [ruta]' primero."

    # Leer archivos del proyecto para detectar el stack
    archivos = [str(f.relative_to(base)) for f in base.rglob("*")
                if f.is_file() and ".git" not in f.parts]
    exts = {Path(f).suffix.lower() for f in archivos}

    # Detectar lenguaje principal
    es_python = ".py" in exts
    es_c = ".c" in exts or ".h" in exts
    es_js = ".js" in exts or ".ts" in exts

    # Construir tareas según lo que el usuario pidió o usar defaults inteligentes
    texto_lower = texto.lower()

    # Parsear tareas explícitas del texto: "agrega UI, corrige bugs, documenta"
    tareas_texto = []
    if ":" in texto:
        parte = texto.split(":", 1)[1]
        tareas_texto = [t.strip() for t in re.split(r"[,;]", parte) if t.strip()]

    if tareas_texto:
        # Asignar agente automáticamente a cada tarea pedida
        def _agente_para_tarea(t: str) -> str:
            t_low = t.lower()
            if any(w in t_low for w in ["ui", "interfaz", "visual", "dashboard", "grafico", "gráfico"]):
                return "frontend developer" if es_js else "ai engineer"
            if any(w in t_low for w in ["bug", "error", "corrige", "fix", "arregla"]):
                return "code reviewer"
            if any(w in t_low for w in ["test", "prueba", "pytest", "unittest"]):
                return "code reviewer"
            if any(w in t_low for w in ["doc", "readme", "comentario"]):
                return "technical writer"
            if any(w in t_low for w in ["alert", "notif", "email", "aviso"]):
                return "ai engineer"
            if any(w in t_low for w in ["optimiz", "rendimiento", "performance"]):
                return "software architect"
            return "ai engineer"

        tareas = [{"agente": _agente_para_tarea(t), "tarea": t, "label": t[:30]} for t in tareas_texto]
    else:
        # Tareas default: 3 mejoras complementarias en paralelo
        if es_python:
            tareas = [
                {"agente": "ai engineer",      "label": "UI Rich",
                 "tarea": "Agrega una interfaz visual en terminal usando la librería 'rich' (tabla en tiempo real con CPU%, RAM%, timestamp). El script debe mostrar los datos en pantalla mientras escribe el CSV."},
                {"agente": "code reviewer",    "label": "Bug Fix",
                 "tarea": "Corrige el bug donde la cabecera CSV se escribe múltiples veces porque csvfile.tell()==0 no funciona en modo append. Usa os.path.exists() para detectar si el archivo ya existe antes de escribir la cabecera."},
                {"agente": "technical writer", "label": "Docs",
                 "tarea": "Mejora el README.md: agrega sección de uso con ejemplos, sección de configuración explicando config.json, y badge de Python version."},
            ]
        elif es_c:
            tareas = [
                {"agente": "embedded firmware engineer", "label": "Error handling",
                 "tarea": "Agrega manejo de errores robusto: verifica retornos de I2C, agrega timeouts, usa ESP_ERROR_CHECK donde corresponda."},
                {"agente": "code reviewer", "label": "Code Review",
                 "tarea": "Revisa el código C: detecta memory leaks, variables no inicializadas, y posibles buffer overflows."},
                {"agente": "technical writer", "label": "Docs",
                 "tarea": "Agrega comentarios Doxygen a todas las funciones públicas y mejora el README con el pinout y dependencias."},
            ]
        else:
            tareas = [
                {"agente": "software architect", "label": "Arquitectura",
                 "tarea": "Refactoriza el proyecto para mejor separación de responsabilidades."},
                {"agente": "code reviewer",      "label": "Code Review",
                 "tarea": "Revisa el código, corrige bugs y mejora el manejo de errores."},
                {"agente": "technical writer",   "label": "Docs",
                 "tarea": "Mejora la documentación y el README."},
            ]

    log.info("[Orquestador] Lanzando %d agentes sobre '%s'", len(tareas), base.name)
    for t in tareas:
        log.debug("  → [%s] %s: %s", t['label'], t['agente'], t['tarea'][:60])

    return _mejorar_paralelo(base, tareas)


def skill_planear_misiones(texto: str = "") -> str:
    """
    Analiza el proyecto activo y propone misiones de mejora específicas.
    Un LLM planifica qué especialistas hacer trabajar y en qué.
    Uso: 'qué misiones propones para el proyecto' o 'cómo mejorarías la UI del detector'
    """
    if not _HAS_SPECIALIST:
        return "Módulo de especialistas no disponible."

    base = _resolver_proyecto("")
    if not base:
        return "No hay proyecto activo. Usa 'abre proyecto [ruta]' primero."

    # Extraer foco del usuario (quitar trigger words)
    foco = re.sub(
        r"^(qué misiones|cómo mejorar[ías]*|propone[s]?|planea[r]?|analiza[r]?|"
        r"misiones para|mejoras para|como mejorarias|qué harías con|"
        r"que misiones|como mejorar)\s*",
        "", texto, flags=re.IGNORECASE
    ).strip()
    foco = re.sub(r"^(el|la|los|las|del|de|un|una)\s+", "", foco, flags=re.I).strip()
    # Quitar "proyecto" al inicio si quedó
    foco = re.sub(r"^proyecto\s+", "", foco, flags=re.I).strip()

    log.info("[Orquestador] Analizando proyecto '%s' para proponer misiones", base.name)
    misiones = _planear_mejoras(base, foco=foco)

    global _misiones_pendientes
    _misiones_pendientes = misiones

    return _formatear_misiones(misiones)


def skill_ejecutar_misiones(texto: str = "") -> str:
    """
    Ejecuta misiones propuestas por skill_planear_misiones.
    Uso: 'ejecutar misiones 1,2,3' o 'ejecutar todas las misiones'
    """
    if not _HAS_SPECIALIST:
        return "Módulo de especialistas no disponible."

    base = _resolver_proyecto("")
    if not base:
        return "No hay proyecto activo."

    global _misiones_pendientes
    if not _misiones_pendientes:
        return "No hay misiones pendientes. Di 'qué misiones propones' primero."

    # Parsear qué misiones ejecutar
    texto_lower = texto.lower()
    if any(w in texto_lower for w in ["todas", "all", "todo"]):
        seleccion = list(range(len(_misiones_pendientes)))
    else:
        nums = re.findall(r"\d+", texto)
        seleccion = [int(n) - 1 for n in nums if 0 < int(n) <= len(_misiones_pendientes)]

    if not seleccion:
        return (
            f"No entendí qué misiones ejecutar. Hay {len(_misiones_pendientes)} misiones.\n"
            "Di 'ejecutar misiones 1,2' o 'ejecutar todas las misiones'."
        )

    tareas = [_misiones_pendientes[i] for i in seleccion]
    log.info("[Orquestador] Ejecutando %d misión(es) sobre '%s'", len(tareas), base.name)
    for t in tareas:
        log.debug('  → [%s] %s: %s', t.get('label','?'), t.get('agente','?'), t.get('tarea','')[:70])

    resultado = _mejorar_paralelo(base, tareas)

    # Limpiar misiones ejecutadas
    ejecutados = set(seleccion)
    _misiones_pendientes = [m for i, m in enumerate(_misiones_pendientes) if i not in ejecutados]

    return resultado


def skill_estructura_proyecto(texto: str = "") -> str:
    """Muestra la estructura del proyecto activo o de uno dado."""
    path = _resolver_proyecto(texto)
    if not path:
        return "No hay proyecto activo. Usa 'abre proyecto [ruta]'."
    archivos = [str(f.relative_to(path)) for f in sorted(path.rglob("*")) if f.is_file() and ".git" not in f.parts]
    return f"📁 {path.name} ({len(archivos)} archivos):\n" + "\n".join(f"  {a}" for a in archivos[:40])


# ══════════════════════════════════════════════════════════════
# 7b. GOOGLE DRIVE — archivos
# ══════════════════════════════════════════════════════════════

def skill_drive_buscar(texto: str) -> str:
    """Busca archivos en Drive. Ej: 'busca el archivo presupuesto 2026'"""
    if not _HAS_N8N:
        return "Módulo n8n no disponible, Señor."
    import re
    # Extraer término de búsqueda — quitar el trigger y quedarnos con lo relevante
    query = re.sub(
        r"^(?:busca[r]?|encontra[r]?|busca en drive|busca en mi drive|"
        r"encontra[r]? en drive|abri[r]?|abre)\s+(?:el\s+|la\s+|un\s+|una\s+)?(?:archivo|carpeta|documento|doc|file)?\s*",
        "", texto, flags=re.I
    ).strip()
    if not query:
        query = texto
    resp = n8n.drive_buscar_detalle(query)
    archivos = resp.get("archivos", [])
    if not archivos:
        return f"No encontré archivos con '{query}' en Drive, Señor."
    resumen = resp.get("resumen", "")
    # Guardar IDs en memoria temporal para acciones posteriores
    _drive_last_results.clear()
    _drive_last_results.extend(archivos)
    return resumen


def skill_drive_leer(texto: str) -> str:
    """Lee un archivo de Drive por nombre o ID."""
    if not _HAS_N8N:
        return "Módulo n8n no disponible, Señor."
    import re
    # Intentar encontrar un ID explícito
    id_match = re.search(r'\b([A-Za-z0-9_-]{25,})\b', texto)
    if id_match:
        return n8n.drive_leer(id_match.group(1))
    # Si hay resultados previos de búsqueda, usar el primero
    if _drive_last_results:
        archivo = _drive_last_results[0]
        return f"Leyendo '{archivo['nombre']}':\n" + n8n.drive_leer(archivo['id'])
    # Buscar primero por nombre y leer
    nombre = re.sub(r"^(?:lee|leer?|abri[r]?|abre|mostra[r]?|muestra)\s+(?:el\s+|la\s+)?(?:archivo|documento|doc)?\s*",
                    "", texto, flags=re.I).strip()
    resp = n8n.drive_buscar_detalle(nombre)
    archivos = resp.get("archivos", [])
    if not archivos:
        return f"No encontré '{nombre}' en Drive, Señor."
    archivo = archivos[0]
    return f"'{archivo['nombre']}':\n" + n8n.drive_leer(archivo['id'])


def skill_drive_crear(texto: str) -> str:
    """Crea un documento en Drive. Ej: 'crea un documento llamado Informe Mayo'"""
    if not _HAS_N8N:
        return "Módulo n8n no disponible, Señor."
    import re
    # Extraer nombre — lo que venga después de "llamado/titulado/con nombre"
    m = re.search(r'(?:llamad[oa]|tituladl?[oa]?|con nombre|nombre)\s+(.+)', texto, re.I)
    if m:
        nombre = m.group(1).strip().rstrip('.,')
    else:
        nombre = re.sub(
            r"^(?:crea[r]?|hace[r]?|genera[r]?|nuevo)\s+(?:un\s+|una\s+)?(?:documento|doc|archivo|nota)\s*",
            "", texto, flags=re.I
        ).strip() or "Nuevo documento"
    return n8n.drive_crear(nombre)


def skill_drive_listar(_=None) -> str:
    """Lista archivos en Mi Drive."""
    if not _HAS_N8N:
        return "Módulo n8n no disponible, Señor."
    return n8n.drive_listar()


# Buffer temporal para resultados de búsqueda (permite "lee ese archivo" después de buscar)
_drive_last_results: list = []


# ══════════════════════════════════════════════════════════════
# 7b. EMAIL — consulta y acciones
# ══════════════════════════════════════════════════════════════

def skill_gmail_no_leidos(texto: str = "") -> str:
    """Lista emails no leídos directo de Gmail (sin n8n)."""
    if not _HAS_GOOGLE:
        return skill_emails(texto)
    import re
    try:
        emails = _goog.gmail.listar_no_leidos(max_results=10)
        if not emails:
            return "No tenés emails sin leer, Señor."
        texto_l = texto.lower()
        # Filtrar por categoría si se menciona
        filtro = ""
        for cat in ["banco", "trabajo", "netflix", "factura", "indeed", "youtube"]:
            if cat in texto_l:
                filtro = cat
                break
        if filtro:
            emails = [e for e in emails if filtro in (e["de"] + e["asunto"]).lower()]
            if not emails:
                return f"No encontré emails de '{filtro}', Señor."
        partes = [f"Tenés {len(emails)} email{'s' if len(emails)>1 else ''} sin leer, Señor:"]
        for e in emails[:5]:
            partes.append(f"• De {e['de'].split('<')[0].strip()[:30]}: {e['asunto'][:50]}")
        if len(emails) > 5:
            partes.append(f"...y {len(emails)-5} más.")
        return "\n".join(partes)
    except Exception as ex:
        log.warning("Gmail directo falló: %s", ex)
        return skill_emails(texto)


def skill_gmail_buscar(texto: str = "") -> str:
    """Busca emails (leídos y no leídos) por remitente, asunto o palabra clave."""
    if not _HAS_GOOGLE:
        return skill_buscar_email(texto)
    import re
    query = re.sub(
        r"^(?:busca[r]?|encontra[r]?|busca(?:me)?|buscar?)\s+"
        r"(?:el\s+|un\s+)?(?:mail|email|correo)\s+(?:de|sobre|del?|con)?\s*",
        "", texto, flags=re.IGNORECASE
    ).strip() or texto.strip()
    if not query:
        return "¿Qué email busco, Señor?"
    try:
        emails = _goog.gmail.buscar(query, max_results=5)
        if not emails:
            return f"No encontré emails para '{query}', Señor."
        partes = [f"Encontré {len(emails)} email{'s' if len(emails)>1 else ''} para '{query}', Señor:"]
        for e in emails:
            estado = "●" if not e["leido"] else "✓"
            partes.append(f"{estado} De {e['de'].split('<')[0].strip()[:30]}: {e['asunto'][:50]}")
        return "\n".join(partes)
    except Exception as ex:
        log.warning("Gmail buscar falló: %s", ex)
        return skill_buscar_email(texto)


def skill_calendar(texto: str = "") -> str:
    """Consulta eventos de Google Calendar directo (sin n8n)."""
    if not _HAS_GOOGLE:
        return skill_consultar_calendario(texto) if _HAS_N8N else "Calendar no disponible, Señor."
    import re
    texto_l = texto.lower()
    fecha = "mañana" if "mañana" in texto_l else "semana" if "semana" in texto_l else "hoy"
    try:
        eventos = _goog.calendar.eventos(fecha)
        if not eventos:
            label = {"hoy": "hoy", "mañana": "mañana", "semana": "esta semana"}[fecha]
            return f"No tenés eventos {label}, Señor."
        label = {"hoy": "hoy", "mañana": "mañana", "semana": "esta semana"}[fecha]
        if len(eventos) == 1:
            e = eventos[0]
            return f"Tenés un evento {label}: {e['titulo']} a las {e['hora']}, Señor."
        partes = [f"Tenés {len(eventos)} eventos {label}, Señor:"]
        for e in eventos[:5]:
            partes.append(f"• {e['hora']} - {e['titulo']}")
        return "\n".join(partes)
    except Exception as ex:
        log.warning("Calendar directo falló: %s", ex)
        return "No pude acceder al calendario, Señor. El token puede estar vencido — re-autenticá en n8n."


def skill_drive_buscar_directo(texto: str = "") -> str:
    """Busca archivos en Google Drive directo."""
    if not _HAS_GOOGLE:
        return "Drive no disponible, Señor."
    import re
    query = re.sub(r"^(?:busca[r]?|encontra[r]?)\s+(?:en\s+drive\s+)?", "", texto, flags=re.IGNORECASE).strip()
    if not query:
        return "¿Qué archivo busco en Drive, Señor?"
    try:
        archivos = _goog.drive.buscar(query)
        if not archivos:
            return f"No encontré '{query}' en Drive, Señor."
        partes = [f"Encontré {len(archivos)} archivo{'s' if len(archivos)>1 else ''} en Drive, Señor:"]
        for f in archivos[:5]:
            partes.append(f"• {f['name']}")
        return "\n".join(partes)
    except Exception as ex:
        log.warning("Drive directo falló: %s", ex)
        return "No pude acceder a Drive, Señor."


# ─── Git-aware workflow ────────────────────────────────────────────────────────

def _git_run(*args, cwd: str | None = None) -> tuple[str, int]:
    """Ejecuta un comando git y devuelve (stdout+stderr, returncode)."""
    base = str(_proyecto_activo["path"]) if _proyecto_activo else None
    wd = cwd or base or str(Path.cwd())
    try:
        r = subprocess.run(
            ["git", *args], cwd=wd, capture_output=True, text=True, timeout=15
        )
        out = (r.stdout + r.stderr).strip()
        return out, r.returncode
    except FileNotFoundError:
        return "git no está instalado o no está en PATH.", 1
    except subprocess.TimeoutExpired:
        return "Tiempo de espera agotado.", 1


def skill_git_status(texto: str = "") -> str:
    """Muestra el estado del repositorio git del proyecto activo."""
    out, rc = _git_run("status", "--short", "--branch")
    if rc != 0:
        return f"No es un repositorio git o hubo un error:\n{out}"
    if not out.strip():
        return "El repositorio está limpio, Señor. No hay cambios pendientes."
    lines = out.splitlines()
    rama = lines[0].lstrip("#").strip() if lines else ""
    cambios = [l for l in lines[1:] if l.strip()]
    if not cambios:
        return f"Repositorio limpio en {rama}."
    partes = [f"Estado del repositorio — {rama}:"]
    for c in cambios[:20]:
        estado, archivo = c[:2].strip(), c[3:].strip()
        partes.append(f"  {estado}  {archivo}")
    if len(cambios) > 20:
        partes.append(f"  ... y {len(cambios)-20} cambios más")
    return "\n".join(partes)


def skill_git_diff(texto: str = "") -> str:
    """Muestra el diff de cambios no commiteados (máx 80 líneas)."""
    out, rc = _git_run("diff", "--stat")
    stat = out.strip()
    out2, _ = _git_run("diff", "--unified=3")
    lines = out2.splitlines()
    if not lines and not stat:
        out3, _ = _git_run("diff", "--cached", "--stat")
        if out3.strip():
            return f"Solo hay cambios en staging:\n{out3}"
        return "No hay cambios para mostrar, Señor."
    MAX = 80
    if len(lines) > MAX:
        recortado = f"\n... [{len(lines)-MAX} líneas omitidas] ..."
        lines = lines[:MAX]
    else:
        recortado = ""
    return f"{stat}\n\n" + "\n".join(lines) + recortado


def skill_git_log(texto: str = "") -> str:
    """Muestra el historial reciente de commits."""
    n = 10
    m = re.search(r"(\d+)\s+(?:últimos?|últimas?|commits?|cambios?)", (texto or "").lower())
    if m:
        n = min(int(m.group(1)), 30)
    out, rc = _git_run("log", f"--oneline", f"-{n}")
    if rc != 0:
        return f"No pude leer el historial: {out}"
    if not out.strip():
        return "No hay commits en este repositorio aún."
    return f"Últimos {n} commits:\n" + out


def skill_git_commit(texto: str = "") -> str:
    """Hace commit de los cambios con el mensaje dado, o genera uno con LLM si no se da."""
    # Verificar que hay cambios
    status_out, _ = _git_run("status", "--short")
    if not status_out.strip():
        return "No hay cambios para commitear, Señor."

    # Extraer mensaje del texto del usuario
    msg = re.sub(
        r"^(?:commit|haz?\s+(?:un\s+)?commit|guarda[r]?\s+(?:los?\s+)?cambios?)"
        r"(?:\s+(?:con\s+(?:mensaje|msg)\s+)?[:\-]?\s*)?",
        "", texto, flags=re.IGNORECASE
    ).strip().strip('"\'')

    # Si no hay mensaje, generarlo con LLM
    if not msg and _router:
        diff_out, _ = _git_run("diff", "--stat")
        files_out, _ = _git_run("diff", "--name-only")
        try:
            resp = _router.route(
                messages=[
                    {"role": "system", "content": (
                        "Generate a concise git commit message (max 72 chars) in Spanish "
                        "following conventional commits format (feat/fix/refactor/docs/etc). "
                        "Return ONLY the commit message, no quotes or explanation."
                    )},
                    {"role": "user", "content": f"Archivos modificados:\n{files_out}\n\nStat:\n{diff_out}"},
                ],
                force_tier=1, max_tokens=80, temperature=0.3,
            )
            msg = resp["response"].strip().strip('"\'')
        except Exception:
            pass

    if not msg:
        return "¿Cuál es el mensaje del commit, Señor?"

    # Agregar todos los cambios y commitear
    _git_run("add", "-A")
    out, rc = _git_run("commit", "-m", msg)
    if rc != 0:
        return f"Error al commitear:\n{out}"
    return f"Commit realizado, Señor:\n  {msg}\n\n{out.splitlines()[0] if out else ''}"


def skill_git_pr(texto: str = "") -> str:
    """Genera una descripción de Pull Request con LLM basada en los commits del branch actual."""
    # Commits vs main/master
    for base in ("main", "master", "develop"):
        log_out, rc = _git_run("log", f"{base}...HEAD", "--oneline")
        if rc == 0:
            break
    else:
        log_out, _ = _git_run("log", "--oneline", "-10")

    diff_stat, _ = _git_run("diff", "--stat", "HEAD~1")

    if not log_out.strip():
        return "No hay commits nuevos respecto a la rama base, Señor."

    if not _router:
        return f"Commits en este branch:\n{log_out}"

    try:
        resp = _router.route(
            messages=[
                {"role": "system", "content": (
                    "You are a senior developer. Write a Pull Request description in Spanish with:\n"
                    "## Resumen\n- bullet points\n## Cambios\n- bullet points\n## Testing\n- bullet points\n"
                    "Keep it concise and professional."
                )},
                {"role": "user", "content": f"Commits:\n{log_out}\n\nStat:\n{diff_stat}"},
            ],
            force_tier=2, max_tokens=400, temperature=0.4,
        )
        return f"Descripción de PR generada:\n\n{resp['response']}"
    except Exception as ex:
        return f"No pude generar la descripción: {ex}"


def skill_imagen(texto: str = "") -> str:
    """Genera una imagen a partir de texto. Ej: 'generá una imagen de un castillo'."""
    if not _HAS_IMAGE:
        return "Módulo de imágenes no disponible, Señor."

    texto_l = texto.lower()

    # Detectar estilo
    estilo = "default"
    if any(w in texto_l for w in ["foto", "fotorealis", "real", "fotográfi"]):
        estilo = "foto"
    elif any(w in texto_l for w in ["anime", "animé", "manga", "cartoon"]):
        estilo = "anime"
    elif any(w in texto_l for w in ["3d", "tridimensional", "render"]):
        estilo = "3d"
    elif any(w in texto_l for w in ["rápido", "rapido", "rápida", "quick", "turbo"]):
        estilo = "rapido"

    # Detectar dimensiones
    ancho, alto = 1024, 1024
    if any(w in texto_l for w in ["horizontal", "landscape", "panorama", "wide"]):
        ancho, alto = 1792, 1024
    elif any(w in texto_l for w in ["vertical", "portrait", "retrato"]):
        ancho, alto = 1024, 1792

    # Limpiar prefijos del prompt
    # "generá/crea/hacé/dibujá/pintá" (arg. imperativo) + "una imagen de X" → X
    prompt = re.sub(
        r"^(?:generar?|genera[r]?|generá|crear?|crea[r]?|creá|hacer?|hace[r]?|hacé|"
        r"dibujar?|dibuja[r]?|dibujá|pintar?|pinta[r]?|pintá|muéstrame|muestra(?:me)?)\s+"
        r"(?:una?\s+)?(?:imagen?|foto|ilustración?|cuadro|dibujo|pintura|render)\s+"
        r"(?:de\s+|del?\s+|estilo\s+\w+\s+(?:de\s+)?)?",
        "", texto, flags=re.IGNORECASE
    ).strip()
    # Si no se limpió, quitar solo el tipo de imagen al inicio
    if prompt == texto.strip():
        prompt = re.sub(
            r"^(?:imagen?|foto|ilustración?|cuadro|dibujo|pintura|render)\s+(?:de\s+|del?\s+)?",
            "", prompt, flags=re.IGNORECASE
        ).strip()

    # Quitar "estilo anime/foto/3d/rápido" del prompt si quedó
    prompt = re.sub(
        r"\s*(?:en\s+estilo\s+|estilo\s+|modo\s+)(?:anime|foto|3d|rápido|rapido|fotorealis\w*)\b",
        "", prompt, flags=re.IGNORECASE
    ).strip()

    if not prompt:
        return "¿De qué quiere la imagen, Señor?"

    # 1. Mejorar prompt con LLM antes de generar
    prompt_final = prompt
    if _router:
        try:
            resp = _router.route(
                messages=[
                    {"role": "system", "content": (
                        "You are an expert prompt engineer for FLUX/Stable Diffusion image generation. "
                        "Expand the user's description into a detailed English prompt (max 100 words). "
                        "CRITICAL RULES:\n"
                        "- PRESERVE all specific model names, weapon names, military terms, brand names, and technical identifiers exactly as given\n"
                        "- A 'mortero' is a MORTAR (artillery weapon that fires projectiles in high arc), NOT a machine gun\n"
                        "- 'Nova' or 'NOVA' is an AI virtual assistant — a futuristic female AI with a sleek holographic interface, glowing blue/purple circuits, and a calm, intelligent presence. When the subject is Nova or an AI assistant, depict her as a sophisticated digital entity, NOT as anything military or abstract.\n"
                        "- If the subject is abstract or a proper name you don't recognize, interpret it creatively as a futuristic/tech concept, NOT as a random unrelated scene\n"
                        "- Include: main subject, lighting, visual style, colors, composition, atmosphere\n"
                        "- Return ONLY the enhanced prompt, no explanations or quotes."
                    )},
                    {"role": "user", "content": prompt},
                ],
                force_tier=2, max_tokens=180, temperature=0.7,
            )
            enhanced = resp["response"].strip().strip('"').strip("'")
            if enhanced and len(enhanced) > len(prompt):
                prompt_final = enhanced
        except Exception:
            pass

    # 2. Generar imagen (steps=28 por defecto en nova_image)
    path = _generar_imagen(prompt_final, estilo=estilo, ancho=ancho, alto=alto)
    if not path:
        return "No pude generar la imagen, Señor. Verificá la conexión a internet."

    _abrir_imagen(path)

    # 3. Analizar la imagen generada
    analisis = ""
    if _HAS_VISION:
        try:
            analisis = _vision_analizar_archivo(
                path,
                "En una oración, describí qué muestra esta imagen: sujeto, estilo y colores principales."
            )
        except Exception:
            pass

    respuesta = f"Imagen generada y abierta, Señor."
    if analisis:
        respuesta += f"\n{analisis}"
    respuesta += f"\n📁 {path}"
    return respuesta


def skill_orquestar(texto: str = "") -> str:
    """Orquesta múltiples agentes en paralelo para responder consultas complejas."""
    if not _HAS_SUBAGENTS:
        return "Módulo de subagentes no disponible, Señor."
    resultado = _orquestar(texto)
    if not resultado:
        return "No identifiqué una tarea multi-agente para eso, Señor."
    return resultado


def skill_analizar_archivo(texto: str = "") -> str:
    """Analiza un archivo con un subagente LLM. Ej: 'analizá el archivo main.py'"""
    if not _HAS_SUBAGENTS:
        return "Módulo de subagentes no disponible, Señor."
    # Extraer ruta del texto
    path = re.sub(
        r"^(?:analiz[aá][r]?|revis[aá][r]?|lee|lee[r]?|examin[aá][r]?|mostr[aá][r]?)\s+"
        r"(?:el\s+)?(?:archivo|fichero|file|código|codigo)?\s*",
        "", texto, flags=re.IGNORECASE
    ).strip().strip("'\"")
    # Instrucción adicional si hay coma
    instruccion = ""
    if "," in path:
        parts = path.split(",", 1)
        path, instruccion = parts[0].strip(), parts[1].strip()
    if not path:
        return "¿Qué archivo analizo, Señor?"
    return _analizar_archivo(path, instruccion)


def skill_analizar_repo(texto: str = "") -> str:
    """Analiza un repositorio git completo en paralelo."""
    if not _HAS_SUBAGENTS:
        return "Módulo de subagentes no disponible, Señor."
    path = re.sub(
        r"^(?:analiz[aá][r]?|revis[aá][r]?|examin[aá][r]?)\s+"
        r"(?:el\s+)?(?:repo(?:sitorio)?|proyecto|project|carpeta)?\s*",
        "", texto, flags=re.IGNORECASE
    ).strip().strip("'\"") or "."
    instruccion = ""
    if "," in path:
        parts = path.split(",", 1)
        path, instruccion = parts[0].strip(), parts[1].strip()
    return _analizar_repo(path, instruccion)


def skill_tarea_compleja(texto: str = "") -> str:
    """Descompone una tarea libre en subtareas paralelas y las ejecuta."""
    if not _HAS_SUBAGENTS:
        return "Módulo de subagentes no disponible, Señor."
    resultado = _descomponer_y_ejecutar(texto)
    if not resultado:
        return "No pude descomponer esa tarea, Señor. Intentá ser más específico."
    return resultado


# ─── Skills de Visión ────────────────────────────────────────────────────────

def skill_ver_pantalla(texto: str = "") -> str:
    """Analiza lo que hay en la pantalla ahora mismo."""
    if not _HAS_VISION:
        return "Módulo de visión no disponible, Señor."
    prompt = re.sub(
        r"^(?:qué ves|que ves|analiz[aá][r]?|describí?|qué hay en|qué estoy viendo|"
        r"mirá|mira|describí?(?:me)?)\s+(?:la\s+)?(?:pantalla|screen|imagen)?",
        "", texto, flags=re.IGNORECASE
    ).strip()
    # Aviso: llava puede tardar 2-3 min en CPU
    import threading
    resultado = [None]
    def _run():
        resultado[0] = _vision_analizar(camara=False, prompt=prompt or "")
    t = threading.Thread(target=_run)
    t.start()
    t.join(timeout=250)
    return resultado[0] or "El análisis visual tardó demasiado, Señor. El modelo de visión corre en CPU en esta máquina."


def skill_ver_camara(texto: str = "") -> str:
    """Captura la cámara y describe lo que ve."""
    if not _HAS_VISION:
        return "Módulo de visión no disponible, Señor."
    prompt = re.sub(
        r"^(?:qué ves|que ves|mirá|mira|analiz[aá][r]?|describí?(?:me)?)\s+"
        r"(?:con\s+la\s+|por\s+la\s+)?(?:cámara|camara|camera|webcam)?",
        "", texto, flags=re.IGNORECASE
    ).strip()
    return _vision_analizar(camara=True, prompt=prompt or "")


def skill_identificar_objeto(_=None) -> str:
    """Usa la cámara para identificar el objeto que tenés enfrente."""
    if not _HAS_VISION:
        return "Módulo de visión no disponible, Señor."
    return _vision_identificar_objeto()


def skill_objeto_a_cad(texto: str = "") -> str:
    """Identifica el objeto en cámara y genera instrucciones / modelo 3D."""
    if not _HAS_VISION:
        return "Módulo de visión no disponible, Señor."
    t = texto.lower()
    software = "AutoCAD" if "autocad" in t else "FreeCAD" if "freecad" in t else "Blender"

    descripcion_cad = _vision_para_cad(software=software)

    # Si vision falló, no proceder con Blender — la descripción sería inútil
    if not descripcion_cad or descripcion_cad.startswith("[vision no disponible"):
        return (
            "No pude ver el objeto con la cámara, Señor — todos los modelos de visión fallaron. "
            "Describime el objeto y lo modelo en Blender."
        )

    # Pipeline completo: si es para Blender y el módulo está disponible, generar el modelo
    if software == "Blender" and _HAS_BLENDER:
        from nova.connectors.nova_blender import crear_con_vision
        return crear_con_vision(descripcion_cad)

    return descripcion_cad


def skill_gestos_activar(texto: str = "") -> str:
    """Activa el detector de gestos. Detecta modo en el texto (pantalla/mesa)."""
    if not _HAS_VISION:
        return "Módulo de visión no disponible, Señor."
    modo = "mesa" if re.search(r"mesa|arena|superficie", texto or "", re.IGNORECASE) else "pantalla"
    return _iniciar_detector(modo=modo)


def skill_gestos_desactivar(_=None) -> str:
    """Desactiva el detector de gestos."""
    if not _HAS_VISION:
        return "Módulo de visión no disponible, Señor."
    return _detener_detector()


def skill_gestos_estado(_=None) -> str:
    if not _HAS_VISION:
        return "Módulo de visión no disponible, Señor."
    return _estado_detector()


def skill_gestos_modo(texto: str = "") -> str:
    """Cambia el modo del detector: pantalla o mesa de arena."""
    if not _HAS_VISION:
        return "Módulo de visión no disponible, Señor."
    estado = _estado_detector()
    if "inactivo" in estado.lower():
        # No está corriendo — arrancar en el modo pedido
        modo = "mesa" if re.search(r"mesa|arena|superficie", texto or "", re.IGNORECASE) else "pantalla"
        return _iniciar_detector(modo=modo)
    # Está corriendo — reiniciar con el nuevo modo
    _detener_detector()
    import time; time.sleep(0.8)
    modo = "mesa" if re.search(r"mesa|arena|superficie", texto or "", re.IGNORECASE) else "pantalla"
    return _iniciar_detector(modo=modo)


def skill_gestos_camara(texto: str = "") -> str:
    """Cambia el índice de cámara del detector (0, 1, 2...)."""
    if not _HAS_VISION:
        return "Módulo de visión no disponible, Señor."
    m = re.search(r"\d+", texto or "")
    idx = int(m.group(0)) if m else 1
    _detener_detector()
    import time; time.sleep(0.5)
    return _iniciar_detector(modo="pantalla", camara=idx)


def skill_gestos_calibrar(_=None) -> str:
    """Inicia calibración del detector de gestos (modo mesa)."""
    if not _HAS_VISION:
        return "Módulo de visión no disponible, Señor."
    estado = _estado_detector()
    if "inactivo" in estado.lower():
        # Arrancar en modo mesa para calibrar
        return _iniciar_detector(modo="mesa")
    # Si ya está corriendo, enviarle señal de calibración via subprocess
    import subprocess
    # El detector escucha 'C' para calibrar — enviamos via xdotool si está disponible
    try:
        subprocess.run(["xdotool", "key", "c"], capture_output=True)
        return "Señal de calibración enviada, Señor. Mirá la ventana del detector."
    except Exception:
        return ("Detector activo. Para calibrar: hacé click en la ventana del detector "
                "y presioná la tecla 'C', Señor.")


def skill_gestos_gui(_=None) -> str:
    """Abre la interfaz gráfica completa del detector de gestos."""
    import sys, subprocess
    from pathlib import Path as _Path
    gui = _Path.home() / "Desktop" / "Detector-de-gestos" / "gui_app.py"
    if not gui.exists():
        return f"No encontré la GUI en {gui}, Señor."
    try:
        subprocess.Popen([sys.executable, str(gui)],
                         cwd=str(gui.parent))
        return "Interfaz gráfica del detector de gestos abierta, Señor."
    except Exception as e:
        return f"No pude abrir la GUI: {e}"


# ── Blender 3D ────────────────────────────────────────────────────────────────

def skill_blender_crear(texto: str = "") -> str:
    """Genera y ejecuta un objeto 3D en Blender desde descripción en lenguaje natural."""
    if not _HAS_BLENDER:
        return "Módulo de Blender no disponible, Señor."
    descripcion = re.sub(
        r"^(?:crea[r]?|creá|genera[r]?|generá|hace[r]?|hacé|modela[r]?|modelá|"
        r"diseña[r]?|diseñá|constru(?:ye[r]?|í[r]?)?)\s+"
        r"(?:(?:en|en\s+el\s+)?blender\s+)?(?:un[ao]?\s+)?(?:objeto\s+|modelo\s+(?:3d\s+)?)?",
        "", texto, flags=re.IGNORECASE
    ).strip()
    if not descripcion:
        return "¿Qué objeto querés crear en Blender, Señor?"
    return _blender_generar(descripcion)


def skill_blender_ejecutar(texto: str = "") -> str:
    """Ejecuta código Python directamente en Blender."""
    if not _HAS_BLENDER:
        return "Módulo de Blender no disponible, Señor."
    codigo = re.sub(
        r"^(?:ejecuta[r]?|ejecutá|corre[r]?|corré|run)\s+(?:en\s+blender\s+)?",
        "", texto, flags=re.IGNORECASE
    ).strip()
    if not codigo:
        return "No entendí el código a ejecutar en Blender, Señor."
    return _blender_ejecutar(codigo)


def skill_blender_abrir(_=None) -> str:
    """Abre Blender."""
    if not _HAS_BLENDER:
        return "Módulo de Blender no disponible, Señor."
    return _blender_abrir()


def skill_blender_estado(_=None) -> str:
    """Verifica el estado de conexión con Blender."""
    if not _HAS_BLENDER:
        return "Módulo de Blender no disponible, Señor."
    return _blender_estado()


def skill_blender_aprobar(texto: str = "") -> str:
    """Aprueba el último script generado y lo guarda como ejemplo de referencia."""
    if not _HAS_BLENDER:
        return "Módulo de Blender no disponible, Señor."
    tags = [t.strip() for t in texto.split(",")] if texto.strip() else None
    return _blender_aprobar(tags=tags)


def skill_emails(texto: str = "") -> str:
    """Consulta emails clasificados. Ej: 'emails urgentes', 'mails del banco'."""
    if not _HAS_N8N:
        return "Módulo n8n no disponible, Señor."
    import re
    texto_l = texto.lower()
    urgentes = bool(re.search(r"urgente|importante|critico", texto_l))
    categoria = ""
    for cat in ["banco", "trabajo", "factura", "gasto", "cita", "alerta", "suscripcion"]:
        if cat in texto_l:
            categoria = cat
            break
    return n8n.consultar_emails(categoria=categoria, urgentes=urgentes)


def skill_buscar_email(texto: str = "") -> str:
    """Busca emails (leídos y no leídos) por remitente, asunto o palabra clave."""
    if not _HAS_N8N:
        return "Módulo n8n no disponible, Señor."
    import re
    # Extraer término de búsqueda del texto natural
    texto_l = texto.strip()
    # Quitar frases de prefijo comunes
    query = re.sub(
        r"^(?:busca(?:r)?|busca(?:me)?|encontra(?:r)?|encuentra(?:me)?|"
        r"(?:busca|buscar)\s+(?:el\s+)?(?:mail|email|correo)\s+(?:de|sobre|del?)?|"
        r"(?:mail|email|correo)\s+(?:de|sobre|del?)?)\s*",
        "", texto_l, flags=re.IGNORECASE
    ).strip()
    if not query:
        return "¿Qué email busco, Señor? Dígame el remitente, asunto o palabra clave."
    return n8n.buscar_email(query)


def skill_email_accion(texto: str) -> str:
    """
    Ejecuta acción sobre un email.
    Ej: 'archiva el mail 18abc', 'elimina el correo 18abc',
        'marca importante el mail 18abc', 'agenda el mail 18abc'
    """
    if not _HAS_N8N:
        return "Módulo n8n no disponible, Señor."
    import re

    # Detectar acción
    _ACCIONES = {
        r"archiv": "archivar",
        r"elimin|borra": "eliminar",
        r"import": "importante",
        r"agenda|calendar": "agenda",
        r"gasto|factur|registra": "gastos",
    }
    accion = None
    for pat, act in _ACCIONES.items():
        if re.search(pat, texto, re.I):
            accion = act
            break
    if not accion:
        return "No entendí la acción. Opciones: archivar, eliminar, importante, agenda, gastos."

    # Detectar ID del email (suele ser un hash hex largo)
    id_match = re.search(r'\b([0-9a-fA-F]{6,})\b', texto)
    if not id_match:
        return "Necesito el ID del email para actuar. El ID aparece en la notificación."
    email_id = id_match.group(1)

    # Extraer fecha/hora si es para agenda
    fecha = ""
    hora  = "09:00"
    if accion == "agenda":
        fm = re.search(r'(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2})', texto)
        hm = re.search(r'(\d{1,2}:\d{2})', texto)
        if fm:
            fecha = fm.group(1).replace("/", "-")
        if hm:
            hora = hm.group(1)

    # Extraer monto si es para gastos
    monto = 0.0
    if accion == "gastos":
        mm = re.search(r'\$?\s*(\d+(?:[.,]\d+)?)', texto)
        if mm:
            monto = float(mm.group(1).replace(",", "."))

    return n8n.accion_email(email_id, accion, fecha_evento=fecha, hora_evento=hora, monto=monto)


def skill_stats_modelos(_=None) -> str:
    """Muestra estadísticas de uso de los modelos LLM."""
    import json as _json
    from pathlib import Path as _Path
    stats_path = _Path(__file__).parents[3] / "model_stats.json"
    if not stats_path.exists():
        return "Sin estadísticas todavía, Señor. Usá Nova un rato primero."
    try:
        data = _json.loads(stats_path.read_text())
        lines = ["Estadísticas de modelos LLM:\n"]
        for proveedor, info in sorted(data.items()):
            if not isinstance(info, dict):
                continue
            ok    = info.get("success", 0)
            fail  = info.get("failure", 0)
            total = ok + fail
            if total == 0:
                continue
            pct   = int(ok / total * 100)
            lat   = info.get("avg_latency", 0)
            bar_w = 16
            filled = int(bar_w * pct / 100)
            bar = "█" * filled + "░" * (bar_w - filled)
            lines.append(f"  {proveedor:<12} [{bar}] {pct:3}%  {ok}ok/{fail}fail  {lat:.1f}s")
        return "\n".join(lines) if len(lines) > 1 else "Sin datos suficientes todavía, Señor."
    except Exception as e:
        return f"Error leyendo estadísticas: {e}"


def skill_agregar_modelo(texto: str) -> str:
    """Agrega un proveedor LLM custom al router dinámicamente."""
    import re as _re

    m = _re.search(
        r"(?:nombre|proveedor|llm|modelo)?\s*"
        r"([A-Za-z0-9_\-]{2,40})"
        r".*?(?:url|base[_\s]?url|endpoint)\s*:?\s*(https?://\S+)"
        r".*?(?:key|api[_\s]?key|token|api)\s*:?\s*([A-Za-z0-9_\-\.]{10,})"
        r"(?:.*?(?:modelo|model)\s*:?\s*([A-Za-z0-9_\-\./:\+]{3,60}))?",
        texto,
        _re.IGNORECASE | _re.DOTALL,
    )
    if not m:
        return (
            "No pude extraer los datos. Usá el formato: "
            "'agrega modelo NombreLLM url https://api.ejemplo.com/v1 key sk-xxx modelo gpt-4'"
        )
    name  = m.group(1).strip()
    url   = m.group(2).strip().rstrip("/")
    key   = m.group(3).strip()
    model = (m.group(4) or "").strip() or "gpt-4o-mini"

    try:
        from nova.core.nova_router import NovaRouter
        from nova.core import nova_router as _nr
        if hasattr(_nr, "router") and isinstance(_nr.router, NovaRouter):
            return _nr.router.add_custom_provider(name, url, key, model)
        router = NovaRouter()
        return router.add_custom_provider(name, url, key, model)
    except Exception as e:
        return f"Error al agregar proveedor: {e}"


def skill_listar_modelos(texto: str = "") -> str:
    """Lista los proveedores LLM activos y sus modelos."""
    try:
        from nova.core import nova_router as _nr
        router = getattr(_nr, "router", None)
        if router is None:
            return "El router no está inicializado todavía, Señor."
        lines = [f"Orden de proveedores: {', '.join(router.provider_order)}"]
        if router._custom_clients:
            lines.append("\nProveedores custom:")
            for c in router._custom_clients:
                lines.append(f"  {c['name']} — modelo: {c['model']} — url: {c['base_url']}")
        else:
            lines.append("Sin proveedores custom configurados.")
        return "\n".join(lines)
    except Exception as e:
        return f"No pude listar los modelos: {e}"


# ══════════════════════════════════════════════════════════════
# 8. DISPATCHER — detección de intención
# ══════════════════════════════════════════════════════════════

# Cada entrada: (patrón_regex, función_handler, índice_grupo_argumento_o_None)
# Si índice_grupo es None → se llama sin argumentos
# Si es un int → se pasa match.group(n) como argumento

_INTENTS: list[tuple] = [
    # ── Música ────────────────────────────────────────────────
    (r"(?:reproduce|reproducir|pon|poner|play|toca|tocar)\s+"
     r"(?:música|musica|algo|una canción|una cancion)$",                      music_play,  None),
    (r"(?:reproduce|reproducir|pon|poner|play|toca)\s+"
     r"(?:música\s+de\s+|musica\s+de\s+|algo\s+de\s+|una\s+canción\s+de\s+|"
     r"una\s+cancion\s+de\s+|canciones?\s+de\s+)?(.+)",                      music_play_query, 1),
    (r"(?:pausa|pausar|pause|para la música|para la musica|detén|deten)",     music_pause, None),
    (r"(?:siguiente canci[oó]n|siguiente pista|next track|siguiente track|skip|siguiente tema musical)",
                                                                               music_next,  None),
    (r"(?:anterior|canci[oó]n anterior|pista anterior|volver|atr[aá]s en m[uú]sica|cancion anterior)",
                                                                               music_prev,  None),
    (r"(?:qué suena|que suena|qué canción|que cancion|qué está sonando|"
     r"canción actual|artista actual|qué música)",                            music_current_track, None),
    (r"(?:modo aleatorio|shuffle|aleatorio on|activar aleatorio)",            music_shuffle_on,  None),
    (r"(?:desactivar aleatorio|shuffle off|quitar aleatorio)",                music_shuffle_off, None),

    # ── Obsidian / diario / vault ─────────────────────────────
    (r"(?:anota|anotar|registra|apunta)"
     r"(?:\s+(?:en\s+(?:el\s+)?(?:diario|obsidian|el\s+cerebro)|al\s+diario))?"
     r"\s*:?\s*(.+)",                                                          obsidian_anota,     1),
    (r"(?:agrega\s+(?:al|en\s+el)\s+diario|escribe\s+en\s+el\s+diario)"
     r"\s*:?\s*(.+)",                                                          obsidian_anota,     1),
    (r"(?:crea una nota|nueva nota|crear nota)\s*:?\s*(.+)",                  obsidian_nota_nueva, 1),
    (r"(?:lee la nota|leer nota|abrir nota|muéstrame la nota)\s+(.+)",        obsidian_lee_nota,  1),
    (r"(?:busca|buscar|encuentra|encontrar|consulta|consultar)\s+"
     r"en\s+(?:el\s+)?(?:cerebro|vault|obsidian|notas|memoria)"
     r"(?:\s+de\s+(?:obsidian|cerebro))?(?:\s*\([^)]+\))?\s+"
     r"(?:sobre\s+|acerca\s+de\s+)?([^,]+?)(?:[,\.]\s*(?:analiza|explica|compara|dime|y\s+).+)?$",
                                                                              obsidian_busca,     1),
    (r"(?:busca|buscar|encuentra|encontrar|consulta|consultar)\s+"
     r"(?:sobre\s+|acerca\s+de\s+)(.+)\s+en\s+(?:el\s+)?(?:cerebro|vault|obsidian|notas|memoria)",
                                                                              obsidian_busca,     1),
    (r"(?:qué\s+(?:sabes|tengo|hay)\s+(?:sobre|en)\s+(?:el\s+)?"
     r"(?:cerebro|vault|obsidian|notas)\s+(?:sobre\s+)?|"
     r"(?:cerebro|vault|obsidian):\s*)(.+)",                                  obsidian_busca,     1),
    (r"(?:lista|listar|mostrar|ver)\s+(?:el\s+)?(?:directorio|carpeta|contenido)\s+"
     r"(?:de\s+)?(?:el\s+)?(?:cerebro|vault|obsidian)(?:\s+(.+))?",          obsidian_lista_dir, 1),
    (r"(?:sincroniza|actualiza|sync|refresca)\s+"
     r"(?:el\s+)?(?:cerebro|vault|obsidian|memoria|notas)",                   sincroniza_cerebro, None),
    (r"(?:estado|status)\s+(?:del\s+)?cerebro",                               skill_cerebro_estado, None),
    (r"(?:qué\s+(?:sabes?|sab[eé]s?|ten[eé]s?|hay)\s+(?:sobre|acerca\s+de)\s+)(.+)",
                                                                              skill_cerebro_que_se, 1),
    (r"(?:busca(?:me)?|encontr[aá](?:me)?)\s+(?:en\s+el\s+)?cerebro\s+(.+)", obsidian_busca,      1),
    (r"(?:escrib[eé]\s+en\s+(?:el\s+)?cerebro)\s*:?\s*(.+)",                 obsidian_nota_nueva, 1),

    # ── Git-aware workflow ────────────────────────────────────
    (r"(?:git\s+)?(?:estado|status)\s+(?:del?\s+)?(?:repo|repositorio|git|proyecto)",
                                                                               skill_git_status, None),
    (r"(?:qué\s+)?(?:cambios?\s+(?:hay|tengo|pendientes?)|modificaciones?\s+(?:hay|tengo))"
     r"(?:\s+en\s+git)?",                                                      skill_git_status, None),
    (r"git\s+status",                                                          skill_git_status, None),
    (r"(?:git\s+)?diff(?:erencias?)?(?:\s+de\s+(?:git|cambios?))?",           skill_git_diff, None),
    (r"(?:ver|mostrar|dame)\s+(?:el\s+)?diff",                                skill_git_diff, None),
    (r"(?:git\s+)?log(?:\s+de\s+git)?|historial\s+de\s+commits?",             skill_git_log, 0),
    (r"(?:últimos?\s+\d+\s+commits?|commits?\s+recientes?)",                   skill_git_log, 0),
    (r"(?:haz?\s+(?:un\s+)?commit|git\s+commit|guarda[r]?\s+(?:los?\s+)?cambios?)"
     r"(?:\s+.{0,100})?",                                                      skill_git_commit, 0),
    (r"(?:genera[r]?\s+(?:una?\s+)?(?:descripción\s+de\s+)?pr|pull\s+request|"
     r"crea[r]?\s+(?:la\s+)?(?:descripción\s+(?:de\s+)?)?(?:pr|pull\s+request))",
                                                                               skill_git_pr, 0),

    # ── Imágenes — PRIMERO para evitar que "crea una imagen" caiga en especialista
    (r"(?:generar?|generá|crear?|creá|hacer?|hacé|dibujar?|dibujá|pintar?|pintá)\s+"
     r"(?:una?\s+)?(?:imagen?|foto|ilustración?|cuadro|dibujo|pintura|render)\s*(.+)",
                                                                               skill_imagen, 0),
    (r"(?:muéstrame\s+una?\s+(?:imagen?|foto)|imagen\s+de|foto\s+de)\s+(.+)", skill_imagen, 0),
    (r"^imagen\s+(?:de\s+|del?\s+)?(.+)",                                      skill_imagen, 0),

    # ── Agentes especializados ────────────────────────────────
    (r"(?:crea(?:r)?|genera(?:r)?|arma(?:r)?|inicializ[ae](?:r)?)\s+"
     r"(?:un\s+|una\s+)?(?:proyecto|repositorio|repo|app|aplicaci[oó]n)\s+.{5,}",
                                                                              skill_crear_proyecto, 0),
    (r"(?:establece(?:r)?\s+proyecto|proyecto\s+activo|"
     r"(?:abre(?:r)?|carga(?:r)?)\s+(?:el\s+|este\s+|ese\s+|mi\s+)?proyecto)\s*.+",
                                                                              skill_abrir_proyecto, 0),
    (r"(?:abre|carga)\s+(?:el\s+)?proyecto\s+(.+)",                          skill_abrir_proyecto, 1),
    (r"(?:lee(?:r)?|muestra(?:r)?|ver)\s+(?:el\s+archivo\s+|archivo\s+)?(?:del\s+proyecto\s+)?(.+\.\w+)",
                                                                              skill_leer_archivo_proyecto, 1),
    (r"(?:(?:dime|muéstrame|lista[r]?|ver|qué hay en|contenido de|qué tiene)\s+"
     r"(?:la\s+)?(?:carpeta|directorio|contenido|archivos|esa carpeta|ese directorio))",
                                                                              skill_listar_carpeta_activa, None),
    (r"(?:modifica(?:r)?|edita(?:r)?|actualiza(?:r)?|agrega(?:r)?)\s+(?:el\s+archivo\s+)?[\w./\-]+\.\w+.{5,}",
                                                                              skill_editar_proyecto, 0),
    (r"(?:estructura|árbol|arbol|archivos)\s+(?:del\s+)?proyecto",            skill_estructura_proyecto, 0),
    (r"(?:mejora(?:r)?|expande(?:r)?|itera(?:r)?)\s+(?:el\s+)?proyecto.{0,100}",
                                                                              skill_mejorar_proyecto, 0),
    (r"(?:c[oó]mo\s+(?:se\s+)?(?:implementa[r]?|usa[r]?|hago?|creo?|configuro?|integro?)|"
     r"ejemplo\s+de|c[oó]mo\s+funciona|qu[eé]\s+es)\s+.{5,}",              skill_codear_con_docs, 0),
    (r"(?:genera(?:r)?|crea(?:r)?|escribe(?:r)?|haz?)\s+(?:los?\s+)?tests?\s+(?:para\s+|de\s+)?",
                                                                              skill_generar_tests, 0),
    (r"(?:testea(?:r)?|prueba(?:r)?)\s+(?:el\s+archivo\s+)?[\w./\-]+\.py",
                                                                              skill_generar_tests, 0),

    # ── LSP — análisis semántico de código ───────────────────────
    (r"(?:dónde|donde)\s+(?:está|esta)\s+(?:definid[ao]|implement[ao]d[ao])\s+"
     r"(?:la\s+función|la\s+clase|el\s+método|el\s+símbolo)?\s*['\"]?(\w+)['\"]?",
                                                                              skill_lsp_definicion, 0),
    (r"definición\s+de\s+['\"]?(\w+)['\"]?",                                 skill_lsp_definicion, 1),
    (r"(?:dónde|donde)\s+se\s+usa\s+['\"]?(\w+)['\"]?",                      skill_lsp_referencias, 1),
    (r"referencias?\s+(?:a|de)\s+['\"]?(\w+)['\"]?",                         skill_lsp_referencias, 1),
    (r"(?:analiza(?:r)?|que\s+funciones?\s+tiene|estructura\s+de)\s+([\w./\-]+\.py)",
                                                                              skill_lsp_analizar, 0),
    (r"(?:hay\s+errores?\s+en|diagnostica(?:r)?|revisa\s+errores?\s+en)\s+([\w./\-]+\.py)",
                                                                              skill_lsp_diagnostico, 0),
    (r"(?:renombra(?:r)?|cambia(?:r)?\s+nombre)\s+.{5,}",                    skill_lsp_renombrar, 0),

    # ── Docker awareness ─────────────────────────────────────────
    (r"(?:dockeriza(?:r)?|genera(?:r)?\s+(?:el\s+)?dockerfile|crea(?:r)?\s+(?:el\s+)?dockerfile|"
     r"agrega(?:r)?\s+docker|configura(?:r)?\s+docker)\s*.{0,100}",          skill_dockerizar, 0),
    (r"(?:lev[aá]nta(?:r)?|sube(?:r)?|lanza(?:r)?|corre(?:r)?|deploy(?:ar)?|despliega(?:r)?)\s+"
     r"(?:el\s+)?(?:proyecto|app|aplicaci[oó]n)\s+(?:en\s+)?(?:docker|contenedor|container).{0,60}",
                                                                              skill_deploy_local, 0),
    (r"(?:deploy\s+local|docker.compose\s+up|levanta\s+(?:el\s+)?docker).{0,60}",
                                                                              skill_deploy_local, 0),

    (r"(?:qué\s+misiones|que\s+misiones|cómo\s+mejorar[ías]*|como\s+mejorar[ías]*|"
     r"propone[s]?\s+misiones?|planea[r]?\s+misiones?|analiza[r]?\s+proyecto|"
     r"misiones?\s+para|mejoras?\s+para|qué\s+har[ías]*|que\s+har[ías]*).{0,120}",
                                                                              skill_planear_misiones, 0),
    (r"(?:ejecuta(?:r)?|lanza(?:r)?|corre(?:r)?)\s+(?:las?\s+)?misiones?.{0,80}",
                                                                              skill_ejecutar_misiones, 0),
    (r"(?:actúa como|actua como|habla como|modo experto|como especialista)\s+.+",
                                                                              skill_especialista, 0),
    (r"(?:consulta(?:r)?|pregunta(?:r)?)\s+(?:al?|a la)\s+.+\s+(?:sobre|para|acerca de)\s+.+",
                                                                              skill_especialista, 0),
    (r"como\s+experto\s+en\s+.+\s*,\s*.+",                                  skill_especialista, 0),
    (r"/?agente\s+\w.+",                                                      skill_especialista, 0),
    (r"(?:listar?|ver|mostrar|qué)\s+agentes?\s+(?:disponibles?|especializados?)?",
                                                                              skill_listar_agentes, 0),

    # ── Notas (legacy) ────────────────────────────────────────
    (r"(?:mis notas|lista.*notas|listar notas|ver notas|qué notas tengo)",    notes_list, None),

    # ── Nuevo documento/ventana en app ────────────────────────
    (r"(?:crea?|abre?|hace?|abrir?)\s+"
     r"(?:un[ao]?\s+)?(?:nuevo|nueva)\s+(?:documento|ventana|archivo|pestaña|tab)\s+"
     r"(?:en\s+|de\s+|con\s+)?(.+)",                                          new_document_in_app, 1),
    (r"(?:nuevo documento|nueva ventana|nuevo archivo)\s+(?:en\s+|de\s+)?(.+)",
                                                                               new_document_in_app, 1),

    # ── Apps ──────────────────────────────────────────────────
    (r"(?:abre|abrir|inicia|iniciar|lanza|lanzar|ejecuta|ejecutar|arranca)\s+"
     r"(?:la app\s+|la aplicación\s+|el programa\s+|la web\s+)?(.+)",        open_app,   1),
    (r"(?:open|launch|start)\s+(.+)",                                          open_app,   1),
    (r"(?:cierra|cerrar|mata|matar|kill)\s+(?:la app\s+|el programa\s+)?(.+)",close_app,  1),
    (r"(?:qu[eé]\s+apps|lista.*apps|aplicaciones instaladas|mis aplicaciones|apps instaladas)",
                                                                               list_apps,  None),
    (r"(?:apps activas|qu[eé]\s+est[aá]\s+abierto|procesos activos|qu[eé]\s+apps\s+est[aá]n\s+abiertas|apps\s+abiertas|apps que tengo abiertas|qu[eé]\s+programas\s+est[aá]n\s+abiertos)",
                                                                               get_running_apps, None),
    (r"(?:qué estoy haciendo|qué app es esta|dónde estoy|contexto)",            get_active_window_context, None),

    # ── Terminal ───────────────────────────────────────────────
    (r"(?:ejecuta el comando|ejecuta comando|corre el comando|run command|en terminal|"
     r"terminal:|comando:|terminal:?\s+run|ejecuta(?:r)?\s+en\s+terminal)\s*:?\s*(.+)",
                                                                               run_command, 1),

    # ── Archivos ───────────────────────────────────────────────
    (r"(?:lista|listar|muestra)\s+(?:la carpeta|el directorio|archivos en)\s+(.+)",
                                                                               list_directory, 1),
    (r"(?:busca el archivo|encuentra el archivo|find file)\s+(.+)",            find_file,  1),
    (r"(?:abre el archivo|abrir archivo|open file)\s+(.+)",                    open_file,  1),
    (r"(?:lee|leer|muestra|mostrar)\s+(?:el\s+)?archivo\s+(.+)",               read_text_file, 1),
    (r"(?:edita|editar|modifica|modificar)\s+(?:el\s+)?archivo\s+(.+)",        edit_file, 1),
    (r"(?:crea|crear|sobrescribe|guardar|guarda)\s+(?:el\s+)?archivo\s+(.+)",  write_text_file, 1),
    (r"(?:añade|agrega|append)\s+(?:al\s+)?archivo\s+(.+)",                     append_text_file, 1),
    (r"(?:reemplaza|replace)\s+en\s+archivo\s+(.+)",                            replace_in_text_file, 1),
    (r"(?:crea|crear|genera|escribe)\s+(?:un\s+)?(?:script|código|codigo)\s+en\s+(.+)",
                                                                               write_text_file, 1),

    # ── Screenshots ────────────────────────────────────────────
    (r"(?:captura de pantalla|screenshot|toma.*pantalla|foto.*pantalla)",      take_screenshot, None),
    (r"(?:qué ves|que ves|analiza|qué hay en|qué estoy viendo|describe)\s+(?:la\s+)?(?:pantalla|imagen)", 
                                                                               analyze_screen, None),
    (r"(?:hazlo t[uú]|toma.*control|maneja.*mouse|maneja.*rat[oó]n|piloto autom[aá]tico|opera.*por m[ií])\s*(?:para|que)?[:,\s]*(.*)",
                                                                               computer_pilot_mode, 1),
    (r"(?:mensaje|escribí|mandá|mandar)\s+(?:a\s+)?telegram\s+(.+)",           skill_telegram, 1),
    (r"(?:notificá|avisá|mandá\s+push)\s+(.+)",                                skill_push,     1),

    # ── Mouse y Teclado ────────────────────────────────────────
    (r"(?:mueve|mover)\s+(?:el\s+)?(?:ratón|mouse)\s+a\s+(\d+)[\s,]+(\d+)",    lambda x, y: mouse_move(int(x), int(y)), 1),
    (r"(?:haz\s+)?click\s+en\s+(\d+)[\s,]+(\d+)",                             lambda x, y: mouse_click(int(x), int(y)), 1),
    (r"(?:haz\s+)?click(?:\s+izquierdo)?$",                                    lambda: mouse_click(), None),
    (r"(?:haz\s+)?click\s+derecho$",                                           lambda: mouse_click(clicks=1), None),
    (r"(?:doble\s+)?click$",                                                   lambda: mouse_click(clicks=2), None),
    (r"(?:teclea|escribe|escribí)\s+(.+)",                                      type_text, 1),
    (r"(?:presiona|apretá)\s+(?:la\s+tecla\s+)?(.+)",                           press_key, 1),
    (r"(?:dónde está el ratón|posición del mouse|dónde está el puntero)",       get_mouse_pos, None),
    (r"(?:subí|bajá|scroll)\s+(?:la\s+pantalla|el\s+scroll)\s+(\d+)",           lambda a: mouse_scroll(int(a)), 1),

    # ── Volumen ────────────────────────────────────────────────
    (r"(?:qué volumen|volumen actual|cuánto está el volumen)",                 get_volume, None),
    (r"(?:silencia|mute|mutea|silenciar)",                                     mute_volume, None),
    (r"(?:activa.*audio|desactiva.*mute|unmute|quitar.*silencio)",             unmute_volume, None),

    # ── Batería ────────────────────────────────────────────────
    (r"(?:batería|battery|cuánta carga|estado.*batería)",                      get_battery, None),

    # ── Pantalla ───────────────────────────────────────────────
    (r"(?:bloquea|bloquear|lock)\s+(?:la\s+)?(?:pantalla|screen|computadora)", lock_screen, None),

    # ── Tiempo ────────────────────────────────────────────────
    (r"(?:qu[eé]\s+hora|la hora|what time|dime la hora|dec[ií]me\s+la\s+hora|qu[eé]\s+hora es)", get_time, None),
    (r"(?:qu[eé]\s+d[ií]a|qu[eé]\s+fecha|what day|what date|hoy es qu[eé] d[ií]a|"
     r"qu[eé]\s+d[ií]a es hoy|d[ií]me\s+(?:la\s+)?fecha|dime\s+(?:el\s+)?d[ií]a|"
     r"el\s+d[ií]a\s+de\s+hoy|fecha\s+de\s+hoy|hoy\s+es|d[ií]a\s+de\s+hoy)", get_date, None),

    # ── GitHub ────────────────────────────────────────────────
    (r"(?:mis\s+repos|listar?\s+repos?|ver\s+repos?|qué\s+repos?\s+tengo)",
     lambda t="": _skill_github_repos(t) if _HAS_GITHUB else "GitHub no disponible, Señor.", None),
    (r"(?:info|detalles?)\s+(?:del?\s+)?repo\s+(.+)",
     lambda t: _skill_github_repo_info(t) if _HAS_GITHUB else "GitHub no disponible, Señor.", 1),
    (r"(?:issues?|tickets?)\s+(?:de[l]?\s+)?(?:repo\s+)?(.+)",
     lambda t: _skill_github_issues(t) if _HAS_GITHUB else "GitHub no disponible, Señor.", 1),
    (r"(?:pull\s*requests?|prs?)\s+(?:de[l]?\s+)?(?:repo\s+)?(.+)",
     lambda t: _skill_github_prs(t) if _HAS_GITHUB else "GitHub no disponible, Señor.", 1),
    (r"(?:commits?|historial)\s+(?:de[l]?\s+)?(?:repo\s+)?(.+)",
     lambda t: _skill_github_commits(t) if _HAS_GITHUB else "GitHub no disponible, Señor.", 1),
    (r"crea\s+(?:un\s+)?(?:issue|ticket)\s+en\s+\S+.+",
     lambda t: _skill_github_crear_issue(t) if _HAS_GITHUB else "GitHub no disponible, Señor.", 0),
    (r"(?:estado|status)\s+(?:de\s+)?github",
     lambda t="": _estado_github() if _HAS_GITHUB else "GitHub no disponible, Señor.", None),

    # ── Browser / Web ─────────────────────────────────────────
    (r"(?:abre|abrir|navega|ir a|entrá a|entra a)\s+"
     r"(?:la\s+(?:web|página|pagina|sitio)\s+(?:de\s+)?)?"
     r"([\w\-]+(?:\.[\w\-]+)+(?:/\S*)?|(?:google|youtube|gmail|instagram|linkedin|twitter|github))",
     lambda u: _skill_abrir_url(u) if _HAS_BROWSER else web_search(u), 1),
    (r"(?:busca[r]?\s+en\s+(?:el\s+)?(?:browser|navegador)|busca[r]?\s+en\s+(?:la\s+)?web\s+con\s+(?:browser|navegador))\s+(.+)",
     lambda q: _skill_buscar_web_browser(q) if _HAS_BROWSER else web_search(q), 1),
    (r"(?:lee|leer)\s+(?:la\s+)?(?:página|pagina|web|sitio)\s+(?:actual|que\s+abriste)?",
     lambda t="": _skill_leer_pagina(t) if _HAS_BROWSER else "Browser no disponible, Señor.", None),
    (r"(?:captura|screenshot)\s+(?:la\s+)?(?:web|página|pagina|browser|sitio)",
     lambda t="": _skill_capturar_web(t) if _HAS_BROWSER else "Browser no disponible, Señor.", None),
    (r"(?:cierra|cerrar)\s+(?:el\s+)?browser",
     lambda t="": _skill_cerrar_browser(t) if _HAS_BROWSER else "Browser no disponible, Señor.", None),
    (r"(?:click|clickeá|presioná|tocá)\s+(?:en\s+)?(?:el\s+|la\s+)?(?:botón\s+|enlace\s+|link\s+)?[\"']?(.+?)[\"']?\s*$",
     lambda t: _skill_hacer_click_voz(t) if _HAS_BROWSER else "Browser no disponible, Señor.", 1),

    # ── Traducción ────────────────────────────────────────────
    (r"(?:traduc[ei]r?|cómo\s+se\s+dice|como\s+se\s+dice|qué\s+significa|que\s+significa)\s+.+",
                                                                               skill_traducir, 0),

    # ── Crypto ────────────────────────────────────────────────
    (r"(?:precio\s+de|cuánto\s+vale|cuanto\s+vale|cotización\s+de|cotizacion\s+de)\s+"
     r"(?:bitcoin|ethereum|solana|dogecoin|btc|eth|sol|doge|xrp|bnb|avax|matic|ada|"
     r"crypto|cripto|criptomoneda)",                                            skill_crypto, 0),
    (r"(?:crypto|cripto)\s+(?:bitcoin|ethereum|solana|dogecoin|btc|eth|sol|doge|xrp|.{3,15})",
                                                                               skill_crypto, 0),

    # ── Forex / Tipo de cambio ────────────────────────────────
    (r"(?:cuántos?|cuantos?)\s+(?:son|vale[n]?|equivalent[e]?)\s+\d+.{0,30}"
     r"(?:dólar|dolar|euro|libra|yen|yuan|real|franco).{0,30}"
     r"(?:en|a|para)\s+(?:dólar|dolar|euro|libra|yen|yuan|real|franco|peso)",  skill_forex, 0),
    (r"tipo\s+de\s+cambio\s+(?:entre\s+)?(?:EUR|USD|GBP|JPY|BRL|CHF|ARS|MXN|CNY).{0,20}"
     r"(?:EUR|USD|GBP|JPY|BRL|CHF|ARS|MXN|CNY)",                               skill_forex, 0),

    # ── Feriados ──────────────────────────────────────────────
    (r"(?:feriados?|días?\s+feriados?|días?\s+libres?|días?\s+no\s+laborables?)"
     r"(?:\s+(?:de|en|para)\s+.+)?",                                           skill_feriados, 0),
    (r"(?:próximos?\s+feriados?|cuándo\s+es\s+el\s+próximo\s+feriado|"
     r"cuando\s+es\s+el\s+proximo\s+feriado)",                                 skill_feriados, 0),

    # ── Clima ─────────────────────────────────────────────────
    (r"(?:pron[oó]stico|forecast|c[oó]mo estar[aá]|va a llover|va a hacer fr[ií]o|va a hacer calor)"
     r"(?:.*?(?:en|de|para)\s+(.+))?",
     lambda loc="Buenos Aires": get_forecast(loc or "Buenos Aires", days=3), 1),
    (r"(?:clima|tiempo|temperatura)\s+(?:de\s+)?(?:hoy\s+)?(?:en|de|para)\s+(.+)",
     lambda loc: get_weather(loc), 1),
    (r"(?:clima|tiempo|temperatura|llueve|qué tal el tiempo)",
     lambda: get_weather("Buenos Aires"), None),

    # ── Búsqueda web (negativa: no interceptar "busca/buscar en drive X") ──────
    (r"(?:busca[r]?|googlea|investiga|dime sobre|search)\s+"
     r"(?!en\s+(?:drive|google\s*drive|mi\s*drive)\b)"
     r"(?!(?:el\s+|un\s+|ese\s+)?(?:mail|email|correo)\b)"
     r"((?:fotos?\s+de\s+|imágenes?\s+de\s+|información\s+(?:sobre|de)\s+)?"
     r"[^,\.]+?)(?:\s*[,\.]\s*(?:y\s+)?(?:luego|después|ahora|también|además|analiza|crea|genera|usa|aplica).+)?$",
                                                                               web_search, 1),

    # ── Memoria ───────────────────────────────────────────────
    (r"(?:recuerda que|recuerda:|guarda que|anota que|recuerda\s+(?:que\s+)?(?:mi|el|la|los|las)\s+.+es)\s*(.+)",
                                                                               skill_remember, 1),
    (r"recuerda\s+(.+?)\s+(?:es|son|=)\s+(.+)",
     lambda k, v: skill_remember(f"{k} es {v}"),                              1),
    (r"(?:qu[eé]\s+sabes\s+de|recuerdas(?:\s+algo)?(?:\s+sobre)?|qu[eé]\s+recuerdas\s+(?:de|sobre))\s+(.+)",
                                                                               skill_recall,   1),
    (r"(?:olvida|elimina de tu memoria)\s+(.+)",                               skill_forget,   1),

    # ── Red y Bluetooth ───────────────────────────────────────
    (r"(?:qué hay en (?:la )?(?:red|mi red)|dispositivos (?:en la )?(?:red|conectados)|escanea(?:r)? (?:la )?red|quién está en (?:la )?red)",
     skill_scan_red, None),
    (r"(?:dispositivos bluetooth|bluetooths?\s+(?:disponibles|cercanos|conectados)|escanea(?:r)? bluetooth|qué bluetooth(?:s)?)",
     skill_scan_bluetooth, None),

    # ── Voz ───────────────────────────────────────────────────
    (r"(?:voces disponibles|qué voces|lista.*voces|ver voces)",                list_voices,    None),
    (r"(?:cambia la voz a|usa la voz|pon la voz)\s+(.+)",                      set_voice,      1),
    (r"(?:habla más lento|habla más despacio|velocidad.*lenta)",               lambda: set_voice_speed(120), None),
    (r"(?:habla más rápido|velocidad.*rápida)",                                lambda: set_voice_speed(180), None),
    (r"(?:velocidad de voz|pon la velocidad).*?(\d+)",                         None,           1),  # handled below

    # ── Sistema NOVA ────────────────────────────────────────
    (r"^(?:reiniciar|reinicia|restart|reiniciate)$",                           _restart_nova, None),
    (r"(?:qué puedes hacer|que puedes hacer|skills disponibles|lista de skills|capacidades|qué sabes hacer)",
                                                                               lambda: capabilities_summary(), None),
    (r"(?:estadísticas?|estadisticas?|stats?|métricas?|metricas?)\s*(?:de\s+(?:modelos?|sistema|uso))?",
                                                                               skill_stats_modelos, None),
    (r"(?:estado del sistema|configuración|audio settings|parámetros de audio)", get_system_status, None),

    # ── Subagentes / Orquestador ──────────────────────────────
    (r"(?:prepara(?:me)?|dame|muéstrame|resumen(?: del)?)\s+(?:el\s+)?día",    skill_orquestar, 0),
    (r"(?:briefing|morning\s+brief|resumen\s+completo|todo\s+de\s+hoy)",       skill_orquestar, 0),
    (r"(?:cómo\s+está|estado\s+(?:del\s+)?(?:mercado|finanzas?|dólar|plata))", skill_orquestar, 0),

    # ── Análisis de archivos / repos ──────────────────────────
    # "puedes ver este repositorio" / "podés ver el repo" / "ves el repo"
    (r"(?:podés?|puedes?|podes?)\s+ver\s+(?:el\s+|este\s+|los?\s+)?(?:repo(?:sitorio)?|proyecto|código|files?)\b(.*)",
                                                                               skill_analizar_repo,    0),
    (r"(?:ves|estás\s+en|estoy\s+en)\s+(?:el\s+|este\s+)?(?:repo(?:sitorio)?|proyecto)\b(.*)",
                                                                               skill_analizar_repo,    0),
    (r"(?:conocés?|conoces?|sabés?|sabes?)\s+(?:el\s+|este\s+)?(?:repo(?:sitorio)?|proyecto|código)\b(.*)",
                                                                               skill_analizar_repo,    0),
    (r"(?:analiz[aá][r]?|revis[aá][r]?|examin[aá][r]?)\s+"
     r"(?:el\s+)?(?:repo(?:sitorio)?|proyecto|project)\s*(.*)",                skill_analizar_repo,    0),
    (r"(?:analiz[aá][r]?|revis[aá][r]?|examin[aá][r]?)\s+"
     r"(?:el\s+|los\s+|estos\s+)?(?:archivo[s]?|fichero[s]?|código[s]?|file[s]?)\s+(.+)",
                                                                               skill_analizar_archivo, 0),
    (r"(?:qué hace|qué es|explicame|explicá(?:me)?)\s+"
     r"(?:el\s+)?(?:archivo|fichero|código|este)\s+(.+\.\w+)",                 skill_analizar_archivo, 0),

    # ── Visión ────────────────────────────────────────────────
    # "describí lo que ves" / "qué ves" / "describí" sin argumento → pantalla
    (r"^(?:describí?(?:me)?|describe(?:me)?)\s+lo\s+que\s+ves\b.*",           skill_ver_pantalla, 0),
    (r"^(?:qué ves|que ves|qué estás viendo|que estas viendo)\??$",            skill_ver_pantalla, 0),
    (r"(?:qué ves|que ves|analiz[aá]|describí?|qué hay en|qué estoy viendo)\s+"
     r"(?:la\s+)?(?:pantalla|screen)(?:\s+.*)?",                               skill_ver_pantalla, 0),
    (r"(?:mirá|mira|qué ves|que ves|analiz[aá]|describí?)\s+"
     r"(?:en\s+(?:mi\s+|tu\s+)?|con\s+la\s+|por\s+la\s+)?(?:cámara|camara|webcam)(?:\s+.*)?",
                                                                               skill_ver_camara,   0),
    (r"(?:identific[aá][r]?|reconoc[eé][r]?|qué objeto|qué es esto)\s*"
     r"(?:con la cámara|frente a la cámara|esto)?",                            skill_identificar_objeto, None),
    (r"(?:recre[aá][r]?|mode[lá]?[r]?|hace[r]?\s+(?:en|para))\s+"
     r"(?:blender|autocad|freecad|3d|cad)\s*(?:esto|el objeto)?(?:\s+.*)?",   skill_objeto_a_cad, 0),
    (r"(?:analiz[aá][r]?\s+(?:para|en)\s+(?:blender|autocad|freecad|cad)|"
     r"objeto\s+para\s+(?:blender|autocad|freecad))",                          skill_objeto_a_cad, 0),

    # ── Gestos ────────────────────────────────────────────────
    # ── Gestos / Detector ─────────────────────────────────────────
    (r"activ[aá][r]?\s+(?:el\s+)?(?:control|detector)\s+de\s+gestos?(.*)",    skill_gestos_activar,   0),
    (r"activ[aá][r]?\s+(?:el\s+)?(?:detector\s+de\s+)?gestos?(\s+\w+)?",     skill_gestos_activar,   0),
    (r"(?:modo\s+gestos?|gestos?\s+on|usar\s+gestos?|iniciar?\s+gestos?)(.*)",skill_gestos_activar,   0),
    (r"(?:modo\s+)?(?:mesa(?:\s+de\s+arena)?|arena)\s*(?:de\s+gestos?)?",     skill_gestos_modo,      0),
    (r"(?:modo\s+)?pantalla\s*(?:de\s+gestos?|con\s+gestos?)",                skill_gestos_modo,      0),
    (r"cambi[aá][r]?\s+(?:la\s+)?cámara\s*(\d*)",                            skill_gestos_camara,    0),
    (r"cambi[aá][r]?\s+(?:a\s+)?cámara\s+(\d+)",                             skill_gestos_camara,    1),
    (r"calibr[aá][r]?\s+(?:el\s+)?(?:detector|gestos?|cámara)?",             skill_gestos_calibrar,  None),
    (r"(?:abrir?|mostrar?|ver)\s+(?:la\s+)?(?:gui|interfaz)\s+(?:de\s+)?gestos?",
                                                                               skill_gestos_gui,       None),
    (r"(?:desactiv[aá][r]?\s+(?:el\s+)?(?:control|detector)\s+de\s+)?gestos?\s+off",
                                                                               skill_gestos_desactivar, None),
    (r"desactiv[aá][r]?\s+(?:el\s+)?(?:control|detector)\s+de\s+gestos?",    skill_gestos_desactivar, None),
    (r"desactiv[aá][r]?\s+(?:el\s+)?(?:detector\s+de\s+)?gestos?",           skill_gestos_desactivar, None),
    (r"(?:estado|status)\s+(?:de\s+(?:los\s+)?)?(?:gestos?|detector)",        skill_gestos_estado,    None),

    # ── Blender 3D ────────────────────────────────────────────
    (r"(?:abrí[r]?|abrir?|abré|lanzá[r]?|iniciar?)\s+blender",                skill_blender_abrir,  None),
    (r"(?:estado|estado\s+de)\s+blender",                                      skill_blender_estado, None),
    (r"(?:blender\s+(?:conectado|activo|listo|disponible)\??)",                skill_blender_estado, None),
    (r"(?:crea[r]?|creá|genera[r]?|generá|model[aá][r]?|diseña[r]?|diseñá|"
     r"constru(?:ye[r]?|í[r]?)?)\s+(?:en\s+)?blender\s+(.*)",                 skill_blender_crear,  1),
    (r"(?:un\s+objeto\s+en\s+blender|modelo\s+3d\s+de?|"
     r"(?:en\s+)?blender[,:]?\s+crea[rá]?)\s+(.*)",                            skill_blender_crear,  1),
    (r"(?:ejecuta[r]?|ejecutá|corre[r]?|corré)\s+(?:esto\s+)?en\s+blender\s+(.*)",
                                                                               skill_blender_ejecutar, 1),
    (r"(?:aprob[aá][r]?|guard[aá][r]?\s+como\s+ejemplo|aprend[eé][r]?\s+(?:este|ese|el)\s+(?:script|modelo|objeto))",
                                                                               skill_blender_aprobar, 0),

    # ── Imágenes (Pollinations.ai) ────────────────────────────
    # ── n8n: Gastos ───────────────────────────────────────────
    (r"(?:cuánto gasté|gastos?|cuánto.*gastado|mis gastos?|resumen.*gastos?)"
     r"(?:.*?(hoy|esta semana|este mes|semana|mes))?",                          skill_gastos,    1),

    # ── n8n: Crear evento (ANTES que consultar para que "crea evento" no matchee calendario)
    (r"(?:agenda[r]?|crea[r]?\s+(?:un\s+)?(?:nuevo\s+)?evento|agrega[r]?|añadi[r]?|"
     r"añade?\s+(?:al?\s+)?calendario|programa[r]?|schedule|nuevo\s+evento|"
     r"agregar?\s+evento|crea[r]?\s+(?:una?\s+)?reuni[oó]n)\s+(.+)",           skill_crear_evento, 1),
    # "crea un almuerzo/reunión/cita a las HH" — evento por título genérico + hora
    (r"crea[r]?\s+(?:un[ao]?\s+)?"
     r"(?!(?:archivo|file|documento|doc|nota|script|código)\b)(\w[\w\s]+?)\s+"
     r"(?:a\s+las?\s+\d{1,2}(?::\d{2})?|\s*\d{1,2}:\d{2})",                  skill_crear_evento, 1),

    # ── n8n: Calendario consultar ─────────────────────────────
    (r"(?:qué tengo|mis?\s+eventos?|qué\s+eventos?|mis?\s+reuniones?|qué reuniones?|qué hay|"
     r"mi calendario|algo en (?:mi )?calendario|ver calendario|calendario|"
     r"revisa(?:r)? (?:el )?calendario|check (?:el )?calendario|"
     r"qué dice (?:el )?calendario|qué hay en (?:el )?calendario)"
     r"(?:.*?(hoy|mañana|esta semana|semana))?",                                skill_calendario, 1),

    # ── n8n: Crear archivo ────────────────────────────────────
    (r"(?:crea?r?|crea)\s+(?:un?\s+)?(?:archivo|file|documento|doc|nota)\s+(.+)",
                                                                               skill_crear_archivo, 1),

    # ── n8n: Estado ───────────────────────────────────────────
    (r"(?:estado.*n8n|n8n.*activo|conectado.*n8n|status.*n8n)",                skill_estado_n8n, None),

    # ── Google Drive ─────────────────────────────────────────
    # Buscar en Drive — requiere "drive" o "en drive" para no chocar con web_search
    (r"(?:busca[r]?|encuentra[r]?|encontra[r]?|search)\s+en\s+(?:drive|google\s*drive|mi\s*drive)\s+(.+)",
                                                                               skill_drive_buscar, 1),
    (r"(?:busca[r]?|encuentra[r]?|encontra[r]?|search)\s+(?:el\s+|la\s+|un\s+|una\s+)?(?:archivo|carpeta|doc(?:umento)?|file)\s+(.+)\s+en\s+drive",
                                                                               skill_drive_buscar, 1),
    (r"drive\s+(?:busca[r]?|search)\s+(.+)",                                  skill_drive_buscar, 1),
    # Leer archivo de Drive
    (r"(?:lee[r]?|abri[r]?|mostra[r]?|muestra|abre)\s+"
     r"(?:el\s+|la\s+)?(?:archivo|documento|doc|file)\s+(?:de\s+drive\s+)?(?:de\s+)?(.+)",
                                                                               skill_drive_leer,   0),
    (r"(?:lee[r]?\s+ese|abrir?\s+ese|lee\s+eso|abre\s+ese|muéstrame\s+ese)\s*"
     r"(?:archivo|documento|doc)?",                                            skill_drive_leer,   None),
    # Crear en Drive
    (r"(?:crea[r]?|hace[r]?|genera[r]?|nuevo|nueva)\s+"
     r"(?:un\s+|una\s+)?(?:documento|doc|archivo|nota)\s+"
     r"en\s+(?:drive|google\s*drive|mi\s*drive)\s+(.+)",                      skill_drive_crear,  1),
    # Listar Drive — acepta "lista drive", "drive listar", "drive listado", "drive", etc.
    (r"^drive\s*(?:lista[rd]o?|listar?|ver|mostrar?)?\s*$",                   skill_drive_listar, None),
    (r"(?:lista[r]?|listar|ver|mostrar?|muéstrame|dame)\s+drive\b",           skill_drive_listar, None),
    (r"drive\s+(?:lista[rd]o?|listar?|ver|mostrar?)",                         skill_drive_listar, None),
    (r"(?:lista[r]?|listar|ver|mostrar?|muéstrame|dame|qué tengo|qué hay)\s+"
     r"(?:mis?\s+)?(?:archivos?|documentos?|carpetas?)\s+"
     r"(?:de\s+|en\s+)(?:drive|google\s*drive|mi\s*drive)\b",                skill_drive_listar, None),
    (r"(?:mis?\s+)?archivos?\s+(?:de\s+|en\s+)(?:drive|google\s*drive|mi\s*drive)\b",
                                                                               skill_drive_listar, None),
    (r"(?:lista mis archivos|ver drive|qué hay en drive|"
     r"abrir? drive|abre drive|archivos de drive|google drive listar|"
     r"mis documentos de drive|listar drive|qué tengo en drive|"
     r"muéstrame mis archivos de drive)",                                     skill_drive_listar, None),

    # ── Gmail directo (sin n8n) ──────────────────────────────
    (r"(?:busca[r]?|encontra[r]?|busca(?:me)?)\s+"
     r"(?:el\s+|un\s+|ese\s+)?(?:mail|email|correo)\s+(?:de|sobre|del?|con)?\s*(.+)",
                                                                                skill_gmail_buscar, 1),
    (r"(?:mail|email|correo)\s+(?:de|sobre|del?)\s+(.+)",                      skill_gmail_buscar, 1),
    (r"(?:tengo\s+)?(?:mails?|emails?|correos?)(?:\s+nuevos?|\s+urgentes?|\s+importantes?|"
     r"\s+del\s+\w+|\s+sin\s+leer)?(?:\s*\?)?",                                skill_gmail_no_leidos, 0),
    (r"(?:revisar?|ver|mostrar?|que\s+(?:hay|llego|llegó))\s+"
     r"(?:en\s+)?(?:mis?\s+)?(?:mails?|emails?|correos?)",                     skill_gmail_no_leidos, 0),

    # ── Calendar directo (sin n8n) ────────────────────────────
    (r"(?:tengo\s+)?(?:eventos?|citas?|turno|agenda|reuniones?)"
     r"(?:\s+(?:hoy|mañana|esta\s+semana))?(?:\s*\?)?",                        skill_calendar, 0),
    (r"(?:qué\s+tengo\s+(?:hoy|mañana|esta\s+semana)|"
     r"(?:ver|revisar?|mostrar?)\s+(?:mi\s+)?(?:agenda|calendario)|"
     r"(?:qué\s+hay\s+(?:hoy|mañana|esta\s+semana))|"
     r"(?:agenda\s+(?:de\s+)?(?:hoy|mañana|esta\s+semana)))",                  skill_calendar, 0),

    # ── Drive directo (sin n8n) ───────────────────────────────
    (r"(?:busca[r]?\s+en\s+drive|encuentra\s+en\s+drive)\s+(.+)",              skill_drive_buscar_directo, 1),

    # ── Email: Acción ─────────────────────────────────────────
    (r"(?:archiva?|elimina?|borra?|marca?|agenda?|registra?)\s+"
     r"(?:el\s+|ese\s+|ese\s+)?(?:mail|email|correo)\s+([0-9a-fA-F]{6,})",    skill_email_accion, 0),
    (r"(?:archiva?|elimina?|borra?|marca?|agenda?|registra?)\s+.*"
     r"(?:mail|email|correo).*([0-9a-fA-F]{6,})",                              skill_email_accion, 0),

    # ── OCR / Lectura de archivos ─────────────────────────────
    (r"(?:lee|leer|analiza|analizar|convierte?|extrae?|abre?)\s+"
     r"(?:el\s+|este\s+|la\s+)?(?:archivo|pdf|word|excel|documento|imagen|foto)\b",
                                                                               skill_leer_archivo, 0),
    (r"(?:lee|leer|analiza)\s+.+\.(?:pdf|docx|xlsx|pptx|txt|md|csv|png|jpg|jpeg)\b",
                                                                               skill_leer_archivo, 0),

    # ── Cambio de idioma (explícito, usuario lo pide) ─────────
    (r"(?:habla|háblame|responde?|cambia?|pon(?:te)?|usa)\s+(?:en|al?)\s+"
     r"(?:inglés|ingles|english|francés|frances|french|portugués|portugues|"
     r"portuguese|alemán|aleman|german|italiano|italian|ruso|russian|español|"
     r"castellano|spanish)",
                                                                               skill_cambiar_idioma, 0),
    (r"(?:vuelve|regresa?|cambia?)\s+(?:al?\s+)?español",                     skill_cambiar_idioma, 0),
    (r"(?:let'?s\s+)?(?:speak|talk)\s+in\s+\w+",                             skill_cambiar_idioma, 0),
    # ── Configurar API key desde chat ────────────────────────────
    (r"(?:mi\s+)?(?:api|key|token)\s+(?:de\s+|del?\s+)?\w+\s+(?:es|:)\s+\S{15,}",
                                                                               skill_configurar_apikey, 0),
    (r"(?:configura[r]?|guarda[r]?|agrega[r]?|setea[r]?)\s+(?:la\s+)?(?:api|key|token)\s+(?:de\s+)?\w+",
                                                                               skill_configurar_apikey, 0),

    # ── Modelos / proveedores LLM custom ─────────────────────────
    (r"agrega(?:r)?\s+(?:modelo|proveedor|llm)",                               skill_agregar_modelo, 0),
    (r"nuevo\s+(?:modelo|proveedor|llm)",                                       skill_agregar_modelo, 0),
    (r"a[nñ]ade?\s+(?:modelo|proveedor|llm)",                                  skill_agregar_modelo, 0),
    (r"(?:lista[r]?|ver|mostrar)\s+(?:modelos?|proveedores?)",                 skill_listar_modelos, 0),
    (r"qu[eé]\s+modelos?\s+(?:hay|ten[eé]s|disponibles?)",                    skill_listar_modelos, 0),
]

# Frases completas que indican búsqueda en tiempo real
# (deliberadamente específicas para evitar falsos positivos)
_REALTIME_KEYWORDS = [
    "últimas noticias", "noticias de hoy", "precio actual", "precio del",
    "temperatura hoy", "clima hoy", "quién ganó", "resultado de",
    "novedades de", "en vivo", "trending", "qué pasó con",
    "cuánto cuesta", "cotización", "tipo de cambio", "dólar hoy",
    "partido de hoy", "estreno de", "lanzamiento de",
]


def capabilities_summary() -> str:
    base = (
        "SKILLS EJECUTABLES (los ejecuto yo directamente, sin LLM):\n"
        "- Hora y fecha actual: 'qué hora es', 'qué día es', 'fecha de hoy'\n"
        "- Abrir/cerrar apps: 'abre Safari', 'cierra Spotify'\n"
        "- Ejecutar comandos de terminal: 'ejecuta el comando ls'\n"
        "- Control música: 'pon música', 'pausa', 'siguiente canción'\n"
        "- Volumen del sistema: 'sube el volumen', 'volumen 50'\n"
        "- Screenshot: 'captura de pantalla'\n"
        "- Archivos: crear, leer, editar, listar, buscar\n"
        "- Temporizadores: 'temporizador 5 minutos'\n"
        "- Búsqueda web: 'busca en Google X', 'busca X'\n"
        "- Memoria persistente: 'recuerda que...', 'qué recuerdas de mí'\n"
        "- n8n workflows: gastos, eventos de calendario, Gmail\n"
        "- Morning briefing: 'briefing matutino', 'morning briefing', 'resumen del día'\n"
        "- Dictado: 'modo dictado', 'dicta en app: ...'\n"
    )
    if _HAS_NOVA_ENHANCED:
        base += (
            "- Mouse: 'lleva el mouse al centro', 'mouse a 500 300', 'mouse arriba'\n"
            "- Click: 'haz click', 'click izquierdo'\n"
            "- Ver pantalla: 'qué ves en pantalla', 'describe la pantalla', 'analiza la pantalla'\n"
            "- Alarmas: 'alarma a las 8:30'\n"
        )
    base += (
        "IMPORTANTE: Cuando el historial muestra que ya respondí con un skill (ej. di la hora), "
        "NO digas que no tengo acceso a esa información. Ya la ejecuté."
    )
    return base


def _dispatch_nova_enhanced(user_input: str) -> str | None:
    """Rutea comandos de Nova Enhanced antes del dispatcher genérico."""
    if not _HAS_NOVA_ENHANCED:
        return None

    lower = user_input.lower()

    # Abrir app + crear documento nuevo (flujo específico de Nova Enhanced)
    open_create = re.search(
        r"(?:abre|abrir|inicia|iniciar|lanza|lanzar)\s+(.+?)\s+(?:y|e)\s+"
        r"(?:crea|crear|abre)\s+(?:un\s+)?(?:documento|archivo|doc)(?:\s+nuevo)?",
        user_input,
        flags=re.I,
    )
    if open_create:
        app = open_create.group(1).strip()
        try:
            return _get_nova_enhanced().open_and_create(app)
        except Exception as e:
            return f"No pude iniciar flujo avanzado para {app}: {e}"

    enhanced_intents = [
        (r"(?:temporizador|timer|recordatorio)\b.*\d+(?:[.,]\d+)?\s*(?:minutos?|mins?|m)\b", _enh_skill_set_timer),
        (r"(?:alarma|despertador)\b.*\d{1,2}:\d{2}(?:\s*(?:am|pm))?\b", _enh_skill_set_alarm),
        # Visión — ampliado para cubrir variantes naturales de voz
        (r"(?:qué ves|que ves|ver pantalla|analiza(?:r)? (?:la )?pantalla|"
         r"qué hay en (?:la )?pantalla|mira(?:r)? (?:la )?pantalla|"
         r"describe(?:r)? (?:la )?pantalla|qué se ve|captura y describe|"
         r"analiza (?:la )?imagen|foto de (?:la )?pantalla|"
         r"qué está pasando en (?:la )?pantalla|muestra(?:r)? (?:la )?pantalla|"
         r"muéstrame (?:la )?pantalla|mira la pantalla|qué ves en (?:la )?pantalla|"
         r"screenshot y describe|toma una foto de (?:la )?pantalla)\b", _enh_skill_see_screen),
        # Mouse — ampliado (con y sin verbo inicial, incluye "maus" = pronunciación ES)
        (r"(?:mueve|mover|lleva|llevar|pon|poner|desplaza|ir|lleva|llevar|corre|manda)\b.*(?:mouse|cursor|rat[oó]n|puntero|maus)\b", _enh_skill_move_mouse),
        (r"(?:mouse|cursor|rat[oó]n|puntero|maus)\s+(?:al?\s+)?(?:centro|arriba|abajo|izquierda|derecha|\d+\s+\d+)\b", _enh_skill_move_mouse),
        # Coordenadas directas: "a 300 500" cuando contexto de mouse está presente
        (r"(?:llevar?|mover?|maus|mouse|cursor)\s+a\s+\d+\s+\d+", _enh_skill_move_mouse),
        # Click — ampliado
        (r"(?:haz|hacer|da(?:r)?|presiona(?:r)?|apreta(?:r)?|clica(?:r)?)\s+(?:un\s+)?click\b", _enh_skill_click),
        (r"(?:figma|sketch|photoshop|illustrator|xd)\b.*(?:frame|componente|component|zoom|export|artboard|capa|layer)\b", _enh_skill_design_app),
    ]

    for pattern, handler in enhanced_intents:
        if re.search(pattern, lower, flags=re.I):
            return handler(user_input)

    return None


def maybe_clarify_command(user_input: str) -> str | None:
    lower = user_input.strip().lower()
    ambiguous = {
        "abre": "¿Qué quieres que abra, Señor? Puedes decir: 'abre Safari' o 'abre archivo ~/Desktop/nota.txt'.",
        "abrir": "¿Qué quieres abrir exactamente, Señor?",
        "cierra": "¿Qué app debo cerrar, Señor?",
        "cerrar": "¿Qué app debo cerrar, Señor? Para cerrar Nova, di 'cerrar Nova' o 'Nova salir'.",
        "busca": "¿Qué quieres que busque, Señor? Puedo buscar en web o archivos.",
        "buscar": "Indícame qué término quieres buscar, Señor.",
        "ejecuta": "Necesito el comando exacto. Ejemplo: 'ejecuta el comando ls -la'.",
        "comando": "Dime el comando completo a ejecutar, Señor.",
        "escribe": "¿Dónde quieres que escriba, Señor? Puedes decir: 'escribe en Pages: ...' o 'escribe: ...'.",
        "dicta": "¿En qué app quieres dictar, Señor? Ejemplo: 'dicta en Word: ...'.",
        "crea archivo": "Necesito ruta y contenido. Ejemplo: 'crea archivo notas.txt con hola mundo'.",
        "edita archivo": "Indica la ruta del archivo que quieres editar, Señor.",
    }
    if lower in ambiguous:
        return ambiguous[lower]
    if re.fullmatch(r"(abre|cierra|busca|ejecuta|escribe|dicta|crea|edita)\s*", lower):
        return "La orden quedó incompleta, Señor. Dame un poco más de detalle para ejecutarla."
    return None


def dispatch(user_input: str) -> str | None:
    """
    Intenta hacer match con un skill registrado.
    Devuelve la respuesta del skill, o None si no hay match (→ LLM).
    """
    lower = user_input.strip().lower()
    clarification = maybe_clarify_command(user_input)
    if clarification:
        return clarification

    # ── Morning briefing ─────────────────────────────────────
    if re.search(
        r"(?:morning\s+bri[ef]+ing|bri[ef]+ing\s+matutino|resumen\s+(?:del\s+)?d[ií]a|"
        r"resumen\s+matutino|novedades\s+del\s+d[ií]a|qu[eé]\s+pas[oó]\s+hoy)",
        lower, re.I
    ):
        try:
            from nova.agents.morning_digest import morning_digest
            return morning_digest()
        except Exception as e:
            return f"No pude generar el briefing matutino, Señor. {e}"

    enhanced_resp = _dispatch_nova_enhanced(user_input)
    if enhanced_resp is not None:
        return enhanced_resp

    # ── Música: volumen numérico ─────────────────────────────
    music_vol_match = re.search(
        r"(?:volumen.*música|música.*volumen|sube.*música|baja.*música|"
        r"volumen.*musica|musica.*volumen).*?(\d+)", lower
    )
    if music_vol_match:
        return music_volume(int(music_vol_match.group(1)))

    # ── Terminal: pre-check antes de open_app ──────────────────────
    # open_app tiene "ejecuta" en su regex, esto tiene prioridad
    terminal_match = re.search(
        r"(?:ejecuta(?:\s+el)?\s+comando|corre(?:\s+el)?\s+comando|run command"
        r"|en\s+terminal|terminal:|comando:)\s*:?\s*(.+)",
        lower
    )
    if terminal_match:
        return run_command(terminal_match.group(1).strip())

    # ── Piloto automático: debe ir ANTES que open_app ──────
    pilot_match = re.search(
        r"(?:piloto\s+autom[aá]tico|hazlo\s+t[uú]|toma\s+el\s+control|maneja\s+(?:el\s+)?(?:mouse|ratón)|opera\s+por\s+m[ií])"
        r"\s*(?:para|que)?[:,\s]*(.*)",
        lower, re.I
    )
    if pilot_match:
        return computer_pilot_mode(pilot_match.group(1).strip())

    # ── URLs: abre X.com/org/net → browser antes que open_app ──
    url_match = re.search(
        r"^(?:abre|abrir|navega|ir\s+a|entra\s+a)\s+([\w\-]+(?:\.[a-z]{2,6})(?:/\S*)?|(?:google|youtube|gmail|instagram|linkedin|twitter|github)\.com)\s*$",
        lower, re.I
    )
    if url_match:
        url = url_match.group(1).strip()
        if not url.startswith("http"):
            url = "https://" + url
        return _skill_abrir_url(url) if _HAS_BROWSER else web_search(url_match.group(1))

    # ── Qué hay en carpeta/escritorio/descargas ──────────────
    quehayen = re.search(
        r"(?:qu[eé]\s+hay\s+en|lista|listar|muestra|ver)\s+"
        r"(?:mi\s+)?(?:escritorio|desktop|descargas|downloads|documentos|documents|(?:la\s+)?carpeta\s+(.+))",
        lower, re.I
    )
    if quehayen:
        _FOLDER_MAP = {
            "escritorio": "~/Desktop", "desktop": "~/Desktop",
            "descargas": "~/Downloads", "downloads": "~/Downloads",
            "documentos": "~/Documents", "documents": "~/Documents",
        }
        for es, path in _FOLDER_MAP.items():
            if es in lower:
                return list_directory(path)
        carpeta = quehayen.group(1)
        return list_directory(carpeta) if carpeta else list_directory("~")

    # ── Notas: "toma nota de X" / "anota X" (forma simple) ──
    # No capturar si menciona diario/obsidian (eso se maneja en _INTENTS)
    toma_nota = re.search(
        r"^(?:toma\s+nota\s+(?:de\s+)?|anota\s+|apunta\s+)"
        r"(?!(?:en\s+(?:el\s+)?(?:diario|obsidian|cerebro|vault)|al\s+diario))(.+)$",
        lower
    )
    if toma_nota:
        body  = toma_nota.group(1).strip()
        title = body[:50]
        return notes_create(title, body)

    # ── Notas: "crea una nota llamada X con Y" ───────────────
    note_create_match = re.search(
        r"(?:crea(?:r)?\s+(?:una?\s+)?nota)"
        r"(?:\s+(?:llamada?|titulada?|sobre)\s+(.+?))?"
        r"(?:\s+(?:con|que diga|que dice|:)\s+(.+))?$",
        lower
    )
    if note_create_match:
        title = (note_create_match.group(1) or "Nota NOVA").strip()
        body  = (note_create_match.group(2) or "").strip()
        return notes_create(title, body)

    # ── Notas: añadir a nota existente ──────────────────────
    note_append_match = re.search(
        r"(?:añade?|agrega?|escribe|agrega)\s+(?:a\s+la\s+nota\s+)?(.+?)"
        r"\s+(?:en la nota|en notas|a la nota)\s+(.+)",
        lower
    )
    if note_append_match:
        return notes_append(note_append_match.group(2).strip(),
                            note_append_match.group(1).strip())

    # ── Dictado: "escribe en Pages/Word: texto" ──────────────
    dictate_pages = re.search(
        r"(?:escribe|redacta|dicta)\s+(?:en\s+pages|en\s+un\s+documento|"
        r"un\s+documento\s+(?:nuevo\s+)?(?:en\s+pages)?)\s*:?\s*(.+)",
        lower
    )
    if dictate_pages:
        return pages_new_doc_with_text(user_input[dictate_pages.start(1):].strip())

    dictate_word = re.search(
        r"(?:escribe|redacta|dicta)\s+(?:en\s+word|en\s+microsoft\s+word)\s*:?\s*(.+)",
        lower
    )
    if dictate_word:
        return word_new_doc_with_text(user_input[dictate_word.start(1):].strip())

    # ── Dictado genérico: "escribe en [app]: texto" ──────────
    dictate_app_match = re.search(
        r"(?:escribe|escribe en|dicta en|abre\s+(.+?)\s+y\s+escribe)\s+"
        r"en\s+(?:la\s+app\s+)?(.+?)\s*[:\-]\s*(.+)",
        lower
    )
    if dictate_app_match:
        app  = (dictate_app_match.group(1) or dictate_app_match.group(2)).strip()
        text = dictate_app_match.group(3).strip()
        return dictate_to_app(app, text)

    # ── Escribir en app activa: "escribe: texto" ────────────
    type_match = re.search(
        r"^(?:escribe|teclea|tipea)\s*:\s*(.+)", lower
    )
    if type_match:
        return type_in_active_app(user_input[type_match.start(1):].strip())

    # Volumen con nivel explícito (ej: "pon el volumen a 60")
    vol_match = re.search(
        r"(?:pon|ajusta|sube|baja|set).*volumen.*?(\d+)", lower
    )
    if vol_match:
        return set_volume(int(vol_match.group(1)))

    # Temporizador (ej: "pon un temporizador de 5 minutos")
    timer_match = re.search(
        r"(?:temporizador|timer|alarma).*?(\d+)\s*(minuto|segundo|min|seg|minute|second)",
        lower,
    )
    if timer_match:
        n = int(timer_match.group(1))
        unit = timer_match.group(2)
        secs = n * 60 if "min" in unit else n
        return set_timer(secs, f"Temporizador {n} {'min' if 'min' in unit else 'seg'}")

    # Resto de intents
    # Velocidad de voz numérica
    speed_match = re.search(r"(?:velocidad de voz|pon la velocidad).*?(\d+)", lower)
    if speed_match:
        return set_voice_speed(int(speed_match.group(1)))

    # ── Red local y Bluetooth (patrones flexibles) ────────────────
    if re.search(
        r"(?:dispositivos?|qui[eé]n|que\s+hay|qu[eé]\s+hay|qu[eé]\s+tiene|ver|lista[r]?|escanea[r]?|mostrar?)"
        r".{0,20}"
        r"(?:en\s+(?:la\s+|mi\s+)?red|en\s+wifi|red\s+local|conectados|en\s+la\s+lan)",
        lower, re.I
    ):
        return skill_scan_red()

    if re.search(
        r"(?:dispositivos?\s+bluetooth|bluetooth|bt\s+cercanos?|"
        r"qui[eé]n\s+(?:hay|tiene)\s+bluetooth|ver\s+bluetooth|"
        r"escanea[r]?\s+bluetooth|lista[r]?\s+bluetooth|conectar\s+bluetooth)",
        lower, re.I
    ):
        return skill_scan_bluetooth()

    for pattern, handler, group in _INTENTS:
        if handler is None:
            continue
        match = re.search(pattern, user_input, flags=re.I)
        if match:
            # Caso especial para lambdas con múltiples argumentos en el regex
            if group == 1 and match.lastindex and match.lastindex > 1:
                try:
                    return handler(*match.groups())
                except Exception as e:
                    return f"Error en ejecución de comando: {e}"

            if group is not None:
                try:
                    captured = match.group(group)
                    arg = captured.strip() if captured is not None else ""
                    return handler(arg)
                except (IndexError, AttributeError):
                    return handler()
            return handler()

    return None  # sin match → ir al LLM


# ─── LLM Tool Dispatcher ──────────────────────────────────────────────────────
# Catálogo de tools que el LLM puede seleccionar cuando regex no matcheó.
# Formato: "clave": (descripción, handler, arg_type)
#   arg_type = None → sin args | "text" → texto libre | "location" → ciudad
_TOOL_CATALOG: dict[str, tuple] = {
    "scan_red":        ("Descubrir dispositivos conectados a la red local (wifi/ethernet)",
                        skill_scan_red, None),
    "scan_bluetooth":  ("Listar dispositivos Bluetooth cercanos o pareados",
                        skill_scan_bluetooth, None),
    "get_weather":     ("Clima actual de una ciudad o ubicación",
                        get_weather, "location"),
    "get_forecast":    ("Pronóstico extendido de 3 días para una ciudad",
                        get_forecast, "location"),
    "skill_imagen":    ("Generar una imagen a partir de texto (arte, foto, render, etc.)",
                        skill_imagen, "text"),
    "skill_calendario":("Ver eventos del calendario (hoy, mañana, semana)",
                        skill_calendario, "text"),
    "web_search":      ("Buscar en internet información actualizada",
                        web_search, "text"),
    "skill_cerebro":   ("Buscar en el Cerebro/Obsidian del usuario (notas personales)",
                        obsidian_busca, "text"),
    "skill_hora":      ("Decir la hora y fecha actuales",
                        lambda: __import__('datetime').datetime.now().strftime("Son las %H:%M del %d/%m/%Y"), None),
    "skill_run":       ("Ejecutar un comando de terminal en el sistema",
                        run_command, "text"),
    "skill_volumen":   ("Cambiar el volumen del sistema a un nivel",
                        set_volume, "text"),
    "ver_camara":      ("Ver qué hay frente a la cámara, identificar objeto, qué estoy sosteniendo",
                        lambda t="": skill_ver_camara(t), "text"),
    "ver_pantalla":    ("Analizar o describir lo que hay en la pantalla ahora",
                        skill_ver_pantalla, None),
    "gestos_activar":  ("Activar el detector de gestos con las manos para controlar el sistema",
                        skill_gestos_activar, None),
    "gestos_desactivar":("Desactivar el detector de gestos",
                        skill_gestos_desactivar, None),
    "blender_crear":   ("Crear o modelar un objeto 3D en Blender a partir de descripción",
                        skill_blender_crear, "text"),
    "objeto_a_cad":    ("Ver objeto en cámara y recrearlo en Blender en 3D",
                        skill_objeto_a_cad, None),
    "especialista":    ("Consultar a un agente especializado (firmware, arquitecto, IA, etc.)",
                        skill_especialista, "text"),
    "listar_agentes":  ("Listar los agentes especializados disponibles por categoría",
                        skill_listar_agentes, "text"),
    "traducir":        ("Traducir texto a otro idioma (inglés, francés, alemán, etc.)",
                        skill_traducir, "text"),
    "crypto":          ("Ver precio de criptomonedas en tiempo real: bitcoin, ethereum, etc.",
                        skill_crypto, "text"),
    "forex":           ("Tipo de cambio entre divisas: dólar, euro, libra, yen, etc.",
                        skill_forex, "text"),
    "feriados":        ("Ver feriados nacionales de Argentina u otro país",
                        skill_feriados, "text"),
    "crear_proyecto":  ("Crear un proyecto completo con archivos reales en disco (repo, código, README)",
                        skill_crear_proyecto, "text"),
    "abrir_proyecto":  ("Abrir un proyecto existente y establecerlo como activo para trabajar",
                        skill_abrir_proyecto, "text"),
    "leer_archivo":    ("Leer el contenido de un archivo del proyecto activo",
                        skill_leer_archivo_proyecto, "text"),
    "editar_proyecto": ("Editar o crear archivos en el proyecto activo usando IA",
                        skill_editar_proyecto, "text"),
    "estructura_proyecto": ("Ver la estructura de archivos del proyecto activo",
                        skill_estructura_proyecto, None),
    "mejorar_proyecto": ("Lanzar múltiples agentes en paralelo para mejorar el proyecto activo",
                        skill_mejorar_proyecto, "text"),
    "codear_con_docs":  ("Buscar documentación real en la web y generar código con un especialista",
                        skill_codear_con_docs, "text"),
    "generar_tests":    ("Generar tests pytest para un archivo del proyecto activo y ejecutarlos",
                        skill_generar_tests, "text"),
    "lsp_definicion":   ("Buscar dónde está definida una función, clase o símbolo en el proyecto",
                        skill_lsp_definicion, "text"),
    "lsp_referencias":  ("Buscar dónde se usa un símbolo en el proyecto activo",
                        skill_lsp_referencias, "text"),
    "lsp_analizar":     ("Analizar un archivo Python: funciones, clases, imports y errores",
                        skill_lsp_analizar, "text"),
    "lsp_diagnostico":  ("Diagnosticar errores de sintaxis en un archivo Python",
                        skill_lsp_diagnostico, "text"),
    "lsp_renombrar":    ("Renombrar un símbolo en todo un archivo de forma segura",
                        skill_lsp_renombrar, "text"),
    "dockerizar":       ("Generar Dockerfile + docker-compose.yml para el proyecto activo",
                        skill_dockerizar, "text"),
    "deploy_local":     ("Levantar el proyecto activo en un contenedor Docker local",
                        skill_deploy_local, "text"),
    "planear_misiones": ("Analizar el proyecto y proponer misiones de mejora con agentes especializados",
                        skill_planear_misiones, "text"),
    "ejecutar_misiones": ("Ejecutar las misiones propuestas (todas o seleccionadas por número)",
                        skill_ejecutar_misiones, "text"),
    "git_status":      ("Ver estado del repositorio git: cambios pendientes, rama actual",
                        skill_git_status, None),
    "git_diff":        ("Ver diff de cambios no commiteados en el repositorio git",
                        skill_git_diff, None),
    "git_log":         ("Ver historial de commits del repositorio git",
                        skill_git_log, "text"),
    "git_commit":      ("Hacer commit con mensaje dado o generado automáticamente por IA",
                        skill_git_commit, "text"),
    "git_pr":          ("Generar descripción de Pull Request basada en los commits del branch",
                        skill_git_pr, "text"),
    "skill_leer_archivo": ("Convierte PDF/DOCX/XLSX/imágenes a Markdown y los muestra como contexto",
                        skill_leer_archivo, "text"),
    "cambiar_idioma":   ("Cambiar el idioma de la sesión: inglés, francés, chino, ruso, alemán, portugués",
                        skill_cambiar_idioma, "text"),
    "configurar_api":   ("Guardar una API key en el .env desde el chat (groq, openrouter, anthropic, etc.)",
                        skill_configurar_apikey, "text"),
}


def llm_dispatch(user_input: str) -> str | None:
    """
    Segundo intento de dispatch: pregunta al LLM qué tool usar.
    Solo se activa cuando dispatch() (regex) no encontró match.
    Latencia: ~400ms (force_tier=1, max_tokens=25).
    """
    if not _router:
        return None

    catalog_lines = "\n".join(
        f"- {k}: {desc}" for k, (desc, _, _) in _TOOL_CATALOG.items()
    )
    system = (
        "Sos un selector de herramientas. Dado lo que pide el usuario, "
        "elegí UNA herramienta de la lista o respondé NONE si es una conversación normal.\n\n"
        f"Herramientas disponibles:\n{catalog_lines}\n\n"
        "Reglas:\n"
        "- Si el usuario pide acción que mapea a una tool → respondé SOLO el nombre (ej: scan_red)\n"
        "- Si necesita argumento → respondé: nombre:argumento (ej: get_weather:Córdoba)\n"
        "- Si es pregunta general/conversación → respondé: NONE\n"
        "- Respondé SOLO el nombre de la tool o NONE, sin explicaciones."
    )

    try:
        resp = _router.route(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_input},
            ],
            force_tier=1, max_tokens=25, temperature=0.0,
        )
        raw = resp["response"].strip()

        # Extraer la primera línea no vacía y limpiarla
        first_line = next((l.strip() for l in raw.splitlines() if l.strip()), "")
        answer = first_line.lower().strip('"').strip("'").strip(".")

        if not answer or "none" in answer or len(answer) > 60:
            return None

        # Buscar cualquier clave del catálogo dentro de la respuesta (tolerante)
        tool_key = None
        arg = ""
        for key in _TOOL_CATALOG:
            if key in answer:
                tool_key = key
                # Si hay ":" después de la clave, extraer argumento
                m = re.search(rf"{re.escape(key)}[:\s]+(.+)", answer)
                if m:
                    arg = m.group(1).strip()
                break

        if not tool_key:
            return None

        _, handler, arg_type = _TOOL_CATALOG[tool_key]
        if arg_type and arg:
            return handler(arg)
        return handler()

    except Exception:
        return None


def needs_web_search(user_input: str) -> bool:
    """
    Heurística estricta: solo activa búsqueda cuando el prompt
    contiene frases que claramente necesitan datos en tiempo real.
    Requiere al menos 5 palabras para evitar falsos positivos.
    """
    lower = user_input.strip().lower()
    if len(lower.split()) < 5:
        return False
    return any(kw in lower for kw in _REALTIME_KEYWORDS)


# Export the module itself as 'skills' for backward compatibility with novaesp.py
import sys
skills = sys.modules[__name__]


# Export the module itself as 'skills' for backward compatibility
import sys
skills = sys.modules[__name__]
