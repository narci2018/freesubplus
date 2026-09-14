import sys
import json
import asyncio
import ipaddress
import random
import os
import time

PROGRESS_FILE = "scan_progress.json"
RESULTS_FILE = "local_custom_pool.txt"

async def check_ip(ip: str, port: int, sem: asyncio.Semaphore):
    async with sem:
        writer = None
        try:
            start_time = time.time()
            reader, writer = await asyncio.wait_for(asyncio.open_connection(ip, port), timeout=1.5)
            latency = (time.time() - start_time) * 1000
            return True, ip, port, latency
        except Exception:
            return False, ip, port, 0
        finally:
            # 修复：wait_for 超时取消时 socket 不会自动关闭，必须在 finally 里显式关闭
            if writer is not None:
                try:
                    writer.close()
                    await asyncio.wait_for(writer.wait_closed(), timeout=0.5)
                except Exception:
                    pass


async def main():
    if len(sys.argv) < 3:
        print("Usage: scanner.py <country> <ports_csv> [<country_name>]")
        return
        
    country = sys.argv[1]
    ports = [int(p) for p in sys.argv[2].split(",")]
    country_name = sys.argv[3] if len(sys.argv) > 3 else country.upper()
    
    # Load CIDRs from sys.argv or from a temp file if too long
    # Since command line has length limits, better to read from a temp file
    cidrs = []
    with open("temp_scan_req.json", "r") as f:
        req = json.load(f)
        cidrs = req.get("cidrs", [])
        
    print(f"Expanding {len(cidrs)} CIDRs for country {country}...")
    
    # Update progress
    def write_progress(scanned, total, is_running):
        with open(PROGRESS_FILE, "w") as f:
            json.dump({"scanned": scanned, "total": total, "is_running": is_running}, f)
            
    write_progress(0, 0, True)
    
    # Expand CIDRs
    all_ips = []
    for cidr in cidrs:
        try:
            net = ipaddress.ip_network(cidr, strict=False)
            # Cap maximum IPs to avoid memory explosion if user selects a /8
            # In a real scanner we'd use a generator, but for simple asyncio we load to list.
            for ip in net:
                all_ips.append(str(ip))
                if len(all_ips) > 500000:
                    break # hard limit for memory safety in Python
        except Exception:
            pass
            
    # Randomize to spread the load
    random.shuffle(all_ips)
    
    # Limit max IPs to scan to something reasonable for a script, e.g. 50,000 to prevent locking up for hours.
    # The user can run it multiple times.
    if len(all_ips) > 100000:
        all_ips = all_ips[:100000]
        
    total_tasks = len(all_ips) * len(ports)
    write_progress(0, total_tasks, True)
    
    sem = asyncio.Semaphore(200)
    
    tasks = []
    scanned_count = 0
    found_ips = []
    new_found_ips = []
    is_running = True
    
    # Clear previous results
    with open(RESULTS_FILE, "w") as f:
        f.write("")
        
    async def progress_monitor():
        while is_running:
            # Write progress
            try:
                write_progress(scanned_count, total_tasks, True)
            except Exception:
                pass
            
            # Write new found results
            if new_found_ips:
                try:
                    with open(RESULTS_FILE, "a") as f:
                        for res in new_found_ips:
                            f.write(res + "\n")
                    new_found_ips.clear()
                except Exception:
                    pass
            await asyncio.sleep(2)
            
    monitor_task = asyncio.create_task(progress_monitor())
        
    async def worker(ip, port):
        nonlocal scanned_count
        success, ip_str, p, latency = await check_ip(ip, port, sem)
        scanned_count += 1
        
        if success:
            result_str = f"{ip_str}:{p}#[{country.upper()} {country_name} {latency:.2f}ms]"
            found_ips.append(result_str)
            new_found_ips.append(result_str)
                
    is_throttled = "--throttle" in sys.argv
    if is_throttled:
        chunk_size = 500
    else:
        chunk_size = 5000
        
    for i in range(0, len(all_ips), chunk_size):
        chunk_ips = all_ips[i:i+chunk_size]
        tasks = []
        for ip in chunk_ips:
            for port in ports:
                tasks.append(asyncio.create_task(worker(ip, port)))
        await asyncio.gather(*tasks)
        if is_throttled:
            await asyncio.sleep(1.5)
        
    is_running = False
    await monitor_task
    
    # Final flush
    write_progress(total_tasks, total_tasks, False)
    if new_found_ips:
        with open(RESULTS_FILE, "a") as f:
            for res in new_found_ips:
                f.write(res + "\n")

if __name__ == "__main__":
    asyncio.run(main())
