@echo off
setlocal
"%~dp0runtime\python.exe" "%~dp0app\scripts\windows_setup.py" --uninstall
if errorlevel 1 (
  echo Uninstall failed. Please close StudentAlbum and try again.
)
pause
