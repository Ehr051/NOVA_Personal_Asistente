"""
nova_google.py
──────────────
Acceso directo a Gmail, Google Calendar y Google Drive via Python SDK.
No requiere n8n ni procesos externos. Los tokens se leen de config/google_tokens.json
y se refrescan automáticamente.

Uso:
    from nova.connectors.nova_google import gmail, calendar, drive
    emails = gmail.listar_no_leidos()
    eventos = calendar.eventos_hoy()
"""

from __future__ import annotations

import os
import json
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Any

log = logging.getLogger(__name__)

# ─── Config ───────────────────────────────────────────────────────────────────

_N8N_DB    = Path.home() / ".n8n" / "database.sqlite"
_TOKEN_URI = "https://oauth2.googleapis.com/token"

_CRED_IDS = {
    "gmail":    "K31rzLSx8cGCc8Ow",
    "calendar": "O1QaQ4FDtuAEdj2J",
    "drive":    "4DM9Stk6CD4Gt5gp",
    "sheets":   "mtcZJ0QMcGs2ZZYo",
}

# ─── Auth helper ──────────────────────────────────────────────────────────────

def _decrypt_n8n(cred_id: str) -> dict:
    """Lee y descifra una credencial de n8n en tiempo real."""
    import base64, hashlib, sqlite3 as _sq
    from Crypto.Cipher import AES

    key = "UAgNQseq31xeoTzyFVfJK0lrVOdsRfji"
    db = _sq.connect(str(_N8N_DB))
    row = db.execute("SELECT data FROM credentials_entity WHERE id=?", (cred_id,)).fetchone()
    db.close()
    if not row:
        raise RuntimeError(f"Credencial {cred_id} no encontrada en n8n")

    enc = base64.b64decode(row[0])
    salt, cipher_data = enc[8:16], enc[16:]
    key_bytes, d, d_i = key.encode(), b"", b""
    while len(d) < 48:
        d_i = hashlib.md5(d_i + key_bytes + salt).digest()
        d += d_i
    decrypted = AES.new(d[:32], AES.MODE_CBC, d[32:48]).decrypt(cipher_data)
    decrypted = decrypted[:-decrypted[-1]]
    return json.loads(decrypted)


_OVERRIDE_TOKENS = {
    # Tokens propios (no n8n) guardados por scripts/auth_google_*.py
    "calendar": Path(__file__).parents[3] / "config" / "calendar_token.json",
}


def _load_creds(service: str):
    """Devuelve google.oauth2.credentials.Credentials listo para usar."""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request

    # Preferir token propio si existe
    override = _OVERRIDE_TOKENS.get(service)
    if override and override.exists():
        d = json.loads(override.read_text())
        creds = Credentials(
            token=d.get("token"),
            refresh_token=d["refresh_token"],
            client_id=d["client_id"],
            client_secret=d["client_secret"],
            token_uri=d.get("token_uri", _TOKEN_URI),
            scopes=d.get("scopes"),
        )
        if not creds.valid:
            creds.refresh(Request())
            # Persistir el nuevo access_token
            d["token"] = creds.token
            override.write_text(json.dumps(d, indent=2))
        return creds

    # Fallback: token de n8n
    data  = _decrypt_n8n(_CRED_IDS[service])
    token = data["oauthTokenData"]
    creds = Credentials(
        token=None,
        refresh_token=token["refresh_token"],
        client_id=data["clientId"],
        client_secret=data["clientSecret"],
        token_uri=_TOKEN_URI,
    )
    creds.refresh(Request())
    return creds


def _build(service_name: str, version: str, cred_key: str):
    """Construye un client de Google API."""
    from googleapiclient.discovery import build
    return build(service_name, version, credentials=_load_creds(cred_key),
                 cache_discovery=False)


# ─── Gmail ────────────────────────────────────────────────────────────────────

