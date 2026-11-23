@echo off
chcp 65001 >nul
rem Демо-дані: акаунти всіх ролей, заявки з історією статусів, журнал аудиту (KAN-66).
rem Пароль демо-акаунтів Demo12345 (лише для локального запуску).

cd /d "%~dp0..\..\backend"
if not exist ".venv" (echo Спершу запусти 1-setup-backend.bat & goto :end)
call .venv\Scripts\activate.bat
python -m app.scripts.seed_demo_data
:end
pause
