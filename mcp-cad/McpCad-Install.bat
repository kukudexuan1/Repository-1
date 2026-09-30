@echo off
REM Optional dev/helper launcher. End users: double-click McpCad.Installer.exe instead.
setlocal
title mcp-cad Installer

echo.
echo ===============================================
echo   mcp-cad - AI + parametric CAD
echo   One-click installer for Claude, Cursor, etc.
echo ===============================================
echo.

set "EXE=%~dp0dist\mcp-cad\McpCad.Installer.exe"
if not exist "%EXE%" set "EXE=%~dp0McpCad.Installer.exe"

if not exist "%EXE%" (
    echo [ERROR] Could not find McpCad.Installer.exe
    echo.
    echo Please extract the full portable package so that
    echo McpCad.Installer.exe is in the same folder as this .bat
    echo (or inside a dist\mcp-cad subfolder).
    echo.
    pause
    exit /b 1
)

echo Launching mcp-cad installer wizard...
echo (Pass --tui for classic keyboard TUI, or --recommended for one-click CLI.)
echo.

"%EXE%" %*
set "INST_EXIT=%ERRORLEVEL%"

echo.
if not "%INST_EXIT%"=="0" (
    echo [ERROR] Installer exited with code %INST_EXIT%.
    echo.
)
echo ===============================================
echo Installation finished (or check messages above).
echo.
echo Remember:
echo   - Restart your AI client (Claude Desktop / Cursor / ...)
echo   - Keep your CAD app running when using the AI (Inventor or SolidWorks)
echo ===============================================
echo.
pause
endlocal & exit /b %INST_EXIT%