class _Gmail:
    def _svc(self):
        return _build("gmail", "v1", "gmail")

    def listar_no_leidos(self, max_results: int = 20) -> list[dict]:
        """Lista emails no leídos de la bandeja de entrada."""
        svc = self._svc()
        res = svc.users().messages().list(
            userId="me", labelIds=["INBOX", "UNREAD"], maxResults=max_results
        ).execute()
        msgs = res.get("messages", [])
        return [self._get_meta(svc, m["id"]) for m in msgs]

    def buscar(self, query: str, max_results: int = 10) -> list[dict]:
        """Busca emails con cualquier query Gmail (from:, subject:, etc.)."""
        svc = self._svc()
        res = svc.users().messages().list(
            userId="me", q=query, maxResults=max_results
        ).execute()
        msgs = res.get("messages", [])
        return [self._get_meta(svc, m["id"]) for m in msgs]

    def leer(self, msg_id: str) -> dict:
        """Lee el contenido completo de un email."""
        svc = self._svc()
        return self._get_meta(svc, msg_id, full=True)

    def archivar(self, msg_id: str) -> bool:
        svc = self._svc()
        svc.users().messages().modify(
            userId="me", id=msg_id,
            body={"removeLabelIds": ["INBOX"]}
        ).execute()
        return True

    def marcar_leido(self, msg_id: str) -> bool:
        svc = self._svc()
        svc.users().messages().modify(
            userId="me", id=msg_id,
            body={"removeLabelIds": ["UNREAD"]}
        ).execute()
        return True

    def eliminar(self, msg_id: str) -> bool:
        svc = self._svc()
        svc.users().messages().trash(userId="me", id=msg_id).execute()
        return True

    def _get_meta(self, svc, msg_id: str, full: bool = False) -> dict:
        fmt = "full" if full else "metadata"
        fields = "id,labelIds,snippet,payload/headers"
        msg = svc.users().messages().get(
            userId="me", id=msg_id, format=fmt,
            metadataHeaders=["Subject", "From", "Date"]
        ).execute()
        headers = {h["name"].lower(): h["value"]
                   for h in msg.get("payload", {}).get("headers", [])}
        result = {
            "id":      msg_id,
            "asunto":  headers.get("subject", "(sin asunto)"),
            "de":      headers.get("from", ""),
            "fecha":   headers.get("date", ""),
            "snippet": msg.get("snippet", ""),
            "leido":   "UNREAD" not in msg.get("labelIds", []),
        }
        if full:
            result["body"] = _extract_body(msg.get("payload", {}))
        return result


def _extract_body(payload: dict) -> str:
    """Extrae el texto plano del payload de un email."""
    import base64
    mime = payload.get("mimeType", "")
    if mime == "text/plain":
        data = payload.get("body", {}).get("data", "")
        return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
    for part in payload.get("parts", []):
        text = _extract_body(part)
        if text:
            return text
    return ""


# ─── Calendar ─────────────────────────────────────────────────────────────────

