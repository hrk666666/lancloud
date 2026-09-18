# -*- coding: utf-8 -*-
"""LanCloud 主服务：网盘 API + 管理 API + DNS 服务控制 + 静态页面"""
import mimetypes
import re
import socket
import uuid
from pathlib import Path

from fastapi import (Cookie, FastAPI, File, HTTPException, Query, Request,
                     UploadFile)
from fastapi.responses import (FileResponse, JSONResponse, Response,
                               StreamingResponse)
from fastapi.staticfiles import StaticFiles

from . import auth, config, shares, storage
from .dns_server import LanDNSServer

# 补充常见文件类型
for _ext, _mt in [(".md", "text/markdown"),
                  (".yml", "text/yaml"), (".yaml", "text/yaml"),
                  (".log", "text/plain"), (".sh", "text/plain"),
                  (".bat", "text/plain"), (".conf", "text/plain"),
                  (".ini", "text/plain"), (".m3u8", "application/vnd.apple.mpegurl")]:
    mimetypes.add_type(_mt, _ext)

BASE = Path(__file__).resolve().parent
STATIC_DIR = BASE / "static"
TEMPLATE_DIR = BASE / "templates"

app = FastAPI(title="LanCloud 局域网私有云网盘", docs_url=None, redoc_url=None)

# ---------------- 全局 DNS 服务单例 ----------------
_dns = LanDNSServer(
    get_domains=lambda: config.load_domains(),
    port=config.load_config().get("dns_port", 53),
    upstream=config.load_config().get("dns_upstream", "223.5.5.5"),
)


# ---------------- 依赖 ----------------
def _token_from(request: Request) -> str:
    return request.cookies.get("lc_session") or ""


def current_user(request: Request) -> str:
    u = auth.get_user(_token_from(request))
    if not u:
        raise HTTPException(status_code=401, detail="未登录或登录已过期")
    return u


def require_admin(request: Request) -> str:
    u = current_user(request)
    if not auth.is_admin(u):
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return u


def _err(e: Exception, status: int = 400):
    return JSONResponse({"error": str(e)}, status_code=status)


# ---------------- 局域网 IP 探测 ----------------
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


# ---------------- 启动 ----------------
@app.on_event("startup")
def startup():
    config.ensure_dirs()
    auth.ensure_admin()
    storage.ensure_user_dir(config.load_config()["admin_user"])
    cfg = config.load_config()
    if cfg.get("dns_enabled"):
        _dns.port = cfg.get("dns_port", 53)
        _dns.upstream = cfg.get("dns_upstream", "223.5.5.5")
        _dns.start()


# ---------------- 认证 ----------------
@app.post("/api/auth/register")
def api_register(body: dict):
    if not config.load_config().get("allow_register"):
        raise HTTPException(status_code=403, detail="暂未开放注册")
    u, err = auth.register(body.get("username", ""), body.get("password", ""))
    if err:
        raise HTTPException(status_code=400, detail=err)
    storage.ensure_user_dir(body["username"])
    return {"ok": True}


@app.post("/api/auth/login")
def api_login(body: dict, request: Request):
    u, err = auth.login(body.get("username", ""), body.get("password", ""))
    if err:
        raise HTTPException(status_code=401, detail=err)
    token = auth.create_session(body["username"])
    resp = JSONResponse({"ok": True, "username": body["username"]})
    resp.set_cookie("lc_session", token, max_age=7 * 86400, httponly=True,
                    samesite="lax")
    return resp


@app.post("/api/auth/logout")
def api_logout(request: Request):
    auth.logout(_token_from(request))
    resp = JSONResponse({"ok": True})
    resp.delete_cookie("lc_session")
    return resp


@app.get("/api/auth/me")
def api_me(user: str = Cookie(None, alias="lc_session")):
    username = auth.get_user(user or "")
    if not username:
        raise HTTPException(status_code=401, detail="未登录")
    total, n = storage.stat_usage(username)
    return {
        "username": username,
        "is_admin": auth.is_admin(username),
        "files": n,
        "size": total,
        "allow_register": config.load_config().get("allow_register", True),
    }


# ---------------- 文件系统 ----------------
@app.get("/api/fs/list")
def fs_list(path: str = "", user: str = Cookie(None, alias="lc_session")):
    username = auth.get_user(user or "")
    if not username:
        raise HTTPException(401, "未登录")
    try:
        return {"items": storage.list_dir(username, path)}
    except Exception as e:
        return _err(e)


