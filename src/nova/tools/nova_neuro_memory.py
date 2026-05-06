import os
import json
import uuid
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

class NovaNeuroMemory:
    """
    Sistema de Memoria Neuronal para NOVA 3.0 usando mem0.
    Reemplaza al antiguo nova_memory basado estrictamente en SQLite y DB plana,
    proveyendo retención semántica y extracción automática de entidades.
    """
    
    def __init__(self, user_id="nova_user"):
        self.user_id = user_id
        # Cargar .env para variables como OPENROUTER_API_KEY, GROQ_API_KEY
        from dotenv import load_dotenv
        load_dotenv()

        # Asegurar directorios
        os.makedirs(os.path.expanduser("__DOTNOVA_PATH__"), exist_ok=True)

        # Lock para evitar dos procesos Nova compitiendo por la misma base Qdrant
        self._lock_path = os.path.expanduser("__DOTNOVA_PATH__/qdrant.lock")
        try:
            import filelock
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
            print("[Memoria] LLM extracción: Groq / llama-3.1-8b-instant")
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
            print(f"[Memoria] LLM extracción: Ollama / {_ollama_llm}")

        # Configurar mem0: embeddings local (Ollama), extracción LLM (Groq/Ollama)
        config = {
            "llm": _mem0_llm,
            "vector_store": {
                "provider": "qdrant",
                "config": {
                    "collection_name": "nova_memories",
                    "path": os.path.expanduser("__DOTNOVA_PATH__/qdrant_db"),
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
        print("[Memoria] Config: vector_store[embedding_model_dims=2560], embedder=openai via Ollama...")
        
        try:
            # Dummy OPENAI_API_KEY para evitar errores del cliente openai en mem0
            if not os.getenv("OPENAI_API_KEY"):
                os.environ["OPENAI_API_KEY"] = "dummy"

            # Adquirir lock antes de abrir Qdrant embedded
            if self._qdrant_lock:
                try:
                    self._qdrant_lock.acquire()
                except Exception:
                    print("⚠️ [Memoria] Otra instancia de Nova tiene Qdrant bloqueado — memoria desactivada.")
                    self.m = None
                    return

            self.m = Memory.from_config(config) if _MEM0_AVAILABLE else None
            
            if self.m:
                print("[Memoria] Memoria vectorial inicializada (OpenAI embedder via Ollama)")
                # Verificar dimensión de la colección
                try:
                    vs = self.m.vector_store
                    info = vs.client.get_collection(config['vector_store']['config']['collection_name'])
                    print(f"[Memoria] Colección '{config['vector_store']['config']['collection_name']}' dimensión: {info.config.params.vectors.size}")
                except Exception as e:
                    print(f"[Memoria] No se pudo verificar colección: {e}")
            if not _MEM0_AVAILABLE:
                print("[Memoria] mem0 no disponible, funcionando en modo limitado")
            elif self.m is None:
                print("⚠️ [Memoria] Error iniciando Qdrant/Mem0 (posible problema de permisos o ruta)")
                print("⚠️ [Memoria] Memoria Vectorial arranca en modo seguro (DESACTIVADA).")
        except Exception as e:
            log.warning("[Memoria] Error iniciando Qdrant/Mem0: %s", e)
            print("⚠️ [Memoria] Memoria Vectorial arranca en modo seguro (DESACTIVADA).")
            self.m = None

    def remember(self, fact: str) -> None:
        """Guarda un hecho específico forzado."""
        if not self.m: 
            print("[Memoria] remember: mem no disponible")
            return
        try:
            print(f"[Memoria] Guardando hecho: {fact[:50]}...")
            embedding = self.m.embedding_model.embed(fact)
            vs = self.m.vector_store
            from qdrant_client.models import PointStruct
            point = PointStruct(
                id=str(uuid.uuid4()),
                vector=embedding,
                payload={'text': fact, 'user_id': self.user_id, 'role': 'user', 'type': 'fact'}
            )
            vs.client.upsert(collection_name=vs.collection_name, points=[point])
            print("[Memoria] Hecho guardado via upsert")
        except Exception as e:
            log.warning("[Memoria] Error guardando hecho: %s", e)

    def add_interaction(self, user_message: str, assistant_response: str) -> None:
        """Extrae memoria pasivamente de una conversación."""
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
            print("[Memoria] Interacción guardada via upsert")
        except Exception as e:
            print(f"⚠️ [Memoria] No se pudo guardar la interacción: {e}")

    def search_context(self, query: str, limit: int = 5, threshold: float = 0.3) -> str:
        """Busca contexto relevante para la query actual."""
        if not self.m: return ""
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
    def save_turn(self, role: str, content: str) -> None:
        """Guarda un turno de conversación."""
        if not self.m: return
        try:
            messages = [
                {"role": role, "content": content},
            ]
            self.m.add(messages, user_id=self.user_id)
        except Exception as e:
            print(f"[Memoria] Error guardando turno: {e}")

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
            print(f"[Memoria] Error obteniendo turns recientes: {e}")
            return []

# Singleton instance
neuro_memory = NovaNeuroMemory()
