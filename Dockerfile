FROM python:3.11-slim

# 设置工作目录与非交互模式
WORKDIR /app
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PORT=18168 \
    DATA_DIR=/app/data

# 安装系统基础依赖（包含 curl、ca-certificates、tzdata）
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    tzdata \
    tar \
    gzip \
    && rm -rf /var/lib/apt/lists/*

# 复制 Python 依赖并安装
COPY requirements-web.txt .
RUN pip install --no-cache-dir -r requirements-web.txt

# 复制项目代码
COPY scripts /app/scripts
COPY web /app/web

# 复制本地已下载好的运行组件（sing-box 内核与 GeoLite2 离线数据库直接本地 COPY，避免每次打包重复联网下载）
COPY runtime /app/runtime
RUN chmod +x /app/runtime/sing-box* 2>/dev/null || true

# 创建持久化数据目录并作组件就绪检测（本地已存在则瞬间跳过，秒级构建）
RUN mkdir -p /app/data && python scripts/download_assets.py --runtime-dir=/app/runtime

# 暴露 WebUI 与订阅直链服务端口
EXPOSE 18168

# 启动 Web 服务
CMD ["python", "-m", "web.main"]
