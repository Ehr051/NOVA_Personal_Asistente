"""
nova_n8n.py
─────────────
Skills de NOVA que se conectan con n8n via HTTP webhooks.

Workflows disponibles:
  • consultar_gastos(periodo)          → resume gastos desde Google Sheets
  • consultar_calendario(fecha)        → lista eventos de Google Calendar
  • crear_evento(titulo, fecha, hora)  → crea evento en Google Calendar
  • crear_archivo(nombre, contenido)   → crea archivo en Google Drive / local
  • clasificar_email_manual(texto)     → clasifica un email manualmente

Configuración (.env):
  N8N_BASE_URL=http://localhost:5678
  N8N_WEBHOOK_SECRET=mi_secreto_opcional   (si usás auth en los webhooks)
"""

from __future__ import annotations

import os
import json
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime

# Cargar variables de entorno
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# ─── Config ───────────────────────────────────────────────────────────────────

_BASE   = os.getenv("N8N_BASE_URL", "http://localhost:5678")
_SECRET = os.getenv("N8N_WEBHOOK_SECRET", "")

_ENDPOINTS = {
    "gastos":           f"{_BASE}/webhook/nova/gastos",           # GET  — activo
    "calendario":       f"{_BASE}/webhook/nova/calendario",       # POST — activo
    "crear_archivo":    f"{_BASE}/webhook/nova/drive",            # POST — usa drive unificado
    "clasificar_email": f"{_BASE}/webhook/nova/clasificar-email", # POST — inactivo (legacy)
    "telegram_send":    f"{_BASE}/webhook/nova/telegram-send",    # POST — workflow nova_telegram_send.json
    "push_notify":      f"{_BASE}/webhook/nova/push",             # POST — no implementado aún
    # ── Email ──────────────────────────────────────────────────
    "emails_query":     f"{_BASE}/webhook/nova/emails",           # GET  — activo
    "emails_buscar":    f"{_BASE}/webhook/nova/emails/buscar",    # POST — activo
    "email_accion":     f"{_BASE}/webhook/nova/email/accion",     # POST — activo
    # ── Google Drive (unified endpoint) ───────────────────────
    "drive":            f"{_BASE}/webhook/nova/drive",            # POST — activo
}

_TIMEOUT = 15  # segundos


# ─── HTTP helpers ─────────────────────────────────────────────────────────────

def _headers() -> dict:
    h = {"Content-Type": "application/json", "Accept": "application/json"}
    if _SECRET:
        h["X-Nova-Secret"] = _SECRET
    return h


def _get(url: str, params: dict | None = None) -> dict:
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=_headers(), method="GET")
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            raw = resp.read().decode().strip()
            if not raw:
                return {"error": "n8n devolvió respuesta vacía (¿workflow activo y publicado?)"}
            return json.loads(raw)
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.reason}"}
    except Exception as e:
        return {"error": str(e)}


def _post(url: str, body: dict) -> dict:
    data = json.dumps(body).encode()
    req  = urllib.request.Request(url, data=data, headers=_headers(), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            raw = resp.read().decode().strip()
            if not raw:
                return {"error": "n8n devolvió respuesta vacía (¿workflow activo y publicado?)"}
            return json.loads(raw)
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.reason}"}
    except Exception as e:
        return {"error": str(e)}


# ─── Skills ───────────────────────────────────────────────────────────────────

def consultar_gastos(periodo: str = "semana") -> str:
    """
    Consulta el resumen de gastos desde Google Sheets via n8n.
    periodo: 'hoy' | 'semana' | 'mes'
    """
    resp = _get(_ENDPOINTS["gastos"], {"periodo": periodo})
    if "error" in resp:
        return f"No pude conectarme al sistema de gastos, Señor. {resp['error']}"

    total    = resp.get("total", 0)
    moneda   = resp.get("moneda", "ARS")
    items    = resp.get("items", [])
    periodo_label = {"hoy": "hoy", "semana": "esta semana", "mes": "este mes"}.get(periodo, periodo)

    if not items:
        return f"No registré gastos {periodo_label}, Señor."

    resumen = f"Gastos {periodo_label}: {moneda} {total:,.2f}."
    if items:
        top = items[:3]
        detalle = ", ".join(f"{i['descripcion']} {moneda} {i['monto']:,.0f}" for i in top)
        resumen += f" Principales: {detalle}."
    return resumen


def consultar_calendario(fecha: str = "hoy") -> str:
    """
    Lista eventos de Google Calendar para una fecha dada.
    fecha: 'hoy' | 'mañana' | 'semana' | 'YYYY-MM-DD'
    """
    resp = _post(_ENDPOINTS["calendario"], {"accion": "consultar", "fecha": fecha})
    if "error" in resp:
        return f"No pude acceder al calendario, Señor. {resp['error']}"

    eventos = resp.get("eventos", [])
    fecha_label = {"hoy": "hoy", "mañana": "mañana", "semana": "esta semana"}.get(fecha, fecha)

    if not eventos:
        return f"No tenés eventos agendados {fecha_label}, Señor."

    if len(eventos) == 1:
        e = eventos[0]
        return f"Tenés un evento {fecha_label}: {e['titulo']} a las {e['hora']}, Señor."

    resumen = f"Tenés {len(eventos)} eventos {fecha_label}, Señor: "
    resumen += ". ".join(f"{e['titulo']} a las {e['hora']}" for e in eventos[:4])
    if len(eventos) > 4:
        resumen += f" y {len(eventos) - 4} más."
    return resumen + "."


