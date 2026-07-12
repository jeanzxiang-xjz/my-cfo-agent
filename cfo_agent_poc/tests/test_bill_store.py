from __future__ import annotations

import unittest
from pathlib import Path

from cfo_agent_poc.bill_store import CATEGORY_RULES, is_generic_merchant_label, normalize_order_id, parse_bill_text


FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class ParseBillTextTests(unittest.TestCase):
    def test_exposes_restored_category_rules_for_legacy_importers(self) -> None:
        categories = {category for category, _, _ in CATEGORY_RULES}

        self.assertTrue({"coffee_tea", "parking", "telecom", "lottery", "personal_transfer"} <= categories)

    def test_parses_new_wechat_convenience_layout_without_generic_header(self) -> None:
        parsed = parse_bill_text(
            load_fixture("wechat_transaction_detail_convenience.txt"),
            source_hint="wechat",
        )

        self.assertEqual(parsed.merchant, "易友佳便利店")
        self.assertEqual(parsed.transaction_id, "4500000000000000000000000001")
        self.assertEqual(parsed.merchant_order_id, "104250000000000000000000000001")
        self.assertEqual(parsed.category, "groceries")
        self.assertEqual(parsed.thing, "超市便利")
        self.assertGreaterEqual(parsed.category_confidence, 0.9)

    def test_parses_new_wechat_lottery_layout_and_stops_at_transaction_service(self) -> None:
        parsed = parse_bill_text(
            load_fixture("wechat_transaction_detail_lottery.txt"),
            source_hint="wechat",
        )

        self.assertEqual(parsed.merchant, "A卓越中寰体彩")
        self.assertEqual(parsed.transaction_id, "4500000000000000000000000002")
        self.assertEqual(parsed.merchant_order_id, "104250000000000000000000000002")
        self.assertEqual(parsed.category, "lottery")
        self.assertEqual(parsed.thing, "彩票")

    def test_parses_legacy_wechat_and_keeps_only_merchant_order_identifier(self) -> None:
        parsed = parse_bill_text(load_fixture("wechat_legacy_grocery.txt"), source_hint="wechat")

        self.assertEqual(parsed.merchant, "长沙市雨花区示例便利店（个体工商户）")
        self.assertEqual(parsed.transaction_id, "4200000000000000000000000003")
        self.assertEqual(parsed.merchant_order_id, "7895216690230525")
        self.assertEqual(parsed.category, "groceries")

    def test_parses_alipay_and_keeps_parse_confidence_independent_of_category(self) -> None:
        parsed = parse_bill_text(load_fixture("alipay_meituan.txt"), source_hint="alipay")

        self.assertEqual(parsed.payment_app, "alipay")
        self.assertEqual(parsed.merchant, "示例餐饮店")
        self.assertEqual(parsed.transaction_id, "20260711000000000004")
        self.assertEqual(parsed.merchant_order_id, "MERCHANT-0004")
        self.assertEqual(parsed.category, "food_delivery")
        self.assertEqual(parsed.thing, "饭")
        self.assertGreaterEqual(parsed.category_confidence, 0.9)
        self.assertLess(parsed.category_confidence, parsed.confidence)

    def test_keeps_parse_confidence_separate_from_strong_local_category_match(self) -> None:
        parsed = parse_bill_text("微信支付\n易友佳便利店\n-8.00", source_hint="wechat")

        self.assertEqual(parsed.category, "groceries")
        self.assertEqual(parsed.confidence, 0.53)
        self.assertGreaterEqual(parsed.category_confidence, 0.9)

    def test_rejects_arbitrary_single_character_ocr_prefix_for_generic_page_labels(self) -> None:
        parsed = parse_bill_text("@交易详情\n-8.00\n当前状态\n支付成功", source_hint="wechat")

        self.assertTrue(is_generic_merchant_label("@交易详情"))
        self.assertFalse(is_generic_merchant_label("交易详情商店"))
        self.assertIsNone(parsed.merchant)
        self.assertIn("rejected_generic_merchant_candidate:@交易详情", parsed.parse_warnings)

    def test_reconstructs_ocr_wrapped_numeric_merchant_order_id(self) -> None:
        parsed = parse_bill_text(
            """示例便利店
-8.00
当前状态
支付成功
交易单号
4500000000000000000000000009
经营单号
104250000000000000000000000059
01
交易服务
对订单有疑惑""",
            source_hint="wechat",
        )

        self.assertEqual(parsed.merchant_order_id, "10425000000000000000000000005901")

    def test_retains_valid_all_letter_order_id(self) -> None:
        self.assertEqual(normalize_order_id("ORDER-ABC"), "ORDER-ABC")

    def test_repeated_merchant_beats_nearby_noisy_candidate(self) -> None:
        parsed = parse_bill_text(
            """示例便利店
购买提示
-8.00
随机备注
示例便利店
当前状态
支付成功""",
            source_hint="wechat",
        )

        self.assertEqual(parsed.merchant, "示例便利店")

    def test_adds_warnings_for_missing_critical_facts(self) -> None:
        parsed = parse_bill_text("@交易详情\n-8.00", source_hint="wechat")

        self.assertIn("missing_status", parsed.parse_warnings)
        self.assertIn("missing_paid_at", parsed.parse_warnings)
        self.assertIn("missing_transaction_id", parsed.parse_warnings)

    def test_adds_warnings_for_invalid_labeled_critical_facts(self) -> None:
        parsed = parse_bill_text(
            """示例商户
-8.00
当前状态
支付成功
支付时间
not-a-date
交易单号
???""",
            source_hint="wechat",
        )

        self.assertIn("invalid_paid_at", parsed.parse_warnings)
        self.assertIn("invalid_transaction_id", parsed.parse_warnings)


if __name__ == "__main__":
    unittest.main()
