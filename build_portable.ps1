param(
  [string]$PythonVersion = "3.12.8",
  [string]$OutputDir = "build\PowerBIDataDTL-portable",
  [string]$ZipPath = "",
  [switch]$SkipDownload
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

function Write-Step($Text) {
  Write-Host ""
  Write-Host "==> $Text" -ForegroundColor Cyan
}

function Ensure-Command($Name, $Message) {
  if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
    throw $Message
  }
}

Ensure-Command "npm" "Không tìm thấy npm. Cần Node.js trên máy build portable."

$OutputPath = Join-Path $Root $OutputDir
$CacheDir = Join-Path $Root "build\cache"
$PythonZip = Join-Path $CacheDir "python-$PythonVersion-embed-amd64.zip"
$PythonUrl = "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-embed-amd64.zip"
$GetPip = Join-Path $CacheDir "get-pip.py"
if ([string]::IsNullOrWhiteSpace($ZipPath)) {
  $ZipPath = Join-Path $Root "build\PowerBIDataDTL-portable.zip"
} elseif (-not [System.IO.Path]::IsPathRooted($ZipPath)) {
  $ZipPath = Join-Path $Root $ZipPath
}

Write-Step "Build frontend dist"
if (-not (Test-Path "node_modules")) {
  npm install
}
npm run build

Write-Step "Chuẩn bị thư mục portable"
if (Test-Path $OutputPath) {
  Remove-Item -Recurse -Force $OutputPath
}
New-Item -ItemType Directory -Force $OutputPath | Out-Null
New-Item -ItemType Directory -Force $CacheDir | Out-Null

if (-not $SkipDownload) {
  if (-not (Test-Path $PythonZip)) {
    Write-Step "Tải Python embeddable $PythonVersion"
    Invoke-WebRequest -Uri $PythonUrl -OutFile $PythonZip
  }
  if (-not (Test-Path $GetPip)) {
    Write-Step "Tải get-pip.py"
    Invoke-WebRequest -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile $GetPip
  }
}

if (-not (Test-Path $PythonZip)) {
  throw "Thiếu $PythonZip. Bỏ -SkipDownload hoặc đặt Python embeddable zip vào build\cache."
}
if (-not (Test-Path $GetPip)) {
  throw "Thiếu $GetPip. Bỏ -SkipDownload hoặc đặt get-pip.py vào build\cache."
}

Write-Step "Giải nén Python portable"
$PortablePython = Join-Path $OutputPath "python"
Expand-Archive -Path $PythonZip -DestinationPath $PortablePython -Force
$PthFile = Get-ChildItem $PortablePython -Filter "python*._pth" | Select-Object -First 1
if ($PthFile) {
  $PthLines = Get-Content $PthFile.FullName
  $RequiredPaths = @("..", "..\sync")
  foreach ($RequiredPath in $RequiredPaths) {
    if ($PthLines -notcontains $RequiredPath) {
      $PthLines = @($RequiredPath) + $PthLines
    }
  }
  $PthText = ($PthLines -join "`r`n")
  if ($PthText -notmatch "(?m)^import site$") {
    $PthText = $PthText -replace "#import site", "import site"
  }
  Set-Content -Path $PthFile.FullName -Value $PthText -Encoding ASCII
}

Write-Step "Cài Python packages vào portable"
$PortablePythonExe = Join-Path $PortablePython "python.exe"
& $PortablePythonExe $GetPip --no-warn-script-location
& $PortablePythonExe -m pip install --no-warn-script-location -r "sync\requirements.txt"

Write-Step "Copy ứng dụng"
robocopy "dist" (Join-Path $OutputPath "dist") /E | Out-Null
robocopy "sync" (Join-Path $OutputPath "sync") /E `
  /XD ".venv" "__pycache__" ".pytest_cache" ".preview_cache" "exports" "logs" "downloads" "uploads" "tests" `
  /XF "*.pyc" "*.pyo" ".env" "config.yaml" "config.yaml.bak" | Out-Null
Copy-Item "README.md" (Join-Path $OutputPath "README.md") -Force
Copy-Item "agent.md" (Join-Path $OutputPath "agent.md") -Force

