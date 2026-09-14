#!/usr/bin/env bash
set -e

# ==============================================================================
# FreeSub Docker 服务一键停止、重构与部署脚本
# ==============================================================================

GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo -e "${CYAN}========================================================${NC}"
echo -e "${CYAN}   🚀 FreeSub WebUI - Docker 一键热重构与部署脚本${NC}"
echo -e "${CYAN}   目标端口: 18168${NC}"
echo -e "${CYAN}========================================================${NC}"
echo ""

# 1. 检查 Docker 是否安装
if ! command -v docker >/dev/null 2>&1; then
    echo -e "${RED}[ERROR] 未检测到 Docker 命令，请先安装 Docker！${NC}"
    exit 1
fi

# 2. 停止并清理旧容器
echo -e "${YELLOW}[1/4] 正在停止并清理旧容器实例...${NC}"
if docker compose version >/dev/null 2>&1; then
    docker compose down --remove-orphans 2>/dev/null || true
elif command -v docker-compose >/dev/null 2>&1; then
    docker-compose down --remove-orphans 2>/dev/null || true
else
    # 纯 docker 命令回退
    if docker ps -a --format '{{.Names}}' | grep -Eq "^freesub-webui$"; then
        docker stop freesub-webui 2>/dev/null || true
        docker rm freesub-webui 2>/dev/null || true
    fi
fi
echo -e "${GREEN}[✓] 旧容器已安全停止并卸载${NC}"
echo ""

# 3. 重新构建镜像 (内置 sing-box 与 GeoLite2 数据，避免容器启动时等待)
echo -e "${YELLOW}[2/4] 正在重新构建 Docker 镜像 (内置加速预置组件)...${NC}"
if docker compose version >/dev/null 2>&1; then
    docker compose build
elif command -v docker-compose >/dev/null 2>&1; then
    docker-compose build
else
    docker build -t freesub-webui:latest .
fi
echo -e "${GREEN}[✓] 镜像构建完成${NC}"
echo ""

# 4. 重新启动容器
echo -e "${YELLOW}[3/4] 正在拉起新容器实例...${NC}"
if docker compose version >/dev/null 2>&1; then
    docker compose up -d
elif command -v docker-compose >/dev/null 2>&1; then
    docker-compose up -d
else
    docker run -d \
      --name freesub-webui \
      -p 18168:18168 \
      -v "$(pwd)/data:/app/data" \
      --restart unless-stopped \
      freesub-webui:latest
fi
echo ""

# 5. 校验运行状态并输出提示
echo -e "${YELLOW}[4/4] 正在检查容器运行状态...${NC}"
sleep 2

if docker ps --format '{{.Names}}' | grep -Eq "^freesub-webui$"; then
    # 获取本机内网 IP
    LOCAL_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "127.0.0.1")
    echo -e "${GREEN}========================================================${NC}"
    echo -e "${GREEN}  🎉 FreeSub WebUI 容器已成功重构并上线运行!${NC}"
    echo -e "${GREEN}========================================================${NC}"
    echo -e "  🌐 本地浏览器访问 : ${CYAN}http://localhost:18168${NC}"
    echo -e "  📡 局域网访问地址 : ${CYAN}http://${LOCAL_IP}:18168${NC}"
    echo -e "  📋 查看实时日志   : ${YELLOW}docker logs -f freesub-webui${NC}"
    echo -e "${GREEN}========================================================${NC}"
else
    echo -e "${RED}[ERROR] 容器启动异常，请执行 'docker logs freesub-webui' 查看原因！${NC}"
    exit 1
fi
