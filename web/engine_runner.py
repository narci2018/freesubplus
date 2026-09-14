import os
import sys
import time
import queue
import threading
import traceback
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "scripts"))

from web.config_mgr import config_mgr
from web.cf_optimizer import cf_optimizer


class LogBuffer:
    def __init__(self, max_lines=2000):
        self.max_lines = max_lines
        self.lines = []
        self.lock = threading.Lock()
        self._subscribers = []

    def write(self, msg: str):
        text = str(msg).strip()
        if not text:
            return
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted = f"[{timestamp}] {text}"
        with self.lock:
            self.lines.append(formatted)
            if len(self.lines) > self.max_lines:
                self.lines.pop(0)
            # 通知 SSE 订阅者
            for q in list(self._subscribers):
                try:
                    q.put_nowait(formatted)
                except Exception:
                    pass

    def get_recent(self, count=100):
        with self.lock:
            return list(self.lines[-count:])

    def subscribe(self) -> queue.Queue:
        q = queue.Queue(maxsize=100)
        with self.lock:
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q: queue.Queue):
        with self.lock:
            if q in self._subscribers:
                self._subscribers.remove(q)


log_buffer = LogBuffer()


class StdOutRedirector:
    def __init__(self, original_stdout, log_buf):
        self.original_stdout = original_stdout
        self.log_buf = log_buf
        self._line_buf = ""

    def write(self, data):
        try:
            self.original_stdout.write(data)
            self.original_stdout.flush()
        except Exception:
            pass
        self._line_buf += data
        while "\n" in self._line_buf:
            line, self._line_buf = self._line_buf.split("\n", 1)
            line = line.strip()
            if line:
                self.log_buf.write(line)

    def flush(self):
        try:
            self.original_stdout.flush()
        except Exception:
            pass
        if self._line_buf.strip():
            self.log_buf.write(self._line_buf.strip())
            self._line_buf = ""


def check_and_normalize_proxy(proxy_url: str):
    """
    检查前置代理连通性，自动兼容 Docker 容器网络 (127.0.0.1 -> host.docker.internal)，
    返回 (is_alive, usable_url, message)
    """
    if not proxy_url or not proxy_url.strip():
        return False, "", "未配置前置代理"

    import socket, re
    p_str = proxy_url.strip()
    m = re.match(r"^(socks5h?|socks4a?|http|https)://([^:/]+):(\d+)", p_str)
    if not m:
        return False, p_str, "代理 URL 格式无效"

    scheme, host, port_str = m.groups()
    port = int(port_str)

    candidates = [host]
    is_docker = os.path.exists("/.dockerenv") or os.environ.get("DATA_DIR") == "/app/data"
    if is_docker and host in ("127.0.0.1", "localhost"):
        # 容器内 127.0.0.1 无法访问宿主机，优先转换为宿主机网关
        candidates = ["host.docker.internal", "172.17.0.1", host]

    for chost in candidates:
        try:
            with socket.create_connection((chost, port), timeout=1.5):
                real_url = p_str.replace(f"//{host}:", f"//{chost}:")
                return True, real_url, f"连通成功 ({chost}:{port})"
        except Exception:
            continue

    return False, p_str, f"无法连接到代理服务 ({host}:{port})，连接超时或被拒绝"


