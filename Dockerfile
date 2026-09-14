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

# 创建运行时与持久化数据目录
RUN mkdir -p /app/data /app/runtime

# 预先拉取运行组件（sing-box 内核与 GeoLite 数据库直接内置进镜像，开箱即用）
RUN python scripts/download_assets.py --runtime-dir=/app/runtime

# 暴露 WebUI 与订阅直链服务端口
EXPOSE 18168

# 启动 Web 服务
CMD ["python", "-m", "web.main"]
