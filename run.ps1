param(
  [switch]$NoInstall,
  [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

function Test-Command($Name) {
  return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Write-Step($Text) {
  Write-Host ""
  Write-Host "==> $Text" -ForegroundColor Cyan
}

function Get-PythonCommand {
  if (Test-Command "py") { return @("py", "-3") }
  if (Test-Command "python") { return @("python") }
  throw "Không tìm thấy Python. Cài Python 3.11+ rồi chạy lại."
}

function Invoke-BasePython {
  param([string[]]$Arguments)
  if ($PythonCommand.Length -gt 1) {
    & $PythonCommand[0] $PythonCommand[1] @Arguments
  } else {
    & $PythonCommand[0] @Arguments
  }
}

if (-not (Test-Command "npm")) {
  throw "Không tìm thấy Node.js/npm. Cài Node.js LTS rồi chạy lại."
}

$PythonCommand = Get-PythonCommand
$VenvPython = Join-Path $Root "sync\.venv\Scripts\python.exe"

if (-not $NoInstall) {
  if (-not (Test-Path $VenvPython)) {
    Write-Step "Tạo Python virtual environment"
    Invoke-BasePython @("-m", "venv", "sync\.venv")
  }

  Write-Step "Cài Python packages"
  & $VenvPython -m pip install -r "sync\requirements.txt"

  if (-not (Test-Path "node_modules")) {
    Write-Step "Cài Node packages"
    npm install
  }
}

if (-not (Test-Path "sync\.env") -and (Test-Path "sync\.env.example")) {
  Copy-Item "sync\.env.example" "sync\.env"
  Write-Host "Đã tạo sync\.env. Hãy sửa PG_HOST, PG_DATABASE, PG_USER, PG_PASSWORD nếu cần." -ForegroundColor Yellow
}

Write-Step "Kiểm tra config"
& $VenvPython "sync\main.py" check-config

$Shell = if (Test-Command "pwsh") { "pwsh" } else { "powershell" }
$ApiCommand = "Set-Location '$Root'; & '$VenvPython' 'sync\main.py' start"
$WebCommand = "Set-Location '$Root'; npm run dev -- --port 5173"

Write-Step "Bật bộ chạy lịch + API"
$ApiProcess = Start-Process $Shell -ArgumentList @("-NoExit", "-Command", $ApiCommand) -PassThru

Write-Step "Bật giao diện web"
$WebProcess = Start-Process $Shell -ArgumentList @("-NoExit", "-Command", $WebCommand) -PassThru

Start-Sleep -Seconds 3
if (-not $NoBrowser) {
  Start-Process "http://127.0.0.1:5173/"
}

Write-Host ""
Write-Host "Đã khởi động PowerBI Data DTL." -ForegroundColor Green
Write-Host "Frontend : http://127.0.0.1:5173/"
Write-Host "Sync API + lịch tự chạy : http://127.0.0.1:8765/"
Write-Host "API PID  : $($ApiProcess.Id)"
Write-Host "Web PID  : $($WebProcess.Id)"
Write-Host ""
Write-Host "Lần sau có thể chạy nhanh: .\run.ps1 -NoInstall"
