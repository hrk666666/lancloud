# -*- coding: utf-8 -*-
"""LanCloud 主服务：网盘 API + 管理 API + DNS/HTTPS 控制 + 静态页面"""
import mimetypes
import re
import socket
import time
import uuid
from pathlib import Path

from fastapi import (BackgroundTasks, Cookie, FastAPI, File, HTTPException,
                     Query, Request, UploadFile)
from fastapi.responses import (FileResponse, JSONResponse, Response,
                               StreamingResponse)
from fastapi.staticfiles import StaticFiles

from . import auth, certs, config, mounts, shares, storage

# 补充常见文件类型
for _ext, _mt in [(".md", "text/markdown"),
                  (".yml", "text/yaml"), (".yaml", "text/yaml"),
                  (".log", "text/plain"), (".sh", "text/plain"),
                  (".bat", "text/plain"), (".conf", "text/plain"),
                  (".ini", "text/plain"),
                  (".m3u8", "application/vnd.apple.mpegurl")]:
    mimetypes.add_type(_mt, _ext)

BASE = Path(__file__).resolve().parent
STATIC_DIR = BASE / "static"
TEMPLATE_DIR = BASE / "templates"

app = FastAPI(title="LanCloud 局域网私有云网盘", docs_url=None, redoc_url=None)

# ---------------- 全局 DNS 服务单例 ----------------
def _make_dns():
    from .dns_server import LanDNSServer
    return LanDNSServer(
        get_domains=lambda: config.load_domains(),
        port=config.load_config().get("dns_port", 53),
        upstream=config.load_config().get("dns_upstream", "223.5.5.5"),
    )


_dns = _make_dns()


# ---------------- 依赖 ----------------
def _token_from(request: Request) -> str:
    return request.cookies.get("lc_session") or ""


def _user_or_none(request: Request):
    return auth.get_user(_token_from(request))


def current_user(request: Request) -> str:
    u = _user_or_none(request)
    if not u:
        raise HTTPException(status_code=401, detail="未登录或登录已过期")
    return u


def require_admin(request: Request) -> str:
    u = current_user(request)
    if not auth.is_admin(u):
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return u


def _err(e: Exception, status: int = 400):
    if isinstance(e, storage.QuotaExceeded):
        return JSONResponse({"error": str(e)}, status_code=413)
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


def _quota_bytes(username: str) -> int:
    info = auth.get_user_info(username)
    q = (info or {}).get("quota_mb") or 0
    return q * 1024 * 1024 if q > 0 else 0


# ---------------- 启动 ----------------
@app.on_event("startup")
def startup():
    config.ensure_dirs()
    auth.ensure_admin()
    for u in auth.admin_list_users():
        storage.ensure_user_dir(u["username"])
    cfg = config.load_config()
    _dns.port = cfg.get("dns_port", 53)
    _dns.upstream = cfg.get("dns_upstream", "223.5.5.5")
    if cfg.get("dns_enabled"):
        _dns.start()


# ---------------- 认证 ----------------
@app.post("/api/auth/register")
def api_register(body: dict):
    cfg = config.load_config()
    if not cfg.get("allow_register"):
        raise HTTPException(status_code=403, detail="管理员已关闭注册")
    u, err = auth.register(body.get("username", ""), body.get("password", ""))
    if err:
        raise HTTPException(status_code=400, detail=err)
    storage.ensure_user_dir(body["username"])
    return {"ok": True}


