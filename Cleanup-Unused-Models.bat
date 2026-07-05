@echo off
setlocal EnableExtensions

echo ============================================
echo     ComfyUI Local Image App Model Cleanup
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

python -m comfyui_app.prune_models %*
if errorlevel 1 (
  echo ERROR: Model cleanup did not complete successfully.
  exit /b 1
)

echo.
echo Model cleanup complete.
endlocal
exit /b 0
