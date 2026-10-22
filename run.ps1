# ═══════════════════════════════════════════════════════════════
#  🚀 ERP Test Automation - Run All Services
#  أمر واحد يشغّل: Docker + Flask + Cloudflare Tunnels
# ═══════════════════════════════════════════════════════════════

param(
    [switch]$SkipDocker,       # تخطى Docker check
    [switch]$SkipTunnel,       # تخطى Cloudflare Tunnel
    [switch]$SkipBrowser,      # متفتحش المتصفح
    [string]$Mode = "prod"     # prod = Grid + Tunnel | dev = Local Chrome
)

$ErrorActionPreference = "Continue"
$BASE_DIR = $PSScriptRoot
$LOG_DIR = Join-Path $BASE_DIR "data\logs"
$CONFIG_DIR = Join-Path $BASE_DIR "config"
$TUNNEL_CONFIG = Join-Path $BASE_DIR "data\settings\tunnel_config.json"
$CF_LOG_FLASK = Join-Path $LOG_DIR "cf_flask.log"
$CF_LOG_VNC = Join-Path $LOG_DIR "cf_vnc.log"

# ═══════════════════════════════════════════════════════════════
# Helper Functions
# ═══════════════════════════════════════════════════════════════

function Write-Header {
    param([string]$Text)
    Write-Host ""
    Write-Host "  ──────────────────────────────────────────" -ForegroundColor DarkGray
    Write-Host "  $Text" -ForegroundColor Cyan
    Write-Host "  ──────────────────────────────────────────" -ForegroundColor DarkGray
}

function Write-Step {
    param([string]$Num, [string]$Text)
    Write-Host ""
    Write-Host "  [$Num] $Text" -ForegroundColor Yellow
}

function Write-Ok   { Write-Host "     ✅ $args" -ForegroundColor Green }
function Write-Info { Write-Host "     ℹ️  $args" -ForegroundColor Cyan }
function Write-Warn { Write-Host "     ⚠️  $args" -ForegroundColor Yellow }
function Write-Err  { Write-Host "     ❌ $args" -ForegroundColor Red }

# ═══════════════════════════════════════════════════════════════
# Start
# ═══════════════════════════════════════════════════════════════

Clear-Host
Write-Host ""
Write-Host "  ╔══════════════════════════════════════════════════════╗" -ForegroundColor Magenta
Write-Host "  ║                                                      ║" -ForegroundColor Magenta
Write-Host "  ║       🚀  ERP Test Automation - Startup              ║" -ForegroundColor Magenta
Write-Host "  ║                                                      ║" -ForegroundColor Magenta
Write-Host "  ╚══════════════════════════════════════════════════════╝" -ForegroundColor Magenta

Write-Info "Mode: $Mode"
Write-Info "Base: $BASE_DIR"

if (-not (Test-Path $LOG_DIR)) {
    New-Item -ItemType Directory -Path $LOG_DIR -Force | Out-Null
}

# ═══════════════════════════════════════════════════════════════
# [0/6] Preflight Checks
# ═══════════════════════════════════════════════════════════════

Write-Step "0/6" "فحص المتطلبات..."

if (-not (Test-Path "$BASE_DIR\venv\Scripts\Activate.ps1")) {
    Write-Err "venv مش موجود. شغّل: python -m venv venv"
    exit 1
}
Write-Ok "venv موجود"

if (-not (Test-Path "$BASE_DIR\web\app.py")) {
    Write-Err "web\app.py مش موجود"
    exit 1
}
Write-Ok "Flask app موجود"

# ═══════════════════════════════════════════════════════════════
# [1/6] Stop Old Processes
# ═══════════════════════════════════════════════════════════════

Write-Step "1/6" "إغلاق العمليات القديمة..."

$stopped = 0

# Flask
$pyProcs = Get-Process python -ErrorAction SilentlyContinue
if ($pyProcs) {
    $pyProcs | Stop-Process -Force -ErrorAction SilentlyContinue
    Write-Ok "اتقفل Flask ($($pyProcs.Count) عملية)"
    $stopped++
} else {
    Write-Info "مفيش Flask شغال"
}

# cloudflared
$cfProcs = Get-Process cloudflared -ErrorAction SilentlyContinue
if ($cfProcs) {
    $cfProcs | Stop-Process -Force -ErrorAction SilentlyContinue
    Write-Ok "اتقفل cloudflared ($($cfProcs.Count) عملية)"
    $stopped++
} else {
    Write-Info "مفيش cloudflared شغال"
}

Start-Sleep -Seconds 2

# ═══════════════════════════════════════════════════════════════
# [2/6] Docker Check
# ═══════════════════════════════════════════════════════════════

Write-Step "2/6" "فحص Docker و Selenium Grid..."

