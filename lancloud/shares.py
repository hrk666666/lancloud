# -*- coding: utf-8 -*-
"""分享链接：生成 / 查询 / 删除（支持强制登录、过期时间）"""
import json
import secrets
import threading
import time

from . import config

SHARES_PATH = config.DATA_DIR / "shares.json"
_lock = threading.Lock()


def _load() -> dict:
    if SHARES_PATH.exists():
        try:
            return json.loads(SHARES_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save(s: dict):
    with _lock:
        SHARES_PATH.write_text(
            json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")


def create(username: str, rel: str, require_login: bool = False,
           expire_days: int = 0) -> dict:
    token = secrets.token_hex(8)
    rec = {
        "user": username,
        "path": rel,
        "created": int(time.time()),
        "token": token,
        "require_login": bool(require_login),
        "expire_at": int(time.time()) + expire_days * 86400 if expire_days > 0 else 0,
    }
    s = _load()
    s[token] = rec
    _save(s)
    return rec


def list_shares(username: str) -> list:
    s = _load()
    items = [v for k, v in s.items() if v["user"] == username]
    items.sort(key=lambda x: -x["created"])
    return items


def get(token: str):
    rec = _load().get(token)
    if not rec:
        return None
    # 过期校验
    if rec.get("expire_at") and rec["expire_at"] < time.time():
        return None
    return rec


def delete(token: str):
    s = _load()
    if token in s:
        del s[token]
        _save(s)
