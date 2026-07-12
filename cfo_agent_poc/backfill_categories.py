from __future__ import annotations

import argparse
import json
import sqlite3
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

try:
    from cfo_agent_poc.bill_store import (
        APP_DB,
        ParsedBill,
        apply_persisted_classification,
        ensure_bill_tables,
        is_generic_merchant_label,
        is_stable_merchant,
        normalize_merchant_key,
        parse_bill_text,
        remember_merchant_classification,
    )
except ModuleNotFoundError:  # Supports direct execution from cfo_agent_poc.
    from bill_store import (
        APP_DB,
        ParsedBill,
        apply_persisted_classification,
        ensure_bill_tables,
        is_generic_merchant_label,
        is_stable_merchant,
        normalize_merchant_key,
        parse_bill_text,
        remember_merchant_classification,
    )


FACT_FIELDS = (
    "source",
    "payment_app",
    "amount",
    "direction",
    "status",
    "paid_at",
    "merchant",
    "platform",
    "thing",
    "category",
    "product",
    "payment_method",
    "bank_name",
    "card_type",
    "card_last4",
    "acquirer",
    "clearing_org",
    "transaction_id",
    "merchant_order_id",
    "confidence",
)


def _integrity_check(conn: sqlite3.Connection) -> None:
    result = conn.execute("pragma integrity_check").fetchone()[0]
    if result != "ok":
        raise RuntimeError(f"SQLite integrity check failed: {result}")


def _backup_database(conn: sqlite3.Connection, backup_dir: Path) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = backup_dir / f"cfo-before-reprocess-{stamp}.sqlite"
    destination = sqlite3.connect(path)
    try:
        conn.backup(destination)
        _integrity_check(destination)
    finally:
        destination.close()
    return path


def _manual_overrides(row: sqlite3.Row, parsed: ParsedBill) -> dict[str, str | None]:
    overrides: dict[str, str | None] = {}
    old_merchant = row["merchant"]
    if (
        old_merchant
        and old_merchant != parsed.merchant
        and not is_generic_merchant_label(old_merchant)
    ):
        overrides["merchant"] = old_merchant
        if row["thing"] != parsed.thing and row["thing"]:
            overrides["thing"] = row["thing"]
    if row["category"] and row["category"] != "uncategorized" and row["category"] != parsed.category:
        overrides["category"] = row["category"]
        if row["thing"]:
            overrides["thing"] = row["thing"]
    return overrides


def _apply_inline_overrides(parsed: ParsedBill, overrides: dict[str, str | None]) -> None:
    for field in ("merchant", "thing", "category", "product"):
        if field in overrides:
            setattr(parsed, field, overrides[field])
    if "category" in overrides:
        parsed.category_confidence = 1.0
        parsed.classification_source = "manual_override"
        parsed.classification_status = "resolved"
        parsed.classification_reason = "preserved_existing_value"


def _changed_fields(row: sqlite3.Row, parsed: ParsedBill) -> dict[str, dict]:
    changes: dict[str, dict] = {}
    parsed_values = asdict(parsed)
    for field in ("transaction_uid", *FACT_FIELDS):
        old = row[field]
        new = parsed_values[field]
        if old != new:
            changes[field] = {"old": old, "new": new}
    return changes


