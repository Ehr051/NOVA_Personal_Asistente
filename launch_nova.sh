#!/bin/bash
# Launch Nova — Script de arranque unificado

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Activar entorno virtual
if [ -f "$SCRIPT_DIR/.venv/bin/activate" ]; then
    source "$SCRIPT_DIR/.venv/bin/activate"
    PYTHON="$SCRIPT_DIR/.venv/bin/python"
else
    export PATH="$HOME/.pyenv/versions/3.10.6/bin:$PATH"
    PYTHON="python3"
    if ! command -v python3 &> /dev/null; then
        echo "Python 3 no encontrado. Ejecuta: python install.py"
        exit 1
    fi
fi

export PYTHONPATH="$SCRIPT_DIR:$SCRIPT_DIR/src"
mkdir -p ~/.nova

# Modo debug: NOVA_DEBUG=1 ./launch_nova.sh  →  muestra output en terminal
if [ "${NOVA_DEBUG:-0}" = "1" ]; then
    clear
    echo "Nova — modo debug (logs en pantalla)"
    exec "$PYTHON" main.py 2>&1 | tee -a ~/.nova/nova.log
fi

# Modo normal: logs a archivo, sin terminal visible
# Si viene de Finder (sin TERM), lanzar directamente
exec "$PYTHON" main.py >> ~/.nova/nova.log 2>&1
