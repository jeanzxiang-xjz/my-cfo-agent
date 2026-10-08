from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path


WEB_APP_DIR = Path(__file__).resolve().parents[1] / "web_app"
if str(WEB_APP_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_APP_DIR))

import server


class ChatAnalysisContextTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "chat-context.sqlite"
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """
            create table transactions (
                paid_at text,
                status text,
                direction text,
                amount real,
                category text,
                merchant text,
                product text,
                thing text
            )
            """
        )
        conn.executemany(
            "insert into transactions values (?, 'success', 'outflow', ?, ?, ?, '', '')",
            [
                ("2026-08-01T06:30:00", 18.0, "food_delivery", "早餐店"),
                ("2026-08-02T10:15:00", 22.0, "coffee_tea", "咖啡店"),
                ("2026-08-03T20:10:00", 48.0, "food_delivery", "炭火烧烤"),
                ("2026-08-04T23:20:00", 26.0, "coffee_tea", "奶茶店"),
            ],
        )
        conn.commit()
        conn.close()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_time_slot_grouping_uses_payment_hours(self) -> None:
        with server.use_ledger(server.Ledger(self.db_path.parent, db_file=self.db_path)):
            result = server._tool_query_spending_summary({
                "start_date": "2026-08-01T00:00:00",
                "end_date": "2026-09-01T00:00:00",
                "group_by": "time_slot",
            })

        rows = {row["group"]: row for row in result["rows"]}
        self.assertEqual(rows["早餐前（0-8点）"]["outflow_count"], 1)
        self.assertEqual(rows["白天（8-18点）"]["outflow_count"], 1)
        self.assertEqual(rows["晚间（18-22点）"]["outflow_count"], 1)
        self.assertEqual(rows["深夜（22-24点）"]["outflow_count"], 1)

    def test_chat_prompt_limits_lifestyle_guidance_to_grounded_analysis(self) -> None:
        with server.use_ledger(server.Ledger(self.db_path.parent, db_file=self.db_path)):
            prompt = server.load_system_prompt()

        self.assertIn("消费健康提醒", prompt)
        self.assertIn("query_lifestyle_health_signals", prompt)
        self.assertIn("付款时间不等于进食或睡眠时间", prompt)

    def test_lifestyle_tool_combines_timing_and_food_type(self) -> None:
        with server.use_ledger(server.Ledger(self.db_path.parent, db_file=self.db_path)):
            result = server._tool_query_lifestyle_health_signals({
                "start_date": "2026-08-01T00:00:00",
                "end_date": "2026-09-01T00:00:00",
            })

        features = result["features"]
        self.assertEqual(features["late_food_drink_payments"]["count"], 1)
        keys = {item["key"] for item in features["food_type_signals"]}
        self.assertIn("barbecue_grill", keys)
        self.assertIn("sweet_drinks_desserts", keys)

    def test_orientation_context_includes_time_distribution(self) -> None:
        with server.use_ledger(server.Ledger(self.db_path.parent, db_file=self.db_path)):
            context = server.get_orientation_context("all", {"day": 100})

        summary = context["current_period_summary"]
        self.assertEqual(summary["outflow_transaction_count"], 4)
        self.assertEqual(len(summary["time_distribution"]), 4)
        self.assertEqual(summary["time_distribution"][0]["group"], "晚间（18-22点）")
        self.assertEqual(summary["lifestyle_health_features"]["ready_food_drink_payment_count"], 4)


if __name__ == "__main__":
    unittest.main()