def _load_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        select t.*
        from transactions t
        where t.raw_capture_hash is not null
        order by t.paid_at, t.created_at
        """
    ).fetchall()


def _write_overrides(
    conn: sqlite3.Connection,
    raw_capture_hash: str,
    overrides: dict[str, str | None],
) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    conn.executemany(
        """
        insert into transaction_overrides (raw_capture_hash, field, value, created_at)
        values (?, ?, ?, ?)
        on conflict(raw_capture_hash, field) do update set value = excluded.value
        """,
        [(raw_capture_hash, field, value, now) for field, value in overrides.items()],
    )


def _update_transaction(conn: sqlite3.Connection, old_uid: str, capture_hash: str, parsed: ParsedBill) -> bool:
    duplicate = conn.execute(
        "select raw_capture_hash from transactions where transaction_uid = ? and transaction_uid <> ?",
        (parsed.transaction_uid, old_uid),
    ).fetchone()
    if duplicate:
        conn.execute("delete from transactions where transaction_uid = ?", (old_uid,))
        return False

    conn.execute(
        """
        update transactions set
            transaction_uid = ?, source = ?, payment_app = ?, amount = ?, direction = ?, status = ?,
            paid_at = ?, merchant = ?, platform = ?, thing = ?, category = ?, product = ?,
            payment_method = ?, bank_name = ?, card_type = ?, card_last4 = ?, acquirer = ?,
            clearing_org = ?, transaction_id = ?, merchant_order_id = ?, confidence = ?,
            classification_source = ?, classification_confidence = ?, classification_status = ?,
            classification_reason = ?, parse_warnings = ?, raw_text = ?
        where raw_capture_hash = ? and transaction_uid = ?
        """,
        (
            parsed.transaction_uid,
            parsed.source,
            parsed.payment_app,
            parsed.amount,
            parsed.direction,
            parsed.status,
            parsed.paid_at,
            parsed.merchant,
            parsed.platform,
            parsed.thing,
            parsed.category,
            parsed.product,
            parsed.payment_method,
            parsed.bank_name,
            parsed.card_type,
            parsed.card_last4,
            parsed.acquirer,
            parsed.clearing_org,
            parsed.transaction_id,
            parsed.merchant_order_id,
            parsed.confidence,
            parsed.classification_source,
            parsed.category_confidence,
            parsed.classification_status,
            parsed.classification_reason,
            json.dumps(parsed.parse_warnings, ensure_ascii=False),
            parsed.raw_text,
            capture_hash,
            old_uid,
        ),
    )
    return True


def _rebuild_memory(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        """
        select merchant, category, thing, max(classification_confidence) as confidence
        from transactions
        where classification_status = 'resolved' and category not in ('uncategorized', 'personal_transfer')
        group by merchant, category, thing
        """
    ).fetchall()
    grouped: dict[str, list[sqlite3.Row]] = {}
    for row in rows:
        if not is_stable_merchant(row["merchant"]):
            continue
        grouped.setdefault(normalize_merchant_key(row["merchant"]) or "", []).append(row)
    for candidates in grouped.values():
        if len({row["category"] for row in candidates}) != 1:
            continue
        row = max(candidates, key=lambda item: float(item["confidence"] or 0))
        remember_merchant_classification(
            conn,
            merchant=row["merchant"],
            category=row["category"],
            thing=row["thing"],
            confidence=float(row["confidence"] or 0.9),
            source="ledger_history",
        )


def reprocess_ledger(
    db_path: str | Path = APP_DB,
    *,
    apply: bool = False,
    backup_dir: str | Path | None = None,
) -> dict:
    path = Path(db_path)
    uri = f"file:{path}?mode={'rw' if apply else 'ro'}"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    _integrity_check(conn)
    backup_path: Path | None = None
    if apply:
        backup_path = _backup_database(conn, Path(backup_dir or path.parent / "backups"))
        ensure_bill_tables(conn)

    rows = _load_rows(conn)
    details: list[dict] = []
    pending = 0
    for row in rows:
        parsed = parse_bill_text(
            row["raw_text"],
            source=row["source"],
            source_hint=row["payment_app"] or row["source"],
        )
        overrides = _manual_overrides(row, parsed)
        _apply_inline_overrides(parsed, overrides)
        if parsed.classification_status == "pending":
            pending += 1
        changes = _changed_fields(row, parsed)
        if changes:
            details.append({
                "raw_capture_hash": row["raw_capture_hash"],
                "old_transaction_uid": row["transaction_uid"],
                "new_transaction_uid": parsed.transaction_uid,
                "changes": changes,
                "overrides": overrides,
            })
        if not apply:
            continue
        if overrides:
            _write_overrides(conn, row["raw_capture_hash"], overrides)
        parsed = apply_persisted_classification(conn, parsed, row["raw_capture_hash"])
        _update_transaction(conn, row["transaction_uid"], row["raw_capture_hash"], parsed)

    if apply:
        _rebuild_memory(conn)
        conn.commit()
        _integrity_check(conn)
    final_count = conn.execute("select count(*) from transactions").fetchone()[0]
    conn.close()
    return {
        "mode": "apply" if apply else "dry-run",
        "database": str(path),
        "backup_path": str(backup_path) if backup_path else None,
        "scanned": len(rows),
        "changed": len(details),
        "pending": pending,
        "final_count": final_count,
        "details": details,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit and safely reprocess CFO transactions.")
    parser.add_argument("--db", default=str(APP_DB))
    parser.add_argument("--apply", action="store_true", help="Apply changes after creating a verified backup.")
    parser.add_argument("--backup-dir")
    args = parser.parse_args()
    report = reprocess_ledger(args.db, apply=args.apply, backup_dir=args.backup_dir)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
