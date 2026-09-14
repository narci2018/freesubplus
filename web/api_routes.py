import os
import json
import asyncio
from datetime import datetime
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
    github_sync: dict = None


class AddSourceRequest(BaseModel):
    name: str
    url: str


class BatchAddSourceRequest(BaseModel):
    urls: list
    prefix: str = ""


class UpdateSourceRequest(BaseModel):
    name: str = None
    url: str = None
    enabled: bool = None


class TestSourceRequest(BaseModel):
    url: str


class GitHubConfigRequest(BaseModel):
    token: str = None
    repo: str = None
    branch: str = "main"
    target_dir: str = "output"
    enabled: bool = None


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
    if req.github_sync is not None:
        updates["github_sync"] = req.github_sync

    config_mgr.save_config(updates)
    if req.scheduler is not None:
        scheduler.reschedule()
    return {"status": "ok", "config": config_mgr.get_config()}


@router.get("/api/nodes")
async def get_nodes(filter: str = "all"):
    """返回节点列表 (filter: 'all' 全部存活节点, 'residential' 住宅家宽/移动)"""
    out_dir = config_mgr.get_output_dir()
    sb_file = out_dir / "singbox.json"
    if not sb_file.exists():
        alt = (Path(out_dir.parent.parent / "output") / "singbox.json").resolve()
        if alt.exists():
            sb_file = alt

    # 尝试从 v2ray.txt / residential.txt 读取原始 URI 方便复制
    uri_filename = "residential.txt" if filter == "residential" else "v2ray.txt"
    uri_file = out_dir / uri_filename
    if not uri_file.exists():
        alt_uri = (Path(out_dir.parent.parent / "output") / uri_filename).resolve()
        if alt_uri.exists():
            uri_file = alt_uri

    uris = []
    if uri_file.exists():
        try:
            with open(uri_file, "r", encoding="utf-8") as f:
                content = f.read().strip()
            import base64
            try:
                decoded = base64.b64decode(content + "==").decode("utf-8", errors="ignore")
                uris = [line.strip() for line in decoded.splitlines() if line.strip()]
            except Exception:
                uris = [line.strip() for line in content.splitlines() if line.strip()]
        except Exception:
            pass

    nodes = []
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
                is_res = "家宽" in tag or "移动" in tag
                if filter == "residential" and not is_res:
                    continue

                server = ob.get("server", "")
                port = ob.get("server_port", 0)

                # 从 tag 提取延迟和速度，如 "... - 93ms-45Mbps"
                lat_str = ""
                spd_str = ""
                if " - " in tag:
                    perf_part = tag.split(" - ")[-1]
                    parts = perf_part.split("-")
                    if len(parts) >= 2:
                        lat_str = parts[0]
                        spd_str = parts[1]

                nodes.append({
                    "tag": tag,
                    "proto": proto.upper(),
                    "server": server,
                    "port": port,
                    "is_residential": is_res,
                    "latency": lat_str,
                    "speed": spd_str,
                    "raw_uri": ""
                })
        except Exception as e:
            print(f"[!] 读取节点列表异常: {e}")

    # 映射 URI
    if uris:
        for i, node in enumerate(nodes):
            if i < len(uris):
                node["raw_uri"] = uris[i]

    return {
        "status": "ok",
        "total": len(nodes),
        "filter": filter,
        "nodes": nodes
    }


@router.get("/api/sources")
async def get_sources():
    # 成功次数降序排列，失败次数升序排列
    return config_mgr.get_sources_sorted()


@router.post("/api/sources")
async def add_source(req: AddSourceRequest):
    if not req.url or not req.url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="订阅源必须是合法的 HTTP/HTTPS 链接")
    new_src = config_mgr.add_source(req.name, req.url)
    return {"status": "ok", "source": new_src}


