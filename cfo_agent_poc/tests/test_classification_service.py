from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from cfo_agent_poc.bill_store import ensure_bill_tables
from cfo_agent_poc.classification_service import (
    build_deepseek_request,
    enrich_pending_transactions,
    parse_deepseek_response,
)


class ClassificationServiceTests(unittest.TestCase):
    def test_deepseek_payload_contains_only_allowed_transaction_fields(self) -> None:
        payload = build_deepseek_request([
            {
                "transaction_uid": "private-transaction-id",
                "merchant": "示例商户",
                "product": "会员服务",
                "platform": "微信",
                "payment_app": "wechat",
                "raw_text": "private raw ocr",
                "payment_method": "银行卡(1234)",
                "amount": 99.0,
            }
        ], model="deepseek-v4-flash")
        serialized = json.dumps(payload, ensure_ascii=False)
        user_payload = json.loads(payload["messages"][1]["content"])

        self.assertIn("示例商户", serialized)
        self.assertEqual(user_payload["items"][0]["item_id"], 0)
        for secret in ("private-transaction-id", "private raw ocr", "1234", "99.0"):
            self.assertNotIn(secret, serialized)

    def test_response_rejects_unknown_categories_and_keeps_ephemeral_item_ids(self) -> None:
        response = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "results": [
                            {"item_id": 0, "category": "digital_services", "thing": "会员", "confidence": 0.91, "reason": "会员服务"},
                            {"item_id": 1, "category": "invented", "thing": "未知", "confidence": 0.99, "reason": "invalid"},
                        ]
                    }, ensure_ascii=False)
                }
            }]
        }

        parsed = parse_deepseek_response(response, item_count=2)

        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["item_id"], 0)
        self.assertEqual(parsed[0]["category"], "digital_services")

    def test_enrichment_updates_only_pending_category_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "cfo.sqlite"
            conn = sqlite3.connect(db_path)
            ensure_bill_tables(conn)
            conn.execute(
                """
                insert into transactions
                (transaction_uid, source, amount, direction, paid_at, merchant, category, confidence,
                 raw_text, created_at, classification_source, classification_confidence,
                 classification_status, parse_warnings)
                values ('tx-1', 'test', 18, 'outflow', '2026-07-12T12:00:00', '示例数字商户',
                        'uncategorized', 0.8, 'private raw text', datetime('now'), 'none', 0,
                        'pending', '[]')
                """
            )
            conn.commit()
            conn.close()

            seen = {}

            def fake_classifier(items: list[dict]) -> list[dict]:
                seen.update(items[0])
                return [{
                    "item_id": 0,
                    "category": "digital_services",
                    "thing": "数字会员",
                    "confidence": 0.9,
                    "reason": "会员类服务",
                }]

            result = enrich_pending_transactions(db_path, classifier=fake_classifier)

            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            row = conn.execute("select * from transactions where transaction_uid='tx-1'").fetchone()
            conn.close()

            self.assertEqual(result["resolved"], 1)
            self.assertEqual(row["merchant"], "示例数字商户")
            self.assertEqual(row["amount"], 18)
            self.assertEqual(row["category"], "digital_services")
            self.assertEqual(row["classification_source"], "deepseek")
            self.assertNotIn("raw_text", seen)
            self.assertNotIn("transaction_uid", seen)


if __name__ == "__main__":
    unittest.main()
