@echo off
setlocal EnableExtensions
cd /d "%~dp0.."
if errorlevel 1 (
  echo INSTALLER ABORTED: Projektroot nicht erreichbar.
  exit /b 1
)

python --version
if errorlevel 1 (
  echo INSTALLER ABORTED: Python nicht gefunden.
  exit /b 1
)

python build_tools\create_installer.py %*
if errorlevel 1 (
  echo INSTALLER ABORTED
  exit /b 1
)

echo INSTALLER OK
exit /b 0
