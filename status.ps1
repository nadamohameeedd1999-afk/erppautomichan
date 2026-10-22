# ═══════════════════════════════════════════════════════════════
#  📊 ERP Test Automation - Status Check
# ═══════════════════════════════════════════════════════════════

Clear-Host
Write-Host ""
Write-Host "  📊 حالة الخدمات" -ForegroundColor Cyan
Write-Host "  ──────────────────────────────────────────" -ForegroundColor DarkGray
Write-Host ""

# Flask
$py = Get-Process python -ErrorAction SilentlyContinue
if ($py) {
    $flaskOk = $false
    try {
        $r = Invoke-WebRequest -Uri "http://localhost:5000/login" -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
        if ($r.StatusCode -eq 200) { $flaskOk = $true }
    } catch {}

    if ($flaskOk) {
        Write-Host "  ✅ Flask (5000)         شغال" -ForegroundColor Green
    } else {
        Write-Host "  ⚠️  Flask (5000)         process موجود بس مش بيرد" -ForegroundColor Yellow
    }
} else {
    Write-Host "  ❌ Flask (5000)         مش شغال" -ForegroundColor Red
}

# Selenium Grid
try {
    $r = Invoke-WebRequest -Uri "http://localhost:4444/status" -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
    $data = $r.Content | ConvertFrom-Json
    if ($data.value.ready) {
        Write-Host "  ✅ Selenium Grid (4444) شغال" -ForegroundColor Green
    } else {
        Write-Host "  ⚠️  Selenium Grid (4444) موجود بس مش ready" -ForegroundColor Yellow
    }
} catch {
    Write-Host "  ❌ Selenium Grid (4444) مش شغال" -ForegroundColor Red
}

# VNC
try {
    $r = Invoke-WebRequest -Uri "http://localhost:7900" -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
    Write-Host "  ✅ VNC (7900)           شغال" -ForegroundColor Green
} catch {
    Write-Host "  ❌ VNC (7900)           مش شغال" -ForegroundColor Red
}

# Cloudflared
$cf = Get-Process cloudflared -ErrorAction SilentlyContinue
if ($cf) {
    Write-Host "  ✅ Cloudflared          شغال ($($cf.Count) عملية)" -ForegroundColor Green
} else {
    Write-Host "  ❌ Cloudflared          مش شغال" -ForegroundColor Red
}

# Docker
try {
    $d = docker ps 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  ✅ Docker               شغال" -ForegroundColor Green
    } else {
        Write-Host "  ❌ Docker               مش شغال" -ForegroundColor Red
    }
} catch {
    Write-Host "  ❌ Docker               مش شغال" -ForegroundColor Red
}

# URLs
Write-Host ""
Write-Host "  ──────────────────────────────────────────" -ForegroundColor DarkGray
Write-Host "  🌐 الروابط:" -ForegroundColor Cyan

$tunnelConfig = Join-Path $PSScriptRoot "data\settings\tunnel_config.json"
if (Test-Path $tunnelConfig) {
    $config = Get-Content $tunnelConfig -Raw | ConvertFrom-Json

    if ($config.flask_url) {
        Write-Host "     Flask: $($config.flask_url)" -ForegroundColor White
        Write-Host "     Live:  $($config.flask_url)/live" -ForegroundColor White
    } else {
        Write-Host "     Flask: (مفيش tunnel URL)" -ForegroundColor Gray
    }

    if ($config.vnc_url) {
        Write-Host "     VNC:   $($config.vnc_url)/vnc.html" -ForegroundColor White
    } else {
        Write-Host "     VNC:   (مفيش tunnel URL)" -ForegroundColor Gray
    }

    Write-Host ""
    Write-Host "     آخر تحديث: $($config.updated_at)" -ForegroundColor DarkGray
} else {
    Write-Host "     (tunnel_config.json مش موجود)" -ForegroundColor Gray
}

Write-Host ""