class EngineRunner:
    def __init__(self):
        self.is_running = False
        self.current_stage = "idle"
        self.last_run_time = None
        self.progress = {"current": 0, "total": 0, "percentage": 0}
        self._lock = threading.Lock()

    def get_status(self) -> dict:
        cfg = config_mgr.get_config()
        sched = cfg.get("scheduler", {})
        return {
            "is_running": self.is_running,
            "current_stage": self.current_stage,
            "progress": self.progress,
            "last_run": sched.get("last_run"),
            "last_status": sched.get("last_status", "就绪"),
            "last_duration_s": sched.get("last_duration_s", 0),
            "last_node_count": sched.get("last_node_count", 0),
            "last_residential_count": sched.get("last_residential_count", 0),
        }

    def run_pipeline_async(self):
        with self._lock:
            if self.is_running:
                return False, "测活任务已在后台运行中"
            self.is_running = True
            self.current_stage = "starting"

        threading.Thread(target=self._execute, daemon=True).start()
        return True, "测活流水线已启动"

    def _execute(self):
        t0 = time.time()
        old_stdout = sys.stdout
        sys.stdout = StdOutRedirector(old_stdout, log_buffer)
        log_buffer.write("🚀 === 开始执行 FreeSub 本地测活流水线 ===")

        try:
            import main_v2 as mv

            # 1. 动态覆盖配置
            output_dir = config_mgr.get_output_dir()
            mv.OUTPUT_DIR = str(output_dir)
            mv.COUNTRY_DIR = str(output_dir / "by-country")
            mv.RESIDENTIAL_COUNTRY_DIR = str(output_dir / "residential-by-country")

            cfg = config_mgr.get_config()
            active_urls = config_mgr.get_active_source_urls()
            mv.SOURCE_URLS = active_urls
            front_proxy = cfg.get("network", {}).get("front_proxy", "").strip()

            fetch_proxy = None
            if front_proxy:
                proxy_ok, real_proxy, msg = check_and_normalize_proxy(front_proxy)
                if proxy_ok:
                    fetch_proxy = real_proxy
                    log_buffer.write(f"[*] 上游订阅源抓取代理就绪: {real_proxy} ({msg})")
                else:
                    log_buffer.write(f"[!] 警告: 订阅源抓取代理 {front_proxy} 检测不可达 ({msg})，拉取将自动使用直连/镜像加速")

            # 节点测活测速严格 100% 直连测试，绝不使用代理
            os.environ.pop("FRONT_PROXY", None)
            os.environ["NODE_TEST_DETOUR"] = "0"
            log_buffer.write("[*] 【本地网络 100% 直连测活模式】节点测延迟测速严格直连，测出本地网络真实可用性与速度")

            # 自定义动态命名函数
            def custom_make_node_name(item, idx, force_residential=False):
                cc = item["country"]
                flag = mv.get_country_flag(cc)
                cname = mv.COUNTRY_NAMES.get(cc, cc)
                is_res = item["net_type"] in ("residential", "mobile") and (item["confidence"] >= 60 or force_residential)
                tag = ""
                if is_res:
                    tag = " (家宽)" if item["net_type"] == "residential" else " (移动家宽)"
                fraud = item.get("fraud_score", -1)
                risk_tag = f" R{fraud}" if 0 <= fraud < 75 and fraud >= 40 else (" ⚠R" if fraud >= 75 else "")

                lat = item.get("latency_ms") or 0
                lat_str = f"{int(lat)}ms" if lat > 0 else "0ms"

                bps = item.get("speed_bps") or 0
                mbps = (bps * 8) / 1_000_000
                spd_str = f"{round(mbps)}Mbps" if mbps >= 1 else (f"{mbps:.1f}Mbps" if mbps > 0 else "0Mbps")

                proto_label = mv.PROTOCOL_LABELS.get(item.get("proto", ""), item.get("proto", "").upper())

                tmpl = cfg.get("naming_rule", {}).get("template", "{flag} {cname} {idx:02d}{tag}{risk_tag} - {lat_str}-{spd_str}")
                try:
                    name = tmpl.format(
                        flag=flag, cname=cname, country=cname, cc=cc,
                        idx=idx, tag=tag, risk_tag=risk_tag,
                        lat_str=lat_str, latency=lat_str,
                        spd_str=spd_str, speed=spd_str,
                        proto=proto_label
                    )
                    return name
                except Exception:
                    return f"{flag} {cname} {idx:02d}{tag}{risk_tag} - {lat_str}-{spd_str}"

            mv.make_node_name = custom_make_node_name

            # 2. 准备运行环境 (sing-box 内核 / GeoLite 数据库)
            self.current_stage = "preparing"
            log_buffer.write("[*] 检查内核及 GeoLite2 离线库...")
            mv.ensure_directories()
            mv.setup_environment()

            # 3. 抓取订阅源
            self.current_stage = "fetching"
            proxy_hint = f" (前置抓取代理: {fetch_proxy})" if fetch_proxy else " (直连优先模式)"
            log_buffer.write(f"[*] 开始抓取 {len(active_urls)} 个活动订阅源{proxy_hint}...")

            def _on_source_result(src_url, success, count, err_msg="", via=""):
                if success:
                    status_txt = f"解析到 {count} 个代理节点" if count > 0 else "成功连接 (0个节点)"
                    config_mgr.record_source_fetch_result(src_url, True, count, status_txt)
                else:
                    status_txt = f"失败: {err_msg[:45]}"
                    config_mgr.record_source_fetch_result(src_url, False, 0, status_txt)

                via_tag = f"[{via}] " if via else ""
                log_buffer.write(f"    {'[✓]' if success else '[✗]'} {via_tag}{src_url} → {status_txt}")

            raw_nodes = mv.fetch_raw_nodes(on_result_cb=_on_source_result, front_proxy=fetch_proxy)
            log_buffer.write(f"[+] 初始抓取去重前总数: {len(raw_nodes)}")

            # 4. 解析协议
            self.current_stage = "parsing"
            candidates = []
            parse_fail = 0
            for uri in raw_nodes:
                p = mv.parse_node_uri(uri)
                if not p:
                    parse_fail += 1
                    continue
                outbound, server, port, proto = p
                if mv.BLACKLIST_NAME_HINTS.search(uri):
                    continue
                candidates.append((uri, outbound, server, port, proto))

            log_buffer.write(f"[+] 协议解析成功: {len(candidates)} 个候选节点 (失败 {parse_fail})")

            # 5. Cloudflare 优选 IP 智能注入
            if cfg.get("cf_clean_ip", {}).get("enabled", True):
                self.current_stage = "optimizing_cf"
                log_buffer.write("[*] 正在执行 Cloudflare Clean IP 优选与注入...")
                candidates = cf_optimizer.optimize_candidates(candidates)

            # 6. 测前凭据去重
            seen_keys, deduped = {}, []
            for item in candidates:
                uri, outbound, server, port, proto = item
                key = (server.lower() if server else "", port, proto, str(outbound.get("uuid") or outbound.get("password") or ""))
                if key not in seen_keys:
                    seen_keys[key] = [uri]
                    deduped.append(item)
                else:
                    seen_keys[key].append(uri)
            log_buffer.write(f"[*] 测前指纹去重: {len(candidates)} → {len(deduped)}")
            candidates = deduped

            # 7. 端口预检
            self.current_stage = "prefiltering"
            log_buffer.write("[*] 正在进行端口预检...")
            candidates = mv.prefilter_candidates(candidates)

            # 8. 真实测活
            self.current_stage = "probing"
            total_cand = len(candidates)
            log_buffer.write(f"[*] 启动 sing-box 多进程真实测活 (总量: {total_cand})...")
            self.progress = {"current": 0, "total": total_cand, "percentage": 0}

            # 包装带进度的单节点测试与失败原因诊断
            test_results = []
            done_cnt = 0
            fail_stats = {}
            with mv.ThreadPoolExecutor(max_workers=cfg.get("network", {}).get("max_workers", 32)) as ex:
                futs = {ex.submit(mv.test_single_node, item, True, True): item for item in candidates}
                for f in mv.as_completed(futs):
                    done_cnt += 1
                    res, reason = f.result()
                    if res:
                        test_results.append(res)
                    else:
                        fail_stats[reason] = fail_stats.get(reason, 0) + 1
                    pct = int(done_cnt / total_cand * 100) if total_cand else 100
                    self.progress = {"current": done_cnt, "total": total_cand, "percentage": pct}
                    if done_cnt % 20 == 0 or done_cnt == total_cand:
                        log_buffer.write(f"[*] 测活进度: {done_cnt}/{total_cand} ({pct}%), 存活: {len(test_results)}")

            # 测活总结诊断
            if not test_results and total_cand > 0:
                log_buffer.write(f"[!] 测活诊断: 候选节点存活数为 0。淘汰原因详细分布: {fail_stats}")
                if fail_stats.get("bin_missing", 0) > 0:
                    log_buffer.write("[❌] 致命错误: 未检测到 sing-box 内核文件，请先执行 download_assets.py 同步组件！")
                elif fail_stats.get("start_fail", 0) > (total_cand * 0.5):
                    log_buffer.write("[❌] 严重警告: 大量节点 sing-box 启动后端口未就绪，可能存在端口冲突或权限限制！")
                elif fail_stats.get("schema_err", 0) > (total_cand * 0.5):
                    log_buffer.write("[❌] 警告: 大量节点未通过 sing-box check 配置校验，可能包含不支持的协议加密格式！")
                else:
                    log_buffer.write(f"[*] 说明: 淘汰均为远端节点未响应、离线或被 GFW 拦截阻断，本地测试无虚标死节点")
            elif test_results:
                log_buffer.write(f"[+] 测活完成! 共筛选出 {len(test_results)} 个真存活低延迟优质节点")

            # 9. 家宽链式复测
            self.current_stage = "chain_retest"
            log_buffer.write("[*] 执行家宽链式双跳复测...")
            test_results = mv.chain_retest(test_results)

            # 10. 分类与多格式导出
            self.current_stage = "exporting"
            log_buffer.write("[*] 分析出口 IP 情报并导出多格式订阅...")
            unique_nodes, residential, non_residential = mv.classify_and_export(test_results)
            total_out, res_out = mv.export_all(unique_nodes, residential, non_residential)
            mv.update_readme(total_out, res_out)

            duration = int(time.time() - t0)
            now_iso = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")

            # 更新配置持久化状态
            config_mgr.save_config({
                "scheduler": {
                    "last_run": now_iso,
                    "last_duration_s": duration,
                    "last_status": "成功",
                    "last_node_count": total_out,
                    "last_residential_count": res_out
                }
            })

            # 自动同步至 GitHub (若启用)
            gh_cfg = cfg.get("github_sync", {})
            if gh_cfg.get("enabled") and gh_cfg.get("token") and gh_cfg.get("repo"):
                log_buffer.write("[*] 检测到 GitHub 云端同步已开启，正在向 GitHub 推送订阅并刷新 CDN 缓存...")
                try:
                    try:
                        import web.github_sync as github_sync
                    except ImportError:
                        import github_sync
                    sync_res = github_sync.sync_files_to_github(
                        token=gh_cfg.get("token", ""),
                        repo=gh_cfg.get("repo", ""),
                        branch=gh_cfg.get("branch", "main"),
                        target_dir=gh_cfg.get("target_dir", "output"),
                        local_dir=config_mgr.get_output_dir(),
                        log_cb=log_buffer.write
                    )
                    cdn_links = github_sync.generate_cdn_links(
                        repo=gh_cfg.get("repo", ""),
                        branch=gh_cfg.get("branch", "main"),
                        target_dir=gh_cfg.get("target_dir", "output")
                    )
                    config_mgr.save_config({
                        "github_sync": {
                            "last_sync_time": now_iso,
                            "last_sync_status": sync_res.get("message", "已同步"),
                            "cdn_links": cdn_links
                        }
                    })
                except Exception as sync_err:
                    log_buffer.write(f"    [!] GitHub 自动同步异常: {sync_err}")
                    config_mgr.save_config({
                        "github_sync": {
                            "last_sync_time": now_iso,
                            "last_sync_status": f"同步失败: {str(sync_err)[:40]}"
                        }
                    })

            log_buffer.write(f"🎉 === 测活完成! 耗时: {duration}s, 存活总数: {total_out}, 住宅IP: {res_out} ===")

        except Exception as e:
            err_trace = traceback.format_exc()
            log_buffer.write(f"❌ [错误] 测活流水线异常中断: {e}\n{err_trace}")
            config_mgr.save_config({
                "scheduler": {
                    "last_run": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "last_status": f"失败: {str(e)[:50]}"
                }
            })
        finally:
            try:
                sys.stdout.flush()
                sys.stdout = old_stdout
            except Exception:
                pass
            with self._lock:
                self.is_running = False
                self.current_stage = "idle"


engine_runner = EngineRunner()
