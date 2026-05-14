$host.UI.RawUI.WindowTitle = "Сервис оценки чатов"
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Сервис оценки чатов сотрудников" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $scriptDir

Write-Host "Установка зависимостей..." -ForegroundColor Yellow
$pipResult = python -m pip install -r (Join-Path $scriptDir "requirements.txt") 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "Ошибка установки зависимостей:" -ForegroundColor Red
    Write-Host $pipResult -ForegroundColor Red
    Read-Host "Нажмите Enter для выхода"
    exit 1
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "  Откройте в браузере:" -ForegroundColor Green
Write-Host "  http://localhost:8000" -ForegroundColor White
Write-Host "============================================" -ForegroundColor Green
Write-Host ""
Write-Host "Для остановки закройте это окно" -ForegroundColor DarkGray
Write-Host ""

Start-Process "http://localhost:8000"
python -m uvicorn main:app --host 0.0.0.0 --port 8000
