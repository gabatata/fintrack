@echo off
:: FinTrack - Inicia o app localmente, acessivel pelo celular via Tailscale.
:: Na primeira execucao, cria o ambiente e instala as dependencias sozinho.
setlocal
cd /d "%~dp0"

:: 1) Cria o ambiente virtual + instala dependencias na primeira vez
if not exist ".venv\Scripts\python.exe" (
    echo ============================================
    echo  Primeira execucao: preparando o ambiente.
    echo  Instalando dependencias - pode levar alguns
    echo  minutos. Aguarde ate aparecer "iniciando".
    echo ============================================
    python -m venv .venv
    if errorlevel 1 (
        echo.
        echo ERRO: Python nao encontrado. Instale em https://python.org
        echo e marque "Add Python to PATH" durante a instalacao.
        pause
        exit /b 1
    )
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
)

set "PY=.venv\Scripts\python.exe"

:: 2) Garante que o streamlit esta presente (caso a instalacao tenha falhado antes)
"%PY%" -c "import streamlit" 2>nul
if errorlevel 1 (
    echo Instalando dependencias que faltam...
    "%PY%" -m pip install -r requirements.txt
)

echo ============================================
echo  FinTrack - iniciando...
echo  No PC:       http://localhost:8501
echo  No celular:  http://[IP-TAILSCALE-DO-PC]:8501   (com Tailscale ligado)
echo  Descubra o IP rodando:  tailscale ip -4
echo ============================================
echo.

"%PY%" -m streamlit run app.py --server.address=0.0.0.0 --server.port=8501 --browser.gatherUsageStats=false

echo.
echo (O FinTrack foi encerrado, ou ocorreu o erro acima.)
pause
