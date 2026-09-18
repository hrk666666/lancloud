# -*- coding: utf-8 -*-
"""局域网 DNS 服务（域名定向）

原理：
  1. 客户端把 DNS 指向本机（路由器 DHCP 或设备手动设置）；
  2. 查询命中了你在管理面板配置的"域名映射"时，直接返回你指定的 IP（如本机局域网 IP）；
  3. 其余域名转发给上游 DNS（默认阿里 223.5.5.5），不影响正常上网。

说明：DNS 只能决定"域名解析到哪个 IP"。目标站点是 HTTPS 时，浏览器会做证书
校验，本服务无法静默劫持 HTTPS 网站（这是 TLS 的设计保证）。本服务面向自建
网盘等自有服务，请仅在你自己拥有或已获授权的网络中使用。
"""
import socket
import threading
import time

from dnslib import A, QTYPE, RR, DNSRecord


class LanDNSServer:
    def __init__(self, get_domains, port: int = 53, upstream: str = "223.5.5.5"):
        self.get_domains = get_domains   # 回调：返回域名映射列表
        self.port = port
        self.upstream = upstream
        self._udp = None
        self._thread = None
        self._running = False
        self._cache = {}
        self.error = None

    @property
    def running(self) -> bool:
        return self._running

    def _resolve_upstream(self, data: bytes, qname: str):
        """未命中映射时转发上游 DNS，带 10 秒缓存"""
        now = time.time()
        hit = self._cache.get(qname)
        if hit and hit[1] > now:
            return hit[0]
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(2.5)
            s.sendto(data, (self.upstream, 53))
            resp, _ = s.recvfrom(4096)
            s.close()
            self._cache[qname] = (resp, now + 10)
            return resp
        except Exception:
            return None

    def _handle(self, data: bytes, addr):
        try:
            req = DNSRecord.parse(data)
            q = req.q
            if q.qtype == QTYPE.A:
                qname = str(q.qname).rstrip(".")
                for d in self.get_domains():
                    if d.get("enabled", True) and d.get("domain", "").lower() == qname.lower():
                        ip = (d.get("ip") or "").strip()
                        if not ip:
                            return None
                        reply = req.reply()
                        reply.add_answer(RR(q.qname, QTYPE.A, rdata=A(ip), ttl=60))
                        return reply.pack()
            # 未匹配 → 转发上游
            return self._resolve_upstream(data, str(q.qname))
        except Exception:
            return None

    def start(self):
        if self._running:
            return True, "DNS 服务已在运行"
        try:
            self._udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._udp.bind(("0.0.0.0", self.port))
            self._udp.settimeout(1.0)
            self._running = True
            self.error = None
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()
            return True, f"DNS 服务已启动，监听端口 {self.port}"
        except PermissionError:
            self.error = (f"端口 {self.port} 需要管理员权限：Windows 请用管理员运行，"
                          "Linux/macOS 请用 sudo 启动或为 python 设置 setcap")
            return False, self.error
        except OSError as e:
            self.error = f"端口 {self.port} 被占用或不可用：{e}"
            return False, self.error

    def _loop(self):
        while self._running:
            try:
                data, addr = self._udp.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                break
            if data:
                resp = self._handle(data, addr)
                if resp:
                    try:
                        self._udp.sendto(resp, addr)
                    except OSError:
                        pass

    def stop(self):
        self._running = False
        if self._udp:
            try:
                self._udp.close()
            except Exception:
                pass
        self._udp = None
        return True, "DNS 服务已停止"
