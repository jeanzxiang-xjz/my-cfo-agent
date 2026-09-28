from __future__ import annotations

"""
拿历史人工校正当金标准，回溯评估商户 / 消费内容的解析效果。

默认只读：重新解析 raw_bill_captures 里的每张截图，和 transaction_overrides
里人工改过的 merchant / thing 对比，输出指标和逐条差异。

--apply 时先备份，再把新解析出的 merchant / merchant_legal / platform / thing
回填到没有人工校正的交易上，并用历史校正种下商户别名。分类不动。
"""

import argparse
import json
import sqlite3
from pathlib import Path

try:
    from cfo_agent_poc.backfill_categories import _backup_database, _integrity_check
    from cfo_agent_poc.bill_classifier import LOCAL_CATEGORY_RULES
    from cfo_agent_poc.bill_store import APP_DB, ensure_bill_tables, normalize_merchant_key, parse_bill_text
    from cfo_agent_poc import bill_store
except ModuleNotFoundError:  # Supports direct execution from cfo_agent_poc.
    from backfill_categories import _backup_database, _integrity_check
    from bill_classifier import LOCAL_CATEGORY_RULES
    from bill_store import APP_DB, ensure_bill_tables, normalize_merchant_key, parse_bill_text
    import bill_store


CATEGORY_LABELS = {thing for _, thing, _ in LOCAL_CATEGORY_RULES}


def _fuzzy_match(parsed: str | None, golden: str | None) -> bool:
    """人工值和解析值互相包含就算对：「农耕记」和「农耕记·湘菜小炒·盖码饭」是同一家。"""
    left, right = normalize_merchant_key(parsed), normalize_merchant_key(golden)
    if not left or not right:
        return False
    return left == right or (min(len(left), len(right)) >= 2 and (left in right or right in left))


def _is_platform(merchant: str | None) -> bool:
    checker = getattr(bill_store, "is_platform_entity", None)
    if checker is not None:
        return checker(merchant)
    key = normalize_merchant_key(merchant) or ""
    return "三快在线" in key or key in {"美团", "美团平台商户"}


def evaluate(conn: sqlite3.Connection) -> dict:
    rows = conn.execute(
        """
        select t.transaction_uid, t.raw_capture_hash, t.source, t.payment_app, t.merchant, t.thing,
               r.ocr_text,
               (select value from transaction_overrides o
                where o.raw_capture_hash = t.raw_capture_hash and o.field = 'merchant') as golden_merchant,
               (select value from transaction_overrides o
                where o.raw_capture_hash = t.raw_capture_hash and o.field = 'thing') as golden_thing
        from transactions t
        join raw_bill_captures r on r.capture_hash = t.raw_capture_hash
        """
    ).fetchall()

    merchant_total = merchant_hit = thing_total = thing_hit = 0
    platform_residual = label_only = missing_merchant = 0
    details: list[dict] = []
    for row in rows:
        parsed = parse_bill_text(row["ocr_text"], source=row["source"], source_hint=row["payment_app"] or row["source"])
        if _is_platform(parsed.merchant):
            platform_residual += 1
        if not parsed.merchant:
            missing_merchant += 1
        if parsed.thing in CATEGORY_LABELS or parsed.thing is None:
            label_only += 1

        golden_merchant, golden_thing = row["golden_merchant"], row["golden_thing"]
        merchant_ok = thing_ok = None
        if golden_merchant:
            merchant_total += 1
            merchant_ok = _fuzzy_match(parsed.merchant, golden_merchant)
            merchant_hit += merchant_ok
        if golden_thing:
            thing_total += 1
            thing_ok = _fuzzy_match(parsed.thing, golden_thing)
            thing_hit += thing_ok
        if merchant_ok is False or thing_ok is False:
            details.append({
                "capture": row["raw_capture_hash"][:8],
                "merchant": parsed.merchant,
                "golden_merchant": golden_merchant,
                "thing": parsed.thing,
                "golden_thing": golden_thing,
            })

    return {
        "scanned": len(rows),
        "merchant_accuracy": f"{merchant_hit}/{merchant_total}",
        "thing_accuracy": f"{thing_hit}/{thing_total}",
        "platform_as_merchant": platform_residual,
        "missing_merchant": missing_merchant,
        "thing_label_only": f"{label_only}/{len(rows)}",
        "misses": details,
    }


def _field_overrides(conn: sqlite3.Connection, capture_hash: str) -> set[str]:
    return {
        row[0]
        for row in conn.execute("select field from transaction_overrides where raw_capture_hash = ?", (capture_hash,))
    }


def apply_backfill(conn: sqlite3.Connection) -> dict:
    ensure_bill_tables(conn)
    rows = conn.execute(
        """
        select t.transaction_uid, t.raw_capture_hash, t.source, t.payment_app, t.merchant, t.thing,
               t.classification_status, r.ocr_text
        from transactions t
        join raw_bill_captures r on r.capture_hash = t.raw_capture_hash
        """
    ).fetchall()
    updated = aliases = 0
    for row in rows:
        parsed = parse_bill_text(row["ocr_text"], source=row["source"], source_hint=row["payment_app"] or row["source"])
        overridden = _field_overrides(conn, row["raw_capture_hash"])

        # 历史人工改过的商户，顺手种成别名：下次同一家店的新截图直接用人工名
        if "merchant" in overridden:
            golden = conn.execute(
                "select value from transaction_overrides where raw_capture_hash = ? and field = 'merchant'",
                (row["raw_capture_hash"],),
            ).fetchone()[0]
            for alias in (parsed.merchant, parsed.merchant_legal):
                aliases += bill_store.remember_merchant_alias(conn, alias=alias, merchant=golden)

        assignments: dict[str, object] = {
            "merchant_legal": parsed.merchant_legal,
            "platform": parsed.platform,
            "merchant_quality": parsed.merchant_quality,
        }
        if "merchant" not in overridden:
            assignments["merchant"] = parsed.merchant
        # 新解析只有分类标签、而旧值已经是模型/人工给的具体内容时，保留旧值
        if "thing" not in overridden and "category" not in overridden and (parsed.items or not row["thing"]):
            assignments["thing"] = parsed.thing
        if parsed.merchant_quality != "ok" and "merchant" not in overridden:
            assignments["extraction_status"] = "pending"

        columns = ", ".join(f"{name} = ?" for name in assignments)
        cursor = conn.execute(
            f"update transactions set {columns} where transaction_uid = ?",
            (*assignments.values(), row["transaction_uid"]),
        )
        updated += cursor.rowcount
    return {"updated": updated, "aliases": aliases}


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate merchant/thing parsing against manual corrections.")
    parser.add_argument("--db", default=str(APP_DB))
    parser.add_argument("--apply", action="store_true", help="Backfill merchant/thing after a verified backup.")
    parser.add_argument("--summary", action="store_true", help="Omit per-row misses.")
    args = parser.parse_args()

    path = Path(args.db)
    conn = sqlite3.connect(f"file:{path}?mode={'rw' if args.apply else 'ro'}", uri=True)
    conn.row_factory = sqlite3.Row
    _integrity_check(conn)
    report: dict = {}
    if args.apply:
        report["backup_path"] = str(_backup_database(conn, path.parent / "backups"))
        report["backfill"] = apply_backfill(conn)
        conn.commit()
        _integrity_check(conn)
    report["evaluation"] = evaluate(conn)
    if args.summary:
        report["evaluation"].pop("misses")
    conn.close()
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
