from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cfo_agent_poc import bill_store


WEB_APP_DIR = Path(__file__).resolve().parents[1] / "web_app"
if str(WEB_APP_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_APP_DIR))

import generate_snapshot
import server


INCOMPLETE = "@交易详情\n-8.00"
COMPLETE_WITHOUT_ID = """示例便利店
-8.00
当前状态
支付成功
支付时间
2026年07月12日 10:20:30"""


class IncompleteTransactionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.db_path = self.root / "cfo.sqlite"
        # 项目根要一起指到临时目录：凭证图片的存法（可能被改写成相对项目根的
        # 可移植路径）和服务端删文件时的解法必须落在同一个根上，否则删不到。
        self.patches = [
            patch.object(bill_store, "APP_DB", self.db_path),
            patch.object(bill_store, "PROJECT_DIR", self.root),
            patch.object(bill_store, "DATA_DIR", self.root / "data"),
            patch.object(server, "DEMO_MODE", False),
        ]
        for item in self.patches:
            item.start()
        self.ledger = server.use_ledger(server.Ledger(self.root, db_file=self.db_path))
        self.ledger.__enter__()

    def tearDown(self) -> None:
        self.ledger.__exit__(None, None, None)
        for item in reversed(self.patches):
            item.stop()
        self.temp_dir.cleanup()

    def test_snapshot_keeps_incomplete_capture_but_excludes_it_from_analysis(self) -> None:
        parsed = bill_store.store_bill_capture(
            INCOMPLETE,
            source="test",
            source_hint="wechat",
            image_path="first.png",
            captured_at="2026-07-12T12:00:00",
        )

        payload = generate_snapshot.build_payload(self.db_path)

        self.assertEqual(len(payload["transactions"]), 1)
        transaction = payload["transactions"][0]
        self.assertEqual(transaction["transaction_uid"], parsed.transaction_uid)
        self.assertEqual(transaction["captured_at"], "2026-07-12T12:00:00")
        self.assertEqual(transaction["correction_fields"], ["paid_at", "merchant"])
        self.assertFalse(transaction["analysis_eligible"])
        self.assertEqual(payload["correction_pending_count"], 1)
        self.assertEqual(server.scoped_transactions(payload["transactions"], "all"), [])

    def test_all_period_analysis_excludes_incomplete_transactions_from_mixed_data(self) -> None:
        bill_store.store_bill_capture(
            INCOMPLETE,
            source="test",
            image_path="incomplete.png",
            captured_at="2026-07-12T12:00:00",
        )
        complete = bill_store.store_bill_capture(
            COMPLETE_WITHOUT_ID,
            source="test",
            image_path="complete.png",
            captured_at="2026-07-12T12:01:00",
        )

        selected = server.scoped_transactions(generate_snapshot.build_payload(self.db_path)["transactions"], "all")

        self.assertEqual([transaction["transaction_uid"] for transaction in selected], [complete.transaction_uid])

    def test_similar_incomplete_captures_do_not_overwrite_each_other(self) -> None:
        first = bill_store.store_bill_capture(INCOMPLETE, source="test", image_path="first.png")
        second = bill_store.store_bill_capture(INCOMPLETE, source="test", image_path="second.png")
        repeated = bill_store.store_bill_capture(INCOMPLETE, source="test", image_path="first.png")

        conn = sqlite3.connect(self.db_path)
        count = conn.execute("select count(*) from transactions").fetchone()[0]
        conn.close()

        self.assertNotEqual(first.transaction_uid, second.transaction_uid)
        self.assertEqual(first.transaction_uid, repeated.transaction_uid)
        self.assertEqual(count, 2)

    def test_manual_correction_clears_active_core_warnings(self) -> None:
        parsed = bill_store.store_bill_capture(INCOMPLETE, source="test", image_path="first.png")

        result = server.update_transaction_fields(parsed.transaction_uid, {
            "paid_at": "2026-07-12T12:05:00",
            "merchant": "楼下便利店",
        })

        self.assertTrue(result["ok"])
        self.assertTrue(result["transaction"]["analysis_eligible"])
        self.assertEqual(result["transaction"]["correction_fields"], [])
        self.assertNotIn("missing_paid_at", result["parse_warnings"])
        self.assertNotIn("missing_merchant", result["parse_warnings"])
        self.assertIn("missing_paid_at", result["original_parse_warnings"])

    def test_permanent_delete_removes_orphaned_capture_and_files(self) -> None:
        data_dir = self.root / "data"
        image_dir = data_dir / "mail_attachments"
        ocr_dir = data_dir / "ocr_texts"
        image_dir.mkdir(parents=True)
        ocr_dir.mkdir(parents=True)
        image_path = image_dir / "bill.png"
        ocr_path = ocr_dir / "bill.txt"
        image_path.write_bytes(b"image")
        ocr_path.write_text("ocr", encoding="utf-8")
        parsed = bill_store.store_bill_capture(
            COMPLETE_WITHOUT_ID,
            source="test",
            image_path=str(image_path),
        )

        result = server.delete_transaction(parsed.transaction_uid)

        self.assertTrue(result["ok"])
        self.assertEqual(result["deleted_file_count"], 2)
        self.assertFalse(image_path.exists())
        self.assertFalse(ocr_path.exists())
        conn = sqlite3.connect(self.db_path)
        self.assertEqual(conn.execute("select count(*) from transactions").fetchone()[0], 0)
        self.assertEqual(conn.execute("select count(*) from raw_bill_captures").fetchone()[0], 0)
        conn.close()

    def test_file_cleanup_failure_keeps_database_record(self) -> None:
        data_dir = self.root / "data" / "mail_attachments"
        data_dir.mkdir(parents=True)
        image_path = data_dir / "bill.png"
        image_path.write_bytes(b"image")
        parsed = bill_store.store_bill_capture(
            COMPLETE_WITHOUT_ID,
            source="test",
            image_path=str(image_path),
        )

        with patch.object(Path, "unlink", side_effect=OSError("readonly")):
            with self.assertRaises(OSError):
                server.delete_transaction(parsed.transaction_uid)

        conn = sqlite3.connect(self.db_path)
        self.assertEqual(conn.execute("select count(*) from transactions").fetchone()[0], 1)
        conn.close()

    def test_demo_mode_keeps_delete_read_only(self) -> None:
        parsed = bill_store.store_bill_capture(
            COMPLETE_WITHOUT_ID,
            source="test",
            image_path="bill.png",
        )

        with patch.object(server, "DEMO_MODE", True):
            result = server.delete_transaction(parsed.transaction_uid)

        self.assertEqual(result["code"], "demo_readonly")
        conn = sqlite3.connect(self.db_path)
        self.assertEqual(conn.execute("select count(*) from transactions").fetchone()[0], 1)
        conn.close()


if __name__ == "__main__":
    unittest.main()