@app.post("/api/auth/login")
def api_login(body: dict):
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
    info = auth.get_user_info(username)
    return {
        "username": username,
        "is_admin": info["is_admin"],
        "quota_mb": info["quota_mb"],
        "can_share": info["can_share"],
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
    quota = _quota_bytes(username)
    saved = []
    for f in files:
        try:
            dst = storage.save_upload(username, path, f.filename or "file",
                                      f.file, quota)
            if max_mb > 0 and dst.stat().st_size > max_mb * 1024 * 1024:
                dst.unlink(missing_ok=True)
                raise HTTPException(413, f"文件超过大小限制（{max_mb} MB）")
        except HTTPException:
            raise
        except storage.QuotaExceeded as qe:
            raise HTTPException(413, str(qe))
        except Exception:
            continue
        saved.append(dst.name)
    return {"ok": True, "saved": saved}


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


@app.get("/api/fs/zip")
def fs_zip(path: str = "", user: str = Cookie(None, alias="lc_session"),
           background: BackgroundTasks = None):
    username = auth.get_user(user or "")
    if not username:
        raise HTTPException(401, "未登录")
    try:
        zpath = storage.make_zip(username, path)
        name = (path.split("/")[-1] or "files") + ".zip"
    except Exception as e:
        return _err(e)
    headers = {"Content-Disposition":
               f"attachment; filename*=UTF-8''{name.encode('utf-8').decode('latin-1')}"}
    if background:
        background.add_task(lambda: zpath.unlink(missing_ok=True))
    return FileResponse(zpath, media_type="application/zip", headers=headers)


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


@app.get("/api/fs/read")
def fs_read(path: str = "", user: str = Cookie(None, alias="lc_session")):
    username = auth.get_user(user or "")
    if not username:
        raise HTTPException(401, "未登录")
    try:
        return {"content": storage.read_text(username, path)}
    except Exception as e:
        return _err(e)


@app.put("/api/fs/edit")
def fs_edit(body: dict, user: str = Cookie(None, alias="lc_session")):
    username = auth.get_user(user or "")
    if not username:
        raise HTTPException(401, "未登录")
    try:
        storage.write_text(username, body.get("path", ""), body.get("content", ""))
        return {"ok": True}
    except Exception as e:
        return _err(e)


# ---------------- 分享 ----------------
@app.post("/api/share")
def share_create(body: dict, user: str = Cookie(None, alias="lc_session")):
    username = auth.get_user(user or "")
    if not username:
        raise HTTPException(401, "未登录")
    if not auth.can_share(username):
        raise HTTPException(403, "管理员已禁止你创建分享")
    try:
        storage.get_path(username, body.get("path", ""))
        rec = shares.create(username, body.get("path", ""),
                            require_login=bool(body.get("require_login")),
                            expire_days=int(body.get("expire_days") or 0))
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


def _share_guard(token: str, request: Request):
    """分享公共访问守卫：过期 / 强制登录校验"""
    rec = shares.get(token)
    if not rec:
        raise HTTPException(404, "分享不存在或已失效")
    if rec.get("require_login") and not _user_or_none(request):
        raise HTTPException(401, "该分享需要登录后访问")
    return rec


@app.get("/api/s/{token}/info")
def share_info(token: str, request: Request):
    rec = _share_guard(token, request)
    try:
        p = storage.get_path(rec["user"], rec["path"])
    except Exception:
        raise HTTPException(404, "分享的文件不存在")
    return {"name": p.name, "is_dir": p.is_dir(), "path": rec["path"],
            "require_login": rec.get("require_login", False)}


@app.get("/api/s/{token}/list")
def share_list_public(token: str, path: str = "", request: Request = None):
    rec = _share_guard(token, request)
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
        return {"is_dir": True, "items": items,
                "current": rel.replace(root, "", 1).strip("/")}
    return {"is_dir": False, "file": {"name": p.name, "share_path": ""}}


@app.get("/api/s/{token}/download")
def share_download_public(token: str, path: str = "", request: Request = None):
    rec = _share_guard(token, request)
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


# ---------------- 外部文件夹挂载 ----------------
@app.get("/api/mounts")
def mounts_list(user: str = Cookie(None, alias="lc_session")):
    username = auth.get_user(user or "")
    if not username:
        raise HTTPException(401, "未登录")
    if auth.is_admin(username):
        return {"items": mounts.list_mounts(public=False)}
    return {"items": mounts.list_mounts(public=True)}


@app.post("/api/mounts")
def mounts_add(body: dict, user: str = Cookie(None, alias="lc_session")):
    require_admin_from_cookie(user)
    try:
        m = mounts.add_mount(body.get("name", ""), body.get("path", ""),
                             readonly=body.get("readonly", True))
        return {"ok": True, "mount": m}
    except Exception as e:
        return _err(e)


@app.put("/api/mounts/{mount_id}")
def mounts_update(mount_id: str, body: dict, user: str = Cookie(None, alias="lc_session")):
    require_admin_from_cookie(user)
    try:
        m = mounts.update_mount(mount_id, **body)
        return {"ok": True, "mount": m}
    except Exception as e:
        return _err(e)


@app.delete("/api/mounts/{mount_id}")
def mounts_delete(mount_id: str, user: str = Cookie(None, alias="lc_session")):
    require_admin_from_cookie(user)
    mounts.delete_mount(mount_id)
    return {"ok": True}


@app.get("/api/mounts/{mount_id}/browse")
def mounts_browse(mount_id: str, path: str = "", user: str = Cookie(None, alias="lc_session")):
    username = auth.get_user(user or "")
    if not username:
        raise HTTPException(401, "未登录")
    try:
        return {"items": mounts.browse(mount_id, path)}
    except Exception as e:
        return _err(e)


@app.get("/api/mounts/{mount_id}/download")
def mounts_download(mount_id: str, path: str = "", inline: int = 0,
                    user: str = Cookie(None, alias="lc_session"),
                    request: Request = None):
    username = auth.get_user(user or "")
    if not username:
        raise HTTPException(401, "未登录")
    try:
        fpath = mounts.resolve_file(mount_id, path)
    except Exception as e:
        return _err(e)
    rng = request.headers.get("range") if request else None
    return _file_response(fpath, inline=bool(inline), range_header=rng)


def require_admin_from_cookie(user: str):
    username = auth.get_user(user or "")
    if not username:
        raise HTTPException(401, "未登录")
    if not auth.is_admin(username):
        raise HTTPException(403, "需要管理员权限")
    return username


# ---------------- 管理：用户 ----------------
@app.get("/api/admin/users")
def admin_users(user: str = Cookie(None, alias="lc_session")):
    require_admin_from_cookie(user)
    items = auth.admin_list_users()
    for it in items:
        total, n = storage.stat_usage(it["username"])
        it["used"] = total
        it["file_count"] = n
    return {"items": items}


@app.post("/api/admin/users")
def admin_user_create(body: dict, user: str = Cookie(None, alias="lc_session")):
    require_admin_from_cookie(user)
    u, err = auth.admin_create_user(
        body.get("username", ""), body.get("password", ""),
        quota_mb=body.get("quota_mb"), is_admin=bool(body.get("is_admin")),
        can_share=body.get("can_share", True),
        disabled=bool(body.get("disabled")))
    if err:
        raise HTTPException(400, detail=err)
    storage.ensure_user_dir(body["username"])
    return {"ok": True}


@app.post("/api/admin/users/batch")
def admin_user_batch(body: dict, user: str = Cookie(None, alias="lc_session")):
    require_admin_from_cookie(user)
    lines = (body.get("lines") or "").strip().splitlines()
    results = []
    for line in lines:
        parts = line.replace("，", ",").split()
        if len(parts) < 2:
            continue
        username, password = parts[0], parts[1]
        quota = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None
        u, err = auth.admin_create_user(username, password, quota_mb=quota)
        if err:
            results.append({"username": username, "ok": False, "error": err})
        else:
            storage.ensure_user_dir(username)
            results.append({"username": username, "ok": True, "error": None})
    return {"ok": True, "results": results}


@app.put("/api/admin/users/{username}")
def admin_user_update(username: str, body: dict,
                      user: str = Cookie(None, alias="lc_session")):
    require_admin_from_cookie(user)
    err = auth.admin_update_user(username, **body)
    if err:
        raise HTTPException(400, detail=err)
    return {"ok": True}


@app.post("/api/admin/users/{username}/reset-password")
def admin_user_reset(username: str, body: dict,
                     user: str = Cookie(None, alias="lc_session")):
    require_admin_from_cookie(user)
    err = auth.admin_reset_password(username, body.get("password", ""))
    if err:
        raise HTTPException(400, detail=err)
    return {"ok": True}


@app.delete("/api/admin/users/{username}")
def admin_user_delete(username: str, user: str = Cookie(None, alias="lc_session")):
    require_admin_from_cookie(user)
    err = auth.admin_delete_user(username)
    if err:
        raise HTTPException(400, detail=err)
    # 清理用户文件目录
    import shutil
    shutil.rmtree(storage.user_root(username), ignore_errors=True)
    shutil.rmtree(storage.trash_root(username), ignore_errors=True)
    return {"ok": True}


# ---------------- 管理：概览 / 配置 / DNS / HTTPS / 诊断 ----------------
@app.get("/api/admin/overview")
def admin_overview(user: str = Cookie(None, alias="lc_session")):
    require_admin_from_cookie(user)
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
        "default_quota_mb": cfg.get("default_quota_mb", 0),
        "max_upload_mb": cfg.get("max_upload_mb", 0),
        "https_enabled": cfg.get("https_enabled", False),
        "https_port": cfg.get("https_port", 8443),
        "mounts": len(config.load_mounts()),
        "ips": lan_ips(),
        "dns": {"running": _dns.running, "port": _dns.port, "error": _dns.error},
    }


