#!/bin/bash
# Launch Nova — Script de arranque unificado v3.0
# Integra: Cerebro sync, módulos mejorados, visión, mouse celeste

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Configurar Python PATH
export PATH="$HOME/.pyenv/versions/3.10.6/bin:$PATH"
export PYTHONPATH="$SCRIPT_DIR:$SCRIPT_DIR/src"

# Si viene de Finder, abrir Terminal y volver a ejecutar
if [ -z "$TERM" ]; then
    osascript -e "tell application \"Terminal\" to do script \"cd '$SCRIPT_DIR' && ./launch_nova.sh\" activate"
    exit 0
fi

# Verificar Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 no encontrado. Instálalo con: brew install python3"
    exit 1
fi

# Verificar dependencias críticas
if [ ! -f "requirements.txt" ]; then
    echo "⚠️  requirements.txt no encontrado"
fi

# Ejecutar el launcher principal
clear
echo "🚀 Iniciando Nova Personal Assistant..."
python3 main.py
