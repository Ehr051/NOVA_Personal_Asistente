#!/usr/bin/env python3
"""
Nova Personal Assistant - Entry Point
Lanza el HUD PyQt5 (novaesp.py).

Para el REPL conversacional en terminal: `./nova chat`
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

if __name__ == "__main__":
    from nova.lang.novaesp import main as esp_main
    esp_main()
