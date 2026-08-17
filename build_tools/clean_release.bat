@echo off
setlocal EnableExtensions
cd /d "%~dp0.."
if errorlevel 1 (
  echo CLEAN ABORT
  exit /b 1
)

set "TARGET=%CD%\release"
for %%I in ("%TARGET%") do set "NAME=%%~nxI"
if /I not "%NAME%"=="release" (
  echo CLEAN ABORT: unerwarteter Zielordner "%TARGET%"
  exit /b 1
)

if not exist "%TARGET%" (
  echo Nichts zu loeschen.
  exit /b 0
)

echo Loesche "%TARGET%"
rmdir /s /q "%TARGET%"
if exist "%TARGET%" (
  echo CLEAN FAIL
  exit /b 1
)
echo CLEAN OK
exit /b 0
