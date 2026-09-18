# LanCloud · 局域网私有云网盘

一个**中文、美观、开箱即用**的局域网私有云项目：自带完整的网盘功能（上传 / 下载 / 预览 / 分享 / 回收站 / 多用户），并提供**域名定向（DNS 劫持）管理界面与新手教程**——让局域网内其他设备**零配置、免证书**地通过一个好记的域名（如 `pan.lan`）访问你的网盘。

> 数据只存在你自己的设备上，不上传任何第三方服务器。

---

## ✨ 功能特性

### 网盘（私有云）
- ✅ 文件上传（支持拖拽、多文件、进度条）、下载、在线预览
- ✅ 图片 / 视频 / 音频 / 文本 / PDF 在线预览（视频支持拖动进度）
- ✅ 新建文件夹、重命名、移动、搜索
- ✅ 分享链接：局域网内任何人打开即访问，无需登录
- ✅ 回收站：误删可恢复，支持彻底删除 / 一键清空
- ✅ 多用户：注册登录，每位用户独立目录
- ✅ 存储占用统计、中文界面、移动端自适应

### 域名定向（"劫持"）与教程
- ✅ 内置 DNS 服务：把任意域名解析到你指定的 IP
- ✅ 管理面板可视化配置：域名 → IP，一键启停、启用开关
- ✅ 未匹配的域名自动转发上游 DNS，**不影响正常上网**
- ✅ 内置图文教程：路由器 / 设备手动 / 域名组合三种接入方式
- ✅ 明确标注 HTTPS 限制与法律边界（见下方"重要说明"）

### 部署
- ✅ Python 一键启动（Windows / macOS / Linux 通用）
- ✅ 可选的 Docker 进阶方案：集成 **Alist**（高性能网盘）+ **AdGuard Home**（DNS 过滤）
- ✅ systemd 开机自启示例

---

## 🚀 快速开始

### 环境要求
- Python 3.9+（[python.org](https://www.python.org/downloads/) 下载，Windows 安装时勾选 "Add to PATH"）

### Windows
双击 `start.bat`，或命令行运行：

```bat
start.bat
```

### macOS / Linux

```bash
./start.sh
```

### 首次使用
1. 浏览器打开终端输出的地址，如 `http://127.0.0.1:8080`
2. 使用默认管理员登录：**admin / admin123**
3. 建议尽快修改密码：编辑 `data/config.json` 中 `admin_password`，保存后重启

> 局域网内其他设备访问：`http://你的IP:8080`（启动时终端会打印所有可用的局域网地址）

---

## 📖 使用教程

### 网盘基础操作
| 操作 | 方法 |
| --- | --- |
| 上传 | 右上角「上传」按钮，或直接把文件拖进页面 |
| 预览 | 双击文件（图片/视频/音频/文本/PDF 均可） |
| 下载 | 悬停文件卡片，点击下载图标；列表视图点击「下载」 |
| 分享 | 点击分享图标 → 生成链接 → 复制给局域网内任何人 |
| 移动 | 列表视图点击「移动」，选择目标文件夹 |
| 删除 | 点击删除 → 进入回收站（可恢复） |

### 域名定向（让 pan.lan 直达你的网盘）
详细图文教程见 [docs/域名定向教程.md](docs/域名定向教程.md) 或登录后的「管理面板 → 接入教程」。

三步速览：
1. 登录 → 管理面板 → 域名定向，添加映射：`pan.lan` → 你的局域网 IP
2. 在路由器「DHCP 服务器 → 首选 DNS」填你的 IP（或单台设备手动设置 DNS）
3. 其他设备打开 `http://pan.lan:8080` 即可直达网盘，全程无需任何配置

---

## 🐳 进阶：Docker 集成高分开源项目

LanCloud 自带轻量网盘与 DNS，不开 Docker 也能完整使用。若想要"更强网盘 + 广告拦截"：

```bash
docker compose up -d
```

- **Alist**（`http://IP:5244`）：高性能网盘，支持本地存储 / WebDAV / 聚合网盘
- **AdGuard Home**（`http://IP:3000`）：DNS 过滤 + 广告拦截

> 注意：AdGuard Home 与 LanCloud DNS 都占用 53 端口，请二选一使用（或在 AdGuard 中改端口）。

---

## 📁 项目结构

```
lancloud/
├── run.py                 # 启动入口
├── start.sh / start.bat   # 一键启动
├── requirements.txt       # Python 依赖
├── docker-compose.yml     # 进阶方案（Alist + AdGuard Home）
├── lancloud/
│   ├── server.py          # Web API（网盘 + 管理 + DNS 控制）
│   ├── storage.py         # 文件存储 / 回收站
│   ├── auth.py            # 用户与会话
│   ├── shares.py          # 分享链接
│   ├── dns_server.py      # 局域网 DNS 服务
│   ├── config.py          # 配置持久化
│   ├── templates/         # 页面（网盘 / 管理面板 / 分享）
│   └── static/            # 前端（CSS / JS / 教程图）
├── docs/                  # 教程文档
├── scripts/               # 安装脚本 / systemd 服务
└── data/                  # 运行数据（自动生成，不入库）
```

---

## 🧰 技术栈与开源组件

| 组件 | 用途 | 说明 |
| --- | --- | --- |
| [FastAPI](https://github.com/tiangolo/fastapi) | Web 框架 | 高星开源 |
| [Uvicorn](https://github.com/encode/uvicorn) | ASGI 服务器 | 高星开源 |
| [dnslib](https://github.com/paulc/dnslib) | DNS 协议库 | 开源 |
| [Alist](https://github.com/alist-org/alist) | 高性能网盘（可选） | 高星开源 |
| [AdGuard Home](https://github.com/AdguardTeam/AdGuardHome) | DNS 过滤（可选） | 高星开源 |

本项目代码基于 **MIT License** 开源。

---

## ⚠️ 重要说明（必读）

1. **HTTPS 限制**：DNS 只能决定"域名解析到哪个 IP"。目标站点是 HTTPS 时，浏览器会做证书校验并提示"证书不受信任"——除非每台设备手动信任你的证书。**静默劫持 HTTPS 网站做不到**，这是 TLS 加密的设计保证。
2. **合法边界**：域名定向/劫持是双用途技术，**只应在你自己拥有或已获授权的网络和设备上使用**。在中国，未经授权截获 / 劫持他人网络流量违反《网络安全法》和《刑法》第 285/286 条，用于钓鱼盗号属于犯罪。本项目不提供任何针对第三方网站的钓鱼能力，请合理使用。
3. **DNS 端口**：53 端口是特权端口。Windows 需以管理员运行；Linux/macOS 需 `sudo` 启动或为 Python 设置 `setcap cap_net_bind_service=+ep`。若启动失败，网盘功能不受影响。
4. **备份**：所有数据在 `data/` 目录，备份时整体复制即可。

---

## ❓ 常见问题

见 [docs/常见问题.md](docs/常见问题.md)。

- 局域网设备打不开网盘？→ 确认同一 WiFi / 防火墙放行 Web 端口
- DNS 启动失败？→ 端口被占用或权限不足，见上方"重要说明"
- 想改端口？→ 编辑 `data/config.json` 或 `LANCLOUD_PORT=9000 python run.py`

---

## 📄 License

[MIT](LICENSE)

LanCloud © 2026 · 用爱发电的开源项目，欢迎 Star ⭐
