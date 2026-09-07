from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime
from pathlib import Path


MAX_PRIMARY_CATEGORIES = 5
RESERVED_CATEGORY_ID = "uncategorized"
ALLOWED_ICON_KEYS = (
    "cup", "meal", "car", "bolt", "bag", "fruit", "book", "cart",
    "train", "heart", "home", "phone", "ticket", "wallet", "drop",
    "pencil", "screen", "plane", "gift", "transfer", "circle", "pet",
    "medicine", "parcel", "beauty", "delivery", "apparel",
)
ALLOWED_COLOR_TOKENS = tuple(f"cat-{index}" for index in range(1, 9))

# The immutable ids and system names are classification semantics. display_name is
# the user-facing layer and is only used to seed a new catalog.
DEFAULT_CATEGORIES = (
    ("coffee_tea", "咖啡茶饮", "咖啡/奶茶", "cup", "cat-1"),
    ("food_delivery", "餐饮外卖", "外卖/餐饮", "meal", "cat-2"),
    ("parking", "停车缴费", "停车交通", "car", "cat-3"),
    ("car_charging", "车辆充电", "车辆充电", "bolt", "cat-4"),
    ("auto", "爱车养车", "爱车养车", "car", "cat-5"),
    ("groceries", "超市便利", "超市便利", "bag", "cat-6"),
    ("fruit", "水果", "水果鲜果", "fruit", "cat-7"),
    ("bakery", "烘焙", "烘焙面包", "meal", "cat-1"),
    ("education", "证券考试", "教育考试", "book", "cat-2"),
    ("books", "图书", "图书书店", "book", "cat-3"),
    ("ecommerce", "网购", "网购", "cart", "cat-4"),
    ("transport", "交通出行", "交通", "train", "cat-5"),
    ("healthcare", "医疗", "医疗", "heart", "cat-6"),
    ("investment", "理财", "投资理财", "wallet", "cat-7"),
    ("property", "物业服务", "物业生活", "home", "cat-1"),
    ("telecom", "通信充值", "通信充值", "phone", "cat-2"),
    ("entertainment", "演出票务", "演出票务", "ticket", "cat-3"),
    ("credit_repayment", "信用借还", "信用借还", "wallet", "cat-4"),
    ("utilities", "水电燃缴费", "水电燃缴费", "drop", "cat-5"),
    ("stationery", "文具用品", "文具用品", "pencil", "cat-6"),
    ("digital_services", "数字服务", "数字服务", "screen", "cat-7"),
    ("general_shopping", "日常购物", "日常购物", "bag", "cat-1"),
    ("leisure_travel", "休闲旅行", "旅行休闲", "plane", "cat-2"),
    ("lottery", "彩票", "彩票", "gift", "cat-3"),
    ("personal_transfer", "个人转账", "个人转账", "transfer", "cat-4"),
    ("uncategorized", "未分类", "未分类", "circle", "cat-8"),
)

DEFAULT_PRIMARY_IDS = ("books", "food_delivery", "groceries", "property", "car_charging")


class CategoryError(ValueError):
    def __init__(self, message: str, *, code: str = "invalid_category", status: int = 400, detail: dict | None = None):
        super().__init__(message)
        self.code = code
        self.status = status
        self.detail = detail or {}