$SyncOutput = Join-Path $OutputPath "sync"
New-Item -ItemType Directory -Force (Join-Path $SyncOutput "logs") | Out-Null
New-Item -ItemType Directory -Force (Join-Path $SyncOutput "downloads") | Out-Null
New-Item -ItemType Directory -Force (Join-Path $SyncOutput "uploads") | Out-Null
Set-Content -Path (Join-Path $SyncOutput "logs\.gitkeep") -Value "" -Encoding ASCII
Set-Content -Path (Join-Path $SyncOutput "downloads\.gitkeep") -Value "" -Encoding ASCII
Set-Content -Path (Join-Path $SyncOutput "uploads\.gitkeep") -Value "" -Encoding ASCII
Copy-Item (Join-Path $SyncOutput "config.example.yaml") (Join-Path $SyncOutput "config.yaml") -Force
Copy-Item (Join-Path $SyncOutput ".env.example") (Join-Path $SyncOutput ".env") -Force

Write-Step "Tạo launcher portable"
$RunPs1 = @'
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
$ConfigPath = Join-Path $Root "sync\config.yaml"
if (-not (Test-Path $ConfigPath)) {
  Copy-Item (Join-Path $Root "sync\config.example.yaml") $ConfigPath
}
$EnvPath = Join-Path $Root "sync\.env"
if (-not (Test-Path $EnvPath)) {
  Copy-Item (Join-Path $Root "sync\.env.example") $EnvPath
}
$AppUrl = "http://127.0.0.1:8765/"
$ServerJob = Start-Job -ScriptBlock {
  param($RootPath)
  Set-Location $RootPath
  & ".\python\python.exe" ".\sync\main.py" --config ".\sync\config.yaml" start
} -ArgumentList $Root
for ($i = 0; $i -lt 30; $i++) {
  try {
    Invoke-WebRequest -UseBasicParsing "$AppUrl`api/health" -TimeoutSec 1 | Out-Null
    Start-Process $AppUrl
    break
  } catch {
    Start-Sleep -Seconds 1
  }
}
Wait-Job $ServerJob | Out-Null
Receive-Job $ServerJob
'@
Set-Content -Path (Join-Path $OutputPath "run-portable.ps1") -Value $RunPs1 -Encoding UTF8

$RunBat = @'
@echo off
cd /d "%~dp0"
where pwsh >nul 2>nul
if %errorlevel%==0 (
  pwsh -ExecutionPolicy Bypass -File "%~dp0run-portable.ps1"
) else (
  powershell -ExecutionPolicy Bypass -File "%~dp0run-portable.ps1"
)
pause
'@
Set-Content -Path (Join-Path $OutputPath "run-portable.bat") -Value $RunBat -Encoding ASCII

$PortableReadme = @"
PowerBI Data DTL Portable

Chay nhanh:
  run-portable.bat

Giao dien:
  http://127.0.0.1:8765/

Lan dau tren may moi:
1. Giai nen file zip vao mot thu muc bat ky, vi du D:\PowerBIDataDTL.
2. Sua sync\.env: PG_HOST, PG_PORT, PG_DATABASE, PG_USER, PG_PASSWORD.
3. Mo run-portable.bat, vao man hinh Cau hinh Sync va them job file Excel/CSV.
4. Bam Test ket noi, Dry run, roi chay thu job.

Lenh CLI huu ich:
  .\python\python.exe .\sync\main.py check-config
  .\python\python.exe .\sync\main.py test-db
  .\python\python.exe .\sync\main.py run-all --force
  .\python\python.exe .\sync\main.py start

Ghi chu bao mat:
- Bundle nay khong copy sync\.env, sync\config.yaml, logs, uploads, downloads tu may build.
- File sync\config.yaml trong bundle duoc tao tu template va cac job mau dang disabled.
- Khi muon chuyen cau hinh that sang may khac, dung Backup & Restore trong app hoac copy rieng sync\config.yaml, sync\.env va sync\uploads.
"@
Set-Content -Path (Join-Path $OutputPath "README_PORTABLE.txt") -Value $PortableReadme -Encoding UTF8

Write-Step "Nén portable zip"
if (Test-Path $ZipPath) {
  Remove-Item -Force $ZipPath
}
Compress-Archive -Path (Join-Path $OutputPath "*") -DestinationPath $ZipPath -Force

Write-Host ""
Write-Host "Portable bundle da tao tai: $OutputPath" -ForegroundColor Green
Write-Host "Portable zip da tao tai: $ZipPath" -ForegroundColor Green
Write-Host "Chay: $OutputPath\run-portable.bat"
