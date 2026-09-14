FROM python:3.11-slim

WORKDIR /app

RUN pip config set global.index-url https://mirrors.aliyun.com/pypi/simple/

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 确保内部池文件是正规普通文件，避免与宿主机挂载冲突
RUN rm -rf cached_pool.txt tested_pool.txt && touch cached_pool.txt tested_pool.txt

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
