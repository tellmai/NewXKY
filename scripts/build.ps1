param([string]$Python = '')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
if (-not $Python) {
    $Python = Join-Path $projectRoot '.venv\Scripts\python.exe'
}
& $Python -m PyInstaller --noconfirm --clean (Join-Path $projectRoot 'NewXKY.spec')
if ($LASTEXITCODE -ne 0) { throw '打包失败' }
Copy-Item -LiteralPath (Join-Path $projectRoot 'README.md') -Destination (Join-Path $projectRoot 'dist\NewXKY\使用说明.md')
Copy-Item -LiteralPath (Join-Path $projectRoot 'THIRD_PARTY_NOTICES.md') -Destination (Join-Path $projectRoot 'dist\NewXKY\THIRD_PARTY_NOTICES.md')
Write-Output (Join-Path $projectRoot 'dist\NewXKY\NewXKY.exe')
