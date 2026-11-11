"""「我的常问」：用户自己定义的快捷提问。

【猜你想问】是模板库现抽的（legacy-controller.js 的 PROMPT_LIBRARY），【常用】是写死的
五枚——两者都只覆盖得到通用的消费结构。每个人真正天天想问的那句（奶茶账、通勤、房贷、
猫粮）只有本人知道，所以这一档交给用户自己写，并且落库：换浏览器、清缓存都还在。

结构照抄 category_catalog：同一套连接/迁移/错误码写法，PromptError 直接继承 CategoryError，
server 里现成的 category_error() 就能接住，不必再加一条错误渲染分支。
"""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

try:
    from cfo_agent_poc.category_catalog import CategoryError
    from cfo_agent_poc.ledger_time import ledger_now_iso
except ModuleNotFoundError:  # Supports direct execution from cfo_agent_poc.
    from category_catalog import CategoryError
    from ledger_time import ledger_now_iso


# 胶囊要和另外两档挤在同一条轨道里，条数无节制就成了第二个账本目录。
PROMPT_LIMIT = 12
MAX_LABEL_LENGTH = 6
MAX_QUESTION_LENGTH = 60


class PromptError(CategoryError):
    def __init__(self, message: str, *, code: str = "invalid_prompt", status: int = 400, detail: dict | None = None):
        super().__init__(message, code=code, status=status, detail=detail)


