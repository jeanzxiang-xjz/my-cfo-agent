from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cfo_agent_poc.bill_classifier import classify_locally, strip_company_noise
from cfo_agent_poc.bill_store import ensure_bill_tables
from cfo_agent_poc.classification_service import (
    MAX_ATTEMPTS,
    build_deepseek_request,
    enrich_pending_transactions,
    parse_deepseek_response,
    redact_ocr,
    settle_stuck_transactions,
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


class PendingNeverStallsTests(unittest.TestCase):
    """
    pending 必须是过渡态。任何一条路径把交易永久留在 pending，
    界面上就是一个永远转不完的「识别中」——这组用例守的就是这件事。
    """

    def _seed(self, db_path: Path) -> None:
        conn = sqlite3.connect(db_path)
        ensure_bill_tables(conn)
        conn.execute(
            """
            insert into transactions
            (transaction_uid, source, amount, direction, paid_at, merchant, category, confidence,
             raw_text, created_at, classification_source, classification_confidence,
             classification_status, parse_warnings)
            values ('tx-stall', 'test', 146, 'outflow', '2026-08-08T23:03:39', '某某文化发展有限公司',
                    'uncategorized', 0.99, 'raw', datetime('now'), 'none', 0, 'pending', '[]')
            """
        )
        conn.commit()
        conn.close()

    def _row(self, db_path: Path) -> sqlite3.Row:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute("select * from transactions where transaction_uid='tx-stall'").fetchone()
        conn.close()
        return row

    def test_moderate_confidence_is_accepted_instead_of_discarded(self) -> None:
        """0.6 这种「不太确定但有答案」的结果要落库，不能丢掉后把行挂死。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "cfo.sqlite"
            self._seed(db_path)
            enrich_pending_transactions(db_path, classifier=lambda items: [{
                "item_id": 0, "category": "entertainment", "thing": "文娱消费",
                "confidence": 0.6, "reason": "疑似娱乐场所",
            }])
            row = self._row(db_path)
            self.assertEqual(row["classification_status"], "resolved")
            self.assertEqual(row["category"], "entertainment")
            self.assertEqual(row["classification_source"], "deepseek_low")

    def test_repeated_failures_settle_instead_of_staying_pending(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "cfo.sqlite"
            self._seed(db_path)

            def boom(items: list[dict]) -> list[dict]:
                raise TimeoutError("upstream timeout")

            for _ in range(MAX_ATTEMPTS):
                enrich_pending_transactions(db_path, classifier=boom)
            row = self._row(db_path)
            self.assertEqual(row["classification_status"], "resolved")
            self.assertEqual(row["category"], "uncategorized")
            self.assertIn("exhausted", row["classification_reason"])

    def test_empty_model_response_settles_after_max_attempts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "cfo.sqlite"
            self._seed(db_path)
            for _ in range(MAX_ATTEMPTS):
                enrich_pending_transactions(db_path, classifier=lambda items: [])
            self.assertEqual(self._row(db_path)["classification_status"], "resolved")

    def test_missing_api_key_settles_immediately(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "cfo.sqlite"
            self._seed(db_path)
            with mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": ""}, clear=False):
                result = enrich_pending_transactions(db_path)
            self.assertEqual(result["error"], "missing_api_key")
            self.assertEqual(self._row(db_path)["classification_status"], "resolved")

    def test_sweeper_settles_rows_left_behind_by_a_crashed_worker(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "cfo.sqlite"
            self._seed(db_path)
            conn = sqlite3.connect(db_path)
            conn.execute("update transactions set classification_attempts = ?", (MAX_ATTEMPTS,))
            conn.commit()
            conn.close()

            self.assertEqual(settle_stuck_transactions(db_path), 1)
            self.assertEqual(self._row(db_path)["classification_status"], "resolved")


class IndustryDictionaryTests(unittest.TestCase):
    def test_company_name_noise_is_stripped_before_matching(self) -> None:
        self.assertEqual(strip_company_noise("长沙湘怡文化发展有限公司"), "湘怡文化发展")

    def test_industry_tier_catches_unenumerable_company_names(self) -> None:
        """一级词表枚举不到的工商名，靠行业词兜住，而不是掉进 pending。"""
        result = classify_locally(
            merchant="长沙湘怡文化发展有限公司",
            product="温莎消费",
            platform=None,
            payment_app="wechat",
            text="",
        )
        self.assertEqual(result.status, "resolved")
        self.assertEqual(result.category, "entertainment")
        self.assertEqual(result.source, "local_industry")

    def test_first_tier_merchant_rules_still_win(self) -> None:
        result = classify_locally(
            merchant="瑞幸咖啡", product="咖啡", platform=None, payment_app="wechat", text=""
        )
        self.assertEqual(result.category, "coffee_tea")
        self.assertEqual(result.source, "local_rule")


if __name__ == "__main__":
    unittest.main()


class ExtractionTests(unittest.TestCase):
    """模型从「只分类」升级为「抽取+分类」后的脱敏和回写优先级。"""

    def test_redact_ocr_hides_identifiers_but_keeps_shop_and_items(self) -> None:
        excerpt = redact_ocr(
            "19:26\n令\n消费详情\n示例包子铺\n肉丝木耳保靖粗粉\n订单号\n2608211420488085010882969481\n"
            "支付方式\n示例银行信用卡（1234）\n联系电话 13812345678\n邮箱 someone@example.com\n"
            "商家订单号\nT200P3316427943086036974"
        )

        self.assertIn("示例包子铺", excerpt)
        self.assertIn("肉丝木耳保靖粗粉", excerpt)
        for secret in ("2608211420488085010882969481", "1234", "13812345678", "someone@example.com",
                       "T200P3316427943086036974", "19:26"):
            self.assertNotIn(secret, excerpt)

    def test_response_drops_platform_entity_merchant(self) -> None:
        response = {"choices": [{"message": {"content": json.dumps({"results": [
            {"item_id": 0, "category": "food_delivery", "merchant": "北京三快在线科技有限公司",
             "thing": "米粉", "confidence": 0.9, "reason": "外卖"},
        ]}, ensure_ascii=False)}}]}

        parsed = parse_deepseek_response(response, item_count=1)

        self.assertIsNone(parsed[0]["merchant"])

    def _seed(self, db_path: Path, *, merchant: str, quality: str, thing: str | None,
              category_status: str, overrides: dict[str, str] | None = None) -> None:
        conn = sqlite3.connect(db_path)
        ensure_bill_tables(conn)
        conn.execute(
            """
            insert into transactions
            (transaction_uid, source, amount, direction, paid_at, merchant, thing, category, confidence,
             raw_capture_hash, raw_text, created_at, classification_source, classification_confidence,
             classification_status, parse_warnings, merchant_quality, extraction_status)
            values ('tx-x', 'test', 20, 'outflow', '2026-08-21T14:20:48', ?, ?, ?, 0.9,
                    'cap-x', '消费详情\n示例包子铺\n肉丝木耳保靖粗粉', datetime('now'), ?, 0.95, ?, '[]', ?, 'pending')
            """,
            (merchant, thing, "food_delivery" if category_status == "resolved" else "uncategorized",
             "local_rule" if category_status == "resolved" else "none", category_status, quality),
        )
        for field, value in (overrides or {}).items():
            conn.execute(
                "insert into transaction_overrides (raw_capture_hash, field, value, created_at) values ('cap-x', ?, ?, datetime('now'))",
                (field, value),
            )
        conn.commit()
        conn.close()

    def _row(self, db_path: Path) -> sqlite3.Row:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute("select * from transactions where transaction_uid='tx-x'").fetchone()
        conn.close()
        return row

    @staticmethod
    def _model(items: list[dict]) -> list[dict]:
        assert "ocr_excerpt" in items[0] and "示例包子铺" in items[0]["ocr_excerpt"]
        return [{"item_id": 0, "category": "food_delivery", "merchant": "示例包子铺",
                 "thing": "米粉", "confidence": 0.9, "reason": "外卖"}]

    def test_extraction_fills_merchant_and_specific_thing_without_touching_category(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "cfo.sqlite"
            self._seed(db_path, merchant="美团", quality="platform", thing="饭", category_status="resolved")

            result = enrich_pending_transactions(db_path, classifier=self._model)
            row = self._row(db_path)

            self.assertEqual(result["extracted"], 1)
            self.assertEqual(row["merchant"], "示例包子铺")
            self.assertEqual(row["merchant_quality"], "ok")
            self.assertEqual(row["thing"], "米粉")
            self.assertEqual(row["classification_source"], "local_rule")
            self.assertEqual(row["extraction_status"], "done")

    def test_extraction_never_overwrites_manual_corrections(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "cfo.sqlite"
            self._seed(db_path, merchant="小象超市", quality="platform", thing="家庭快手菜",
                       category_status="resolved", overrides={"merchant": "小象超市", "thing": "家庭快手菜"})

            enrich_pending_transactions(db_path, classifier=self._model)
            row = self._row(db_path)

            self.assertEqual(row["merchant"], "小象超市")
            self.assertEqual(row["thing"], "家庭快手菜")
            self.assertEqual(row["extraction_status"], "done")

    def test_extraction_gives_up_after_max_attempts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "cfo.sqlite"
            self._seed(db_path, merchant="tb**5", quality="masked", thing=None, category_status="resolved")

            for _ in range(MAX_ATTEMPTS):
                enrich_pending_transactions(db_path, classifier=lambda items: [])

            self.assertEqual(self._row(db_path)["extraction_status"], "failed")
