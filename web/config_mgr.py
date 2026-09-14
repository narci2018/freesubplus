import os
import json
import uuid
import copy
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("DATA_DIR", BASE_DIR / "data"))
CONFIG_FILE = DATA_DIR / "config.json"

DEFAULT_CONFIG = {
    "port": 18168,
    "scheduler": {
        "enabled": True,
        "interval_hours": 6,
        "last_run": None,
        "last_duration_s": 0,
        "last_status": "未运行",
        "last_node_count": 0,
        "last_residential_count": 0,
    },
    "naming_rule": {
        "template": "{flag} {cname} {idx:02d}{tag}{risk_tag} - {lat_str}-{spd_str}",
        "example": "🇭🇰 中国香港 (Hong Kong) 01 - 93ms-45Mbps"
    },
    "cf_clean_ip": {
        "enabled": True,
        "auto_fetch": True,
        "fetch_urls": [
            "https://addressesapi.090227.xyz/CloudFlareYes",
            "https://raw.githubusercontent.com/vfarid/cf-clean-ips/main/list.json"
        ],
        "custom_ips": [
            "162.159.192.1",
            "104.16.160.1",
            "172.64.32.1",
            "104.17.160.1",
            "104.18.160.1",
            "162.159.193.1"
        ],
        "top_n_to_use": 3
    },
    "network": {
        "front_proxy": "",
        "max_workers": 32,
        "probe_timeout": 12,
        "speed_test_budget": 5.0,
        "min_speed_kbps": 70
    },
    "sources": [
        {
            "id": "src_1",
            "name": "Cloudflare Worker 汇聚源",
            "url": "https://wild-cloud-9893.heleimail.workers.dev",
            "enabled": True,
            "last_fetched_count": 0,
            "last_status": "未测试",
            "success_count": 0,
            "fail_count": 0
        },
        {
            "id": "src_2",
            "name": "台湾专区订阅源",
            "url": "https://github.com/Au1rxx/free-vpn-subscriptions/raw/main/output/by-country/v2ray-base64-TW.txt",
            "enabled": True,
            "last_fetched_count": 0,
            "last_status": "未测试",
            "success_count": 0,
            "fail_count": 0
        },
        {
            "id": "src_3",
            "name": "ConfigForge 全协议汇总",
            "url": "https://raw.githubusercontent.com/ShatakVPN/ConfigForge-V2Ray/main/configs/all.txt",
            "enabled": True,
            "last_fetched_count": 0,
            "last_status": "未测试",
            "success_count": 0,
            "fail_count": 0
        },
        {
            "id": "src_4",
            "name": "HiN-VPN 混合协议池",
            "url": "https://raw.githubusercontent.com/10ium/HiN-VPN/main/subscription/base64/mix",
            "enabled": True,
            "last_fetched_count": 0,
            "last_status": "未测试",
            "success_count": 0,
            "fail_count": 0
        },
        {
            "id": "src_5",
            "name": "TG 采集池 - Hysteria 协议",
            "url": "https://raw.githubusercontent.com/10ium/telegram-configs-collector/main/protocols/hysteria",
            "enabled": True,
            "last_fetched_count": 0,
            "last_status": "未测试",
            "success_count": 0,
            "fail_count": 0
        },
        {
            "id": "src_6",
            "name": "TG 采集池 - TLS 安全节点",
            "url": "https://raw.githubusercontent.com/10ium/telegram-configs-collector/main/security/tls",
            "enabled": True,
            "last_fetched_count": 0,
            "last_status": "未测试",
            "success_count": 0,
            "fail_count": 0
        },
        {
            "id": "src_7",
            "name": "全球综合节点池",
            "url": "https://github.com/Au1rxx/free-vpn-subscriptions/raw/main/output/v2ray-base64.txt",
            "enabled": True,
            "last_fetched_count": 0,
            "last_status": "未测试",
            "success_count": 0,
            "fail_count": 0
        },
        {
            "id": "src_8",
            "name": "FreeFQ v2 订阅源",
            "url": "https://raw.githubusercontent.com/freefq/free/master/v2",
            "enabled": True,
            "last_fetched_count": 0,
            "last_status": "未测试",
            "success_count": 0,
            "fail_count": 0
        },
        {
            "id": "src_9",
            "name": "Open Helei Worker 接口",
            "url": "https://open.heleimail.workers.dev/",
            "enabled": True,
            "last_fetched_count": 0,
            "last_status": "未测试",
            "success_count": 0,
            "fail_count": 0
        },
        {
            "id": "src_10",
            "name": "二毛博客 v2ray 订阅",
            "url": "https://www.ermao.net/sub/v2ray/ermao.net",
            "enabled": True,
            "last_fetched_count": 0,
            "last_status": "未测试",
            "success_count": 0,
            "fail_count": 0
        }
    ]
}


class ConfigManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ConfigManager, cls).__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        (DATA_DIR / "output").mkdir(parents=True, exist_ok=True)
        if not CONFIG_FILE.exists():
            self._save_file(DEFAULT_CONFIG)
            self._config = copy.deepcopy(DEFAULT_CONFIG)
        else:
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                self._config = copy.deepcopy(DEFAULT_CONFIG)
                self._deep_update(self._config, loaded)
            except Exception as e:
                print(f"[!] 读取配置文件失败，重置为默认: {e}")
                self._config = copy.deepcopy(DEFAULT_CONFIG)
                self._save_file(self._config)

        # 确保旧配置文件中的订阅源具有 success_count 和 fail_count 字段
        for s in self._config.get("sources", []):
            s.setdefault("success_count", 0)
            s.setdefault("fail_count", 0)

    def _deep_update(self, base_dict, update_dict):
        for k, v in update_dict.items():
            if isinstance(v, dict) and k in base_dict and isinstance(base_dict[k], dict):
                self._deep_update(base_dict[k], v)
            else:
                base_dict[k] = v

    def _save_file(self, data):
        tmp_file = CONFIG_FILE.with_suffix(".tmp")
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        tmp_file.replace(CONFIG_FILE)

    def get_config(self) -> dict:
        return copy.deepcopy(self._config)

    def save_config(self, new_config: dict):
        self._deep_update(self._config, new_config)
        self._save_file(self._config)

    def get_active_source_urls(self) -> list:
        return [s["url"] for s in self._config.get("sources", []) if s.get("enabled", True)]

    def add_source(self, name: str, url: str) -> dict:
        sources = self._config.setdefault("sources", [])
        new_source = {
            "id": f"src_{uuid.uuid4().hex[:8]}",
            "name": name.strip() or "未命名订阅源",
            "url": url.strip(),
            "enabled": True,
            "last_fetched_count": 0,
            "last_status": "未测试",
            "success_count": 0,
            "fail_count": 0
        }
        sources.append(new_source)
        self.save_config({"sources": sources})
        return new_source

    def update_source(self, source_id: str, updates: dict) -> bool:
        sources = self._config.get("sources", [])
        for s in sources:
            if s["id"] == source_id:
                s.update(updates)
                self.save_config({"sources": sources})
                return True
        return False

    def delete_source(self, source_id: str) -> bool:
        sources = self._config.get("sources", [])
        orig_len = len(sources)
        sources = [s for s in sources if s["id"] != source_id]
        if len(sources) != orig_len:
            self.save_config({"sources": sources})
            return True
        return False

    def record_source_fetch_result(self, url: str, success: bool, count: int = 0, status_msg: str = ""):
        """记录单次订阅源拉取结果，自增成功/失败计数并更新状态"""
        sources = self._config.get("sources", [])
        changed = False
        target_url = url.strip().rstrip("/")

        for s in sources:
            curr_url = s.get("url", "").strip().rstrip("/")
            if curr_url == target_url:
                if success:
                    s["success_count"] = s.get("success_count", 0) + 1
                    s["last_status"] = f"成功 (解析 {count} 个)"
                    s["last_fetched_count"] = count
                else:
                    s["fail_count"] = s.get("fail_count", 0) + 1
                    s["last_status"] = f"失败: {status_msg[:35]}" if status_msg else "拉取失败"
                changed = True
                break

        if changed:
            self.save_config({"sources": sources})

    def get_output_dir(self) -> Path:
        out = DATA_DIR / "output"
        out.mkdir(parents=True, exist_ok=True)
        return out


config_mgr = ConfigManager()
