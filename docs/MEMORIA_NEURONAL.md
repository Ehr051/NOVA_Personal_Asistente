# Sistema de Memoria Neuronal de Nova (NovaNeuroMemory)

## 📖 Visión General

NovaNeuroMemory es el sistema de memoria persistente y semántica de Nova. Reemplaza la antigua memoria basada solo en SQLite por un sistema vectorial que permite:

- **Almacenamiento semántico**: Guarda información basada en significado, no solo palabras clave
- **Búsqueda por similitud**: Encuentra recuerdos relacionados aunque no usemos las mismas palabras
- **Contexto conversacional**: Mantiene el hilo de la conversación entre turnos
- **Persistencia entre sesiones**: La memoria sobrevive a reinicios del sistema

## 🏗️ Arquitectura

```
NovaNeuroMemory
├── Mem0 (framework) → orquesta embeddings + vector store
├── Embedder: Ollama (qwen3-embedding:4b) → genera vectores de 2560 dimensiones
├── Vector Store: Qdrant → almacena y busca vectores
└── Collection: "nova_memories" → tabla donde se guardan los recuerdos
```

### Componentes

1. **Mem0** (`Memory` object): Framework de memoria que gestiona:
   - Extracción de entidades (opcional, desactivado)
   - Filtrado por `user_id` (aislamiento entre usuarios)
   - API simple: `add()`, `search()`, `get_all()`

2. **Embedder** (`embedding_model`): Convierte texto en vectores
   - Proveedor: **OpenAI-compatible** via `openai` provider
   - Backend: **Ollama** local (`http://127.0.0.1:11434/v1`)
   - Modelo: `qwen3-embedding:4b`
   - Dimensión: **2560** (optimizado para idioma español)
   - Gratis, local, sin dependencia de APIs externas de pago

3. **Vector Store** (`vector_store`): Base de datos vectorial
   - Proveedor: **Qdrant** (modo local, archivos en disco)
   - Colección: `nova_memories`
   - Path: `__DOTNOVA_PATH__/qdrant_db`
   - Dimensión: 2560 (coincide con el embedder)
   - Almacenamiento persistente en disco

4. **Configuración de mem0**:
   ```python
   config = {
       "vector_store": {
           "provider": "qdrant",
           "config": {
               "collection_name": "nova_memories",
               "path": "__DOTNOVA_PATH__/qdrant_db",
               "embedding_model_dims": 2560  ← CRÍTICO: debe coincidir con el embedder
           }
       },
       "embedder": {
           "provider": "openai",  ← usa API OpenAI-compatible (Ollama)
           "config": {
               "model": "qwen3-embedding:4b",
               "openai_base_url": "http://127.0.0.1:11434/v1",
               "embedding_dims": 2560,
               "api_key": "dummy"  ← no se usa, pero mem0 lo requiere
           }
       },
       "extract_entities": False  ← desactivado para no necesitar LLM adicional
   }
   ```

## 🔄 Flujo de Funcionamiento

### 1. Inicialización (`__init__`)

```python
neuro_memory = NovaNeuroMemory(user_id="nova_user")
```

Pasos:
1. Carga `.env` (variables como `OPENROUTER_API_KEY`, `OLLAMA_BASE_URL`)
2. Crea `config` (ver arriba)
3. Llama a `Memory.from_config(config)` → inicializa mem0
4. **Verifica dimensión de colección Qdrant**:
   - Si es 1536 (default incorrecto), la borra y crea nueva con 2560
   - Reemplaza `vector_store` de mem0 con uno nuevo que tenga `embedding_model_dims=2560`
5. Imprime estado: "Memoria vectorial inicializada (OpenAI embedder via Ollama)"

### 2. Guardar Recuerdos

Hay dos formas:

#### A. `remember(fact: str)` → Guarda un **hecho específico** (ej: "Me gusta programar en Python")

```python
neuro_memory.remember("Me gusta programar en Python")
```

Proceso:
1. Genera embedding con `self.m.embedding_model.embed(fact)`
2. Crea un `PointStruct` con:
   - `id`: UUID generado
   - `vector`: embedding de 2560 floats
   - `payload`: `{'text': fact, 'user_id': ..., 'role': 'user', 'type': 'fact'}`
