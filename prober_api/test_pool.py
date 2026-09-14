import asyncio
import time
import os
import sys

CACHE_PATH = "cached_pool.txt"
TESTED_PATH = "tested_pool.txt"
TIMEOUT_SEC = 1.5
# 并发上限从 500 降至 200：
# - 容器默认 ulimit -n = 1024，500 并发 + Python 内部 FD (~30) + 泄漏累积会超上限
# - 已在 docker-compose.yml 中将 ulimits.nofile 调至 65535，但代码层也做保守限制
CONCURRENCY_LIMIT = 200


async def check_tcp_latency(ip_str: str, remark: str, default_port: int,
                             sem: asyncio.Semaphore) -> tuple:
    async with sem:
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
        writer = None
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(ip, port),
                timeout=TIMEOUT_SEC
            )
            latency = (time.time() - start_time) * 1000
            return (True, ip_str, remark, latency)
        except Exception:
            return (False, ip_str, remark, -1)
        finally:
            # ── 关键修复：asyncio.wait_for 超时取消时，底层 socket 不会自动关闭 ──
            # 若不在 finally 里强制关闭，每次 timeout 都会泄漏一个 FD，
            # 3000+ 节点跑到约 79% 时就会耗尽默认的 1024 FD 上限 (Errno 24)
            if writer is not None:
                try:
                    writer.close()
                    await asyncio.wait_for(writer.wait_closed(), timeout=0.5)
                except Exception:
                    pass


async def run_test():
    if not os.path.isfile(CACHE_PATH):
        print(f"[错误] {CACHE_PATH} 不存在，请先执行「更新原始池」。")
        return

    nodes = []
    with open(CACHE_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or "#" not in line:
                continue
            ip_port, remark = line.split("#", 1)
            nodes.append((ip_port, remark))

    total = len(nodes)
    print(f"[*] 开始测活，共 {total} 个节点，并发上限 {CONCURRENCY_LIMIT}...")

    sem = asyncio.Semaphore(CONCURRENCY_LIMIT)
    alive_nodes_data = []
    done_count = 0
    alive_count = 0
    report_interval = max(1, total // 20)   # 每完成约 5% 打印一次进度
    last_report = 0

    # 用 as_completed 模式逐个处理结果，避免 gather 把所有任务一次性调度
    # （gather 不会减少内存里同时存在的 Task 数量，as_completed 更友好）
    tasks = {
        asyncio.ensure_future(
            check_tcp_latency(ip_port, remark, 443, sem)
        ): (ip_port, remark)
        for ip_port, remark in nodes
    }

    try:
        for coro in asyncio.as_completed(tasks.keys()):
            success, ip_str, remark, latency = await coro
            done_count += 1
            if success and latency <= 1500:
                alive_count += 1
                alive_nodes_data.append((ip_str, remark, latency))

            if done_count - last_report >= report_interval or done_count == total:
                pct = done_count * 100 // total
                ts = time.strftime("%H:%M:%S")
                print(f"[{ts}] [*] 测活进度: {done_count}/{total} ({pct}%), 存活: {alive_count}")
                last_report = done_count

    except Exception as e:
        ts = time.strftime("%H:%M:%S")
        print(f"[{ts}] ❌ [错误] 测活流水线异常中断: {e}", file=sys.stderr)
        # 取消所有尚未完成的任务，防止 FD 泄漏
        for t in tasks:
            if not t.done():
                t.cancel()
        raise

    # 按延迟升序排列
    alive_nodes_data.sort(key=lambda x: x[2])

    alive_nodes_strings = []
    for ip_str, remark, latency in alive_nodes_data:
        clean_remark = remark.rstrip("]")
        formatted = f"{clean_remark} {latency:.2f}ms]"
        alive_nodes_strings.append(f"{ip_str}#{formatted}")

    with open(TESTED_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(alive_nodes_strings))

    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] ✅ 测活完成。存活节点 (<1500ms): {len(alive_nodes_strings)} / {total}")

    # 自动触发 CFBox 优选节点实时同步 (方案一)
    try:
        from sync_cfbox import sync_to_cfbox
        sync_to_cfbox()
    except Exception as e:
        print(f"[CFBox Sync Error] 自动同步异常: {e}")


if __name__ == "__main__":
    asyncio.run(run_test())
