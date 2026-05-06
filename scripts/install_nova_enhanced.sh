#!/bin/bash
# install_nova_enhanced.sh
# Instalador del sistema mejorado de Nova

echo "═══════════════════════════════════════════════════════════"
echo "  🚀 Nova Enhanced - Instalador"
echo "═══════════════════════════════════════════════════════════"
echo ""

cd "$(dirname "$0")"

# Verificar Python 3
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 no encontrado. Instálalo primero:"
    echo "   brew install python3"
    exit 1
fi

echo "✓ Python 3 encontrado"
echo ""

# Instalar dependencias
echo "📦 Instalando dependencias..."
echo ""

pip3 install --user pillow numpy pyautogui 2>/dev/null || pip3 install pillow numpy pyautogui

# Dependencias opcionales
echo ""
echo "📦 Instalando dependencias opcionales..."
pip3 install --user pytesseract opencv-python 2>/dev/null || pip3 install pytesseract opencv-python

echo ""
echo "✓ Dependencias instaladas"
echo ""

# Verificar imports
echo "🔍 Verificando módulos..."
python3 -c "
import PIL
import numpy
import pyautogui
print('✓ PIL (Pillow) OK')
print('✓ NumPy OK')
print('✓ PyAutoGUI OK')
"

echo ""

# Verificar sintaxis de archivos
echo "🔍 Verificando archivos de Nova..."
python3 -m py_compile nova_vision.py nova_mouse.py nova_skills_enhanced.py nova_integracion.py
echo "✓ Todos los archivos son válidos"

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  ✅ Instalación completada"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "⚠️  IMPORTANTE: Configurar permisos de macOS"
echo ""
echo "1. Abre Preferencias del Sistema"
echo "2. Ve a Seguridad y Privacidad → Privacidad"
echo "3. Agrega permisos para:"
echo "   • Accesibilidad → Terminal, Python"
echo "   • Grabación de pantalla → Terminal, Python"
echo ""
echo "Para probar:"
echo "   python3 nova_integracion.py"
echo ""
echo "Documentación: SETUP_NOVA_ENHANCED.md"
echo ""
