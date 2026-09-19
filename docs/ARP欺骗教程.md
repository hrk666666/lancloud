# ARP DNS 劫持（方案 C · 零配置全自动接管）

> 场景：想让局域网内所有设备**一个设置都不用做**，连上同一个 WiFi / 网线就自动被接管 DNS，打开 `pan.lan` 直达你的网盘。
> 这需要从**网络层**接管，由本机伪装成网关，自动截获设备的 DNS 查询。

## 一、原理（30 秒看懂）

普通劫持需要设备把 DNS 指向你（路由器 DHCP 或手动设置）。方案 C 反过来：**本机主动"冒充网关"**。

```
设备本来以为:  网关(路由器)  ←── 所有流量（含 DNS 查询）

方案C之后:     网关(路由器)     ←── 非 DNS 流量（本机内核转发，上网不受影响）
                 ↑ 伪造 ARP 应答
               本机(假装自己是网关) ←── 设备所有流量
                 └─ DNS 查询(53) → iptables 重定向 → LanCloud DNS → 命中 pan.lan → 返回你的 IP
```

- 设备端零设置、零感知：它以为自己一直在跟网关通信
- 未匹配的域名由 LanCloud 转发上游 DNS，**正常上网不受影响**
- 每 2 秒重播一次伪造 ARP，防止设备缓存被纠正

## 二、环境要求

| 项 | 要求 |
| --- | --- |
| 系统 | Linux（Ubuntu / Debian / 树莓派 / 软路由均可） |
| 权限 | root（ARP 欺骗与 iptables 都需要） |
| 依赖 | `scapy`、`iptables`、`ip`（iproute2） |
| LanCloud | 先启动 DNS 服务（管理面板 → DNS 服务，默认端口 53） |

> 为什么不做进 Windows 绿色版？Windows 上 ARP 欺骗需要安装 Npcap 驱动、极易被杀毒软件拦截，且没有内置 iptables，无法优雅转发。方案 C 定位为 Linux 进阶实验。

## 三、安装与使用

```bash
# 1. 安装依赖（Ubuntu/Debian）
sudo apt install -y iptables iproute2 python3-pip
pip3 install scapy

# 2. 环境体检（确认网卡/网关/DNS 服务都正常）
sudo python3 scripts/arp_hijack.py --check

# 3a. 接管全部发现设备（推荐）
sudo python3 scripts/arp_hijack.py --all --yes

# 3b. 只接管指定设备
sudo python3 scripts/arp_hijack.py --target 192.168.1.50

# 3c. 主动扫描网段并接管（设备没在 ARP 缓存时）
sudo python3 scripts/arp_hijack.py --all --cidr 192.168.1.0/24 --yes

# 4. 结束：Ctrl+C 自动恢复；或手动立即恢复
sudo python3 scripts/arp_hijack.py --restore
```

参数速查：

| 参数 | 作用 |
| --- | --- |
| `--check` | 环境体检（网卡/网关/DNS 探测/发现设备数） |
| `--all` | 接管全部已发现设备（自动排除网关与本机） |
| `--target IP` | 只接管指定 IP（可逗号分隔） |
| `--cidr 网段` | 主动 ARP 扫描该网段后接管 |
| `--dns-port N` | 本机 LanCloud DNS 端口（默认 53；若用 8053 需指定） |
| `--interval 秒` | ARP 重播间隔（默认 2 秒） |
| `--dry-run` | 只打印将执行的命令，不实际操作（教学/预览） |
| `--restore` | 立即恢复（清 iptables 规则 + 广播真实网关 MAC） |

## 四、验证是否生效

1. 在**另一台设备**（如手机）上打开浏览器访问 `http://pan.lan:8080` —— 应直达你的网盘，无需任何设置
2. 在 LanCloud 管理面板「劫持向导 → 查询日志」—— 应看到该设备的查询记录（IP 不是你的本机 IP）
3. 设备上 `nslookup pan.lan` 应返回你配置的 IP

## 五、重要注意事项

### 恢复机制（重要）
- **Ctrl+C 会自动恢复**：清除 iptables 规则、广播真实网关 MAC、关闭 IP 转发
- 设备 ARP 缓存最多几十秒内自动纠正，无需重启设备
- 万一脚本异常退出，手动执行：`sudo python3 scripts/arp_hijack.py --restore`

### 常见问题
| 现象 | 原因与处理 |
| --- | --- |
| 设备上不了网 | 检查 IP 转发是否开启（脚本会自动开）；Ctrl+C 恢复后重试 |
| 部分设备没被接管 | 该设备有静态 ARP 或已开 ARP 防护（交换机端口安全等），无法欺骗 |
| HTTPS 网站打不开/警告 | HTTPS 需要证书，见 README「HTTPS 与劫持」；HSTS 站点无法劫持 |
| 手机偶尔断网 | 路由器主动 ARP 通告纠正了设备，脚本每 2 秒重播会拉回来 |

### 法律边界（必读）
ARP 欺骗属于**网络中间人技术**，本脚本只允许在**你自己拥有或已获明确授权**的网络和设备上使用。
- 在中国，未经授权截获/劫持他人网络流量违反《网络安全法》和《刑法》第 285/286 条
- 用于钓鱼、盗号、窃取信息属于犯罪行为
- 本脚本**不包含**任何内容注入/伪造页面能力，仅接管 DNS 解析
- 公共 WiFi、公司网络、他人网络**一律禁止使用**
