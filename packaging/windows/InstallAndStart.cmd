@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-shortcut.ps1"
if errorlevel 1 (
  echo Installation failed. Please keep this folder in a writable location and try again.
  pause
)
