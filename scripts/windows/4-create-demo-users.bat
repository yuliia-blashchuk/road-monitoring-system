@echo off
chcp 65001 >nul
rem Демо-акаунти для кожної ролі, пароль Demo12345 (лише для локального запуску).

cd /d "%~dp0..\..\backend"
if not exist ".venv" (echo Спершу запусти 1-setup-backend.bat & goto :end)
call .venv\Scripts\activate.bat
python -m app.scripts.create_demo_users
:end
pause
