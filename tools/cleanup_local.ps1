# ═══════════════════════════════════════════════════════════════
#  تنظيف المشروع على الجهاز — آمن: مفيش أي حذف
#  1) نسخة كاملة من المشروع  ->  D:\erp-automation-backups\full_<التاريخ>\
#  2) نقل البيانات القديمة لفولدر data\  (نسخ، مش نقل)
#  3) نقل الملفات اللي ملهاش لزمة  ->  D:\erp-automation-archive\<التاريخ>\
#
#  التشغيل (من فولدر المشروع):
#     powershell -ExecutionPolicy Bypass -File tools\cleanup_local.ps1 -DryRun   # يعرض بس
#     powershell -ExecutionPolicy Bypass -File tools\cleanup_local.ps1           # ينفّذ
# ═══════════════════════════════════════════════════════════════
param(
    [switch]$DryRun,
    [string]$BackupRoot  = "D:\erp-automation-backups",
    [string]$ArchiveRoot = "D:\erp-automation-archive"
)

$ErrorActionPreference = "Stop"
$ROOT  = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$STAMP = Get-Date -Format "yyyyMMdd_HHmmss"
$ARCH  = Join-Path $ArchiveRoot $STAMP

function Ok($m)   { Write-Host "  [OK] $m" -ForegroundColor Green }
function Info($m) { Write-Host "  $m" -ForegroundColor Cyan }
function Warn($m) { Write-Host "  [!] $m" -ForegroundColor Yellow }

if (-not (Test-Path (Join-Path $ROOT "web\app.py"))) { throw "شغّلي السكربت من جوه فولدر المشروع (مش لاقي web\app.py)" }
Write-Host "`n=== تنظيف $ROOT ===" -ForegroundColor White
if ($DryRun) { Warn "وضع العرض بس (DryRun) — مفيش حاجة هتتغير" }

# ---------- 1) نسخة كاملة ----------
$BK = Join-Path $BackupRoot "full_$STAMP"
Info "1) نسخة كاملة -> $BK"
if (-not $DryRun) {
    New-Item -ItemType Directory -Force -Path $BK | Out-Null
    robocopy $ROOT $BK /E /R:1 /W:1 /NFL /NDL /NJH /NJS /NP /XD venv .venv __pycache__ .pytest_cache chrome_profile | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "النسخة الاحتياطية فشلت (robocopy $LASTEXITCODE) — وقفت ومغيرتش حاجة" }
    Ok "النسخة اتعملت"
}

# ---------- 2) نقل البيانات لـ data\ ----------
Info "2) نقل البيانات القديمة لـ data\"
$py = Join-Path $ROOT "venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }
if (-not $DryRun) {
    Push-Location $ROOT
    try { & $py -c "import config.paths" } finally { Pop-Location }
    if (-not (Test-Path (Join-Path $ROOT "data\.migrated"))) { throw "نقل البيانات منجحش — وقفت قبل ما أنقل أي حاجة للأرشيف" }
    Ok "البيانات في data\"
}

# ---------- 3) الأرشيف ----------
Info "3) نقل الحاجات اللي ملهاش لزمة -> $ARCH"
$patterns = @(
    "_backup*", "_safe_*", "_old_builder", "_check_*", "_probe_*", "_discover_*",
    "dump_*.txt", "tree.txt", "*.zip", "*.patch", "*.bak", "*.bak*", "Dockerfile.bak",
    "ngrok.exe", "dashboard", "PROJECT_FINAL.md", "PROJECT_SUMMARY.md", "update_ui.ps1",
    "run_scheduled.bat", "Procfile", "runtime.txt", ".pytest_cache", "allure-results", "allure-report"
)
# البيانات القديمة (اتنسخت لـ data\ في الخطوة 2)
$oldData = @(
    "reports", "logs", "chrome_profile", "web\data", "config\schedules", "config\users.json.old",
    "config\users.json", "config\site_config.json", "config\email_config.json", "config\slack_config.json",
    "config\test_sites.json", "config\tunnel_config.json",
    "config\test_registry.py", "config\test_runner.py", "config\cash_receipt_data.py",
    ".github\workflows\test.yml", "pages\cash_receipt_voucher_page.py", "tests\functional\test_04_cash_receipt_voucher.py", "web\requirements.txt"
)
$keep = @("venv", ".venv", ".git", "data", "drivers", ".env", "cloudflared.exe", "tools")

$items = @()
foreach ($p in $patterns) { $items += Get-ChildItem -Path $ROOT -Filter $p -Force -ErrorAction SilentlyContinue }
foreach ($p in $oldData)  { $f = Join-Path $ROOT $p; if (Test-Path $f) { $items += Get-Item $f -Force } }
# __pycache__ في كل مكان (برا venv)
$items += Get-ChildItem -Path $ROOT -Recurse -Directory -Force -Filter "__pycache__" -ErrorAction SilentlyContinue |
          Where-Object { $_.FullName -notmatch "[\\/](venv|\.venv|\.git)[\\/]" }

$items = $items | Where-Object { $keep -notcontains $_.Name } | Sort-Object FullName -Unique
$n = 0
foreach ($it in $items) {
    if (-not (Test-Path $it.FullName)) { continue }          # اتنقل مع الفولدر الأب
    $rel  = $it.FullName.Substring($ROOT.Length).TrimStart("\", "/")
    $dest = Join-Path $ARCH $rel
    Write-Host "     -> $rel" -ForegroundColor Gray
    if (-not $DryRun) {
        New-Item -ItemType Directory -Force -Path (Split-Path $dest) | Out-Null
        Move-Item -LiteralPath $it.FullName -Destination $dest -Force
    }
    $n++
}
Ok "$n عنصر $(if ($DryRun) {'هيتنقل'} else {'اتنقل'})"

# _tools.ps1 -> tools\
$t = Join-Path $ROOT "_tools.ps1"
if (Test-Path $t) {
    Info "_tools.ps1 -> tools\_tools.ps1"
    if (-not $DryRun) { Move-Item -LiteralPath $t -Destination (Join-Path $ROOT "tools\_tools.ps1") -Force }
}

Write-Host "`n=== خلصت ===" -ForegroundColor White
if (-not $DryRun) {
    Write-Host "  النسخة الكاملة : $BK"
    Write-Host "  الأرشيف        : $ARCH   (لو كل حاجة شغالة كويس بعد أسبوع امسحيه بإيدك)"
}
Write-Host "  جربي: python web\app.py  وافتحي http://localhost:5000`n"
