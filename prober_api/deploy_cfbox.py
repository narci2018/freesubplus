import argparse
import json
import os
import shutil
import subprocess
import sys
import uuid
from typing import Tuple, Dict, Any

CFBOX_SOURCE = os.path.join("CFBox", "CFBox混淆版.js")
DIST_DIR = "dist_cfbox"
CONFIG_PATH = "prober_config.json"

def http_request(method: str, url: str, headers: Dict[str, str], payload: Dict[str, Any] = None, timeout: float = 30.0) -> Tuple[int, str]:
    """支持 httpx，无依赖时自动降级使用 Python 标准库 urllib"""
    try:
        import httpx
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.request(method, url, headers=headers, json=payload)
            return resp.status_code, resp.text
    except ImportError:
        import urllib.request
        import urllib.error
        req_data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(
            url,
            data=req_data,
            headers=headers,
            method=method
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return response.status, response.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8")

def get_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=4, ensure_ascii=False)

def log(msg):
    print(f"[CFBox Deploy] {msg}", flush=True)

def prepare_dist_folder():
    """准备 Pages 部署文件 (Advanced Mode 需要根目录 _worker.js)"""
    if not os.path.exists(CFBOX_SOURCE):
        raise FileNotFoundError(f"未找到 CFBox 源码: {CFBOX_SOURCE}")
    
    os.makedirs(DIST_DIR, exist_ok=True)
    target_worker = os.path.join(DIST_DIR, "_worker.js")
    shutil.copy2(CFBOX_SOURCE, target_worker)
    
    # 创建一个默认 index.html 占位
    target_html = os.path.join(DIST_DIR, "index.html")
    with open(target_html, "w", encoding="utf-8") as f:
        f.write("<!DOCTYPE html><html><head><title>EdgeTunnel</title></head><body><h1>EdgeTunnel Service is Active</h1></body></html>")
        
    log(f"已生成 Pages 发布文件目录: {DIST_DIR} (包含 _worker.js 与 index.html)")

def get_or_create_kv_namespace(headers: dict, account_id: str, title: str = "CFBOX_KV") -> str:
    """查询或自动创建 Cloudflare KV 命名空间"""
    log(f"正在检查 Cloudflare KV 命名空间 [{title}]...")
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/storage/kv/namespaces"
    
    status_code, resp_text = http_request("GET", url, headers)
    if status_code != 200:
        raise Exception(f"获取 KV 列表失败 (HTTP {status_code}): {resp_text}")
        
    data = json.loads(resp_text)
    for item in data.get("result", []):
        if item.get("title") == title:
            log(f"复用已存在的 KV 命名空间: {title} (ID: {item['id']})")
            return item["id"]
            
    # 创建新的 KV
    log(f"未找到 KV 命名空间，正在自动创建 [{title}]...")
    status_code, resp_text = http_request("POST", url, headers, payload={"title": title})
    if status_code != 200:
        raise Exception(f"创建 KV 命名空间失败 (HTTP {status_code}): {resp_text}")
        
    new_item = json.loads(resp_text).get("result", {})
    kv_id = new_item.get("id")
    log(f"✅ 成功创建 KV 命名空间: {title} (ID: {kv_id})")
    return kv_id

def setup_pages_project(headers: dict, account_id: str, project_name: str, kv_id: str, user_uuid: str, custom_path: str = ""):
    """创建或更新 Pages 项目配置（绑定 KV 变量 K，绑定环境变量 U）"""
    log(f"正在检查 Pages 项目 [{project_name}]...")
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/pages/projects/{project_name}"
    
    status_code, _ = http_request("GET", url, headers)
    project_exists = (status_code == 200)
    
    env_vars = {
        "U": {"type": "plain_text", "value": user_uuid}
    }
    if custom_path:
        env_vars["d"] = {"type": "plain_text", "value": custom_path}
        
    deployment_configs = {
        "production": {
            "env_vars": env_vars,
            "kv_namespaces": {
                "K": {"namespace_id": kv_id}
            },
            "compatibility_date": "2024-09-01",
            "compatibility_flags": ["nodejs_compat"]
        },
        "preview": {
            "env_vars": env_vars,
            "kv_namespaces": {
                "K": {"namespace_id": kv_id}
            },
            "compatibility_date": "2024-09-01",
            "compatibility_flags": ["nodejs_compat"]
        }
    }

    if not project_exists:
        log(f"Pages 项目 [{project_name}] 不存在，正在创建并绑定 KV 与环境变量...")
        create_url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/pages/projects"
        create_payload = {
            "name": project_name,
            "production_branch": "main",
            "deployment_configs": deployment_configs
        }
        status_code, resp_text = http_request("POST", create_url, headers, payload=create_payload)
        if status_code not in (200, 201):
            raise Exception(f"创建 Pages 项目失败 (HTTP {status_code}): {resp_text}")
        log(f"✅ Pages 项目 [{project_name}] 创建成功！")
    else:
        log(f"Pages 项目 [{project_name}] 已存在，正在更新绑定配置 (KV 'K' 及环境变量 'U')...")
        patch_payload = {
            "deployment_configs": deployment_configs
        }
        status_code, resp_text = http_request("PATCH", url, headers, payload=patch_payload)
        if status_code != 200:
            log(f"⚠️ 更新 Pages 配置提示 (HTTP {status_code}): {resp_text}")
        else:
            log(f"✅ Pages 项目配置更新成功！")

