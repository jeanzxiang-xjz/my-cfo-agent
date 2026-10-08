from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

WEB_APP_DIR = Path(__file__).resolve().parents[1] / "web_app"
if str(WEB_APP_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_APP_DIR))

from server import (
    Ledger,
    build_lifestyle_health_features,
    build_profile_features,
    ensure_ledger_schema,
    load_profile_report_prompt,
    normalize_profile_report,
    profile_ledger_fingerprint,
    use_ledger,
)


def sample_transaction(uid: str, amount: float, paid_at: str, merchant: str, category: str) -> dict:
    return {
        "transaction_uid": uid,
        "amount": amount,
        "paid_at": paid_at,
        "merchant": merchant,
        "product": "",
        "thing": "",
        "category": category,
        "status": "success",
        "direction": "outflow",
        "classification_status": "resolved",
        "_amount": amount,
        "_paid_at": datetime.fromisoformat(paid_at),
    }


class ProfileReportTests(unittest.TestCase):
    def setUp(self) -> None:
        # 分类名称和提示词里的称呼都按账本取，给每个用例一个空的临时账本
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        ledger = Ledger(Path(temp_dir.name))
        ensure_ledger_schema(ledger)
        binding = use_ledger(ledger)
        binding.__enter__()
        self.addCleanup(binding.__exit__, None, None, None)

    def test_profile_prompt_requires_grounded_lifestyle_guidance(self) -> None:
        prompt = load_profile_report_prompt()

        self.assertIn("独立的 `wellbeing` 篇章", prompt)
        self.assertIn("lifestyle_health_features", prompt)
        self.assertIn("付款时间不等于实际进食", prompt)

    def test_profile_features_cover_full_ledger(self) -> None:
        rows = [
            sample_transaction("a", 18.5, "2026-07-01T09:10:00", "早餐店", "food_delivery"),
            sample_transaction("b", 25.0, "2026-07-05T22:30:00", "奶茶店", "coffee_tea"),
            sample_transaction("c", 60.0, "2026-08-01T19:15:00", "餐厅", "food_delivery"),
        ]

        features = build_profile_features(rows)

        self.assertEqual(features["coverage"], {
            "start_date": "2026-07-01",
            "end_date": "2026-08-01",
            "transaction_count": 3,
            "total_outflow_cny": 103.5,
            "active_days": 3,
            "active_months": 2,
        })
        self.assertEqual(features["categories"][0]["label"], "外卖/餐饮")
        self.assertEqual(features["categories"][0]["count"], 2)
        self.assertEqual(features["amount_profile"]["median_cny"], 25.0)
        self.assertEqual(len(features["representative_transactions"]), 3)
        time_distribution = {item["label"]: item for item in features["time_distribution"]}
        self.assertEqual(time_distribution["白天（8-18点）"]["count"], 1)
        self.assertEqual(time_distribution["晚间（18-22点）"]["count"], 1)
        self.assertEqual(time_distribution["深夜（22-24点）"]["count"], 1)
        lifestyle = features["lifestyle_health_features"]
        self.assertEqual(lifestyle["ready_food_drink_payment_count"], 3)
        self.assertEqual(lifestyle["late_food_drink_payments"]["count"], 1)
        self.assertEqual(lifestyle["food_type_signals"][0]["key"], "sweet_drinks_desserts")

    def test_lifestyle_features_combine_late_timing_and_food_type(self) -> None:
        rows = [
            sample_transaction("a", 68.0, "2026-08-01T22:40:00", "阿强烧烤", "food_delivery"),
            sample_transaction("b", 42.0, "2026-08-03T23:15:00", "夜猫烧烤", "food_delivery"),
            sample_transaction("c", 19.0, "2026-08-04T20:10:00", "清茶铺", "coffee_tea"),
        ]

        features = build_lifestyle_health_features(rows)

        barbecue = next(item for item in features["food_type_signals"] if item["key"] == "barbecue_grill")
        self.assertEqual(features["late_food_drink_payments"]["count"], 2)
        self.assertEqual(features["late_food_drink_payments"]["count_share_percent"], 66.7)
        self.assertEqual(barbecue["count"], 2)
        self.assertEqual(barbecue["late_night_count"], 2)

    def test_profile_fingerprint_changes_when_classification_changes(self) -> None:
        rows = [sample_transaction("a", 18.5, "2026-07-01T09:10:00", "早餐店", "food_delivery")]
        first = profile_ledger_fingerprint(rows)
        rows[0]["category"] = "coffee_tea"
        second = profile_ledger_fingerprint(rows)

        self.assertNotEqual(first, second)

    def test_profile_report_normalization_uses_authoritative_coverage(self) -> None:
        features = build_profile_features([
            sample_transaction("a", 18.5, "2026-07-01T09:10:00", "早餐店", "food_delivery")
        ])
        raw = {
            "persona": {
                "title": "城市续航玩家",
                "subtitle": "把效率吃进日常",
                "intro": "账本刚开场，早餐先写下第一句。",
                "traits": [
                    {"emoji": "🥣", "label": "早间补给", "text": "一天从一顿早餐启动。", "evidence": "早餐店 1 笔 18.5 元"},
                    {"emoji": "🪶", "label": "轻量开场", "text": "目前只有一笔，先不把偶然当习惯。", "evidence": "有效支出共 1 笔"},
                ],
            },
            "tags": [
                {"emoji": "🥣", "label": "早餐续航", "reason": "早间补给明确", "evidence": "早餐店 1 笔 18.5 元"},
                {"emoji": "⚡", "label": "小额快决", "reason": "单笔金额克制", "evidence": "中位数 18.5 元"},
                {"emoji": "🌱", "label": "样本待长", "reason": "目前记录较少", "evidence": "当前共 1 笔"},
            ],
            "highlights": [
                {"emoji": "💴", "value": "18.5 元", "label": "累计支出", "context": "当前唯一一笔支出"},
                {"emoji": "🧾", "value": "1 笔", "label": "消费笔数", "context": "画像仍处于起步阶段"},
                {"emoji": "🥐", "value": "100%", "label": "餐饮占比", "context": "全部来自早餐补给"},
            ],
            "moments": [
                {"emoji": "🌤️", "title": "一天从早餐开始", "lines": ["第一笔记录落在早餐时段。"], "evidence": "7 月 1 日 9:10，18.5 元"},
                {"emoji": "📖", "title": "账本刚刚开场", "lines": ["当前只有一笔记录。", "先不把偶然写成习惯。"], "evidence": "有效支出共 1 笔"},
            ],
            "wellbeing": {
                "headline": "早餐付款提供了一点规律线索",
                "summary": "目前只有一笔餐饮记录，只能暂时推测早间进餐节奏。",
                "confidence": "低",
                "signals": [
                    {"label": "进餐节奏", "inference": "可能习惯在上午安排第一餐。", "evidence": "早餐店 9:10 付款 1 笔", "confidence": "低"},
                    {"label": "样本充分度", "inference": "记录太少，无法判断长期饮食构成。", "evidence": "餐饮付款仅 1 笔", "confidence": "低"},
                ],
                "reminder": "继续记录一周，再观察餐时是否稳定。",
                "disclaimer": "付款记录只能提供生活线索，不能替代真实饮食和作息记录。",
            },
            "cfo": {
                "headline": "当前画像只是开场，真实记录会让它更像你。",
                "takeaways": [
                    {"emoji": "👍", "label": "值得肯定", "text": "第一笔记录已经落进账本。"},
                    {"emoji": "👀", "label": "留意一下", "text": "样本太少，暂时不放大单次选择。"},
                ],
                "suggestions": ["继续记录一周后再更新画像。"],
            },
        }

        report = normalize_profile_report(raw, features)

        self.assertEqual(report["persona"]["title"], "城市续航玩家")
        self.assertEqual(len(report["persona"]["traits"]), 2)
        self.assertEqual(report["coverage"], features["coverage"])
        self.assertEqual(len(report["tags"]), 3)
        self.assertEqual(report["moments"][1]["lines"], ["当前只有一笔记录。", "先不把偶然写成习惯。"])
        self.assertEqual(report["wellbeing"]["confidence"], "低")
        self.assertEqual(len(report["wellbeing"]["signals"]), 2)
        self.assertEqual(len(report["cfo"]["takeaways"]), 2)