@app.get("/api/dns/status")
def dns_status(user: str = Cookie(None, alias="lc_session")):
    require_admin_from_cookie(user)
    return {"running": _dns.running, "port": _dns.port, "error": _dns.error}


@app.post("/api/dns/start")
def dns_start(user: str = Cookie(None, alias="lc_session")):
    require_admin_from_cookie(user)
    ok, msg = _dns.start()
    return {"ok": ok, "message": msg}


@app.post("/api/dns/stop")
def dns_stop(user: str = Cookie(None, alias="lc_session")):
    require_admin_from_cookie(user)
    ok, msg = _dns.stop()
    return {"ok": ok, "message": msg}


@app.get("/api/dns/log")
def dns_log(user: str = Cookie(None, alias="lc_session")):
    require_admin_from_cookie(user)
    return {"items": list(_dns.log)}


_DOMAIN_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9.\-]{0,190}[a-zA-Z0-9]$")
_IP_RE = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")


@app.get("/api/dns/domains")
def dns_domains(user: str = Cookie(None, alias="lc_session")):
    require_admin_from_cookie(user)
    return {"items": config.load_domains()}


@app.post("/api/dns/domains")
def dns_domains_add(body: dict, user: str = Cookie(None, alias="lc_session")):
    require_admin_from_cookie(user)
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
        "created": int(time.time()),
    })
    config.save_domains(items)
    return {"ok": True, "items": items}


