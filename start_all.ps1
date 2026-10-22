# ═══════════════════════════════════════════════════════════════
#  ERP Test Automation - Start All Services
#  يشغّل: Flask + Cloudflare (Flask) + Cloudflare (VNC)
#  ويحدّث tunnel_config.json تلقائياً
# ═══════════════════════════════════════════════════════════════

$ErrorActionPreference = "Stop"
$BASE_DIR = $PSScriptRoot
$LOG_DIR = Join-Path $BASE_DIR "data\logs"
$TUNNEL_CONFIG = Join-Path $BASE_DIR "data\settings\tunnel_config.json"
$CF_LOG_FLASK = Join-Path $LOG_DIR "cloudflared_flask.log"
$CF_LOG_VNC   = Join-Path $LOG_DIR "cloudflared_vnc.log"

# ألوان
function Write-Ok($msg)   { Write-Host "  ✅ $msg" -ForegroundColor Green }
function Write-Info($msg) { Write-Host "  ℹ️  $msg" -ForegroundColor Cyan }
function Write-Warn($msg) { Write-Host "  ⚠️  $msg" -ForegroundColor Yellow }
function Write-Err($msg)  { Write-Host "  ❌ $msg" -ForegroundColor Red }

Clear-Host
Write-Host ""
Write-Host "╔══════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║   🚀 ERP Test Automation - Start All Services            ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# ═══════════════════════════════════════════════════════════════
# 0) تأكد من الملفات المطلوبة
# ═══════════════════════════════════════════════════════════════

Write-Host "[1/6] فحص الملفات..." -ForegroundColor Yellow

if (-not (Test-Path "$BASE_DIR\venv\Scripts\Activate.ps1")) {
    Write-Err "venv مش موجود. شغّل: python -m venv venv"
    exit 1
}
Write-Ok "venv موجود"

if (-not (Test-Path "$BASE_DIR\cloudflared.exe")) {
    Write-Err "cloudflared.exe مش موجود. نزّله من:"
    Write-Host "     https://github.com/cloudflare/cloudflared/releases/latest" -ForegroundColor White
    exit 1
}
Write-Ok "cloudflared.exe موجود"

if (-not (Test-Path $LOG_DIR)) {
    New-Item -ItemType Directory -Path $LOG_DIR -Force | Out-Null
}
Write-Ok "logs dir جاهز"

# ═══════════════════════════════════════════════════════════════
# 1) اقفل أي عمليات قديمة
# ═══════════════════════════════════════════════════════════════

Write-Host ""
Write-Host "[2/6] إغلاق العمليات القديمة..." -ForegroundColor Yellow

# اقفل Flask
Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Write-Ok "Flask اتقفل"

# اقفل cloudflared
Get-Process cloudflared -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Write-Ok "cloudflared اتقفل"

# اقفل أي cloudflared processes
Get-WmiObject Win32_Process -Filter "name='cloudflared.exe'" -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

Start-Sleep -Seconds 2
Write-Ok "كل العمليات اتقفلت"

# ═══════════════════════════════════════════════════════════════
# 2) شغّل Flask
# ═══════════════════════════════════════════════════════════════

Write-Host ""
Write-Host "[3/6] تشغيل Flask..." -ForegroundColor Yellow

$flaskCmd = "cd '$BASE_DIR'; .\venv\Scripts\Activate.ps1; Write-Host '🚀 Flask Server' -ForegroundColor Green; python web\app.py"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $flaskCmd
Write-Ok "Flask بدأ في نافذة منفصلة"

Write-Info "بانتظار Flask يبدأ (5 ثواني)..."
Start-Sleep -Seconds 5

