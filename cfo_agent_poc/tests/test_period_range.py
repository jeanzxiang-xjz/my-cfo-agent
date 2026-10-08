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


class ParseCustomRangeTests(unittest.TestCase):
    """闭区间日期 → 半开区间 [start, end+1天)。"""

    def test_inclusive_end_covers_the_whole_last_day(self) -> None:
        parsed = server.parse_custom_range({"start": "2026-08-01", "end": "2026-08-15"})
        self.assertEqual(
            parsed,
            {"start": "2026-08-01T00:00:00", "end": "2026-08-16T00:00:00"},
        )

    def test_single_day_range_spans_that_day(self) -> None:
        parsed = server.parse_custom_range({"start": "2026-08-03", "end": "2026-08-03"})
        self.assertEqual(
            parsed,
            {"start": "2026-08-03T00:00:00", "end": "2026-08-04T00:00:00"},
        )

    def test_month_boundary_is_not_clipped(self) -> None:
        parsed = server.parse_custom_range({"start": "2026-07-28", "end": "2026-08-12"})
        self.assertEqual(parsed["start"], "2026-07-28T00:00:00")
        self.assertEqual(parsed["end"], "2026-08-13T00:00:00")

    def test_invalid_input_falls_back_instead_of_raising(self) -> None:
        for bad in (
            None,
            {},
            {"start": "", "end": ""},
            {"start": "不是日期", "end": "2026-08-15"},
            {"start": "2026-08-15", "end": "2026-08-01"},  # 首尾颠倒
            {"start": "2026-13-01", "end": "2026-13-05"},  # 不存在的月份
        ):
            with self.subTest(bad=bad):
                self.assertIsNone(server.parse_custom_range(bad))


class CustomPeriodLabelTests(unittest.TestCase):
    def test_reads_as_a_chinese_date_span(self) -> None:
        self.assertEqual(
            server.custom_period_label({"start": "2026-08-01", "end": "2026-08-15"}),
            "8月1日–8月15日",
        )

    def test_single_day_says_one_day(self) -> None:
        self.assertEqual(
            server.custom_period_label({"start": "2026-08-03", "end": "2026-08-03"}),
            "8月3日",
        )

    def test_invalid_input_reads_as_all(self) -> None:
        self.assertEqual(server.custom_period_label({"start": "x", "end": "y"}), "全部")


class ComputePeriodDateRangeTests(unittest.TestCase):
    def test_custom_period_uses_the_supplied_range(self) -> None:
        self.assertEqual(
            server.compute_period_date_range("custom", {"start": "2026-08-01", "end": "2026-08-15"}),
            {"start": "2026-08-01T00:00:00", "end": "2026-08-16T00:00:00"},
        )

    def test_custom_period_with_bad_range_returns_none(self) -> None:
        self.assertIsNone(server.compute_period_date_range("custom", {"start": "", "end": ""}))
        self.assertIsNone(server.compute_period_date_range("custom", None))

    def test_preset_periods_ignore_the_custom_range(self) -> None:
        noise = {"start": "2020-01-01", "end": "2020-01-02"}
        for period in ("today", "week", "month", "last_month", "year"):
            with self.subTest(period=period):
                self.assertEqual(
                    server.compute_period_date_range(period, noise),
                    server.compute_period_date_range(period),
                )

    def test_all_still_means_unbounded(self) -> None:
        self.assertIsNone(server.compute_period_date_range("all"))


class OrientationContextCustomRangeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "period-range.sqlite"
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
                # 区间之前：不该被统计进来
                ("2026-07-31T20:00:00", 500.0, "food_delivery", "区间外早"),
                # 区间之内
                ("2026-08-01T00:00:00", 18.0, "food_delivery", "首日零点"),
                ("2026-08-07T12:00:00", 32.0, "transport", "中段"),
                ("2026-08-15T23:59:00", 50.0, "food_delivery", "末日深夜"),
                # 区间之后：不该被统计进来
                ("2026-08-16T00:00:00", 900.0, "shopping", "区间外晚"),
            ],
        )
        conn.commit()
        conn.close()
        self.addCleanup(self.temp_dir.cleanup)

    def test_summary_covers_exactly_the_selected_range(self) -> None:
        with server.use_ledger(server.Ledger(self.db_path.parent, db_file=self.db_path)):
            context = server.get_orientation_context(
                "custom", {"day": 100}, {"start": "2026-08-01", "end": "2026-08-15"}
            )

        self.assertEqual(context["current_period_label"], "8月1日–8月15日")
        self.assertEqual(
            context["current_period_date_range"],
            {"start": "2026-08-01T00:00:00", "end": "2026-08-16T00:00:00"},
        )
        summary = context["current_period_summary"]
        # 18 + 32 + 50，两端的 500 / 900 都在区间外
        self.assertEqual(summary["outflow_transaction_count"], 3)
        self.assertAlmostEqual(summary["total_outflow_cny"], 100.0, places=2)

    def test_bad_custom_range_degrades_to_all(self) -> None:
        with server.use_ledger(server.Ledger(self.db_path.parent, db_file=self.db_path)):
            context = server.get_orientation_context("custom", {}, {"start": "", "end": ""})

        # 落回「最早交易 ~ 明日零点」，5 笔全部计入，而不是报错或返回空。
        self.assertEqual(context["current_period_date_range"]["start"], "2026-07-31T20:00:00")
        self.assertEqual(context["current_period_summary"]["outflow_transaction_count"], 5)


if __name__ == "__main__":
    unittest.main()
