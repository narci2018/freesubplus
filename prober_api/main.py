import asyncio
import time
import os
import json
import subprocess
import sys
from typing import List, Optional, Dict
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

app = FastAPI()

CONFIG_PATH = "prober_config.json"
CACHE_PATH = "cached_pool.txt"
UPDATE_SCRIPT = "update_pool.py"

# --- Models ---
class SpeedtestRequest(BaseModel):
    countries: Optional[List[str]] = []
    port: int = 443
    timeout_ms: int = 1500
    limit: int = 1

class SpeedtestResponse(BaseModel):
    country_results: Optional[Dict[str, dict]] = None

class ConfigModel(BaseModel):
    subscriptions: List[str]
    cron_raw: str
    cron_tested: str
    github_token: str = ""

class CFBoxSyncModel(BaseModel):
    enabled: bool = False
    url: str = ""
    uuid: str = ""
    custom_path: str = ""
    max_nodes: int = 600000
    default_per_country: int = 0         # 0 = 不限；>0 = 每国默认上限
    country_rules: Dict[str, int] = {}   # 特殊国家覆盖，如 {"HK": 10, "US": 5}

class DeployCFBoxModel(BaseModel):
    account_id: str
    api_token: str
    project_name: str = "cfbox"
    uuid: Optional[str] = ""
    custom_path: Optional[str] = ""

# --- Global State ---
IP_POOL: Dict[str, List[str]] = {}
LAST_CACHE_MTIME = 0
scheduler = AsyncIOScheduler()