@app.post("/api/fs/mkdir")
def fs_mkdir(body: dict, user: str = Cookie(None, alias="lc_session")):
    username = auth.get_user(user or "")
    if not username:
        raise HTTPException(401, "未登录")
    try:
        storage.mkdir(username, body.get("path", ""), body.get("name", ""))
        return {"ok": True}
    except Exception as e:
        return _err(e)


@app.post("/api/fs/upload")
async def fs_upload(path: str = Query(""), files: list[UploadFile] = File(...),
                    user: str = Cookie(None, alias="lc_session")):
    username = auth.get_user(user or "")
    if not username:
        raise HTTPException(401, "未登录")
    cfg = config.load_config()
    max_mb = cfg.get("max_upload_mb", 0)
    saved = []
    for f in files:
        limit = max_mb * 1024 * 1024 if max_mb > 0 else 0
        try:
            if limit > 0:
                dst = storage.save_upload(username, path, f.filename or "file",
                                          _LimitedReader(f.file, limit))
                if dst.stat().st_size > limit:
                    dst.unlink(missing_ok=True)
                    raise HTTPException(413, f"文件超过大小限制（{max_mb} MB）")
            else:
                dst = storage.save_upload(username, path, f.filename or "file", f.file)
        except HTTPException:
            raise
        except Exception:
            continue
        saved.append(dst.name)
    return {"ok": True, "saved": saved}


class _LimitedReader:
    """限制读取字节数，超出则抛异常"""

    def __init__(self, f, limit: int):
        self.f = f
        self.left = limit

    def read(self, n=-1):
        if self.left <= 0:
            raise HTTPException(413, "文件超过大小限制")
        data = self.f.read(min(n if n > 0 else 65536, self.left))
        self.left -= len(data)
        return data


@app.get("/api/fs/download")
def fs_download(path: str = "", inline: int = 0, user: str = Cookie(None, alias="lc_session"),
                request: Request = None):
    username = auth.get_user(user or "")
    if not username:
        raise HTTPException(401, "未登录")
    try:
        fpath = storage.get_path(username, path)
    except Exception as e:
        return _err(e)
    if fpath.is_dir():
        raise HTTPException(400, "不能下载目录")
    rng = request.headers.get("range") if request else None
    return _file_response(fpath, inline=bool(inline), range_header=rng)


def _file_response(fpath: Path, inline: bool = False, range_header: str = None):
    size = fpath.stat().st_size
    media = mimetypes.guess_type(fpath.name)[0] or "application/octet-stream"
    disp = "inline" if inline else "attachment"
    # 中文文件名做 RFC5987 编码
    fn = fpath.name.encode("utf-8").decode("latin-1")
    cd = f"{disp}; filename*=UTF-8''{fn}"
    rng = range_header
    if rng:
        m = re.fullmatch(r"bytes=(\d*)-(\d*)", rng.strip())
        if m:
            start = int(m.group(1)) if m.group(1) else 0
            end = int(m.group(2)) if m.group(2) else size - 1
            if start >= size:
                return Response(status_code=416,
                                headers={"Content-Range": f"bytes */{size}"})
            end = min(end, size - 1)
            length = end - start + 1
            f = open(fpath, "rb")
            f.seek(start)

            def gen():
                try:
                    remaining = length
                    while remaining > 0:
                        chunk = f.read(min(256 * 1024, remaining))
                        if not chunk:
                            break
                        remaining -= len(chunk)
                        yield chunk
                finally:
                    f.close()

            return StreamingResponse(
                gen(), status_code=206, media_type=media,
                headers={"Content-Range": f"bytes {start}-{end}/{size}",
                         "Accept-Ranges": "bytes", "Content-Length": str(length),
                         "Content-Disposition": cd})
    return FileResponse(fpath, media_type=media, headers={
        "Accept-Ranges": "bytes", "Content-Disposition": cd})


@app.post("/api/fs/delete")
def fs_delete(body: dict, user: str = Cookie(None, alias="lc_session")):
    username = auth.get_user(user or "")
    if not username:
        raise HTTPException(401, "未登录")
    try:
        storage.delete(username, body.get("path", ""))
        return {"ok": True}
    except Exception as e:
        return _err(e)


@app.post("/api/fs/rename")
def fs_rename(body: dict, user: str = Cookie(None, alias="lc_session")):
    username = auth.get_user(user or "")
    if not username:
        raise HTTPException(401, "未登录")
    try:
        storage.rename(username, body.get("path", ""), body.get("new_name", ""))
        return {"ok": True}
    except Exception as e:
        return _err(e)


@app.post("/api/fs/move")
def fs_move(body: dict, user: str = Cookie(None, alias="lc_session")):
    username = auth.get_user(user or "")
    if not username:
        raise HTTPException(401, "未登录")
    try:
        storage.move(username, body.get("path", ""), body.get("dest", ""))
        return {"ok": True}
    except Exception as e:
        return _err(e)


