param(
    [string]$SourceJarvisDir = "C:\Users\Pavan\Desktop\jarvis",
    [string]$TargetDir = "",
    [string]$FridayApiBaseUrl = "http://127.0.0.1:8000"
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
if (-not $TargetDir) {
    $TargetDir = Join-Path $repoRoot "apps\jarvis-bridge"
}

if (-not (Test-Path $SourceJarvisDir)) {
    throw "Jarvis source folder not found: $SourceJarvisDir"
}

Write-Host "Preparing bridge copy..."
if (Test-Path $TargetDir) {
    Remove-Item -Recurse -Force $TargetDir
}

robocopy $SourceJarvisDir $TargetDir /MIR /XD node_modules node_modules_old dist .git /XF package-lock.json | Out-Null

$bridgePreload = Join-Path $repoRoot "integrations\jarvis_ui\preload_http_bridge.ts"
if (-not (Test-Path $bridgePreload)) {
    throw "Bridge preload file missing: $bridgePreload"
}

Copy-Item $bridgePreload "$TargetDir\src\main\preload.ts" -Force

$envFile = "$TargetDir\.env.local"
"FRIDAY_API_BASE_URL=$FridayApiBaseUrl" | Out-File -Encoding utf8 $envFile

Write-Host "Bridge prepared at $TargetDir"
Write-Host "Next:"
Write-Host "1) cd $TargetDir"
Write-Host "2) npm install"
Write-Host "3) `$env:FRIDAY_API_BASE_URL='$FridayApiBaseUrl'; npm run dev"
