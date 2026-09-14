import os
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from web.api_routes import router as api_router
from web.scheduler import scheduler
from web.config_mgr import config_mgr

STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动定时任务调度器
    scheduler.start()
    yield
    # 关闭时清理
    scheduler.shutdown()


app = FastAPI(
    title="FreeSub Node Hub & Prober",
    description="高端自动化节点测活、优选IP注入与订阅分发中心",
    version="2.0.0",
    lifespan=lifespan
)

# 允许跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载 API 与 订阅路由
app.include_router(api_router)

# 挂载静态文件
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", response_class=FileResponse)
async def serve_index():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"message": "FreeSub WebUI is running. (static/index.html not found)"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 18168))
    uvicorn.run("web.main:app", host="0.0.0.0", port=port, reload=False)
