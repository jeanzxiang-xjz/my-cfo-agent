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


def build_payload() -> dict:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
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
            confidence
        from transactions
        where paid_at is not null
        order by paid_at desc
        """
    ).fetchall()
    conn.close()

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "demo": DEMO_MODE,
        "transactions": [dict(row) for row in rows],
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
