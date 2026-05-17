"""
nova_router.py
────────────────
Motor central de NOVA — Multi-proveedor con scoring inteligente.

Proveedores soportados:
  • Ollama     — modelos locales (rápido, privado, gratuito)
  • OpenClaw   — gateway local (OpenAI-compatible HTTP API)
  • Groq       — 100% gratis, ultra rápido
  • OpenRouter — acceso a 100+ modelos
  • Anthropic  — Claude Haiku / Sonnet / Opus (requiere ANTHROPIC_API_KEY)

Características:
  • Scoring de modelos basado en éxito/fallo/latencia
  • Estadísticas persistentes en model_stats.json
  • Detección automática de modelos Ollama locales
  • Fallback inteligente entre proveedores
  • Priorización por ROUTER_PROVIDER_ORDER

Configuración (.env):
  OLLAMA_BASE_URL=http://127.0.0.1:11434/v1
  OPENCLAW_BASE_URL=http://127.0.0.1:18789/v1
  GROQ_API_KEY=...
  OPENROUTER_API_KEY=...
  ANTHROPIC_API_KEY=...
  ROUTER_PROVIDER_ORDER=ollama,openclaw,groq,openrouter,anthropic
"""

from __future__ import annotations

import logging
import os
import json
import time
import urllib.error
import urllib.request
import base64
from dataclasses import dataclass, field
from typing import ClassVar
from collections import defaultdict

from dotenv import load_dotenv
from openai import OpenAI

# Timeout máximo por proveedor.  Si un proveedor no responde en este tiempo
# se salta al siguiente.  Ajustable con NOVA_API_TIMEOUT en .env.
# 10s es suficiente para respuestas normales; redes lentas pueden usar 15-20.
_API_TIMEOUT = int(os.getenv("NOVA_API_TIMEOUT", "10"))

logger = logging.getLogger(__name__)

try:
    import anthropic as _anthropic_sdk
    _HAS_ANTHROPIC = True
except ImportError:
    _HAS_ANTHROPIC = False

load_dotenv()

# ─── RATE LIMIT HELPERS ──────────────────────────────────────────────────────

_RATE_LIMIT_MAX_WAIT = 30  # nunca esperar más de 30s por un solo proveedor

def _parse_retry_after(exc: Exception) -> float | None:
    """
    Extrae el tiempo de espera de un error 429.
    Soporta:
      - openai.RateLimitError con response.headers["retry-after"]
      - HTTPStatusError / RateLimitError de otros SDKs
      - Errores cuyo str() contiene 'retry after N' o 'please try again in Xs'
    Retorna segundos (float) o None si no es un 429 / no tiene retry-after.
    """
    import re as _re
    exc_str = str(exc).lower()

    # Detectar que es realmente un rate-limit
    is_rate_limit = (
        "429" in exc_str
        or "rate limit" in exc_str
        or "too many requests" in exc_str
        or "rateLimitError" in type(exc).__name__
    )
    if not is_rate_limit:
        return None

    # 1. Intentar leer el header retry-after del SDK de openai
    try:
        headers = exc.response.headers  # type: ignore[attr-defined]
        val = headers.get("retry-after") or headers.get("x-ratelimit-reset-requests")
        if val:
            return float(val)
    except Exception:
        pass

    # 2. Parsear "please try again in 1.5s" / "retry after 2s" en el mensaje
    for pattern in (
        r"try again in\s+([\d.]+)\s*s",
        r"retry after\s+([\d.]+)\s*s",
        r"retry_after[\":\s]+([\d.]+)",
        r"reset in\s+([\d.]+)\s*s",
    ):
        m = _re.search(pattern, exc_str)
        if m:
            return float(m.group(1))

    # 3. Valor por defecto conservador para 429 sin tiempo explícito
    return 5.0


# ─── CONTEXT WINDOW MANAGEMENT ───────────────────────────────────────────────

# Límite de contexto en caracteres por provider (~4 chars/token como estimación)
# Conservadores: reservamos ~30% para la respuesta
_PROVIDER_CTX_CHARS: dict[str, int] = {
    "Ollama":      24_000,   # depende del modelo local; 6k tokens es seguro
    "Groq":        24_000,   # 8k tokens en modelos gratuitos
    "Cerebras":    24_000,   # 8k tokens tier gratuito
    "Mistral":     96_000,   # 32k tokens
    "Codestral":   96_000,
    "DeepSeek":    96_000,
    "OpenRouter": 384_000,   # modelos 128k+
    "OpenClaw":    24_000,
    "Anthropic":  192_000,   # 200k tokens
    "_default":    24_000,
}

_MAX_SINGLE_MSG_CHARS = 6_000   # ningún mensaje individual supera esto


def _trim_messages(
    messages: list[dict],
    provider: str = "_default",
    reserve_for_response: int = 2_000,
) -> list[dict]:
    """
    Recorta el historial para que quepa en el contexto del provider.

    Estrategia:
      1. Preserva siempre el mensaje system (si existe).
      2. Trunca mensajes individuales que superen _MAX_SINGLE_MSG_CHARS.
      3. Elimina los turnos más antiguos (user+assistant) hasta entrar en límite.
      4. El mensaje de usuario más reciente nunca se elimina.
    """
    limit = _PROVIDER_CTX_CHARS.get(provider, _PROVIDER_CTX_CHARS["_default"])
    budget = limit - reserve_for_response

    # Separar system del resto
    system_msgs = [m for m in messages if m.get("role") == "system"]
    other_msgs  = [m for m in messages if m.get("role") != "system"]

    # Truncar mensajes individuales muy largos
    def _truncate(m: dict) -> dict:
        content = str(m.get("content", ""))
        if len(content) > _MAX_SINGLE_MSG_CHARS:
            m = dict(m)
            m["content"] = content[:_MAX_SINGLE_MSG_CHARS] + " … [truncado]"
        return m

    system_msgs = [_truncate(m) for m in system_msgs]
    other_msgs  = [_truncate(m) for m in other_msgs]

    # Calcular cuántos chars ocupan los mensajes system
    sys_chars = sum(len(str(m.get("content", ""))) for m in system_msgs)
    remaining = budget - sys_chars

    # Mantener siempre el último mensaje (la pregunta actual del usuario)
    if not other_msgs:
        return system_msgs

    last_msg = other_msgs[-1]
    candidates = other_msgs[:-1]

    # Agregar mensajes desde el más reciente hacia atrás hasta llenar el budget
    kept: list[dict] = []
    used = len(str(last_msg.get("content", "")))
    for m in reversed(candidates):
        chars = len(str(m.get("content", "")))
        if used + chars > remaining:
            break
        kept.insert(0, m)
        used += chars

    return system_msgs + kept + [last_msg]


# ─── CONFIG ──────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT_TEMPLATE = (
    "Eres Nova, asistente IA personal de voz. {address_fragment} "
    "Respondes en español. Sé conciso para voz por defecto (2-3 oraciones), "
    "pero si el usuario te pide un reporte, briefing o detalles, puedes explayarte más. "
    "IMPORTANTE — Reglas de comportamiento:\n"
    "1. NUNCA afirmes que ejecutaste una acción a menos que el historial muestre el resultado real "
    "de esa acción. Si el historial no tiene el resultado, di exactamente: "
    "'Esa acción no se ejecutó. Por favor repita el comando.' "
    "NUNCA inventes que abriste una app, activaste algo, o hiciste algo. "
    "Las acciones del sistema las ejecuta el código, no tú. Solo las ves en el historial.\n"
    "2. Si el historial muestra resultados de una acción (hora, clima, cámara, etc.), "
    "esos son reales. Puedes comentarlos naturalmente.\n"
    "3. Respondes en texto plano. Sin asteriscos, sin guiones de lista, sin markdown. "
    "Solo oraciones naturales separadas por punto o coma.\n"
    "4. NUNCA inventes datos de Google Calendar, Gmail, Google Drive ni gastos. "
    "Si no tienes esos datos en el historial, di: 'No pude conectarme al servicio.'\n"
    "5. Obsidian es la memoria interna. No es el calendario ni el Drive del usuario.\n"
    "6. Si no entendés la orden, hacé UNA sola pregunta corta y específica.\n"
    "7. NUNCA inventes datos personales: nombres, fechas, direcciones. "
    "Si no están en memoria, di: 'No encontré esa información en mi memoria.'\n"
    "8. Cuando el usuario te reporta un problema técnico (algo no funciona, se repite, etc.), "
    "NUNCA actives ni simules activar una función. Solo pregunta qué necesita exactamente.\n"
    "9. Eres un asistente integrado en el sistema operativo. TIENES capacidades reales e integradas "
    "para ejecutar comandos, leer archivos, usar git, controlar domótica, interactuar con el navegador "
    "y abrir aplicaciones. Si el usuario te pide una tarea que requiere estas habilidades, asume SIEMPRE "
    "que puedes hacerla y responde afirmativamente de forma natural. El entorno interceptará y "
    "ejecutará las acciones por ti. NUNCA digas 'no tengo acceso al sistema' o 'soy un asistente de texto'.\n"
    "10. Cuando hables de cotizaciones o precios en Argentina (ej: Dólar Blue), el símbolo $ representa Pesos Argentinos. Di 'pesos' en lugar de 'dólares' para el precio. Ejemplo: '$1430' se dice 'mil cuatrocientos treinta pesos'."
)



