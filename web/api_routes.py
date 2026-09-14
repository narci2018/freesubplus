import os
import json
import asyncio
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from web.config_mgr import config_mgr
from web.engine_runner import engine_runner, log_buffer
from web.cf_optimizer import cf_optimizer
from web.scheduler import scheduler

router = APIRouter()


class ConfigUpdateRequest(BaseModel):
    naming_rule: dict = None
    scheduler: dict = None
    cf_clean_ip: dict = None
    network: dict = None


class AddSourceRequest(BaseModel):
    name: str
    url: str


class UpdateSourceRequest(BaseModel):
    name: str = None
    url: str = None
    enabled: bool = None


class TestSourceRequest(BaseModel):
    url: str


@router.get("/api/status")
async def get_status():
    status = engine_runner.get_status()
    out_dir = config_mgr.get_output_dir()
    
    # 获取产物文件列表
    sub_files = []
    if out_dir.exists():
        for f in out_dir.iterdir():
            if f.is_file() and f.suffix in (".txt", ".yaml", ".json"):
                sub_files.append({
                    "name": f.name,
                    "size_kb": round(f.stat().st_size / 1024, 1),
                    "modified": f.stat().st_mtime
                })
    status["output_files"] = sub_files
    return status


@router.get("/api/stats")
async def get_stats():
    out_dir = config_mgr.get_output_dir()
    sb_file = out_dir / "singbox.json"
    by_country = {}
    by_proto = {}
    total_nodes = 0
    res_nodes = 0

    if sb_file.exists():
        try:
            with open(sb_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            outbounds = data.get("outbounds", [])
            for ob in outbounds:
                proto = ob.get("type", "other")
                tag = ob.get("tag", "")
                if proto in ("direct", "block", "dns"):
                    continue
                total_nodes += 1
                by_proto[proto] = by_proto.get(proto, 0) + 1
                if "家宽" in tag:
                    res_nodes += 1
                # 尝试从 tag 解析国家 emoji / 名称
                parts = tag.split()
                if len(parts) >= 2:
                    cname = parts[1]
                    by_country[cname] = by_country.get(cname, 0) + 1
        except Exception as e:
            print(f"[!] 读取统计数据异常: {e}")

    top_countries = sorted(by_country.items(), key=lambda x: -x[1])[:8]
    return {
        "total_nodes": total_nodes,
        "residential_nodes": res_nodes,
        "by_proto": by_proto,
        "top_countries": dict(top_countries)
    }


@router.get("/api/config")
async def get_config():
    return config_mgr.get_config()


@router.post("/api/config")
async def update_config(req: ConfigUpdateRequest):
    updates = {}
    if req.naming_rule is not None:
        updates["naming_rule"] = req.naming_rule
    if req.scheduler is not None:
        updates["scheduler"] = req.scheduler
    if req.cf_clean_ip is not None:
        updates["cf_clean_ip"] = req.cf_clean_ip
    if req.network is not None:
        updates["network"] = req.network

    config_mgr.save_config(updates)
    if req.scheduler is not None:
        scheduler.reschedule()
    return {"status": "ok", "config": config_mgr.get_config()}


@router.get("/api/sources")
async def get_sources():
    return config_mgr.get_config().get("sources", [])


@router.post("/api/sources")
async def add_source(req: AddSourceRequest):
    if not req.url or not req.url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="订阅源必须是合法的 HTTP/HTTPS 链接")
    new_src = config_mgr.add_source(req.name, req.url)
    return {"status": "ok", "source": new_src}


@router.put("/api/sources/{source_id}")
async def update_source(source_id: str, req: UpdateSourceRequest):
    updates = {k: v for k, v in req.dict().items() if v is not None}
    ok = config_mgr.update_source(source_id, updates)
    if not ok:
        raise HTTPException(status_code=404, detail="未找到指定的订阅源")
    return {"status": "ok"}


