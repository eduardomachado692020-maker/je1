@echo on
setlocal enabledelayedexpansion

rem ===== AJUSTE ESTES 2 ITENS, SE PRECISAR =====
set "PROJECT_DIR=C:\Users\ruthp\Downloads\StellaVisionMG_EXE_PATCH2_FIXED\StellaVisionMG_EXE_PATCH2_FIXED\StellaVisionMG"
set "PYTHON=python"
rem =============================================

echo.
echo [1/6] Fechando processos nas portas 5000 e 5001...
for /f "tokens=5" %%p in ('netstat -aon ^| findstr :5000') do taskkill /F /PID %%p 2>nul
for /f "tokens=5" %%p in ('netstat -aon ^| findstr :5001') do taskkill /F /PID %%p 2>nul

echo [2/6] (Opcional) Matando EXE/py remanescentes...
taskkill /F /IM StellaVisionMG.exe /T 2>nul
taskkill /F /IM python.exe /T 2>nul

echo [3/6] Conferindo caminho do projeto...
if not exist "%PROJECT_DIR%\app.py" (
  echo ERRO: app.py nao encontrado em "%PROJECT_DIR%"
  echo Verifique a variavel PROJECT_DIR no .bat.
  pause
  exit /b 1
)

echo [4/6] Indo para a pasta do projeto...
cd /d "%PROJECT_DIR%" || (
  echo ERRO ao entrar na pasta do projeto.
  pause
  exit /b 1
)

echo [5/6] Definindo porta 5001...
set "PORT=5001"

echo [6/6] Subindo servidor em python (log: run_5001.log)...
echo ------------------------------------------------------- >> "%PROJECT_DIR%\run_5001.log"
echo Iniciado em %date% %time% >> "%PROJECT_DIR%\run_5001.log"

"%PYTHON%" app.py 1>>"%PROJECT_DIR%\run_5001.log" 2>&1

echo.
echo O Python saiu com ERRORLEVEL=%errorlevel%.
echo Veja o log em: "%PROJECT_DIR%\run_5001.log"
pause