if ($SkipDocker) {
    Write-Info "اتخطى Docker (SkipDocker)"
} else {
    # شوف Docker
    $dockerOk = $false
    try {
        $dockerPs = docker ps 2>&1
        if ($LASTEXITCODE -eq 0) { $dockerOk = $true }
    } catch { $dockerOk = $false }

    if (-not $dockerOk) {
        Write-Warn "Docker مش شغال - شغّله من Desktop"
        Write-Info "بستمر بدون Selenium Grid"
    } else {
        Write-Ok "Docker شغال"

        # شوف selenium-chrome
        $selContainer = docker ps --filter "name=selenium-chrome" --format "{{.Names}}" 2>&1
        if ($selContainer -match "selenium-chrome") {
            Write-Ok "selenium-chrome شغال"
        } else {
            Write-Info "selenium-chrome مش شغال - بحاول أشغّله..."

            $selExists = docker ps -a --filter "name=selenium-chrome" --format "{{.Names}}" 2>&1
            if ($selExists -match "selenium-chrome") {
                docker start selenium-chrome 2>&1 | Out-Null
                Write-Ok "selenium-chrome اتشغّل"
            } else {
                Write-Info "selenium-chrome مش موجود - بنزّله..."
                docker run -d --name selenium-chrome `
                    -p 4444:4444 -p 7900:7900 `
                    --shm-size="2g" `
                    selenium/standalone-chrome:latest 2>&1 | Out-Null
                Write-Ok "selenium-chrome اتنزّل واتشغّل"
            }
            Start-Sleep -Seconds 5
        }
    }
}

# ═══════════════════════════════════════════════════════════════
# [3/6] Start Flask
# ═══════════════════════════════════════════════════════════════

Write-Step "3/6" "تشغيل Flask..."

# اجلب إعدادات Grid
$env_grid = if ($Mode -eq "dev") { "false" } else { "true" }

$flaskCmd = @"
Set-Location '$BASE_DIR'
`$env:USE_SELENIUM_GRID = '$env_grid'
& '$BASE_DIR\venv\Scripts\Activate.ps1'
Write-Host '🚀 Flask Server (Mode: $Mode)' -ForegroundColor Green
python web\app.py
"@

Start-Process powershell -ArgumentList "-NoExit", "-Command", $flaskCmd
Write-Ok "Flask بدأ في نافذة منفصلة"

# انتظر Flask يشتغل
Write-Info "بانتظار Flask... (5 ثواني)"
Start-Sleep -Seconds 5

$flaskUp = $false
for ($i = 0; $i -lt 5; $i++) {
    try {
        $r = Invoke-WebRequest -Uri "http://localhost:5000/login" -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
        if ($r.StatusCode -eq 200) {
            $flaskUp = $true
            break
        }
    } catch {
        Start-Sleep -Seconds 2
    }
}

if ($flaskUp) {
    Write-Ok "Flask شغال على http://localhost:5000"
} else {
    Write-Warn "Flask مش بيرد - تأكد من النافذة"
}

# ═══════════════════════════════════════════════════════════════
# [4/6] Cloudflare Tunnel - Flask
# ═══════════════════════════════════════════════════════════════

$flaskUrl = $null
$vncUrl = $null

if ($SkipTunnel) {
    Write-Info "اتخطى Cloudflare Tunnel"
} else {
    Write-Step "4/6" "تشغيل Cloudflare Tunnel - Flask (5000)..."

    if (-not (Test-Path "$BASE_DIR\cloudflared.exe")) {
        Write-Warn "cloudflared.exe مش موجود - اتخطى"
    } else {
        if (Test-Path $CF_LOG_FLASK) { Remove-Item $CF_LOG_FLASK -Force }

        $cfCmd = @"
Set-Location '$BASE_DIR'
Write-Host '🌐 Cloudflared - Flask (5000)' -ForegroundColor Cyan
& '$BASE_DIR\cloudflared.exe' tunnel --url http://localhost:5000 2>&1 | Tee-Object -FilePath '$CF_LOG_FLASK'
"@

        Start-Process powershell -ArgumentList "-NoExit", "-Command", $cfCmd
        Write-Ok "cloudflared (Flask) بدأ"

        # استنى الرابط
        Write-Info "بانتظار الرابط... (15 ثانية)"
        for ($i = 0; $i -lt 15; $i++) {
            Start-Sleep -Seconds 1
            if (Test-Path $CF_LOG_FLASK) {
                $content = Get-Content $CF_LOG_FLASK -Raw -ErrorAction SilentlyContinue
                if ($content -match '(https://[a-z0-9\-]+\.trycloudflare\.com)') {
                    $flaskUrl = $matches[1]
                    break
                }
            }
        }

        if ($flaskUrl) {
            Write-Ok "Flask URL: $flaskUrl"
        } else {
            Write-Warn "مقدرتش أستخرج الرابط - شوف النافذة"
        }
    }

    # ═══════════════════════════════════════════════════════════════
    # [5/6] Cloudflare Tunnel - VNC
    # ═══════════════════════════════════════════════════════════════

    Write-Step "5/6" "تشغيل Cloudflare Tunnel - VNC (7900)..."

    if (-not (Test-Path "$BASE_DIR\cloudflared.exe")) {
        Write-Warn "cloudflared.exe مش موجود - اتخطى"
    } else {
        if (Test-Path $CF_LOG_VNC) { Remove-Item $CF_LOG_VNC -Force }

        $cfVncCmd = @"
Set-Location '$BASE_DIR'
Write-Host '🌐 Cloudflared - VNC (7900)' -ForegroundColor Cyan
& '$BASE_DIR\cloudflared.exe' tunnel --url http://localhost:7900 2>&1 | Tee-Object -FilePath '$CF_LOG_VNC'
"@

        Start-Process powershell -ArgumentList "-NoExit", "-Command", $cfVncCmd
        Write-Ok "cloudflared (VNC) بدأ"

        Write-Info "بانتظار الرابط... (15 ثانية)"
        for ($i = 0; $i -lt 15; $i++) {
            Start-Sleep -Seconds 1
            if (Test-Path $CF_LOG_VNC) {
                $content = Get-Content $CF_LOG_VNC -Raw -ErrorAction SilentlyContinue
                if ($content -match '(https://[a-z0-9\-]+\.trycloudflare\.com)') {
                    $vncUrl = $matches[1]
                    break
                }
            }
        }

        if ($vncUrl) {
            Write-Ok "VNC URL: $vncUrl"
        } else {
            Write-Warn "مقدرتش أستخرج الرابط - شوف النافذة"
        }
    }
}

# ═══════════════════════════════════════════════════════════════
# [6/6] Update Config + Summary
# ═══════════════════════════════════════════════════════════════

Write-Step "6/6" "حفظ الإعدادات..."

if ($flaskUrl -or $vncUrl) {
    $newConfig = @{
        flask_url = if ($flaskUrl) { $flaskUrl } else { "" }
        vnc_url = if ($vncUrl) { $vncUrl } else { "" }
        provider = "cloudflare"
        updated_at = (Get-Date).ToString("o")
    } | ConvertTo-Json

    New-Item -ItemType Directory -Force -Path (Split-Path $TUNNEL_CONFIG) | Out-Null
    $newConfig | Out-File -Encoding utf8 $TUNNEL_CONFIG
    Write-Ok "tunnel_config.json اتحدّث"
} else {
    Write-Info "مفيش روابط جديدة"
}

# ═══════════════════════════════════════════════════════════════
# Final Summary
# ═══════════════════════════════════════════════════════════════

Write-Host ""
Write-Host "  ╔══════════════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "  ║                                                      ║" -ForegroundColor Green
Write-Host "  ║       ✅  كل الخدمات شغالة!                          ║" -ForegroundColor Green
Write-Host "  ║                                                      ║" -ForegroundColor Green
Write-Host "  ╚══════════════════════════════════════════════════════╝" -ForegroundColor Green

Write-Host ""
Write-Host "  📍 الروابط:" -ForegroundColor Cyan
Write-Host "     محلي Flask:  http://localhost:5000" -ForegroundColor White
Write-Host "     محلي VNC:    http://localhost:7900/vnc.html" -ForegroundColor White
Write-Host "     Selenium:    http://localhost:4444" -ForegroundColor White

if ($flaskUrl) {
    Write-Host ""
    Write-Host "     🌐 Flask:    $flaskUrl" -ForegroundColor Green
    Write-Host "        → /live:  $flaskUrl/live" -ForegroundColor Green
}

if ($vncUrl) {
    Write-Host ""
    Write-Host "     🌐 VNC:      $vncUrl/vnc.html?autoconnect=true&resize=scale&password=secret" -ForegroundColor Green
}

Write-Host ""
Write-Host "  🔑 تسجيل الدخول:" -ForegroundColor Cyan
Write-Host "     Username: admin" -ForegroundColor White
Write-Host "     Password: password" -ForegroundColor White

if ($flaskUrl) {
    Write-Host ""
    Write-Host "  🔗 ابعت لصاحبك:" -ForegroundColor Yellow
    Write-Host "     $flaskUrl/live" -ForegroundColor White
}

Write-Host ""
Write-Host "  💡 نصايح:" -ForegroundColor Cyan
Write-Host "     • متقفلش النوافذ اللي فتحت" -ForegroundColor Gray
Write-Host "     • لإيقاف كل حاجة:  .\stop.ps1" -ForegroundColor Gray
Write-Host "     • لفحص الحالة:     .\status.ps1" -ForegroundColor Gray
Write-Host ""

if (-not $SkipBrowser -and $flaskUp) {
    Start-Sleep -Seconds 2
    Start-Process "http://localhost:5000/live"
    Write-Ok "المتصفح اتفتح على /live"
}

Write-Host ""