@app.put("/api/dns/domains/{domain_id}")
def dns_domains_update(domain_id: str, body: dict,
                       user: str = Cookie(None, alias="lc_session")):
    require_admin_from_cookie(user)
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
    require_admin_from_cookie(user)
    items = config.load_domains()
    items = [d for d in items if d["id"] != domain_id]
    config.save_domains(items)
    return {"ok": True, "items": items}


# ---------------- HTTPS ----------------
@app.get("/api/https/status")
def https_status(user: str = Cookie(None, alias="lc_session")):
    require_admin_from_cookie(user)
    cfg = config.load_config()
    ca_ok = (config.DATA_DIR / "certs" / "ca.crt").exists()
    return {"enabled": cfg.get("https_enabled", False),
            "port": cfg.get("https_port", 8443), "ca_ready": ca_ok}


@app.put("/api/admin/config")
def admin_config(body: dict, user: str = Cookie(None, alias="lc_session")):
    """修改部分全局配置（开放注册 / 默认配额 / 单文件限制 / 上游 DNS）"""
    require_admin_from_cookie(user)
    cfg = config.load_config()
    if "allow_register" in body:
        cfg["allow_register"] = bool(body["allow_register"])
    if "default_quota_mb" in body:
        cfg["default_quota_mb"] = max(0, int(body["default_quota_mb"] or 0))
    if "max_upload_mb" in body:
        cfg["max_upload_mb"] = max(0, int(body["max_upload_mb"] or 0))
    if "dns_upstream" in body and str(body["dns_upstream"]).strip():
        cfg["dns_upstream"] = str(body["dns_upstream"]).strip()
        _dns.upstream = cfg["dns_upstream"]
    config.save_config(cfg)
    return {"ok": True}


