#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LanCloud 启动入口

用法：
    python run.py                 # 使用 data/config.json 中的配置启动
    LANCLOUD_PORT=9000 python run.py   # 临时改 Web 端口
    LANCLOUD_DNS_PORT=8053 python run.py  # 临时改 DNS 端口

启动 HTTP 服务；若配置开启自签名 HTTPS（https_enabled），同时在
https_port 上启动 HTTPS 服务。
"""
import os
import socket
import sys
import threading
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
    port = int(os.environ.get("LANCLOUD_PORT", cfg.get("web_port", 8080)))
    dns_port = int(os.environ.get("LANCLOUD_DNS_PORT", cfg.get("dns_port", 53)))
    if os.environ.get("LANCLOUD_DNS_PORT"):
        cfg["dns_port"] = dns_port
        config.save_config(cfg)

    import uvicorn

    http_cfg = uvicorn.Config(app, host="0.0.0.0", port=port,
                              log_level="warning")
    http_server = uvicorn.Server(http_cfg)

    https_server = None
    if cfg.get("https_enabled"):
        try:
            from lancloud import certs
            from lancloud.server import lan_ips as server_lan_ips

            domains = [d["domain"] for d in config.load_domains()
                       if d.get("enabled", True)]
            certs.ensure_certs(domains, server_lan_ips())
            https_port = int(cfg.get("https_port", 8443))
            https_cfg = uvicorn.Config(
                app, host="0.0.0.0", port=https_port,
                ssl_certfile=str(config.DATA_DIR / "certs" / "server.crt"),
                ssl_keyfile=str(config.DATA_DIR / "certs" / "server.key"),
                log_level="warning")
            https_server = uvicorn.Server(https_cfg)
            print(f"[HTTPS] 已启用：https://127.0.0.1:{https_port}"
                  "（首次访问有证书警告，可在管理面板下载 CA 证书安装）")
        except Exception as e:
            print(f"[HTTPS] 启动失败（已跳过）：{e}")

    print("=" * 56)
    print(" LanCloud 局域网私有云网盘")
    print("=" * 56)
    print(f" 网盘地址   : http://127.0.0.1:{port}")
    for ip in lan_ips():
        print(f" 局域网地址 : http://{ip}:{port}")
    print(f" DNS 服务   : 端口 {dns_port}（未匹配域名转发上游，不影响上网）")
    print(" 数据目录   :", config.DATA_DIR)
    print(" 提示: 局域网其他设备需把 DNS 指向本机后，"
          "才能通过自定义域名访问（见管理面板教程）")
    print("=" * 56)

    if https_server:
        t = threading.Thread(target=https_server.run, daemon=True)
        t.start()
    http_server.run()


if __name__ == "__main__":
    main()
