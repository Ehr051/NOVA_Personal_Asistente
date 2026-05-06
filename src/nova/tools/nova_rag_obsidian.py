import os
try:
    from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, StorageContext, Settings
    from llama_index.vector_stores.qdrant import QdrantVectorStore
    import qdrant_client
    _LLAMA_INDEX_AVAILABLE = True
except ImportError as e:
    print(f"[RAG Obsidian] llama-index import error: {e}")
    _LLAMA_INDEX_AVAILABLE = False
    # Create dummy classes for when llama_index is not available
    class VectorStoreIndex:
        pass
    class SimpleDirectoryReader:
        pass
    class StorageContext:
        pass
    class Settings:
        pass
    class QdrantVectorStore:
        pass
    class qdrant_client:
        class QdrantClient:
            pass

class NovaRAGObsidian:
    def __init__(self, vault_path="~/Cerebro"):
        """
        Indexador Vectorial para Obsidian.
        Lee todos los .md, los convierte en embeddings locales y permite consultarlos.
        """
        if not _LLAMA_INDEX_AVAILABLE:
            print("[RAG Obsidian] llama-index no disponible, funcionando en modo limitado")
            self.vault_path = os.path.expanduser(vault_path)
            self.index = None
            return
            
        self.vault_path = os.path.expanduser(vault_path)
        
        try:
            # Configurar LlamaIndex para no usar OpenAI (100% Privado / Local)
            # Usar una aproximación más segura para establecer el modelo embed
            Settings.embed_model = "local"
            
            # Configurar cliente local de Qdrant
            self.qdrant_path = os.path.expanduser("~/Cerebro/Qdrant")
            os.makedirs(self.qdrant_path, exist_ok=True)
            self.client = qdrant_client.QdrantClient(path=self.qdrant_path)
            self.vector_store = QdrantVectorStore(client=self.client, collection_name="obsidian_vault")
            self.storage_context = StorageContext.from_defaults(vector_store=self.vector_store)
            
            self.index = None
            self._load_or_index()
        except Exception as e:
            print(f"[RAG Obsidian] Error initializing RAG components: {e}")
            print("[RAG Obsidian] Funcionando en modo limitado sin indexing vectorial")
            self.index = None

    def _load_or_index(self):
        """Carga el index existente o indexa desde cero si no existe."""
        if not self.index:  # Already determined to be None in limited mode
            return
            
        # TODO: Implement persistence check properly for llama-index
        # For now we will check if the collection has points.
        collection_info = None
        try:
            collection_info = self.client.get_collection("obsidian_vault")
        except Exception:
            pass

        if collection_info and collection_info.points_count > 0:
            print("[Nova RAG] Cargando índice existente de Obsidian...")
            try:
                self.index = VectorStoreIndex.from_vector_store(
                    vector_store=self.vector_store
                )
            except Exception as e:
                print(f"[RAG Obsidian] Error loading index: {e}")
                self.index = None
        else:
            self.refresh_index()

    def refresh_index(self):
        """Lee el directorio completo de Obsidian y reconstruye el índice."""
        if not _LLAMA_INDEX_AVAILABLE or not self.index:
            print("[Nova RAG] Indexación no disponible en modo limitado")
            return
            
        print(f"[Nova RAG] Indexando bóveda en: {self.vault_path}... Esto puede tardar.")
        try:
            # Requerido_exts asegura que solo leamos texto y evitemos multimedia
            documents = SimpleDirectoryReader(
                self.vault_path, 
                required_exts=[".md", ".txt", ".json", ".csv"],
                recursive=True
            ).load_data()
            
            # Intentar configurar el modelo de embeddings de forma más explícita
            try:
                from llama_index.embeddings.huggingface import HuggingFaceEmbedding
                Settings.embed_model = HuggingFaceEmbedding(
                    model_name="sentence-transformers/all-MiniLM-L6-v2"
                )
            except Exception as e:
                print(f"[RAG Obsidian] No se pudo configurar embeddings HuggingFace: {e}")
                # Continuar con la configuración por defecto
            
            self.index = VectorStoreIndex.from_documents(
                documents, 
                storage_context=self.storage_context
            )
            print(f"[Nova RAG] ✓ Indexación completada. {len(documents)} fragmentos leídos.")
        except Exception as e:
            print(f"[Nova RAG] Error al indexar: {e}")
            self.index = None

    def query(self, question: str) -> str:
        """Busca en Obsidian la respuesta exacta a una pregunta militar/documental."""
        if not self.index:
            return "El índice RAG no está listo."
             
        print(f"[Nova RAG] Investigando en Obsidian: '{question}'...")
        try:
            query_engine = self.index.as_query_engine(
                similarity_top_k=3  # Trae los 3 párrafos más relevantes
            )
            response = query_engine.query(question)
            return str(response)
        except Exception as e:
            print(f"[RAG Obsidian] Error durante la consulta: {e}")
            return "Error al procesar la consulta en el índice RAG."

# Pruebas manuales
if __name__ == "__main__":
    rag = NovaRAGObsidian()
    print("\nRespuesta Nova:", rag.query("Resume el último archivo militar o briefing disponible."))