def crear_evento(titulo: str, fecha: str, hora: str, descripcion: str = "") -> str:
    """
    Crea un evento en Google Calendar via n8n.
    fecha: 'hoy' | 'mañana' | 'YYYY-MM-DD'
    hora:  'HH:MM'
    """
    body = {
        "accion":      "crear",
        "titulo":      titulo,
        "fecha":       fecha,
        "hora":        hora,
        "descripcion": descripcion,
    }
    resp = _post(_ENDPOINTS["calendario"], body)
    if "error" in resp:
        return f"No pude crear el evento, Señor. {resp['error']}"

    link = resp.get("link", "")
    return f"Evento '{titulo}' agendado para el {fecha} a las {hora}, Señor."


def crear_archivo(nombre: str, contenido: str, destino: str = "drive") -> str:
    """
    Crea un archivo de texto en Google Drive o local via n8n.
    destino: 'drive' | 'local'
    """
    body = {
        "nombre":    nombre,
        "contenido": contenido,
        "destino":   destino,
    }
    resp = _post(_ENDPOINTS["crear_archivo"], body)
    if "error" in resp:
        return f"No pude crear el archivo, Señor. {resp['error']}"

    ruta = resp.get("ruta", nombre)
    return f"Archivo '{nombre}' creado en {destino}, Señor."


def clasificar_email_manual(texto: str) -> str:
    """
    Envía un texto de email a n8n para clasificarlo manualmente.
    Util para testear el clasificador sin esperar un email real.
    """
    resp = _post(_ENDPOINTS["clasificar_email"], {"texto": texto})
    if "error" in resp:
        return f"No pude clasificar el email, Señor. {resp['error']}"

    categoria = resp.get("categoria", "desconocida")
    accion    = resp.get("accion", "ninguna")
    return f"Email clasificado como '{categoria}'. Acción tomada: {accion}, Señor."


