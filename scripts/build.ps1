param(
    [string]$Python = '',
    [string]$DistRoot = ''
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
if (-not $Python) {
    $Python = Join-Path $projectRoot '.venv\Scripts\python.exe'
}
if (-not $DistRoot) {
    $DistRoot = Join-Path $projectRoot 'dist\release'
} elseif (-not [System.IO.Path]::IsPathRooted($DistRoot)) {
    $DistRoot = Join-Path $projectRoot $DistRoot
}
$distRoot = [System.IO.Path]::GetFullPath($DistRoot)
$workRoot = Join-Path $projectRoot ('build\' + (Split-Path $distRoot -Leaf))
& $Python -m PyInstaller --noconfirm --clean --distpath $distRoot --workpath $workRoot (Join-Path $projectRoot 'NewXKY.spec')
if ($LASTEXITCODE -ne 0) { throw '打包失败' }
$app = Join-Path $distRoot 'NewXKY'
& $Python -c "import json; from pathlib import Path; from newxky.license_config import LICENSE_SERVER_URL; Path(r'$($app)\build-config.json').write_text(json.dumps({'license_server_url': LICENSE_SERVER_URL}, ensure_ascii=False, indent=2), encoding='utf-8')"
if ($LASTEXITCODE -ne 0) { throw '构建配置写入失败' }
Copy-Item -LiteralPath (Join-Path $projectRoot 'README.md') -Destination (Join-Path $app 'README.md')
Copy-Item -LiteralPath (Join-Path $projectRoot 'THIRD_PARTY_NOTICES.md') -Destination (Join-Path $app 'THIRD_PARTY_NOTICES.md')
Write-Output (Join-Path $app 'NewXKY.exe')
