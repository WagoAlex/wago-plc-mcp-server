# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for wago-mcp-server.exe (the HTTP MCP server)."""

from PyInstaller.utils.hooks import collect_all, collect_submodules

datas_mcp,     binaries_mcp,     hiddenimports_mcp     = collect_all('mcp')
datas_uvicorn, binaries_uvicorn, hiddenimports_uvicorn = collect_all('uvicorn')
datas_httpx,   binaries_httpx,   hiddenimports_httpx   = collect_all('httpx')

a = Analysis(
    ['../../src/main.py'],
    pathex=['../../src'],
    binaries=binaries_mcp + binaries_uvicorn + binaries_httpx,
    datas=datas_mcp + datas_uvicorn + datas_httpx + [('../../_env', '.')],
    hiddenimports=(
        hiddenimports_mcp
        + hiddenimports_uvicorn
        + hiddenimports_httpx
        + ['logging_config', 'plc_manager', 'enricher', 'wda_client']
        + collect_submodules('loguru')
        + collect_submodules('dotenv')
    ),
    hookspath=[],
    runtime_hooks=[],
    excludes=['tkinter', 'test', 'unittest'],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='wago-mcp-server',
    debug=False,
    strip=False,
    upx=True,
    console=True,
    icon=None,
)
