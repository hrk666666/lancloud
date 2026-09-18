# -*- coding: utf-8 -*-
"""用户文件存储：目录浏览 / 上传 / 下载 / 重命名 / 移动 / 回收站 / 打包"""
import json
import os
import re
import shutil
import threading
import time
import zipfile
from pathlib import Path

from . import config

TRASH_INDEX = config.DATA_DIR / "trash_index.json"
_lock = threading.Lock()

# 可在线编辑的文本类型
EDITABLE_EXT = {"txt", "md", "json", "js", "py", "html", "css", "xml", "yml",
                "yaml", "log", "ini", "conf", "sh", "bat", "c", "cpp", "h",
                "java", "go", "rs", "csv", "sql", "toml", "env"}


class QuotaExceeded(Exception):
    pass


def user_root(username: str) -> Path:
    return config.DATA_DIR / "files" / username


def trash_root(username: str) -> Path:
    return config.DATA_DIR / "trash" / username


def ensure_user_dir(username: str):
    user_root(username).mkdir(parents=True, exist_ok=True)
    trash_root(username).mkdir(parents=True, exist_ok=True)


def safe_path(base: Path, rel: str) -> Path:
    """将相对路径安全限定在 base 目录内，防止路径穿越"""
    rel = (rel or "").replace("\\", "/").strip("/")
    p = (base / rel).resolve()
    base_res = base.resolve()
    if p != base_res and base_res not in p.parents:
        raise ValueError("非法路径")
    return p


