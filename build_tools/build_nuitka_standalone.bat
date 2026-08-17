@echo off
setlocal EnableExtensions
cd /d "%~dp0.."
if errorlevel 1 (
  echo BUILD ABORT: Projektroot nicht erreichbar.
  exit /b 1
)

echo === Python ===
python --version
if errorlevel 1 (
  echo BUILD ABORT: Python nicht gefunden.
  exit /b 1
)

echo === Nuitka ===
python -m nuitka --version
if errorlevel 1 (
  echo BUILD ABORT: Nuitka nicht installiert.
  exit /b 1
)

echo === Tests ===
python -m pytest
if errorlevel 1 (
  echo BUILD ABORT
  exit /b 1
)

echo === Nuitka standalone ===
python build_tools\nuitka_standalone.py
if errorlevel 1 (
  echo BUILD ABORT
  exit /b 1
)

echo BUILD OK
exit /b 0
