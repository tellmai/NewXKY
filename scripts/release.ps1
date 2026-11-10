param(
    [Parameter(Mandatory = $true)]
    [string]$LicenseServer,
    [string]$Python = ''
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
if (-not $Python) {
    $Python = Join-Path $projectRoot '.venv\Scripts\python.exe'
}
if (-not (Test-Path $Python)) {
    $fallback = Join-Path $projectRoot 'runtime\python.exe'
    if (Test-Path $fallback) { $Python = $fallback }
}
$version = (& $Python -c "import sys; sys.path.insert(0, '.'); from newxky import __version__; print(__version__)").Trim()
if ($LASTEXITCODE -ne 0 -or -not $version) { throw '无法读取版本号 newxky/__init__.py' }

& $Python scripts\configure_license_signing.py
if ($LASTEXITCODE -ne 0) { throw '授权签名配置失败' }
& $Python scripts\set_license_url.py $LicenseServer
if ($LASTEXITCODE -ne 0) { throw '授权地址无效' }

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$distRoot = Join-Path $projectRoot "dist\release-$stamp"
& powershell -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'build.ps1') -Python $Python -DistRoot $distRoot
if ($LASTEXITCODE -ne 0) { throw '构建失败' }

$app = Join-Path $distRoot 'NewXKY'
$builtExe = Join-Path $projectRoot "build\release-$stamp\NewXKY\NewXKY.exe"
$distExe = Join-Path $app 'NewXKY.exe'
if (-not (Test-Path $distExe) -and (Test-Path $builtExe)) {
    Copy-Item -LiteralPath $builtExe -Destination $distExe -Force
}
& $Python scripts\package_executable.py --app-dir $app
if ($LASTEXITCODE -ne 0) { throw '免安装包生成失败' }

& $Python scripts\package_server.py
if ($LASTEXITCODE -ne 0) { throw '服务端包生成失败' }

Write-Output 'RELEASE_READY'
Get-ChildItem (Join-Path $projectRoot "dist\NewXKY-V$version-Portable.zip*")
Get-ChildItem (Join-Path $projectRoot "dist\NewXKY-LicenseServer-V$version.zip*")
