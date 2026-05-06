# Arquitectura de Memoria — NOVA Personal Assistant

## 🧠 Visión General

Nova tiene un **sistema de memoria híbrida** que combina almacenamiento local rápido con el **Gran Cerebro** centralizado en Obsidian.

```
┌─────────────────────────────────────────────────────────────────┐
│                        NOVA                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐ │
│  │  SQLite      │  │  Router      │  │  Skills              │ │
│  │  __DOTNOVA_PATH__/  │  │  nova_      │  │  nova_skills.py    │ │
│  │  memory.db   │  │  router.py   │  │                      │ │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬───────────┘ │
│         │                  │                     │             │
│         │                  ▼                     │             │
│         │         ┌──────────────────┐            │             │
│         │         │  ModelStats      │            │             │
│         │         │  model_stats.json│            │             │
│         │         └────────┬─────────┘            │             │
│         │                  │                     │             │
│         └──────────────────┼─────────────────────┘             │
│                            │                                   │
└────────────────────────────┼───────────────────────────────────┘
                             │
                             ▼ REST API
┌─────────────────────────────────────────────────────────────────┐
│                     OBSIDIAN VAULT                               │
│                  ~/Cerebro/ (Gran Cerebro)                      │
│                                                                  │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐              │
│  │  NOVA/     │ │  Claude/     │ │  Stats/      │              │
│  │  Memoria/    │ │  memoria/    │ │  model_stats │              │
│  │  facts.md    │ │  MEMORY.md   │ │  .json       │              │
│  │  Briefing.md │ │              │ │              │              │
│  └──────────────┘ └──────────────┘ └──────────────┘              │
│                                                                  │
│  ┌──────────────────────────────────────────────────────┐        │
│  │  Diario/  ─ Notas diarias de voz                     │        │
│  │  Drops/   ─ Exports manuales de otras IAs            │        │
│  │  Proyectos/ ─ Código, docs, contexto compartido      │        │
│  └──────────────────────────────────────────────────────┘        │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📁 Capas de Memoria

### 1. **SQLite Local** (`__DOTNOVA_PATH__/memory.db`)

Almacenamiento rápido, acceso instantáneo.

**Tablas:**
- `facts` → Hechos sobre el usuario (clave-valor)
- `conversations` → Historial de conversaciones

**Uso:**
```python
import nova_memory as mem

# Guardar
mem.remember("prefiere_voz", "masculina")

# Recuperar
mem.recall("voz")

# Diario
diary_append("Reunión con equipo a las 10am")
```

---

### 2. **Gran Cerebro** (Obsidian Vault)

Memoria compartida entre todas las IAs del sistema.

**Sincronización automática:**
- ✅ Facts → `NOVA/Memoria/facts.md`
- ✅ Stats de modelos → `Stats/model_stats.json`
- ✅ Entradas de diario → `Diario/YYYY-MM-DD.md`

**Contexto cargado al arrancar:**
Nova carga automáticamente:
1. `NOVA/Briefing.md` → Proyectos activos
2. `NOVA/Memoria/facts.md` → Datos del usuario
3. `Claude/memoria/MEMORY.md` → Memorias de Claude Code

Esto enriquece el system prompt con contexto de TODO el ecosistema.

---

### 3. **Model Stats** (Estadísticas de Router)

Guarda el rendimiento de cada modelo/proveedor.

**Almacenamiento dual:**
- Local: `model_stats.json` (rápido)
- Vault: `~/Cerebro/Stats/model_stats.json` (compartido)

**Datos guardados:**
```json
{
  "qwen2.5:7b": {
    "success": 45,
    "fail": 2,
    "avg_latency": 1.2,
    "last_fail": 1699999999
  },
  "groq/llama-3.3-70b": {
    "success": 120,
    "fail": 0,
    "avg_latency": 0.8,
    "last_fail": 0
  }
}
```

**Uso:** El router ordena modelos por score (éxito/latencia/fallos).

---

## 🔄 Flujo de Datos

### Al Guardar un Fact
```
Usuario: "Recordá que prefiero dark mode"

