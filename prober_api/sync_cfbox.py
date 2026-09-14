import json
import os
import re
from collections import defaultdict
from typing import Dict, Any, Tuple, List

CONFIG_PATH = "prober_config.json"
TESTED_POOL_PATH = "tested_pool.txt"


def http_post_json(url: str, payload: dict, timeout: float = 15.0) -> Tuple[int, str]:
    """支持 httpx，无依赖时自动降级使用 Python 标准库 urllib"""
    try:
        import httpx
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.post(url, json=payload, headers={"Content-Type": "application/json"})
            return resp.status_code, resp.text
    except ImportError:
        import urllib.request
        import urllib.error
        req_data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=req_data,
            headers={"Content-Type": "application/json", "User-Agent": "ProberAPI-CFBoxSync/1.0"},
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return response.status, response.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8")


def load_prober_config() -> Dict[str, Any]:
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[CFBox Sync] 加载配置文件失败: {e}")
    return {}


def parse_country_code(node_line: str) -> str:
    """
    从节点备注中提取国家代码。
    节点格式示例：
        104.16.1.1:443#[HK 香港 13.5ms]
        1.2.3.4:443#[US 美国 20ms]
        5.6.7.8:443#[SG 新加坡 44.99ms]
    提取 # 后方括号内第一个两字母大写单词作为国家代码。
    无法识别时返回 "XX"（归入未知分组）。
    """
    m = re.search(r'#\[([A-Z]{2})\b', node_line)
    if m:
        return m.group(1)
    # 兼容无方括号格式：#US 美国
    m2 = re.search(r'#([A-Z]{2})\b', node_line)
    if m2:
        return m2.group(1)
    return "XX"


def apply_country_rules(
    nodes: List[str],
    default_per_country: int = 0,
    country_rules: Dict[str, int] = None,
    max_nodes: int = 0
) -> List[str]:
    """
    对已按延迟从小到大排序的节点列表，按国家配额规则进行筛选：
    
    - default_per_country: 每个国家的默认上限，0 表示不限。
    - country_rules: 特殊国家覆盖规则，格式 {"HK": 10, "US": 5, "US": 0 表示不限该国}。
      特殊值 -1 表示该国家节点全部排除。
    - max_nodes: 最终总数上限（0 = 不限），在国家规则过滤后再做总数截断。
    
    节点保留优先级：延迟最低的优先（输入列表已按延迟正序排列）。
    """
    if country_rules is None:
        country_rules = {}

    # 将 country_rules 的键统一为大写
    rules = {k.upper(): v for k, v in country_rules.items()}

    # 如果没有任何国家规则且 default_per_country == 0，直接按总数截断返回
    if default_per_country == 0 and not rules:
        result = nodes[:max_nodes] if max_nodes > 0 else nodes
        return result

    country_count: Dict[str, int] = defaultdict(int)
    result: List[str] = []

    for node in nodes:
        cc = parse_country_code(node)
        # 优先使用特殊规则，再使用默认规则
        if cc in rules:
            cap = rules[cc]
        else:
            cap = default_per_country  # 0 = 不限

        if cap == -1:
            # -1 表示完全排除该国家
            continue
        if cap > 0 and country_count[cc] >= cap:
            # 已达该国配额
            continue

        result.append(node)
        country_count[cc] += 1

        if max_nodes > 0 and len(result) >= max_nodes:
            break

    return result


def print_country_summary(nodes: List[str]) -> None:
    """打印节点按国家分布统计"""
    counter: Dict[str, int] = defaultdict(int)
    for n in nodes:
        cc = parse_country_code(n)
        counter[cc] += 1
    sorted_cc = sorted(counter.items(), key=lambda x: -x[1])
    parts = [f"{cc}:{cnt}" for cc, cnt in sorted_cc]
    print(f"[CFBox Sync] 国家分布: {', '.join(parts)}")


