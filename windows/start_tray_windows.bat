@echo off
setlocal
cd /d "%~dp0"
set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" if exist "%CD%\..\.venv\Scripts\python.exe" set "PYTHON_EXE=%CD%\..\.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
  echo Python virtual environment not found.
  echo Create one at windows\.venv or reuse the repository root .venv.
  exit /b 1
)
"%PYTHON_EXE%" -u -m agent.windows.tray