Nova → nova_memory.remember("prefiere_tema", "dark")
     → SQLite (facts table)
     → Obsidian REST API → NOVA/Memoria/facts.md
```

### Al Arrancar Nova
```
Nova → nova_memory.load_vault_context()
     → Lee NOVA/Briefing.md
     → Lee NOVA/Memoria/facts.md
     → Lee Claude/memoria/MEMORY.md
     → Concatena al system_prompt del router
```

### Al Usar un Modelo
```
Nova → router.route(messages)
     → ModelStatsTracker.score(model)
     → Ordena intentos por score
     → Ejecuta llamada
     → Si éxito: record_success(latencia)
     → Si fallo: record_fail()
     → Guarda en JSON local + Vault/Stats/
```

---

## 🗂️ Estructura del Vault

```
~/Cerebro/
├── NOVA/
│   ├── Briefing.md           ← Índice de proyectos + memoria
│   └── Memoria/
│       └── facts.md          ← Tabla de hechos
├── Claude/
│   └── memoria/
│       └── MEMORY.md         ← Índice de memorias Claude Code
├── OpenClaw/
│   └── memoria/              ← Memorias de OpenClaw
├── Stats/
│   └── model_stats.json      ← Estadísticas de modelos
├── Diario/
│   └── 2024-01-15.md         ← Notas diarias de voz
└── Drops/
    └── export_claude.json    ← Exports manuales de otras IAs
```

---

## 🔧 Configuración

### Requisitos
```bash
# 1. Obsidian con plugin REST API instalado
#    https://github.com/coddingtonbear/obsidian-local-rest-api

# 2. Variables en .env
OBSIDIAN_BASE_URL=https://127.0.0.1:27124
OBSIDIAN_API_KEY=tu_api_key_aqui
```

### Verificar conexión
```bash
python3 -c "
import nova_memory as mem
ctx = mem.load_vault_context()
print(f'Contexto cargado: {len(ctx)} chars' if ctx else 'Vault no disponible')
"
```

---

## 📋 Sincronización Manual

Si necesitas forzar sync:

```bash
# Sync todo el cerebro
python3 sync_cerebro.py

# Solo archivos nuevos/modificados
python3 sync_cerebro.py --fast

# Preview sin subir
python3 sync_cerebro.py --dry-run
```

---

## 💡 Ventajas de Esta Arquitectura

| Aspecto | SQLite Local | Obsidian Vault |
|---------|--------------|----------------|
| **Velocidad** | ⚡ Instantáneo | 🌐 REST API (ms) |
| **Persistencia** | 💾 Solo local | ☁️ Backup + sync |
| **Compartido** | ❌ Solo Nova | ✅ Todas las IAs |
| **Búsqueda** | SQL básico | 🔍 Full-text Obsidian |
| **Visibilidad** | Archivo binario | 📖 Markdown legible |

**Mejor de ambos mundos:**
- Velocidad local para operaciones frecuentes
- Compartido/visible para memoria importante
- Backup automático vía Obsidian sync

---

## 🚀 Comandos de Voz Relacionados

| Comando | Acción |
|---------|--------|
| "Nova, recordá que..." | Guarda un fact |
| "Nova, ¿qué sabés sobre...?" | Busca en memoria |
| "Nova, sincroniza el cerebro" | Ejecuta sync_cerebro.py |
| "Nova, olvidá [clave]" | Elimina un fact |

---

## 🔍 Troubleshooting

### "Vault no disponible"
```bash
# Verificar que Obsidian está abierto
curl https://127.0.0.1:27124/ -k

# Verificar API key
grep OBSIDIAN_API_KEY .env
```

### Stats no se sincronizan
```bash
# Verificar carpeta Stats existe
ls -la ~/Cerebro/Stats/

# Crear si no existe
mkdir -p ~/Cerebro/Stats
```

### Duplicados en facts
```bash
# Limpiar duplicados (SQLite)
sqlite3 __DOTNOVA_PATH__/memory.db "DELETE FROM facts WHERE rowid NOT IN (SELECT MIN(rowid) FROM facts GROUP BY key);"
```
