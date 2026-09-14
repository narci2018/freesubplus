#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自动检查并下载/更新运行所需组件 (sing-box 官方内核 + GeoLite2 离线数据库)
具备版本比对与时效检查: 仅当组件缺失或版本过旧时才重新下载，避免重复下载。
"""

import os
import re
import sys
import time
import shutil
import tarfile
import zipfile
import platform
import subprocess
import urllib.parse
from pathlib import Path

try:
    import requests
except ImportError:
    print("[!] 缺少 requests 库，请先安装依赖: pip install requests")
    sys.exit(1)

SINGBOX_VERSION = "v1.14.0"
BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_RUNTIME_DIR = BASE_DIR / "runtime"

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Mozilla/5.0 (FreeSub-Asset-Downloader)"})


def get_singbox_installed_version(exe_path: str) -> str:
    """检查已安装 sing-box 的版本号"""
    if not os.path.exists(exe_path) or os.path.getsize(exe_path) < 1024:
        return ""
    try:
        res = subprocess.run([exe_path, "version"], capture_output=True, text=True, timeout=10)
        out = (res.stdout or "") + (res.stderr or "")
        # 匹配 version 1.14.0 或 v1.14.0
        m = re.search(r"sing-box version\s+([v\d\.]+)", out, re.IGNORECASE)
        if m:
            ver = m.group(1).strip()
            return ver if ver.startswith("v") else f"v{ver}"
    except Exception:
        pass
    return ""


def download_with_mirrors(url: str, dest: Path, desc: str, timeout: int = 35) -> bool:
    """使用多路国内高速加速源下载文件，支持实时分块进度与原子写入"""
    filename = dest.name
    mirrors = []

    if "github.com" in url or "raw.githubusercontent.com" in url:
        # jsdelivr 镜像 (针对 raw 文件有效)
        m = re.match(r"^https://(?:github\.com|raw\.githubusercontent\.com)/([^/]+)/([^/]+)/(?:raw|releases/download)/(.+)$", url)
        if m and "releases/download" not in url:
            owner, repo, path = m.groups()
            mirrors.append(f"https://cdn.jsdelivr.net/gh/{owner}/{repo.replace('.git','')}@{path}")

        # 高速 GitHub 反代加速节点
        mirrors.append(f"https://ghproxy.net/{url}")
        mirrors.append(f"https://gh.ddlc.top/{url}")
        mirrors.append(f"https://mirror.ghproxy.com/{url}")

    # 原始地址作为最后兜底
    mirrors.append(url)

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = dest.with_suffix(".part")
    print(f"[*] 开始下载 {desc} ({filename})...")

    for mirror in mirrors:
        domain = urllib.parse.urlparse(mirror).netloc or "origin"
        print(f"[*] 尝试从节点 [{domain}] 获取...")
        try:
            with SESSION.get(mirror, timeout=timeout, stream=True) as r:
                r.raise_for_status()
                total = int(r.headers.get("content-length", 0))
                downloaded = 0
                last_log = time.time()
                with open(tmp_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=512 * 1024):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            now = time.time()
                            if now - last_log >= 2.0:
                                last_log = now
                                if total > 0:
                                    pct = int(downloaded / total * 100)
                                    print(f"[*] {desc} 进度: {downloaded//(1024*1024)}MB / {total//(1024*1024)}MB ({pct}%)")
                                else:
                                    print(f"[*] {desc} 已下载: {downloaded//1024} KB...")

            if tmp_path.stat().st_size < 1024:
                raise RuntimeError(f"文件大小异常: {tmp_path.stat().st_size} bytes")

            tmp_path.replace(dest)
            print(f"[+] {desc} 下载完成! (大小: {dest.stat().st_size // 1024} KB)")
            return True
        except Exception as e:
            print(f"[!] 节点 [{domain}] 连接超时或失败 ({str(e)[:50]}), 自动尝试下一个镜像...")

    if tmp_path.exists():
        try:
            tmp_path.unlink()
        except OSError:
            pass
    return False


def ensure_singbox(runtime_dir: Path, force_update: bool = False):
    """确保 sing-box 内核处于指定版本，若已是最新则自动跳过"""
    is_win = os.name == "nt"
    exe_name = "sing-box.exe" if is_win else "sing-box"
    exe_path = runtime_dir / exe_name

    installed_ver = get_singbox_installed_version(str(exe_path))
    target_ver = SINGBOX_VERSION.lstrip("v")

    if not force_update and installed_ver and target_ver in installed_ver:
        print(f"[✓] sing-box 内核已是最新版 ({installed_ver})，无需重新下载。")
        return

    if installed_ver:
        print(f"[*] 检测到旧版本 sing-box ({installed_ver})，准备更新至 v{target_ver}...")
    else:
        print(f"[*] 未检测到可用 sing-box 内核，准备下载 v{target_ver}...")

    system = "windows" if is_win else "linux"
    ext = "zip" if is_win else "tar.gz"

    machine = platform.machine().lower()
    arch = "arm64" if ("arm" in machine or "aarch64" in machine) else "amd64"

    url = (f"https://github.com/SagerNet/sing-box/releases/download/"
           f"{SINGBOX_VERSION}/sing-box-{target_ver}-{system}-{arch}.{ext}")
    archive_path = runtime_dir / f"sing-box.{ext}"

    ok = download_with_mirrors(url, archive_path, f"sing-box {SINGBOX_VERSION} 内核")
    if not ok:
        raise RuntimeError("sing-box 内核下载失败，请检查网络连接")

    # 解压内核
    print(f"[*] 正在解压内核到 {runtime_dir}...")
    if is_win:
        with zipfile.ZipFile(archive_path) as z:
            for name in z.namelist():
                if name.endswith("sing-box.exe"):
                    with z.open(name) as src, open(exe_path, "wb") as dst:
                        shutil.copyfileobj(src, dst)
    else:
        with tarfile.open(archive_path) as t:
            for m in t.getmembers():
                if m.name.endswith("sing-box"):
                    f = t.extractfile(m)
                    with open(exe_path, "wb") as dst:
                        shutil.copyfileobj(f, dst)
        os.chmod(exe_path, 0o755)

    try:
        archive_path.unlink()
    except OSError:
        pass

    new_ver = get_singbox_installed_version(str(exe_path))
    print(f"[+] sing-box 内核安装就绪: {new_ver}")


def ensure_geolite(runtime_dir: Path, force_update: bool = False):
    """确保 GeoLite2 数据库存在（超过 14 天可自动更新）"""
    country_file = runtime_dir / "Country.mmdb"
    asn_file = runtime_dir / "ASN.mmdb"

    now = time.time()
    # 14 天过期检测 (14 * 86400 = 1209600s)
    country_need = force_update or not country_file.exists() or country_file.stat().st_size < 1024 or (now - country_file.stat().st_mtime > 1209600)
    asn_need = force_update or not asn_file.exists() or asn_file.stat().st_size < 1024 or (now - asn_file.stat().st_mtime > 1209600)

    if not country_need and not asn_need:
        print(f"[✓] GeoLite2 离线数据库均处于有效期内，无需重新下载。")
        return

    if country_need:
        ok = download_with_mirrors(
            "https://github.com/P3TERX/GeoLite.mmdb/raw/download/GeoLite2-Country.mmdb",
            country_file,
            "GeoLite2 Country 数据库"
        )
        if not ok:
            print("[!] GeoLite2 Country 数据库下载异常，若存在旧版将继续沿用")

    if asn_need:
        ok = download_with_mirrors(
            "https://github.com/P3TERX/GeoLite.mmdb/raw/download/GeoLite2-ASN.mmdb",
            asn_file,
            "GeoLite2 ASN 数据库"
        )
        if not ok:
            print("[!] GeoLite2 ASN 数据库下载异常，若存在旧版将继续沿用")


def sync_all_assets(target_dir: Path = None, force_update: bool = False):
    runtime_dir = target_dir or Path(os.environ.get("RUNTIME_DIR", DEFAULT_RUNTIME_DIR))
    runtime_dir.mkdir(parents=True, exist_ok=True)

    print(f"==== 检查 FreeSub 依赖组件 (目录: {runtime_dir}) ====")
    ensure_singbox(runtime_dir, force_update=force_update)
    ensure_geolite(runtime_dir, force_update=force_update)
    print("==== 组件就绪检查完毕 ====\n")


if __name__ == "__main__":
    force = "--force" in sys.argv
    custom_dir = None
    for arg in sys.argv[1:]:
        if arg.startswith("--runtime-dir="):
            custom_dir = Path(arg.split("=", 1)[1])
        elif not arg.startswith("--"):
            custom_dir = Path(arg)

    sync_all_assets(target_dir=custom_dir, force_update=force)
