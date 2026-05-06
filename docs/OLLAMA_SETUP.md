# Ollama + Nova — Guía de Configuración

## ¿Qué es Ollama?

Ollama te permite ejecutar **modelos de IA localmente** en tu Mac. Es 100% privado, gratuito y funciona sin internet una vez descargados los modelos.

**Ventajas para Nova:**
- 🚀 **Sin latencia** — respuestas instantáneas
- 🔒 **100% privado** — tus datos nunca salen de tu Mac
- 💰 **Gratuito** — sin límites de uso
- 🛠️ **Coding local** — código sensible no va a la nube

---

## Instalación

```bash
# Instalar Ollama (copia y pega en Terminal)
curl -fsSL https://ollama.com/install.sh | sh

# Iniciar el servicio
ollama serve
```

O descarga la app desde: https://ollama.com/download

---

## Modelos Recomendados para Nova

Para tu setup (16GB RAM, 4 cores), estos son los mejores:

### 🎯 Esenciales (instala primero)
```bash
# Rápido para comandos y saludos (~600MB)
ollama pull llama3.2:1b

# Coding y tareas generales excelente (~4.7GB)
ollama pull qwen2.5:7b

# Alternativa ligera buena para código (~2GB)
ollama pull qwen2.5-coder:1.5b
```

### 🧠 Opcionales (más pesados)
```bash
# Máxima calidad para análisis complejo (~9GB)
ollama pull qwen2.5:14b

# Coding especializado avanzado (~4GB)
ollama pull deepseek-coder:6.7b

# Visión — para analizar imágenes (~4GB)
ollama pull llava:7b

# Visión ultra ligera (~800MB)
ollama pull moondream:2b
```

### 📊 Resumen por uso
| Uso | Modelo | Tamaño | Comando |
|-----|--------|--------|---------|
| Saludos/comandos | llama3.2:1b | 600MB | `ollama pull llama3.2:1b` |
| Coding general | qwen2.5:7b | 4.7GB | `ollama pull qwen2.5:7b` |
| Análisis complejo | qwen2.5:14b | 9GB | `ollama pull qwen2.5:14b` |
| Ver/analizar imágenes | llava:7b | 4GB | `ollama pull llava:7b` |
| Visión rápida | moondream:2b | 800MB | `ollama pull moondream:2b` |

---

## Configuración de Nova con Ollama

### 1. Asegúrate de que Ollama esté corriendo
```bash
ollama serve
```

### 2. Configura Nova para usar Ollama primero

Edita tu `.env`:
```env
# Ollama primero, luego los demás
ROUTER_PROVIDER_ORDER=ollama,groq,openrouter,openclaw

# URL de Ollama (default)
OLLAMA_BASE_URL=http://127.0.0.1:11434/v1
```

### 3. Nova detectará automáticamente los modelos instalados

Al iniciar, verás algo como:
```
[Router] Ollama detectado con 4 modelos
[Router] Proveedores activos: Ollama + Groq + OpenRouter
[Router] Orden de fallback: ollama, groq, openrouter, openclaw
```

---

## Comandos Útiles de Ollama

```bash
# Ver modelos instalados
ollama list

# Ejecutar un modelo en chat interactivo
ollama run qwen2.5:7b

# Eliminar un modelo
ollama rm llama3.2:1b

# Actualizar un modelo
ollama pull qwen2.5:7b

# Ver información del sistema
ollama ps

# Detener el servicio
ollama stop
```

---

## Uso Avanzado: Visión con Nova

Para analizar imágenes, usa modelos de visión:

```python
# En Python con el router
result = router.vision_query(
    prompt="¿Qué ves en esta imagen?",
    image_path="/ruta/a/captura.png",
    tier=3
)
```

Requiere tener instalado:
```bash
ollama pull llava:7b
# o
ollama pull moondream:2b
```

---

## Troubleshooting

### "Ollama no detectado"
```bash
# Verificar que el servicio está corriendo
curl http://localhost:11434/api/tags

# Si no responde, iniciar:
ollama serve
```

### "El modelo es muy lento"
- Con 16GB RAM, no uses modelos > 14B params mientras corres otros programas
- Cierra apps pesadas (Chrome con muchas tabs, etc.)

### "Sin memoria RAM"
```bash
# Ver qué modelos están cargados (ocupan RAM)
ollama ps

# Descargar modelos más pequeños
ollama pull llama3.2:1b  # en lugar de 7b
```

### Nova no usa Ollama
Revisa el orden en `.env`:
```env
ROUTER_PROVIDER_ORDER=ollama,groq,openrouter
```

---

## Comparativa: Ollama vs Nube

| Característica | Ollama (Local) | Groq/OpenRouter |
|---------------|----------------|-----------------|
| **Privacidad** | ✅ 100% local | ⚠️ Va a la nube |
| **Velocidad** | ⚡ Inmediata | ⚡ Muy rápida |
| **Costo** | ✅ Gratis | ✅ Gratis (con límites) |
| **Calidad** | 🟢 Buena | 🟢🟢 Muy buena |
| **Sin internet** | ✅ Funciona | ❌ Requiere conexión |
| **Modelos** | Limitados | 100+ modelos |

**Recomendación:** Usa Ollama para tareas rápidas y código sensible, nube para análisis complejos.

---

## Scripts Útiles

Crea un script para iniciar todo junto:

```bash
#!/bin/bash
# start_nova.sh

echo "🦙 Iniciando Ollama..."
ollama serve &
sleep 3

echo "🚀 Iniciando Nova..."
cd /Users/mac/Desktop/NOVA_Personal_Asistente
python3 novaesp.py
```

Hazlo ejecutable:
```bash
chmod +x start_nova.sh
```

---

## Recursos

- **Modelos disponibles:** https://ollama.com/library
- **Documentación:** https://github.com/ollama/ollama
- **Qwen (coding):** https://ollama.com/library/qwen2.5-coder
- **Llava (visión):** https://ollama.com/library/llava
