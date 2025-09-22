@echo off
SETLOCAL
cd /d "%~dp0"
echo === Building EXE (onefile) ===
pip install -U pip
pip install pyinstaller==6.8.0
pyinstaller app.py --name "StellaVisionMG" --onefile --windowed ^
 --add-data "templates;templates" --add-data "static;static"
echo.
echo Build completo! Executavel em: dist\StellaVisionMG.exe
pause
