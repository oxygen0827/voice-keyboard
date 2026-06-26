@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" -u -m agent.windows.tray
