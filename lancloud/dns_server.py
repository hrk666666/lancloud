# -*- coding: utf-8 -*-
"""局域网 DNS 服务（域名定向）

原理：
  1. 客户端把 DNS 指向本机（路由器 DHCP 或设备手动设置）；
  2. 查询命中配置的"域名映射"时，直接返回你指定的 IP（如本机局域网 IP）；
  3. 其余域名转发给上游 DNS（默认阿里 223.5.5.5），不影响正常上网。

支持 UDP + TCP 两种查询（Windows 解析器可能在 UDP 失败时用 TCP 兜底），
并记录最近查询日志，便于诊断"设备是否真的来查询了"。

说明：DNS 只能决定"域名解析到哪个 IP"。目标站点是 HTTPS 时，浏览器会做证书
校验（自签名证书可显示但会警告）。本服务面向自建网盘等自有服务，请仅在
你自己拥有或已获授权的网络中使用。
"""
import socket
import threading
import time
from collections import deque

from dnslib import A, QTYPE, RR, DNSRecord


class LanDNSServer:
    def __init__(self, get_domains, port: int = 53, upstream: str = "223.5.5.5"):
        self.get_domains = get_domains   # 回调：返回域名映射列表
        self.port = port
        self.upstream = upstream
        self._udp = None
        self._tcp = None
        self._threads = []
        self._running = False
        self._cache = {}
        self.error = None
        self.log = deque(maxlen=200)     # (time, client, qname, action)

    @property
    def running(self) -> bool:
        return self._running

    def _log(self, client: str, qname: str, action: str):
        self.log.appendleft((int(time.time()), client, qname, action))

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

    def _handle(self, data: bytes, addr) -> bytes:
        client = addr[0] if isinstance(addr, tuple) else str(addr)
        try:
            req = DNSRecord.parse(data)
            q = req.q
            qname = str(q.qname).rstrip(".")
            if q.qtype == QTYPE.A:
                for d in self.get_domains():
                    if d.get("enabled", True) and d.get("domain", "").lower() == qname.lower():
                        ip = (d.get("ip") or "").strip()
                        if not ip:
                            return None
                        reply = req.reply()
                        reply.add_answer(RR(q.qname, QTYPE.A, rdata=A(ip), ttl=60))
                        self._log(client, qname, "命中映射 → " + ip)
                        return reply.pack()
            # 未匹配 → 转发上游
            resp = self._resolve_upstream(data, qname)
            self._log(client, qname, "转发上游" if resp else "上游无响应")
            return resp
        except Exception as e:
            self._log(client, str(addr), f"解析异常: {e}")
            return None

    # ---------- UDP ----------
    def _udp_loop(self):
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

    # ---------- TCP ----------
    def _tcp_loop(self):
        while self._running:
            try:
                conn, addr = self._tcp.accept()
            except OSError:
                break
            threading.Thread(target=self._tcp_session, args=(conn, addr),
                             daemon=True).start()

    def _tcp_session(self, conn, addr):
        with conn:
            conn.settimeout(5)
            try:
                length = conn.recv(2)
                if len(length) != 2:
                    return
                (msg_len,) = struct_unpack(length)
                data = b""
                while len(data) < msg_len:
                    chunk = conn.recv(msg_len - len(data))
                    if not chunk:
                        return
                    data += chunk
                resp = self._handle(data, addr)
                if resp:
                    conn.sendall(len(resp).to_bytes(2, "big") + resp)
            except Exception:
                pass

    # ---------- 启停 ----------
    def start(self):
        if self._running:
            return True, "DNS 服务已在运行"
        try:
            self._udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._udp.bind(("0.0.0.0", self.port))
            self._udp.settimeout(1.0)
        except PermissionError:
            self.error = (f"端口 {self.port} 需要管理员权限：Windows 请以管理员身份"
                          "运行 LanCloud.exe，Linux/macOS 请用 sudo 启动")
            return False, self.error
        except OSError as e:
            self.error = f"端口 {self.port} 被占用或不可用：{e}"
            return False, self.error
        # TCP（失败不阻断 UDP 服务）
        self._tcp = None
        try:
            self._tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._tcp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._tcp.bind(("0.0.0.0", self.port))
            self._tcp.listen(16)
            self._tcp.settimeout(1.0)
        except OSError:
            self._tcp = None
        self._running = True
        self.error = None
        threading.Thread(target=self._udp_loop, daemon=True).start()
        if self._tcp:
            threading.Thread(target=self._tcp_loop, daemon=True).start()
        return True, f"DNS 服务已启动，监听 UDP{self.port}" + \
            (f"/TCP{self.port}" if self._tcp else "")

    def stop(self):
        self._running = False
        for s in (self._udp, self._tcp):
            if s:
                try:
                    s.close()
                except Exception:
                    pass
        self._udp = self._tcp = None
        return True, "DNS 服务已停止"


def struct_unpack(b: bytes) -> int:
    return int.from_bytes(b, "big")
