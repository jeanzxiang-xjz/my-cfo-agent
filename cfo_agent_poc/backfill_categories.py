from __future__ import annotations

import argparse
from collections import Counter

from bill_store import connect, detect_category_and_thing


def build_haystack(row: dict) -> str:
    return "\n".join(
        str(row.get(key) or "")
        for key in ["merchant", "platform", "product", "payment_method", "raw_text"]
    )


def backfill_categories(dry_run: bool = False) -> list[dict]:
    conn = connect()
    conn.row_factory = None
    columns = [
        "transaction_uid",
        "merchant",
        "platform",
        "product",
        "payment_method",
        "raw_text",
    ]
    rows = conn.execute(
        f"""
        select {", ".join(columns)}
        from transactions
        where category = 'uncategorized'
        order by paid_at desc
        """
    ).fetchall()

    changes: list[dict] = []
    for values in rows:
        row = dict(zip(columns, values))
        category, thing = detect_category_and_thing(build_haystack(row), row.get("product"))
        if category == "uncategorized":
            continue
        changes.append({
            "transaction_uid": row["transaction_uid"],
            "merchant": row.get("merchant") or "",
            "product": row.get("product") or "",
            "category": category,
            "thing": thing,
        })

    if not dry_run and changes:
        conn.executemany(
            """
            update transactions
            set category = ?, thing = coalesce(?, thing)
            where transaction_uid = ? and category = 'uncategorized'
            """,
            [(item["category"], item["thing"], item["transaction_uid"]) for item in changes],
        )
        conn.commit()
    conn.close()
    return changes


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill uncategorized CFO transactions using current category rules.")
    parser.add_argument("--dry-run", action="store_true", help="Print planned changes without updating SQLite.")
    args = parser.parse_args()

    changes = backfill_categories(dry_run=args.dry_run)
    counter = Counter(item["category"] for item in changes)
    mode = "DRY RUN" if args.dry_run else "UPDATED"
    print(f"{mode}: {len(changes)} transaction(s)")
    for category, count in sorted(counter.items()):
        print(f"  {category}: {count}")
    for item in changes:
        merchant = item["merchant"] or item["product"] or item["transaction_uid"]
        print(f"- {item['transaction_uid']} -> {item['category']} / {item['thing'] or '-'} / {merchant}")


if __name__ == "__main__":
    main()
