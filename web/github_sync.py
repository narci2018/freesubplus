# -*- coding: utf-8 -*-
"""
GitHub 自动同步与 jsDelivr CDN 加速模块
========================================
- 使用 GitHub REST API 将本地测活产物文件自动推送到用户指定的 GitHub 仓库
- 自动生成 GitHub Raw 与 jsDelivr 免费 CDN 加速订阅链接
- 每次推送后自动请求 purge.jsdelivr.net 刷新 CDN 边缘节点缓存
"""

import os
import json
import base64
import requests
from pathlib import Path
from datetime import datetime, timezone


def get_headers(token: str) -> dict:
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "FreeSub-WebUI/2.0"
    }
    if token:
        clean_token = token.strip()
        headers["Authorization"] = f"Bearer {clean_token}"
    return headers


def test_github_connection(token: str, repo: str) -> dict:
    """测试 GitHub Token 和 Repo 的连通性与读写权限"""
    token = token.strip()
    repo = repo.strip().strip("/")
    if not token:
        return {"status": "error", "message": "GitHub Token 不能为空"}
    if not repo or "/" not in repo:
        return {"status": "error", "message": "仓库格式必须为 '用户名/仓库名'，如 'myname/freesub-sub'"}

    url = f"https://api.github.com/repos/{repo}"
    try:
        r = requests.get(url, headers=get_headers(token), timeout=15)
        if r.status_code == 200:
            data = r.json()
            permissions = data.get("permissions", {})
            can_push = permissions.get("push", False) or permissions.get("admin", False)
            default_branch = data.get("default_branch", "main")
            return {
                "status": "ok",
                "message": f"连接成功！仓库: {data.get('full_name')} (公开/私有: {'私有' if data.get('private') else '公开'})",
                "can_push": can_push,
                "default_branch": default_branch,
                "stars": data.get("stargazers_count", 0)
            }
        elif r.status_code == 401:
            return {"status": "error", "message": "GitHub Token 无效或已过期 (401 Unauthorized)"}
        elif r.status_code == 404:
            return {"status": "error", "message": f"未找到仓库 '{repo}'，请确认仓库已在 GitHub 创建且 Token 具有访问权限 (404 Not Found)"}
        else:
            return {"status": "error", "message": f"GitHub API 响应异常: HTTP {r.status_code} - {r.text[:100]}"}
    except Exception as e:
        return {"status": "error", "message": f"网络连接异常: {str(e)}"}


def generate_cdn_links(repo: str, branch: str = "main", target_dir: str = "output") -> dict:
    """根据 repo、branch 和产物路径生成 GitHub Raw 和 jsdelivr CDN 加速链接"""
    repo = repo.strip().strip("/")
    branch = branch.strip() or "main"
    path_prefix = target_dir.strip("/").strip()
    if path_prefix:
        path_prefix = f"{path_prefix}/"
    else:
        path_prefix = ""

    if not repo:
        return {}

    files = {
        "clash": f"{path_prefix}clash.yaml",
        "v2ray": f"{path_prefix}v2ray.txt",
        "singbox": f"{path_prefix}singbox.json",
        "residential_clash": f"{path_prefix}residential-clash.yaml",
        "residential_v2ray": f"{path_prefix}residential.txt",
        "residential_singbox": f"{path_prefix}residential-singbox.json"
    }

    links = {}
    for key, fpath in files.items():
        links[key] = {
            "github_raw": f"https://raw.githubusercontent.com/{repo}/{branch}/{fpath}",
            "jsdelivr_cdn": f"https://cdn.jsdelivr.net/gh/{repo}@{branch}/{fpath}",
            "ghproxy_cdn": f"https://ghfast.top/https://raw.githubusercontent.com/{repo}/{branch}/{fpath}",
            "filename": os.path.basename(fpath)
        }
    return links


def purge_jsdelivr_cache(repo: str, branch: str, file_path: str) -> bool:
    """向 purge.jsdelivr.net 发送缓存刷新请求"""
    repo = repo.strip().strip("/")
    branch = branch.strip() or "main"
    url = f"https://purge.jsdelivr.net/gh/{repo}@{branch}/{file_path}"
    try:
        r = requests.get(url, timeout=10)
        return r.status_code == 200
    except Exception:
        return False


def sync_files_to_github(token: str, repo: str, branch: str, target_dir: str, local_dir: Path, log_cb=None) -> dict:
    """
    将本地输出目录中的文件批量上传至 GitHub 仓库，并刷新 jsdelivr 缓存
    """
    token = token.strip()
    repo = repo.strip().strip("/")
    branch = branch.strip() or "main"
    path_prefix = target_dir.strip("/").strip()
    if path_prefix:
        path_prefix = f"{path_prefix}/"
    else:
        path_prefix = ""

    if not token or not repo:
        return {"status": "error", "message": "GitHub Token 或仓库名称未配置"}

    def log(msg):
        if log_cb:
            log_cb(msg)
        else:
            print(f"[GitHubSync] {msg}")

    log(f"[*] 开始向 GitHub 同步产物: {repo} (分支: {branch})...")
    headers = get_headers(token)

    # 需要同步的产物文件
    target_filenames = [
        "clash.yaml", "v2ray.txt", "singbox.json",
        "residential-clash.yaml", "residential.txt", "residential-singbox.json"
    ]

    synced_files = []
    failed_files = []

    for fname in target_filenames:
        local_file = local_dir / fname
        if not local_file.exists():
            continue

        remote_path = f"{path_prefix}{fname}"
        file_api_url = f"https://api.github.com/repos/{repo}/contents/{remote_path}"

        try:
            with open(local_file, "rb") as f:
                content_bytes = f.read()
            b64_content = base64.b64encode(content_bytes).decode("utf-8")

            # 1. 检查远端是否已存在该文件 (获取其 sha 以便更新)
            sha = None
            get_res = requests.get(f"{file_api_url}?ref={branch}", headers=headers, timeout=15)
            if get_res.status_code == 200:
                sha = get_res.json().get("sha")

            # 2. 提交 PUT 请求新建或更新文件
            commit_payload = {
                "message": f"Auto update subscriptions [{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}]",
                "content": b64_content,
                "branch": branch
            }
            if sha:
                commit_payload["sha"] = sha

            put_res = requests.put(file_api_url, headers=headers, json=commit_payload, timeout=30)
            if put_res.status_code in (200, 201):
                synced_files.append(fname)
                log(f"    [✓] 已推送 {remote_path} 至 GitHub")
                # 3. 刷新 jsDelivr 缓存
                purge_ok = purge_jsdelivr_cache(repo, branch, remote_path)
                if purge_ok:
                    log(f"    [⚡] 已刷新 jsDelivr CDN 边缘节点缓存: {fname}")
            else:
                err_text = put_res.text[:100]
                failed_files.append(f"{fname} (HTTP {put_res.status_code})")
                log(f"    [✗] 推送 {fname} 失败: HTTP {put_res.status_code} - {err_text}")
        except Exception as e:
            failed_files.append(f"{fname} ({str(e)[:40]})")
            log(f"    [✗] 上传 {fname} 异常: {str(e)[:50]}")

    if synced_files:
        msg = f"GitHub 同步完成: 成功推送 {len(synced_files)} 个文件"
        if failed_files:
            msg += f"，失败 {len(failed_files)} 个"
        log(f"[+] {msg}")
        return {"status": "ok", "synced": synced_files, "failed": failed_files, "message": msg}
    else:
        msg = f"未成功同步任何文件: {', '.join(failed_files)}"
        log(f"[!] {msg}")
        return {"status": "error", "message": msg}