def deploy_with_wrangler(account_id: str, api_token: str, project_name: str):
    """调用 npx wrangler 执行 Pages 发布"""
    log("正在启动 Wrangler 上传构建包并发布到 Cloudflare Pages...")
    env = os.environ.copy()
    env["CLOUDFLARE_ACCOUNT_ID"] = account_id
    env["CLOUDFLARE_API_TOKEN"] = api_token
    
    cmd = ["npx", "wrangler", "pages", "deploy", DIST_DIR, "--project-name", project_name, "--branch", "main", "--commit-dirty=true"]
    
    process = subprocess.Popen(
        cmd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        shell=True if sys.platform == "win32" else False
    )
    
    deployment_url = f"https://{project_name}.pages.dev"
    while True:
        line = process.stdout.readline()
        if not line and process.poll() is not None:
            break
        if line:
            stripped = line.strip()
            print(f"[Wrangler] {stripped}")
            if "pages.dev" in stripped and ("http://" in stripped or "https://" in stripped):
                for part in stripped.split():
                    if "pages.dev" in part and part.startswith("http"):
                        deployment_url = part
                        
    ret_code = process.poll()
    if ret_code != 0:
        raise Exception(f"Wrangler 部署失败，退出码: {ret_code}")
        
    log(f"✅ Wrangler 部署执行成功！发布页面: {deployment_url}")
    return deployment_url

def main():
    parser = argparse.ArgumentParser(description="自动化部署 CFBox 至 Cloudflare Pages")
    parser.add_argument("--account-id", help="Cloudflare Account ID (32位)")
    parser.add_argument("--api-token", help="Cloudflare API Token (需具备 Pages 与 KV 编辑权限)")
    parser.add_argument("--project-name", default="cfbox", help="Pages 项目名称 (默认: cfbox)")
    parser.add_argument("--uuid", help="自定义 UUID (留空自动生成)")
    parser.add_argument("--custom-path", default="", help="自定义面板访问路径 (可选)")
    args = parser.parse_args()

    cfg = get_config()
    deploy_cfg = cfg.get("cf_deploy", {})
    
    account_id = args.account_id or deploy_cfg.get("account_id") or os.environ.get("CLOUDFLARE_ACCOUNT_ID")
    api_token = args.api_token or deploy_cfg.get("api_token") or os.environ.get("CLOUDFLARE_API_TOKEN")
    project_name = args.project_name or deploy_cfg.get("project_name", "cfbox")
    user_uuid = args.uuid or deploy_cfg.get("uuid") or str(uuid.uuid4())
    custom_path = args.custom_path or deploy_cfg.get("custom_path", "")

    if not account_id:
        if sys.stdin.isatty():
            account_id = input("请输入 Cloudflare Account ID: ").strip()
        else:
            log("❌ 错误: 缺少 Cloudflare Account ID，请通过参数或配置文件指定。")
            sys.exit(1)

    if not api_token:
        if sys.stdin.isatty():
            api_token = input("请输入 Cloudflare API Token: ").strip()
        else:
            log("❌ 错误: 缺少 Cloudflare API Token，请通过参数或配置文件指定。")
            sys.exit(1)

    log("=" * 60)
    log("🚀 开始自动化部署 CFBox 到 Cloudflare Pages")
    log(f"项目名称: {project_name}")
    log(f"管理 UUID: {user_uuid}")
    log(f"自定义路径: {custom_path if custom_path else '(使用UUID)'}")
    log("=" * 60)

    prepare_dist_folder()

    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json"
    }

    # 获取或创建 KV 命名空间
    kv_id = get_or_create_kv_namespace(headers, account_id, title="CFBOX_KV")
    
    # 创建/更新 Pages 项目配置（绑定 KV: K, 环境变量: U）
    setup_pages_project(headers, account_id, project_name, kv_id, user_uuid, custom_path)

    # 调用 Wrangler 进行 Pages 部署
    deployment_url = deploy_with_wrangler(account_id, api_token, project_name)

    # 回写配置到 prober_config.json，自动打通实时同步闭环
    cfg["cf_deploy"] = {
        "account_id": account_id,
        "api_token": api_token,
        "project_name": project_name,
        "uuid": user_uuid,
        "custom_path": custom_path
    }
    
    cfg["cfbox_sync"] = {
        "enabled": True,
        "url": deployment_url,
        "uuid": user_uuid,
        "custom_path": custom_path,
        "max_nodes": 600000
    }
    save_config(cfg)
    log("✅ 部署信息已成功写入 prober_config.json，CFBox 实时同步通道已自动就绪！")

    log("正在尝试执行首次节点同步...")
    try:
        from sync_cfbox import sync_to_cfbox
        sync_ok, sync_msg = sync_to_cfbox()
        log(f"首次同步结果: {sync_msg}")
    except Exception as e:
        log(f"首次同步跳过: {e}")

    panel_path = custom_path if custom_path else user_uuid
    log("=" * 60)
    log("🎉 CFBox 部署圆满成功！")
    log(f"🌐 面板访问地址: {deployment_url}/{panel_path}")
    log(f"🔑 管理 UUID: {user_uuid}")
    log(f"📡 实时同步通道: 已打通 (prober_api 每次测速后将自动更新至此面板)")
    log("=" * 60)

if __name__ == "__main__":
    main()
