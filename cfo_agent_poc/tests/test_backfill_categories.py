from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from cfo_agent_poc.bill_store import ensure_bill_tables
from cfo_agent_poc.backfill_categories import reprocess_ledger


BAD_WECHAT = """A卓越中寰体彩
主页
C 交易详情
-50.00
A卓越中寰体彩
当前状态
支付成功
支付时间
2026年07月10日 17:37:26
支付方式
零钱
交易单号
4500000000000000000000000201
经营单号
104250000000000000000000000059
01
交易服务
对订单有疑惑"""

MANUAL_BILL = """账单详情
今 220
-135.57
支付成功
支付时间
2026年07月01日 09:00:00
商品
Apple Gift Card - Example
交易单号
20260618000000000202"""


def insert_capture_and_transaction(
    conn: sqlite3.Connection,
    *,
    capture_hash: str,
    raw_text: str,
    transaction_uid: str,
    merchant: str,
    thing: str | None,
    category: str,
) -> None:
    conn.execute(
        "insert into raw_bill_captures values (?, 'email_screenshot', ?, null, null, datetime('now'))",
        (capture_hash, raw_text),
    )
    conn.execute(
        """
        insert into transactions
        (transaction_uid, source, direction, merchant, thing, category, confidence,
         raw_capture_hash, raw_text, created_at)
        values (?, 'email_screenshot', 'outflow', ?, ?, ?, 0.9, ?, ?, datetime('now'))
        """,
        (transaction_uid, merchant, thing, category, capture_hash, raw_text),
    )


class ReprocessLedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.db_path = self.root / "cfo.sqlite"
        conn = sqlite3.connect(self.db_path)
        ensure_bill_tables(conn)
        insert_capture_and_transaction(
            conn,
            capture_hash="capture-bad",
            raw_text=BAD_WECHAT,
            transaction_uid="wechat_txn_4500000000000000000000000201经营单号bad",
            merchant="C 交易详情",
            thing=None,
            category="uncategorized",
        )
        insert_capture_and_transaction(
            conn,
            capture_hash="capture-manual",
            raw_text=MANUAL_BILL,
            transaction_uid="txn_20260618000000000202",
            merchant="apple礼品卡",
            thing="apple礼品卡",
            category="uncategorized",
        )
        conn.commit()
        conn.close()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_dry_run_does_not_modify_database(self) -> None:
        before = self.db_path.read_bytes()
        report = reprocess_ledger(self.db_path, apply=False, backup_dir=self.root / "backups")

        self.assertEqual(self.db_path.read_bytes(), before)
        self.assertEqual(report["mode"], "dry-run")
        self.assertGreaterEqual(report["changed"], 1)
        self.assertFalse((self.root / "backups").exists())

    def test_apply_backs_up_repairs_uid_and_preserves_manual_title(self) -> None:
        report = reprocess_ledger(self.db_path, apply=True, backup_dir=self.root / "backups")

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("select * from transactions order by raw_capture_hash").fetchall()
        overrides = conn.execute("select field, value from transaction_overrides where raw_capture_hash='capture-manual'").fetchall()
        integrity = conn.execute("pragma integrity_check").fetchone()[0]
        conn.close()

        bad = next(row for row in rows if row["raw_capture_hash"] == "capture-bad")
        manual = next(row for row in rows if row["raw_capture_hash"] == "capture-manual")
        self.assertEqual(report["mode"], "apply")
        self.assertTrue(Path(report["backup_path"]).exists())
        self.assertEqual(integrity, "ok")
        self.assertEqual(len(rows), 2)
        self.assertEqual(bad["merchant"], "A卓越中寰体彩")
        self.assertEqual(bad["category"], "lottery")
        self.assertNotIn("经营单号", bad["transaction_uid"])
        self.assertEqual(manual["merchant"], "apple礼品卡")
        self.assertEqual(manual["thing"], "apple礼品卡")
        self.assertIn(("merchant", "apple礼品卡"), [tuple(row) for row in overrides])


if __name__ == "__main__":
    unittest.main()
