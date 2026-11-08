param(
    [Parameter(Mandatory = $true)]
    [string]$LicenseServer
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
Set-Location -LiteralPath $projectRoot

& $python scripts\set_license_url.py $LicenseServer
if ($LASTEXITCODE -ne 0) { throw '授权地址无效' }

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$distRoot = Join-Path $projectRoot "dist\release-$stamp"
& powershell -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'build.ps1') -DistRoot $distRoot
if ($LASTEXITCODE -ne 0) { throw '构建失败' }

$app = Join-Path $distRoot 'NewXKY'
$builtExe = Join-Path $projectRoot "build\release-$stamp\NewXKY\NewXKY.exe"
$distExe = Join-Path $app 'NewXKY.exe'
if (-not (Test-Path $distExe) -and (Test-Path $builtExe)) {
    Copy-Item -LiteralPath $builtExe -Destination $distExe -Force
}
& $python scripts\package_executable.py --app-dir $app
if ($LASTEXITCODE -ne 0) { throw '免安装包生成失败' }

& $python scripts\package_server.py
if ($LASTEXITCODE -ne 0) { throw '服务端包生成失败' }

Write-Output 'RELEASE_READY'
Get-ChildItem (Join-Path $projectRoot 'dist\NewXKY-V1.0.7-Portable.zip*')
Get-ChildItem (Join-Path $projectRoot 'dist\NewXKY-LicenseServer-V1.0.7.zip*')