3. Inserta via `vs.client.upsert(collection_name, points=[point])`
4. El punto queda en Qdrant persistente

#### B. `add_interaction(user_msg, assistant_resp)` → Guarda un **intercambio conversacional**

```python
neuro_memory.add_interaction("Hola NOVA", "Hola! ¿En qué puedo ayudarte?")
```

Proceso similar, pero payload incluye:
```python
{
  'text': "User: Hola NOVA\nAssistant: Hola! ¿En qué puedo ayudarte?",
  'role': 'conversation',
  'type': 'interaction'
}
```

### 3. Recuperar Recuerdos

#### `get_all_facts()` → Todos los recuerdos (para exportar a Obsidian)

```python
facts = neuro_memory.get_all_facts()
```

 Implementación:
1. Hace `vs.client.scroll(collection_name, limit=100)` → obtiene todos los puntos
2. Construye string markdown:
   ```
   ## Memorias Neuronales Extraídas (Mem0)

   - User: Hola NOVA
   Assistant: Hola! ...
   - Me gusta programar en Python
   ...
   ```
3. Retorna ese texto (luego `obsidian_anota("Briefing", facts)` lo guarda en Obsidian)

#### `search_context(query)` → Búsqueda semántica

```python
ctx = neuro_memory.search_context("programación")
```

Proceso:
1. Genera embedding de la query: `query_emb = self.m.embedding_model.embed(query)`
2. Busca en Qdrant: `vs.client.query_points(collection_name, query=query_emb, limit=5, score_threshold=0.3)`
3. Retorna los `payload['text']` de los puntos más similares (cosine similarity)
4. Formato:
   ```
   Contexto histórico relevante:
   - Me gusta programar en Python
   - ...
   ```

Esta salida se inyecta como **contexto histórico** en el prompt del LLM (NovaRouter) para que Nova "recuerde" conversaciones pasadas.

#### `get_recent_turns(limit=20)` → Últimos turnos en formato Chat API

```python
turns = neuro_memory.get_recent_turns(10)
# [{'role': 'conversation', 'content': '...'}, {'role': 'user', 'content': '...'}, ...]
```

Usado por el HUD (`novaesp.py`) para mantener el contexto conversacional reciente en la interfaz.

## 🔍 ¿Por Qué `openai` Provider en Lugar de `ollama`?

El proveedor `ollama` de mem0 inicializa el embedder con dimensión **1536** (default) y no detecta correctamente los 2560 de `qwen3-embedding:4b`. El proveedor `openai` (que habla HTTP API OpenAI-compatible) permite:

1. Pasar `embedding_dims` explícitamente → fuerza a 2560
2. Usar `openai_base_url` para apuntar a Ollama: `http://127.0.0.1:11434/v1`
3. La API de embeddings de Ollama es compatible con OpenAI: POST `/v1/embeddings` con JSON `{model, input}`

Así, mem0 piensa que está usando OpenAI, pero en realidad usa Ollama local (gratis).

## 🧠 Integración con Nova

### En el HUD (`novaesp.py`)

Cada vez que el usuario habla y Nova responde:
```python
# Después de generar respuesta del asistente
neuro_memory.add_interaction(user_text, assistant_text)
```
Esto guarda la conversación en Qdrant para contexto futuro.

Antes de procesar cada comando:
```python
context = neuro_memory.search_context(user_text)
# context = "Contexto histórico relevante:\n- ..."
# Se inyecta en el system prompt del LLM
```

### En el Morning Digest Agent

El agente matutino incluye memorias recientes en la sección de recordatorios:
```python
from nova.tools.nova_neuro_memory import neuro_memory
reminders = neuro_memory.search_context("recordatorio hoy")
```

Y **guarda el briefing completo en Obsidian** automáticamente al ejecutarse:
```python
obsidian_nota_nueva(f"Briefing {fecha}: {contenido_del_briefing}")
```
Crea una nota en la carpeta `Nova/Briefings` del vault de Obsidian.

### En la CLI (`nova`)

Skills disponibles:
```bash
nova skill remember "hecho importante"   # Guarda en memoria neuronal
nova skill recall "tema"                 # Busca en memoria semántica
nova skill export_obsidian               # Exporta todas las memorias a Obsidian
```

