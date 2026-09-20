param([switch]$Build)

$ErrorActionPreference = 'Stop'
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$projectRoot = Split-Path -Parent $PSScriptRoot
$projectPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $projectPython)) { throw '项目虚拟环境不存在，请先创建 .venv。' }
if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) { throw '未找到 npm，请先安装 Node.js。' }
$originalPath = $env:PATH
$originalVirtualEnv = $env:VIRTUAL_ENV
$originalEncoding = $env:PYTHONIOENCODING
try {
    $env:VIRTUAL_ENV = Join-Path $projectRoot '.venv'
    $env:PATH = "$(Join-Path $env:VIRTUAL_ENV 'Scripts');$originalPath"
    $env:PYTHONIOENCODING = 'utf-8'
    Push-Location $projectRoot
    try {
        & $projectPython -m ruff check backend
        if ($LASTEXITCODE -ne 0) { throw '后端 lint 未通过。' }
        & $projectPython -m ruff format --check backend
        if ($LASTEXITCODE -ne 0) { throw '后端格式检查未通过。' }
        & $projectPython -m pytest backend/tests -q
        if ($LASTEXITCODE -ne 0) { throw '后端测试未通过。' }
        & $projectPython -m pip check
        if ($LASTEXITCODE -ne 0) { throw 'Python 依赖检查未通过。' }
    } finally { Pop-Location }
    Push-Location (Join-Path $projectRoot 'frontend')
    try {
        & npm.cmd run lint
        if ($LASTEXITCODE -ne 0) { throw '前端 lint 未通过。' }
        & npm.cmd run typecheck
        if ($LASTEXITCODE -ne 0) { throw '前端类型检查未通过。' }
        & npm.cmd run test
        if ($LASTEXITCODE -ne 0) { throw '前端测试未通过。' }
        if ($Build) {
            & npm.cmd run build
            if ($LASTEXITCODE -ne 0) { throw '前端构建未通过。' }
        }
    } finally { Pop-Location }
    Write-Host '检查通过：中文输出正常，前后端检查完成。'
} finally {
    $env:PATH = $originalPath
    $env:VIRTUAL_ENV = $originalVirtualEnv
    $env:PYTHONIOENCODING = $originalEncoding
}
