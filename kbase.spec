# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for KBase macOS .app bundle."""
import os
import sys

block_cipher = None
project_dir = os.path.abspath('.')

# Collect all static files
static_dir = os.path.join(project_dir, 'kbase', 'static')
static_files = []
for root, dirs, files in os.walk(static_dir):
    for f in files:
        if f == '__pycache__' or f.endswith('.pyc'):
            continue
        src = os.path.join(root, f)
        dst = os.path.relpath(root, project_dir)
        static_files.append((src, dst))

# Collect connector templates
connector_dir = os.path.join(project_dir, 'kbase', 'connectors')
connector_files = []
for f in os.listdir(connector_dir):
    if f.endswith('.py') and not f.startswith('__'):
        connector_files.append((os.path.join(connector_dir, f), 'kbase/connectors'))

a = Analysis(
    ['launcher.py'],
    pathex=[project_dir],
    binaries=[],
    datas=static_files + connector_files + [
        # Jieba dictionary
        ('kbase', 'kbase'),
    ],
    hiddenimports=[
        'kbase', 'kbase.web', 'kbase.cli', 'kbase.store', 'kbase.chat',
        'kbase.search', 'kbase.enhance', 'kbase.extract', 'kbase.chunk',
        'kbase.ingest', 'kbase.config', 'kbase.websearch', 'kbase.agent_loop',
        'kbase.connectors', 'kbase.connectors.feishu', 'kbase.connectors.feishu_guide',
        'uvicorn', 'uvicorn.logging', 'uvicorn.loops', 'uvicorn.loops.auto',
        'uvicorn.protocols', 'uvicorn.protocols.http', 'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets', 'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan', 'uvicorn.lifespan.on',
        'fastapi', 'starlette', 'starlette.routing', 'starlette.middleware',
        'chromadb', 'chromadb.api', 'chromadb.api.rust', 'chromadb.api.client',
        'chromadb.api.shared_system_client', 'chromadb.config',
        'chromadb.telemetry', 'chromadb.telemetry.product',
        'chromadb.telemetry.product.posthog',
        'chromadb.segment', 'chromadb.segment.impl',
        'chromadb.segment.impl.manager', 'chromadb.segment.impl.manager.local',
        'chromadb.segment.impl.vector', 'chromadb.segment.impl.metadata',
        'chromadb.db', 'chromadb.db.impl', 'chromadb.db.impl.sqlite',
        'chromadb.migrations', 'chromadb.auth',
        'posthog', 'onnxruntime', 'tokenizers',
        'jieba', 'jieba.posseg', 'jieba.analyse',
        'pptx', 'docx', 'openpyxl', 'fitz',
        'click', 'rich', 'watchdog',
        'multipart', 'email', 'email.mime',
        'tkinter',
        'sqlite3',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'scipy', 'notebook', 'IPython',
              'torch', 'torchvision', 'torchaudio', 'sentence_transformers',
              'transformers', 'safetensors'],
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
    name='KBase',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # No terminal window
    target_arch=None,  # Use native arch (arm64 on Apple Silicon, x86_64 on Intel)
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name='KBase',
)

app = BUNDLE(
    coll,
    name='KBase.app',
    icon='build/KBase.icns',  # Will create icon separately
    bundle_identifier='com.penguinmiaou.kbase',
    info_plist={
        'CFBundleName': 'KBase',
        'CFBundleDisplayName': 'KBase',
        'CFBundleVersion': '0.2.0',
        'CFBundleShortVersionString': '0.2.0',
        'NSHighResolutionCapable': True,
        'LSMinimumSystemVersion': '10.15',
        'NSHumanReadableCopyright': 'Copyright@PenguinMiaou',
    },
)
