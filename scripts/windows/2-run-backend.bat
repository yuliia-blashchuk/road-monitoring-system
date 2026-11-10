@echo off
chcp 65001 >nul
rem Запуск бекенду БЕЗ Docker. Спершу один раз виконай 1-setup-backend.bat.

cd /d "%~dp0..\..\backend"
if not exist ".venv" (echo Спершу запусти 1-setup-backend.bat & goto :fail)
call .venv\Scripts\activate.bat || goto :fail

alembic upgrade head || goto :fail
echo.
echo Бекенд запущено: http://localhost:8000/docs
echo Щоб зупинити, натисни Ctrl+C у цьому вікні.
echo.
uvicorn app.main:app --reload --port 8000
goto :end

:fail
echo.
echo ПОМИЛКА. Зроби скріншот цього вікна.
:end
pause
