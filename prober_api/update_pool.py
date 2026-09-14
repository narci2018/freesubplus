import asyncio
import httpx
import base64
import urllib.parse
import json
import os
import socket
import sys
import tarfile
import zipfile
import shutil

# Check if geoip2 is available
try:
    import geoip2.database
except ImportError:
    print("Please install geoip2: pip install geoip2")
    sys.exit(1)

MMDB_URLS = [
    "https://gh.llkk.cc/https://github.com/P3TERX/GeoLite.mmdb/raw/download/GeoLite2-Country.mmdb",
    "https://ghp.ci/https://github.com/P3TERX/GeoLite.mmdb/raw/download/GeoLite2-Country.mmdb",
    "https://mirror.ghproxy.com/https://github.com/P3TERX/GeoLite.mmdb/raw/download/GeoLite2-Country.mmdb",
    "https://ghproxy.net/https://github.com/P3TERX/GeoLite.mmdb/raw/download/GeoLite2-Country.mmdb",
    "https://raw.gitmirror.com/P3TERX/GeoLite.mmdb/download/GeoLite2-Country.mmdb",
    "https://ghproxy.cn/https://github.com/P3TERX/GeoLite.mmdb/raw/download/GeoLite2-Country.mmdb",
    "https://github.com/P3TERX/GeoLite.mmdb/raw/download/GeoLite2-Country.mmdb"
]
MMDB_PATH = "GeoLite2-Country.mmdb"
CONFIG_PATH = "prober_config.json"
CACHE_PATH = "cached_pool.txt"

async def download_mmdb():
    local_mmdb = "GeoLite2-Country-local.mmdb"
    if os.path.exists(local_mmdb):
        if not os.path.exists(MMDB_PATH) or os.path.getmtime(local_mmdb) > os.path.getmtime(MMDB_PATH):
            import shutil
            shutil.copy2(local_mmdb, MMDB_PATH)
            print(f"Using local {local_mmdb} for MMDB.")
        return
    else:
        print(f"Local fallback {local_mmdb} not found. Please click 'Update GeoLite2' or provide the file manually.")
        sys.exit(1)

async def resolve_domain(domain):
    try:
        loop = asyncio.get_running_loop()
        ip = await loop.run_in_executor(None, socket.gethostbyname, domain)
        return ip
    except Exception:
        return None

async def process_subscriptions():
    await download_mmdb()
    
    # Load config
    sub_urls = []
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                sub_urls = cfg.get("subscriptions", [])
        except Exception as e:
            print(f"Failed to load config: {e}")
            
    if not sub_urls:
        print("No subscriptions found in config.")
        return

    reader = geoip2.database.Reader(MMDB_PATH)
    
    print("Fetching subscriptions concurrently...")
    
    async def fetch_url(client, url):
        url = url.strip()
        if not url: return set()
        print(f"Fetching {url}...")
        nodes = set()
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            text = resp.text
            try:
                if not ("#" in text or "." in text):
                    text = base64.b64decode(text).decode('utf-8')
            except Exception:
                pass
            
            for line in text.splitlines():
                line = line.strip()
                if not line: continue
                ip_port = line
                if "://" in line:
                    try:
                        scheme, rest = line.split("://", 1)
                        host_port_path = rest.split("@", 1)[-1]
                        host_port = host_port_path.split("?")[0].split("/")[0]
                        ip_port = host_port
                    except Exception:
                        continue
                else:
                    if "#" in line:
                        ip_port = line.split("#", 1)[0]
                        
                ip_port = ip_port.strip()
                if ":" in ip_port and ip_port.count(":") == 1:
                    nodes.add(ip_port)
                elif ":" not in ip_port:
                    nodes.add(f"{ip_port}:443")
        except Exception as e:
            print(f"Error fetching {url}: {e}")
        return nodes

    raw_nodes = set()
    async with httpx.AsyncClient(timeout=15.0, verify=False) as client:
        tasks = [fetch_url(client, url) for url in sub_urls if url.strip()]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for res in results:
            if isinstance(res, set):
                raw_nodes.update(res)

    print(f"Found {len(raw_nodes)} raw nodes. Resolving and locating...")
    
    # Resolve domains concurrently
    results = []
    for node in raw_nodes:
        host, port = node, "443"
        if node.count(":") == 1:
            host, port = node.split(":")
        elif node.startswith("[") and "]:" in node:
            parts = node.split("]:")
            host = parts[0][1:]
            port = parts[1]
            
        ip = host
        # Basic check if it's an IPv4 or IPv6
        is_ip = False
        try:
            socket.inet_pton(socket.AF_INET, host)
            is_ip = True
        except socket.error:
            try:
                socket.inet_pton(socket.AF_INET6, host)
                is_ip = True
            except socket.error:
                pass
                
        results.append({"original": node, "host": host, "port": port, "is_ip": is_ip, "ip": ip if is_ip else None})

    # Resolve domains
    domains_to_resolve = [r for r in results if not r["is_ip"]]
    tasks = [resolve_domain(r["host"]) for r in domains_to_resolve]
    resolved_ips = await asyncio.gather(*tasks)
    
    for r, ip in zip(domains_to_resolve, resolved_ips):
        r["ip"] = ip
        
    # GeoIP Lookup
    output_lines = []
    country_counts = {}
    
    for r in results:
        ip = r["ip"]
        if not ip: continue
        try:
            response = reader.country(ip)
            iso_code = response.country.iso_code
            if not iso_code: continue
            
            # Use original node representation + Country Code
            # Format: 1.1.1.1:443#[US] or domain.com:443#[JP]
            # Since the user requested something like "155.248.181.189:443#[JP 日本]"
            # We will use just the ISO code and standard names if available.
            name = response.country.names.get('zh-CN', response.country.name) or iso_code
            formatted = f"{r['original']}#[{iso_code} {name}]"
            output_lines.append(formatted)
            
            country_counts[iso_code] = country_counts.get(iso_code, 0) + 1
        except geoip2.errors.AddressNotFoundError:
            pass
        except Exception:
            pass

    # Save to cached_pool.txt
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(output_lines))
        
    print(f"Update complete. {len(output_lines)} valid nodes cached.")
    print("Country distribution:", country_counts)

if __name__ == "__main__":
    import asyncio
    import sys
    asyncio.run(process_subscriptions())
    sys.exit(0)
