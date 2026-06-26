@echo off
setlocal
cd /d "%~dp0"
set "PYINSTALLER_EXE=%CD%\.venv\Scripts\pyinstaller.exe"
if not exist "%PYINSTALLER_EXE%" if exist "%CD%\..\.venv\Scripts\pyinstaller.exe" set "PYINSTALLER_EXE=%CD%\..\.venv\Scripts\pyinstaller.exe"
if not exist "%PYINSTALLER_EXE%" (
  echo PyInstaller was not found.
  echo Install dependencies in windows\.venv or the repository root .venv first.
  exit /b 1
)
"%PYINSTALLER_EXE%" --clean --noconfirm packaging\windows\voice-keyboard-tray.spec
echo.
echo Built app: %CD%\dist\VoiceKeyboard\VoiceKeyboard.exe
pause
