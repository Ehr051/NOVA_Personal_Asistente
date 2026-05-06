#!/usr/bin/env python3
"""
diagnostico_cerebro.py
──────────────────────
Verifica que la conexión con Obsidian (Gran Cerebro) esté funcionando correctamente.
"""

import os
import sys
import ssl
import urllib.request
from pathlib import Path

# Cargar .env
from dotenv import load_dotenv
load_dotenv()

def check_env():
    """Verifica variables de entorno."""
    print("🔍 Variables de entorno:")
    print(f"   OBSIDIAN_BASE_URL = {os.getenv('OBSIDIAN_BASE_URL', 'NO CONFIGURADO')}")
    obs_key = os.getenv('OBSIDIAN_API_KEY', '')
    print(f"   OBSIDIAN_API_KEY = {'✓ Configurado' if obs_key else '✗ Vacío'}")
    return bool(obs_key)

def check_obsidian_connection():
    """Intenta conectar con Obsidian REST API."""
    base = os.getenv("OBSIDIAN_BASE_URL", "https://127.0.0.1:27124")
    key = os.getenv("OBSIDIAN_API_KEY", "")

    if not key:
        return False, "API key no configurada"

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    try:
        req = urllib.request.Request(f"{base}/")
        req.add_header("Authorization", f"Bearer {key}")
        with urllib.request.urlopen(req, context=ctx, timeout=3) as r:
            return True, f"Conectado (status {r.status})"
    except urllib.error.HTTPError as e:
        return False, f"HTTP Error {e.code} - Verifica API key"
    except Exception as e:
        return False, f"Error: {str(e)[:50]}"

def check_memory_system():
    """Verifica sistema de memoria local."""
    print("\n💾 Sistema de Memoria Local:")

    db_path = Path.home() / ".nova" / "memory.db"
    if db_path.exists():
        import sqlite3
        try:
            with sqlite3.connect(db_path) as con:
                facts = con.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
                convs = con.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
            print(f"   ✓ Base de datos SQLite encontrada")
            print(f"     - {facts} facts guardados")
            print(f"     - {convs} conversaciones almacenadas")
        except Exception as e:
            print(f"   ⚠️ Error leyendo DB: {e}")
    else:
        print(f"   ℹ️ Base de datos no existe aún (se creará al primer uso)")

def check_vault_structure():
    """Verifica estructura del vault."""
    print("\n📁 Estructura del Gran Cerebro:")

    cerebro = Path.home() / "Cerebro"
    carpetas = ["NOVA", "Claude", "Stats", "Diario", "Drops"]

    for carpeta in carpetas:
        path = cerebro / carpeta
        if path.exists():
            archivos = len(list(path.iterdir()))
            print(f"   ✓ {carpeta}/ ({archivos} items)")
        else:
            print(f"   ℹ️ {carpeta}/ (no existe - se creará al usar)")

def check_router_stats():
    """Verifica estadísticas del router."""
    print("\n📊 Estadísticas del Router:")

    stats_file = Path("model_stats.json")
    vault_stats = Path.home() / "Cerebro" / "Stats" / "model_stats.json"

    if stats_file.exists():
        import json
        try:
            with open(stats_file) as f:
                data = json.load(f)
            print(f"   ✓ Local: {len(data)} modelos trackeados")
            for model, stats in data.items():
                total = stats['success'] + stats['fail']
                rate = (stats['success'] / total * 100) if total > 0 else 0
                print(f"     - {model}: {rate:.0f}% éxito ({stats['success']}/{total})")
        except Exception as e:
            print(f"   ⚠️ Error leyendo stats: {e}")
    else:
        print(f"   ℹ️ No hay estadísticas locales aún")

    if vault_stats.exists():
        print(f"   ✓ Vault: Stats sincronizadas")
    else:
        print(f"   ℹ️ Vault: Stats no sincronizadas aún")

def main():
    print("═══════════════════════════════════════════════════════════")
    print("  🧠 Diagnóstico del Gran Cerebro")
    print("═══════════════════════════════════════════════════════════\n")

    # 1. Variables
    if not check_env():
        print("\n❌ OBSIDIAN_API_KEY no configurada")
        print("   Agrega a tu .env:")
        print("   OBSIDIAN_API_KEY=tu_api_key_de_obsidian")
        sys.exit(1)

    # 2. Conexión
    print("\n🌐 Conexión a Obsidian:")
    ok, msg = check_obsidian_connection()
    if ok:
        print(f"   ✓ {msg}")
    else:
        print(f"   ✗ {msg}")
        print("\n💡 Tips:")
        print("   - Asegúrate de que Obsidian esté abierto")
        print("   - Instala el plugin 'Local REST API'")
        print("   - Verifica que el puerto 27124 esté disponible")

    # 3. Memoria local
    check_memory_system()

    # 4. Vault
    check_vault_structure()

    # 5. Router
    check_router_stats()

    print("\n═══════════════════════════════════════════════════════════")
    if ok:
        print("  ✅ Todo listo - El Gran Cerebro está operativo")
    else:
        print("  ⚠️  Revisar conexión - Nova funcionará sin contexto del vault")
    print("═══════════════════════════════════════════════════════════\n")

if __name__ == "__main__":
    main()
