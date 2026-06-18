@echo off
setlocal enabledelayedexpansion
:: ─────────────────────────────────────────────────────────────────────────────
:: setup.bat  —  First-run configuration for wago-mcp-server on Windows
::
:: Run from the directory containing the .exe files.
:: Safe to re-run — never overwrites an existing .env.
:: ─────────────────────────────────────────────────────────────────────────────

set "HERE=%~dp0"
set "ENV_FILE=%HERE%.env"
set "TEMPLATE=%HERE%_env"

echo.
echo  WAGO PLC MCP Server — Windows Setup
echo =========================================
echo.

:: ── 1. Create .env from template if missing ───────────────────────────────
if exist "%ENV_FILE%" (
    echo [1/4] .env already exists — skipping copy.
) else (
    if not exist "%TEMPLATE%" (
        echo ERROR: _env template not found in %HERE%
        echo        Download a fresh release package and try again.
        pause & exit /b 1
    )
    copy /Y "%TEMPLATE%" "%ENV_FILE%" >nul
    echo [1/4] Created .env from template.
)

:: ── 2. Create data directory for audit log + fleet file ───────────────────
if not exist "%HERE%data\" (
    mkdir "%HERE%data"
    echo [2/4] Created data\ directory.
) else (
    echo [2/4] data\ directory already exists.
)

:: ── 3. Open .env in notepad for editing ───────────────────────────────────
echo [3/4] Opening .env in Notepad — set your PLC IPs and credentials, then save.
echo       (Close Notepad when done to continue.)
notepad "%ENV_FILE%"

:: ── 4. Print Claude Desktop snippet ───────────────────────────────────────
echo.
echo [4/4] Add this to your Claude Desktop config
echo       (%%APPDATA%%\Claude\claude_desktop_config.json):
echo.
echo {
echo   "mcpServers": {
echo     "wago-plc": {
echo       "command": "%HERE%wago-proxy.exe",
echo       "env": {
echo         "WAGO_MCP_URL": "http://localhost:6042/mcp"
echo       }
echo     }
echo   }
echo }
echo.
echo  If you set MCP_API_KEY in .env, also add:
echo    "WAGO_MCP_API_KEY": "your-key-here"
echo  inside the "env" block above.
echo.
echo ─────────────────────────────────────────────────────────────────────────────
echo  Next steps:
echo    1. Start the server:   double-click wago-mcp-server.exe
echo                           (or: sc create wago-mcp binPath= "%HERE%wago-mcp-server.exe")
echo    2. Restart Claude Desktop
echo    3. Ask Claude: "list my PLCs"
echo ─────────────────────────────────────────────────────────────────────────────
echo.
pause
