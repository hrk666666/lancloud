#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LanCloud 启动入口

用法：
    python run.py                 # 使用 data/config.json 中的配置启动
    LANCLOUD_PORT=9000 python run.py   # 临时改 Web 端口
    LANCLOUD_DNS_PORT=8053 python run.py  # 临时改 DNS 端口
"""
import os
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lancloud import config  # noqa: E402
from lancloud.server import app  # noqa: E402  显式导入，供 PyInstaller 收集


def lan_ips() -> list:
    ips = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ips.append(s.getsockname()[0])
        s.close()
    except Exception:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127.") and ip not in ips:
                ips.append(ip)
    except Exception:
        pass
    return ips


def main():
    cfg = config.load_config()
    port = int(os.environ.get("LANCLOUD_PORT", cfg["web_port"]))
    dns_port = int(os.environ.get("LANCLOUD_DNS_PORT", cfg["dns_port"]))
    if port != cfg["web_port"] or dns_port != cfg["dns_port"]:
        cfg["web_port"] = port
        cfg["dns_port"] = dns_port
        config.save_config(cfg)

    print("=" * 56)
    print("  LanCloud 局域网私有云网盘  v" +
          __import__("lancloud").__version__)
    print("=" * 56)
    print("  网盘地址：")
    for ip in lan_ips():
        print(f"    http://{ip}:{port}   （局域网内任何设备可访问）")
    print(f"    本机：   http://127.0.0.1:{port}")
    print(f"  DNS 服务：UDP 端口 {dns_port}（域名定向，启动失败不影响网盘）")
    print("  管理面板：登录后点击左侧「管理面板」")
    print("  数据目录：data/（用户、文件、配置均在本机）")
    print("=" * 56)

    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


if __name__ == "__main__":
    main()
