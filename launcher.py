import subprocess
import sys
import os
import webbrowser
import time

os.chdir(os.path.dirname(os.path.abspath(__file__)))

print("=" * 44)
print("   Сервис оценки чатов сотрудников")
print("=" * 44)
print()

print("Установка зависимостей...")
result = subprocess.run(
    [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
    cwd=os.path.dirname(os.path.abspath(__file__)),
    capture_output=True,
    text=True,
)
if result.returncode != 0:
    print("Ошибка установки зависимостей:")
    print(result.stderr)
    input("Нажмите Enter для выхода...")
    sys.exit(1)

print()
print("=" * 44)
print("   Откройте в браузере:")
print("   http://localhost:8000")
print("=" * 44)
print()
print("Для остановки закройте это окно")
print()

time.sleep(1)
webbrowser.open("http://localhost:8000")

subprocess.run(
    [sys.executable, "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
)
