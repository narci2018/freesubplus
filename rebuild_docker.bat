@echo off
chcp 65001 >nul
title FreeSub Docker 一键重构与部署脚本

echo ========================================================
echo    🚀 FreeSub WebUI - Docker 一键热重构与部署脚本
echo    目标端口: 18168
echo ========================================================
echo.

where docker >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] 未检测到 Docker，请先启动 Docker Desktop！
    pause
    exit /b 1
)

echo [1/4] 正在停止旧容器...
docker compose down 2>nul || docker stop freesub-webui 2>nul && docker rm freesub-webui 2>nul
echo [✓] 旧服务已停止
echo.

echo [2/4] 正在重新构建镜像 (内置 sing-box 与 GeoLite2 数据)...
docker compose build || docker build -t freesub-webui:latest .
echo [✓] 镜像构建完成
echo.

echo [3/4] 正在启动新容器...
docker compose up -d || docker run -d --name freesub-webui -p 18168:18168 -v "%cd%/data:/app/data" --restart unless-stopped freesub-webui:latest
echo.

echo [4/4] 检查运行状态...
timeout /t 2 >nul
docker ps | findstr "freesub-webui" >nul
if %errorlevel% equ 0 (
    echo ========================================================
    echo   🎉 FreeSub WebUI 容器已成功重构并上线!
    echo ========================================================
    echo   本地访问: http://localhost:18168
    echo ========================================================
) else (
    echo [ERROR] 容器未正常运行，请执行 docker logs freesub-webui 查看详情。
)
pause
