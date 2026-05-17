"""
auth_google_calendar.py
───────────────────────
Hace el flow OAuth de Google Calendar UNA SOLA VEZ y guarda el token.
Después nova_google.py lo usa directamente, sin n8n.

Uso:
    python3 scripts/auth_google_calendar.py
"""

import base64, hashlib, sqlite3, json, os
from pathlib import Path
from Crypto.Cipher import AES

# ── Extraer credenciales de n8n ────────────────────────────────────────────────
def _decrypt(cred_id: str) -> dict:
    key = "UAgNQseq31xeoTzyFVfJK0lrVOdsRfji"
    db  = sqlite3.connect(str(Path.home() / ".n8n" / "database.sqlite"))
    row = db.execute("SELECT data FROM credentials_entity WHERE id=?", (cred_id,)).fetchone()
    db.close()
    enc = base64.b64decode(row[0])
    salt, cdata = enc[8:16], enc[16:]
    kb, d, di = key.encode(), b"", b""
    while len(d) < 48:
        di = hashlib.md5(di + kb + salt).digest(); d += di
    dec = AES.new(d[:32], AES.MODE_CBC, d[32:48]).decrypt(cdata)
    return json.loads(dec[:-dec[-1]])

data = _decrypt("O1QaQ4FDtuAEdj2J")  # Google Calendar credential

client_id     = data["clientId"]
client_secret = data["clientSecret"]
scopes        = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
]

# ── OAuth flow ─────────────────────────────────────────────────────────────────
from google_auth_oauthlib.flow import InstalledAppFlow

client_config = {
    "installed": {
        "client_id":     client_id,
        "client_secret": client_secret,
        "auth_uri":      "https://accounts.google.com/o/oauth2/auth",
        "token_uri":     "https://oauth2.googleapis.com/token",
        "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"],
    }
}

flow = InstalledAppFlow.from_client_config(client_config, scopes)
creds = flow.run_local_server(port=8085, prompt="consent", open_browser=True)

# ── Guardar token ──────────────────────────────────────────────────────────────
token_path = Path(__file__).parent.parent / "config" / "calendar_token.json"
token_path.parent.mkdir(exist_ok=True)

token_data = {
    "token":         creds.token,
    "refresh_token": creds.refresh_token,
    "client_id":     client_id,
    "client_secret": client_secret,
    "token_uri":     "https://oauth2.googleapis.com/token",
    "scopes":        scopes,
}
token_path.write_text(json.dumps(token_data, indent=2))
print(f"\n✅ Token guardado en {token_path}")
print("Ahora Nova puede usar Google Calendar directamente.")
