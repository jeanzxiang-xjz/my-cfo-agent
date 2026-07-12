from __future__ import annotations

import unittest

from cfo_agent_poc.bill_classifier import classify_locally


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
        self.assertEqual(result.thing, "餐饮外卖")
        self.assertGreaterEqual(result.confidence, 0.9)

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
