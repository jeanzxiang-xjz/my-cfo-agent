from __future__ import annotations

import unittest

from cfo_agent_poc.bill_classifier import ClassificationResult, classify_locally


class LocalClassificationTests(unittest.TestCase):
    def test_classifies_ocr_split_meituan_as_food_delivery(self) -> None:
        result = classify_locally(
            merchant="示例餐饮店",
            product="美 团 外 卖 - 午餐",
            platform=None,
            payment_app="alipay",
            text="账单详情 美 团 外 卖",
        )

        self.assertEqual(result.category, "food_delivery")
        self.assertEqual(result.thing, "饭")
        self.assertGreaterEqual(result.confidence, 0.9)
        self.assertEqual(result.source, "local_rule")
        self.assertEqual(result.status, "resolved")

    def test_classifies_personal_qr_transfer(self) -> None:
        result = classify_locally(
            merchant="张三",
            product=None,
            platform=None,
            payment_app="wechat",
            text="微信支付 向个人收款码付款 二维码收款",
        )

        self.assertEqual(result.category, "personal_transfer")
        self.assertEqual(result.thing, "个人转账")
        self.assertGreaterEqual(result.confidence, 0.9)

    def test_restores_coffee_tea_rule(self) -> None:
        result = classify_locally(
            merchant="瑞幸咖啡",
            product="生椰拿铁",
            platform=None,
            payment_app="wechat",
            text="",
        )

        self.assertIsInstance(result, ClassificationResult)
        self.assertEqual(result.category, "coffee_tea")
        self.assertEqual(result.thing, "咖啡")

    def test_restores_parking_and_telecom_rules(self) -> None:
        parking = classify_locally(
            merchant="示例停车场",
            product="停车缴费",
            platform=None,
            payment_app="wechat",
            text="",
        )
        telecom = classify_locally(
            merchant="中国移动",
            product="手机话费充值",
            platform=None,
            payment_app="alipay",
            text="",
        )

        self.assertEqual(parking.category, "parking")
        self.assertEqual(telecom.category, "telecom")

    def test_specific_structured_coffee_rule_beats_generic_raw_meituan(self) -> None:
        result = classify_locally(
            merchant="瑞幸咖啡",
            product="生椰拿铁",
            platform="美团",
            payment_app="wechat",
            text="美团订单详情",
        )

        self.assertEqual(result.category, "coffee_tea")
        self.assertEqual(result.thing, "咖啡")

    def test_unknown_result_is_pending(self) -> None:
        result = classify_locally(
            merchant="示例商户",
            product="未知项目",
            platform=None,
            payment_app="wechat",
            text="",
        )

        self.assertEqual(result.category, "uncategorized")
        self.assertEqual(result.source, "none")
        self.assertEqual(result.status, "pending")

    def test_specific_lottery_signal_beats_personal_qr_fallback(self) -> None:
        result = classify_locally(
            merchant="扫二维码付款-给示例体彩店",
            product=None,
            platform=None,
            payment_app="wechat",
            text="扫二维码付款-给示例体彩店",
        )

        self.assertEqual(result.category, "lottery")

    def test_pickle_shop_is_treated_as_grocery_food_purchase(self) -> None:
        result = classify_locally(
            merchant="示例泡菜店",
            product="收银台订单",
            platform=None,
            payment_app="wechat",
            text="",
        )

        self.assertEqual(result.category, "groceries")
