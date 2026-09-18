# -*- coding: utf-8 -*-
"""用户与登录会话（PBKDF2 密码哈希 + 随机 token 会话）"""
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
        salt, pw = hash_password(cfg["admin_password"])
        users[admin] = {
            "salt": salt, "hash": pw, "is_admin": True,
            "created": time.time(),
        }
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
    salt, pw = hash_password(password)
    users[username] = {
        "salt": salt, "hash": pw, "is_admin": False, "created": time.time(),
    }
    _save_users(users)
    return users[username], None


def login(username: str, password: str):
    users = _load_users()
    u = users.get((username or "").strip())
    if not u:
        return None, "用户名或密码错误"
    if not verify_password(password, u["salt"], u["hash"]):
        return None, "用户名或密码错误"
    return u, None


def is_admin(username: str) -> bool:
    users = _load_users()
    u = users.get(username)
    return bool(u and u.get("is_admin"))


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
    return rec["user"]


def logout(token: str):
    s = _load_sessions()
    if token in s:
        del s[token]
        _save_sessions(s)