# تحقق إن Flask شغال
$flaskUp = $false
for ($i = 0; $i -lt 6; $i++) {
    try {
        $r = Invoke-WebRequest -Uri "http://localhost:5000/login" -UseBasicParsing -TimeoutSec 3
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
    Write-Warn "Flask مش بيرد - تأكد إنه شغال في النافذة التانية"
}

# ═══════════════════════════════════════════════════════════════
# 3) شغّل Cloudflare Tunnel للـ Flask (5000)
# ═══════════════════════════════════════════════════════════════

Write-Host ""
Write-Host "[4/6] تشغيل Cloudflare Tunnel للـ Flask (5000)..." -ForegroundColor Yellow

# امسح اللوج القديم
if (Test-Path $CF_LOG_FLASK) { Remove-Item $CF_LOG_FLASK -Force }

# شغّل cloudflared في الخلفية واكتب اللوج
$cfFlaskCmd = "cd '$BASE_DIR'; .\cloudflared.exe tunnel --url http://localhost:5000 --logfile '$CF_LOG_FLASK' --loglevel info"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $cfFlaskCmd
Write-Ok "cloudflared (Flask) بدأ"

Write-Info "بانتظار الرابط (10 ثواني)..."
Start-Sleep -Seconds 10

# ═══════════════════════════════════════════════════════════════
# 4) شغّل Cloudflare Tunnel للـ VNC (7900)
# ═══════════════════════════════════════════════════════════════

Write-Host ""
Write-Host "[5/6] تشغيل Cloudflare Tunnel للـ VNC (7900)..." -ForegroundColor Yellow

if (Test-Path $CF_LOG_VNC) { Remove-Item $CF_LOG_VNC -Force }

$cfVncCmd = "cd '$BASE_DIR'; .\cloudflared.exe tunnel --url http://localhost:7900 --logfile '$CF_LOG_VNC' --loglevel info"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $cfVncCmd
Write-Ok "cloudflared (VNC) بدأ"

Write-Info "بانتظار الرابط (10 ثواني)..."
Start-Sleep -Seconds 10

# ═══════════════════════════════════════════════════════════════
# 5) استخرج الروابط من اللوجات
# ═══════════════════════════════════════════════════════════════

Write-Host ""
Write-Host "[6/6] استخراج الروابط وتحديث الإعدادات..." -ForegroundColor Yellow

function Get-TunnelUrl($logFile) {
    if (-not (Test-Path $logFile)) { return $null }
    $content = Get-Content $logFile -Raw -ErrorAction SilentlyContinue
    # ابحث عن trycloudflare.com
    if ($content -match '(https://[a-z0-9\-]+\.trycloudflare\.com)') {
        return $matches[1]
    }
    return $null
}

$flaskUrl = $null
$vncUrl = $null

# حاول 3 مرات
for ($i = 0; $i -lt 3; $i++) {
    if (-not $flaskUrl) { $flaskUrl = Get-TunnelUrl $CF_LOG_FLASK }
    if (-not $vncUrl)   { $vncUrl   = Get-TunnelUrl $CF_LOG_VNC }

    if ($flaskUrl -and $vncUrl) { break }
    Start-Sleep -Seconds 3
}

if (-not $flaskUrl) {
    Write-Warn "مقدرتش أستخرج Flask URL من اللوج"
    Write-Info "افتح يدوياً: http://127.0.0.1:4040 (ngrok) أو شوف النافذة"
}

if (-not $vncUrl) {
    Write-Warn "مقدرتش أستخرج VNC URL من اللوج"
}

# حدّث tunnel_config.json
if ($flaskUrl -or $vncUrl) {
    $config = @{
        flask_url  = if ($flaskUrl) { $flaskUrl } else { "" }
        vnc_url    = if ($vncUrl)   { $vncUrl }   else { "" }
        provider   = "cloudflare"
        updated_at = (Get-Date).ToString("o")
    } | ConvertTo-Json

    New-Item -ItemType Directory -Force -Path (Split-Path $TUNNEL_CONFIG) | Out-Null
    $config | Out-File -Encoding utf8 $TUNNEL_CONFIG
    Write-Ok "tunnel_config.json اتحدّث"
} else {
    Write-Warn "محدّثتش الـ config - مفيش روابط"
}

# ═══════════════════════════════════════════════════════════════
# 6) عرض النتيجة النهائية
# ═══════════════════════════════════════════════════════════════

Write-Host ""
Write-Host "╔══════════════════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "║   ✅ كل الخدمات شغالة!                                    ║" -ForegroundColor Green
Write-Host "╚══════════════════════════════════════════════════════════╝" -ForegroundColor Green
Write-Host ""

Write-Host "📍 الروابط:" -ForegroundColor Cyan
Write-Host "   محلي Flask:      http://localhost:5000" -ForegroundColor White
Write-Host "   محلي VNC:        http://localhost:7900/vnc.html" -ForegroundColor White
Write-Host ""

if ($flaskUrl) {
    Write-Host "   🌐 Flask عام:    $flaskUrl" -ForegroundColor Green
    Write-Host "      → Live:        $flaskUrl/live" -ForegroundColor Green
} else {
    Write-Host "   🌐 Flask عام:    (شوف النافذة)" -ForegroundColor Yellow
}

if ($vncUrl) {
    Write-Host "   🌐 VNC عام:      $vncUrl/vnc.html?autoconnect=true&resize=scale&password=secret" -ForegroundColor Green
} else {
    Write-Host "   🌐 VNC عام:      (شوف النافذة)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "🔑 تسجيل الدخول:" -ForegroundColor Cyan
Write-Host "   Username: admin" -ForegroundColor White
Write-Host "   Password: password" -ForegroundColor White
Write-Host ""

if ($flaskUrl) {
    Write-Host "🔗 ابعت لصاحبك:" -ForegroundColor Yellow
    Write-Host "   $flaskUrl/live" -ForegroundColor White
    Write-Host ""
}

Write-Host "💡 نصايح:" -ForegroundColor Cyan
Write-Host "   • سيب كل النوافذ مفتوحة" -ForegroundColor Gray
Write-Host "   • متقفلش Flask ولا cloudflared" -ForegroundColor Gray
Write-Host "   • الروابط بتتغير كل مرة تشغّل السكريبت" -ForegroundColor Gray
Write-Host ""

Write-Host "🎯 أوامر سريعة:" -ForegroundColor Cyan
Write-Host "   إيقاف كل حاجة:  Get-Process python,cloudflared -EA SilentlyContinue | Stop-Process -Force" -ForegroundColor Gray
Write-Host ""

# افتح المتصفح على الصفحة الرئيسية
Start-Sleep -Seconds 2
try {
    Start-Process "http://localhost:5000/live"
    Write-Ok "المتصفح اتفتح على /live"
} catch {
    Write-Warn "افتح المتصفح يدوياً: http://localhost:5000/live"
}

Write-Host ""