@router.post("/api/sources/batch")
async def batch_add_sources(req: BatchAddSourceRequest):
    if not req.urls:
        raise HTTPException(status_code=400, detail="请提供至少一个订阅源 URL")
    res = config_mgr.add_sources_batch(req.urls, req.prefix)
    return {
        "status": "ok",
        "added_count": res["added_count"],
        "skipped_count": res["skipped_count"],
        "sources": config_mgr.get_sources_sorted()
    }


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

    cfg = config_mgr.get_config()
    front_proxy = cfg.get("network", {}).get("front_proxy", "").strip()
    if front_proxy.startswith("socks5://"):
        front_proxy = "socks5h://" + front_proxy[len("socks5://"):]
    elif front_proxy.startswith("socks4://"):
        front_proxy = "socks4a://" + front_proxy[len("socks4://"):]

    res_text = None
    via = "直连"
    err_msg = ""

    # 1. 尝试直连
    try:
        r = requests.get(req.url, timeout=15)
        if r.status_code == 200:
            res_text = r.text
        else:
            err_msg = f"直连 HTTP {r.status_code}"
    except Exception as e:
        err_msg = f"直连异常: {str(e)[:60]}"

    # 2. 直连失败，若配置了代理则通过代理重试
    if res_text is None and front_proxy:
        via = "前置代理"
        try:
            proxies = {"http": front_proxy, "https": front_proxy}
            r = requests.get(req.url, proxies=proxies, timeout=20)
            if r.status_code == 200:
                res_text = r.text
            else:
                err_msg = f"{err_msg} & 代理 HTTP {r.status_code}"
        except Exception as e:
            err_msg = f"{err_msg} & 代理异常: {str(e)[:60]}"

    if res_text is None:
        config_mgr.record_source_fetch_result(req.url, False, 0, err_msg)
        return {"status": "error", "message": err_msg}

    nodes = mv.extract_nodes_from_text(res_text)
    cf_ips = mv.extract_cf_ips_from_text(res_text) if not nodes else []

    if nodes:
        msg = f"[{via}] 成功提取到 {len(nodes)} 个代理节点"
        config_mgr.record_source_fetch_result(req.url, True, len(nodes), msg)
        return {
            "status": "ok",
            "type": "nodes",
            "node_count": len(nodes),
            "message": msg,
            "sample": list(nodes)[:3]
        }
    elif cf_ips:
        msg = f"[{via}] 识别为 Cloudflare 优选 IP 库，成功提取 {len(cf_ips)} 个优选 IP"
        config_mgr.record_source_fetch_result(req.url, True, len(cf_ips), msg)
        cf_optimizer.add_dynamic_clean_ips(cf_ips)
        return {
            "status": "ok",
            "type": "clean_ips",
            "node_count": len(cf_ips),
            "message": msg,
            "sample": list(cf_ips)[:3]
        }
    else:
        msg = f"[{via}] 成功响应，但未识别到有效节点或优选 IP"
        config_mgr.record_source_fetch_result(req.url, False, 0, msg)
        return {"status": "error", "message": msg}


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


@router.get("/api/github-sync")
async def get_github_sync():
    import web.github_sync as gh
    cfg = config_mgr.get_config().get("github_sync", {})
    repo = cfg.get("repo", "")
    branch = cfg.get("branch", "main")
    target_dir = cfg.get("target_dir", "output")
    cdn_links = gh.generate_cdn_links(repo, branch, target_dir)
    return {
        "config": cfg,
        "cdn_links": cdn_links
    }


@router.post("/api/github-sync")
async def update_github_sync(req: GitHubConfigRequest):
    import web.github_sync as gh
    gh_cfg = config_mgr.get_config().get("github_sync", {})
    if req.token is not None:
        gh_cfg["token"] = req.token.strip()
    if req.repo is not None:
        gh_cfg["repo"] = req.repo.strip()
    if req.branch is not None:
        gh_cfg["branch"] = req.branch.strip()
    if req.target_dir is not None:
        gh_cfg["target_dir"] = req.target_dir.strip()
    if req.enabled is not None:
        gh_cfg["enabled"] = req.enabled

    cdn_links = gh.generate_cdn_links(
        gh_cfg.get("repo", ""),
        gh_cfg.get("branch", "main"),
        gh_cfg.get("target_dir", "output")
    )
    gh_cfg["cdn_links"] = cdn_links
    config_mgr.save_config({"github_sync": gh_cfg})
    return {"status": "ok", "config": gh_cfg, "cdn_links": cdn_links}


@router.post("/api/github-sync/test")
async def test_github_sync(req: GitHubConfigRequest):
    import web.github_sync as gh
    token = req.token if req.token is not None else config_mgr.get_config().get("github_sync", {}).get("token", "")
    repo = req.repo if req.repo is not None else config_mgr.get_config().get("github_sync", {}).get("repo", "")
    res = gh.test_github_connection(token, repo)
    return res


@router.post("/api/github-sync/now")
async def sync_github_now():
    import web.github_sync as gh
    cfg = config_mgr.get_config().get("github_sync", {})
    token = cfg.get("token", "")
    repo = cfg.get("repo", "")
    branch = cfg.get("branch", "main")
    target_dir = cfg.get("target_dir", "output")
    if not token or not repo:
        raise HTTPException(status_code=400, detail="请先在设置中配置 GitHub Token 与仓库名称")

    out_dir = config_mgr.get_output_dir()
    res = gh.sync_files_to_github(token, repo, branch, target_dir, out_dir, log_cb=log_buffer.write)
    cdn_links = gh.generate_cdn_links(repo, branch, target_dir)
    config_mgr.save_config({
        "github_sync": {
            "last_sync_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "last_sync_status": res.get("message", "已同步"),
            "cdn_links": cdn_links
        }
    })
    return res


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