class _Calendar:
    def _svc(self):
        return _build("calendar", "v3", "calendar")

    def eventos(self, fecha: str = "hoy", max_results: int = 10) -> list[dict]:
        """Lista eventos del día/semana/fecha específica."""
        svc = self._svc()
        now = datetime.now(timezone.utc)

        if fecha == "hoy":
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end   = start + timedelta(days=1)
        elif fecha == "mañana":
            start = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            end   = start + timedelta(days=1)
        elif fecha == "semana":
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end   = start + timedelta(days=7)
        else:
            # YYYY-MM-DD
            from datetime import date
            d = datetime.strptime(fecha, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            start = d.replace(hour=0, minute=0, second=0)
            end   = start + timedelta(days=1)

        res = svc.events().list(
            calendarId="primary",
            timeMin=start.isoformat(),
            timeMax=end.isoformat(),
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime",
        ).execute()

        events = []
        for e in res.get("items", []):
            s = e.get("start", {})
            hora = s.get("dateTime", s.get("date", ""))
            if "T" in hora:
                hora = hora[11:16]  # HH:MM
            events.append({
                "id":          e["id"],
                "titulo":      e.get("summary", "(sin título)"),
                "hora":        hora,
                "ubicacion":   e.get("location", ""),
                "descripcion": e.get("description", ""),
            })
        return events

    def crear(self, titulo: str, fecha: str, hora: str = "", descripcion: str = "",
              todo_el_dia: bool = False) -> dict:
        """Crea un evento en Google Calendar. hora="" + todo_el_dia=True → evento de día completo."""
        svc = self._svc()

        if fecha == "hoy":
            fecha = datetime.now().strftime("%Y-%m-%d")
        elif fecha == "mañana":
            fecha = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

        if todo_el_dia or not hora:
            # Evento de día completo
            end_fecha = (datetime.strptime(fecha, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
            event = {
                "summary":     titulo,
                "description": descripcion,
                "start":       {"date": fecha},
                "end":         {"date": end_fecha},
            }
        else:
            start_dt = f"{fecha}T{hora}:00"
            h, m = int(hora.split(":")[0]), int(hora.split(":")[1])
            end_h, end_m = (h, m + 30) if m < 30 else (h + 1, m - 30)
            end_dt = f"{fecha}T{str(end_h).zfill(2)}:{str(end_m).zfill(2)}:00"
            event = {
                "summary":     titulo,
                "description": descripcion,
                "start":       {"dateTime": start_dt, "timeZone": "America/Argentina/Buenos_Aires"},
                "end":         {"dateTime": end_dt,   "timeZone": "America/Argentina/Buenos_Aires"},
            }

        created = svc.events().insert(calendarId="primary", body=event).execute()
        return {"id": created["id"], "link": created.get("htmlLink", "")}

    def eliminar(self, event_id: str) -> bool:
        self._svc().events().delete(calendarId="primary", eventId=event_id).execute()
        return True


# ─── Drive ────────────────────────────────────────────────────────────────────

class _Drive:
    def _svc(self):
        return _build("drive", "v3", "drive")

    def buscar(self, query: str, max_results: int = 10) -> list[dict]:
        """Busca archivos en Drive por nombre."""
        svc = self._svc()
        res = svc.files().list(
            q=f"name contains '{query}' and trashed=false",
            pageSize=max_results,
            fields="files(id,name,mimeType,modifiedTime,webViewLink)"
        ).execute()
        return res.get("files", [])

    def leer(self, file_id: str) -> str:
        """Lee el contenido de un archivo de texto/doc."""
        svc = self._svc()
        # Para Google Docs, exportar como texto plano
        try:
            content = svc.files().export(fileId=file_id, mimeType="text/plain").execute()
            return content.decode("utf-8") if isinstance(content, bytes) else str(content)
        except Exception:
            # Para archivos regulares, descargar
            from googleapiclient.http import MediaIoBaseDownload
            import io
            fh = io.BytesIO()
            req = svc.files().get_media(fileId=file_id)
            dl = MediaIoBaseDownload(fh, req)
            done = False
            while not done:
                _, done = dl.next_chunk()
            return fh.getvalue().decode("utf-8", errors="replace")

    def crear(self, nombre: str, contenido: str = "", carpeta_id: str = "") -> dict:
        """Crea un documento de texto en Drive."""
        svc = self._svc()
        meta: dict[str, Any] = {"name": nombre, "mimeType": "application/vnd.google-apps.document"}
        if carpeta_id:
            meta["parents"] = [carpeta_id]

        from googleapiclient.http import MediaInMemoryUpload
        media = MediaInMemoryUpload(contenido.encode("utf-8"), mimetype="text/plain")
        f = svc.files().create(body=meta, media_body=media, fields="id,webViewLink").execute()
        return {"id": f["id"], "url": f.get("webViewLink", "")}

    def listar(self, max_results: int = 20) -> list[dict]:
        """Lista archivos recientes en Drive."""
        svc = self._svc()
        res = svc.files().list(
            pageSize=max_results,
            orderBy="modifiedTime desc",
            q="trashed=false",
            fields="files(id,name,mimeType,modifiedTime)"
        ).execute()
        return res.get("files", [])


# ─── Singletons ───────────────────────────────────────────────────────────────

gmail    = _Gmail()
calendar = _Calendar()
drive    = _Drive()