def enviar_telegram(mensaje: str, chat_id: str | None = None) -> str:
    """Envía un mensaje a Telegram via n8n webhook o Telegram API directa."""
    body = {"mensaje": mensaje}
    if chat_id:
        body["chat_id"] = chat_id
    resp = _post(_ENDPOINTS["telegram_send"], body)
    if "error" not in resp:
        return "Mensaje enviado a Telegram, Señor."

    # Fallback: Telegram Bot API directa
    tg_token  = os.getenv("TELEGRAM_BOT_TOKEN", "")
    tg_chat   = chat_id or os.getenv("TELEGRAM_CHAT_ID", "")
    if tg_token and tg_chat:
        try:
            data = json.dumps({"chat_id": tg_chat, "text": mensaje, "parse_mode": "Markdown"}).encode()
            req  = urllib.request.Request(
                f"https://api.telegram.org/bot{tg_token}/sendMessage",
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as r:
                if r.status == 200:
                    return "Mensaje enviado a Telegram, Señor."
        except Exception as e:
            return f"No pude enviar a Telegram, Señor. {e}"
    return f"No pude enviar el mensaje a Telegram, Señor. {resp.get('error','')}"


def enviar_push(titulo: str, mensaje: str) -> str:
    """Envía una notificación push al celular via n8n."""
    body = {"titulo": titulo, "mensaje": mensaje}
    resp = _post(_ENDPOINTS["push_notify"], body)
    if "error" in resp:
        return f"No pude enviar la notificación push, Señor. {resp['error']}"
    return "Notificación push enviada al celular, Señor."


# ─── Email ────────────────────────────────────────────────────────────────────

def consultar_emails(categoria: str = "", urgentes: bool = False) -> str:
    """
    Consulta los emails clasificados desde Google Sheets.
    categoria: 'banco' | 'trabajo' | 'factura/gasto' | 'cita' | 'alerta' | '' (todos)
    """
    resp = _get(_ENDPOINTS["emails_query"])
    if "error" in resp:
        return f"No pude acceder a los emails, Señor. {resp['error']}"

    emails = resp.get("emails", [])
    resumen = resp.get("resumen", "")
    cantidad = resp.get("cantidad", 0)
    urgentes_n = resp.get("urgentes", 0)

    if not emails:
        return "No hay emails registrados aún. El monitor clasifica cada 10 minutos, Señor."

    if urgentes and urgentes_n:
        emails = [e for e in emails if e.get("urgente") == "SI"]
        if not emails:
            return "No hay emails urgentes, Señor."

    if categoria:
        emails = [e for e in emails if categoria.lower() in e.get("categoria", "").lower()]
        if not emails:
            return f"No hay emails de categoría '{categoria}', Señor."

    # Resumen oral
    partes = [resumen] if resumen else []
    for e in emails[:5]:
        urg = "🚨 " if e.get("urgente") == "SI" else ""
        partes.append(f"{urg}De {e.get('de','?')}: {e.get('asunto','?')} ({e.get('categoria','?')})")

    if len(emails) > 5:
        partes.append(f"...y {len(emails)-5} más.")

    return "\n".join(partes)


def buscar_email(query: str) -> str:
    """
    Busca emails en Gmail (leídos y no leídos) por remitente, asunto o texto.
    query: cualquier búsqueda Gmail válida, ej. 'from:banco', 'factura', 'subject:reunion'
    """
    resp = _post(_ENDPOINTS["emails_buscar"], {"query": query})
    if "error" in resp:
        return f"No pude buscar emails, Señor. {resp['error']}"

    emails = resp.get("emails", [])
    resumen = resp.get("resumen", "")
    if not emails:
        return resumen or f"No encontré emails para '{query}', Señor."

    partes = [resumen]
    for e in emails[:5]:
        leido_str = "✓" if e.get("leido") == "SI" else "●"
        partes.append(f"{leido_str} De {e.get('de','?')}: {e.get('asunto','?')} ({e.get('fecha','')})")
    if len(emails) > 5:
        partes.append(f"...y {len(emails)-5} más.")
    return "\n".join(partes)


def accion_email(email_id: str, accion: str,
                 asunto: str = "", de: str = "", resumen_email: str = "",
                 fecha_evento: str = "", hora_evento: str = "09:00",
                 monto: float = 0, descripcion: str = "") -> str:
    """
    Ejecuta una acción sobre un email.
    accion: 'archivar' | 'eliminar' | 'importante' | 'agenda' | 'gastos'
    """
    body = {
        "accion":        accion,
        "email_id":      email_id,
        "asunto":        asunto,
        "de":            de,
        "resumen":       resumen_email,
        "fecha_evento":  fecha_evento or datetime.now().strftime("%Y-%m-%d"),
        "hora_evento":   hora_evento,
        "monto":         monto,
        "descripcion":   descripcion or asunto,
    }
    resp = _post(_ENDPOINTS["email_accion"], body)
    if "error" in resp:
        return f"No pude ejecutar la acción, Señor. {resp['error']}"

    labels = {
        "archivar":    "archivado",
        "eliminar":    "eliminado",
        "importante":  "marcado como importante",
        "agenda":      "agregado al calendario",
        "gastos":      "registrado en gastos",
    }
    msg = resp.get("mensaje", labels.get(accion, accion))
    return f"Email {msg}, Señor."


# ─── Google Drive ─────────────────────────────────────────────────────────────

def drive_buscar(query: str) -> str:
    """Busca archivos en Google Drive por nombre o contenido."""
    resp = _post(_ENDPOINTS["drive"], {"accion": "buscar", "q": query})
    if "error" in resp:
        return f"No pude buscar en Drive, Señor. {resp['error']}"
    return resp.get("resumen", "Sin resultados.")


def drive_buscar_detalle(query: str) -> dict:
    """Busca archivos y retorna lista con IDs para acciones posteriores."""
    resp = _post(_ENDPOINTS["drive"], {"accion": "buscar", "q": query})
    if "error" in resp:
        return {"archivos": [], "resumen": resp["error"]}
    return resp


def drive_leer(file_id: str) -> str:
    """Lee el contenido de un archivo de Drive por ID."""
    resp = _post(_ENDPOINTS["drive"], {"accion": "leer", "id": file_id})
    if "error" in resp:
        return f"No pude leer el archivo, Señor. {resp['error']}"
    contenido = resp.get("contenido", "")
    truncado = resp.get("truncado", False)
    suffix = "\n[...contenido truncado a 2000 caracteres]" if truncado else ""
    return contenido + suffix if contenido else "El archivo está vacío o no es legible."


def drive_crear(nombre: str, contenido: str = "") -> str:
    """Crea un documento en Google Drive."""
    resp = _post(_ENDPOINTS["drive"], {"accion": "crear", "nombre": nombre, "contenido": contenido})
    if "error" in resp:
        return f"No pude crear el documento, Señor. {resp['error']}"
    url = resp.get("url", "")
    return f"Documento '{nombre}' creado en Drive{', Señor. Url: ' + url if url else ', Señor.'}"


def drive_listar(carpeta_id: str = "root") -> str:
    """Lista archivos en una carpeta de Drive (root = Mi Drive)."""
    resp = _post(_ENDPOINTS["drive"], {"accion": "listar"})
    if "error" in resp:
        return f"No pude listar Drive, Señor. {resp['error']}"
    return resp.get("resumen", "Carpeta vacía.")


# ─── Estado de conexión n8n ───────────────────────────────────────────────────

def estado_n8n() -> str:
    """Verifica si n8n está corriendo y los webhooks responden."""
    try:
        req = urllib.request.Request(
            f"{_BASE}/healthz",
            headers=_headers(),
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=5):
            return f"n8n operativo en {_BASE}, Señor."
    except Exception as e:
        return f"No puedo conectarme a n8n en {_BASE}. ¿Está corriendo?, Señor."