def _clean_name(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", (name or "").strip())
    return name or "未命名"


# ---------------- 目录与文件 ----------------
def list_dir(username: str, rel: str) -> list:
    base = user_root(username)
    d = safe_path(base, rel)
    if not d.exists():
        raise FileNotFoundError("目录不存在")
    if not d.is_dir():
        raise NotADirectoryError("不是目录")
    items = []
    for e in sorted(d.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
        st = e.stat()
        rel_path = e.name if not rel.strip("/") else rel.strip("/") + "/" + e.name
        items.append({
            "name": e.name,
            "is_dir": e.is_dir(),
            "size": st.st_size if e.is_file() else 0,
            "mtime": int(st.st_mtime),
            "path": rel_path,
        })
    return items


def mkdir(username: str, rel: str, name: str) -> Path:
    base = user_root(username)
    d = safe_path(base, rel)
    if not d.is_dir():
        raise NotADirectoryError("目录不存在")
    nd = safe_path(d, _clean_name(name))
    nd.mkdir(parents=True, exist_ok=True)
    return nd


def rename(username: str, rel: str, new_name: str):
    base = user_root(username)
    p = safe_path(base, rel)
    if not p.exists():
        raise FileNotFoundError("文件不存在")
    np = p.parent / _clean_name(new_name)
    if np == p:
        return
    if np.exists():
        raise FileExistsError("同名文件已存在")
    p.rename(np)


def move(username: str, rel: str, dest_dir: str):
    base = user_root(username)
    p = safe_path(base, rel)
    d = safe_path(base, dest_dir)
    if not p.exists():
        raise FileNotFoundError("文件不存在")
    if not d.is_dir():
        raise FileNotFoundError("目标目录不存在")
    if d == p.parent:
        return
    if d == p or d in p.parents:
        raise ValueError("不能移动到自身或其子目录")
    target = d / p.name
    if target.exists():
        raise FileExistsError("目标位置已存在同名文件")
    shutil.move(str(p), str(target))


def save_upload(username: str, rel: str, filename: str, stream,
                quota_bytes: int = 0) -> Path:
    base = user_root(username)
    d = safe_path(base, rel)
    if not d.is_dir():
        raise NotADirectoryError("目录不存在")
    dest = d / _clean_name(filename)
    if dest.exists():
        stem, ext = os.path.splitext(dest.name)
        dest = d / f"{stem}.{int(time.time())}{ext}"
    # 配额预检：新文件大小未知，先写入临时文件再校验
    tmp = dest.with_name(dest.name + ".part")
    with open(tmp, "wb") as f:
        shutil.copyfileobj(stream, f, 1024 * 1024)
    if quota_bytes > 0:
        used, _ = stat_usage(username)
        if used + tmp.stat().st_size > quota_bytes:
            tmp.unlink(missing_ok=True)
            raise QuotaExceeded("存储空间不足，已超出配额")
    tmp.replace(dest)
    return dest


def get_path(username: str, rel: str) -> Path:
    base = user_root(username)
    p = safe_path(base, rel)
    if not p.exists():
        raise FileNotFoundError("文件不存在")
    return p


def search(username: str, q: str, rel: str = "") -> list:
    base = user_root(username)
    start = safe_path(base, rel)
    if not start.exists():
        return []
    q = (q or "").lower()
    results = []
    for p in start.rglob("*"):
        if q and q not in p.name.lower():
            continue
        if p.is_file():
            rel_path = str(p.relative_to(base)).replace("\\", "/")
            results.append({
                "name": p.name, "is_dir": False,
                "size": p.stat().st_size, "mtime": int(p.stat().st_mtime),
                "path": rel_path,
            })
        if len(results) >= 200:
            break
    return results


def stat_usage(username: str):
    root = user_root(username)
    total, n = 0, 0
    if root.exists():
        for p in root.rglob("*"):
            if p.is_file():
                total += p.stat().st_size
                n += 1
    return total, n


def make_zip(username: str, rel: str) -> Path:
    """把文件或目录打包为 zip，返回临时文件路径"""
    base = user_root(username)
    p = safe_path(base, rel)
    if not p.exists():
        raise FileNotFoundError("文件不存在")
    config.ensure_dirs()
    out = config.DATA_DIR / "tmp" / f"zip_{username}_{int(time.time())}.zip"
    name = p.name
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        if p.is_file():
            zf.write(p, name)
        else:
            for f in sorted(p.rglob("*")):
                if f.is_file():
                    zf.write(f, f"{name}/{f.relative_to(p)}".replace("\\", "/"))
    return out


# ---------------- 在线编辑 ----------------
def is_editable(name: str) -> bool:
    return (name.split(".").pop() or "").lower() in EDITABLE_EXT


def read_text(username: str, rel: str, max_bytes: int = 2 * 1024 * 1024) -> str:
    p = get_path(username, rel)
    if p.is_dir():
        raise NotADirectoryError("不能编辑目录")
    if p.stat().st_size > max_bytes:
        raise ValueError("文件过大，不支持在线编辑")
    return p.read_text(encoding="utf-8", errors="replace")


def write_text(username: str, rel: str, content: str):
    p = get_path(username, rel)
    if p.is_dir():
        raise NotADirectoryError("不能编辑目录")
    if not is_editable(p.name):
        raise ValueError("该文件类型不支持在线编辑")
    quota = 0
    p.write_text(content or "", encoding="utf-8")


# ---------------- 回收站 ----------------
def _load_trash_index() -> list:
    if TRASH_INDEX.exists():
        try:
            return json.loads(TRASH_INDEX.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _save_trash_index(idx: list):
    with _lock:
        TRASH_INDEX.write_text(
            json.dumps(idx, ensure_ascii=False, indent=2), encoding="utf-8")


def delete(username: str, rel: str):
    base = user_root(username)
    p = safe_path(base, rel)
    if not p.exists():
        raise FileNotFoundError("文件不存在")
    t = trash_root(username)
    target = t / p.name
    if target.exists():
        target = t / f"{p.name}.{int(time.time())}"
    shutil.move(str(p), str(target))
    idx = _load_trash_index()
    idx.append({
        "user": username, "trash_name": target.name, "rel": rel,
        "is_dir": p.is_dir(), "time": int(time.time()),
    })
    _save_trash_index(idx)


def list_trash(username: str) -> list:
    idx = _load_trash_index()
    t = trash_root(username)
    items = []
    for rec in idx:
        if rec["user"] != username:
            continue
        items.append({
            "trash_name": rec["trash_name"], "rel": rec["rel"],
            "is_dir": rec["is_dir"], "time": rec["time"],
            "exists": (t / rec["trash_name"]).exists(),
        })
    items.sort(key=lambda x: -x["time"])
    return items


def restore(username: str, trash_name: str):
    idx = _load_trash_index()
    rec = next((r for r in idx if r["user"] == username
                and r["trash_name"] == trash_name), None)
    if not rec:
        raise FileNotFoundError("回收站记录不存在")
    t = trash_root(username)
    src = t / rec["trash_name"]
    if not src.exists():
        raise FileNotFoundError("回收站文件已被清理")
    dest = safe_path(user_root(username), rec["rel"])
    if dest.exists():
        raise FileExistsError("原位置已存在同名文件，请先处理")
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dest))
    _save_trash_index([r for r in idx if r is not rec])


def empty_trash(username: str):
    t = trash_root(username)
    if t.exists():
        for e in t.iterdir():
            if e.is_dir():
                shutil.rmtree(e, ignore_errors=True)
            else:
                e.unlink(missing_ok=True)
    idx = _load_trash_index()
    _save_trash_index([r for r in idx if r["user"] != username])


def purge_trash_item(username: str, trash_name: str):
    """彻底删除回收站中的单条记录"""
    idx = _load_trash_index()
    rec = next((r for r in idx if r["user"] == username
                and r["trash_name"] == trash_name), None)
    if not rec:
        raise FileNotFoundError("回收站记录不存在")
    t = trash_root(username)
    p = t / rec["trash_name"]
    if p.is_dir():
        shutil.rmtree(p, ignore_errors=True)
    else:
        p.unlink(missing_ok=True)
    _save_trash_index([r for r in idx if r is not rec])