def _build_system_prompt() -> str:
    """Construye el system prompt con el perfil del usuario activo."""
    try:
        from nova.core.nova_user_profile import get_active_profile
        profile = get_active_profile()
        fragment = profile.system_prompt_fragment()
    except Exception:
        fragment = "Llamas al usuario 'Señor'."
    return _SYSTEM_PROMPT_TEMPLATE.format(address_fragment=fragment)


# Mantener alias para compatibilidad con código que importe SYSTEM_PROMPT_DEFAULT
SYSTEM_PROMPT_DEFAULT = _build_system_prompt()

# ─── Modelos por proveedor y tier ────────────────────────────────────────────

GROQ_MODELS: dict[int, list[str]] = {
    1: [
        "llama-3.1-8b-instant",       # más rápido
        "gemma2-9b-it",               # fallback tier 1
    ],
    2: [
        "llama-3.3-70b-versatile",    # mejor calidad gratuita
        "mixtral-8x7b-32768",         # contexto largo
    ],
    3: [
        "llama-3.3-70b-versatile",    # Groq no tiene GPT-4, usa el mejor disponible
    ],
}

OPENROUTER_MODELS: dict[int, list[str]] = {
    # Tier 1 — rápidos, comandos cortos, extracción ligera
    1: [
        "nvidia/nemotron-nano-9b-v2:free",          # confiable, rápido
        "nvidia/nemotron-3-nano-30b-a3b:free",      # confiable
        "meta-llama/llama-3.1-8b-instruct:free",    # amplia disponibilidad
    ],
    # Tier 2 — balance calidad/velocidad
    2: [
        "nvidia/nemotron-3-super-120b-a12b:free",   # 120B, excelente calidad
        "nvidia/nemotron-nano-12b-v2-vl:free",      # visión + texto
        "meta-llama/llama-3.3-70b-instruct:free",   # 70B sólido
    ],
    # Tier 3 — máxima calidad, análisis, código, visión
    3: [
        "google/gemma-4-31b-it:free",               # 262K ctx, visión nativa
        "nvidia/nemotron-3-super-120b-a12b:free",   # 120B texto
        "meta-llama/llama-3.3-70b-instruct:free",   # fallback texto
    ],
}

# ─── OPENROUTER MODELOS DE VISIÓN (para vision_query) ─────────────────────────
OPENROUTER_VISION_MODELS: list[str] = [
    "google/gemma-4-31b-it:free",          # Mejor opción — 262K ctx, visión nativa
    "google/gemma-4-26b-a4b-it:free",      # Fallback visión
    "google/gemma-3-27b-it:free",          # Fallback visión alternativo
    "nvidia/nemotron-nano-12b-v2-vl:free", # Nemotron VL gratis
]

# OpenClaw usa un "agent model" (normalmente openclaw/default) y opcionalmente
# un hint de modelo backend por header x-openclaw-model.
# Si no se define hint, OpenClaw decide internamente.
OPENCLAW_ENV_PROFILES = {"auto", "eco", "balanced", "power"}
DEFAULT_OPENCLAW_AGENT_MODEL = "openclaw/default"

# ─── OLLAMA MODELS (optimizados para asistente visual/coding) ──────────────
# Modelos recomendados para: código, diseño, visión, automatización
# Con 16GB RAM puedes correr modelos hasta ~13B params cómodamente
OLLAMA_MODELS: dict[int, list[str]] = {
    1: [  # ⚡ Rápidos: saludos, comandos, control de sistema
        "llama3.2:3b",           # 2GB — muy rápido, sin thinking
        "qwen2.5:7b",            # 4.7GB — bueno para razonamiento
        "qwen3.5:latest",        # 6.6GB — fallback
    ],
    2: [  # 🎯 Balance: consultas, código, automatización
        "qwen2.5:7b",            # 4.7GB — excelente código y razonamiento
        "llama3.2:3b",           # fallback rápido
        "qwen3.5:latest",        # fallback grande
    ],
    3: [  # 🧠 Análisis complejo, visión, código difícil
        "qwen3-vl:latest",       # 6.1GB — visión + lenguaje
        "qwen2.5:7b",            # fallback texto
        "qwen3.5:latest",        # fallback grande
    ],
}

# ─── OLLAMA MODELOS DE VISIÓN (para análisis de imagen) ─────────────────────
# Requieren soporte de imágenes en el modelo
OLLAMA_VISION_MODELS: list[str] = [
    "llava:7b",                  # Rápido y probado — primero
    "qwen3-vl:latest",           # Visión + lenguaje Qwen3 — más lento
    "llava:13b",                 # Visión mejor calidad
    "bakllava:7b",               # Alternativo
    "moondream:latest",          # Ultra ligero si está disponible
]

# ─── CEREBRAS MODELS ────────────────────────────────────────────────────────
# 100% gratuito — 14.400 req/día, 1M tokens/día (igual que Groq pero más rápido)
# Registrar en: https://cloud.cerebras.ai
CEREBRAS_MODELS: dict[int, list[str]] = {
    1: ["llama3.1-8b"],               # ⚡ Ultra-rápido (~2000 tokens/seg)
    2: ["llama-3.3-70b"],             # 🎯 Balance calidad/velocidad
    3: ["llama-3.3-70b"],             # 🧠 Mejor disponible en Cerebras
}
CEREBRAS_BASE_URL = "https://api.cerebras.ai/v1"

# ─── MISTRAL MODELS ──────────────────────────────────────────────────────────
# Free tier generoso — Registrar en: https://console.mistral.ai
# Codestral (coding): key aparte en https://codestral.mistral.ai
MISTRAL_MODELS: dict[int, list[str]] = {
    1: ["mistral-small-latest"],      # ⚡ Rápido, buena calidad
    2: ["mistral-small-latest"],      # 🎯 Mismo, fine para uso general
    3: ["mistral-large-latest",       # 🧠 Máxima calidad
        "mistral-small-latest"],
}
CODESTRAL_MODELS: dict[int, list[str]] = {
    1: ["codestral-latest"],          # código tier 1
    2: ["codestral-latest"],          # código tier 2
    3: ["codestral-latest"],          # código tier 3
}
MISTRAL_BASE_URL    = "https://api.mistral.ai/v1"
CODESTRAL_BASE_URL  = "https://codestral.mistral.ai/v1"

# ─── DEEPSEEK MODELS ────────────────────────────────────────────────────────
# API compatible con OpenAI — base_url: https://api.deepseek.com/v1
# deepseek-chat: GPT-4-class, muy barato ($0.14/1M input)
# deepseek-coder: especialista en código (mismo precio)
# deepseek-reasoner: R1 con chain-of-thought (más lento, tier 3)
DEEPSEEK_MODELS: dict[int, list[str]] = {
    1: ["deepseek-v4-flash"],         # ⚡ Rápido, general — $0.07/1M tokens
    2: ["deepseek-v4-flash"],         # 🎯 Igual que tier 1 (es de muy buena calidad)
    3: ["deepseek-v4-pro",            # 🧠 Con thinking (CoT visible)
        "deepseek-v4-flash"],         # fallback sin thinking
}
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"

# ─── CLAUDE / ANTHROPIC MODELS ──────────────────────────────────────────────
CLAUDE_MODELS: dict[int, list[str]] = {
    1: ["claude-haiku-4-5-20251001"],                    # ⚡ Rápido y barato
    2: ["claude-sonnet-4-6"],                            # 🎯 Balance calidad/costo
    3: ["claude-opus-4-7", "claude-sonnet-4-6"],         # 🧠 Máxima capacidad
}

# ─── OLLAMA MODELOS DE HERRAMIENTAS/TOOL USE ───────────────────────────────
# Para llamar funciones/MCP tools (experimental en Ollama)
OLLAMA_TOOL_MODELS: list[str] = [
    "qwen3.5:latest",            # Disponible — buen tool following
    "llama3.2:3b",               # Soporte nativo de tools
    "qwen2.5:7b",                # Buen tool following
    "mistral:7b",                # Function calling
]

# Modelos disponibles detectados en Ollama (se llena dinámicamente)
OLLAMA_AVAILABLE_MODELS: dict[int, list[str]] = {1: [], 2: [], 3: []}


def _is_placeholder(key: str) -> bool:
    """Detecta si un valor de API key es un placeholder del .env.example (no configurado)."""
    return not key or "..." in key or len(key) < 20


def _csv_env(name: str, default: str = "") -> list[str]:
    raw = os.getenv(name, default).strip()
    if not raw:
        return []
    return [x.strip() for x in raw.split(",") if x.strip()]


def _safe_float(value: str, fallback: float) -> float:
    try:
        return float(value)
    except ValueError:
        return fallback


def _with_tier1_fallback(models_by_tier: dict[int, list[str]], tier: int) -> list[str]:
    models = list(models_by_tier.get(tier, []))
    if tier != 1:
        models.extend(models_by_tier.get(1, []))
    return models


# ─── ModelStatsTracker ───────────────────────────────────────────────────────