@app.get("/api/fs/search")
def fs_search(q: str = "", path: str = "", user: str = Cookie(None, alias="lc_session")):
    username = auth.get_user(user or "")
    if not username:
        raise HTTPException(401, "未登录")
    try:
        return {"items": storage.search(username, q, path)}
    except Exception as e:
        return _err(e)


# ---------------- 分享 ----------------
@app.post("/api/share")
def share_create(body: dict, user: str = Cookie(None, alias="lc_session")):
    username = auth.get_user(user or "")
    if not username:
        raise HTTPException(401, "未登录")
    try:
        storage.get_path(username, body.get("path", ""))
        rec = shares.create(username, body.get("path", ""))
        return rec
    except Exception as e:
        return _err(e)


@app.get("/api/share/list")
def share_list(user: str = Cookie(None, alias="lc_session")):
    username = auth.get_user(user or "")
    if not username:
        raise HTTPException(401, "未登录")
    return {"items": shares.list_shares(username)}


@app.delete("/api/share/{token}")
def share_delete(token: str, user: str = Cookie(None, alias="lc_session")):
    username = auth.get_user(user or "")
    if not username:
        raise HTTPException(401, "未登录")
    rec = shares.get(token)
    if rec and rec["user"] == username:
        shares.delete(token)
    return {"ok": True}


@app.get("/api/s/{token}/info")
def share_info(token: str):
    rec = shares.get(token)
    if not rec:
        raise HTTPException(404, "分享不存在或已失效")
    try:
        p = storage.get_path(rec["user"], rec["path"])
    except Exception:
        raise HTTPException(404, "分享的文件不存在")
    return {"name": p.name, "is_dir": p.is_dir(), "path": rec["path"]}


@app.get("/api/s/{token}/list")
def share_list_public(token: str, path: str = ""):
    rec = shares.get(token)
    if not rec:
        raise HTTPException(404, "分享不存在或已失效")
    root = rec["path"]
    rel = (root + "/" + path).strip("/") if path else root
    try:
        p = storage.get_path(rec["user"], rel)
    except Exception:
        raise HTTPException(404, "路径不存在")
    if p.is_dir():
        items = storage.list_dir(rec["user"], rel)
        for it in items:
            it["share_path"] = it["path"].replace(root + "/", "", 1) if root else it["path"]
        return {"is_dir": True, "items": items, "current": rel.replace(root, "", 1).strip("/")}
    return {"is_dir": False, "file": {"name": p.name, "share_path": ""}}


@app.get("/api/s/{token}/download")
def share_download_public(token: str, path: str = "", request: Request = None):
    rec = shares.get(token)
    if not rec:
        raise HTTPException(404, "分享不存在或已失效")
    root = rec["path"]
    rel = (root + "/" + path).strip("/") if path else root
    try:
        p = storage.get_path(rec["user"], rel)
    except Exception:
        raise HTTPException(404, "文件不存在")
    if p.is_dir():
        raise HTTPException(400, "不能直接下载目录")
    rng = request.headers.get("range") if request else None
    return _file_response(p, inline=False, range_header=rng)


# ---------------- 回收站 ----------------
@app.get("/api/trash")
def trash_list(user: str = Cookie(None, alias="lc_session")):
    username = auth.get_user(user or "")
    if not username:
        raise HTTPException(401, "未登录")
    return {"items": storage.list_trash(username)}


@app.post("/api/trash/restore")
def trash_restore(body: dict, user: str = Cookie(None, alias="lc_session")):
    username = auth.get_user(user or "")
    if not username:
        raise HTTPException(401, "未登录")
    try:
        storage.restore(username, body.get("trash_name", ""))
        return {"ok": True}
    except Exception as e:
        return _err(e)


@app.post("/api/trash/empty")
def trash_empty(user: str = Cookie(None, alias="lc_session")):
    username = auth.get_user(user or "")
    if not username:
        raise HTTPException(401, "未登录")
    storage.empty_trash(username)
    return {"ok": True}


@app.post("/api/trash/delete-forever")
def trash_delete_forever(body: dict, user: str = Cookie(None, alias="lc_session")):
    username = auth.get_user(user or "")
    if not username:
        raise HTTPException(401, "未登录")
    try:
        storage.purge_trash_item(username, body.get("trash_name", ""))
        return {"ok": True}
    except Exception as e:
        return _err(e)


