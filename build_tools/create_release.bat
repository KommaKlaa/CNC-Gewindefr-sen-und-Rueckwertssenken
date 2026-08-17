@echo off
setlocal EnableExtensions
cd /d "%~dp0.."
if errorlevel 1 (
  echo RELEASE ABORTED: Projektroot nicht erreichbar.
  exit /b 1
)

python --version
if errorlevel 1 (
  echo RELEASE ABORTED: Python nicht gefunden.
  exit /b 1
)

python build_tools\create_release.py %*
if errorlevel 1 (
  echo RELEASE ABORTED
  exit /b 1
)

echo RELEASE OK
exit /b 0
