from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cfo_agent_poc import bill_store


LOCAL_BILL = """示例便利店
-8.00
示例便利店
当前状态
支付成功
支付时间
2026年07月12日 10:20:30
支付方式
零钱
交易单号
4500000000000000000000000101"""

UNKNOWN_BILL = """示例数字商户
-18.00
示例数字商户
当前状态
支付成功
支付时间
2026年07月12日 11:20:30
支付方式
零钱
交易单号
4500000000000000000000000102"""


class BillPersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "cfo.sqlite"
        self.db_patch = patch.object(bill_store, "APP_DB", self.db_path)
        self.db_patch.start()

    def tearDown(self) -> None:
        self.db_patch.stop()
        self.temp_dir.cleanup()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def test_schema_contains_classification_metadata_memory_and_overrides(self) -> None:
        conn = bill_store.connect()
        columns = {row[1] for row in conn.execute("pragma table_info(transactions)")}
        tables = {row[0] for row in conn.execute("select name from sqlite_master where type='table'")}
        conn.close()

        self.assertTrue({
            "classification_source",
            "classification_confidence",
            "classification_status",
            "classification_reason",
            "parse_warnings",
        }.issubset(columns))
        self.assertIn("merchant_category_memory", tables)
        self.assertIn("transaction_overrides", tables)

    def test_local_rule_is_persisted_and_remembered(self) -> None:
        bill_store.store_bill_capture(LOCAL_BILL, source="test", source_hint="wechat")

        conn = self.connect()
        row = conn.execute("select * from transactions").fetchone()
        memory = conn.execute("select * from merchant_category_memory").fetchone()
        conn.close()

        self.assertEqual(row["category"], "groceries")
        self.assertEqual(row["classification_source"], "local_rule")
        self.assertEqual(row["classification_status"], "resolved")
        self.assertIsInstance(json.loads(row["parse_warnings"]), list)
        self.assertEqual(memory["category"], "groceries")

    def test_memory_precedes_an_unknown_local_rule(self) -> None:
        conn = bill_store.connect()
        bill_store.remember_merchant_classification(
            conn,
            merchant="示例数字商户",
            category="digital_services",
            thing="数字服务",
            confidence=0.92,
            source="deepseek",
        )
        conn.commit()
        conn.close()

        parsed = bill_store.store_bill_capture(UNKNOWN_BILL, source="test", source_hint="wechat")

        self.assertEqual(parsed.category, "digital_services")
        self.assertEqual(parsed.classification_source, "merchant_memory")
        self.assertEqual(parsed.classification_status, "resolved")

    def test_capture_override_has_highest_precedence(self) -> None:
        bill_store.store_bill_capture(UNKNOWN_BILL, source="test", source_hint="wechat")
        conn = self.connect()
        capture_hash = conn.execute("select raw_capture_hash from transactions").fetchone()[0]
        conn.executemany(
            "insert into transaction_overrides (raw_capture_hash, field, value, created_at) values (?, ?, ?, datetime('now'))",
            [
                (capture_hash, "merchant", "apple礼品卡"),
                (capture_hash, "category", "digital_services"),
                (capture_hash, "thing", "Apple 礼品卡"),
            ],
        )
        conn.commit()
        conn.close()

        parsed = bill_store.store_bill_capture(UNKNOWN_BILL, source="test", source_hint="wechat")

        self.assertEqual(parsed.merchant, "apple礼品卡")
        self.assertEqual(parsed.category, "digital_services")
        self.assertEqual(parsed.thing, "Apple 礼品卡")
        self.assertEqual(parsed.classification_source, "manual_override")

    def test_generic_merchant_is_not_saved_to_memory(self) -> None:
        conn = bill_store.connect()
        saved = bill_store.remember_merchant_classification(
            conn,
            merchant="美团平台商户",
            category="food_delivery",
            thing="饭",
            confidence=0.95,
            source="local_rule",
        )
        conn.commit()
        count = conn.execute("select count(*) from merchant_category_memory").fetchone()[0]
        conn.close()

        self.assertFalse(saved)
        self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
