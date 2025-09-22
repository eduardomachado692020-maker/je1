@echo off
cd /d "%~dp0"
if exist ".\dist\StellaVisionMG.exe" (
  ".\dist\StellaVisionMG.exe"
) else (
  echo Nao encontrei dist\StellaVisionMG.exe. Rode primeiro o build.bat.
)
pause
