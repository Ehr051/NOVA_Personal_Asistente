#!/usr/bin/env python3
"""
nova_launcher.py
────────────────
Launcher principal de NOVA.

Integra:
  • Sincronización del Gran Cerebro (Obsidian)
  • Inicialización de módulos mejorados (visión, mouse)
  • Verificación de dependencias
  • Limpieza de sesiones anteriores
  • Inicio del sistema principal (novaesp.py)

Uso:
  python3 nova_launcher.py

O desde el dock:
  ./launch_nova.sh
"""

from __future__ import annotations

import os
import sys
import time
import subprocess
import threading
from pathlib import Path

# Configurar paths
BASE_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(BASE_DIR))

# Cargar variables de entorno
from dotenv import load_dotenv
load_dotenv(BASE_DIR / ".env")


class NovaLauncher:
    """Gestiona el inicio completo de Nova."""

    def __init__(self):
        self.checks_passed = []
        self.checks_failed = []
        self.enhanced_loaded = False

    def print_header(self):
        """Muestra banner de inicio."""
        print("""
╔═══════════════════════════════════════════════════════════════╗
║                                                               ║
║   🚀 NOVA Personal Assistant v3.0                            ║
║                                                               ║
║   Vision • Mouse • AI • Automation                            ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝
""")

    def check_dependencies(self) -> bool:
        """Verifica que todas las dependencias estén instaladas."""
        print("🔍 Verificando dependencias...")
        print()

        deps = {
            "pyautogui": "Control de mouse/teclado",
            "PIL": "Procesamiento de imágenes",
            "openai": "API de modelos",
            "dotenv": "Variables de entorno",
            "speech_recognition": "Reconocimiento de voz",
            "pyaudio": "Audio",
        }

        all_ok = True
        for module, description in deps.items():
            try:
                __import__(module)
                print(f"   ✅ {module:<20} - {description}")
                self.checks_passed.append(module)
            except ImportError:
                print(f"   ❌ {module:<20} - {description} (FALTA)")
                self.checks_failed.append(module)
                all_ok = False

        # Verificar módulos mejorados opcionales
        print()
        print("   Módulos mejorados (opcionales):")
        enhanced = {
            "nova_vision": "Visión de pantalla",
            "nova_mouse": "Mouse inteligente",
            "nova_skills_enhanced": "Skills avanzadas",
        }

        for module, description in enhanced.items():
            try:
                __import__(module)
                print(f"   ✅ {module:<25} - {description}")
                self.enhanced_loaded = True
            except ImportError as e:
                print(f"   ⚠️  {module:<25} - {description} (no disponible: {e})")

        print()
        return all_ok

    def sync_cerebro(self) -> bool:
        """Sincroniza el Gran Cerebro con Obsidian."""
        print("🧠 Sincronizando Gran Cerebro...")

        sync_script = BASE_DIR / "sync_cerebro.py"
        if not sync_script.exists():
            print("   ⚠️  sync_cerebro.py no encontrado, saltando")
            return False

        try:
            # Ejecutar sync en modo silencioso
            result = subprocess.run(
                [sys.executable, str(sync_script), "--fast"],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(BASE_DIR)
            )

            if result.returncode == 0:
                # Extraer resumen
                lines = result.stdout.strip().split('\n')
                for line in lines:
                    if 'sincronizado' in line.lower() or '✓' in line:
                        print(f"   ✅ {line.strip()}")
                self.checks_passed.append("sync_cerebro")
                return True
            else:
                print(f"   ⚠️  Sync completado con advertencias")
                return True

        except subprocess.TimeoutExpired:
            print("   ⚠️  Sync tardó demasiado, continuando...")
            return False
        except Exception as e:
            print(f"   ⚠️  Error en sync: {e}")
            return False

    def check_ollama(self) -> bool:
        """Verifica/inicia Ollama."""
        print()
        print("🦙 Verificando Ollama...")

        try:
            result = subprocess.run(
                ["curl", "-s", "http://localhost:11434/api/tags"],
                capture_output=True,
                timeout=3
            )

            if result.returncode == 0:
                print("   ✅ Ollama activo")
                self.checks_passed.append("ollama")
                return True
            else:
                print("   ℹ️  Ollama no disponible (opcional)")
                print("      Ejecuta: ollama serve")
                return False

        except Exception:
            print("   ℹ️  Ollama no detectado (opcional)")
            return False

    def init_enhanced_modules(self):
        """Inicializa módulos mejorados si están disponibles."""
        if not self.enhanced_loaded:
            return

        print()
        print("🔧 Inicializando módulos mejorados...")
        # Importante: no inicializar mouse/visión acá para evitar bloqueos en arranque.
        # Algunos entornos pueden colgarse al crear overlays/captura durante bootstrap.
        print("   ✅ Módulos enhanced detectados")
        print("      Se inicializan bajo demanda cuando uses cada skill.")

    def show_status(self):
        """Muestra resumen del estado."""
        print()
        print("═" * 63)
        print("  📊 Estado del sistema")
        print("═" * 63)
        print()
        print(f"   Checks pasados: {len(self.checks_passed)}/{len(self.checks_passed) + len(self.checks_failed)}")
        print(f"   Módulos mejorados: {'✅ Activados' if self.enhanced_loaded else '⚠️  Básicos'}")
        print()

        # Mostrar wake word
        wake = os.getenv("WAKE_WORD", "nova")
        print(f"   🎤 Wake word: '{wake}'")
        print(f"      Ejemplos: '{wake}, abre Safari', '{wake}, qué hora es'")
        print()

        # Provider order
        providers = os.getenv("ROUTER_PROVIDER_ORDER", "ollama,groq,openrouter").split(",")
        print(f"   🤖 Proveedores IA: {', '.join(providers)}")

        if self.enhanced_loaded:
            print()
            print("   ✨ Nuevas capacidades disponibles:")
            print("      • Visión de pantalla")
            print("      • Cursor celeste independiente")
            print("      • Alarmas y timers funcionales")
            print("      • Dictado universal")
            print("      • Integración con apps de diseño")

        print()
        print("═" * 63)
        print()

    def launch_main(self):
        """Lanza el sistema principal."""
        print("🚀 Iniciando NOVA...")
        print()
        time.sleep(1)

        # Ejecutar novaesp como proceso principal (bloqueante).
        # Importarlo no alcanza porque el main solo corre con __name__ == "__main__".
        try:
            main_script = BASE_DIR / "novaesp.py"
            if not main_script.exists():
                print(f"❌ No se encontró {main_script}")
                return

            print(f"   ▶ Ejecutando: {sys.executable} {main_script.name}")
            result = subprocess.run(
                [sys.executable, str(main_script)],
                cwd=str(BASE_DIR),
            )
            if result.returncode != 0:
                print(f"❌ NOVA terminó con código {result.returncode}")
            else:
                print("✅ NOVA finalizó correctamente")
        except Exception as e:
            print(f"❌ Error iniciando NOVA: {e}")
            print("   Ejecuta manualmente: python3 novaesp.py")

    def run(self):
        """Ejecuta el flujo completo de inicio."""
        self.print_header()

        # 1. Verificar dependencias
        if not self.check_dependencies():
            print("❌ Faltan dependencias esenciales.")
            print("   Ejecuta: pip3 install -r requirements.txt")
            return 1

        # 2. Sync cerebro
        self.sync_cerebro()

        # 3. Verificar Ollama
        self.check_ollama()

        # 4. Inicializar módulos mejorados
        self.init_enhanced_modules()

        # 5. Mostrar status
        self.show_status()

        # 6. Launch
        self.launch_main()

        return 0


def main():
    """Entry point."""
    launcher = NovaLauncher()
    return launcher.run()


if __name__ == "__main__":
    sys.exit(main())
