# -*- coding: utf-8 -*-
"""外部文件夹挂载：把本机任意目录共享给局域网用户浏览 / 下载"""
import os
import re
import time
import uuid
from pathlib import Path

from . import config


def _clean_name(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", (name or "").strip()) or "未命名"


def list_mounts(public: bool = False) -> list:
    mounts = config.load_mounts()
    if public:
        return [{"id": m["id"], "name": m["name"], "readonly": m.get("readonly", True)}
                for m in mounts if m.get("enabled", True)]
    return mounts


def get_mount(mount_id: str):
    for m in config.load_mounts():
        if m["id"] == mount_id:
            return m
    return None


def add_mount(name: str, path: str, readonly: bool = True) -> dict:
    p = Path(path).expanduser()
    if not p.exists() or not p.is_dir():
        raise FileNotFoundError("路径不存在或不是文件夹")
    m = {
        "id": uuid.uuid4().hex[:8],
        "name": _clean_name(name),
        "path": str(p.resolve()),
        "readonly": bool(readonly),
        "enabled": True,
        "created": int(time.time()),
    }
    mounts = config.load_mounts()
    mounts.append(m)
    config.save_mounts(mounts)
    return m


def update_mount(mount_id: str, **fields):
    mounts = config.load_mounts()
    for m in mounts:
        if m["id"] != mount_id:
            continue
        if "name" in fields:
            m["name"] = _clean_name(fields["name"])
        if "path" in fields and fields["path"]:
            p = Path(fields["path"]).expanduser()
            if not p.is_dir():
                raise FileNotFoundError("路径不存在或不是文件夹")
            m["path"] = str(p.resolve())
        if "readonly" in fields:
            m["readonly"] = bool(fields["readonly"])
        if "enabled" in fields:
            m["enabled"] = bool(fields["enabled"])
        config.save_mounts(mounts)
        return m
    raise FileNotFoundError("挂载不存在")


def delete_mount(mount_id: str):
    mounts = config.load_mounts()
    mounts = [m for m in mounts if m["id"] != mount_id]
    config.save_mounts(mounts)


def mount_root(m: dict) -> Path:
    return Path(m["path"]).resolve()


def browse(mount_id: str, rel: str) -> list:
    m = get_mount(mount_id)
    if not m or not m.get("enabled", True):
        raise FileNotFoundError("共享文件夹不存在或已停用")
    root = mount_root(m)
    rel = (rel or "").replace("\\", "/").strip("/")
    d = (root / rel).resolve()
    if d != root and root not in d.parents:
        raise ValueError("非法路径")
    if not d.exists() or not d.is_dir():
        raise FileNotFoundError("目录不存在")
    items = []
    for e in sorted(d.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
        st = e.stat()
        items.append({
            "name": e.name, "is_dir": e.is_dir(),
            "size": st.st_size if e.is_file() else 0,
            "mtime": int(st.st_mtime),
            "path": e.name if not rel else rel + "/" + e.name,
        })
    return items


def resolve_file(mount_id: str, rel: str) -> Path:
    """解析挂载内文件路径（限文件，供下载）"""
    m = get_mount(mount_id)
    if not m or not m.get("enabled", True):
        raise FileNotFoundError("共享文件夹不存在或已停用")
    root = mount_root(m)
    rel = (rel or "").replace("\\", "/").strip("/")
    p = (root / rel).resolve()
    if p != root and root not in p.parents:
        raise ValueError("非法路径")
    if not p.exists() or not p.is_file():
        raise FileNotFoundError("文件不存在")
    return p


def stat_total_size() -> int:
    """统计所有挂载目录占用（用于管理面板展示，可裁剪）"""
    return 0
