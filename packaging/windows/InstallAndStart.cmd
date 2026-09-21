@echo off
setlocal
"%~dp0runtime\python.exe" "%~dp0app\scripts\windows_setup.py"
if errorlevel 1 (
  echo Installation failed. Please keep this folder in a writable location and try again.
  pause
)
