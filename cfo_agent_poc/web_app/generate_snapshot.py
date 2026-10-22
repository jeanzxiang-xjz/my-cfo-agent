from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.environ.get("CFO_DB_PATH") or ROOT / "data" / "cfo.sqlite")
DEMO_MODE = os.environ.get("CFO_DEMO") == "1"
OUT_PATH = Path(__file__).resolve().parent / "data.json"

CORE_CORRECTION_FIELDS = ("amount", "paid_at", "merchant")


def correction_fields(record: dict) -> list[str]:
    """Return the core facts that still need a human correction."""
    missing: list[str] = []
    try:
        amount = float(record.get("amount") or 0)
    except (TypeError, ValueError):
        amount = 0
    # 全额退款的支出按净额记成 0，金额是对的，不用补
    if amount <= 0 and not (amount == 0 and record.get("status") == "refunded"):
        missing.append("amount")

    paid_at = record.get("paid_at")
    try:
        if not paid_at:
            raise ValueError
        datetime.fromisoformat(str(paid_at))
    except ValueError:
        missing.append("paid_at")

    if not str(record.get("merchant") or "").strip():
        missing.append("merchant")
    return missing


def _parse_warnings(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    try:
        parsed = json.loads(str(value or "[]"))
    except json.JSONDecodeError:
        return [str(value)] if value else []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def is_demo_database() -> bool:
    """本地免登录验证模式不等于当前读取的是演示数据库。"""
    return DEMO_MODE and DB_PATH.name == "cfo-demo.sqlite"


def build_payload(db_path: Path | str | None = None) -> dict:
    selected_db = Path(db_path) if db_path is not None else DB_PATH
    conn = sqlite3.connect(selected_db)
    conn.row_factory = sqlite3.Row
    columns = {row[1] for row in conn.execute("pragma table_info(transactions)")}
    classification_source = (
        "classification_source"
        if "classification_source" in columns
        else "case when category = 'uncategorized' then 'none' else 'legacy' end as classification_source"
    )
    classification_confidence = (
        "classification_confidence"
        if "classification_confidence" in columns
        else "0 as classification_confidence"
    )
    classification_status = (
        "classification_status"
        if "classification_status" in columns
        else "case when category = 'uncategorized' then 'pending' else 'resolved' end as classification_status"
    )
    classification_reason = (
        "classification_reason"
        if "classification_reason" in columns
        else "null as classification_reason"
    )
    parse_warnings = "parse_warnings" if "parse_warnings" in columns else "'[]' as parse_warnings"
    reviewed_at = "reviewed_at" if "reviewed_at" in columns else "null as reviewed_at"
    rows = conn.execute(
        f"""
        select
            transaction_uid,
            payment_app,
            amount,
            direction,
            status,
            paid_at,
            merchant,
            platform,
            thing,
            category,
            product,
            payment_method,
            bank_name,
            card_type,
            card_last4,
            confidence,
            {classification_source},
            {classification_confidence},
            {classification_status},
            {classification_reason},
            {parse_warnings},
            {reviewed_at},
            t.created_at,
            c.captured_at
        from transactions t
        left join raw_bill_captures c on c.capture_hash = t.raw_capture_hash
        order by coalesce(t.paid_at, c.captured_at, t.created_at) desc, t.transaction_uid desc
        """
    ).fetchall()
    conn.close()

    transactions = []
    for row in rows:
        record = dict(row)
        record["parse_warnings"] = _parse_warnings(record.get("parse_warnings"))
        record["correction_fields"] = correction_fields(record)
        record["analysis_eligible"] = not record["correction_fields"]
        transactions.append(record)

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "demo": DEMO_MODE and selected_db.name == "cfo-demo.sqlite",
        "classification_pending_count": sum(
            1 for row in transactions if row["classification_status"] == "pending"
        ),
        "correction_pending_count": sum(1 for row in transactions if not row["analysis_eligible"]),
        "transactions": transactions,
    }


def write_snapshot(path: Path = OUT_PATH) -> dict:
    payload = build_payload()
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def main() -> None:
    payload = write_snapshot()
    print(f"wrote {OUT_PATH} with {len(payload['transactions'])} transactions")


if __name__ == "__main__":
    main()
