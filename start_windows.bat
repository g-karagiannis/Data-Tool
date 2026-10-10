@echo off
title Ergaleio Analysis Dedomenon
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Dimiourgia apomonomenou periballontos Python ^(.venv^)...
    python -m venv .venv
)
echo Elegchos / egkatastasi apaitoumenon paketon...
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul 2>&1
".venv\Scripts\python.exe" -m pip install -r requirements-lock.txt
echo.
echo Ekkinisi efarmogis... Tha anoixei aftomata sto browser.
".venv\Scripts\python.exe" -m streamlit run app.py
pause
