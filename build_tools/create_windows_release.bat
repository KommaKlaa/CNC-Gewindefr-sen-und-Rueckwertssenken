@echo off
setlocal EnableExtensions
cd /d "%~dp0.."
if errorlevel 1 (
  echo WINDOWS RELEASE ABORTED: Projektroot nicht erreichbar.
  exit /b 1
)

python --version
if errorlevel 1 (
  echo WINDOWS RELEASE ABORTED: Python nicht gefunden.
  exit /b 1
)

python build_tools\create_windows_release.py %*
if errorlevel 1 (
  echo WINDOWS RELEASE ABORTED
  exit /b 1
)

echo WINDOWS RELEASE OK
exit /b 0
