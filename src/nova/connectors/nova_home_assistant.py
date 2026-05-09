"""
nova_home_assistant.py
──────────────────────
Conector para Home Assistant — controla dispositivos del hogar inteligente.

Configuración (.env):
  HOMEASSISTANT_URL=http://192.168.1.X:8123
  HOMEASSISTANT_TOKEN=eyJhbGc...  (Settings → Users → Long-Lived Access Tokens)

Entidades típicas:
  light.living_room, switch.tv, vacuum.robot, climate.thermostat
  media_player.salon, cover.garage, scene.movie_time, script.good_night
"""
from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_HA_URL   = (os.getenv("HOMEASSISTANT_URL") or "").rstrip("/")
_HA_TOKEN = os.getenv("HOMEASSISTANT_TOKEN") or ""

# Alias map: ~/.nova/ha_aliases.json  → {"aspiradora": "vacuum.robot", "living": "light.living_room"}
_ALIASES_PATH = Path.home() / ".nova" / "ha_aliases.json"
_aliases: dict[str, str] = {}

def _load_aliases() -> None:
    global _aliases
    if _ALIASES_PATH.exists():
        try:
            _aliases = json.loads(_ALIASES_PATH.read_text(encoding="utf-8"))
        except Exception:
            _aliases = {}

_load_aliases()


def ha_available() -> bool:
    return bool(_HA_URL and _HA_TOKEN)


def _ha_request(method: str, path: str, body: dict | None = None) -> Any:
    url = f"{_HA_URL}/api/{path.lstrip('/')}"
    headers = {"Authorization": f"Bearer {_HA_TOKEN}", "Content-Type": "application/json"}
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=5) as resp:
        raw = resp.read()
        return json.loads(raw) if raw.strip() else {}


def _not_configured() -> str:
    return (
        "Home Assistant no configurado.\n"
        "Agregá en tu .env:\n"
        "  HOMEASSISTANT_URL=http://192.168.1.X:8123\n"
        "  HOMEASSISTANT_TOKEN=eyJhbGc...\n"
        "(Settings → Users → Long-Lived Access Tokens)"
    )


# ─── Resolución de entidades ─────────────────────────────────────────────────

_REMOVE_ARTICLES = re.compile(
    r"^(el |la |los |las |de |del |un |una |al )", re.I
)
_DOMAIN_HINTS: dict[str, list[str]] = {
    "light":        ["luz", "luces", "lampara", "lámpara", "iluminacion", "iluminación"],
    "switch":       ["enchufe", "interruptor", "switch"],
    "vacuum":       ["aspiradora", "robot", "roomba", "roborock"],
    "media_player": ["parlante", "altavoz", "tv", "television", "televisor", "chromecast", "sonos"],
    "climate":      ["aire", "calefaccion", "calefacción", "termostato", "ac"],
    "cover":        ["persiana", "cortina", "garaje", "puerta"],
    "fan":          ["ventilador", "fan"],
    "scene":        ["escena", "modo", "ambiente"],
    "script":       ["rutina", "script"],
}


def _guess_domain(name: str) -> str:
    lower = name.lower()
    for domain, keywords in _DOMAIN_HINTS.items():
        if any(kw in lower for kw in keywords):
            return domain
    return ""


def _resolve_entity(name: str, domain_hint: str = "") -> str:
    """Resuelve un nombre natural a entity_id. Usa aliases primero."""
    if not name:
        return ""
    # Check alias map
    lower = name.lower().strip()
    if lower in _aliases:
        return _aliases[lower]
    # Guess domain
    domain = domain_hint or _guess_domain(lower)
    # Normalize name: remove articles, spaces → underscores
    clean = _REMOVE_ARTICLES.sub("", lower).strip()
    clean = re.sub(r"[^a-z0-9_áéíóúñü ]+", "", clean)
    clean = re.sub(r"\s+", "_", clean).strip("_")
    if domain:
        return f"{domain}.{clean}"
    return clean


# ─── API pública ─────────────────────────────────────────────────────────────

def ha_status() -> str:
    if not ha_available():
        return _not_configured()
    try:
        info = _ha_request("GET", "")
        version = info.get("version", "?")
        return f"Home Assistant {version} — conectado en {_HA_URL}"
    except Exception as e:
        return f"Home Assistant configurado pero no responde: {e}"


def ha_call_service(domain: str, service: str, entity_id: str, **kwargs) -> str:
    if not ha_available():
        return _not_configured()
    try:
        body: dict = {"entity_id": entity_id}
        body.update(kwargs)
        _ha_request("POST", f"services/{domain}/{service}", body)
        action = {"turn_on": "encendido", "turn_off": "apagado", "toggle": "alternado",
                  "start": "iniciado", "stop": "detenido", "return_to_base": "volviendo a base"
                  }.get(service, service)
        return f"{entity_id} — {action}."
    except urllib.error.HTTPError as e:
        return f"Error HA {e.code}: {e.reason} — ¿existe la entidad '{entity_id}'?"
    except Exception as e:
        return f"Error HA: {e}"


