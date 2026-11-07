# -*- mode: python ; coding: utf-8 -*-
import sys
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

backend_dir = os.path.abspath(SPECPATH if 'SPECPATH' in globals() else os.getcwd())

hidden_imports = [
    'uvicorn',
    'uvicorn.logging',
    'uvicorn.loops',
    'uvicorn.loops.auto',
    'uvicorn.protocols',
    'uvicorn.protocols.http',
    'uvicorn.protocols.http.auto',
    'uvicorn.protocols.http.h11_impl',
    'uvicorn.protocols.websockets',
    'uvicorn.protocols.websockets.auto',
    'uvicorn.lifespans',
    'uvicorn.lifespans.on',
    'fastapi',
    'starlette',
    'pydantic',
    'pydantic_core',
    'scipy',
    'scipy.stats',
    'scipy.special',
    'scipy.spatial',
    'scipy.optimize',
    'scipy.linalg',
    'pandas',
    'numpy',
    'cryptography',
    'openpyxl',
    'reportlab',
    'sqlite3',
]

try:
    hidden_imports += collect_submodules('engine')
    hidden_imports += collect_submodules('data')
    hidden_imports += collect_submodules('reporting')
    hidden_imports += collect_submodules('core')
except Exception as e:
    print(f"Warning collecting submodules: {e}")

datas = []
reporting_templates = os.path.join(backend_dir, 'reporting', 'templates')
if os.path.exists(reporting_templates):
    datas.append((reporting_templates, 'reporting/templates'))

tests_data = os.path.join(backend_dir, 'tests', 'data')
if os.path.exists(tests_data):
    datas.append((tests_data, 'tests/data'))

a = Analysis(
    ['server_entry.py'],
    pathex=[backend_dir],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'PyQt5', 'PySide2', 'wx', 'IPython', 'jupyter'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='statsem-backend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
