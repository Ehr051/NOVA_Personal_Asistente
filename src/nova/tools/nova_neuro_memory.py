import os
import json
import uuid
import time
import logging
from datetime import datetime

log = logging.getLogger(__name__)

try:
    from mem0 import Memory
    _MEM0_AVAILABLE = True
except ImportError:
    _MEM0_AVAILABLE = False
    class Memory:
        @staticmethod
        def from_config(config):
            return None

# SQLite cross-thread safety: QdrantClient.__del__ gets called from the GC
# thread which differs from the thread that opened the SQLite connection,
# causing "SQLite objects created in a thread can only be used in that same
# thread" errors on shutdown. Silencing __del__ is safe because close() is
# called explicitly by NovaNeuralMemory.close() before the object is released.
try:
    from qdrant_client import QdrantClient as _QdrantClient
    if not getattr(_QdrantClient, "_nova_del_patched", False):
        _QdrantClient.__del__ = lambda self: None
        _QdrantClient._nova_del_patched = True
except BaseException:
    # BaseException (not just Exception) to also catch KeyboardInterrupt raised
    # by Pydantic v2 schema generation on Python 3.10 during qdrant_client import.
    pass

# Suppress mem0 telemetry atexit handler — it blocks shutdown and crashes on KeyboardInterrupt.
try:
    from mem0.memory import telemetry as _mem0_tel
    if hasattr(_mem0_tel, "AnonymousTelemetry"):
        _mem0_tel.AnonymousTelemetry.close = lambda self: None
except BaseException:
    pass


def _pick_ollama_memory_model() -> str:
    """Elige el modelo Ollama más liviano disponible para mem0."""
    try:
        import urllib.request
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=2) as r:
            import json
            data = json.loads(r.read())
        names = [m["name"] for m in data.get("models", [])]
        # Preferencia: modelos livianos/rápidos en orden
        for preferred in ("llama3.2:3b", "llama3.2:1b", "qwen2.5:3b", "qwen2.5:1.5b",
                          "mistral:7b", "llama3.1:8b"):
            if any(preferred in n for n in names):
                return preferred
        return names[0] if names else "llama3.2:3b"
    except Exception:
        return "llama3.2:3b"

def _ollama_embedding_available() -> bool:
    """Verifica si Ollama está corriendo y tiene un modelo de embeddings."""
    try:
        import urllib.request
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=2) as r:
            data = json.loads(r.read())
        models = [m["name"] for m in data.get("models", [])]
        return any("embed" in m or "qwen3" in m or "nomic" in m for m in models)
    except Exception:
        return False


class _SimpleJSONMemory:
    """
    Memoria de respaldo cuando Ollama/Qdrant no está disponible.
    Persiste en JSON — sin embeddings, con búsqueda por palabras clave.
    """
    def __init__(self, path: str):
        self._path = path
        self._data: list[dict] = []
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
            except Exception:
                self._data = []

    def _save(self):
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._data[-500:], f, ensure_ascii=False)  # últimas 500 entradas
        except Exception:
            pass

    def add(self, text: str, role: str = "user"):
        self._data.append({"text": text, "role": role,
                           "ts": datetime.now().isoformat()})
        self._save()

    def search(self, query: str, limit: int = 5) -> str:
        if not self._data:
            return ""
        words = set(query.lower().split())
        scored = []
        for item in self._data:
            text_words = set(item["text"].lower().split())
            score = len(words & text_words)
            if score > 0:
                scored.append((score, item["text"]))
        scored.sort(reverse=True)
        if not scored:
            return ""
        hits = [t for _, t in scored[:limit]]
        return "Contexto histórico relevante:\n" + "\n".join(f"- {h}" for h in hits)


