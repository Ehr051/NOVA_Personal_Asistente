#!/bin/bash
# setup_ollama_models.sh
# Script para instalar los modelos recomendados de Ollama para Nova

echo "═══════════════════════════════════════════════════════════"
echo "  Nova + Ollama — Instalador de Modelos"
echo "═══════════════════════════════════════════════════════════"
echo ""

# Verificar que Ollama está instalado
if ! command -v ollama &> /dev/null; then
    echo "❌ Ollama no está instalado"
    echo ""
    echo "Instálalo primero con:"
    echo "  curl -fsSL https://ollama.com/install.sh | sh"
    echo ""
    echo "O descarga desde: https://ollama.com/download"
    exit 1
fi

echo "✓ Ollama detectado"
echo ""

# Iniciar Ollama en background si no está corriendo
if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "🚀 Iniciando servidor Ollama..."
    ollama serve &
    sleep 3
fi

echo "✓ Servidor Ollama activo"
echo ""

# Preguntar qué nivel de instalación
echo "¿Qué modelos instalar?"
echo ""
echo "  [1] ESSENCIAL (~5GB) — Recomendado para empezar"
echo "      • llama3.2:1b — Comandos rápidos"
echo "      • qwen2.5:7b — Coding general"
echo ""
echo "  [2] COMPLETO (~15GB) — Para uso intensivo de código"
echo "      • Incluye todos los esenciales"
echo "      • qwen2.5:14b — Máxima calidad"
echo "      • deepseek-coder:6.7b — Coding especializado"
echo ""
echo "  [3] CON VISIÓN (~20GB) — Todo + análisis de imágenes"
echo "      • Incluye todos los anteriores"
echo "      • llava:7b — Visión"
echo "      • moondream:2b — Visión rápida"
echo ""
echo "  [4] Personalizado"
echo ""

read -p "Selección (1-4): " choice

case $choice in
    1)
        echo ""
        echo "📦 Instalando modelos esenciales..."
        echo ""

        echo "→ Descargando llama3.2:1b (comandos rápidos)..."
        ollama pull llama3.2:1b

        echo "→ Descargando qwen2.5:7b (coding general)..."
        ollama pull qwen2.5:7b

        echo "→ Descargando qwen2.5-coder:1.5b (coding ligero)..."
        ollama pull qwen2.5-coder:1.5b
        ;;

    2)
        echo ""
        echo "📦 Instalando modelos completos..."
        echo ""

        echo "→ Descargando llama3.2:1b..."
        ollama pull llama3.2:1b

        echo "→ Descargando qwen2.5:7b..."
        ollama pull qwen2.5:7b

        echo "→ Descargando qwen2.5-coder:1.5b..."
        ollama pull qwen2.5-coder:1.5b

        echo "→ Descargando qwen2.5:14b (puede tardar)..."
        ollama pull qwen2.5:14b

        echo "→ Descargando deepseek-coder:6.7b..."
        ollama pull deepseek-coder:6.7b
        ;;

    3)
        echo ""
        echo "📦 Instalando todos los modelos + visión..."
        echo ""

        echo "→ Descargando llama3.2:1b..."
        ollama pull llama3.2:1b

        echo "→ Descargando qwen2.5:7b..."
        ollama pull qwen2.5:7b

        echo "→ Descargando qwen2.5-coder:1.5b..."
        ollama pull qwen2.5-coder:1.5b

        echo "→ Descargando qwen2.5:14b (puede tardar)..."
        ollama pull qwen2.5:14b

        echo "→ Descargando deepseek-coder:6.7b..."
        ollama pull deepseek-coder:6.7b

        echo "→ Descargando llava:7b (visión)..."
        ollama pull llava:7b

        echo "→ Descargando moondream:2b (visión ligera)..."
        ollama pull moondream:2b
        ;;

    4)
        echo ""
        echo "Modelos disponibles:"
        echo "  1. llama3.2:1b    - Comandos ultra rápidos"
        echo "  2. llama3.2       - Balance general"
        echo "  3. qwen2.5:7b     - Coding excelente"
        echo "  4. qwen2.5:14b    - Máxima calidad"
        echo "  5. qwen2.5-coder:* - Especializado código"
        echo "  6. deepseek-coder:* - Coding avanzado"
        echo "  7. llava:*        - Visión"
        echo "  8. moondream:*    - Visión rápida"
        echo ""
        read -p "Escribe el nombre del modelo (ej: qwen2.5:7b): " model
        ollama pull $model
        ;;

    *)
        echo "❌ Opción inválida"
        exit 1
        ;;
esac

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  ✅ Instalación completada"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "Modelos instalados:"
ollama list
echo ""
echo "💡 Configurar Nova para usar Ollama primero:"
echo "   En tu .env, establece:"
echo "   ROUTER_PROVIDER_ORDER=ollama,groq,openrouter"
echo ""
echo "🚀 Para iniciar Nova con Ollama:"
echo "   ollama serve &"
echo "   python3 main.py"
echo ""
