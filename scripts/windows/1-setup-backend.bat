@echo off
chcp 65001 >nul
rem Перше налаштування бекенду БЕЗ Docker: віртуальне середовище, бібліотеки, база, таблиці.
rem Потрібно: Python 3.12+ і PostgreSQL з PostGIS. Запускати один раз (або після оновлення коду).

cd /d "%~dp0..\.."
if not exist ".env" (
    copy ".env.example" ".env" >nul
    echo Створено файл .env з шаблону. Впиши в нього користувача й пароль PostgreSQL і запусти скрипт ще раз.
    notepad ".env"
    goto :end
)

cd backend
where python >nul 2>nul || (echo Python не знайдено. Встанови Python 3.12+ з python.org з галочкою "Add python.exe to PATH". & goto :fail)
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)" || (echo Потрібен Python 3.12 або новіший. & goto :fail)

if not exist ".venv" (
    echo [1/4] Створюю віртуальне середовище...
    python -m venv .venv || goto :fail
)
call .venv\Scripts\activate.bat || goto :fail

echo [2/4] Встановлюю бібліотеки (перший раз кілька хвилин)...
python -m pip install --quiet --upgrade pip || goto :fail
pip install --quiet -r requirements-dev.txt || goto :fail

echo [3/4] Створюю базу даних...
python -m app.scripts.create_database || goto :fail

echo [4/4] Створюю таблиці й довідники...
alembic upgrade head || goto :fail

echo.
echo Готово. Тепер запусти 2-run-backend.bat
goto :end

:fail
echo.
echo ПОМИЛКА. Зроби скріншот цього вікна.
:end
pause
