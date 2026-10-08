"""账户体系：注册、登录、会话、邀请码和每个用户的设置。

平台库 ``platform.sqlite`` 只放账户数据，不放任何账单；每个用户的账单在自己的
账本目录 ``tenants/<user_id>/`` 里（布局和 ``cfo_agent_poc/`` 一样，见 tenancy.py）。

密码用标准库 scrypt 加盐哈希；会话 cookie 里只放随机串，库里只存它的 SHA-256，
库文件泄露也拿不到能用的会话。
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

try:
    from cfo_agent_poc.tenancy import Ledger
except ModuleNotFoundError:  # Supports direct execution from cfo_agent_poc.
    from tenancy import Ledger


PROJECT_DIR = Path(__file__).resolve().parent
SESSION_DAYS = 30
INVITE_DAYS = 14
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128
MAX_DISPLAY_NAME_LENGTH = 20
EMAIL_PATTERN = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")
BUDGET_KEYS = ("day", "week", "month")

# scrypt 参数：n=2^14, r=8 约占 16MB 内存、几十毫秒，足够拖慢离线爆破
SCRYPT_N, SCRYPT_R, SCRYPT_P, SCRYPT_DKLEN = 2**14, 8, 1, 32


class AccountError(ValueError):
    def __init__(self, message: str, *, code: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


def default_home() -> Path:
    """平台数据根目录：platform.sqlite 和 tenants/ 都在这里。"""
    configured = os.environ.get("CFO_HOME", "").strip()
    return Path(configured).expanduser().resolve() if configured else PROJECT_DIR / "data"


def _now() -> datetime:
    return datetime.now().replace(microsecond=0)


def _iso(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=SCRYPT_DKLEN
    )
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_hex, digest_hex = stored.split("$")
        if scheme != "scrypt":
            return False
        digest = hashlib.scrypt(
            password.encode("utf-8"),
            salt=bytes.fromhex(salt_hex),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(digest_hex) // 2,
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest.hex(), digest_hex)


# 用户不存在时也算一遍哈希，免得靠响应快慢就能探出哪些邮箱注册过
_DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


def _token_hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def normalize_email(value: object) -> str:
    email = str(value or "").strip().lower()
    if not EMAIL_PATTERN.match(email) or len(email) > 254:
        raise AccountError("请输入有效的邮箱地址。", code="invalid_email")
    return email


def validate_password(value: object) -> str:
    password = str(value or "")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise AccountError(f"密码至少需要 {MIN_PASSWORD_LENGTH} 位。", code="weak_password")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise AccountError("密码太长了。", code="invalid_password")
    return password


def clean_display_name(value: object, fallback: str = "") -> str:
    name = " ".join(str(value or "").split())
    if not name:
        name = fallback
    if not name:
        raise AccountError("请填写称呼。", code="invalid_display_name")
    if len(name) > MAX_DISPLAY_NAME_LENGTH:
        raise AccountError(f"称呼最多 {MAX_DISPLAY_NAME_LENGTH} 个字。", code="invalid_display_name")
    return name


def clean_budgets(value: object) -> dict[str, float]:
    if not isinstance(value, dict):
        raise AccountError("预算格式不正确。", code="invalid_budgets")
    budgets: dict[str, float] = {}
    for key in BUDGET_KEYS:
        try:
            amount = float(value.get(key, 0) or 0)
        except (TypeError, ValueError):
            raise AccountError("预算需要是数字。", code="invalid_budgets") from None
        if not (0 <= amount <= 10_000_000):
            raise AccountError("预算需要是 0 或更大的数字。", code="invalid_budgets")
        budgets[key] = round(amount, 2)
    return budgets


class AccountStore:
    def __init__(self, home: str | Path) -> None:
        self.home = Path(home)
        self.db_path = self.home / "platform.sqlite"
        self._ready = False
        self._ready_lock = threading.Lock()

    # ------------------------------------------------------------------ 基础

    def connect(self) -> sqlite3.Connection:
        if not self._ready:
            with self._ready_lock:
                if not self._ready:
                    self.home.mkdir(parents=True, exist_ok=True)
                    conn = sqlite3.connect(self.db_path)
                    try:
                        self._ensure_tables(conn)
                    finally:
                        conn.close()
                    self._ready = True
        conn = sqlite3.connect(self.db_path, timeout=10, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("pragma foreign_keys = on")
        return conn

    @staticmethod
    def _ensure_tables(conn: sqlite3.Connection) -> None:
        conn.execute("pragma journal_mode = wal")
        conn.executescript(
            """
            create table if not exists users (
                id text primary key,
                email text not null unique,
                password_hash text not null,
                display_name text not null,
                tenant_dir text not null unique,
                is_admin integer not null default 0,
                status text not null default 'active',
                created_at text not null
            );
            create table if not exists sessions (
                token_hash text primary key,
                user_id text not null references users(id) on delete cascade,
                created_at text not null,
                expires_at text not null,
                user_agent text
            );
            create index if not exists sessions_user on sessions(user_id);
            create table if not exists invites (
                code text primary key,
                created_by text,
                created_at text not null,
                expires_at text not null,
                used_by text references users(id) on delete set null,
                used_at text
            );
            create table if not exists user_settings (
                user_id text primary key references users(id) on delete cascade,
                budgets_json text,
                updated_at text not null
            );
            """
        )
        conn.commit()

    @staticmethod
    def _public(row: sqlite3.Row | None) -> dict | None:
        if row is None:
            return None
        return {
            "id": row["id"],
            "email": row["email"],
            "display_name": row["display_name"],
            "tenant_dir": row["tenant_dir"],
            "is_admin": bool(row["is_admin"]),
            "status": row["status"],
            "created_at": row["created_at"],
        }

    def ledger_for(self, user: dict) -> Ledger:
        return Ledger(self.home / user["tenant_dir"], display_name=user["display_name"])

    def user_count(self) -> int:
        conn = self.connect()
        try:
            return conn.execute("select count(*) from users").fetchone()[0]
        finally:
            conn.close()

    def needs_invite(self) -> bool:
        """第一个注册的人成为管理员，不需要邀请码；之后都要。"""
        return self.user_count() > 0

    def list_users(self) -> list[dict]:
        conn = self.connect()
        try:
            rows = conn.execute("select * from users order by created_at").fetchall()
            return [self._public(row) for row in rows]
        finally:
            conn.close()

    def get_user(self, user_id: str) -> dict | None:
        conn = self.connect()
        try:
            return self._public(conn.execute("select * from users where id = ?", (user_id,)).fetchone())
        finally:
            conn.close()

    def find_user_by_email(self, email: str) -> dict | None:
        conn = self.connect()
        try:
            row = conn.execute("select * from users where email = ?", (email.strip().lower(),)).fetchone()
            return self._public(row)
        finally:
            conn.close()

    # ------------------------------------------------------------ 注册登录

    def create_user(
        self,
        email: object,
        password: object,
        display_name: object = "",
        *,
        is_admin: bool = False,
        conn: sqlite3.Connection | None = None,
    ) -> dict:
        email = normalize_email(email)
        password = validate_password(password)
        name = clean_display_name(display_name, fallback=email.split("@")[0])
        user_id = secrets.token_hex(8)
        own_conn = conn is None
        conn = conn or self.connect()
        try:
            try:
                conn.execute(
                    """
                    insert into users (id, email, password_hash, display_name, tenant_dir, is_admin, created_at)
                    values (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (user_id, email, hash_password(password), name, f"tenants/{user_id}", int(is_admin), _iso(_now())),
                )
            except sqlite3.IntegrityError:
                raise AccountError("这个邮箱已经注册过了，请直接登录。", code="email_taken", status=409) from None
            row = conn.execute("select * from users where id = ?", (user_id,)).fetchone()
        finally:
            if own_conn:
                conn.close()
        user = self._public(row)
        self.ledger_for(user).data_dir.mkdir(parents=True, exist_ok=True)
        return user

    def register(self, email: object, password: object, display_name: object = "", invite_code: object = "") -> dict:
        conn = self.connect()
        try:
            # 写锁：两个人同时抢「第一个注册」时只能有一个成为管理员
            conn.execute("begin immediate")
            try:
                first_user = conn.execute("select count(*) from users").fetchone()[0] == 0
                code = str(invite_code or "").strip().upper()
                if not first_user:
                    if not code:
                        raise AccountError("注册需要邀请码。", code="invite_required", status=403)
                    invite = conn.execute("select * from invites where code = ?", (code,)).fetchone()
                    if invite is None or invite["used_by"] or invite["expires_at"] < _iso(_now()):
                        raise AccountError("邀请码无效或已过期。", code="invalid_invite", status=403)
                user = self.create_user(email, password, display_name, is_admin=first_user, conn=conn)
                if not first_user:
                    conn.execute(
                        "update invites set used_by = ?, used_at = ? where code = ?",
                        (user["id"], _iso(_now()), code),
                    )
                conn.execute("commit")
            except BaseException:
                conn.execute("rollback")
                raise
        finally:
            conn.close()
        return user

    def authenticate(self, email: object, password: object) -> dict:
        address = str(email or "").strip().lower()
        conn = self.connect()
        try:
            row = conn.execute("select * from users where email = ?", (address,)).fetchone()
        finally:
            conn.close()
        stored = row["password_hash"] if row is not None else _DUMMY_HASH
        if not verify_password(str(password or ""), stored) or row is None:
            raise AccountError("邮箱或密码不正确。", code="invalid_credentials", status=401)
        if row["status"] != "active":
            raise AccountError("这个账户已停用。", code="account_disabled", status=403)
        return self._public(row)

    def set_password(self, user_id: str, new_password: object) -> None:
        password = validate_password(new_password)
        conn = self.connect()
        try:
            conn.execute("update users set password_hash = ? where id = ?", (hash_password(password), user_id))
        finally:
            conn.close()

    def change_password(self, user_id: str, current: object, new_password: object, *, keep_session: str | None) -> None:
        user = self.get_user(user_id)
        if user is None:
            raise AccountError("账户不存在。", code="not_found", status=404)
        conn = self.connect()
        try:
            stored = conn.execute("select password_hash from users where id = ?", (user_id,)).fetchone()[0]
        finally:
            conn.close()
        if not verify_password(str(current or ""), stored):
            raise AccountError("当前密码不正确。", code="invalid_credentials", status=401)
        self.set_password(user_id, new_password)
        # 改密码后，别的设备上的登录全部作废，只留当前这个
        self.revoke_user_sessions(user_id, except_token=keep_session)

    def delete_user(self, user_id: str, *, remove_ledger: bool = False) -> None:
        user = self.get_user(user_id)
        if user is None:
            return
        conn = self.connect()
        try:
            conn.execute("delete from users where id = ?", (user_id,))
        finally:
            conn.close()
        if remove_ledger:
            import shutil

            shutil.rmtree(self.ledger_for(user).root, ignore_errors=True)

    def update_display_name(self, user_id: str, value: object) -> dict:
        name = clean_display_name(value)
        conn = self.connect()
        try:
            conn.execute("update users set display_name = ? where id = ?", (name, user_id))
        finally:
            conn.close()
        return self.get_user(user_id)

    # ---------------------------------------------------------------- 会话

    def create_session(self, user_id: str, user_agent: str | None = None) -> str:
        raw = secrets.token_urlsafe(32)
        now = _now()
        conn = self.connect()
        try:
            conn.execute(
                "insert into sessions (token_hash, user_id, created_at, expires_at, user_agent) values (?, ?, ?, ?, ?)",
                (_token_hash(raw), user_id, _iso(now), _iso(now + timedelta(days=SESSION_DAYS)), (user_agent or "")[:200]),
            )
            conn.execute("delete from sessions where expires_at < ?", (_iso(now),))
        finally:
            conn.close()
        return raw

    def session_user(self, raw: str | None) -> dict | None:
        if not raw:
            return None
        conn = self.connect()
        try:
            row = conn.execute(
                """
                select users.* from sessions join users on users.id = sessions.user_id
                where sessions.token_hash = ? and sessions.expires_at > ? and users.status = 'active'
                """,
                (_token_hash(raw), _iso(_now())),
            ).fetchone()
        finally:
            conn.close()
        return self._public(row)

    def revoke_session(self, raw: str | None) -> None:
        if not raw:
            return
        conn = self.connect()
        try:
            conn.execute("delete from sessions where token_hash = ?", (_token_hash(raw),))
        finally:
            conn.close()

    def revoke_user_sessions(self, user_id: str, *, except_token: str | None = None) -> None:
        keep = _token_hash(except_token) if except_token else ""
        conn = self.connect()
        try:
            conn.execute("delete from sessions where user_id = ? and token_hash != ?", (user_id, keep))
        finally:
            conn.close()

    # -------------------------------------------------------------- 邀请码

    def create_invite(self, created_by: str | None, *, days: int = INVITE_DAYS) -> dict:
        # 去掉易混的 0/O/1/I，方便口头或截图转告
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        code = "".join(secrets.choice(alphabet) for _ in range(8))
        now = _now()
        item = {"code": code, "created_at": _iso(now), "expires_at": _iso(now + timedelta(days=days))}
        conn = self.connect()
        try:
            conn.execute(
                "insert into invites (code, created_by, created_at, expires_at) values (?, ?, ?, ?)",
                (code, created_by, item["created_at"], item["expires_at"]),
            )
        finally:
            conn.close()
        return {**item, "used": False}

    def list_invites(self, limit: int = 20) -> list[dict]:
        conn = self.connect()
        try:
            rows = conn.execute(
                """
                select invites.*, users.email as used_by_email from invites
                left join users on users.id = invites.used_by
                order by invites.created_at desc limit ?
                """,
                (limit,),
            ).fetchall()
        finally:
            conn.close()
        now = _iso(_now())
        return [
            {
                "code": row["code"],
                "created_at": row["created_at"],
                "expires_at": row["expires_at"],
                "used": bool(row["used_by"]),
                "used_by_email": row["used_by_email"],
                "expired": not row["used_by"] and row["expires_at"] < now,
            }
            for row in rows
        ]

    # ---------------------------------------------------------------- 设置

    def get_budgets(self, user_id: str) -> dict | None:
        conn = self.connect()
        try:
            row = conn.execute("select budgets_json from user_settings where user_id = ?", (user_id,)).fetchone()
        finally:
            conn.close()
        if row is None or not row["budgets_json"]:
            return None
        try:
            return clean_budgets(json.loads(row["budgets_json"]))
        except (json.JSONDecodeError, AccountError):
            return None

    def set_budgets(self, user_id: str, value: object) -> dict:
        budgets = clean_budgets(value)
        conn = self.connect()
        try:
            conn.execute(
                """
                insert into user_settings (user_id, budgets_json, updated_at) values (?, ?, ?)
                on conflict(user_id) do update set budgets_json = excluded.budgets_json, updated_at = excluded.updated_at
                """,
                (user_id, json.dumps(budgets), _iso(_now())),
            )
        finally:
            conn.close()
        return budgets


