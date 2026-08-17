@echo off
cd /d "%~dp0"
echo Iniciando AudioTo-txt com o ambiente audio...
"%~dp0audio\Scripts\python.exe" app.py
if errorlevel 1 pause
