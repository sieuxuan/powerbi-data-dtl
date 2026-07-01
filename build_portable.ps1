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
param(
  [switch]$NoBrowser
)

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
$PythonExe = Join-Path $Root "python\python.exe"
$LogsDir = Join-Path $Root "sync\logs"
New-Item -ItemType Directory -Force $LogsDir | Out-Null
$RuntimeLog = Join-Path $LogsDir "runtime.log"
$RuntimeErr = Join-Path $LogsDir "runtime.err.log"

function Test-ApiReady {
  try {
    Invoke-WebRequest -UseBasicParsing "$AppUrl`api/health" -TimeoutSec 1 | Out-Null
    return $true
  } catch {
    return $false
  }
}

function Invoke-ApiPost {
  param([string]$Path)
  Invoke-WebRequest -UseBasicParsing -Method Post "$AppUrl$Path" -TimeoutSec 5 | Out-Null
}

function Start-AppServer {
  if (Test-ApiReady) {
    return
  }
  $script:ServerProcess = Start-Process -FilePath $PythonExe `
    -ArgumentList @("sync\main.py", "--config", "sync\config.yaml", "start") `
    -WorkingDirectory $Root `
    -WindowStyle Hidden `
    -RedirectStandardOutput $RuntimeLog `
    -RedirectStandardError $RuntimeErr `
    -PassThru
  $script:OwnsServer = $true
}

function Stop-AppServer {
  if ($script:OwnsServer -and $script:ServerProcess -and -not $script:ServerProcess.HasExited) {
    Stop-Process -Id $script:ServerProcess.Id -Force -ErrorAction SilentlyContinue
  }
}

$OwnsServer = $false
$ServerProcess = $null
if (-not (Test-ApiReady)) {
  Start-AppServer
}

for ($i = 0; $i -lt 30; $i++) {
  if (Test-ApiReady) {
    if (-not $NoBrowser) {
      Start-Process $AppUrl
    }
    break
  }
  Start-Sleep -Seconds 1
}

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

function New-AppTrayIcon {
  $Bitmap = New-Object System.Drawing.Bitmap 32, 32
  $Graphics = [System.Drawing.Graphics]::FromImage($Bitmap)
  $Graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
  $Graphics.Clear([System.Drawing.Color]::Transparent)

  $BackgroundBrush = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(11, 18, 32))
  $AccentBrush = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(34, 197, 94))
  $BlueBrush = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(56, 189, 248))
  $PaperBrush = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(248, 250, 252))
  $BorderPen = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(148, 163, 184)), 1

  $Graphics.FillEllipse($BackgroundBrush, 1, 1, 30, 30)
  $Graphics.DrawEllipse($BorderPen, 1, 1, 30, 30)
  $Graphics.FillRectangle($BlueBrush, 9, 15, 4, 8)
  $Graphics.FillRectangle($AccentBrush, 15, 10, 4, 13)
  $Graphics.FillRectangle($PaperBrush, 21, 6, 4, 17)
  $Graphics.DrawLine($BorderPen, 7, 24, 26, 24)

  $Graphics.Dispose()
  $BackgroundBrush.Dispose()
  $AccentBrush.Dispose()
  $BlueBrush.Dispose()
  $PaperBrush.Dispose()
  $BorderPen.Dispose()

  $script:TrayIconBitmap = $Bitmap
  return [System.Drawing.Icon]::FromHandle($Bitmap.GetHicon())
}

$Context = New-Object System.Windows.Forms.ApplicationContext
$Tray = New-Object System.Windows.Forms.NotifyIcon
try {
  $script:TrayIcon = New-AppTrayIcon
  $Tray.Icon = $script:TrayIcon
} catch {
  $Tray.Icon = [System.Drawing.SystemIcons]::Application
}
$Tray.Text = "PowerBI Data DTL"
$Tray.Visible = $true

$Menu = New-Object System.Windows.Forms.ContextMenuStrip
$OpenItem = $Menu.Items.Add("Open dashboard")
$RunAllItem = $Menu.Items.Add("Run all")
$PauseSchedulerItem = $Menu.Items.Add("Pause scheduler")
$ResumeSchedulerItem = $Menu.Items.Add("Resume scheduler")
$RestartApiItem = $Menu.Items.Add("Restart API")
$Menu.Items.Add("-") | Out-Null
$FolderItem = $Menu.Items.Add("Open app folder")
$LogsItem = $Menu.Items.Add("Open logs")
$Menu.Items.Add("-") | Out-Null
$ExitItem = $Menu.Items.Add("Stop and exit")

