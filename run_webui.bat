@echo off
chcp 65001 >nul
title FreeSub WebUI Hub

echo ========================================================
echo   FreeSub WebUI - 本地智能测活与节点订阅中心
echo   端口: 18168
echo ========================================================
echo.

echo [*] 检查并安装运行依赖...
python -m pip install -q -r requirements-web.txt

echo [*] 启动 WebUI 服务...
echo [*] 浏览器访问: http://127.0.0.1:18168
echo.

python -m web.main
pause
