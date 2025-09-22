# ERP Machado Games - Start (PowerShell)
$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

if (!(Test-Path ".venv")) {
  py -3 -m venv .venv
}

& ".venv\Scripts\Activate.ps1"

python -m pip install --upgrade pip
pip install -r requirements.txt

if (!(Test-Path "erp.db")) {
  python init_db.py
  python seed.py
}

$env:FLASK_APP = "app.py"
python app.py
