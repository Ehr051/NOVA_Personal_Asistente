#!/usr/bin/env python3
"""
diagnostico_openclaw.py
───────────────────────
Verifica el estado de OpenClaw y sus skills disponibles.
"""

import os
import sys
import json
import urllib.request
import urllib.error
import ssl

from dotenv import load_dotenv
load_dotenv()

def check_openclaw_connection():
    """Verifica si OpenClaw está corriendo."""
    base = os.getenv("OPENCLAW_BASE_URL", "http://127.0.0.1:18789").rstrip("/")
    key = os.getenv("OPENCLAW_API_KEY", "") or "openclaw-local"

    results = {
        "base_url": base,
        "connected": False,
        "api_v1": False,
        "skills_available": [],
        "errors": []
    }

    # 1. Verificar API v1 (chat completions)
    try:
        url = f"{base}/v1/models"
        req = urllib.request.Request(url, method="GET")
        req.add_header("Authorization", f"Bearer {key}")
        with urllib.request.urlopen(req, timeout=3) as r:
            if r.status == 200:
                results["api_v1"] = True
                results["connected"] = True
                data = json.loads(r.read().decode("utf-8"))
                results["models"] = [m.get("id", "?") for m in data.get("data", [])]
    except Exception as e:
        results["errors"].append(f"API v1: {str(e)[:50]}")

    # 2. Verificar endpoint de skills
    try:
        url = f"{base}/skills"
        req = urllib.request.Request(url, method="GET")
        req.add_header("Authorization", f"Bearer {key}")
        with urllib.request.urlopen(req, timeout=3) as r:
            if r.status == 200:
                data = json.loads(r.read().decode("utf-8"))
                results["skills_available"] = data.get("skills", [])
    except Exception as e:
        results["errors"].append(f"Skills endpoint: {str(e)[:50]}")

    # 3. Verificar estado del servidor
    try:
        url = f"{base}/health"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=2) as r:
            if r.status == 200:
                results["connected"] = True
    except:
        pass

    return results

def analyze_skills(skills):
    """Analiza el estado de las skills."""
    if not skills:
        return {"total": 0, "ready": 0, "needs_setup": 0, "disabled": 0}

    ready = sum(1 for s in skills if s.get("status") == "ready")
    needs_setup = sum(1 for s in skills if s.get("status") == "needs_setup")
    disabled = sum(1 for s in skills if s.get("status") == "disabled")

    return {
        "total": len(skills),
        "ready": ready,
        "needs_setup": needs_setup,
        "disabled": disabled
    }

def print_skill_categories(skills):
    """Agrupa skills por categoría."""
    if not skills:
        return

    categories = {}
    for skill in skills:
        cat = skill.get("category", "Otros")
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(skill)

    print("\n📂 Skills por categoría:")
    for cat, items in sorted(categories.items()):
        print(f"\n   {cat}:")
        for s in items[:5]:  # Mostrar primeros 5
            status = s.get("status", "?")
            icon = "✓" if status == "ready" else "✗" if status == "needs_setup" else "○"
            print(f"     {icon} {s.get('name', '?'):20} ({status})")
        if len(items) > 5:
            print(f"     ... y {len(items) - 5} más")

def main():
    print("═══════════════════════════════════════════════════════════")
    print("  🔍 Diagnóstico de OpenClaw")
    print("═══════════════════════════════════════════════════════════\n")

    # Variables
    base = os.getenv("OPENCLAW_BASE_URL", "NO CONFIGURADO")
    key = os.getenv("OPENCLAW_API_KEY", "")

    print("🔧 Configuración:")
    print(f"   OPENCLAW_BASE_URL = {base}")
    print(f"   OPENCLAW_API_KEY = {'✓ Configurado' if key else '✗ No configurado'}")
    print()

    # Conexión
    print("🌐 Probando conexión...")
    results = check_openclaw_connection()

    if not results["connected"]:
        print("   ✗ OpenClaw no está respondiendo")
        print("\n💡 Posibles soluciones:")
        print("   1. Verifica que OpenClaw esté corriendo:")
        print(f"      curl {results['base_url']}/health")
        print("   2. Revisa que el puerto esté disponible")
        print("   3. Verifica OPENCLAW_BASE_URL en tu .env")
        print("\n⚠️  Sin OpenClaw, Nova usará Ollama/Groq/OpenRouter para IA")
        print("   pero NO tendrá acceso a las 31+ herramientas de ClawHub.")
        sys.exit(1)

    print("   ✓ OpenClaw está conectado")
    print()

    # API v1
    if results["api_v1"]:
        print("✓ API OpenAI-compatible (/v1):")
        if "models" in results:
            print(f"   Modelos disponibles: {', '.join(results['models'][:5])}")
    else:
        print("✗ API v1 no disponible")
        print("   El router puede que no funcione con OpenClaw")

    # Skills
    skills = results.get("skills_available", [])
    if skills:
        stats = analyze_skills(skills)
        print(f"\n🔧 Skills disponibles: {stats['total']}")
        print(f"   ✓ Ready: {stats['ready']}")
        print(f"   ✗ Needs Setup: {stats['needs_setup']}")
        print(f"   ○ Disabled: {stats['disabled']}")

        print_skill_categories(skills)

        if stats["needs_setup"] > 0:
            print("\n⚠️  Skills que necesitan configuración:")
            for s in skills:
                if s.get("status") == "needs_setup":
                    print(f"   • {s.get('name')} - {s.get('description', 'Sin descripción')}")
    else:
        print("\nℹ️  No se pudieron obtener las skills")
        print("   OpenClaw podría estar en modo 'solo gateway de LLM'")

    print("\n═══════════════════════════════════════════════════════════")
    print("  📋 Resumen")
    print("═══════════════════════════════════════════════════════════")
    print()
    print("Estado actual:")
    print(f"   • Gateway de LLM: {'✓' if results['api_v1'] else '✗'}")
    print(f"   • Skills/tools: {'✓' if skills else '✗'}")

    if results["api_v1"]:
        print("\n✅ Nova PUEDE usar OpenClaw como proveedor de IA")
        print("   (generación de texto, chat, código)")

    if skills and stats.get("ready", 0) > 0:
        print(f"\n✅ Hay {stats['ready']} skills listas para usar")
        print("   Nova puede ejecutarlas vía OpenClaw")
    elif skills and stats.get("needs_setup", 0) > 0:
        print(f"\n⚠️  {stats['needs_setup']} skills necesitan configuración")
        print("   Ver guía de configuración de OpenClaw")

    print()

if __name__ == "__main__":
    main()