def sync_to_cfbox(max_nodes: int = None) -> Tuple[bool, str]:
    """
    将 tested_pool.txt 中优选出的低延迟 IP 实时同步推送至部署在 CF Pages 的 CFBox
    使用 CFBox 原生 /{UUID}/api/config 接口更新 yx 字段并实时重载优选池
    """
    cfg = load_prober_config()
    cfbox_cfg = cfg.get("cfbox_sync", {})

    if not cfbox_cfg.get("enabled", False):
        msg = "CFBox 自动同步未开启 (enabled=false)，跳过同步。"
        print(f"[CFBox Sync] {msg}")
        return False, msg

    base_url = cfbox_cfg.get("url", "").strip().rstrip("/")
    uuid = cfbox_cfg.get("uuid", "").strip()
    custom_path = cfbox_cfg.get("custom_path", "").strip().lstrip("/")
    limit = max_nodes or cfbox_cfg.get("max_nodes", 600000)
    default_per_country = int(cfbox_cfg.get("default_per_country", 0))
    country_rules: Dict[str, int] = cfbox_cfg.get("country_rules", {})

    if not base_url or not uuid:
        msg = "未配置 CFBox 访问域名 (url) 或 UUID，无法同步。"
        print(f"[CFBox Sync] {msg}")
        return False, msg

    if not os.path.exists(TESTED_POOL_PATH):
        msg = f"未找到优选节点文件 {TESTED_POOL_PATH}，请先执行测速洗池。"
        print(f"[CFBox Sync] {msg}")
        return False, msg

    # 读取清洗且排序后的节点（已按延迟从小到大）
    all_nodes: List[str] = []
    with open(TESTED_POOL_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and "#" in line:
                all_nodes.append(line)

    if not all_nodes:
        msg = "优选节点池为空，无可用节点进行同步。"
        print(f"[CFBox Sync] {msg}")
        return False, msg

    # ── 按国家配额规则过滤 ───────────────────────────────────────────
    nodes = apply_country_rules(
        nodes=all_nodes,
        default_per_country=default_per_country,
        country_rules=country_rules,
        max_nodes=limit
    )

    if not nodes:
        msg = "经国家规则过滤后无可用节点，请检查 country_rules 配置。"
        print(f"[CFBox Sync] {msg}")
        return False, msg

    print(f"[CFBox Sync] 原始节点 {len(all_nodes)} 个 → 规则过滤后 {len(nodes)} 个")
    print_country_summary(nodes)

    # CFBox 内部有两个优选模块：
    # 1. 进阶模式高级控制的 yx: 逗号分隔
    # 2. 首页中央【优选订阅生成】的 subCustomIPs: 换行符分隔 (每行一个)
    yx_comma = ",".join(nodes)
    sub_custom_newline = "\n".join(nodes)
    payload = {
        "yx": yx_comma,
        "subCustomIPs": sub_custom_newline
    }

    # 构造请求 URL: /{custom_path}/api/config 或 /{uuid}/api/config
    path_prefix = custom_path if custom_path else uuid
    api_endpoint = f"{base_url}/{path_prefix}/api/config"

    print(f"[CFBox Sync] 正在向 {api_endpoint} 推送 {len(nodes)} 个优质节点...")

    try:
        status_code, resp_text = http_post_json(api_endpoint, payload, timeout=15.0)

        if status_code == 200:
            try:
                res_data = json.loads(resp_text)
            except Exception:
                res_data = {}
            if res_data.get("success", False) or "config" in res_data:
                msg = (
                    f"[SUCCESS] 同步成功！已向 CFBox 更新 {len(nodes)} 个优质节点，"
                    f"Cloudflare KV 已保存并即时生效。"
                )
                print(f"[CFBox Sync] {msg}")
                return True, msg
            else:
                msg = f"[FAILED] 同步失败: CFBox 返回错误: {res_data.get('message', resp_text)}"
                print(f"[CFBox Sync] {msg}")
                return False, msg
        else:
            msg = f"[FAILED] 同步失败: HTTP 状态码 {status_code}, 响应: {resp_text}"
            print(f"[CFBox Sync] {msg}")
            return False, msg
    except Exception as e:
        msg = f"[ERROR] 同步异常: {str(e)}"
        print(f"[CFBox Sync] {msg}")
        return False, msg


if __name__ == "__main__":
    success, message = sync_to_cfbox()
    print(f"执行结果: success={success}, msg={message}")