def _connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(Path(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def ensure_prompt_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        create table if not exists custom_prompts (
            id text primary key,
            label text not null collate nocase unique,
            question text not null,
            follow_period integer not null default 1,
            sort_order integer not null,
            created_at text not null,
            updated_at text not null
        )
        """
    )


def _serialize_rows(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "select * from custom_prompts order by sort_order, created_at, id"
    ).fetchall()
    items = []
    for row in rows:
        item = dict(row)
        item["follow_period"] = bool(item["follow_period"])
        items.append(item)
    return items


def list_prompts(db_path: str | Path) -> dict:
    conn = _connect(db_path)
    try:
        ensure_prompt_tables(conn)
        items = _serialize_rows(conn)
        return {"ok": True, "limit": PROMPT_LIMIT, "prompts": items}
    finally:
        conn.close()


def _clean_label(value: object) -> str:
    label = " ".join(str(value or "").split())
    if not label:
        raise PromptError("标签不能为空。", code="empty_label")
    if len(label) > MAX_LABEL_LENGTH:
        raise PromptError(f"标签最多 {MAX_LABEL_LENGTH} 个字。", code="label_too_long")
    return label


def _clean_question(value: object) -> str:
    question = " ".join(str(value or "").split())
    if len(question) < 2:
        raise PromptError("问题太短了，写清楚想问什么。", code="empty_question")
    if len(question) > MAX_QUESTION_LENGTH:
        raise PromptError(f"问题最多 {MAX_QUESTION_LENGTH} 个字。", code="question_too_long")
    return question


def _next_sort_order(conn: sqlite3.Connection) -> int:
    row = conn.execute("select max(sort_order) from custom_prompts").fetchone()
    return 0 if row[0] is None else int(row[0]) + 1


def create_prompt(db_path: str | Path, payload: dict) -> dict:
    label = _clean_label(payload.get("label"))
    question = _clean_question(payload.get("question"))
    follow_period = 0 if payload.get("follow_period") is False else 1
    prompt_id = f"cp_{uuid.uuid4().hex[:12]}"
    now = ledger_now_iso()
    conn = _connect(db_path)
    try:
        ensure_prompt_tables(conn)
        count = conn.execute("select count(*) from custom_prompts").fetchone()[0]
        if count >= PROMPT_LIMIT:
            raise PromptError(
                f"最多只能存 {PROMPT_LIMIT} 条常问，先删掉一条再加。",
                code="prompt_limit",
                status=409,
            )
        try:
            conn.execute(
                """
                insert into custom_prompts
                    (id, label, question, follow_period, sort_order, created_at, updated_at)
                values (?, ?, ?, ?, ?, ?, ?)
                """,
                (prompt_id, label, question, follow_period, _next_sort_order(conn), now, now),
            )
        except sqlite3.IntegrityError:
            raise PromptError("已经有同名标签了，换一个。", code="duplicate_label", status=409) from None
        conn.commit()
        return next(item for item in _serialize_rows(conn) if item["id"] == prompt_id)
    finally:
        conn.close()


def patch_prompt(db_path: str | Path, prompt_id: str, payload: dict) -> dict:
    allowed = {"label", "question", "follow_period"}
    unknown = set(payload) - allowed
    if unknown:
        raise PromptError(f"不支持修改这些字段：{'、'.join(sorted(unknown))}。", code="unknown_field")
    conn = _connect(db_path)
    try:
        ensure_prompt_tables(conn)
        row = conn.execute("select * from custom_prompts where id = ?", (prompt_id,)).fetchone()
        if not row:
            raise PromptError("没有找到这条常问。", code="not_found", status=404)

        updates: dict[str, object] = {}
        if "label" in payload:
            updates["label"] = _clean_label(payload["label"])
        if "question" in payload:
            updates["question"] = _clean_question(payload["question"])
        if "follow_period" in payload:
            updates["follow_period"] = 0 if payload["follow_period"] is False else 1
        if not updates:
            return next(item for item in _serialize_rows(conn) if item["id"] == prompt_id)

        now = ledger_now_iso()
        updates["updated_at"] = now
        assignments = ", ".join(f"{key} = ?" for key in updates)
        try:
            conn.execute(
                f"update custom_prompts set {assignments} where id = ?",
                (*updates.values(), prompt_id),
            )
        except sqlite3.IntegrityError:
            raise PromptError("已经有同名标签了，换一个。", code="duplicate_label", status=409) from None
        conn.commit()
        return next(item for item in _serialize_rows(conn) if item["id"] == prompt_id)
    finally:
        conn.close()


def delete_prompt(db_path: str | Path, prompt_id: str) -> dict:
    conn = _connect(db_path)
    try:
        ensure_prompt_tables(conn)
        row = conn.execute("select 1 from custom_prompts where id = ?", (prompt_id,)).fetchone()
        if not row:
            raise PromptError("没有找到这条常问。", code="not_found", status=404)
        conn.execute("delete from custom_prompts where id = ?", (prompt_id,))
        _normalize_sort_order(conn)
        conn.commit()
        return {"ok": True, "deleted_id": prompt_id}
    finally:
        conn.close()


def _normalize_sort_order(conn: sqlite3.Connection) -> None:
    """删除或重排后把 sort_order 重新压回 0..n-1，别让空洞越攒越大。"""
    rows = conn.execute("select id from custom_prompts order by sort_order, created_at, id").fetchall()
    for index, row in enumerate(rows):
        conn.execute("update custom_prompts set sort_order = ? where id = ?", (index, row[0]))


def set_prompt_order(db_path: str | Path, prompt_ids: object) -> list[dict]:
    """接受一份完整的 id 顺序表。前端的 ↑/↓ 每次都发全量，缺项就是前端状态和库不同步了。"""
    if not isinstance(prompt_ids, list):
        raise PromptError("顺序必须是一组常问 id。", code="invalid_order")
    ids = [str(value) for value in prompt_ids]
    if len(set(ids)) != len(ids):
        raise PromptError("顺序里不能有重复项。", code="duplicate_order")
    conn = _connect(db_path)
    try:
        ensure_prompt_tables(conn)
        existing = [row[0] for row in conn.execute("select id from custom_prompts").fetchall()]
        if set(ids) != set(existing):
            raise PromptError("顺序表和现有的常问对不上，请刷新后再试。", code="order_mismatch", status=409)
        now = ledger_now_iso()
        for index, prompt_id in enumerate(ids):
            conn.execute(
                "update custom_prompts set sort_order = ?, updated_at = ? where id = ?",
                (index, now, prompt_id),
            )
        conn.commit()
        return _serialize_rows(conn)
    finally:
        conn.close()
