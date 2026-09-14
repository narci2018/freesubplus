import re
import socket
import time
import requests
from concurrent.futures import ThreadPoolExecutor
from web.config_mgr import config_mgr

# 默认高质量 Cloudflare Anycast Clean IP 备用池（三网多段覆盖）
BUILTIN_CLEAN_IPS = [
    {"ip": "162.159.192.1", "desc": "CF官方Anycast 1"},
    {"ip": "162.159.193.1", "desc": "CF官方Anycast 2"},
    {"ip": "104.16.160.1", "desc": "CF优化段 1"},
    {"ip": "104.17.160.1", "desc": "CF优化段 2"},
    {"ip": "172.64.32.1", "desc": "CF优质节点 1"},
    {"ip": "108.162.236.1", "desc": "CF亚太优化段"},
    {"ip": "141.101.120.1", "desc": "CF香港/国际段"},
    {"ip": "188.114.96.1", "desc": "CF欧洲/中东段"}
]


class CloudflareOptimizer:
    def __init__(self):
        self._tested_clean_ips = []
        self._last_test_time = 0

    def is_cloudflare_node(self, outbound: dict) -> bool:
        """判断一个节点是否属于 Cloudflare 代理（Workers/Pages 反代）"""
        if not outbound:
            return False

        tls = outbound.get("tls") or {}
        transport = outbound.get("transport") or {}
        server = str(outbound.get("server", "")).lower()

        # 1) SNI 检查
        sni = str(tls.get("server_name", "")).lower()
        if any(d in sni for d in ("workers.dev", "pages.dev", "cloudflare")):
            return True

        # 2) Transport Host / Path 检查
        headers = transport.get("headers") or {}
        host = str(headers.get("Host", "")).lower()
        if any(d in host for d in ("workers.dev", "pages.dev", "cloudflare")):
            return True

        h2_host = transport.get("host")
        if isinstance(h2_host, list):
            for h in h2_host:
                if any(d in str(h).lower() for d in ("workers.dev", "pages.dev")):
                    return True
        elif isinstance(h2_host, str):
            if any(d in h2_host.lower() for d in ("workers.dev", "pages.dev")):
                return True

        # 3) Server 域名/IP 命中
        if any(d in server for d in ("workers.dev", "pages.dev", "cloudflare")):
            return True

        return False

    def fetch_online_clean_ips(self) -> list:
        """从公开优选源异步拉取最新可用 Clean IP 列表"""
        cfg = config_mgr.get_config().get("cf_clean_ip", {})
        urls = cfg.get("fetch_urls", [])
        ips = set()

        for url in urls:
            try:
                r = requests.get(url, timeout=6)
                if r.status_code == 200:
                    text = r.text
                    # 匹配 IPv4 地址
                    matches = re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", text)
                    for ip in matches:
                        # 简单过滤局域网或广播
                        if not ip.startswith(("127.", "192.168.", "10.", "0.")):
                            ips.add(ip)
            except Exception as e:
                print(f"[!] 拉取优选IP源失败 {url}: {e}")

        # 混合用户自定义 IP
        for ip in cfg.get("custom_ips", []):
            if ip and re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", ip.strip()):
                ips.add(ip.strip())

        # 若在线拉取失败，兜底内置列表
        if not ips:
            for item in BUILTIN_CLEAN_IPS:
                ips.add(item["ip"])

        return list(ips)

    def test_ip_latency(self, ip: str, port: int = 443, timeout: float = 1.2) -> int:
        """本地 TCP Ping 测延迟，返回毫秒数，失败返回 9999"""
        t0 = time.time()
        try:
            with socket.create_connection((ip, port), timeout=timeout):
                return int((time.time() - t0) * 1000)
        except Exception:
            return 9999

    def get_optimal_clean_ips(self, force_refresh: bool = False) -> list:
        """获取本地网络测试后延迟最低的 Clean IP 列表 (按延迟升序)"""
        now = time.time()
        # 缓存 15 分钟
        if not force_refresh and self._tested_clean_ips and (now - self._last_test_time < 900):
            return self._tested_clean_ips

        raw_ips = self.fetch_online_clean_ips()
        results = []

        def _probe(ip):
            lat = self.test_ip_latency(ip)
            if lat < 9000:
                return {"ip": ip, "latency": lat}
            return None

        with ThreadPoolExecutor(max_workers=20) as ex:
            for res in ex.map(_probe, raw_ips):
                if res:
                    results.append(res)

        results.sort(key=lambda x: x["latency"])
        self._tested_clean_ips = results
        self._last_test_time = now
        print(f"[+] 优选 IP 测速完成: 存活 {len(results)}/{len(raw_ips)}，最优 IP: {results[0] if results else '无'}")
        return results

    def optimize_candidates(self, candidates: list) -> list:
        """对全部候选节点中的 Cloudflare 节点进行优选 IP 注入与复制"""
        cfg = config_mgr.get_config().get("cf_clean_ip", {})
        if not cfg.get("enabled", True):
            return candidates

        optimal_ips = self.get_optimal_clean_ips()
        if not optimal_ips:
            print("[!] 未获取到有效优选 IP，保留原始节点连接目标")
            return candidates

        top_n = min(cfg.get("top_n_to_use", 2), len(optimal_ips))
        best_ips = optimal_ips[:top_n]

        new_candidates = []
        cf_count = 0

        for item in candidates:
            uri, outbound, server, port, proto = item
            if self.is_cloudflare_node(outbound):
                cf_count += 1
                # 保留原始的真实伪装头 (确保 Cloudflare 能正确反代回源)
                tls = outbound.setdefault("tls", {})
                transport = outbound.setdefault("transport", {})

                # 如果没有显式指定 SNI，把原 server 保存为 SNI
                if not tls.get("server_name"):
                    tls["server_name"] = server

                # 如果是 WS 传输层，确保 headers.Host 被保留
                if transport.get("type") == "ws":
                    headers = transport.setdefault("headers", {})
                    if not headers.get("Host"):
                        headers["Host"] = server

                # 衍生出最优连接 IP 的节点
                for opt in best_ips:
                    clean_ip = opt["ip"]
                    opt_outbound = dict(outbound)
                    opt_outbound["server"] = clean_ip
                    # 替换原连接地址
                    new_candidates.append((uri, opt_outbound, clean_ip, port, proto))
            else:
                new_candidates.append(item)

        print(f"[*] 优选 IP 注入完成: 识别 CF 节点 {cf_count} 个，注入后总节点数: {len(new_candidates)}")
        return new_candidates


cf_optimizer = CloudflareOptimizer()
