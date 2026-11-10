@echo off
chcp 65001 >nul
rem Автотести бекенду БЕЗ Docker. Тести працюють з окремою базою <назва>_test.

cd /d "%~dp0..\..\backend"
if not exist ".venv" (echo Спершу запусти 1-setup-backend.bat & goto :end)
call .venv\Scripts\activate.bat
pytest
:end
pause
