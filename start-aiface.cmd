@echo off
setlocal
chcp 65001 >nul
title AIFACE

rem 从启动文件所在目录运行，支持双击及含空格的路径。
pushd "%~dp0"
if errorlevel 1 exit /b 1

rem 清除前端隔离验收配置，恢复日常 3000/8000 服务。
set "AIFACE_NEXT_DIST_DIR="
set "AIFACE_BACKEND_ORIGIN="

echo 正在启动 AIFACE，请保持此窗口打开。
echo 启动成功后访问 http://127.0.0.1:3000
echo 按 Ctrl+C 停止服务。
echo.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-dev.ps1"
set "aifaceExitCode=%errorlevel%"
echo.
echo 启动程序已退出，返回码：%aifaceExitCode%。如有错误，请查看上方提示。
pause
popd
exit /b %aifaceExitCode%
