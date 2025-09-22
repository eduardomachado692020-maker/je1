@echo off
REM === ERP Machado Games - Start (Windows) ===
setlocal enabledelayedexpansion

REM Descobrir diretório do script
set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

REM 1) Criar venv se não existir
if not exist ".venv" (
    py -3 -m venv .venv
)

REM 2) Ativar venv
call .venv\Scripts\activate.bat

REM 3) Instalar dependências
python -m pip install --upgrade pip
pip install -r requirements.txt

REM 4) Inicializar banco se não existir
if not exist "erp.db" (
    python init_db.py
    python seed.py
)

REM 5) Rodar app
set FLASK_APP=app.py
python app.py
