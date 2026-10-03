@echo off
REM ============================================================================
REM  OpenRotas Desktop — executar em modo DEV (sem instalar, direto do repo).
REM  Cria o ambiente virtual na 1a vez, instala as dependencias e abre o app
REM  numa janela nativa. Rode com clique duplo (ou pelo terminal) na raiz do repo.
REM ============================================================================
setlocal
cd /d "%~dp0\..\.."

echo [OpenRotas] Pasta do projeto: %cd%

if not exist "venv\Scripts\python.exe" (
  echo [OpenRotas] Criando ambiente virtual ^(primeira vez^)...
  py -3.12 -m venv venv || python -m venv venv
  echo [OpenRotas] Instalando dependencias ^(pode levar alguns minutos^)...
  venv\Scripts\python -m pip install --upgrade pip
  venv\Scripts\python -m pip install -r desktop\requirements-desktop.txt
)

echo [OpenRotas] Abrindo o software...
venv\Scripts\python desktop\app\launcher.py
endlocal