class ModelStatsTracker:
    """
    Sistema de estadísticas persistentes para modelos.
    Guarda éxitos, fallos, latencia promedio y tiempo del último fallo.

    Almacenamiento dual:
      • JSON local → model_stats.json (búsqueda rápida)
      • Obsidian vault → Cerebro/Stats/model_stats.json (gran cerebro compartido)
    """
    def __init__(self, stats_file: str = "model_stats.json", sync_to_vault: bool = True):
        self.stats_file = stats_file
        self.sync_to_vault = sync_to_vault
        self.vault_path = os.path.expanduser("~/Cerebro/Stats/model_stats.json")
        self.model_stats = defaultdict(lambda: {
            "success": 1,
            "fail": 0,
            "avg_latency": 1.0,
            "last_fail": 0
        })
        self._load_stats()

    def _load_stats(self) -> None:
        # Intentar cargar desde archivo local primero
        sources = [self.stats_file]
        # Si existe en el vault, también considerarlo
        if os.path.exists(self.vault_path):
            sources.append(self.vault_path)

        for source in sources:
            try:
                with open(source, "r") as f:
                    data = json.load(f)
                for k, v in data.items():
                    # Merge: mantener el más actualizado
                    if k not in self.model_stats or v.get("last_fail", 0) > self.model_stats[k].get("last_fail", 0):
                        self.model_stats[k] = v
            except Exception:
                continue

    def _save_stats(self) -> None:
        data = dict(self.model_stats)
        # Guardar local
        try:
            with open(self.stats_file, "w") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

        # Sincronizar al vault si está habilitado
        if self.sync_to_vault:
            try:
                os.makedirs(os.path.dirname(self.vault_path), exist_ok=True)
                with open(self.vault_path, "w") as f:
                    json.dump(data, f, indent=2, sort_keys=True)
            except Exception:
                pass

    def record_success(self, model: str, latency: float) -> None:
        s = self.model_stats[model]
        s["success"] += 1
        s["avg_latency"] = (s["avg_latency"] + latency) / 2
        self._save_stats()

    def record_fail(self, model: str) -> None:
        s = self.model_stats[model]
        s["fail"] += 1
        s["last_fail"] = time.time()
        self._save_stats()

    def score(self, model: str) -> float:
        """
        Calcula un score para el modelo basado en:
        - Tasa de éxito (60%)
        - Latencia promedio penalizada (30%)
        - Cooldown por fallos recientes (50%)
        """
        s = self.model_stats[model]
        success_rate = s["success"] / (s["success"] + s["fail"])
        latency = s["avg_latency"]
        cooldown = min(300, s["fail"] * 30)
        recent_fail = 1 if time.time() - s["last_fail"] < cooldown else 0
        return success_rate * 0.6 - latency * 0.3 - recent_fail * 0.5

    def get_stats(self) -> dict:
        return dict(self.model_stats)

# ─── Keywords para detección de complejidad ──────────────────────────────────

_HIGH_COMPLEXITY = [
    "analiza", "análisis", "explica", "explícame", "compara", "diferencia",
    "detalla", "investiga", "redacta", "código", "programa", "script",
    "debug", "implementa", "arquitectura", "matemáticas", "filosofía",
    "traduce", "escribe un", "crea un informe",
    "analyze", "explain", "compare", "code", "implement", "debug",
    "architecture", "essay", "translate", "summarize", "develop",
]

_SIMPLE_TRIGGERS = [
    "hola", "buenos días", "buenas tardes", "buenas noches",
    "cómo estás", "gracias", "adiós", "hasta luego", "chau",
    "qué hora", "qué día",
    "hello", "hi", "good morning", "how are you", "thank you", "bye",
]

# ─── ModelUsageTracker ───────────────────────────────────────────────────────

@dataclass
class ModelUsageTracker:
    session_budget_usd: float
    budget_warning_threshold: float = 0.8

    total_tokens: int = field(default=0, init=False)
    estimated_cost_usd: float = field(default=0.0, init=False)

    # Groq es gratis → costo 0. OpenRouter premium tiene costo.
    COST_PER_1K: ClassVar[dict[str, float]] = {
        # OpenClaw virtual model
        DEFAULT_OPENCLAW_AGENT_MODEL: 0.0,
        # Groq (gratis)
        "llama-3.1-8b-instant":    0.0,
        "llama-3.3-70b-versatile": 0.0,
        "gemma2-9b-it":            0.0,
        "mixtral-8x7b-32768":      0.0,
        # OpenRouter free
        "meta-llama/llama-3.1-8b-instruct:free": 0.0,
        "mistralai/mistral-7b-instruct:free":     0.0,
        # OpenRouter premium
        "openai/gpt-4o-mini":          0.00015,
        "anthropic/claude-3.5-sonnet": 0.003,
        "anthropic/claude-3.7-sonnet": 0.0035,
        "openai/gpt-4o":               0.005,
    }

    def record(self, model: str, tokens: int) -> None:
        self.total_tokens += tokens
        cost = self.COST_PER_1K.get(model, 0.0) / 1000
        self.estimated_cost_usd += tokens * cost

    def consumed_pct(self) -> float:
        if self.session_budget_usd <= 0:
            return 0.0
        return min(1.0, self.estimated_cost_usd / self.session_budget_usd) * 100

    def remaining_pct(self) -> float:
        return max(0.0, 100.0 - self.consumed_pct())

    def over_threshold(self) -> bool:
        if self.session_budget_usd <= 0:
            return False
        return (self.estimated_cost_usd / self.session_budget_usd) >= self.budget_warning_threshold

    def summary(self) -> dict:
        return {
            "total_tokens":        self.total_tokens,
            "cost_usd":            round(self.estimated_cost_usd, 6),
            "budget_usd":          self.session_budget_usd,
            "budget_consumed_pct": round(self.consumed_pct(), 1),
        }


# ─── ComplexityDetector ──────────────────────────────────────────────────────

class ComplexityDetector:
    TIER3_LEN = 300
    TIER2_LEN = 100

    @staticmethod
    def detect(prompt: str) -> int:
        lower  = prompt.lower()
        length = len(prompt)

        if length < 60 and any(kw in lower for kw in _SIMPLE_TRIGGERS):
            return 1
        if length >= ComplexityDetector.TIER3_LEN and any(kw in lower for kw in _HIGH_COMPLEXITY):
            return 3
        if length >= ComplexityDetector.TIER3_LEN:
            return 2
        if any(kw in lower for kw in _HIGH_COMPLEXITY):
            return 2
        if length >= ComplexityDetector.TIER2_LEN:
            return 2
        return 1


# ─── NovaRouter ────────────────────────────────────────────────────────────