@router.delete("/api/sources/{source_id}")
async def delete_source(source_id: str):
    ok = config_mgr.delete_source(source_id)
    if not ok:
        raise HTTPException(status_code=404, detail="未找到指定的订阅源")
    return {"status": "ok"}


@router.post("/api/sources/{source_id}/toggle")
async def toggle_source(source_id: str):
    sources = config_mgr.get_config().get("sources", [])
    for s in sources:
        if s["id"] == source_id:
            new_state = not s.get("enabled", True)
            config_mgr.update_source(source_id, {"enabled": new_state})
            return {"status": "ok", "enabled": new_state}
    raise HTTPException(status_code=404, detail="未找到指定的订阅源")


@router.post("/api/sources/test")
async def test_source(req: TestSourceRequest):
    import requests
    import main_v2 as mv

    try:
        r = requests.get(req.url, timeout=15)
        if r.status_code != 200:
            config_mgr.record_source_fetch_result(req.url, False, 0, f"HTTP {r.status_code}")
            return {"status": "error", "message": f"HTTP {r.status_code}"}
        nodes = mv.extract_nodes_from_text(r.text)
        config_mgr.record_source_fetch_result(req.url, True, len(nodes))
        return {
            "status": "ok",
            "node_count": len(nodes),
            "sample": list(nodes)[:3] if nodes else []
        }
    except Exception as e:
        config_mgr.record_source_fetch_result(req.url, False, 0, str(e))
        return {"status": "error", "message": str(e)}


@router.post("/api/run")
async def trigger_run():
    ok, msg = engine_runner.run_pipeline_async()
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"status": "ok", "message": msg}


@router.get("/api/logs")
async def get_logs(count: int = 200):
    return {"logs": log_buffer.get_recent(count)}


@router.get("/api/logs/stream")
async def stream_logs():
    async def log_generator():
        q = log_buffer.subscribe()
        try:
            # 先发已有历史
            for line in log_buffer.get_recent(50):
                yield f"data: {line}\n\n"
            while True:
                try:
                    # 轮询队列
                    line = q.get_nowait()
                    yield f"data: {line}\n\n"
                except Exception:
                    await asyncio.sleep(0.5)
                    # 保活心跳
                    yield ": heartbeat\n\n"
        finally:
            log_buffer.unsubscribe(q)

    return StreamingResponse(log_generator(), media_type="text/event-stream")


@router.get("/api/cf-clean-ips")
async def get_cf_clean_ips():
    ips = cf_optimizer.get_optimal_clean_ips(force_refresh=False)
    return {"clean_ips": ips}


@router.post("/api/cf-clean-ips/test")
async def test_cf_clean_ips():
    ips = cf_optimizer.get_optimal_clean_ips(force_refresh=True)
    return {"clean_ips": ips}


# ═════════════════════════════════════════════════════════════════════
# 客户端直链订阅分发服务
# ═════════════════════════════════════════════════════════════════════

@router.get("/sub/{file_path:path}")
async def serve_subscription(file_path: str):
    out_dir = config_mgr.get_output_dir()
    target = (out_dir / file_path).resolve()

    # 安全路径检查
    if not str(target).startswith(str(out_dir.resolve())):
        raise HTTPException(status_code=403, detail="非法访问路径")

    if not target.exists() or not target.is_file():
        # 如果 output 目录下没有，去根目录 output 找一找兜底
        alt = (Path(out_dir.parent.parent / "output") / file_path).resolve()
        if alt.exists() and alt.is_file():
            target = alt
        else:
            raise HTTPException(status_code=404, detail=f"订阅文件未生成或不存在: {file_path}")

    media_type = "text/plain; charset=utf-8"
    if target.suffix == ".yaml" or target.suffix == ".yml":
        media_type = "application/x-yaml; charset=utf-8"
    elif target.suffix == ".json":
        media_type = "application/json; charset=utf-8"

    return FileResponse(
        path=str(target),
        media_type=media_type,
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Content-Disposition": f'inline; filename="{target.name}"'
        }
    )
