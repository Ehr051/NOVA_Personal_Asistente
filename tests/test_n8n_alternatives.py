#!/usr/bin/env python3
import urllib.request
import os
import pytest

if os.getenv("NOVA_RUN_N8N_TESTS") != "1":
    pytest.skip(
        "n8n endpoint probe requires local workflows. Set NOVA_RUN_N8N_TESTS=1 to run manually.",
        allow_module_level=True,
    )

BASE = "http://localhost:5678"
PATHS = [
    "/webhook/nova/gastos",
    "/webhook/gastos",
    "/webhook-test/nova/gastos",
    "/webhook-test/gastos",
]

print(f"Probando alternativas n8n en {BASE}...")

for p in PATHS:
    url = f"{BASE}{p}"
    try:
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=3) as resp:
            print(f"  [OK] {p} -> HTTP {resp.status}")
    except Exception as e:
        print(f"  [--] {p} -> {e}")