class NovaRouter:
    """
    Router multi-proveedor con estadísticas persistentes y scoring inteligente.
    Soporta: Ollama (local), OpenClaw, Groq, OpenRouter.

    Orden configurable por env:
      ROUTER_PROVIDER_ORDER=ollama,openclaw,groq,openrouter
    """

    def __init__(self) -> None:
        self._openclaw_client:   OpenAI | None = None
        self._groq_client:       OpenAI | None = None
        self._or_client:         OpenAI | None = None
        self._ollama_client:     OpenAI | None = None
        self._deepseek_client:   OpenAI | None = None
        self._cerebras_client:   OpenAI | None = None
        self._mistral_client:    OpenAI | None = None
        self._codestral_client:  OpenAI | None = None
        self._anthropic_client:  object | None = None   # anthropic.Anthropic
        self._openclaw_ready  = False
        self._ollama_ready    = False
        self._active_provider = "ninguno"

        # ── Stats Tracker (persistente) ─────────────────────
        self.stats_tracker = ModelStatsTracker()

        # ── Ollama ────────────────────────────────────────────
        self._ollama_base = self._resolve_ollama_base()
        self._ollama_models = self._detect_ollama_models()
        if self._ollama_models:
            self._ollama_client = OpenAI(
                base_url=self._ollama_base,
                api_key="ollama",  # Ollama no requiere API key real
            )
            self._ollama_ready = True
            self._active_provider = "Ollama"
            logger.info("[Router] Ollama detectado con %d modelos", sum(len(v) for v in self._ollama_models.values()))

        # ── OpenClaw ────────────────────────────────────────
        self._openclaw_agent_model = os.getenv(
            "OPENCLAW_AGENT_MODEL", DEFAULT_OPENCLAW_AGENT_MODEL
        ).strip() or DEFAULT_OPENCLAW_AGENT_MODEL
        self._openclaw_models = self._resolve_openclaw_models()

        openclaw_base = os.getenv("OPENCLAW_BASE_URL", "").strip()
        openclaw_key  = (
            os.getenv("OPENCLAW_API_KEY", "").strip()
            or os.getenv("OPENCLAW_AUTH_TOKEN", "").strip()
            or "openclaw-local"
        )
        if openclaw_base:
            self._openclaw_client = OpenAI(base_url=openclaw_base, api_key=openclaw_key, timeout=_API_TIMEOUT)
            self._openclaw_ready = self._probe_openclaw_http(openclaw_base, openclaw_key)
            if self._openclaw_ready:
                self._append_active_provider("OpenClaw")
            else:
                logger.warning("[Router] OpenClaw detectado pero /v1 no disponible (se omite).")

        # ── Groq ─────────────────────────────────────────────
        groq_key = os.getenv("GROQ_API_KEY", "").strip()
        if groq_key and not _is_placeholder(groq_key):
            self._groq_client = OpenAI(
                base_url="https://api.groq.com/openai/v1",
                api_key=groq_key,
                timeout=_API_TIMEOUT,
            )
            self._append_active_provider("Groq")

        # ── OpenRouter ───────────────────────────────────────
        or_key = os.getenv("OPENROUTER_API_KEY", "").strip()
        if or_key and not _is_placeholder(or_key):
            self._or_client = OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=or_key,
                timeout=_API_TIMEOUT,
            )
            self._append_active_provider("OpenRouter")

        # ── Cerebras (GRATIS: 14.400 req/día) ────────────────────
        cerebras_key = os.getenv("CEREBRAS_API_KEY", "").strip()
        if cerebras_key and not _is_placeholder(cerebras_key):
            self._cerebras_client = OpenAI(
                base_url=CEREBRAS_BASE_URL,
                api_key=cerebras_key,
                timeout=_API_TIMEOUT,
            )
            self._append_active_provider("Cerebras")

        # ── Mistral (GRATIS: free tier generoso) ─────────────────
        mistral_key = os.getenv("MISTRAL_API_KEY", "").strip()
        if mistral_key and not _is_placeholder(mistral_key):
            self._mistral_client = OpenAI(
                base_url=MISTRAL_BASE_URL,
                api_key=mistral_key,
                timeout=_API_TIMEOUT,
            )
            self._append_active_provider("Mistral")

        # ── Codestral (GRATIS: 2.000 req/día — solo código) ──────
        codestral_key = os.getenv("CODESTRAL_API_KEY", "").strip()
        if codestral_key and not _is_placeholder(codestral_key):
            self._codestral_client = OpenAI(
                base_url=CODESTRAL_BASE_URL,
                api_key=codestral_key,
                timeout=_API_TIMEOUT,
            )
            self._append_active_provider("Codestral")

        # ── DeepSeek ─────────────────────────────────────────────
        deepseek_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
        if deepseek_key and not _is_placeholder(deepseek_key):
            self._deepseek_client = OpenAI(
                base_url=DEEPSEEK_BASE_URL,
                api_key=deepseek_key,
                timeout=_API_TIMEOUT,
            )
            self._append_active_provider("DeepSeek")

        # ── Anthropic / Claude ───────────────────────────────────
        anthropic_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        if anthropic_key and not _is_placeholder(anthropic_key) and _HAS_ANTHROPIC:
            self._anthropic_client = _anthropic_sdk.Anthropic(api_key=anthropic_key)
            self._append_active_provider("Anthropic")

        # ── Custom providers (CUSTOM_PROVIDERS env var) ──────────
        self._custom_clients: list[dict] = []
        custom_raw = os.getenv("CUSTOM_PROVIDERS", "").strip()
        for entry in (e.strip() for e in custom_raw.split(",") if e.strip()):
            parts = entry.split("|", 3)
            if len(parts) == 4:
                name, base_url, api_key, model = [p.strip() for p in parts]
                if name and base_url and not _is_placeholder(api_key):
                    try:
                        client = OpenAI(base_url=base_url, api_key=api_key)
                        self._custom_clients.append({
                            "name": name, "client": client,
                            "model": model, "base_url": base_url, "api_key": api_key,
                        })
                        self._append_active_provider(name)
                    except Exception as e:
                        logger.warning("[Router] Custom provider %s: %s", name, e)

        if not self._has_any_provider():
            raise EnvironmentError(
                "No hay proveedores configurados.\n"
                "Configura al menos uno:\n"
                "  • OLLAMA_BASE_URL=http://127.0.0.1:11434/v1\n"
                "  • OPENCLAW_BASE_URL=http://127.0.0.1:18789/v1\n"
                "  • GROQ_API_KEY=...\n"
                "  • DEEPSEEK_API_KEY=...\n"
                "  • OPENROUTER_API_KEY=...\n"
                "  • ANTHROPIC_API_KEY=..."
            )

        # Orden de proveedores: configurable por env
        self.provider_order = self._resolve_provider_order()

        budget    = float(os.getenv("SESSION_BUDGET_USD", "0.10"))
        threshold = float(os.getenv("BUDGET_WARNING_THRESHOLD", "0.8"))
        self.tracker = ModelUsageTracker(
            session_budget_usd=budget,
            budget_warning_threshold=threshold,
        )
        self.system_prompt = os.getenv("SYSTEM_PROMPT") or _build_system_prompt()

        logger.info("[Router] Proveedores activos: %s", self._active_provider)
        logger.info("[Router] Orden de fallback: %s", ", ".join(self.provider_order))

    # ── API pública ───────────────────────────────────────────────────────────

    def route(
        self,
        messages:    list[dict],
        force_tier:  int | None = None,
        max_tokens:  int = 2048,
        temperature: float = 0.7,
    ) -> dict:
        last_msg     = self._last_user(messages)
        desired_tier = force_tier or ComplexityDetector.detect(last_msg)
        actual_tier  = self._apply_budget_cap(desired_tier)

        # Solo añadir el system prompt si no hay uno ya en la lista
        if not any(m.get("role") == "system" for m in messages):
            full_messages = [{"role": "system", "content": self.system_prompt}] + messages
        else:
            full_messages = list(messages)

        # Determinar provider del primer candidato viable para calcular el límite
        _first_provider = (self.provider_order[0] if self.provider_order else "_default").capitalize()
        full_messages = _trim_messages(full_messages, provider=_first_provider)

        text, tokens, model, provider, billing_model = self._call_with_fallback(
            actual_tier, full_messages, max_tokens, temperature
        )
        self.tracker.record(billing_model, tokens)

        return {
            "response":              text,
            "model":                 model,
            "provider":              provider,
            "tier":                  actual_tier,
            "desired_tier":          desired_tier,
            "tokens_used":           tokens,
            "session_tokens":        self.tracker.total_tokens,
            "budget_remaining_pct":  round(self.tracker.remaining_pct(), 1),
        }

    def route_stream(
        self,
        messages:    list[dict],
        force_tier:  int | None = None,
        max_tokens:  int = 600,
        temperature: float = 0.7,
    ):
        """
        Generator: yields text chunks token-by-token.
        Soporta todos los proveedores OpenAI-compat (Ollama, Groq, Cerebras,
        Mistral, DeepSeek, OpenRouter, OpenClaw, custom).
        Anthropic (SDK nativo) se salta por ahora — cae a route() como fallback.
        Si ningún proveedor acepta stream, devuelve la respuesta completa en un único yield.
        """
        last_msg     = self._last_user(messages)
        desired_tier = force_tier or ComplexityDetector.detect(last_msg)
        actual_tier  = self._apply_budget_cap(desired_tier)

        if not any(m.get("role") == "system" for m in messages):
            full_messages = [{"role": "system", "content": self.system_prompt}] + messages
        else:
            full_messages = list(messages)

        _first_provider = (self.provider_order[0] if self.provider_order else "_default").capitalize()
        full_messages = _trim_messages(full_messages, provider=_first_provider)

        for provider in self.provider_order:
            client: OpenAI | None = None
            model:  str   | None = None
            extra_headers: dict  = {}

            if provider == "ollama" and self._ollama_client and self._ollama_ready:
                models = _with_tier1_fallback(self._ollama_models, actual_tier) or ["llama3.2:1b"]
                client, model = self._ollama_client, models[0]
            elif provider == "openclaw" and self._openclaw_client and self._openclaw_ready:
                hints = _with_tier1_fallback(self._openclaw_models, actual_tier)
                hint = hints[0] if hints else ""
                client = self._openclaw_client
                model = self._openclaw_agent_model
                if hint:
                    extra_headers = {"x-openclaw-model": hint}
            elif provider == "groq" and self._groq_client:
                models = _with_tier1_fallback(GROQ_MODELS, actual_tier)
                client, model = self._groq_client, (models[0] if models else "llama-3.1-8b-instant")
            elif provider == "cerebras" and self._cerebras_client:
                models = _with_tier1_fallback(CEREBRAS_MODELS, actual_tier)
                client, model = self._cerebras_client, (models[0] if models else "llama3.1-8b")
            elif provider == "mistral" and self._mistral_client:
                models = _with_tier1_fallback(MISTRAL_MODELS, actual_tier)
                client, model = self._mistral_client, (models[0] if models else "mistral-small-latest")
            elif provider == "codestral" and self._codestral_client:
                models = _with_tier1_fallback(CODESTRAL_MODELS, actual_tier)
                client, model = self._codestral_client, (models[0] if models else "codestral-latest")
            elif provider == "deepseek" and self._deepseek_client:
                models = _with_tier1_fallback(DEEPSEEK_MODELS, actual_tier)
                client, model = self._deepseek_client, (models[0] if models else "deepseek-v4-flash")
            elif provider == "openrouter" and self._or_client:
                models = _with_tier1_fallback(OPENROUTER_MODELS, actual_tier)
                client, model = self._or_client, (models[0] if models else "google/gemma-3-27b-it:free")
                extra_headers = {
                    "HTTP-Referer": "https://github.com/nova-assistant",
                    "X-Title": "NOVA Personal Assistant",
                }
            elif provider == "anthropic":
                continue  # SDK nativo no se integra aquí — fallback al final
            else:
                custom = next(
                    (c for c in self._custom_clients if c["name"].lower() == provider), None
                )
                if custom:
                    client, model = custom["client"], custom["model"]

            if client is None or model is None:
                continue

            try:
                started = False
                for chunk in self._call_stream(client, provider, model,
                                               full_messages, max_tokens, temperature,
                                               extra_headers or None):
                    started = True
                    yield chunk
                if started:
                    self._last_provider = provider
                    return
            except Exception as exc:
                wait = _parse_retry_after(exc)
                if wait and wait <= _RATE_LIMIT_MAX_WAIT:
                    logger.debug("[rate-limit/stream] %s/%s: esperando %.1fs", provider, model, wait)
                    time.sleep(wait)
                    try:
                        started = False
                        for chunk in self._call_stream(client, provider, model,
                                                       full_messages, max_tokens, temperature,
                                                       extra_headers or None):
                            started = True
                            yield chunk
                        if started:
                            self._last_provider = provider
                            return
                    except Exception:
                        pass
                logger.debug("[Stream] %s/%s falló: %s", provider, model, str(exc)[:80])

        # Fallback: ningún proveedor acepta stream → respuesta completa en un yield
        try:
            result = self.route(messages, force_tier=force_tier,
                                max_tokens=max_tokens, temperature=temperature)
            self._last_provider = result.get("provider", "?")
            yield result.get("response", "")
        except Exception as exc:
            yield f"Error: {exc}"

    # ── Tool calling ─────────────────────────────────────────────────────────

    def _call_with_tools(
        self,
        client: "OpenAI",
        provider: str,
        model: str,
        messages: list[dict],
        max_tokens: int,
        temperature: float,
        tools: list[dict],
        tool_choice: str = "auto",
        extra_headers: dict | None = None,
    ) -> dict:
        """
        Llamada OpenAI con function calling. Retorna:
          {"text": str, "tool_calls": [...], "tokens": int}
        tool_calls = [{"id":..., "type":"function",
                        "function":{"name":..., "arguments": dict}}]
        """
        import json as _json
        headers: dict = {}
        if provider in ("openrouter", "OpenRouter"):
            headers.update({
                "HTTP-Referer": "https://github.com/nova-assistant",
                "X-Title": "NOVA Personal Assistant",
            })
        if extra_headers:
            headers.update(extra_headers)

        actual_messages = messages
        if provider in ("ollama", "Ollama") and self._should_disable_thinking(model):
            actual_messages = self._disable_thinking_in_messages(messages)

        extra = {"extra_headers": headers} if headers else {}
        r = client.chat.completions.create(
            model=model, messages=actual_messages,
            max_tokens=max_tokens, temperature=temperature,
            tools=tools, tool_choice=tool_choice,
            **extra,
        )
        msg = r.choices[0].message
        text = msg.content or ""
        raw_calls = msg.tool_calls or []
        tool_calls: list[dict] = []
        for tc in raw_calls:
            try:
                args = _json.loads(tc.function.arguments or "{}")
            except Exception:
                args = {}
            tool_calls.append({
                "id":   tc.id,
                "type": "function",
                "function": {"name": tc.function.name, "arguments": args},
            })
        tokens = r.usage.total_tokens if r.usage else 0
        return {"text": text, "tool_calls": tool_calls, "tokens": tokens}

    def route_with_tools_simple(
        self,
        messages: list[dict],
        tools: list[dict],
        force_tier: int = 1,
        max_tokens: int = 50,
        temperature: float = 0.0,
    ) -> dict:
        """
        1 turno con function calling. Retorna el dict raw de _call_with_tools.
        Itera providers hasta encontrar uno que responda sin error.
        Si todos fallan devuelve {"text": "", "tool_calls": [], "tokens": 0}.
        """
        actual_tier = self._apply_budget_cap(force_tier)
        for provider in self.provider_order:
            client = model = None
            extra_headers: dict = {}
            if provider == "ollama" and self._ollama_client and self._ollama_ready:
                models = _with_tier1_fallback(self._ollama_models, actual_tier)
                if not models:
                    continue
                client, model = self._ollama_client, models[0]
            elif provider == "groq" and self._groq_client:
                models = _with_tier1_fallback(GROQ_MODELS, actual_tier)
                client, model = self._groq_client, (models[0] if models else "llama-3.1-8b-instant")
            elif provider == "cerebras" and self._cerebras_client:
                models = _with_tier1_fallback(CEREBRAS_MODELS, actual_tier)
                client, model = self._cerebras_client, (models[0] if models else "llama3.1-8b")
            elif provider == "mistral" and self._mistral_client:
                models = _with_tier1_fallback(MISTRAL_MODELS, actual_tier)
                client, model = self._mistral_client, (models[0] if models else "mistral-small-latest")
            elif provider == "openrouter" and self._or_client:
                models = _with_tier1_fallback(OPENROUTER_MODELS, actual_tier)
                client, model = self._or_client, (models[0] if models else "meta-llama/llama-3.1-8b-instruct:free")
                extra_headers = {
                    "HTTP-Referer": "https://github.com/nova-assistant",
                    "X-Title": "NOVA Personal Assistant",
                }
            elif provider == "deepseek" and self._deepseek_client:
                models = _with_tier1_fallback(DEEPSEEK_MODELS, actual_tier)
                client, model = self._deepseek_client, (models[0] if models else "deepseek-v4-flash")
            else:
                continue
            if client is None or model is None:
                continue
            try:
                return self._call_with_tools(
                    client, provider, model, messages,
                    max_tokens, temperature, tools,
                    extra_headers=extra_headers or None,
                )
            except Exception as exc:
                logger.debug("[tools_simple] %s/%s falló: %s", provider, model, str(exc)[:80])
        return {"text": "", "tool_calls": [], "tokens": 0}

    def route_agentic(
        self,
        goal: str,
        tools: list[dict],
        executor_fn,
        history: list[dict] | None = None,
        max_iter: int = 6,
        progress_cb=None,
        force_tier: int = 2,
    ) -> dict:
        """
        Loop agéntico Plan → Execute → Verify.

        1. PLAN  — 1 llamada LLM sin tools: genera plan numerado
        2. EXEC  — loop hasta max_iter: llama con tools, ejecuta tool_calls,
                   añade resultados al contexto, itera
        3. SYNTH — si se agotaron iteraciones, pide resumen

        Args:
            goal:        objetivo del usuario (string)
            tools:       list[dict] OpenAI function schemas
            executor_fn: callable(name: str, args: dict) -> str
            progress_cb: callable(msg: str) — imprime progreso (opcional)
            force_tier:  tier LLM (2 = modelos 70B, mejor tool following)

        Returns:
            {"response": str, "plan": str, "iters": int}
        """
        def _cb(msg: str) -> None:
            if progress_cb:
                progress_cb(msg)

        tool_names = ", ".join(
            t["function"]["name"] for t in tools if t.get("function")
        )

        # ── Cargar contexto de memoria neuronal ──────────────────────────────
        mem_ctx = ""
        try:
            from nova.tools.nova_neuro_memory import neuro_memory
            if neuro_memory is not None:
                mem_ctx = neuro_memory.search_context(goal, limit=4) or ""
        except Exception:
            pass

        # ── PHASE 1: PLAN ────────────────────────────────────────────────────
        plan_sys = (
            f"{self.system_prompt}\n\n"
            "Antes de ejecutar cualquier acción, creá un plan numerado claro. "
            "Muestra el plan completo. Luego lo ejecutarás paso a paso."
        )
        if mem_ctx:
            plan_sys += f"\n\nContexto de memoria relevante:\n{mem_ctx}"

        plan_msgs = [
            {"role": "system", "content": plan_sys},
            {
                "role": "user",
                "content": (
                    f"Objetivo: {goal}\n\n"
                    f"Herramientas disponibles: {tool_names}\n\n"
                    "Creá un plan numerado ANTES de ejecutar. Solo el plan, sin ejecutar todavía."
                ),
            },
        ]
        try:
            _cb("\n📋 Plan:\n")
            plan_chunks: list[str] = []
            for _chunk in self.route_stream(plan_msgs, force_tier=force_tier, max_tokens=400, temperature=0.3):
                _cb(_chunk)
                plan_chunks.append(_chunk)
            plan_text = "".join(plan_chunks)
            _cb("\n")
        except Exception:
            plan_text = "(no se pudo generar un plan previo)"
            _cb(f"\n📋 Plan:\n{plan_text}\n")

        # ── PHASE 2: EXECUTE ─────────────────────────────────────────────────
        exec_messages: list[dict] = [
            {
                "role": "system",
                "content": (
                    f"{self.system_prompt}\n\n"
                    "Ejecutá el objetivo usando las herramientas disponibles. "
                    "Llamá UNA herramienta a la vez. Cuando termines, respondé con un resumen."
                ),
            },
            {"role": "user",    "content": goal},
            {"role": "assistant", "content": plan_text},
            {"role": "user",    "content": "Ejecutá el plan ahora, paso a paso."},
        ]

        actual_tier = self._apply_budget_cap(force_tier)
        for iteration in range(max_iter):
            result = self.route_with_tools_simple(
                exec_messages, tools,
                force_tier=force_tier, max_tokens=600, temperature=0.3,
            )

            if result["tool_calls"]:
                # Añadir el mensaje assistant con tool_calls al contexto
                exec_messages.append({
                    "role": "assistant",
                    "content": result["text"] or None,
                    "tool_calls": [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["function"]["name"],
                                "arguments": json.dumps(tc["function"]["arguments"]),
                            },
                        }
                        for tc in result["tool_calls"]
                    ],
                })
                for tc in result["tool_calls"]:
                    name = tc["function"]["name"]
                    args = tc["function"]["arguments"]
                    _cb(f"  ⚙️  {name}({args})")
                    try:
                        tool_result = executor_fn(name, args)
                    except Exception as exc:
                        tool_result = f"Error: {exc}"
                    _cb(f"     → {str(tool_result)[:300]}")
                    exec_messages.append({
                        "role":         "tool",
                        "tool_call_id": tc["id"],
                        "content":      str(tool_result),
                    })
            else:
                # LLM no pidió más tools → respuesta final
                final = result["text"] or "(sin respuesta)"
                return {"response": final, "plan": plan_text, "iters": iteration + 1}

        # ── PHASE 3: SYNTH ───────────────────────────────────────────────────
        _cb("\n🔄 Sintetizando resultados...\n")
        exec_messages.append({"role": "user", "content": "Resumí en 2-3 oraciones qué hiciste y el resultado."})
        try:
            synth_chunks: list[str] = []
            for _chunk in self.route_stream(exec_messages, force_tier=force_tier, max_tokens=300):
                _cb(_chunk)
                synth_chunks.append(_chunk)
            final = "".join(synth_chunks)
            _cb("\n")
        except Exception:
            final = "Tarea completada."
        return {"response": final, "plan": plan_text, "iters": max_iter}

    def get_session_summary(self) -> dict:
        return self.tracker.summary()

    @staticmethod
    def _resize_image_for_vision(image_path: str, max_width: int = 1280) -> str:
        """
        Escala la imagen a max_width px y la convierte a JPEG para reducir
        el payload (crítico en displays Retina 3360×2100 → ~3MB base64).
        Retorna el path del archivo escalado (temporal).
        """
        try:
            from PIL import Image
            import tempfile
            img = Image.open(image_path).convert("RGB")
            w, h = img.size
            if w > max_width:
                scale = max_width / w
                img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
            fd, out_path = tempfile.mkstemp(suffix=".jpg")
            os.close(fd)
            img.save(out_path, "JPEG", quality=80)
            return out_path
        except Exception:
            return image_path  # Si falla PIL, usar original

    def _vision_query_ollama_native(
        self, model: str, prompt: str, image_path: str, max_tokens: int, timeout: int = 60
    ) -> str | None:
        """
        Llama a /api/generate de Ollama directamente (más fiable para visión
        que la capa OpenAI-compat). Retorna texto o None si falla/timeout.
        """
        import urllib.request as _ur
        scaled = self._resize_image_for_vision(image_path)
        try:
            with open(scaled, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            payload = json.dumps({
                "model": model,
                "prompt": prompt + " /no_think",
                "images": [b64],
                "stream": False,
                "options": {"num_predict": max_tokens},
            }).encode()
            base_url = self._ollama_base.rstrip("/").replace("/v1", "")
            req = _ur.Request(
                f"{base_url}/api/generate", data=payload,
                headers={"Content-Type": "application/json"},
            )
            with _ur.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read())
                return data.get("response", "").strip() or None
        except Exception as exc:
            logger.debug("[ollama native vision] %s: %s", model, str(exc)[:60])
            return None
        finally:
            if scaled != image_path:
                try:
                    os.unlink(scaled)
                except Exception:
                    pass

    def vision_query(
        self,
        prompt: str,
        image_path: str,
        tier: int = 3,
        max_tokens: int = 1500,
        system_override: str = None,
    ) -> str:
        """
        Analiza una imagen con la cadena de visión:
          1. Ollama local — llava/qwen3-vl (privado, sin rate limits)
          2. OpenRouter Gemma-4 (cloud, gratis, visión nativa) — fallback
          3. Fallback: mensaje de error

        Ollama se intenta primero para evitar los 429 (rate limit) frecuentes
        de los modelos gratuitos de OpenRouter.  Si Ollama no está disponible
        o no tiene un modelo de visión instalado, se cae a OpenRouter.
        """
        if not os.path.exists(image_path):
            return "No encontré el archivo de imagen para analizar, Señor."

        sys_content = system_override if system_override else self.system_prompt

        # ── 1. Ollama local — llava primero (rápido), qwen3-vl como respaldo ──
        # Intentar local primero para evitar rate limits de OpenRouter.
        if self._ollama_ready:
            all_local = {m for lst in self._ollama_models.values() for m in lst}
            for vision_model in OLLAMA_VISION_MODELS:
                if vision_model not in all_local:
                    continue
                logger.debug("[vision] Intentando Ollama local: %s", vision_model)
                result = self._vision_query_ollama_native(
                    model=vision_model, prompt=prompt,
                    image_path=image_path, max_tokens=max_tokens, timeout=75,
                )
                if result:
                    logger.info("[vision OK] Ollama/%s", vision_model)
                    return result

        # ── 2. OpenRouter — Gemma 4 con visión (cloud, gratis) ──────────────
        if self._or_client:
            scaled = self._resize_image_for_vision(image_path)
            try:
                with open(scaled, "rb") as f:
                    b64_data = base64.b64encode(f.read()).decode("utf-8")
                messages = [
                    {"role": "system", "content": sys_content},
                    {"role": "user", "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url",
                         "image_url": {"url": f"data:image/jpeg;base64,{b64_data}"}},
                    ]},
                ]
                for vision_model in OPENROUTER_VISION_MODELS:
                    try:
                        t0 = time.time()
                        text, tokens = self._call(
                            client=self._or_client, provider="OpenRouter",
                            model=vision_model, messages=messages,
                            max_tokens=max_tokens, temperature=0.2,
                        )
                        self.stats_tracker.record_success(vision_model, time.time() - t0)
                        logger.info("[vision OK] OpenRouter/%s en %.1fs", vision_model, time.time()-t0)
                        return text
                    except Exception as exc:
                        self.stats_tracker.record_fail(vision_model)
                        logger.debug("[vision fallback] OpenRouter/%s: %s", vision_model, str(exc)[:60])
            finally:
                if scaled != image_path:
                    try:
                        os.unlink(scaled)
                    except Exception:
                        pass

        return "No pude analizar la imagen en este momento, Señor."

    # ── Internos ──────────────────────────────────────────────────────────────

    def _apply_budget_cap(self, tier: int) -> int:
        return 1 if (self.tracker.over_threshold() and tier > 1) else tier

    def _has_any_provider(self) -> bool:
        return any([
            self._ollama_client is not None and self._ollama_ready,
            self._openclaw_client is not None and self._openclaw_ready,
            self._groq_client is not None,
            self._cerebras_client is not None,
            self._mistral_client is not None,
            self._codestral_client is not None,
            self._deepseek_client is not None,
            self._or_client is not None,
            self._anthropic_client is not None,
            bool(self._custom_clients),
        ])

    def _resolve_ollama_base(self) -> str:
        """
        Auto-detecta la URL correcta de Ollama.
        Versiones nuevas (>=0.1.24) tienen /v1 (OpenAI-compatible).
        Versiones viejas solo tienen la API nativa en el puerto raíz.
        Prueba /v1/models primero; si falla, usa la base sin /v1.
        """
        env_url = os.getenv("OLLAMA_BASE_URL", "").strip()
        base_host = (env_url.rstrip("/").replace("/v1", "")
                     if env_url else "http://127.0.0.1:11434")

        # Probar endpoint OpenAI-compatible (/v1)
        try:
            url = f"{base_host}/v1/models"
            with urllib.request.urlopen(
                urllib.request.Request(url), timeout=2
            ) as r:
                if r.status == 200:
                    return f"{base_host}/v1"
        except Exception:
            pass

        # Fallback: Ollama sin /v1 — usamos la URL base directa
        # El cliente OpenAI igual puede conectarse; Ollama nativo responde en /
        return base_host

    def _detect_ollama_models(self) -> dict[int, list[str]]:
        """
        Detecta qué modelos de Ollama están disponibles localmente.
        Hace una petición a /api/tags para obtener la lista.
        """
        global OLLAMA_AVAILABLE_MODELS
        available = {1: [], 2: [], 3: []}

        try:
            base = self._ollama_base.rstrip("/").replace("/v1", "")
            url = f"{base}/api/tags"
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=2) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    local_models = {m["name"] for m in data.get("models", [])}

                    # Filtrar modelos conocidos por tier
                    for tier, models in OLLAMA_MODELS.items():
                        for model in models:
                            if model in local_models:
                                available[tier].append(model)

                    # También agregar cualquier otro modelo detectado como tier 2.
                    # Excluir modelos de embeddings — no soportan /chat/completions.
                    _EMBEDDING_SUFFIXES = ("embedding", "embed", "rerank")
                    for model in local_models:
                        if not any(model in lst for lst in available.values()):
                            model_lower = model.lower()
                            if any(s in model_lower for s in _EMBEDDING_SUFFIXES):
                                logger.debug("[Router] Modelo de embeddings ignorado en chat: %s", model)
                                continue
                            available[2].append(model)

                    OLLAMA_AVAILABLE_MODELS = available
        except Exception as e:
            logger.debug("[Router] Ollama no detectado o error: %s", e)

        return available

    def _append_active_provider(self, name: str) -> None:
        if self._active_provider == "ninguno":
            self._active_provider = name
        else:
            self._active_provider += f" + {name}"

    def _resolve_provider_order(self) -> list[str]:
        raw = _csv_env("ROUTER_PROVIDER_ORDER", "ollama,openclaw,groq,cerebras,mistral,openrouter")
        allowed = {"ollama", "openclaw", "groq", "cerebras", "mistral", "codestral",
                   "deepseek", "openrouter", "anthropic"}
        for c in self._custom_clients:
            allowed.add(c["name"].lower())
        order = [x.lower() for x in raw if x.lower() in allowed]
        _avail_map: dict[str, bool] = {
            "ollama":     self._ollama_ready,
            "openclaw":   self._openclaw_ready,
            "groq":       self._groq_client is not None,
            "cerebras":   self._cerebras_client is not None,
            "mistral":    self._mistral_client is not None,
            "codestral":  self._codestral_client is not None,
            "deepseek":   self._deepseek_client is not None,
            "openrouter": self._or_client is not None,
            "anthropic":  self._anthropic_client is not None,
        }
        for c in self._custom_clients:
            _avail_map[c["name"].lower()] = True
        available = [p for p in order if _avail_map.get(p, False)]
        if not available:
            available = [p for p, ok in _avail_map.items() if ok]
        return available

    def _resolve_openclaw_models(self) -> dict[int, list[str]]:
        # 1) Overrides explícitos por tier
        explicit = {
            1: _csv_env("OPENCLAW_TIER1_MODELS"),
            2: _csv_env("OPENCLAW_TIER2_MODELS"),
            3: _csv_env("OPENCLAW_TIER3_MODELS"),
        }
        if any(explicit.values()):
            return explicit

        # 2) Derivar por perfil (eco/balanced/power)
        profile = (os.getenv("OPENCLAW_PROFILE", "auto").strip().lower() or "auto")
        if profile not in OPENCLAW_ENV_PROFILES:
            profile = "auto"

        if profile == "auto":
            low_budget  = _safe_float(os.getenv("OPENCLAW_AUTO_LOW_BUDGET_USD", "0.08"), 0.08)
            high_budget = _safe_float(os.getenv("OPENCLAW_AUTO_HIGH_BUDGET_USD", "0.30"), 0.30)
            budget = _safe_float(os.getenv("SESSION_BUDGET_USD", "0.10"), 0.10)
            if budget <= low_budget:
                profile = "eco"
            elif budget >= high_budget:
                profile = "power"
            else:
                profile = "balanced"

        eco_model      = os.getenv("OPENCLAW_MODEL_ECO", "").strip()
        balanced_model = os.getenv("OPENCLAW_MODEL_BALANCED", "").strip()
        power_model    = os.getenv("OPENCLAW_MODEL_POWER", "").strip()

        # Si no hay hints, OpenClaw decide internamente.
        if not any([eco_model, balanced_model, power_model]):
            return {1: [], 2: [], 3: []}

        if profile == "eco":
            return {
                1: [eco_model] if eco_model else [],
                2: [eco_model] if eco_model else [],
                3: [balanced_model] if balanced_model else ([eco_model] if eco_model else []),
            }
        if profile == "power":
            return {
                1: [balanced_model] if balanced_model else ([eco_model] if eco_model else []),
                2: [power_model] if power_model else ([balanced_model] if balanced_model else []),
                3: [power_model] if power_model else ([balanced_model] if balanced_model else []),
            }
        # balanced
        return {
            1: [eco_model] if eco_model else [],
            2: [balanced_model] if balanced_model else ([eco_model] if eco_model else []),
            3: [power_model] if power_model else ([balanced_model] if balanced_model else []),
        }

    @staticmethod
    def _probe_openclaw_http(base_url: str, api_key: str) -> bool:
        """
        Verifica si OpenClaw expone la API HTTP OpenAI-compatible.
        Consideramos "activo" si /models responde 200/401/403.
        """
        url = base_url.rstrip("/") + "/models"
        req = urllib.request.Request(url, method="GET")
        if api_key:
            req.add_header("Authorization", f"Bearer {api_key}")
        try:
            with urllib.request.urlopen(req, timeout=1.8) as resp:
                return resp.status == 200
        except urllib.error.HTTPError as exc:
            return exc.code in (401, 403)
        except Exception:
            return False

    def _call_with_fallback(
        self, tier: int, messages: list[dict], max_tokens: int, temperature: float
    ) -> tuple[str, int, str, str, str]:
        """
        Orden de intento:
          1. Se define por ROUTER_PROVIDER_ORDER
          2. Dentro de cada proveedor, los modelos se ordenan por score
        """
        attempts: list[dict] = []
        for provider in self.provider_order:
            if provider == "ollama" and self._ollama_client and self._ollama_ready:
                models = _with_tier1_fallback(self._ollama_models, tier) or ["llama3.2:1b"]
                for model in models:
                    attempts.append({
                        "client": self._ollama_client,
                        "provider": "Ollama",
                        "model": model,
                        "display_model": model,
                        "billing_model": model,
                        "extra_headers": {},
                    })

            elif provider == "openclaw" and self._openclaw_client and self._openclaw_ready:
                hints = _with_tier1_fallback(self._openclaw_models, tier)
                if not hints:
                    hints = [""]
                for hint in hints:
                    headers = {"x-openclaw-model": hint} if hint else {}
                    display = (
                        f"{self._openclaw_agent_model} => {hint}"
                        if hint else self._openclaw_agent_model
                    )
                    billing_model = hint or self._openclaw_agent_model
                    attempts.append({
                        "client": self._openclaw_client,
                        "provider": "OpenClaw",
                        "model": self._openclaw_agent_model,
                        "display_model": display,
                        "billing_model": billing_model,
                        "extra_headers": headers,
                    })

            elif provider == "groq" and self._groq_client:
                for model in _with_tier1_fallback(GROQ_MODELS, tier):
                    attempts.append({
                        "client": self._groq_client,
                        "provider": "Groq",
                        "model": model,
                        "display_model": model,
                        "billing_model": model,
                        "extra_headers": {},
                    })

            elif provider == "cerebras" and self._cerebras_client:
                for model in _with_tier1_fallback(CEREBRAS_MODELS, tier):
                    attempts.append({
                        "client": self._cerebras_client,
                        "provider": "Cerebras",
                        "model": model,
                        "display_model": f"cerebras/{model}",
                        "billing_model": model,
                        "extra_headers": {},
                    })

            elif provider == "mistral" and self._mistral_client:
                for model in _with_tier1_fallback(MISTRAL_MODELS, tier):
                    attempts.append({
                        "client": self._mistral_client,
                        "provider": "Mistral",
                        "model": model,
                        "display_model": f"mistral/{model}",
                        "billing_model": model,
                        "extra_headers": {},
                    })

            elif provider == "codestral" and self._codestral_client:
                for model in _with_tier1_fallback(CODESTRAL_MODELS, tier):
                    attempts.append({
                        "client": self._codestral_client,
                        "provider": "Codestral",
                        "model": model,
                        "display_model": f"codestral/{model}",
                        "billing_model": model,
                        "extra_headers": {},
                    })

            elif provider == "deepseek" and self._deepseek_client:
                for model in _with_tier1_fallback(DEEPSEEK_MODELS, tier):
                    attempts.append({
                        "client": self._deepseek_client,
                        "provider": "DeepSeek",
                        "model": model,
                        "display_model": f"deepseek/{model}",
                        "billing_model": model,
                        "extra_headers": {},
                    })

            elif provider == "openrouter" and self._or_client:
                for model in _with_tier1_fallback(OPENROUTER_MODELS, tier):
                    attempts.append({
                        "client": self._or_client,
                        "provider": "OpenRouter",
                        "model": model,
                        "display_model": model,
                        "billing_model": model,
                        "extra_headers": {},
                    })

            elif provider == "anthropic" and self._anthropic_client:
                for model in _with_tier1_fallback(CLAUDE_MODELS, tier):
                    attempts.append({
                        "client": None,          # usa _call_anthropic
                        "provider": "Anthropic",
                        "model": model,
                        "display_model": model,
                        "billing_model": model,
                        "extra_headers": {},
                    })

            else:
                custom = next(
                    (c for c in self._custom_clients if c["name"].lower() == provider),
                    None,
                )
                if custom:
                    attempts.append({
                        "client": custom["client"],
                        "provider": custom["name"],
                        "model": custom["model"],
                        "display_model": f"{custom['name']}/{custom['model']}",
                        "billing_model": custom["model"],
                        "extra_headers": {},
                    })

        # Ordenar por score de estadísticas (mejores primero)
        attempts.sort(key=lambda x: self.stats_tracker.score(x["billing_model"]), reverse=True)

        last_error: Exception | None = None
        for attempt in attempts:
            start_time = time.time()
            try:
                if attempt["provider"] == "Anthropic":
                    text, tokens = self._call_anthropic(
                        model=attempt["model"],
                        messages=messages,
                        max_tokens=max_tokens,
                        temperature=temperature,
                    )
                else:
                    text, tokens = self._call(
                        client=attempt["client"],
                        provider=attempt["provider"],
                        model=attempt["model"],
                        messages=messages,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        extra_headers=attempt["extra_headers"],
                    )
                latency = time.time() - start_time
                self.stats_tracker.record_success(attempt["billing_model"], latency)
                return (
                    text,
                    tokens,
                    attempt["display_model"],
                    attempt["provider"],
                    attempt["billing_model"],
                )
            except Exception as exc:
                latency = time.time() - start_time
                self.stats_tracker.record_fail(attempt["billing_model"])
                exc_str = str(exc)
                wait = _parse_retry_after(exc)
                if wait and wait <= _RATE_LIMIT_MAX_WAIT:
                    logger.debug("[rate-limit] %s/%s: esperando %.1fs",
                                 attempt['provider'], attempt['display_model'], wait)
                    time.sleep(wait)
                    # Retry once after waiting
                    try:
                        start_time = time.time()
                        if attempt["provider"] == "Anthropic":
                            text, tokens = self._call_anthropic(
                                model=attempt["model"], messages=messages,
                                max_tokens=max_tokens, temperature=temperature,
                            )
                        else:
                            text, tokens = self._call(
                                client=attempt["client"], provider=attempt["provider"],
                                model=attempt["model"], messages=messages,
                                max_tokens=max_tokens, temperature=temperature,
                                extra_headers=attempt["extra_headers"],
                            )
                        latency = time.time() - start_time
                        self.stats_tracker.record_success(attempt["billing_model"], latency)
                        return (text, tokens, attempt["display_model"],
                                attempt["provider"], attempt["billing_model"])
                    except Exception as exc2:
                        exc_str = str(exc2)
                        self.stats_tracker.record_fail(attempt["billing_model"])
                logger.debug("[fallback] %s/%s: %s",
                             attempt['provider'], attempt['display_model'], exc_str[:70])
                last_error = exc

        raise RuntimeError(f"Todos los modelos fallaron. Último error: {last_error}")

    # Modelos Qwen3/Qwen3.5 que tienen modo "thinking" activado por defecto
    _THINKING_MODELS = {"qwen3", "qwen3.5", "qwen3-vl"}

    def _should_disable_thinking(self, model: str) -> bool:
        """Detecta si el modelo es Qwen3 con thinking mode activado."""
        model_lower = model.lower()
        return any(name in model_lower for name in self._THINKING_MODELS)

    def _disable_thinking_in_messages(self, messages: list[dict]) -> list[dict]:
        """
        Agrega /no_think al último mensaje de usuario para desactivar
        el chain-of-thought en modelos Qwen3 (ahorra 5-15 segundos).
        """
        msgs = [m.copy() for m in messages]
        for i in range(len(msgs) - 1, -1, -1):
            if msgs[i].get("role") == "user":
                content = msgs[i].get("content", "")
                if isinstance(content, str) and "/no_think" not in content:
                    msgs[i]["content"] = content + " /no_think"
                break
        return msgs

    def _call(
        self,
        client: OpenAI,
        provider: str,
        model: str,
        messages: list[dict],
        max_tokens: int,
        temperature: float,
        extra_headers: dict | None = None,
    ) -> tuple[str, int]:
        headers = {}
        if provider == "OpenRouter":
            headers.update({
                "HTTP-Referer": "https://github.com/nova-assistant",
                "X-Title": "NOVA Personal Assistant",
            })
        if extra_headers:
            headers.update(extra_headers)

        # Desactivar thinking en Qwen3 para respuestas rápidas (tier 1/2)
        actual_messages = messages
        if provider == "Ollama" and self._should_disable_thinking(model):
            actual_messages = self._disable_thinking_in_messages(messages)

        extra = {"extra_headers": headers} if headers else {}
        r = client.chat.completions.create(
            model=model, messages=actual_messages,
            max_tokens=max_tokens, temperature=temperature,
            **extra,
        )
        message = r.choices[0].message
        raw_content = message.content or ""
        if isinstance(raw_content, list):
            text = " ".join(
                p.get("text", "") if isinstance(p, dict) else str(p)
                for p in raw_content
            ).strip()
        else:
            text = str(raw_content).strip()
        if not text:
            text = "Orden procesada, Señor."
        tokens = r.usage.total_tokens if r.usage else 0
        return text, tokens

    def _call_stream(
        self,
        client: OpenAI,
        provider: str,
        model: str,
        messages: list[dict],
        max_tokens: int,
        temperature: float,
        extra_headers: dict | None = None,
    ):
        """Generator: yields text chunks from a streaming completions call."""
        headers: dict = {}
        if provider == "OpenRouter":
            headers.update({
                "HTTP-Referer": "https://github.com/nova-assistant",
                "X-Title": "NOVA Personal Assistant",
            })
        if extra_headers:
            headers.update(extra_headers)

        actual_messages = messages
        if provider == "Ollama" and self._should_disable_thinking(model):
            actual_messages = self._disable_thinking_in_messages(messages)

        extra = {"extra_headers": headers} if headers else {}
        stream = client.chat.completions.create(
            model=model, messages=actual_messages,
            max_tokens=max_tokens, temperature=temperature,
            stream=True, **extra,
        )
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    def _call_anthropic(
        self,
        model: str,
        messages: list[dict],
        max_tokens: int,
        temperature: float,
    ) -> tuple[str, int]:
        """
        Llama a la API de Anthropic (Claude).
        Convierte el formato OpenAI messages → Anthropic format.
        """
        # Extraer system prompt si está en el primer mensaje
        system_content = None
        conv_messages = []
        for m in messages:
            role = m.get("role")
            content = m.get("content", "")
            if role == "system":
                system_content = content
            else:
                conv_messages.append({"role": role, "content": content})

        kwargs: dict = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": conv_messages,
        }
        if system_content:
            kwargs["system"] = system_content

        resp = self._anthropic_client.messages.create(**kwargs)
        text = resp.content[0].text.strip() if resp.content else "Orden procesada, Señor."
        tokens = (resp.usage.input_tokens or 0) + (resp.usage.output_tokens or 0)
        return text, tokens

    @staticmethod
    def _write_env_var(key: str, value: str) -> bool:
        import re as _re
        try:
            from dotenv import find_dotenv
            env_path = find_dotenv(usecwd=True) or find_dotenv()
        except Exception:
            env_path = ""
        if not env_path:
            base = os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.dirname(os.path.abspath(__file__))
            )))
            env_path = os.path.join(base, ".env")
        try:
            if os.path.exists(env_path):
                with open(env_path, "r", encoding="utf-8") as fh:
                    content = fh.read()
            else:
                content = ""
            pattern = rf"^{_re.escape(key)}=.*$"
            if _re.search(pattern, content, _re.MULTILINE):
                content = _re.sub(pattern, f"{key}={value}", content, flags=_re.MULTILINE)
            else:
                content = content.rstrip("\n") + f"\n{key}={value}\n"
            with open(env_path, "w", encoding="utf-8") as fh:
                fh.write(content)
            return True
        except Exception as exc:
            logger.warning("[Router] _write_env_var %s: %s", key, exc)
            return False

    def add_custom_provider(
        self, name: str, base_url: str, api_key: str, model: str
    ) -> str:
        if _is_placeholder(api_key):
            return f"La API key para '{name}' parece inválida o es un placeholder."
        try:
            client = OpenAI(base_url=base_url, api_key=api_key)
            client.models.list()
        except Exception as exc:
            probe_err = str(exc)[:120]
            try:
                client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": "hi"}],
                    max_tokens=4,
                )
            except Exception as exc2:
                return (
                    f"No pude conectar con el proveedor '{name}'. "
                    f"Error probe: {probe_err} | {str(exc2)[:80]}"
                )
        existing = next(
            (i for i, c in enumerate(self._custom_clients) if c["name"].lower() == name.lower()),
            None,
        )
        entry = {"name": name, "client": client, "model": model,
                 "base_url": base_url, "api_key": api_key}
        if existing is not None:
            self._custom_clients[existing] = entry
        else:
            self._custom_clients.append(entry)
            if name.lower() not in [p.lower() for p in self.provider_order]:
                self.provider_order.append(name.lower())
            self._append_active_provider(name)

        existing_entries = []
        for c in self._custom_clients:
            existing_entries.append(f"{c['name']}|{c['base_url']}|{c['api_key']}|{c['model']}")
        serialized = ",".join(existing_entries)
        self._write_env_var("CUSTOM_PROVIDERS", serialized)
        os.environ["CUSTOM_PROVIDERS"] = serialized

        action = "actualizado" if existing is not None else "agregado"
        return (
            f"Proveedor '{name}' {action} correctamente. "
            f"Modelo: {model}. Proveedores activos: {self._active_provider}"
        )

    def get_model_stats(self) -> dict:
        """Retorna las estadísticas de uso de los modelos."""
        return self.stats_tracker.get_stats()

    def route_parallel(self, tasks: list[dict], max_workers: int = 3) -> list[dict]:
        """
        Ejecuta múltiples consultas al router en paralelo consolidando especialistas.
        Cada dict en tasks debe tener un 'messages', y opcionalmente 'force_tier', 'agentic', 'max_iter', etc.
        Si 'agentic' es True, invoca route_agentic(), de lo contrario route().
        Retorna la lista de resultados en el mismo orden.
        """
        import concurrent.futures
        
        def _execute_task(task_spec: dict) -> dict:
            try:
                if task_spec.get("agentic", False):
                    # Si es agentic se asume que hay tools y executor_fn proveídos en task_spec o globalmente
                    # Para simplificar, intentamos usar un fallback si no vienen en el task_spec
                    from nova.tools.nova_tools_schemas import get_tool_schemas
                    from nova.tools.nova_skills import execute_tool
                    tools = task_spec.get("tools", get_tool_schemas())
                    executor = task_spec.get("executor_fn", execute_tool)
                    return self.route_agentic(
                        goal=task_spec.get("goal", self._last_user(task_spec.get("messages", []))),
                        tools=tools,
                        executor_fn=executor,
                        max_iter=task_spec.get("max_iter", 3),
                        force_tier=task_spec.get("force_tier", 2)
                    )
                else:
                    return self.route(
                        messages=task_spec.get("messages", []),
                        force_tier=task_spec.get("force_tier"),
                        max_tokens=task_spec.get("max_tokens", 2048),
                        temperature=task_spec.get("temperature", 0.7)
                    )
            except Exception as e:
                return {"response": f"Error en subagente: {e}", "error": str(e)}

        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(_execute_task, t) for t in tasks]
            for future in concurrent.futures.as_completed(futures):
                pass  # Wait for all to complete
            
            # Preserve order
            for future in futures:
                results.append(future.result())
                
        return results

    @staticmethod
    def _last_user(messages: list[dict]) -> str:
        for m in reversed(messages):
            if m.get("role") == "user":
                return m.get("content", "")
        return ""