class LoginThrottle:
    """同一 IP 或同一邮箱短时间内连续输错太多次就先挡一会儿。单进程内存计数即可。"""

    def __init__(self, max_failures: int = 10, window_seconds: int = 15 * 60) -> None:
        self.max_failures = max_failures
        self.window = window_seconds
        self._failures: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _recent(self, key: str, now: float) -> list[float]:
        stamps = [stamp for stamp in self._failures.get(key, []) if now - stamp < self.window]
        if stamps:
            self._failures[key] = stamps
        else:
            self._failures.pop(key, None)
        return stamps

    def blocked(self, *keys: str) -> bool:
        now = time.monotonic()
        with self._lock:
            return any(len(self._recent(key, now)) >= self.max_failures for key in keys if key)

    def fail(self, *keys: str) -> None:
        now = time.monotonic()
        with self._lock:
            for key in keys:
                if key:
                    self._failures.setdefault(key, []).append(now)

    def clear(self, *keys: str) -> None:
        with self._lock:
            for key in keys:
                self._failures.pop(key, None)


def main() -> None:
    parser = argparse.ArgumentParser(description="CFO 账户管理（邀请码、用户列表、重置密码）")
    parser.add_argument("--home", help="平台数据目录，默认 CFO_HOME 或 cfo_agent_poc/data")
    sub = parser.add_subparsers(dest="command", required=True)
    invite = sub.add_parser("invite", help="生成一个邀请码")
    invite.add_argument("--days", type=int, default=INVITE_DAYS)
    sub.add_parser("users", help="列出所有用户")
    reset = sub.add_parser("reset-password", help="给用户生成一个新的随机密码，并让他所有设备重新登录")
    reset.add_argument("email")
    args = parser.parse_args()

    store = AccountStore(Path(args.home).resolve() if args.home else default_home())
    if args.command == "invite":
        item = store.create_invite("cli", days=args.days)
        print(f"邀请码 {item['code']}，有效期至 {item['expires_at']}")
    elif args.command == "users":
        for user in store.list_users():
            flag = " [管理员]" if user["is_admin"] else ""
            print(f"{user['email']}\t{user['display_name']}\t{user['tenant_dir']}\t{user['status']}{flag}")
    elif args.command == "reset-password":
        user = store.find_user_by_email(args.email)
        if user is None:
            raise SystemExit(f"没有这个用户：{args.email}")
        password = secrets.token_urlsafe(9)
        store.set_password(user["id"], password)
        store.revoke_user_sessions(user["id"])
        print(f"{user['email']} 的新密码：{password}")


if __name__ == "__main__":
    main()
