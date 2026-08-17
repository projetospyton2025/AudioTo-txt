@echo off
cd /d "%~dp0"
set PYTHONUNBUFFERED=1
echo Iniciando AudioTo-txt com o ambiente audio...
echo Aguarde o Python carregar (pode levar cerca de 1 minuto).
"%~dp0audio\Scripts\python.exe" -u app.py
if errorlevel 1 pause