$OpenItem.add_Click({ Start-Process $AppUrl })
$RunAllItem.add_Click({
  try {
    Invoke-ApiPost "api/run-all?force=false"
    $Tray.ShowBalloonTip(2500, "PowerBI Data DTL", "Run all command sent.", [System.Windows.Forms.ToolTipIcon]::Info)
  } catch {
    $Tray.ShowBalloonTip(3500, "PowerBI Data DTL", "Run all failed. Check runtime logs.", [System.Windows.Forms.ToolTipIcon]::Error)
  }
})
$PauseSchedulerItem.add_Click({
  try {
    Invoke-ApiPost "api/runtime/scheduler/pause"
    $Tray.ShowBalloonTip(2500, "PowerBI Data DTL", "Scheduler paused.", [System.Windows.Forms.ToolTipIcon]::Info)
  } catch {
    $Tray.ShowBalloonTip(3500, "PowerBI Data DTL", "Could not pause scheduler.", [System.Windows.Forms.ToolTipIcon]::Error)
  }
})
$ResumeSchedulerItem.add_Click({
  try {
    Invoke-ApiPost "api/runtime/scheduler/resume"
    $Tray.ShowBalloonTip(2500, "PowerBI Data DTL", "Scheduler resumed.", [System.Windows.Forms.ToolTipIcon]::Info)
  } catch {
    $Tray.ShowBalloonTip(3500, "PowerBI Data DTL", "Could not resume scheduler.", [System.Windows.Forms.ToolTipIcon]::Error)
  }
})
$RestartApiItem.add_Click({
  try {
    Stop-AppServer
    Start-Sleep -Seconds 1
    Start-AppServer
    for ($i = 0; $i -lt 20; $i++) {
      if (Test-ApiReady) { break }
      Start-Sleep -Milliseconds 500
    }
    $Tray.ShowBalloonTip(2500, "PowerBI Data DTL", "API restarted.", [System.Windows.Forms.ToolTipIcon]::Info)
  } catch {
    $Tray.ShowBalloonTip(3500, "PowerBI Data DTL", "Could not restart API.", [System.Windows.Forms.ToolTipIcon]::Error)
  }
})
$FolderItem.add_Click({ Start-Process $Root })
$LogsItem.add_Click({ Start-Process $LogsDir })
$ExitItem.add_Click({
  $Tray.Visible = $false
  Stop-AppServer
  $Context.ExitThread()
})

$Tray.ContextMenuStrip = $Menu
$Tray.add_DoubleClick({ Start-Process $AppUrl })
$Tray.ShowBalloonTip(3000, "PowerBI Data DTL", "App is running in the system tray.", [System.Windows.Forms.ToolTipIcon]::Info)

[System.Windows.Forms.Application]::Run($Context)
$Tray.Dispose()
if ($script:TrayIcon) { $script:TrayIcon.Dispose() }
if ($script:TrayIconBitmap) { $script:TrayIconBitmap.Dispose() }
'@
Set-Content -Path (Join-Path $OutputPath "run-portable.ps1") -Value $RunPs1 -Encoding UTF8

$RunBat = @'
@echo off
cd /d "%~dp0"
set "POWERSHELL_EXE=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
if not exist "%POWERSHELL_EXE%" set "POWERSHELL_EXE=powershell"
start "" "%POWERSHELL_EXE%" -NoProfile -ExecutionPolicy Bypass -STA -WindowStyle Hidden -File "%~dp0run-portable.ps1"
exit /b 0
'@
Set-Content -Path (Join-Path $OutputPath "run-portable.bat") -Value $RunBat -Encoding ASCII

$PortableReadme = @"
PowerBI Data DTL Portable

Chay nhanh:
  run-portable.bat

Giao dien:
  http://127.0.0.1:8765/

Sau khi chay, ung dung nam trong system tray. Bam dup icon tray de mo dashboard,
hoac chuot phai icon tray de Run all, Pause/Resume scheduler, Restart API,
mo thu muc log va dung runtime.

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
