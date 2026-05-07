#!/usr/bin/env python3
"""
test_all_skills.py — Prueba REAL de las skills que dependen de servicios externos.
Testea n8n, GitHub y Visión (Ollama).
"""
import os, sys
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
sys.path.insert(0, "/Users/mac/Desktop/NOVA_Personal_Asistente")
sys.path.insert(0, "/Users/mac/Desktop/NOVA_Personal_Asistente/src")

import pytest

if os.getenv("NOVA_RUN_INTEGRATION_TESTS") != "1":
    pytest.skip(
        "External integration script touches n8n/GitHub/Ollama/browser. "
        "Set NOVA_RUN_INTEGRATION_TESTS=1 to run manually.",
        allow_module_level=True,
    )

from nova.connectors import nova_n8n as n8n
from nova.tools import nova_github as github
from nova.tools.nova_vision import get_vision
import urllib.request

PASS = "✅"
FAIL = "❌"

print("\n" + "═"*70)
print("  NOVA — PRUEBA DE INTEGRACIÓN DE SERVICIOS EXTERNOS")
print("═"*70)

# ─── 1. n8n ───────────────────────────────────────────────────
print("\n  ── 1. n8n ──")
print(f"  URL Base: {n8n._BASE}")
estado = n8n.estado_n8n()
if "operativo" in estado:
    print(f"  {PASS} Conexión: {estado}")
    # Probar un endpoint específico (gastos)
    print("  Probando endpoint de gastos...")
    res_gastos = n8n.consultar_gastos("semana")
    print(f"  Respuesta gastos: {res_gastos}")
else:
    print(f"  {FAIL} Conexión: {estado}")

# ─── 2. GitHub ───────────────────────────────────────────────
print("\n  ── 2. GitHub ──")
estado_gh = github.estado_github()
if "conectado" in estado_gh:
    print(f"  {PASS} Conexión: {estado_gh}")
    # Listar repos reales
    print("  Listando tus repositorios...")
    repos = github.listar_repos(3)
    print(f"  {repos}")
else:
    print(f"  {FAIL} Conexión: {estado_gh}")

# ─── 3. Visión (Ollama) ───────────────────────────────────────
print("\n  ── 3. Visión (Ollama) ──")
try:
    import subprocess
    print("  Verificando modelos de visión en Ollama...")
    r = subprocess.run(["ollama", "list"], capture_output=True, text=True)
    models = r.stdout.lower()
    vision_models = [m for m in ["llava", "qwen2-vl", "moondream", "bakllava"] if m in models]
    if vision_models:
        print(f"  {PASS} Modelos detectados: {', '.join(vision_models)}")
    else:
        print(f"  {FAIL} No se detectaron modelos de visión (llava, qwen2-vl, etc.)")
except Exception as e:
    print(f"  {FAIL} Error al verificar Ollama: {e}")

# ─── 4. Browser (Playwright) ──────────────────────────────────
print("\n  ── 4. Browser (Playwright) ──")
try:
    from nova.tools.nova_browser import _HAS_PLAYWRIGHT
    if _HAS_PLAYWRIGHT:
        print(f"  {PASS} Playwright está instalado.")
    else:
        print(f"  {FAIL} Playwright NO está instalado.")
except ImportError:
    print(f"  {FAIL} No se pudo importar el módulo de browser.")

print("\n" + "═"*70 + "\n")
