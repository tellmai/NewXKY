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
& $Python (Join-Path $PSScriptRoot 'build_bank_from_pdf.py')
if ($LASTEXITCODE -ne 0) { throw '指定 PDF 题库构建失败' }
& $Python -m PyInstaller --noconfirm --clean --distpath $distRoot --workpath $workRoot (Join-Path $projectRoot 'NewXKY.spec')
if ($LASTEXITCODE -ne 0) { throw '打包失败' }
$app = Join-Path $distRoot 'NewXKY'
& $Python (Join-Path $PSScriptRoot 'write_build_config.py') $app
if ($LASTEXITCODE -ne 0) { throw '构建配置写入失败' }
Copy-Item -LiteralPath (Join-Path $projectRoot 'README.md') -Destination (Join-Path $app 'README.md')
Copy-Item -LiteralPath (Join-Path $projectRoot 'THIRD_PARTY_NOTICES.md') -Destination (Join-Path $app 'THIRD_PARTY_NOTICES.md')
Write-Output (Join-Path $app 'NewXKY.exe')