# ---------------- 管理：概览 / 配置 / DNS ----------------
@app.get("/api/admin/overview")
def admin_overview(user: str = Cookie(None, alias="lc_session")):
    require_admin_ctx(user)
    cfg = config.load_config()
    total_size, total_files = 0, 0
    files_root = config.DATA_DIR / "files"
    n_users = 0
    if files_root.exists():
        for d in files_root.iterdir():
            if d.is_dir():
                n_users += 1
                t, n = storage.stat_usage(d.name)
                total_size += t
                total_files += n
    return {
        "users": n_users,
        "files": total_files,
        "total_size": total_size,
        "web_port": cfg.get("web_port", 8080),
        "dns_port": cfg.get("dns_port", 53),
        "dns_enabled": cfg.get("dns_enabled", True),
        "dns_upstream": cfg.get("dns_upstream", "223.5.5.5"),
        "allow_register": cfg.get("allow_register", True),
        "ips": lan_ips(),
        "dns": {"running": _dns.running, "port": _dns.port,
                "error": _dns.error},
    }


def require_admin_ctx(user):
    username = auth.get_user(user or "")
    if not username:
        raise HTTPException(401, "未登录")
    if not auth.is_admin(username):
        raise HTTPException(403, "需要管理员权限")
    return username


@app.get("/api/dns/status")
def dns_status(user: str = Cookie(None, alias="lc_session")):
    require_admin_ctx(user)
    return {"running": _dns.running, "port": _dns.port, "error": _dns.error}


@app.post("/api/dns/start")
def dns_start(user: str = Cookie(None, alias="lc_session")):
    require_admin_ctx(user)
    ok, msg = _dns.start()
    return {"ok": ok, "message": msg}


@app.post("/api/dns/stop")
def dns_stop(user: str = Cookie(None, alias="lc_session")):
    require_admin_ctx(user)
    ok, msg = _dns.stop()
    return {"ok": ok, "message": msg}


_DOMAIN_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9.\-]{0,190}[a-zA-Z0-9]$")
_IP_RE = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")


@app.get("/api/dns/domains")
def dns_domains(user: str = Cookie(None, alias="lc_session")):
    require_admin_ctx(user)
    return {"items": config.load_domains()}


@app.post("/api/dns/domains")
def dns_domains_add(body: dict, user: str = Cookie(None, alias="lc_session")):
    require_admin_ctx(user)
    domain = (body.get("domain") or "").strip().lower().rstrip(".")
    ip = (body.get("ip") or "").strip()
    if not _DOMAIN_RE.match(domain):
        raise HTTPException(400, "域名格式不正确（示例：pan.lan）")
    if not _IP_RE.match(ip):
        raise HTTPException(400, "IP 格式不正确（示例：192.168.1.100）")
    items = config.load_domains()
    for d in items:
        if d["domain"] == domain:
            raise HTTPException(400, "该域名已存在映射")
    items.append({
        "id": uuid.uuid4().hex[:8],
        "domain": domain,
        "ip": ip,
        "enabled": True,
        "note": (body.get("note") or "").strip(),
        "created": int(__import__("time").time()),
    })
    config.save_domains(items)
    return {"ok": True, "items": items}


@app.put("/api/dns/domains/{domain_id}")
def dns_domains_update(domain_id: str, body: dict, user: str = Cookie(None, alias="lc_session")):
    require_admin_ctx(user)
    items = config.load_domains()
    for d in items:
        if d["id"] == domain_id:
            if "enabled" in body:
                d["enabled"] = bool(body["enabled"])
            if "ip" in body and body["ip"]:
                if not _IP_RE.match(body["ip"].strip()):
                    raise HTTPException(400, "IP 格式不正确")
                d["ip"] = body["ip"].strip()
            if "note" in body:
                d["note"] = str(body["note"]).strip()
            config.save_domains(items)
            return {"ok": True, "items": items}
    raise HTTPException(404, "映射不存在")


@app.delete("/api/dns/domains/{domain_id}")
def dns_domains_delete(domain_id: str, user: str = Cookie(None, alias="lc_session")):
    require_admin_ctx(user)
    items = config.load_domains()
    items = [d for d in items if d["id"] != domain_id]
    config.save_domains(items)
    return {"ok": True, "items": items}


# ---------------- 静态页面 ----------------
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def index():
    return FileResponse(TEMPLATE_DIR / "index.html")


@app.get("/admin")
def admin_page():
    return FileResponse(TEMPLATE_DIR / "admin.html")


@app.get("/share.html")
def share_page():
    return FileResponse(TEMPLATE_DIR / "share.html")


@app.get("/s/{token}")
def share_page_route(token: str):
    return FileResponse(TEMPLATE_DIR / "share.html")