def ha_get_state(entity_id: str) -> str:
    if not ha_available():
        return _not_configured()
    try:
        s = _ha_request("GET", f"states/{entity_id}")
        state  = s.get("state", "?")
        attrs  = s.get("attributes", {})
        name   = attrs.get("friendly_name", entity_id)
        detail = ""
        if "brightness" in attrs:
            detail = f" (brillo: {round(attrs['brightness'] / 255 * 100)}%)"
        elif "current_temperature" in attrs:
            detail = f" ({attrs['current_temperature']}°)"
        elif "battery_level" in attrs:
            detail = f" (batería: {attrs['battery_level']}%)"
        return f"{name}: {state}{detail}"
    except urllib.error.HTTPError:
        return f"Entidad '{entity_id}' no encontrada en Home Assistant."
    except Exception as e:
        return f"Error obteniendo estado: {e}"


def ha_list_entities(domain: str = "") -> str:
    if not ha_available():
        return _not_configured()
    try:
        states = _ha_request("GET", "states")
        if domain:
            states = [s for s in states if s["entity_id"].startswith(f"{domain}.")]
        if not states:
            return f"No hay entidades{' del dominio ' + domain if domain else ''}."
        lines = []
        for s in sorted(states, key=lambda x: x["entity_id"])[:30]:
            attrs = s.get("attributes", {})
            name  = attrs.get("friendly_name", s["entity_id"])
            lines.append(f"  {s['entity_id']:<40} {s['state']:<10} {name}")
        if len(states) > 30:
            lines.append(f"  … y {len(states) - 30} entidades más")
        return "\n".join(lines)
    except Exception as e:
        return f"Error listando entidades: {e}"


# ─── Skills de alto nivel ─────────────────────────────────────────────────────

def skill_ha_turn_on(texto: str) -> str:
    entity = _resolve_entity(texto)
    if not entity:
        return "¿Qué dispositivo querés encender?"
    domain = entity.split(".")[0] if "." in entity else "homeassistant"
    return ha_call_service(domain, "turn_on", entity)


def skill_ha_turn_off(texto: str) -> str:
    entity = _resolve_entity(texto)
    if not entity:
        return "¿Qué dispositivo querés apagar?"
    domain = entity.split(".")[0] if "." in entity else "homeassistant"
    return ha_call_service(domain, "turn_off", entity)


def skill_ha_lights_on(room: str = "") -> str:
    if room:
        entity = _resolve_entity(room, "light")
    else:
        entity = "all"
    return ha_call_service("light", "turn_on", entity)


def skill_ha_lights_off(room: str = "") -> str:
    if room:
        entity = _resolve_entity(room, "light")
    else:
        entity = "all"
    return ha_call_service("light", "turn_off", entity)


def skill_ha_lights_dim(texto: str) -> str:
    """Atenúa las luces: 'luces al 30' o 'luces del living al 50%'."""
    m = re.search(r"(\d+)\s*%?", texto)
    pct = int(m.group(1)) if m else 50
    brightness = round(pct / 100 * 255)
    room_match = re.search(r"(?:del?|de la)\s+(.+?)(?:\s+al|\s+a\s|\s+\d|$)", texto, re.I)
    room = room_match.group(1).strip() if room_match else ""
    entity = _resolve_entity(room, "light") if room else "all"
    return ha_call_service("light", "turn_on", entity, brightness=brightness)


def skill_ha_scene(scene_name: str) -> str:
    entity = _resolve_entity(scene_name, "scene")
    return ha_call_service("scene", "turn_on", entity)


def skill_ha_vacuum_start(_=None) -> str:
    entity = _aliases.get("aspiradora", "vacuum.robot")
    return ha_call_service("vacuum", "start", entity)


def skill_ha_vacuum_stop(_=None) -> str:
    entity = _aliases.get("aspiradora", "vacuum.robot")
    return ha_call_service("vacuum", "stop", entity)


def skill_ha_vacuum_return(_=None) -> str:
    entity = _aliases.get("aspiradora", "vacuum.robot")
    return ha_call_service("vacuum", "return_to_base", entity)


def skill_ha_state(texto: str) -> str:
    entity = _resolve_entity(texto)
    if not entity:
        return "¿De qué dispositivo querés saber el estado?"
    return ha_get_state(entity)


def skill_ha_alias(texto: str) -> str:
    """
    Define un alias: 'llama aspiradora a vacuum.robot_aspiradora'
    Formato: llama <alias> a <entity_id>
    """
    m = re.match(r"llama\s+(.+?)\s+a\s+(.+)", texto, re.I)
    if not m:
        return "Uso: 'llama aspiradora a vacuum.mi_robot'"
    alias, entity_id = m.group(1).strip().lower(), m.group(2).strip()
    _aliases[alias] = entity_id
    _ALIASES_PATH.parent.mkdir(parents=True, exist_ok=True)
    _ALIASES_PATH.write_text(
        json.dumps(_aliases, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return f"Alias guardado: '{alias}' → {entity_id}"