@app.post("/api/https/set")
def https_set(body: dict, user: str = Cookie(None, alias="lc_session")):
    require_admin_from_cookie(user)
    cfg = config.load_config()
    cfg["https_enabled"] = bool(body.get("enabled", False))
    if body.get("port"):
        cfg["https_port"] = int(body["port"])
    config.save_config(cfg)
    return {"ok": True, "message": "已保存，重启 LanCloud 后生效"}


@app.get("/api/ca/download")
def ca_download(user: str = Cookie(None, alias="lc_session")):
    require_admin_from_cookie(user)
    ca = config.DATA_DIR / "certs" / "ca.crt"
    if not ca.exists():
        certs.ensure_certs([], lan_ips())
    return FileResponse(ca, media_type="application/x-x509-ca-cert",
                        filename="LanCloud-CA.crt")


# ---------------- 诊断 ----------------
@app.get("/api/diag")
def diag(user: str = Cookie(None, alias="lc_session")):
    require_admin_from_cookie(user)
    cfg = config.load_config()
    ips = lan_ips()
    out = {
        "web": {"port": cfg.get("web_port"), "running": True},
        "dns": {"running": _dns.running, "port": _dns.port, "error": _dns.error},
        "ips": ips,
        "domains": config.load_domains(),
        "self_tests": [],
        "firewall_tips": _firewall_tips(cfg),
    }
    # 自测：向本机 DNS 发查询，验证映射是否生效
    if _dns.running:
        for d in config.load_domains():
            if not d.get("enabled", True):
                continue
            ok, detail = _self_query(d["domain"], _dns.port)
            out["self_tests"].append({
                "domain": d["domain"], "expect": d["ip"],
                "ok": ok, "detail": detail,
            })
    else:
        out["self_tests"].append({"domain": None, "expect": None,
                                  "ok": False,
                                  "detail": "DNS 服务未运行：" + str(_dns.error)})
    return out


def _firewall_tips(cfg: dict):
    import platform
    sysname = platform.system()
    tips = []
    for p in (cfg.get("web_port"), cfg.get("dns_port")):
        if sysname == "Windows":
            tips.append(f"Windows 防火墙放行端口 {p}："
                        f"netsh advfirewall firewall add rule name=\"LanCloud-{p}\" "
                        f"dir=in action=allow protocol=TCP localport={p}")
        else:
            tips.append(f"Linux 放行端口 {p}：sudo ufw allow {p}/tcp")
    return tips


def _self_query(domain: str, port: int):
    """向本机 DNS 服务发送 A 记录查询，验证劫持是否生效"""
    try:
        from dnslib import QTYPE as _QT, DNSRecord as _DR
        q = _DR.question(domain, qtype="A")
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(2.5)
        s.sendto(q.pack(), ("127.0.0.1", port))
        data, _ = s.recvfrom(4096)
        s.close()
        ans = [str(rr.rdata) for rr in _DR.parse(data).rr if rr.rtype == _QT.A]
        return (True, "返回 " + ", ".join(ans)) if ans else (False, "无 A 记录返回")
    except Exception as e:
        return False, f"查询失败：{e}"


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


# ---------------- 文件响应（含 Range） ----------------
def _file_response(fpath: Path, inline: bool = False, range_header: str = None):
    size = fpath.stat().st_size
    media = mimetypes.guess_type(fpath.name)[0] or "application/octet-stream"
    disp = "inline" if inline else "attachment"
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