# --- Helpers ---
def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            # migration from old `cron_expression` if exists
            if "cron_expression" in cfg and "cron_raw" not in cfg:
                cfg["cron_raw"] = "0 0 * * 0"
                cfg["cron_tested"] = "*/30 * * * *"
            return cfg
            
    # Fallback to default.txt
    default_subs = []
    if os.path.exists("default.txt"):
        with open("default.txt", "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    default_subs.append(line.strip())
                    
    return {"subscriptions": default_subs, "cron_raw": "0 0 * * 0", "cron_tested": "*/30 * * * *"}

def save_config(new_data: dict):
    current = {}
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                current = json.load(f)
        except Exception as e:
            print(f"Error reading {CONFIG_PATH}: {e}")
            current = {}
            
    # 增量安全合并，确保 cfbox_sync、github_token 等所有字段绝不丢失
    current.update(new_data)
    
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(current, f, indent=4, ensure_ascii=False)
        f.flush()
        try:
            os.fsync(f.fileno())
        except Exception:
            pass
    print(f"[Config Saved] 已成功持久化配置至 {CONFIG_PATH}")
    return current
        
def reload_ip_pool():
    global IP_POOL, LAST_CACHE_MTIME
    if not os.path.isfile(CACHE_PATH):
        return
        
    mtime = os.path.getmtime(CACHE_PATH)
    if mtime == LAST_CACHE_MTIME:
        return
        
    new_pool = {}
    with open(CACHE_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or "#" not in line: continue
            ip_port, remark = line.split("#", 1)
            # remark format: [US 美国]
            if remark.startswith("[") and remark.endswith("]"):
                code = remark[1:3].upper() # extract US
                if code not in new_pool:
                    new_pool[code] = []
                new_pool[code].append(ip_port)
                
    IP_POOL = new_pool
    LAST_CACHE_MTIME = mtime
    print(f"Loaded {sum(len(v) for v in IP_POOL.values())} IPs from cache across {len(IP_POOL)} countries.")

def run_update_raw():
    print("Running background update_pool.py (Raw)...")
    subprocess.Popen([sys.executable, "-u", UPDATE_SCRIPT])
    
def run_update_tested():
    print("Running background test_pool.py (Tested)...")
    subprocess.Popen([sys.executable, "-u", "test_pool.py"])

# --- Custom Jobs Management ---
CUSTOM_JOBS_FILE = "custom_jobs.json"

class CustomJobUpdate(BaseModel):
    cron: str
    enabled: bool

class CustomJobCreate(BaseModel):
    country: str
    country_name: str
    cidrs: List[str]
    ports: List[int]
    cron: str = "0 0 * * 0"

def load_custom_jobs():
    if not os.path.exists(CUSTOM_JOBS_FILE):
        return {}
    try:
        with open(CUSTOM_JOBS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_custom_jobs(jobs):
    with open(CUSTOM_JOBS_FILE, "w", encoding="utf-8") as f:
        json.dump(jobs, f, indent=4)

def run_custom_job(job_id: str):
    print(f"Running background cron_custom_job.py for {job_id}...")
    subprocess.Popen([sys.executable, "-u", "cron_custom_job.py", job_id])

def _parse_and_add_job(cron_expr: str, func, job_id: str, args=None):
    if not cron_expr or cron_expr.strip() == "":
        return
    try:
        parts = cron_expr.strip().split()
        if len(parts) == 6:
            from apscheduler.triggers.cron import CronTrigger
            trigger = CronTrigger(second=parts[0], minute=parts[1], hour=parts[2], day=parts[3], month=parts[4], day_of_week=parts[5])
        elif len(parts) == 5:
            from apscheduler.triggers.cron import CronTrigger
            trigger = CronTrigger.from_crontab(cron_expr)
        else:
            raise ValueError(f"Cron expression must have 5 or 6 fields, got: {cron_expr}")
            
        if args:
            scheduler.add_job(func, trigger, id=job_id, args=args)
        else:
            scheduler.add_job(func, trigger, id=job_id)
    except Exception as e:
        print(f"Failed to schedule job {job_id} with cron '{cron_expr}': {e}")

def update_scheduler():
    config = load_config()
    cron_raw = config.get("cron_raw", "0 0 * * 0")
    cron_tested = config.get("cron_tested", "*/30 * * * *")
    
    # Remove old main jobs
    if scheduler.get_job("update_job_raw"):
        scheduler.remove_job("update_job_raw")
    if scheduler.get_job("update_job_tested"):
        scheduler.remove_job("update_job_tested")
        
    _parse_and_add_job(cron_raw, run_update_raw, "update_job_raw")
    _parse_and_add_job(cron_tested, run_update_tested, "update_job_tested")
    
    # Reload custom jobs
    jobs = load_custom_jobs()
    
    # Remove existing custom jobs from scheduler
    for j in scheduler.get_jobs():
        if j.id.endswith(".JOB"):
            scheduler.remove_job(j.id)
            
    for job_id, job in jobs.items():
        if job.get("enabled", True):
            _parse_and_add_job(job.get("cron", "0 0 * * 0"), run_custom_job, job_id, args=[job_id])

@app.on_event("startup")
async def startup_event():
    update_scheduler()
    scheduler.start()
    reload_ip_pool()
    # Trigger first run on startup (run both)
    subprocess.Popen([sys.executable, "-u", UPDATE_SCRIPT])
    subprocess.Popen([sys.executable, "-u", "test_pool.py"])

# --- Web UI ---
@app.get("/", response_class=HTMLResponse)
async def get_ui():
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>EdgeTunnel Prober 控制台</title>
        <meta charset="utf-8">
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background: #f8fafc; margin: 0; padding: 20px; color: #334155; }
            .container { max-width: 800px; margin: 0 auto; background: white; padding: 30px; border-radius: 12px; box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1); }
            h1 { margin-top: 0; color: #0f172a; border-bottom: 2px solid #e2e8f0; padding-bottom: 10px; }
            .form-group { margin-bottom: 20px; }
            label { display: block; font-weight: 600; margin-bottom: 8px; }
            textarea { width: 100%; height: 150px; padding: 10px; border: 1px solid #cbd5e1; border-radius: 6px; font-family: monospace; resize: vertical; box-sizing: border-box;}
            input[type="text"] { width: 100%; padding: 10px; border: 1px solid #cbd5e1; border-radius: 6px; font-family: monospace; box-sizing: border-box;}
            .btn { padding: 10px 20px; border: none; border-radius: 6px; font-weight: 600; cursor: pointer; transition: all 0.2s; }
            .btn-primary { background: #3b82f6; color: white; }
            .btn-primary:hover { background: #2563eb; }
            .btn-success { background: #10b981; color: white; }
            .btn-success:hover { background: #059669; }
            .header-flex { display: flex; justify-content: space-between; align-items: center; }
            .toast { position: fixed; top: 30px; left: 50%; transform: translateX(-50%); padding: 14px 28px; background: #0f172a; color: white; border-radius: 8px; display: none; z-index: 99999; box-shadow: 0 10px 25px rgba(0,0,0,0.35); font-weight: 500; font-size: 14px; border: 1px solid #334155; }
            .help-text { font-size: 13px; color: #64748b; margin-top: 5px; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header-flex">
                <h1>🚀 Prober API 控制台</h1>
                <div style="display: flex; gap: 10px;">
                    <button class="btn btn-secondary" onclick="updateMMDB()">🌐 更新GeoLite2库</button>
                    <button class="btn btn-primary" onclick="triggerUpdateRaw()">📥 立即更新基础池</button>
                    <button class="btn btn-success" onclick="triggerUpdateTested()">⚡ 立即测速洗池</button>
                </div>
            </div>
            
            <div class="form-group">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                    <label style="margin: 0;">订阅源列表 (一行一个)</label>
                    <a href="/custom_sub" class="btn btn-success" style="padding: 5px 10px; font-size: 13px;" target="_blank">🛠️ 自建订阅源</a>
                </div>
                <textarea id="subscriptions"></textarea>
            </div>
            
            <div class="form-group" style="display: flex; gap: 20px;">
                <div style="flex: 1;">
                    <label>基础 GeoIP 池定时更新规则 (Cron 表达式)</label>
                    <input type="text" id="cron_raw" placeholder="0 0 * * 0">
                    <div class="help-text">
                        默认: <code>0 0 * * 0</code> (每周日凌晨 0 点)<br>
                        用途: 定期从订阅源抓取最新原始节点。
                    </div>
                </div>
                <div style="flex: 1;">
                    <label>优选池定时测速规则 (Cron 表达式)</label>
                    <input type="text" id="cron_tested" placeholder="*/30 * * * *">
                    <div class="help-text">
                        默认: <code>*/30 * * * *</code> (每 30 分钟一次)<br>
                        用途: 对基础池进行实时延迟检测并过滤。
                    </div>
                </div>
            </div>
            
            <button id="saveConfigBtn" class="btn btn-primary" onclick="saveConfig()">💾 保存配置</button>

            <!-- CFBox 实时同步模块 (方案一) -->
            <div class="form-group" style="margin-top: 25px; border: 1px solid #cbd5e1; border-radius: 8px; padding: 20px; background: #f8fafc;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                    <h3 style="margin: 0; color: #0f172a; font-size: 1.1rem; display: flex; align-items: center; gap: 8px;">
                        <span>☁️</span> CFBox 节点管理联动 (方案一：实时推送)
                    </h3>
                    <label style="display: flex; align-items: center; gap: 8px; cursor: pointer; margin: 0; font-size: 14px; font-weight: 600; color: #1e293b;">
                        <input type="checkbox" id="cfbox_enabled" style="width: auto; cursor: pointer;">
                        启用测速后自动实时同步
                    </label>
                </div>
                <div class="help-text" style="margin-bottom: 15px; line-height: 1.5;">
                    每次测速洗池完成后，自动将优质节点直接推送到部署在 Cloudflare Pages 的 CFBox 节点管理中（通过原生 <code>/{UUID}/api/config</code> 接口更新 KV 并即时生效）。
                </div>
                <div style="display: flex; gap: 15px; margin-bottom: 15px;">
                    <div style="flex: 1.5;">
                        <label style="font-size: 13px;">CFBox Pages 域名</label>
                        <input type="text" id="cfbox_url" placeholder="https://your-cfbox.pages.dev">
                    </div>
                    <div style="flex: 1.5;">
                        <label style="font-size: 13px;">管理 UUID</label>
                        <input type="text" id="cfbox_uuid" placeholder="如 07d2aca9-c060-4039-b265-454fc8510d4c">
                    </div>
                </div>
                <div style="display: flex; gap: 15px; margin-bottom: 15px;">
                    <div style="flex: 2;">
                        <label style="font-size: 13px;">自定义访问路径 (可选，未设置留空)</label>
                        <input type="text" id="cfbox_custom_path" placeholder="若设置了自定义路径 d 则填写，默认留空">
                    </div>
                    <div style="flex: 1;">
                        <label style="font-size: 13px;">最大推送节点数</label>
                        <input type="number" id="cfbox_max_nodes" value="600000" style="width: 100%; padding: 10px; border: 1px solid #cbd5e1; border-radius: 6px; box-sizing: border-box;">
                    </div>
                </div>

                <!-- ── 国家节点配额规则 ── -->
                <div style="border: 1px dashed #94a3b8; border-radius: 8px; padding: 15px; margin-bottom: 15px; background: #f0f6ff;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                        <label style="font-size: 13px; font-weight: 600; color: #1e40af;">🌍 国家节点配额规则</label>
                        <button class="btn btn-secondary" style="padding: 4px 10px; font-size: 12px;" onclick="addCountryRule()">＋ 添加特殊国家</button>
                    </div>
                    <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 10px;">
                        <label style="font-size: 13px; white-space: nowrap; min-width: 130px;">每国默认上限</label>
                        <input type="number" id="cfbox_default_per_country" value="0" min="0" style="width: 100px; padding: 6px 8px; border: 1px solid #cbd5e1; border-radius: 6px; font-size: 13px;">
                        <span style="font-size: 12px; color: #64748b;">0 = 不限；填正整数 = 每国最多取该数量个（按延迟由低到高优先）</span>
                    </div>
                    <div style="font-size: 12px; color: #64748b; margin-bottom: 8px;">
                        特殊国家覆盖规则（优先级高于默认上限）：<code>-1</code> = 完全排除该国；<code>0</code> = 该国不限；正整数 = 该国专属上限。
                    </div>
                    <table style="width: 100%; border-collapse: collapse; font-size: 13px;" id="countryRulesTable">
                        <thead>
                            <tr style="background: #dbeafe;">
                                <th style="padding: 6px 10px; text-align: left; border-radius: 4px 0 0 4px;">国家代码 (如 HK / US)</th>
                                <th style="padding: 6px 10px; text-align: left;">最多节点数（-1=排除，0=不限）</th>
                                <th style="padding: 6px 10px; text-align: center; border-radius: 0 4px 4px 0;">操作</th>
                            </tr>
                        </thead>
                        <tbody id="countryRulesBody">
                            <!-- 动态行由 JS 填充 -->
                        </tbody>
                    </table>
                </div>

                <div style="display: flex; gap: 10px; align-items: center; flex-wrap: wrap;">
                    <button id="saveCFBoxBtn" class="btn btn-primary" onclick="saveCFBoxConfig()">💾 保存 CFBox 设置</button>
                    <button class="btn btn-success" onclick="triggerCFBoxSync()">⚡ 立即推送到 CFBox</button>
                    <button class="btn btn-secondary" onclick="openDeployModal()">🚀 自动化部署 CFBox 到 Pages</button>
                    <span id="cfboxStatus" style="font-size: 13px; color: #64748b; margin-left: 5px;"></span>
                </div>
            </div>


            <div class="form-group" style="margin-top: 40px; border-top: 2px solid #e2e8f0; padding-top: 20px;">
                <div class="header-flex" style="border-bottom: none; padding-bottom: 0;">
                    <h2 style="margin: 0; color: #0f172a; font-size: 1.25rem;">📝 节点池双层过滤状态 (预览)</h2>
                    <button class="btn btn-primary" style="background: #64748b;" onclick="loadPool()">🔄 刷新预览</button>
                </div>
                
                <div style="display: flex; gap: 20px;">
                    <!-- Raw Pool -->
                    <div style="flex: 1; border: 1px solid #e2e8f0; border-radius: 8px; padding: 15px; background: #fff;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 5px;">
                            <h3 style="margin: 0; color: #3b82f6; font-size: 1rem;">1. 基础 GeoIP 池 (cached_pool)</h3>
                            <span id="totalCountRaw" style="font-size: 0.85rem; color: #3b82f6; font-weight: bold;"></span>
                        </div>
                        <div class="help-text" style="margin-bottom: 10px;">未经测速的所有原始节点 (不推荐直连)</div>
                        <div style="display: flex; gap: 10px; margin-bottom: 15px;">
                            <select id="countrySelectRaw" style="flex: 1; padding: 8px; border-radius: 6px; border: 1px solid #cbd5e1;" onchange="changeCountry('raw')"></select>
                        </div>
                        <textarea id="ipListRaw" style="height: 250px; background: #f8fafc; font-size: 13px;" readonly placeholder="Loading..."></textarea>
                        <div id="pageInfoRaw" style="font-size: 13px; color: #64748b; margin-top: 10px;"></div>
                    </div>
                    
                    <!-- Tested Pool -->
                    <div style="flex: 1; border: 1px solid #e2e8f0; border-radius: 8px; padding: 15px; background: #fff;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 5px;">
                            <h3 style="margin: 0; color: #10b981; font-size: 1rem;">2. 已测优选池 (tested_pool)</h3>
                            <span id="totalCountTested" style="font-size: 0.85rem; color: #10b981; font-weight: bold;"></span>
                        </div>
                        <div class="help-text" style="margin-bottom: 10px;">延迟 < 1500ms 的极品节点 (CF接口首选)</div>
                        <div style="display: flex; gap: 10px; margin-bottom: 15px;">
                            <select id="countrySelectTested" style="flex: 1; padding: 8px; border-radius: 6px; border: 1px solid #cbd5e1;" onchange="changeCountry('tested')"></select>
                        </div>
                        <textarea id="ipListTested" style="height: 250px; background: #f8fafc; font-size: 13px;" readonly placeholder="Loading..."></textarea>
                        <div id="pageInfoTested" style="font-size: 13px; color: #64748b; margin-top: 10px;"></div>
                    </div>
                </div>
            </div>
        </div>
        <div id="toast" class="toast"></div>

        <script>
            const state = {
                raw: { poolData: {}, currentCountry: "", currentPage: 1 },
                tested: { poolData: {}, currentCountry: "", currentPage: 1 }
            };
            const pageSize = 20;

            function showToast(msg) {
                const toast = document.getElementById('toast');
                toast.innerText = msg;
                toast.style.display = 'block';
                setTimeout(() => toast.style.display = 'none', 3000);
            }
            
            async function loadConfig() {
                const res = await fetch(`/api/config?t=${new Date().getTime()}`);
                const data = await res.json();
                document.getElementById('subscriptions').value = data.subscriptions.join('\\n');
                document.getElementById('cron_raw').value = data.cron_raw;
                document.getElementById('cron_tested').value = data.cron_tested;
            }
            
            async function saveConfig() {
                const btn = document.getElementById('saveConfigBtn');
                if (btn) { btn.disabled = true; btn.innerText = '⏳ 保存中...'; }
                try {
                    const subs = document.getElementById('subscriptions').value.split('\\n').map(s => s.trim()).filter(s => s);
                    const cron_raw = document.getElementById('cron_raw').value.trim();
                    const cron_tested = document.getElementById('cron_tested').value.trim();
                    
                    const res = await fetch('/api/config', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({subscriptions: subs, cron_raw: cron_raw, cron_tested: cron_tested})
                    });
                    
                    if (res.ok) {
                        showToast('✅ 基础配置保存成功，定时任务已重载！');
                    } else {
                        const err = await res.text();
                        alert('保存失败: ' + err);
                    }
                } catch (e) {
                    alert('网络或请求异常: ' + e);
                } finally {
                    if (btn) { btn.disabled = false; btn.innerText = '💾 保存配置'; }
                }
            }
            
            async function triggerUpdateRaw() {
                const res = await fetch('/api/trigger_update_raw', { method: 'POST' });
                if (res.ok) {
                    showToast('已触发基础池更新！可刷新预览查看。');
                }
            }
            
            async function updateMMDB() {
                const res = await fetch('/api/update_mmdb', { method: 'POST' });
                if (res.ok) {
                    showToast('已在后台开始下载更新 GeoLite2 库！这可能需要一两分钟。');
                }
            }

            async function triggerUpdateTested() {
                const res = await fetch('/api/trigger_update_tested', { method: 'POST' });
                const data = await res.json();
                if (data.status === 'busy') {
                    showToast('测速正在进行中，请耐心等待...');
                    return;
                }
                showToast('已触发优选池测速！后台大约需要几分钟，完成后将自动刷新面板。');
                
                // Poll status every 5 seconds
                const interval = setInterval(async () => {
                    try {
                        const statusRes = await fetch('/api/status?t=' + new Date().getTime());
                        const statusData = await statusRes.json();
                        if (!statusData.is_testing) {
                            clearInterval(interval);
                            showToast('测速完成！正在刷新面板数据...');
                            await fetchPool('tested');
                        }
                    } catch (e) {
                        console.error(e);
                    }
                }, 5000);
            }
            
            async function fetchPool(type) {
                try {
                    const res = await fetch(`/api/pool/${type}?t=${new Date().getTime()}`);
                    const data = await res.json();
                    if (data.status === 'ok') {
                        state[type].poolData = data.data;
                        const select = document.getElementById(`countrySelect${type === 'raw' ? 'Raw' : 'Tested'}`);
                        select.innerHTML = '';
                        let totalCount = 0;
                        
                        const sortedCountries = Object.keys(state[type].poolData).sort();
                        for (const country of sortedCountries) {
                            const count = state[type].poolData[country].length;
                            totalCount += count;
                            const option = document.createElement('option');
                            option.value = country;
                            option.text = `${country} (${count} 个节点)`;
                            select.appendChild(option);
                        }
                        
                        document.getElementById(`totalCount${type === 'raw' ? 'Raw' : 'Tested'}`).innerText = `总计: ${totalCount} IP`;
                        
                        if (sortedCountries.length > 0) {
                            state[type].currentCountry = sortedCountries[0];
                            state[type].currentPage = 1;
                            renderPool(type);
                        } else {
                            document.getElementById(`ipList${type === 'raw' ? 'Raw' : 'Tested'}`).innerHTML = "池子为空";
                        }
                        return totalCount;
                    } else {
                        document.getElementById(`ipList${type === 'raw' ? 'Raw' : 'Tested'}`).innerHTML = '获取失败: ' + data.message;
                        return 0;
                    }
                } catch (e) {
                    document.getElementById(`ipList${type === 'raw' ? 'Raw' : 'Tested'}`).innerHTML = '加载错误';
                    return 0;
                }
            }
            
            async function loadPool() {
                document.getElementById('ipListRaw').innerHTML = 'Loading...';
                document.getElementById('ipListTested').innerHTML = 'Loading...';
                
                fetchPool('raw').then(rawCount => {
                    if (rawCount > 0) {
                        showToast(`基础池加载完成: ${rawCount} 个`);
                    }
                });
                
                fetchPool('tested').then(testedCount => {
                    if (testedCount > 0) {
                        showToast(`优选池加载完成: ${testedCount} 个`);
                    }
                });
            }
            
            function changeCountry(type) {
                state[type].currentCountry = document.getElementById(`countrySelect${type === 'raw' ? 'Raw' : 'Tested'}`).value;
                state[type].currentPage = 1;
                renderPool(type);
            }
            
            function renderPool(type) {
                const ips = state[type].poolData[state[type].currentCountry] || [];
                const textarea = document.getElementById(`ipList${type === 'raw' ? 'Raw' : 'Tested'}`);
                
                if (ips.length === 0) {
                    textarea.value = "无数据";
                } else {
                    textarea.value = ips.join('\\n');
                }
                
                document.getElementById(`pageInfo${type === 'raw' ? 'Raw' : 'Tested'}`).innerText = `共 ${ips.length} 条节点 (可直接复制)`;
            }

            // --- CFBox Functions ---
            async function loadCFBoxConfig() {
                try {
                    const res = await fetch(`/api/cfbox/config?t=${new Date().getTime()}`);
                    const data = await res.json();
                    document.getElementById('cfbox_enabled').checked = !!data.enabled;
                    document.getElementById('cfbox_url').value = data.url || '';
                    document.getElementById('cfbox_uuid').value = data.uuid || '';
                    document.getElementById('cfbox_custom_path').value = data.custom_path || '';
                    document.getElementById('cfbox_max_nodes').value = data.max_nodes || 600000;
                    document.getElementById('cfbox_default_per_country').value = data.default_per_country || 0;
                    renderCountryRules(data.country_rules || {});
                } catch (e) {
                    console.error("加载 CFBox 配置失败:", e);
                }
            }

            // 渲染国家规则表格
            function renderCountryRules(rules) {
                const tbody = document.getElementById('countryRulesBody');
                tbody.innerHTML = '';
                Object.entries(rules).forEach(([cc, limit]) => {
                    addCountryRuleRow(cc.toUpperCase(), limit);
                });
            }

            // 向表格中插入一行国家规则
            function addCountryRuleRow(cc, limit) {
                const tbody = document.getElementById('countryRulesBody');
                const tr = document.createElement('tr');
                tr.style.borderBottom = '1px solid #e2e8f0';
                tr.innerHTML = `
                    <td style="padding: 5px 8px;">
                        <input type="text" maxlength="3" placeholder="HK"
                            style="width:70px; padding:4px 6px; border:1px solid #cbd5e1; border-radius:4px; font-size:13px; text-transform:uppercase;"
                            value="${cc || ''}" class="cr-code">
                    </td>
                    <td style="padding: 5px 8px;">
                        <input type="number" min="-1" placeholder="5"
                            style="width:90px; padding:4px 6px; border:1px solid #cbd5e1; border-radius:4px; font-size:13px;"
                            value="${limit !== undefined ? limit : 5}" class="cr-limit">
                    </td>
                    <td style="padding: 5px 8px; text-align:center;">
                        <button class="btn btn-secondary"
                            style="padding:2px 8px; font-size:12px; background:#fee2e2; color:#dc2626; border:none;"
                            onclick="this.closest('tr').remove()">✕ 删除</button>
                    </td>`;
                tbody.appendChild(tr);
            }

            // 点击"添加特殊国家"按钮
            function addCountryRule() {
                addCountryRuleRow('', 5);
            }

            // 从表格中收集 country_rules 对象
            function collectCountryRules() {
                const rows = document.querySelectorAll('#countryRulesBody tr');
                const rules = {};
                rows.forEach(tr => {
                    const cc = tr.querySelector('.cr-code')?.value?.trim().toUpperCase();
                    const limit = parseInt(tr.querySelector('.cr-limit')?.value);
                    if (cc && !isNaN(limit)) {
                        rules[cc] = limit;
                    }
                });
                return rules;
            }

            async function saveCFBoxConfig() {
                const btn = document.getElementById('saveCFBoxBtn');
                if (btn) { btn.disabled = true; btn.innerText = '⏳ 保存中...'; }
                try {
                    const payload = {
                        enabled: document.getElementById('cfbox_enabled').checked,
                        url: document.getElementById('cfbox_url').value.trim(),
                        uuid: document.getElementById('cfbox_uuid').value.trim(),
                        custom_path: document.getElementById('cfbox_custom_path').value.trim(),
                        max_nodes: parseInt(document.getElementById('cfbox_max_nodes').value) || 600000,
                        default_per_country: parseInt(document.getElementById('cfbox_default_per_country').value) || 0,
                        country_rules: collectCountryRules()
                    };
                    const res = await fetch('/api/cfbox/config', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify(payload)
                    });
                    if (res.ok) {
                        showToast('✅ CFBox 联动配置已保存至文件！');
                    } else {
                        const err = await res.text();
                        alert('保存 CFBox 配置失败: ' + err);
                    }
                } catch (e) {
                    alert('保存 CFBox 配置异常: ' + e);
                } finally {
                    if (btn) { btn.disabled = false; btn.innerText = '💾 保存 CFBox 设置'; }
                }
            }


            async function triggerCFBoxSync() {
                const statusSpan = document.getElementById('cfboxStatus');
                statusSpan.innerText = '正在向 CFBox 推送节点...';
                try {
                    const res = await fetch('/api/cfbox/sync', { method: 'POST' });
                    const data = await res.json();
                    if (data.status === 'ok') {
                        statusSpan.innerText = '✅ 同步成功！';
                        showToast(data.message);
                    } else {
                        statusSpan.innerText = '❌ 同步失败';
                        showToast('同步失败: ' + data.message);
                    }
                } catch (e) {
                    statusSpan.innerText = '❌ 请求异常';
                    showToast('请求异常: ' + e);
                }
            }

            function openDeployModal() {
                document.getElementById('deployModal').style.display = 'block';
            }

            function closeDeployModal() {
                document.getElementById('deployModal').style.display = 'none';
            }

            async function submitDeployCFBox() {
                const account_id = document.getElementById('deploy_account_id').value.trim();
                const api_token = document.getElementById('deploy_api_token').value.trim();
                const project_name = document.getElementById('deploy_project_name').value.trim() || 'cfbox';
                const uuid = document.getElementById('deploy_uuid').value.trim();
                const custom_path = document.getElementById('deploy_custom_path').value.trim();

                if (!account_id || !api_token) {
                    alert('请填写 Account ID 和 API Token！');
                    return;
                }

                document.getElementById('deployBtn').disabled = true;
                document.getElementById('deployBtn').innerText = '正在提交部署...';

                try {
                    const res = await fetch('/api/cfbox/deploy', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({
                            account_id: account_id,
                            api_token: api_token,
                            project_name: project_name,
                            uuid: uuid,
                            custom_path: custom_path
                        })
                    });
                    const data = await res.json();
                    if (res.ok) {
                        alert('🚀 部署任务已在后台启动！脚本正在执行：创建 KV -> 绑定环境变量 -> Wrangler 发布 Pages。大约需要 1~2 分钟，部署完成后刷新本页面即可。');
                        closeDeployModal();
                    } else {
                        alert('触发部署失败: ' + JSON.stringify(data));
                    }
                } catch (e) {
                    alert('请求失败: ' + e);
                } finally {
                    document.getElementById('deployBtn').disabled = false;
                    document.getElementById('deployBtn').innerText = '🚀 开始全自动部署';
                }
            }
            
            window.addEventListener('DOMContentLoaded', async () => {
                await loadConfig();
                await loadCFBoxConfig();
                await loadPool();
            });
        </script>

        <!-- Deploy Modal -->
        <div id="deployModal" style="display: none; position: fixed; z-index: 1000; left: 0; top: 0; width: 100%; height: 100%; overflow: auto; background-color: rgba(0,0,0,0.5);">
            <div style="background-color: #fff; margin: 8% auto; padding: 25px; border-radius: 10px; width: 90%; max-width: 550px; box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.2);">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; border-bottom: 1px solid #e2e8f0; padding-bottom: 10px;">
                    <h2 style="margin: 0; font-size: 1.25rem; color: #0f172a;">🚀 一键部署 CFBox 到 Cloudflare Pages</h2>
                    <span style="font-size: 24px; cursor: pointer; color: #94a3b8;" onclick="closeDeployModal()">&times;</span>
                </div>
                <div class="help-text" style="margin-bottom: 15px;">
                    脚本将自动将 <code>CFBox混淆版.js</code> 复制为 <code>_worker.js</code>，并在 Cloudflare 创建并绑定 KV 命名空间 <code>CFBOX_KV</code>、设置 UUID 并发布至 Pages。
                </div>
                <div class="form-group" style="margin-bottom: 12px;">
                    <label style="font-size: 13px;">Cloudflare Account ID (必需)</label>
                    <input type="text" id="deploy_account_id" placeholder="32位十六进制字符串，可在 CF 面板右下角找到">
                </div>
                <div class="form-group" style="margin-bottom: 12px;">
                    <label style="font-size: 13px;">Cloudflare API Token (必需，需包含 Pages:Edit 与 KV:Edit 权限)</label>
                    <input type="password" id="deploy_api_token" placeholder="CF API Token">
                </div>
                <div class="form-group" style="margin-bottom: 12px;">
                    <label style="font-size: 13px;">Pages 项目名称</label>
                    <input type="text" id="deploy_project_name" value="cfbox" placeholder="cfbox">
                </div>
                <div class="form-group" style="margin-bottom: 12px;">
                    <label style="font-size: 13px;">管理 UUID (留空则自动生成)</label>
                    <input type="text" id="deploy_uuid" placeholder="留空自动生成标准 UUIDv4">
                </div>
                <div class="form-group" style="margin-bottom: 20px;">
                    <label style="font-size: 13px;">自定义访问路径 d (可选，留空使用 UUID)</label>
                    <input type="text" id="deploy_custom_path" placeholder="例如 myvipsub">
                </div>
                <div style="display: flex; justify-content: flex-end; gap: 10px;">
                    <button class="btn btn-secondary" onclick="closeDeployModal()">取消</button>
                    <button class="btn btn-primary" id="deployBtn" onclick="submitDeployCFBox()">🚀 开始全自动部署</button>
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    return html_content

@app.get("/api/config")
async def api_get_config():
    return load_config()

@app.post("/api/config")
async def api_set_config(config: ConfigModel):
    save_config(config.dict(exclude_unset=True))
    update_scheduler()
    return {"status": "ok"}

class GithubTokenModel(BaseModel):
    github_token: str

@app.get("/api/config/github")
async def api_get_github_config():
    cfg = load_config()
    return {"github_token": cfg.get("github_token", "")}

@app.post("/api/config/github")
async def api_set_github_config(req: GithubTokenModel):
    save_config({"github_token": req.github_token})
    return {"status": "ok"}

# --- CFBox Sync & Deploy APIs ---
@app.get("/api/cfbox/config")
async def api_get_cfbox_config():
    cfg = load_config()
    return cfg.get("cfbox_sync", {
        "enabled": False,
        "url": "",
        "uuid": "",
        "custom_path": "",
        "max_nodes": 600000,
        "default_per_country": 0,
        "country_rules": {}
    })

@app.post("/api/cfbox/config")
async def api_set_cfbox_config(req: CFBoxSyncModel):
    save_config({"cfbox_sync": req.dict()})
    return {"status": "ok", "config": req.dict()}

@app.post("/api/cfbox/sync")
async def api_trigger_cfbox_sync():
    try:
        from sync_cfbox import sync_to_cfbox
        success, msg = sync_to_cfbox()
        return {"status": "ok" if success else "error", "message": msg}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/cfbox/deploy")
async def api_trigger_cfbox_deploy(req: DeployCFBoxModel, background_tasks: BackgroundTasks):
    cmd = [
        sys.executable, "-u", "deploy_cfbox.py",
        "--account-id", req.account_id,
        "--api-token", req.api_token,
        "--project-name", req.project_name
    ]
    if req.uuid:
        cmd.extend(["--uuid", req.uuid])
    if req.custom_path:
        cmd.extend(["--custom-path", req.custom_path])
        
    def run_deploy():
        subprocess.run(cmd)
        
    background_tasks.add_task(run_deploy)
    return {"status": "started", "message": "部署任务已在后台启动，请查看后台终端日志或等待几分钟后刷新页面。"}

# --- State for Polling ---
is_testing = False

def run_test_pool_sync():
    global is_testing
    is_testing = True
    try:
        # Run test_pool.py synchronously in background thread
        subprocess.run([sys.executable, "-u", "test_pool.py"])
    finally:
        is_testing = False

@app.post("/api/trigger_update_raw")
async def api_trigger_update_raw():
    subprocess.Popen([sys.executable, "-u", UPDATE_SCRIPT])
    return {"status": "ok"}

@app.post("/api/trigger_update_tested")
async def api_trigger_update_tested(background_tasks: BackgroundTasks):
    global is_testing
    if is_testing:
        return {"status": "busy"}
    background_tasks.add_task(run_test_pool_sync)
    return {"status": "ok"}

@app.post("/api/update_mmdb")
async def api_update_mmdb():
    subprocess.Popen([sys.executable, "-u", "update_mmdb.py"])
    return {"status": "ok"}

@app.get("/api/status")
async def api_status():
    global is_testing
    return {"is_testing": is_testing}

@app.get("/api/pool/{pool_type}")
async def api_get_pool(pool_type: str):
    path = "tested_pool.txt" if pool_type == "tested" else CACHE_PATH
    if not os.path.isfile(path):
        return {"status": "error", "message": "节点池暂未生成，请触发更新或等待后台测试完毕"}
    try:
        data = {}
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or "#" not in line: continue
                _, remark = line.split("#", 1)
                
                # Extract Country (e.g. "US 美国")
                country_key = remark.strip("[]")
                if country_key.endswith("ms"):
                    # Strip the latency part if it exists (e.g. "US 美国 123.45ms" -> "US 美国")
                    if " " in country_key:
                        country_key = country_key.rsplit(" ", 1)[0]
                
                if country_key not in data:
                    data[country_key] = []
                data[country_key].append(line) # append the full line exactly as the user wants
        return {"status": "ok", "data": data}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# --- Speedtest Core ---
import socket

async def check_tcp_latency(ip_str: str, default_port: int, timeout_sec: float) -> dict:
    ip = ip_str.strip()
    port = default_port
    if ":" in ip:
        if ip.startswith("[") and "]:" in ip:
            parts = ip.split("]:")
            ip = parts[0][1:]
            port = int(parts[1])
        elif ip.count(":") == 1:
            parts = ip.split(":")
            ip = parts[0]
            port = int(parts[1])
            
    start_time = time.time()
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(ip, port),
            timeout=timeout_sec
        )
        writer.close()
        await writer.wait_closed()
        latency = (time.time() - start_time) * 1000
        return {"ip": ip_str, "latency": latency, "status": "ok"}
    except Exception as e:
        return {"ip": ip_str, "latency": -1, "error": str(e), "status": "error"}

import random

@app.post("/api/speedtest", response_model=SpeedtestResponse)
async def speedtest(req: SpeedtestRequest):
    reload_ip_pool()
    
    country_results = {}
    timeout_sec = req.timeout_ms / 1000.0
    
    for country in req.countries:
        country_code = country.upper()
        pool = IP_POOL.get(country_code, [])
        if not pool:
            continue
            
        candidates = pool[:20] + random.sample(pool[20:], min(30, len(pool)-20)) if len(pool) > 20 else pool
        tasks = [check_tcp_latency(ip, req.port, timeout_sec) for ip in candidates]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        valid_results = [r for r in results if isinstance(r, dict) and r.get("status") == "ok"]
        if valid_results:
            valid_results.sort(key=lambda x: x["latency"])
            best_nodes = valid_results[:req.limit]
            country_results[country_code] = {
                "best_ip": best_nodes[0]["ip"],
                "latency": best_nodes[0]["latency"],
                "status": "ok",
                "ips": [{"ip": n["ip"], "latency": n["latency"]} for n in best_nodes]
            }
            
    return SpeedtestResponse(country_results=country_results)

@app.get("/custom_sub", response_class=HTMLResponse)
async def custom_sub_page():
    if os.path.exists("custom_sub.html"):
        with open("custom_sub.html", "r", encoding="utf-8") as f:
            return f.read()
    return "custom_sub.html not found"

@app.get("/api/custom_sub/zones")
async def api_custom_sub_zones():
    zones = []
    if os.path.exists("countries"):
        for f in os.listdir("countries"):
            if f.endswith(".zone"):
                zones.append(f.replace(".zone", ""))
    return {"zones": sorted(zones)}

@app.get("/api/custom_sub/zone/{country}")
async def api_custom_sub_zone(country: str):
    cidrs = []
    if country == "ALL":
        if os.path.exists("countries"):
            for f in os.listdir("countries"):
                if f.endswith(".zone"):
                    with open(os.path.join("countries", f), "r") as zf:
                        cidrs.extend(zf.read().splitlines())
    else:
        path = f"countries/{country.lower()}.zone"
        if os.path.exists(path):
            with open(path, "r") as zf:
                cidrs = zf.read().splitlines()
    return {"cidrs": cidrs}

@app.get("/api/custom_sub/jobs")
async def api_get_custom_jobs():
    return load_custom_jobs()

@app.post("/api/custom_sub/jobs")
async def api_create_custom_job(req: CustomJobCreate):
    jobs = load_custom_jobs()
    job_id = f"{req.country.upper()}.JOB"
    
    jobs[job_id] = {
        "job_id": job_id,
        "country": req.country,
        "country_name": req.country_name,
        "cidrs": req.cidrs,
        "ports": req.ports,
        "cron": req.cron,
        "enabled": True,
        "status": "idle",
        "run_count": 0,
        "fail_count": 0,
        "gist_url": ""
    }
    save_custom_jobs(jobs)
    update_scheduler()
    return {"status": "ok", "job_id": job_id}

@app.put("/api/custom_sub/jobs/{job_id}")
async def api_update_custom_job(job_id: str, req: CustomJobUpdate):
    jobs = load_custom_jobs()
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
        
    jobs[job_id]["cron"] = req.cron
    jobs[job_id]["enabled"] = req.enabled
    save_custom_jobs(jobs)
    update_scheduler()
    return {"status": "ok"}

@app.delete("/api/custom_sub/jobs/{job_id}")
async def api_delete_custom_job(job_id: str):
    jobs = load_custom_jobs()
    if job_id in jobs:
        del jobs[job_id]
        save_custom_jobs(jobs)
        update_scheduler()
    return {"status": "ok"}

@app.post("/api/custom_sub/jobs/{job_id}/execute")
async def api_execute_custom_job(job_id: str):
    jobs = load_custom_jobs()
    if job_id not in jobs:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Job not found")
    run_custom_job(job_id)
    return {"status": "started"}

@app.get("/api/custom_sub/jobs/{job_id}/download")
async def api_download_custom_job(job_id: str):
    from fastapi.responses import FileResponse
    path = f"job_results_{job_id}.txt"
    if not os.path.exists(path):
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Result file not found")
    return FileResponse(path, media_type="text/plain", filename=f"best_cf_{job_id}_ips.txt")

class ScanRequest(BaseModel):
    cidrs: List[str]
    ports: List[int]
    country: str
    country_name: str = ""

@app.post("/api/custom_sub/scan")
async def api_custom_sub_scan(req: ScanRequest):
    # Check if currently running
    if os.path.exists("scan_progress.json"):
        with open("scan_progress.json", "r") as f:
            try:
                prog = json.load(f)
                if prog.get("is_running"):
                    return {"status": "busy"}
            except Exception:
                pass
                
    with open("temp_scan_req.json", "w") as f:
        json.dump({"cidrs": req.cidrs}, f)
        
    ports_str = ",".join(map(str, req.ports))
    subprocess.Popen([sys.executable, "-u", "scanner.py", req.country, ports_str, req.country_name])
    return {"status": "started"}

@app.get("/api/custom_sub/progress")
async def api_custom_sub_progress():
    progress = {"scanned": 0, "total": 0, "is_running": False, "results": []}
    if os.path.exists("scan_progress.json"):
        with open("scan_progress.json", "r") as f:
            try:
                progress.update(json.load(f))
            except Exception:
                pass
                
    if os.path.exists("local_custom_pool.txt"):
        with open("local_custom_pool.txt", "r") as f:
            progress["results"] = f.read().splitlines()
            
    return progress

class CronRequest(BaseModel):
    country: str
    cron: str

@app.post("/api/custom_sub/cron")
async def api_custom_sub_cron(req: CronRequest):
    # This is a placeholder for actual cron persistence of custom_sub.
    # In a full app, this would be saved to config and loaded in scheduler.
    return {"status": "ok"}

@app.get("/api/local_sub")
async def api_local_sub():
    if os.path.exists("local_custom_pool.txt"):
        with open("local_custom_pool.txt", "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read(), media_type="text/plain")
    return HTMLResponse(content="", media_type="text/plain")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
