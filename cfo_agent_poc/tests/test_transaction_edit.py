"""解析字段的人工兜底校正。

OCR 会认错、正则会解析歪，所以每条记录都要能手动改回来。这里守住三件事：
校验不能被绕过、只有真正改动的字段才算「校正」、重新解析同一张截图不能把改动冲掉。
"""

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

import server


BILL = """示例便利店
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


class TransactionEditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "cfo.sqlite"
        self.patches = [
            patch.object(bill_store, "APP_DB", self.db_path),
            patch.object(server, "DEMO_MODE", False),
        ]
        for item in self.patches:
            item.start()
        self.ledger = server.use_ledger(server.Ledger(self.db_path.parent, db_file=self.db_path))
        self.ledger.__enter__()
        parsed = bill_store.store_bill_capture(BILL, source="test", source_hint="wechat")
        self.uid = parsed.transaction_uid

    def tearDown(self) -> None:
        self.ledger.__exit__(None, None, None)
        for item in self.patches:
            item.stop()
        self.temp_dir.cleanup()

    def row(self) -> sqlite3.Row:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            return conn.execute("select * from transactions where transaction_uid = ?", (self.uid,)).fetchone()
        finally:
            conn.close()

    def overrides(self) -> dict:
        conn = sqlite3.connect(self.db_path)
        try:
            return dict(conn.execute("select field, value from transaction_overrides").fetchall())
        finally:
            conn.close()

    # --------------------------- 校验 ---------------------------

    def test_rejects_bad_values(self) -> None:
        for fields, expect in (
            ({"amount": "0"}, "大于 0"),
            ({"amount": "-3"}, "大于 0"),
            ({"amount": "很多钱"}, "数字"),
            ({"amount": "99999999"}, "上限"),
            ({"paid_at": "上周三"}, "格式"),
            ({"category": "不存在的分类"}, "范围"),
            ({"payment_app": "paypal"}, "微信或支付宝"),
            ({"direction": "refund"}, "支出或收入"),
            ({"direction": ""}, "支出或收入"),
            ({"card_last4": "12"}, "4 位数字"),
            ({"merchant": "长" * 61}, "最多"),
        ):
            with self.subTest(fields=fields):
                result = server.update_transaction_fields(self.uid, fields)
                self.assertFalse(result["ok"])
                self.assertIn(expect, result["answer"])
        self.assertEqual(self.overrides(), {}, "校验失败不该留下任何 override")

    def test_rejects_fields_outside_the_whitelist(self) -> None:
        """字段名会拼进 SQL，白名单之外的一律挡掉。"""
        for field in ("classification_source", "transaction_uid", "raw_text", "amount = 1, category"):
            with self.subTest(field=field):
                result = server.update_transaction_fields(self.uid, {field: "x"})
                self.assertFalse(result["ok"])
                self.assertEqual(result["code"], "unknown_field")

    def test_rejects_unknown_transaction(self) -> None:
        result = server.update_transaction_fields("nope", {"amount": "1"})
        self.assertEqual(result["code"], "not_found")

    def test_demo_mode_is_read_only(self) -> None:
        with patch.object(server, "DEMO_MODE", True):
            result = server.update_transaction_fields(self.uid, {"amount": "1"})
        self.assertEqual(result["code"], "demo_readonly")
        self.assertEqual(self.row()["amount"], 8.0)

    # ----------------------- 只记录真的改动 -----------------------

    def test_resubmitting_the_same_values_changes_nothing(self) -> None:
        before = self.row()
        result = server.update_transaction_fields(self.uid, {
            "amount": str(before["amount"]),
            "paid_at": before["paid_at"],
            "merchant": before["merchant"],
            "category": before["category"],
        })
        self.assertTrue(result["ok"])
        self.assertEqual(result["saved_fields"], [])
        self.assertEqual(self.overrides(), {})

    def test_only_changed_fields_are_recorded(self) -> None:
        before = self.row()
        result = server.update_transaction_fields(self.uid, {
            "amount": "12.34",
            "merchant": before["merchant"],
            "paid_at": before["paid_at"],
        })
        self.assertEqual(result["saved_fields"], ["amount"])
        self.assertEqual(set(self.overrides()), {"amount"})
        self.assertEqual(self.row()["amount"], 12.34)

    def test_empty_string_and_null_are_the_same_value(self) -> None:
        server.update_transaction_fields(self.uid, {"card_last4": ""})
        self.assertEqual(self.overrides(), {})

    # --------------------- 分类元数据的边界 ---------------------

    def test_changing_category_marks_it_manual(self) -> None:
        server.update_transaction_fields(self.uid, {"category": "digital_services"})
        row = self.row()
        self.assertEqual(row["category"], "digital_services")
        self.assertEqual(row["classification_source"], "manual_override")
        self.assertEqual(row["classification_confidence"], 1.0)
        self.assertEqual(row["classification_status"], "resolved")

    def test_changing_amount_leaves_classification_alone(self) -> None:
        before = self.row()
        server.update_transaction_fields(self.uid, {"amount": "99.90"})
        row = self.row()
        self.assertEqual(row["amount"], 99.90)
        self.assertEqual(row["classification_source"], before["classification_source"])
        self.assertEqual(row["classification_confidence"], before["classification_confidence"])

    # ------------------------ 重新解析不冲掉 ------------------------

    def test_corrections_survive_a_reparse_of_the_same_capture(self) -> None:
        server.update_transaction_fields(self.uid, {
            "amount": "42.50",
            "merchant": "楼下便利店",
            "paid_at": "2026-07-12T11:00:00",
            "payment_method": "花呗",
            "card_last4": "8888",
            "category": "digital_services",
        })

        # 同一张截图再解析一次：字段应该回到人工校正后的值，而不是 OCR 的原值。
        conn = sqlite3.connect(self.db_path)
        capture_hash = conn.execute(
            "select raw_capture_hash from transactions where transaction_uid = ?", (self.uid,)
        ).fetchone()[0]
        fresh = bill_store.parse_bill_text(BILL, source="test", source_hint="wechat")
        self.assertEqual(fresh.merchant, "示例便利店")  # 前提：原始解析确实不一样
        replayed = bill_store.apply_persisted_classification(conn, fresh, capture_hash)
        conn.close()

        self.assertEqual(replayed.amount, 42.50)
        self.assertEqual(replayed.merchant, "楼下便利店")
        self.assertEqual(replayed.paid_at, "2026-07-12T11:00:00")
        self.assertEqual(replayed.payment_method, "花呗")
        self.assertEqual(replayed.card_last4, "8888")
        self.assertEqual(replayed.category, "digital_services")
        self.assertEqual(replayed.classification_source, "manual_override")

    def test_direction_can_be_flipped_to_inflow(self) -> None:
        """解析把转账收款这类收入记成了支出，人工改成收入后只记这一个字段。"""
        self.assertEqual(self.row()["direction"], "outflow")  # 前提：原始解析是支出
        result = server.update_transaction_fields(self.uid, {"direction": "inflow", "amount": "8.00"})
        self.assertTrue(result["ok"])
        self.assertEqual(result["saved_fields"], ["direction"])
        self.assertEqual(self.row()["direction"], "inflow")

    def test_direction_correction_survives_a_reparse(self) -> None:
        server.update_transaction_fields(self.uid, {"direction": "inflow"})
        self.assertEqual(self.overrides().get("direction"), "inflow")

        conn = sqlite3.connect(self.db_path)
        capture_hash = conn.execute(
            "select raw_capture_hash from transactions where transaction_uid = ?", (self.uid,)
        ).fetchone()[0]
        fresh = bill_store.parse_bill_text(BILL, source="test", source_hint="wechat")
        self.assertEqual(fresh.direction, "outflow")  # 前提：原始解析确实是支出
        replayed = bill_store.apply_persisted_classification(conn, fresh, capture_hash)
        conn.close()
        self.assertEqual(replayed.direction, "inflow")

    def test_reparse_keeps_untouched_fields_from_ocr(self) -> None:
        server.update_transaction_fields(self.uid, {"merchant": "楼下便利店"})

        conn = sqlite3.connect(self.db_path)
        capture_hash = conn.execute(
            "select raw_capture_hash from transactions where transaction_uid = ?", (self.uid,)
        ).fetchone()[0]
        fresh = bill_store.parse_bill_text(BILL, source="test", source_hint="wechat")
        replayed = bill_store.apply_persisted_classification(conn, fresh, capture_hash)
        conn.close()

        self.assertEqual(replayed.merchant, "楼下便利店")
        self.assertEqual(replayed.amount, 8.0, "没改过的字段应该还是 OCR 解析的结果")
        self.assertEqual(replayed.paid_at, "2026-07-12T10:20:30")


class ReviewClearsUnsureFlagTests(TransactionEditTests):
    """人工核对过的交易不该继续挂在「待核实」。

    前端的判定是三选一：classification_status=pending、confidence<0.6、
    或分类来源偏弱。原先只有「改动了 category」才会写分类元数据，
    而 confidence 从不重算，于是出现两条清不掉的死路：
      A. 因 confidence 低被标记 —— 改什么都没用；
      B. 因分类弱被标记，但只改了商户/金额 —— 分类元数据没被触碰。
    再加上「解析本来就对、只想确认一下」根本无处记录。
    reviewed_at 就是为这三种情况兜底的。
    """

    def set_unsure(self, **columns: object) -> None:
        assignments = ", ".join(f"{name} = ?" for name in columns)
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                f"update transactions set {assignments} where transaction_uid = ?",
                (*columns.values(), self.uid),
            )
            conn.commit()
        finally:
            conn.close()

    def test_editing_an_unrelated_field_still_marks_the_row_reviewed(self) -> None:
        """失败路径 B：因分类弱被标记，用户只改了商户。"""
        self.set_unsure(classification_source="local_industry", classification_status="pending")

        result = server.update_transaction_fields(self.uid, {"merchant": "示例便利店（河西店）"})

        self.assertEqual(result["saved_fields"], ["merchant"])
        self.assertIsNotNone(self.row()["reviewed_at"])

    def test_low_parse_confidence_row_can_be_cleared(self) -> None:
        """失败路径 A：confidence 低是清不掉的死路，因为它不可编辑也从不重算。"""
        self.set_unsure(confidence=0.35)

        server.update_transaction_fields(self.uid, {"thing": "饭"})

        row = self.row()
        self.assertIsNotNone(row["reviewed_at"])
        self.assertAlmostEqual(row["confidence"], 0.35, msg="解析置信是机器指标，不该被人工校正篡改")

    def test_saving_without_changes_counts_as_a_review(self) -> None:
        """交互死角 C：解析本来就对，用户只想说「看过了，没问题」。"""
        self.set_unsure(confidence=0.4)
        before = self.row()

        result = server.update_transaction_fields(self.uid, {"merchant": before["merchant"]})

        self.assertEqual(result["saved_fields"], [], "没改动就不该记成校正")
        self.assertEqual(self.overrides(), {}, "没改动就不该留 override")
        self.assertIsNotNone(self.row()["reviewed_at"], "但必须记下「已核对」")

    def test_review_timestamp_reaches_the_frontend_payload(self) -> None:
        """前端靠 data.json 里的 reviewed_at 过滤，取不到就等于没修。"""
        server.update_transaction_fields(self.uid, {"thing": "饭"})

        payload = server.build_payload()
        entry = next(tx for tx in payload["transactions"] if tx["transaction_uid"] == self.uid)
        self.assertIsNotNone(entry["reviewed_at"])


if __name__ == "__main__":
    unittest.main()
