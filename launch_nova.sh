#!/bin/bash
# Launch Nova — Script de arranque unificado

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Si viene de Finder, abrir Terminal y volver a ejecutar
if [ -z "$TERM" ]; then
    osascript -e "tell application \"Terminal\" to do script \"cd '$SCRIPT_DIR' && ./launch_nova.sh\" activate"
    exit 0
fi

# Activar entorno virtual si existe
if [ -f "$SCRIPT_DIR/.venv/bin/activate" ]; then
    source "$SCRIPT_DIR/.venv/bin/activate"
    PYTHON="$SCRIPT_DIR/.venv/bin/python"
else
    # Fallback: pyenv o sistema
    export PATH="$HOME/.pyenv/versions/3.10.6/bin:$PATH"
    PYTHON="python3"
    if ! command -v python3 &> /dev/null; then
        echo "Python 3 no encontrado. Ejecuta: python install.py"
        exit 1
    fi
fi

export PYTHONPATH="$SCRIPT_DIR:$SCRIPT_DIR/src"

clear
echo "Iniciando Nova Personal Assistant..."
"$PYTHON" main.py
