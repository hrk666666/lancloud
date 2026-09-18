# -*- coding: utf-8 -*-
"""配置管理：全局配置、域名映射、外部挂载的读取 / 持久化"""
import json
import sys
import threading
from pathlib import Path

if getattr(sys, "frozen", False):
    # PyInstaller 打包环境：数据目录放在可执行文件旁边，实现"绿色版便携"
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
CONFIG_PATH = DATA_DIR / "config.json"
DOMAINS_PATH = DATA_DIR / "domains.json"
MOUNTS_PATH = DATA_DIR / "mounts.json"

DEFAULTS = {
    "web_port": 8080,              # 网盘 Web 服务端口
    "dns_port": 53,                # DNS 服务端口（<1024 需要管理员权限）
    "dns_enabled": True,           # 启动时自动开启 DNS 服务
    "dns_upstream": "223.5.5.5",   # 未匹配域名的上游 DNS（阿里公共 DNS）
    "allow_register": True,        # 是否开放普通用户注册
    "default_quota_mb": 0,         # 新用户默认存储配额，0 = 不限
    "admin_user": "admin",         # 管理员账号
    "admin_password": "admin123",  # 首次启动自动创建
    "max_upload_mb": 0,            # 单文件上传大小限制，0 = 不限
    "https_enabled": False,        # 是否启用自签名 HTTPS
    "https_port": 8443,            # HTTPS 端口（劫持 HTTPS 站点时可设为 443）
}

_lock = threading.Lock()


def ensure_dirs():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "files").mkdir(exist_ok=True)
    (DATA_DIR / "trash").mkdir(exist_ok=True)
    (DATA_DIR / "tmp").mkdir(exist_ok=True)
    (DATA_DIR / "certs").mkdir(exist_ok=True)


def load_config() -> dict:
    ensure_dirs()
    cfg = dict(DEFAULTS)
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                cfg.update(json.load(f))
        except Exception:
            pass
    return cfg


def save_config(cfg: dict):
    with _lock:
        CONFIG_PATH.write_text(
            json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def load_domains() -> list:
    """域名映射列表：[{id, domain, ip, enabled, note}]"""
    ensure_dirs()
    if DOMAINS_PATH.exists():
        try:
            return json.loads(DOMAINS_PATH.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def save_domains(domains: list):
    with _lock:
        DOMAINS_PATH.write_text(
            json.dumps(domains, ensure_ascii=False, indent=2), encoding="utf-8")


def load_mounts() -> list:
    """外部文件夹挂载：[{id, name, path, readonly, enabled, created}]"""
    ensure_dirs()
    if MOUNTS_PATH.exists():
        try:
            return json.loads(MOUNTS_PATH.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def save_mounts(mounts: list):
    with _lock:
        MOUNTS_PATH.write_text(
            json.dumps(mounts, ensure_ascii=False, indent=2), encoding="utf-8")
