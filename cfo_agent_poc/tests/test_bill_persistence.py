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

    def test_project_absolute_image_path_is_stored_as_relative(self) -> None:
        absolute_path = bill_store.DATA_DIR / "mail_attachments" / "mail_test_1.png"

        self.assertEqual(
            bill_store.portable_image_path(absolute_path),
            "data/mail_attachments/mail_test_1.png",
        )
        self.assertEqual(
            bill_store.portable_image_path("./data/mail_attachments/mail_test_1.png"),
            "data/mail_attachments/mail_test_1.png",
        )

        bill_store.store_bill_capture(LOCAL_BILL, source="test", image_path=str(absolute_path))
        conn = self.connect()
        image_path = conn.execute("select image_path from raw_bill_captures").fetchone()[0]
        conn.close()
        self.assertEqual(image_path, "data/mail_attachments/mail_test_1.png")

    def test_external_image_is_copied_into_project_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as project_dir, tempfile.TemporaryDirectory() as source_dir:
            project = Path(project_dir)
            source = Path(source_dir) / "receipt.PNG"
            source.write_bytes(b"test image bytes")
            with patch.object(bill_store, "PROJECT_DIR", project), patch.object(
                bill_store, "DATA_DIR", project / "data"
            ):
                stored = bill_store.portable_image_path(source)

            self.assertTrue(stored.startswith("data/evidence/capture_"))
            self.assertTrue((project / stored).is_file())

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

    def test_polluted_platform_memory_is_purged_on_startup(self) -> None:
        conn = bill_store.connect()
        conn.execute(
            """
            insert into merchant_category_memory
            (merchant_key, merchant, category, thing, confidence, source, updated_at)
            values ('北京三快在线科技有限公司', '北京三快在线科技有限公司', 'healthcare', '中式按摩SPA', 0.9, 'deepseek', '2026-01-01')
            """
        )
        conn.commit()
        conn.close()

        conn = bill_store.connect()
        count = conn.execute("select count(*) from merchant_category_memory").fetchone()[0]
        conn.close()
        self.assertEqual(count, 0)

    def test_manual_merchant_alias_applies_to_future_captures(self) -> None:
        conn = bill_store.connect()
        self.assertTrue(bill_store.remember_merchant_alias(conn, alias="示例便利店", merchant="街角小卖部"))
        self.assertFalse(bill_store.remember_merchant_alias(conn, alias="美团平台商户", merchant="小象超市"))
        conn.commit()
        conn.close()

        parsed = bill_store.store_bill_capture(LOCAL_BILL, source="test", source_hint="wechat")

        self.assertEqual(parsed.merchant, "街角小卖部")

    def test_low_quality_merchant_is_queued_for_model_extraction(self) -> None:
        bill = "账单详情\n淘\ntb**5\n-65.00\n交易成功\n支付时间\n2026-09-20 00:32:31\n订单号\n2026092000000000000000000001"
        parsed = bill_store.store_bill_capture(bill, source="test", source_hint="alipay")
        conn = self.connect()
        row = conn.execute(
            "select merchant_quality, extraction_status from transactions where transaction_uid = ?",
            (parsed.transaction_uid,),
        ).fetchone()
        conn.close()

        self.assertEqual(row["merchant_quality"], "masked")
        self.assertEqual(row["extraction_status"], "pending")

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
