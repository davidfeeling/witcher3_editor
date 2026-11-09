@echo off
rem Abre el editor de partidas de The Witcher 3 (Remaster)
cd /d "%~dp0"
where pythonw >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw "%~dp0w3editor_gui.py"
) else (
    py -3 "%~dp0w3editor_gui.py"
    if errorlevel 1 pause
)
