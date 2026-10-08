"""把一个旧的单用户实例并入多用户系统。

旧实例就是一份 ``cfo_agent_poc/`` 目录：账本在 ``data/cfo.sqlite``，截图、OCR 文本
在 ``data/`` 下面，库里存的是 ``data/...`` 相对路径。新系统每个用户的账本目录布局
和它一样，所以迁移 = 建账户 + 整库拷贝 + 拷贝证据目录，**不改任何一行账单数据**。

    python3 cfo_agent_poc/migrate_instance.py --src /srv/cfo-alice/cfo_agent_poc --email alice@example.com

旧目录只读不写；迁移失败会把新建的账户和账本目录一起撤掉，可以放心重跑。
"""

from __future__ import annotations

import argparse
import secrets
import shutil
import sqlite3
from pathlib import Path

try:
    from cfo_agent_poc.accounts import AccountStore, default_home
except ModuleNotFoundError:  # Supports direct execution from cfo_agent_poc.
    from accounts import AccountStore, default_home


EVIDENCE_DIRS = ("mail_attachments", "ocr_texts", "evidence", "captures")


def read_env_value(env_path: Path, key: str) -> str:
    if not env_path.is_file():
        return ""
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def ledger_totals(db_path: Path) -> dict:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        count, total = conn.execute("select count(*), coalesce(round(sum(amount), 2), 0) from transactions").fetchone()
        captures = conn.execute("select count(*) from raw_bill_captures").fetchone()[0]
    except sqlite3.OperationalError as exc:
        raise SystemExit(f"{db_path} 不是有效的 CFO 账本（{exc}）") from None
    finally:
        conn.close()
    return {"transactions": count, "amount_sum": total, "captures": captures}


def image_coverage(db_path: Path, root: Path) -> dict:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        paths = [row[0] for row in conn.execute("select image_path from raw_bill_captures where image_path is not null and image_path != ''")]
    finally:
        conn.close()
    found = absolute = missing = 0
    for raw in paths:
        candidate = Path(raw)
        if candidate.is_absolute():
            absolute += 1  # 早期记录存的是旧机器的绝对路径，新系统不会去读账本目录以外的文件
        elif (root / candidate).is_file():
            found += 1
        else:
            missing += 1
    return {"with_image": len(paths), "found": found, "absolute_paths": absolute, "missing": missing}


def copy_database(src: Path, dst: Path) -> None:
    # 用 SQLite 在线备份而不是直接拷文件：旧实例还开着、WAL 没落盘时也能拿到一致的快照
    dst.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    target = sqlite3.connect(dst)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()


def migrate(
    src_root: Path,
    email: str,
    *,
    store: AccountStore,
    display_name: str = "",
    password: str = "",
    admin: bool | None = None,
    db_path: Path | None = None,
) -> dict:
    src_db = db_path or src_root / "data" / "cfo.sqlite"
    if not src_db.is_file():
        raise SystemExit(f"找不到旧账本：{src_db}")
    if store.find_user_by_email(email):
        raise SystemExit(f"{email} 已经有账户了，不重复迁移。")

    name = display_name or read_env_value(src_root / ".env", "CFO_OWNER_NAME")
    initial_password = password or secrets.token_urlsafe(9)
    is_admin = admin if admin is not None else store.user_count() == 0
    before = ledger_totals(src_db)

    user = store.create_user(email, initial_password, name, is_admin=is_admin)
    ledger = store.ledger_for(user)
    try:
        copy_database(src_db, ledger.db_path)
        for name_ in EVIDENCE_DIRS:
            source_dir = src_root / "data" / name_
            if source_dir.is_dir():
                shutil.copytree(source_dir, ledger.data_dir / name_, dirs_exist_ok=True)
        after = ledger_totals(ledger.db_path)
        if after != before:
            raise RuntimeError(f"迁移前后账本不一致：{before} → {after}")
        coverage = image_coverage(ledger.db_path, ledger.root)
    except BaseException:
        store.delete_user(user["id"], remove_ledger=True)
        raise

    return {
        "user": user,
        "password": initial_password,
        "ledger_root": str(ledger.root),
        "totals": after,
        "images": coverage,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="把旧的单用户实例迁移成新系统里的一个账户")
    parser.add_argument("--src", required=True, help="旧实例的 cfo_agent_poc 目录")
    parser.add_argument("--email", required=True, help="新账户的登录邮箱")
    parser.add_argument("--name", default="", help="称呼，默认取旧 .env 的 CFO_OWNER_NAME")
    parser.add_argument("--password", default="", help="初始密码，不填则随机生成")
    parser.add_argument("--db", help="旧账本不在 data/cfo.sqlite 时单独指定")
    parser.add_argument("--admin", action="store_true", help="设为管理员（平台里还没有账户时自动成为管理员）")
    parser.add_argument("--home", help="新系统数据目录，默认 CFO_HOME 或 cfo_agent_poc/data")
    args = parser.parse_args()

    store = AccountStore(Path(args.home).resolve() if args.home else default_home())
    result = migrate(
        Path(args.src).expanduser().resolve(),
        args.email,
        store=store,
        display_name=args.name,
        password=args.password,
        admin=True if args.admin else None,
        db_path=Path(args.db).expanduser().resolve() if args.db else None,
    )
    user, totals, images = result["user"], result["totals"], result["images"]
    print(f"已迁移 {user['email']}（{user['display_name']}{'，管理员' if user['is_admin'] else ''}）")
    print(f"  账本目录：{result['ledger_root']}")
    print(f"  交易 {totals['transactions']} 笔，金额合计 {totals['amount_sum']}，原始截图记录 {totals['captures']} 条（与迁移前一致）")
    print(
        f"  截图可回溯 {images['found']}/{images['with_image']}"
        + (f"，旧绝对路径 {images['absolute_paths']} 条" if images["absolute_paths"] else "")
        + (f"，文件缺失 {images['missing']} 条" if images["missing"] else "")
    )
    print(f"  初始密码：{result['password']}（请转告本人登录后在「账户」里修改）")


if __name__ == "__main__":
    main()
