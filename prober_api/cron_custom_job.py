import sys
import json
import subprocess
import os

CUSTOM_JOBS_FILE = "custom_jobs.json"

def main():
    if len(sys.argv) < 2:
        print("Usage: cron_custom_job.py <job_id>")
        return
        
    job_id = sys.argv[1]
    
    # Load jobs
    if not os.path.exists(CUSTOM_JOBS_FILE):
        return
        
    with open(CUSTOM_JOBS_FILE, "r", encoding="utf-8") as f:
        try:
            jobs = json.load(f)
        except Exception:
            return
            
    if job_id not in jobs:
        return
        
    job = jobs[job_id]
    
    # Update status to running
    job["status"] = "running"
    with open(CUSTOM_JOBS_FILE, "w", encoding="utf-8") as f:
        json.dump(jobs, f, indent=4)
        
    # Write cidrs to temp file for scanner
    with open("temp_scan_req.json", "w", encoding="utf-8") as f:
        json.dump({"cidrs": job["cidrs"]}, f)
        
    ports_str = ",".join(map(str, job["ports"]))
    country = job["country"]
    country_name = job["country_name"]
    
    print(f"Starting custom scan for {job_id} ({country_name}) with ports {ports_str}...")
    
    # Run scanner with throttle
    cmd = [sys.executable, "-u", "scanner.py", country, ports_str, country_name, "--throttle"]
    
    # Important: wait for it to finish
    result = subprocess.run(cmd)
    
    if result.returncode == 0 and os.path.exists("local_custom_pool.txt"):
        print("Scanner finished successfully. Sorting and Uploading to Gist...")
        
        # --- SORTING LOGIC ---
        try:
            with open("local_custom_pool.txt", "r", encoding="utf-8") as f:
                lines = f.read().splitlines()
                
            parsed_nodes = []
            for line in lines:
                if "#" not in line: continue
                ip_port, info = line.split("#", 1)
                info = info.strip("[]")
                parts = info.split()
                if len(parts) >= 3:
                    c_code = parts[0]
                    c_name = " ".join(parts[1:-1])
                    latency_str = parts[-1].replace("ms", "")
                    try:
                        latency = float(latency_str)
                    except:
                        latency = 9999.0
                    parsed_nodes.append({
                        "line": line,
                        "ip": ip_port.split(":")[0],
                        "port": ip_port.split(":")[1] if ":" in ip_port else "443",
                        "c_code": c_code,
                        "c_name": c_name,
                        "latency": latency
                    })
            
            if country == "ALL":
                import ipaddress
                import re
                
                # Load country name mapping
                name_map = {}
                try:
                    with open("custom_sub.html", "r", encoding="utf-8") as hf:
                        html = hf.read()
                    for match in re.finditer(r'<option value="([A-Z]{2})">([^（]+)（', html):
                        name_map[match.group(1)] = match.group(2)
                except:
                    pass

                ip_objs = {n["ip"]: ipaddress.ip_address(n["ip"]) for n in parsed_nodes}
                
                if os.path.exists("countries"):
                    for f_name in os.listdir("countries"):
                        if not f_name.endswith(".zone"): continue
                        real_c_code = f_name.replace(".zone", "").upper()
                        real_c_name = name_map.get(real_c_code, real_c_code)
                        
                        try:
                            with open(os.path.join("countries", f_name), "r") as zf:
                                for cidr_str in zf:
                                    cidr_str = cidr_str.strip()
                                    if not cidr_str: continue
                                    try:
                                        net = ipaddress.ip_network(cidr_str, strict=False)
                                        matched_ips = []
                                        for ip_str, ip_obj in ip_objs.items():
                                            if ip_obj in net:
                                                for n in parsed_nodes:
                                                    if n["ip"] == ip_str:
                                                        n["c_code"] = real_c_code
                                                        n["c_name"] = real_c_name
                                                        n["line"] = f'{n["ip"]}:{n["port"]}#[{real_c_code} {real_c_name} {n["latency"]:.2f}ms]'
                                                matched_ips.append(ip_str)
                                        for mip in matched_ips:
                                            del ip_objs[mip]
                                        if not ip_objs:
                                            break
                                    except:
                                        pass
                        except:
                            pass
                        if not ip_objs:
                            break
                            
                parsed_nodes.sort(key=lambda x: (x["c_code"], x["latency"]))
            else:
                parsed_nodes.sort(key=lambda x: x["latency"])
                
            with open("local_custom_pool.txt", "w", encoding="utf-8") as f:
                for n in parsed_nodes:
                    f.write(n["line"] + "\n")
            import shutil
            shutil.copy2("local_custom_pool.txt", f"job_results_{job_id}.txt")
        except Exception as e:
            print(f"Sorting failed: {e}")
        # --- END SORTING LOGIC ---
        
        # Load GitHub Token
        config = {}
        if os.path.exists("prober_config.json"):
            with open("prober_config.json", "r", encoding="utf-8") as f:
                try:
                    config = json.load(f)
                except Exception:
                    pass
        
        token = config.get("github_token", "")
        if token:
            gist_filename = f"best_cf_{country.lower()}_ips.txt"
            
            # Execute gist_uploader.py
            ul_cmd = [sys.executable, "-u", "gist_uploader.py", token, gist_filename, "local_custom_pool.txt"]
            # Capture output to get GIST_URL
            ul_proc = subprocess.run(ul_cmd, capture_output=True, text=True)
            gist_url = ""
            for line in ul_proc.stdout.splitlines():
                if line.startswith("GIST_URL="):
                    gist_url = line.split("GIST_URL=")[1].strip()
                    break
                    
            if gist_url:
                job["gist_url"] = gist_url
                job["run_count"] = job.get("run_count", 0) + 1
            else:
                job["fail_count"] = job.get("fail_count", 0) + 1
        else:
            print("No GitHub Token set, skipping Gist upload.")
            job["fail_count"] = job.get("fail_count", 0) + 1
    else:
        print("Scanner failed or no results.")
        job["fail_count"] = job.get("fail_count", 0) + 1
        
    job["status"] = "idle"
    
    # Reload and save to avoid overwriting other edits
    with open(CUSTOM_JOBS_FILE, "r", encoding="utf-8") as f:
        try:
            curr_jobs = json.load(f)
            curr_jobs[job_id].update(job)
            with open(CUSTOM_JOBS_FILE, "w", encoding="utf-8") as f:
                json.dump(curr_jobs, f, indent=4)
        except Exception:
            pass

if __name__ == "__main__":
    main()
