"""
nova_user_profile.py
────────────────────
Perfil de usuario de Nova.

Estructura:
  ~/.nova/users/<id>/profile.json
  ~/.nova/users/<id>/voice.npy   (opcional — speaker embedding)

Ejemplo de profile.json:
  {
    "id": "default",
    "address": "Señor",
    "name": "",
    "language": "es",
    "notes": "",
    "voice_enrolled": false,
    "created_at": "2026-05-09"
  }
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional

USERS_DIR = Path.home() / ".nova" / "users"


@dataclass
class UserProfile:
    id: str = "default"
    address: str = "Señor"      # cómo Nova llama al usuario
    name: str = ""              # nombre personal (opcional)
    language: str = "es"
    notes: str = ""             # contexto libre que Nova debe recordar
    voice_enrolled: bool = False
    created_at: str = field(default_factory=lambda: str(date.today()))

    # ── Propiedades ───────────────────────────────────────────────────────────

    @property
    def display_address(self) -> str:
        return self.address or "Señor"

    @property
    def voice_path(self) -> Path:
        return USERS_DIR / self.id / "voice.npy"

    def system_prompt_fragment(self) -> str:
        """Fragmento para inyectar en el system prompt del router."""
        addr = self.display_address
        name_part = f" Su nombre es {self.name}." if self.name else ""
        notes_part = f" Contexto del usuario: {self.notes}" if self.notes else ""
        return f"Llamas al usuario '{addr}'.{name_part}{notes_part}"

    # ── Persistencia ─────────────────────────────────────────────────────────

    def save(self) -> None:
        path = USERS_DIR / self.id / "profile.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(asdict(self), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, user_id: str = "default") -> Optional["UserProfile"]:
        path = USERS_DIR / user_id / "profile.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            valid = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
            return cls(**valid)
        except Exception:
            return None

    @classmethod
    def load_or_default(cls, user_id: str = "default") -> "UserProfile":
        return cls.load(user_id) or cls(id=user_id)

    @classmethod
    def exists(cls, user_id: str = "default") -> bool:
        return (USERS_DIR / user_id / "profile.json").exists()

    @classmethod
    def list_users(cls) -> list[str]:
        if not USERS_DIR.exists():
            return []
        return [d.name for d in USERS_DIR.iterdir() if (d / "profile.json").exists()]


# ─── Active user tracking ─────────────────────────────────────────────────────

_ACTIVE_USER_FILE = Path.home() / ".nova" / "active_user"
_active_user_id: str = "default"


def _load_persisted_active_user() -> None:
    global _active_user_id
    try:
        if _ACTIVE_USER_FILE.exists():
            uid = _ACTIVE_USER_FILE.read_text(encoding="utf-8").strip()
            if uid and UserProfile.exists(uid):
                _active_user_id = uid
    except Exception:
        pass


def get_active_user_id() -> str:
    return _active_user_id


def get_active_profile() -> "UserProfile":
    return UserProfile.load_or_default(_active_user_id)


def set_active_user(user_id: str) -> "UserProfile":
    global _active_user_id
    _active_user_id = user_id
    try:
        _ACTIVE_USER_FILE.parent.mkdir(parents=True, exist_ok=True)
        _ACTIVE_USER_FILE.write_text(user_id, encoding="utf-8")
    except Exception:
        pass
    return UserProfile.load_or_default(user_id)


_load_persisted_active_user()
