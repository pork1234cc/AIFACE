param([switch]$SmokeTest)

$ErrorActionPreference = 'Stop'
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$projectRoot = Split-Path -Parent $PSScriptRoot
$projectPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
$nextCli = Join-Path $projectRoot 'frontend\node_modules\next\dist\bin\next'
if (-not (Test-Path -LiteralPath $projectPython)) { throw '项目虚拟环境不存在，请先创建 .venv。' }
if (-not (Test-Path -LiteralPath $nextCli)) { throw '前端依赖尚未安装，请先在 frontend 运行 npm ci。' }
$nodeCommand = Get-Command node.exe -ErrorAction Stop

# 端口被占用时直接报错，不停止其他程序。
foreach ($port in @(8000, 3000)) {
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $port)
    try { $listener.Start() } catch { throw "本机端口 $port 已被占用，请先停止占用该端口的服务。" }
    finally { $listener.Stop() }
}

$logDirectory = Join-Path $projectRoot 'storage\logs'
[System.IO.Directory]::CreateDirectory($logDirectory) | Out-Null
$runId = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
$originalPath = $env:PATH
$originalVirtualEnv = $env:VIRTUAL_ENV
$originalEncoding = $env:PYTHONIOENCODING
$backendProcess = $null
$frontendProcess = $null
$workerProcess = $null
try {
    $env:VIRTUAL_ENV = Join-Path $projectRoot '.venv'
    $env:PATH = "$(Join-Path $env:VIRTUAL_ENV 'Scripts');$originalPath"
    $env:PYTHONIOENCODING = 'utf-8'
    Push-Location $projectRoot
    try {
        & $projectPython (Join-Path $projectRoot 'main.py') migrate
        if ($LASTEXITCODE -ne 0) { throw '数据库迁移失败，未启动服务。' }
    } finally { Pop-Location }

    $backendProcess = Start-Process -FilePath $projectPython -ArgumentList @(
        ('"' + (Join-Path $projectRoot 'main.py') + '"'), 'api', '--port', '8000'
    ) -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $logDirectory "$runId-backend.log") `
        -RedirectStandardError (Join-Path $logDirectory "$runId-backend-error.log")
    $frontendProcess = Start-Process -FilePath $nodeCommand.Source -ArgumentList @(
        ('"' + $nextCli + '"'), 'dev', '--hostname', '127.0.0.1', '--port', '3000'
    ) -WorkingDirectory (Join-Path $projectRoot 'frontend') -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $logDirectory "$runId-frontend.log") `
        -RedirectStandardError (Join-Path $logDirectory "$runId-frontend-error.log")
    if (-not $SmokeTest) {
        $workerProcess = Start-Process -FilePath $projectPython -ArgumentList @(
            ('"' + (Join-Path $projectRoot 'main.py') + '"'), 'worker', '--port', '8000'
        ) `
            -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru `
            -RedirectStandardOutput (Join-Path $logDirectory "$runId-worker.log") `
            -RedirectStandardError (Join-Path $logDirectory "$runId-worker-error.log")
    }

    $ready = $false
    $deadline = (Get-Date).AddSeconds(60)
    while ((Get-Date) -lt $deadline) {
        if ($backendProcess.HasExited -or $frontendProcess.HasExited) { throw "服务提前退出，请查看 $logDirectory 中本次启动日志。" }
        try {
            $health = Invoke-RestMethod -Uri 'http://127.0.0.1:3000/api/health' -TimeoutSec 3
            if ($health.status -eq 'ok') { $ready = $true; break }
        } catch [System.Net.WebException] { }
        Start-Sleep -Milliseconds 500
    }
    if (-not $ready) { throw "服务启动超时，请查看 $logDirectory 中本次启动日志。" }
    Write-Host '工作台已启动：http://127.0.0.1:3000'
    Write-Host 'API 文档：http://127.0.0.1:8000/api/docs'
    Write-Host "运行日志：$logDirectory"

    if ($SmokeTest) {
        $page = Invoke-WebRequest -Uri 'http://127.0.0.1:3000' -UseBasicParsing -TimeoutSec 30
        if ($page.StatusCode -ne 200 -or $page.Content -notmatch 'AIFACE') { throw '前端首页冒烟检查失败。' }
        Write-Host '冒烟检查通过：首页与同源 API 可访问。'
    } else {
        Write-Host '生成 Worker 等待或已通过网页授权；按 Ctrl+C 停止本次启动的前后端与 Worker。'
        while (-not $backendProcess.HasExited -and -not $frontendProcess.HasExited -and -not $workerProcess.HasExited) {
            Start-Sleep -Seconds 1
        }
        throw "服务意外退出，请查看 $logDirectory 中本次启动日志。"
    }
} finally {
    # 仅停止本次脚本启动的进程树，不按程序名称批量终止。
    foreach ($managedProcess in @($workerProcess, $frontendProcess, $backendProcess)) {
        if ($null -ne $managedProcess -and -not $managedProcess.HasExited) {
            & taskkill.exe /PID $managedProcess.Id /T /F 2>&1 | Out-Null
        }
    }
    $env:PATH = $originalPath
    $env:VIRTUAL_ENV = $originalVirtualEnv
    $env:PYTHONIOENCODING = $originalEncoding
}
