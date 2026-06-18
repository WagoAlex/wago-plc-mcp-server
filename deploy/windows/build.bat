@echo off
setlocal enabledelayedexpansion
:: ─────────────────────────────────────────────────────────────────────────────
:: build.bat  —  Build wago-mcp-server.exe and wago-proxy.exe
::
:: Requirements: Python 3.11+ on PATH, internet access for pip
:: Run from anywhere — paths are relative to this script's directory.
:: ─────────────────────────────────────────────────────────────────────────────

set "ROOT=%~dp0..\.."
set "WIN=%~dp0"
set "DIST=%ROOT%\dist\windows"

echo.
echo [wago-build] Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: python not found on PATH. Install Python 3.11+ from python.org.
    pause & exit /b 1
)

echo [wago-build] Installing build dependencies...
python -m pip install --quiet --upgrade pip
python -m pip install --quiet pyinstaller fastmcp httpx python-dotenv "mcp[cli]" uvicorn loguru anyio typer
if errorlevel 1 (
    echo ERROR: pip install failed. Try running this script as Administrator,
    echo        or check your internet connection.
    pause & exit /b 1
)

echo.
echo [wago-build] Building wago-mcp-server.exe...
python -m PyInstaller "%WIN%server.spec" --distpath "%DIST%" --workpath "%ROOT%\build\server" --noconfirm
if errorlevel 1 (
    echo ERROR: server build failed.
    pause & exit /b 1
)

echo.
echo [wago-build] Building wago-proxy.exe...
python -m PyInstaller "%WIN%proxy.spec" --distpath "%DIST%" --workpath "%ROOT%\build\proxy" --noconfirm
if errorlevel 1 (
    echo ERROR: proxy build failed.
    pause & exit /b 1
)

echo.
echo [wago-build] Copying config template...
copy /Y "%WIN%_env.windows" "%DIST%\_env" >nul

echo.
echo ─────────────────────────────────────────────────────────────────────────────
echo  Build complete:  %DIST%\
echo    wago-mcp-server.exe  — the MCP server (run this first)
echo    wago-proxy.exe       — stdio bridge for Claude Desktop
echo    _env                 — config template (run setup.bat to configure)
echo ─────────────────────────────────────────────────────────────────────────────
echo.
pause