def _connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(Path(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def ensure_category_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        create table if not exists category_catalog (
            id text primary key,
            display_name text not null collate nocase unique,
            system_name text not null,
            icon_key text not null,
            color_token text not null,
            is_enabled integer not null default 1,
            is_system integer not null default 1,
            primary_order integer,
            created_at text not null,
            updated_at text not null
        )
        """
    )
    conn.execute(
        """
        create table if not exists category_catalog_meta (
            singleton integer primary key check (singleton = 1),
            version integer not null,
            updated_at text not null
        )
        """
    )
    now = datetime.now().isoformat(timespec="seconds")
    conn.execute(
        "insert or ignore into category_catalog_meta (singleton, version, updated_at) values (1, 1, ?)",
        (now,),
    )
    for category_id, system_name, display_name, icon_key, color_token in DEFAULT_CATEGORIES:
        primary_order = DEFAULT_PRIMARY_IDS.index(category_id) if category_id in DEFAULT_PRIMARY_IDS else None
        conn.execute(
            """
            insert or ignore into category_catalog
                (id, display_name, system_name, icon_key, color_token, is_enabled,
                 is_system, primary_order, created_at, updated_at)
            values (?, ?, ?, ?, ?, 1, 1, ?, ?, ?)
            """,
            (category_id, display_name, system_name, icon_key, color_token, primary_order, now, now),
        )


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "select 1 from sqlite_master where type = 'table' and name = ?", (name,)
    ).fetchone() is not None


def _reference_counts(conn: sqlite3.Connection) -> tuple[dict[str, int], dict[str, int], dict[str, int]]:
    transaction_counts: dict[str, int] = {}
    memory_counts: dict[str, int] = {}
    override_counts: dict[str, int] = {}
    if _table_exists(conn, "transactions"):
        transaction_counts = dict(conn.execute(
            "select category, count(*) from transactions group by category"
        ).fetchall())
    if _table_exists(conn, "merchant_category_memory"):
        memory_counts = dict(conn.execute(
            "select category, count(*) from merchant_category_memory group by category"
        ).fetchall())
    if _table_exists(conn, "transaction_overrides"):
        override_counts = dict(conn.execute(
            "select value, count(*) from transaction_overrides where field = 'category' group by value"
        ).fetchall())
    return transaction_counts, memory_counts, override_counts


def _serialize_rows(conn: sqlite3.Connection) -> list[dict]:
    tx_counts, memory_counts, override_counts = _reference_counts(conn)
    rows = conn.execute(
        """
        select * from category_catalog
        order by case when primary_order is null then 1 else 0 end,
                 primary_order, is_enabled desc, display_name collate nocase
        """
    ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["is_enabled"] = bool(item["is_enabled"])
        item["is_system"] = bool(item["is_system"])
        item["is_primary"] = item["primary_order"] is not None
        item["transaction_count"] = int(tx_counts.get(item["id"], 0))
        item["merchant_memory_count"] = int(memory_counts.get(item["id"], 0))
        item["override_count"] = int(override_counts.get(item["id"], 0))
        item["can_delete"] = (
            not item["is_system"]
            and item["transaction_count"] == 0
            and item["merchant_memory_count"] == 0
            and item["override_count"] == 0
        )
        item["is_reserved"] = item["id"] == RESERVED_CATEGORY_ID
        result.append(item)
    return result


def get_catalog(db_path: str | Path, *, demo: bool = False) -> dict:
    conn = _connect(db_path)
    try:
        ensure_category_tables(conn)
        conn.commit()
        items = _serialize_rows(conn)
        version = conn.execute("select version from category_catalog_meta where singleton = 1").fetchone()[0]
    finally:
        conn.close()
    return {
        "ok": True,
        "version": int(version),
        "demo": bool(demo),
        "primary_limit": MAX_PRIMARY_CATEGORIES,
        "enabled_count": sum(1 for item in items if item["is_enabled"]),
        "primary_count": sum(1 for item in items if item["is_primary"]),
        "categories": items,
        "allowed_icons": list(ALLOWED_ICON_KEYS),
        "allowed_colors": list(ALLOWED_COLOR_TOKENS),
    }


def category_version(db_path: str | Path) -> int:
    try:
        conn = _connect(db_path)
        ensure_category_tables(conn)
        conn.commit()
        row = conn.execute("select version from category_catalog_meta where singleton = 1").fetchone()
        conn.close()
        return int(row[0]) if row else 1
    except sqlite3.Error:
        return 1


def category_labels(db_path: str | Path, *, enabled_only: bool = False) -> dict[str, str]:
    conn = _connect(db_path)
    try:
        ensure_category_tables(conn)
        where = " where is_enabled = 1" if enabled_only else ""
        rows = conn.execute(f"select id, display_name from category_catalog{where}").fetchall()
        conn.commit()
        return {row["id"]: row["display_name"] for row in rows}
    finally:
        conn.close()


def model_taxonomy(db_path: str | Path) -> dict[str, str]:
    conn = _connect(db_path)
    try:
        ensure_category_tables(conn)
        rows = conn.execute(
            "select id, display_name from category_catalog where is_enabled = 1 and id != ? order by is_system desc, display_name",
            (RESERVED_CATEGORY_ID,),
        ).fetchall()
        conn.commit()
        return {row["id"]: row["display_name"] for row in rows}
    finally:
        conn.close()


def is_enabled_category(conn: sqlite3.Connection, category_id: str) -> bool:
    ensure_category_tables(conn)
    row = conn.execute(
        "select is_enabled from category_catalog where id = ?", (category_id,)
    ).fetchone()
    return bool(row and row[0])


def _clean_name(value: object) -> str:
    name = " ".join(str(value or "").split())
    if not name:
        raise CategoryError("分类名称不能为空。", code="empty_name")
    if len(name) > 20:
        raise CategoryError("分类名称最多 20 个字符。", code="name_too_long")
    return name


def _validate_appearance(icon_key: object, color_token: object) -> tuple[str, str]:
    icon = str(icon_key or "circle")
    color = str(color_token or "cat-1")
    if icon not in ALLOWED_ICON_KEYS:
        raise CategoryError("这个图标不在可选范围里。", code="invalid_icon")
    if color not in ALLOWED_COLOR_TOKENS:
        raise CategoryError("这个颜色不在安全色板里。", code="invalid_color")
    return icon, color


def _bump_version(conn: sqlite3.Connection, now: str) -> None:
    conn.execute(
        "update category_catalog_meta set version = version + 1, updated_at = ? where singleton = 1",
        (now,),
    )


def create_category(db_path: str | Path, payload: dict) -> dict:
    name = _clean_name(payload.get("display_name"))
    icon, color = _validate_appearance(payload.get("icon_key"), payload.get("color_token"))
    category_id = f"custom_{uuid.uuid4().hex[:12]}"
    now = datetime.now().isoformat(timespec="seconds")
    conn = _connect(db_path)
    try:
        ensure_category_tables(conn)
        try:
            conn.execute(
                """
                insert into category_catalog
                    (id, display_name, system_name, icon_key, color_token, is_enabled,
                     is_system, primary_order, created_at, updated_at)
                values (?, ?, ?, ?, ?, 1, 0, null, ?, ?)
                """,
                (category_id, name, name, icon, color, now, now),
            )
        except sqlite3.IntegrityError:
            raise CategoryError("已经有同名分类，请换一个名称。", code="duplicate_name", status=409) from None
        _bump_version(conn, now)
        conn.commit()
        return next(item for item in _serialize_rows(conn) if item["id"] == category_id)
    finally:
        conn.close()


def patch_category(db_path: str | Path, category_id: str, payload: dict) -> dict:
    allowed = {"display_name", "icon_key", "color_token", "is_enabled", "is_primary"}
    unknown = set(payload) - allowed
    if unknown:
        raise CategoryError(f"不支持修改这些字段：{'、'.join(sorted(unknown))}。", code="unknown_field")
    conn = _connect(db_path)
    try:
        ensure_category_tables(conn)
        row = conn.execute("select * from category_catalog where id = ?", (category_id,)).fetchone()
        if not row:
            raise CategoryError("没有找到这个分类。", code="not_found", status=404)
        if category_id == RESERVED_CATEGORY_ID and payload:
            raise CategoryError("“未分类”是保留分类，不能修改。", code="reserved_category", status=409)

        updates: dict[str, object] = {}
        if "display_name" in payload:
            updates["display_name"] = _clean_name(payload["display_name"])
        if "icon_key" in payload or "color_token" in payload:
            icon, color = _validate_appearance(
                payload.get("icon_key", row["icon_key"]), payload.get("color_token", row["color_token"])
            )
            updates.update({"icon_key": icon, "color_token": color})
        if "is_enabled" in payload:
            updates["is_enabled"] = int(bool(payload["is_enabled"]))
            if not updates["is_enabled"]:
                updates["primary_order"] = None
        if "is_primary" in payload:
            wants_primary = bool(payload["is_primary"])
            if wants_primary and not bool(updates.get("is_enabled", row["is_enabled"])):
                raise CategoryError("请先启用分类，再设为常用。", code="disabled_primary", status=409)
            if wants_primary and row["primary_order"] is None:
                count = conn.execute("select count(*) from category_catalog where primary_order is not null").fetchone()[0]
                if count >= MAX_PRIMARY_CATEGORIES:
                    raise CategoryError("常用分类最多 5 个，请先移除一个。", code="primary_limit", status=409)
                updates["primary_order"] = int(count)
            elif not wants_primary:
                updates["primary_order"] = None

        if not updates:
            return next(item for item in _serialize_rows(conn) if item["id"] == category_id)
        now = datetime.now().isoformat(timespec="seconds")
        updates["updated_at"] = now
        try:
            conn.execute(
                f"update category_catalog set {', '.join(f'{key} = ?' for key in updates)} where id = ?",
                (*updates.values(), category_id),
            )
        except sqlite3.IntegrityError:
            raise CategoryError("已经有同名分类，请换一个名称。", code="duplicate_name", status=409) from None
        _normalize_primary_order(conn)
        _bump_version(conn, now)
        conn.commit()
        return next(item for item in _serialize_rows(conn) if item["id"] == category_id)
    finally:
        conn.close()


def _normalize_primary_order(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        "select id from category_catalog where primary_order is not null order by primary_order, updated_at, id"
    ).fetchall()
    for index, row in enumerate(rows):
        conn.execute("update category_catalog set primary_order = ? where id = ?", (index, row[0]))


def set_primary_order(db_path: str | Path, category_ids: object) -> list[dict]:
    if not isinstance(category_ids, list) or len(category_ids) > MAX_PRIMARY_CATEGORIES:
        raise CategoryError("常用分类顺序必须是最多 5 个分类。", code="invalid_primary_order")
    ids = [str(value) for value in category_ids]
    if len(set(ids)) != len(ids):
        raise CategoryError("常用分类顺序里不能有重复项。", code="duplicate_primary")
    conn = _connect(db_path)
    try:
        ensure_category_tables(conn)
        if ids:
            placeholders = ",".join("?" for _ in ids)
            rows = conn.execute(
                f"select id, is_enabled from category_catalog where id in ({placeholders})", ids
            ).fetchall()
            found = {row["id"]: bool(row["is_enabled"]) for row in rows}
            if set(found) != set(ids):
                raise CategoryError("常用分类中包含不存在的分类。", code="not_found", status=404)
            if not all(found.values()):
                raise CategoryError("已停用分类不能设为常用。", code="disabled_primary", status=409)
            if RESERVED_CATEGORY_ID in ids:
                raise CategoryError("“未分类”不能设为常用。", code="reserved_category", status=409)
        now = datetime.now().isoformat(timespec="seconds")
        conn.execute("update category_catalog set primary_order = null")
        for index, category_id in enumerate(ids):
            conn.execute(
                "update category_catalog set primary_order = ?, updated_at = ? where id = ?",
                (index, now, category_id),
            )
        _bump_version(conn, now)
        conn.commit()
        return _serialize_rows(conn)
    finally:
        conn.close()


def delete_category(db_path: str | Path, category_id: str) -> dict:
    conn = _connect(db_path)
    try:
        ensure_category_tables(conn)
        item = next((item for item in _serialize_rows(conn) if item["id"] == category_id), None)
        if not item:
            raise CategoryError("没有找到这个分类。", code="not_found", status=404)
        if item["is_system"]:
            raise CategoryError("系统分类不能删除，可以选择停用。", code="system_category", status=409)
        if not item["can_delete"]:
            detail = {
                "transaction_count": item["transaction_count"],
                "merchant_memory_count": item["merchant_memory_count"],
                "override_count": item["override_count"],
                "suggestion": "disable",
            }
            raise CategoryError("这个分类仍被交易或商户记忆引用，请改为停用。", code="category_in_use", status=409, detail=detail)
        conn.execute("delete from category_catalog where id = ?", (category_id,))
        now = datetime.now().isoformat(timespec="seconds")
        _bump_version(conn, now)
        conn.commit()
        return {"ok": True, "deleted_id": category_id}
    finally:
        conn.close()
