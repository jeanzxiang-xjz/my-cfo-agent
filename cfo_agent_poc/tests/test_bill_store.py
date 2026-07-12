from __future__ import annotations

import unittest
from pathlib import Path

from cfo_agent_poc.bill_store import parse_bill_text


FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class ParseBillTextTests(unittest.TestCase):
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
        self.assertEqual(parsed.thing, "餐饮外卖")
        self.assertGreaterEqual(parsed.category_confidence, 0.9)
        self.assertLess(parsed.category_confidence, parsed.confidence)

    def test_keeps_parse_confidence_separate_from_strong_local_category_match(self) -> None:
        parsed = parse_bill_text("微信支付\n易友佳便利店\n-8.00", source_hint="wechat")

        self.assertEqual(parsed.category, "groceries")
        self.assertEqual(parsed.confidence, 0.53)
        self.assertGreaterEqual(parsed.category_confidence, 0.9)


if __name__ == "__main__":
    unittest.main()