class NovaNeuroMemory:
    """
    Sistema de Memoria Neuronal para NOVA 3.0 usando mem0.
    Reemplaza al antiguo nova_memory basado estrictamente en SQLite y DB plana,
    proveyendo retención semántica y extracción automática de entidades.
    """
    
    def close(self) -> None:
        """Cierra el cliente Qdrant en el thread correcto para evitar el error SQLite cross-thread."""
        if not self.m:
            return
        try:
            vs = getattr(self.m, "vector_store", None)
            client = getattr(vs, "client", None)
            if client:
                client.close()
        except Exception:
            pass
        finally:
            self.m = None
            if self._qdrant_lock:
                try:
                    self._qdrant_lock.release()
                except Exception:
                    pass

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    def __init__(self, user_id="nova_user"):
        self.user_id = user_id
        self._simple: _SimpleJSONMemory | None = None  # fallback siempre activo
        # Cargar .env para variables como OPENROUTER_API_KEY, GROQ_API_KEY
        from dotenv import load_dotenv
        load_dotenv()

        # Inicializar memoria JSON de respaldo (siempre, independiente de Ollama)
        _simple_path = os.path.expanduser("~/.nova/memory_simple.json")
        self._simple = _SimpleJSONMemory(_simple_path)

        # Asegurar directorios
        os.makedirs(os.path.expanduser("~/.nova"), exist_ok=True)

        # Lock para evitar dos procesos Nova compitiendo por la misma base Qdrant
        self._lock_path = os.path.expanduser("~/.nova/qdrant.lock")
        try:
            import filelock
            # Limpiar lock huérfano (proceso anterior murió sin liberarlo)
            if os.path.exists(self._lock_path):
                age = time.time() - os.path.getmtime(self._lock_path)
                if age > 30:  # si tiene >30s nadie lo debería tener activo
                    try:
                        os.remove(self._lock_path)
                        log.debug("[Memoria] Lock huérfano eliminado (age=%.0fs)", age)
                    except OSError:
                        pass
            self._qdrant_lock = filelock.FileLock(self._lock_path, timeout=5)
        except ImportError:
            self._qdrant_lock = None
        
        # LLM para extracción de mem0: Groq primero (rápido y gratis), Ollama como fallback
        _groq_key = os.getenv("GROQ_API_KEY", "")
        if _groq_key and _groq_key != "gsk_...":
            _mem0_llm = {
                "provider": "groq",
                "config": {
                    "model": "llama-3.1-8b-instant",
                    "api_key": _groq_key,
                    "temperature": 0,
                    "max_tokens": 1500,
                }
            }
            log.info("[Memoria] LLM extracción: Groq / llama-3.1-8b-instant")
        else:
            _ollama_llm = _pick_ollama_memory_model()
            _mem0_llm = {
                "provider": "ollama",
                "config": {
                    "model": _ollama_llm,
                    "ollama_base_url": "http://127.0.0.1:11434",
                    "temperature": 0,
                    "max_tokens": 1500,
                }
            }
            log.info("[Memoria] LLM extracción: Ollama / %s", _ollama_llm)

        # Configurar mem0: embeddings local (Ollama), extracción LLM (Groq/Ollama)
        config = {
            "llm": _mem0_llm,
            "vector_store": {
                "provider": "qdrant",
                "config": {
                    "collection_name": "nova_memories",
                    "path": os.path.expanduser("~/.nova/qdrant_db"),
                    "embedding_model_dims": 2560
                }
            },
            "embedder": {
                "provider": "openai",
                "config": {
                    "model": "qwen3-embedding:4b",
                    "openai_base_url": "http://127.0.0.1:11434/v1",
                    "embedding_dims": 2560,
                    "api_key": "dummy"
                }
            },
            "extract_entities": False
        }
        # Solo iniciar mem0/Qdrant si Ollama está disponible con embeddings
        if not _ollama_embedding_available():
            log.warning("[Memoria] Ollama sin embeddings — usando memoria JSON simple (Nova igual aprende)")
            self.m = None
            return

        log.info("[Memoria] Config: vector_store dims=2560, embedder=openai via Ollama")

        try:
            # Dummy OPENAI_API_KEY para evitar errores del cliente openai en mem0
            if not os.getenv("OPENAI_API_KEY"):
                os.environ["OPENAI_API_KEY"] = "dummy"

            # Adquirir lock antes de abrir Qdrant embedded
            if self._qdrant_lock:
                try:
                    self._qdrant_lock.acquire()
                except Exception:
                    log.warning("[Memoria] Qdrant bloqueado — usando memoria JSON simple")
                    self.m = None
                    return

            self.m = Memory.from_config(config) if _MEM0_AVAILABLE else None
            
            if self.m:
                log.info("[Memoria] Memoria vectorial inicializada (OpenAI embedder via Ollama)")
                # Verificar dimensión de la colección
                try:
                    vs = self.m.vector_store
                    info = vs.client.get_collection(config['vector_store']['config']['collection_name'])
                    log.info("[Memoria] Colección '%s' dimensión: %s", config['vector_store']['config']['collection_name'], info.config.params.vectors.size)
                except Exception as e:
                    log.debug("[Memoria] No se pudo verificar colección: %s", e)
            if not _MEM0_AVAILABLE:
                log.warning("[Memoria] mem0 no disponible, funcionando en modo limitado")
            elif self.m is None:
                log.warning("[Memoria] Error iniciando Qdrant/Mem0 (permisos o ruta)")
                log.warning("[Memoria] Memoria Vectorial arranca en modo seguro (DESACTIVADA).")
        except Exception as e:
            log.warning("[Memoria] Error iniciando Qdrant/Mem0: %s", e)
            log.warning("[Memoria] Memoria Vectorial arranca en modo seguro (DESACTIVADA).")
            self.m = None

    def remember(self, fact: str) -> None:
        """Guarda un hecho específico forzado."""
        if not self.m: 
            log.debug("[Memoria] remember: mem no disponible")
            return
        try:
            log.debug("[Memoria] Guardando hecho: %s", fact[:50])
            embedding = self.m.embedding_model.embed(fact)
            vs = self.m.vector_store
            from qdrant_client.models import PointStruct
            point = PointStruct(
                id=str(uuid.uuid4()),
                vector=embedding,
                payload={'text': fact, 'user_id': self.user_id, 'role': 'user', 'type': 'fact'}
            )
            vs.client.upsert(collection_name=vs.collection_name, points=[point])
            log.debug("[Memoria] Hecho guardado via upsert")
        except Exception as e:
            log.warning("[Memoria] Error guardando hecho: %s", e)

    def add_interaction(self, user_message: str, assistant_response: str) -> None:
        """Extrae memoria pasivamente de una conversación."""
        if self._simple:
            self._simple.add(f"User: {user_message}", "user")
            self._simple.add(f"Nova: {assistant_response}", "assistant")
        if not self.m: return
        try:
            combined = f"User: {user_message}\nAssistant: {assistant_response}"
            embedding = self.m.embedding_model.embed(combined)
            vs = self.m.vector_store
            from qdrant_client.models import PointStruct
            point = PointStruct(
                id=str(uuid.uuid4()),
                vector=embedding,
                payload={'text': combined, 'user_id': self.user_id, 'role': 'conversation', 'type': 'interaction'}
            )
            vs.client.upsert(collection_name=vs.collection_name, points=[point])
            log.debug("[Memoria] Interacción guardada via upsert")
        except Exception as e:
            log.warning("[Memoria] No se pudo guardar la interacción: %s", e)

    def search_context(self, query: str, limit: int = 5, threshold: float = 0.3) -> str:
        """Busca contexto relevante para la query actual."""
        if not self.m:
            return self._simple.search(query, limit) if self._simple else ""
        try:
            # Generar embedding de la query
            query_emb = self.m.embedding_model.embed(query)
            # Buscar en Qdrant directamente usando query_points
            vs = self.m.vector_store
            from qdrant_client.models import SearchRequest
            # Construir request
            search_result = vs.client.query_points(
                collection_name=vs.collection_name,
                query=query_emb,
                limit=limit,
                score_threshold=threshold
            )
            hits = search_result.points if hasattr(search_result, 'points') else search_result
            if not hits:
                return ""
            context = "Contexto histórico relevante:\n"
            for hit in hits:
                text = hit.payload.get('text', str(hit.payload))
                context += f"- {text}\n"
            return context
        except Exception as e:
            log.warning("[Memoria] Error buscando contexto: %s", e)
            return ""

    def get_all_facts(self) -> str:
        """Recupera todas las memorias para exportar al Vault (Obsidian)."""
        if not self.m: return "Memoria neuronal desactivada."
        try:
            # Leer todos los puntos directamente de Qdrant
            vs = self.m.vector_store
            points = vs.client.scroll(
                collection_name=vs.collection_name,
                limit=100  # Ajustar si hay más
            )[0]
            if not points:
                return "Sin memorias registradas."
            output = "## Memorias Neuronales Extraídas (Mem0)\n\n"
            for p in points:
                text = p.payload.get('text', str(p.payload))
                output += f"- {text}\n"
            return output
        except Exception as e:
            return f"Error recuperando memorias: {e}"

    # Métodos adicionales para compatibilidad con novaesp.py
    _TRIVIAL = {"ok", "sí", "si", "no", "gracias", "bueno", "bien", "dale",
                "claro", "listo", "perfecto", "entendido", "ya", "genial"}

    def save_turn(self, role: str, content: str) -> None:
        """Guarda un turno de conversación usando upsert directo (sin pipeline LLM de mem0)."""
        stripped = content.strip()
        if len(stripped) < 15 or stripped.lower().rstrip(".,!?") in self._TRIVIAL:
            log.debug("[Memoria] Turno trivial omitido: %r", stripped[:30])
            return
        if self._simple:
            self._simple.add(content, role)
        if not self.m: return
        try:
            # Upsert directo: evita que mem0 llame al LLM con miles de tokens
            embedding = self.m.embedding_model.embed(content[:2000])
            vs = self.m.vector_store
            from qdrant_client.models import PointStruct
            point = PointStruct(
                id=str(uuid.uuid4()),
                vector=embedding,
                payload={'text': content[:2000], 'user_id': self.user_id,
                         'role': role, 'type': 'turn'}
            )
            vs.client.upsert(collection_name=vs.collection_name, points=[point])
            log.debug("[Memoria] Turno '%s' guardado via upsert", role)
        except Exception as e:
            msg = str(e)
            if "SQLite" in msg and "thread" in msg:
                # mem0 abre SQLite en el hilo principal; deshabilitar para hilos background
                log.debug("[Memoria] mem0 deshabilitado en hilo background (SQLite thread-unsafe) — _simple activo")
                self.m = None
            else:
                log.warning("[Memoria] Error guardando turno: %s", e)

    def get_recent_turns(self, limit: int = 20) -> list[dict]:
        """Devuelve los últimos N turnos en formato Chat API."""
        if not self.m: return []
        try:
            vs = self.m.vector_store
            # Obtener todos los puntos ordenados por ID (más reciente)
            points = vs.client.scroll(
                collection_name=vs.collection_name,
                limit=1000  # Traer muchos y luego cortar
            )[0]
            if not points:
                return []
            # Ordenar por ID (asumiendo que crece)
            points.sort(key=lambda p: p.id)
            # Tomar los últimos 'limit'
            recent = points[-limit:]
            turns = []
            for p in recent:
                text = p.payload.get('text', '')
                if text:
                    # Intentar extraer role del payload
                    role = p.payload.get('role', 'user')
                    turns.append({"role": role, "content": text})
            return turns
        except Exception as e:
            log.warning("[Memoria] Error obteniendo turns recientes: %s", e)
            return []

# Singleton instance — protected from KeyboardInterrupt during slow qdrant/Pydantic init.
try:
    neuro_memory = NovaNeuroMemory()
except BaseException as _e:
    log.warning("[Memoria] Init interrumpida (%s) — usando memoria JSON simple.", type(_e).__name__)
    _nm = object.__new__(NovaNeuroMemory)
    _nm.user_id = "nova_user"
    _nm.m = None
    _nm._qdrant_lock = None
    _nm._simple = _SimpleJSONMemory(os.path.expanduser("~/.nova/memory_simple.json"))
    neuro_memory = _nm
