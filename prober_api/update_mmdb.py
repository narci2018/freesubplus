import asyncio
import httpx
import os
import shutil
import sys

MMDB_URLS = [
    "https://gh.llkk.cc/https://github.com/P3TERX/GeoLite.mmdb/raw/download/GeoLite2-Country.mmdb",
    "https://ghp.ci/https://github.com/P3TERX/GeoLite.mmdb/raw/download/GeoLite2-Country.mmdb",
    "https://mirror.ghproxy.com/https://github.com/P3TERX/GeoLite.mmdb/raw/download/GeoLite2-Country.mmdb",
    "https://ghproxy.net/https://github.com/P3TERX/GeoLite.mmdb/raw/download/GeoLite2-Country.mmdb",
    "https://raw.gitmirror.com/P3TERX/GeoLite.mmdb/download/GeoLite2-Country.mmdb",
    "https://ghproxy.cn/https://github.com/P3TERX/GeoLite.mmdb/raw/download/GeoLite2-Country.mmdb",
    "https://github.com/P3TERX/GeoLite.mmdb/raw/download/GeoLite2-Country.mmdb"
]

LOCAL_PATH = "GeoLite2-Country-local.mmdb"
PROD_PATH = "GeoLite2-Country.mmdb"

async def main():
    print("Downloading GeoLite2-Country.mmdb...")
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        for url in MMDB_URLS:
            print(f"Trying to download from {url}...")
            try:
                resp = await client.get(url)
                resp.raise_for_status()
                with open(LOCAL_PATH, "wb") as f:
                    f.write(resp.content)
                print(f"Downloaded successfully to {LOCAL_PATH}.")
                
                # Copy to PROD_PATH so it takes effect immediately
                shutil.copy2(LOCAL_PATH, PROD_PATH)
                print("Applied successfully.")
                return
            except Exception as e:
                print(f"Failed to download from {url}: {e}")
                
        print("All attempts to download MMDB failed.")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