## 📁 Estructura de Datos en Qdrant

Cada punto en la colección `nova_memories`:

```json
{
  "id": "uuid-v4-string",
  "vector": [2560 floats],  // embedding generado por qwen3-embedding:4b via Ollama
  "payload": {
    "text": "User: ...\nAssistant: ...",  // texto original de la interacción o hecho
    "user_id": "nova_user",               // aislamiento multi-usuario (futuro)
    "role": "conversation" | "user",      // tipo de turno
    "type": "interaction" | "fact"        // conversación o hecho suelto
  }
}
```

## 🔄 Flujo Completo: De la Voz a la Memoria

1. **Usuario**: "Nova, recuerda que me gusta programar en Python"
2. **STT**: Audio → texto
3. **Router**: Detecta intento `skill_remember`
4. **Skill `remember`**: 
   - Llama a `neuro_memory.remember("Me gusta programar en Python")`
   - Genera embedding (2560 dims)
   - Inserta en Qdrant con payload
5. **Respuesta**: "Anotado, Señor"
6. **Persistencia**: El punto queda en disco (`__DOTNOVA_PATH__/qdrant_db`)

Más tarde:
1. **Usuario**: "Nova, ¿qué lenguajes me gustan?"
2. **Router**: Busca contexto: `neuro_memory.search_context("lenguajes")`
3. **Búsqueda semántica**: Embedding de "lenguajes" → Qdrant encuentra "Python" por similitud
4. **Contexto inyectado**: "Contexto histórico relevante:\n- Me gusta programar en Python"
5. **LLM** (OpenRouter/Groq): Usa ese contexto para responder: "Señor, según lo que recuerdo, le gusta Python"
6. **Respuesta hablada**: TTS

## 🗃️ Segundo Cerebro: Obsidian

Obsidian es la **memoria a largo plazo** y base de conocimiento estructurado de Nova.

### Por qué dos memorias?

| Memoria Neuronal (Qdrant) | Obsidian (Vault) |
|---------------------------|------------------|
| Contexto conversacional reciente (turnos) | Conocimiento permanente y estructurado |
| Búsqueda semántica por similitud | Notas organizadas en carpetas y tags |
| Persistencia corto-medio plazo | Archivo histórico de alto valor |
| No estructurado (texto plano) | Markdown con enlaces, formato, metadatos |
| Acceso via API (programa) | Accesible por humano (editor) y API REST |

### Cómo se sincronizan?

1. **Exportación manual**:
   ```bash
   nova skill export_obsidian   # Vuelca toda la memoria neuronal a una nota en Obsidian
   ```

2. **Briefing matutino**:
   Cada mañana, `morning_digest` crea automáticamente una nota:
   ```
   Nova/Briefings/Briefing 2026-05-02.md
   ```
   Contiene: clima, hora, noticias, recordatorios (extraídos de la memoria neuronal).

3. **Comandos de voz**:
   - "Nova, crea una nota llamada 'Ideas proyecto'" → `obsidian_nota_nueva`
   - "Nova, léeme la nota 'Reunión con Juan'" → `obsidian_lee_nota`

### Configuración del Vault

Obsidian debe tener instalado el plugin **"Obsidian Local REST API"** y configurado:

- **URL base**: `https://127.0.0.1:27124` (por defecto)
- **API Key**: se guarda en `__DOTNOVA_PATH__/obsidian.json`
- **Vault name**: el nombre del vault abierto en Obsidian

Nova usa la API REST para:
- `POST /vault/note` → crear nota
- `GET /vault/note` → leer nota

## ⚙️ Solución de Problemas

Ver sección completa en [ARQUITECTURA_MEMORIA.md](ARQUITECTURA_MEMORIA.md) (documentación técnica detallada).

## 🚀 Futuro

- Memoria **multi-usuario** (cada usuario tiene su `user_id` en Qdrant)
- **Forgetting** automático: borrar recuerdos antiguos o irrelevantes
- **Compresión** de memorias: resumir conversaciones largas
- **Indexado híbrido**: combinar búsqueda semántica (Qdrant) con keyword (BM25)
- **Backup automático** a Obsidian semanal
