@echo off
setlocal EnableExtensions

echo ============================================
echo           TeaCache Speedup Installer
echo ============================================
echo.

cd /d "%~dp0" 2>nul
if errorlevel 1 (
  echo ERROR: Could not change to the repository folder.
  exit /b 1
)

if not exist "venv\Scripts\activate.bat" (
  echo ERROR: The virtual environment was not found.
  echo Run Install.bat first.
  exit /b 1
)

call "venv\Scripts\activate.bat"
if errorlevel 1 (
  echo ERROR: Could not activate the virtual environment.
  exit /b 1
)

python -m comfyui_app.installer --install-teacache
if errorlevel 1 (
  echo WARNING: TeaCache installation did not complete successfully.
  endlocal
  exit /b 1
)

echo.
echo TeaCache is ready. Relaunch the app with Launch.bat.
endlocal
exit /b 0
