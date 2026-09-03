# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for CRM AI Desk

import sys
from pathlib import Path

block_cipher = None
root = Path(SPECPATH)

datas = [
    (str(root / "desktop"), "desktop"),
    (str(root / "widget"), "widget"),
]

hidden = [
    "uvicorn",
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "fastapi",
    "starlette",
    "anyio",
    "sniffio",
    "httpx",
    "openai",
    "webview",
    "clr",
    "pythonnet",
    "crm",
    "crm.amocrm_adapter",
    "crm.bitrix24_adapter",
    "crm.registry",
    "crm.base",
    "api_server",
    "assistant_service",
    "analyzer",
    "collector",
    "transcriber",
    "storage",
    "profiles",
    "medical_coach",
    "bilingual",
    "report_generator",
    "publisher",
    "config",
    "amocrm_client",
    "pydantic",
    "multipart",
    "dotenv",
    "apscheduler",
]

a = Analysis(
    [str(root / "product_main.py")],
    pathex=[str(root)],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy.tests"],
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
    name="CRMAIDesk",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="CRMAIDesk",
)
