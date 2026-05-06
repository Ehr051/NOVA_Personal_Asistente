#!/usr/bin/env python3
"""
Verificador del Sistema - Detector de Gestos
===========================================

Script para verificar que todos los componentes del sistema
estén instalados correctamente antes de ejecutar el programa principal.
"""

import sys
import subprocess
import importlib
import platform
import os
from pathlib import Path

# Intentar importar cv2 con manejo de errores
try:
    import cv2  # type: ignore
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    cv2 = None

def print_header():
    """Muestra el encabezado del verificador"""
    print("=" * 60)
    print("    VERIFICADOR DEL SISTEMA - DETECTOR DE GESTOS")
    print("=" * 60)
    print()

def check_python_version():
    """Verifica la versión de Python"""
    print("🐍 Verificando versión de Python...")
    version = sys.version_info
    
    if version.major >= 3 and version.minor >= 7:
        print(f"   ✅ Python {version.major}.{version.minor}.{version.micro} - ¡Correcto!")
        return True
    else:
        print(f"   ❌ Python {version.major}.{version.minor}.{version.micro} - Se requiere 3.7+")
        return False

def check_required_packages():
    """Verifica las dependencias requeridas"""
    print("\n📦 Verificando dependencias de Python...")
    
    required_packages = {
        'cv2': 'opencv-python',
        'mediapipe': 'mediapipe', 
        'numpy': 'numpy',
        'pyautogui': 'pyautogui'
    }
    
    all_installed = True
    
    for module_name, package_name in required_packages.items():
        try:
            importlib.import_module(module_name)
            print(f"   ✅ {package_name} - Instalado")
        except ImportError:
            print(f"   ❌ {package_name} - No instalado")
            all_installed = False
    
    return all_installed

def check_camera():
    """Verifica el acceso a la cámara"""
    print("\n📷 Verificando acceso a la cámara...")
    
    if not CV2_AVAILABLE:
        print("   ❌ Cámara - OpenCV no está disponible")
        return False
    
    try:
        cap = cv2.VideoCapture(0)  # type: ignore
        if cap.isOpened():
            ret, frame = cap.read()
            if ret:
                print("   ✅ Cámara - Accesible y funcionando")
                result = True
            else:
                print("   ⚠️  Cámara - Accesible pero no puede capturar frames")
                result = False
            cap.release()
        else:
            print("   ❌ Cámara - No se puede acceder")
            result = False
    except Exception as e:
        print(f"   ❌ Cámara - Error: {e}")
        result = False
    
    return result

def check_system_permissions():
    """Verifica permisos del sistema según la plataforma"""
    print(f"\n🔐 Verificando permisos del sistema ({platform.system()})...")
    
    if platform.system() == "Darwin":  # macOS
        print("   ℹ️  macOS detectado")
        print("   📋 Permisos requeridos:")
        print("      • Cámara: Preferencias > Seguridad y privacidad > Cámara")
        print("      • Accesibilidad: Preferencias > Seguridad y privacidad > Accesibilidad")
        print("   ⚠️  Asegúrate de haber configurado estos permisos manualmente")
        
    elif platform.system() == "Windows":  # Windows
        print("   ℹ️  Windows detectado")
        print("   📋 Recomendaciones:")
        print("      • Ejecutar como administrador si hay problemas")
        print("      • Verificar permisos de cámara en Configuración > Privacidad")
        print("      • Instalar Visual C++ Redistributable si es necesario")
        
    elif platform.system() == "Linux":  # Linux
        print("   ℹ️  Linux detectado")
        print("   📋 Recomendaciones:")
        print("      • Asegurar que el usuario está en el grupo 'video'")
        print("      • Verificar permisos de dispositivos /dev/video*")
    
    return True

def check_files():
    """Verifica que los archivos necesarios existan"""
    print("\n📁 Verificando archivos del proyecto...")
    
    required_files = [
        'detectorGestos.py',
        'requirements.txt',
        'config.json'
    ]
    
    optional_files = [
        'control_gestos.py',
        'DetectorGestosOptimizado.py',
        'demo.py',
        'launch_macos.sh',
        'launch_windows.bat'
    ]
    
    all_present = True
    
    for file_name in required_files:
        if Path(file_name).exists():
            print(f"   ✅ {file_name} - Encontrado")
        else:
            print(f"   ❌ {file_name} - No encontrado (REQUERIDO)")
            all_present = False
    
    for file_name in optional_files:
        if Path(file_name).exists():
            print(f"   ✅ {file_name} - Encontrado")
        else:
            print(f"   ⚠️  {file_name} - No encontrado (opcional)")
    
    return all_present

def check_pyautogui_config():
    """Verifica la configuración de PyAutoGUI"""
    print("\n🖱️  Verificando configuración de PyAutoGUI...")
    
    try:
        import pyautogui  # type: ignore
        
        # Obtener información de la pantalla
        screen_size = pyautogui.size()
        print(f"   ✅ Resolución de pantalla: {screen_size[0]}x{screen_size[1]}")
        
        # Verificar configuración de seguridad
        print(f"   ℹ️  Fail-safe activado: {pyautogui.FAILSAFE}")
        print(f"   ℹ️  Tiempo de pausa: {pyautogui.PAUSE}s")
        
        return True
        
    except Exception as e:
        print(f"   ❌ Error configurando PyAutoGUI: {e}")
        return False

def provide_installation_help():
    """Proporciona ayuda para la instalación"""
    print("\n" + "=" * 60)
    print("    AYUDA PARA LA INSTALACIÓN")
    print("=" * 60)
    
    print("\n🔧 Para instalar dependencias faltantes:")
    print("   pip install -r requirements.txt")
    
    print("\n🔧 O instalar individualmente:")
    print("   pip install opencv-python mediapipe numpy pyautogui")
    
    print("\n🚀 Para ejecutar con los launchers:")
    if platform.system() == "Darwin":
        print("   ./launch_macos.sh")
    elif platform.system() == "Windows":
        print("   launch_windows.bat")
    
    print("\n📖 Para más ayuda, consulta README_v2.md")

def main():
    """Función principal del verificador"""
    print_header()
    
    checks = [
        ("Python", check_python_version()),
        ("Dependencias", check_required_packages()),
        ("Cámara", check_camera()),
        ("Permisos", check_system_permissions()),
        ("Archivos", check_files()),
        ("PyAutoGUI", check_pyautogui_config())
    ]
    
    print("\n" + "=" * 60)
    print("    RESUMEN DE VERIFICACIÓN")
    print("=" * 60)
    
    passed = 0
    total = len(checks)
    
    for check_name, result in checks:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"   {check_name:.<30} {status}")
        if result:
            passed += 1
    
    print(f"\nResultado: {passed}/{total} verificaciones pasaron")
    
    if passed == total:
        print("\n🎉 ¡Todo está configurado correctamente!")
        print("   Puedes ejecutar el programa principal:")
        print("   python detectorGestos.py")
    else:
        print(f"\n⚠️  {total - passed} problemas encontrados.")
        provide_installation_help()
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
