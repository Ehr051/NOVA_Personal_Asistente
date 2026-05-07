# -*- mode: python ; coding: utf-8 -*-
import sys
import os
from pathlib import Path

block_cipher = None
IS_WINDOWS = sys.platform == "win32"
IS_MACOS   = sys.platform == "darwin"

a = Analysis(
    ["main.py"],
    pathex=[str(Path("src"))],
    binaries=[],
    datas=[
        ("src/nova", "nova"),
        ("assets",   "assets"),
        (".env.example", "."),
    ],
    hiddenimports=[
        "nova.cli.repl",
        "nova.core.nova_router",
        "nova.tools.nova_skills",
        "nova.lang.novaesp",
        "nova.platform.adapter",
        "speech_recognition",
        "sounddevice",
        "edge_tts",
        "groq",
        "openai",
        "dotenv",
        "qdrant_client",
        "qdrant_client.local",
        "numpy",
        "pyautogui",
        "PIL",
        "requests",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["PyAudio"] if IS_WINDOWS else [],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Nova",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/nova.ico" if IS_WINDOWS else "assets/nova.png",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Nova",
)

# macOS: crear .app bundle
if IS_MACOS:
    app = BUNDLE(
        coll,
        name="Nova.app",
        icon="assets/nova.png",
        bundle_identifier="com.ehr051.nova",
        info_plist={
            "NSMicrophoneUsageDescription": "Nova necesita el micrófono para reconocimiento de voz.",
            "NSCameraUsageDescription":     "Nova usa la cámara para percepción visual.",
            "CFBundleShortVersionString":   "3.1",
            "LSUIElement": False,
        },
    )
