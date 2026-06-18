# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for wago-proxy.exe (stdio<->HTTP bridge for Claude Desktop)."""

from PyInstaller.utils.hooks import collect_all, collect_submodules

datas_fmcp, binaries_fmcp, hiddenimports_fmcp = collect_all('fastmcp')
datas_httpx, binaries_httpx, hiddenimports_httpx = collect_all('httpx')

a = Analysis(
    ['../../wago_proxy.py'],
    pathex=['../..'],
    binaries=binaries_fmcp + binaries_httpx,
    datas=datas_fmcp + datas_httpx,
    hiddenimports=(
        hiddenimports_fmcp
        + hiddenimports_httpx
        + collect_submodules('dotenv')
        + collect_submodules('anyio')
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
    name='wago-proxy',
    debug=False,
    strip=False,
    upx=True,
    console=True,
    icon=None,
)
