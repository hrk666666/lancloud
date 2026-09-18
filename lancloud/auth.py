# -*- coding: utf-8 -*-
"""用户与登录会话（PBKDF2 密码哈希 + 随机 token 会话）

用户字段：
  username  -> {salt, hash, is_admin, created, quota_mb, can_share, disabled}
"""
import hashlib
import hmac
import json
import secrets
import threading
import time

from . import config

USERS_PATH = config.DATA_DIR / "users.json"
SESSIONS_PATH = config.DATA_DIR / "sessions.json"
SESSION_DAYS = 7

_lock = threading.Lock()


def _load_users() -> dict:
    if USERS_PATH.exists():
        try:
            return json.loads(USERS_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_users(users: dict):
    with _lock:
        USERS_PATH.write_text(
            json.dumps(users, ensure_ascii=False, indent=2), encoding="utf-8")


def _new_user(password: str, is_admin: bool = False,
              quota_mb: int = None, can_share: bool = True):
    salt, pw = hash_password(password)
    cfg = config.load_config()
    q = quota_mb if quota_mb is not None else cfg.get("default_quota_mb", 0)
    return {
        "salt": salt, "hash": pw, "is_admin": is_admin,
        "created": time.time(),
        "quota_mb": int(q or 0),
        "can_share": bool(can_share),
        "disabled": False,
    }


def hash_password(password: str, salt: str = None):
    if salt is None:
        salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                             salt.encode("utf-8"), 120_000)
    return salt, dk.hex()


def verify_password(password: str, salt: str, expected: str) -> bool:
    _, dk = hash_password(password, salt)
    return hmac.compare_digest(dk, expected)


def ensure_admin():
    """首次启动时按配置创建管理员账号"""
    users = _load_users()
    cfg = config.load_config()
    admin = cfg["admin_user"]
    if admin not in users:
        users[admin] = _new_user(cfg["admin_password"], is_admin=True,
                                 quota_mb=0, can_share=True)
        _save_users(users)


def register(username: str, password: str):
    users = _load_users()
    username = (username or "").strip()
    if len(username) < 2:
        return None, "用户名至少 2 个字符"
    if not password or len(password) < 6:
        return None, "密码至少 6 位"
    if username in users:
        return None, "用户名已存在"
    users[username] = _new_user(password)
    _save_users(users)
    return users[username], None


def login(username: str, password: str):
    users = _load_users()
    u = users.get((username or "").strip())
    if not u:
        return None, "用户名或密码错误"
    if u.get("disabled"):
        return None, "该账号已被管理员禁用"
    if not verify_password(password, u["salt"], u["hash"]):
        return None, "用户名或密码错误"
    return u, None


def is_admin(username: str) -> bool:
    users = _load_users()
    u = users.get(username)
    return bool(u and u.get("is_admin"))


def get_user_info(username: str) -> dict:
    """返回不含敏感字段的用户信息"""
    users = _load_users()
    u = users.get(username)
    if not u:
        return None
    return {
        "username": username,
        "is_admin": bool(u.get("is_admin")),
        "quota_mb": int(u.get("quota_mb") or 0),
        "can_share": bool(u.get("can_share", True)),
        "disabled": bool(u.get("disabled")),
        "created": u.get("created"),
    }


# ---------------- 管理员：用户管理 ----------------
def admin_list_users() -> list:
    users = _load_users()
    out = []
    for name, u in users.items():
        info = get_user_info(name)
        info["has_password"] = bool(u.get("hash"))
        out.append(info)
    out.sort(key=lambda x: (not x["is_admin"], x["username"]))
    return out


def admin_create_user(username: str, password: str, quota_mb: int = None,
                      is_admin: bool = False, can_share: bool = True,
                      disabled: bool = False):
    users = _load_users()
    username = (username or "").strip()
    if len(username) < 2:
        return None, "用户名至少 2 个字符"
    if not password or len(password) < 6:
        return None, "密码至少 6 位"
    if username in users:
        return None, "用户名已存在"
    users[username] = _new_user(password, is_admin=is_admin,
                                quota_mb=quota_mb, can_share=can_share)
    users[username]["disabled"] = bool(disabled)
    _save_users(users)
    return users[username], None


def admin_update_user(username: str, **fields):
    """fields: quota_mb / can_share / disabled / is_admin"""
    users = _load_users()
    u = users.get(username)
    if not u:
        return "用户不存在"
    if "quota_mb" in fields:
        u["quota_mb"] = max(0, int(fields["quota_mb"] or 0))
    if "can_share" in fields:
        u["can_share"] = bool(fields["can_share"])
    if "disabled" in fields:
        u["disabled"] = bool(fields["disabled"])
    if "is_admin" in fields:
        u["is_admin"] = bool(fields["is_admin"])
    _save_users(users)
    return None


def admin_reset_password(username: str, new_password: str):
    users = _load_users()
    u = users.get(username)
    if not u:
        return "用户不存在"
    if not new_password or len(new_password) < 6:
        return "密码至少 6 位"
    salt, pw = hash_password(new_password)
    u["salt"], u["hash"] = salt, pw
    _save_users(users)
    return None


def admin_delete_user(username: str):
    users = _load_users()
    if username not in users:
        return "用户不存在"
    if users[username].get("is_admin"):
        return "不能删除管理员账号"
    del users[username]
    _save_users(users)
    return None


def can_share(username: str) -> bool:
    users = _load_users()
    u = users.get(username)
    return bool(u and u.get("can_share", True))


# ---------------- 会话 ----------------
def _load_sessions() -> dict:
    if SESSIONS_PATH.exists():
        try:
            return json.loads(SESSIONS_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_sessions(s: dict):
    with _lock:
        SESSIONS_PATH.write_text(
            json.dumps(s, ensure_ascii=False), encoding="utf-8")


def create_session(username: str) -> str:
    s = _load_sessions()
    token = secrets.token_urlsafe(32)
    s[token] = {"user": username, "exp": time.time() + SESSION_DAYS * 86400}
    _save_sessions(s)
    return token


def get_user(token: str):
    if not token:
        return None
    s = _load_sessions()
    rec = s.get(token)
    if not rec:
        return None
    if rec["exp"] < time.time():
        del s[token]
        _save_sessions(s)
        return None
    username = rec["user"]
    # 用户被禁用后立即失效
    users = _load_users()
    u = users.get(username)
    if not u or u.get("disabled"):
        return None
    return username


def logout(token: str):
    s = _load_sessions()
    if token in s:
        del s[token]
        _save_sessions(s)
