@echo off
python "%~dp0launcher.py"
if errorlevel 1 (
    echo.
    echo ОШИБКА: Python не найден.
    echo Установите Python: https://www.python.org/downloads/
    echo.
    pause
)
