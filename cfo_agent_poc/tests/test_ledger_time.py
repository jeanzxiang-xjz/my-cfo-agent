from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from cfo_agent_poc import bill_store, ledger_time


WEB_APP_DIR = Path(__file__).resolve().parents[1] / "web_app"
if str(WEB_APP_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_APP_DIR))

import generate_snapshot
import server


class _EnvTzMixin:
    """临时切换进程时区 / CFO_LEDGER_TZ，结束后恢复，避免污染其他用例。"""

    def _set_env(self, key: str, value: str | None) -> None:
        if not hasattr(self, "_saved_env"):
            self._saved_env = {}
        self._saved_env.setdefault(key, os.environ.get(key))
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
        if key == "TZ":
            time.tzset()
        ledger_time.reset_ledger_tz_cache()

    def _restore_env(self) -> None:
        for key, value in getattr(self, "_saved_env", {}).items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        time.tzset()
        ledger_time.reset_ledger_tz_cache()


class LedgerNowTests(_EnvTzMixin, unittest.TestCase):
    def tearDown(self) -> None:
        self._restore_env()

    def test_independent_of_process_timezone(self) -> None:
        self._set_env("CFO_LEDGER_TZ", None)
        for process_tz in ("UTC", "America/Los_Angeles", "Europe/London", "Asia/Tokyo"):
            with self.subTest(process_tz=process_tz):
                self._set_env("TZ", process_tz)
                expected = datetime.now(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None)
                actual = ledger_time.ledger_now()
                self.assertIsNone(actual.tzinfo)
                self.assertLess(abs((actual - expected).total_seconds()), 5)
                self.assertEqual(ledger_time.ledger_tz_name(), "Asia/Shanghai")

    def test_configurable_via_env(self) -> None:
        self._set_env("CFO_LEDGER_TZ", "Europe/London")
        expected = datetime.now(ZoneInfo("Europe/London")).replace(tzinfo=None)
        self.assertLess(abs((ledger_time.ledger_now() - expected).total_seconds()), 5)
        self.assertEqual(ledger_time.ledger_tz_name(), "Europe/London")

    def test_invalid_timezone_falls_back_to_shanghai(self) -> None:
        self._set_env("CFO_LEDGER_TZ", "Not/AZone")
        with patch("sys.stderr"):
            self.assertEqual(ledger_time.ledger_tz_name(), "Asia/Shanghai")
        expected = datetime.now(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None)
        self.assertLess(abs((ledger_time.ledger_now() - expected).total_seconds()), 5)

    def test_iso_has_no_offset_and_seconds_precision(self) -> None:
        value = ledger_time.ledger_now_iso()
        self.assertRegex(value, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")


class PeriodRangeUsesLedgerClockTests(unittest.TestCase):
    """北京时间凌晨 0:30 时，UTC 服务器上 datetime.now() 还是前一天——区间必须按账本时区算。"""

    def _range(self, period: str, now: datetime) -> dict:
        with patch.object(server, "ledger_now", return_value=now):
            return server.compute_period_date_range(period)

    def test_today_after_beijing_midnight(self) -> None:
        self.assertEqual(
            self._range("today", datetime(2026, 11, 11, 0, 30)),
            {"start": "2026-11-11T00:00:00", "end": "2026-11-12T00:00:00"},
        )

    def test_week_starts_on_monday(self) -> None:
        # 2026-11-11 是周三
        self.assertEqual(
            self._range("week", datetime(2026, 11, 11, 0, 30)),
            {"start": "2026-11-09T00:00:00", "end": "2026-11-16T00:00:00"},
        )

    def test_month_and_year_cross_boundaries(self) -> None:
        now = datetime(2026, 12, 31, 23, 59)
        self.assertEqual(self._range("month", now), {"start": "2026-12-01T00:00:00", "end": "2027-01-01T00:00:00"})
        self.assertEqual(self._range("year", now), {"start": "2026-01-01T00:00:00", "end": "2027-01-01T00:00:00"})
        self.assertEqual(
            self._range("last_month", datetime(2027, 1, 1, 0, 5)),
            {"start": "2026-12-01T00:00:00", "end": "2027-01-01T00:00:00"},
        )


class ScopedTransactionsTests(unittest.TestCase):
    """与前端 scopedTransactions 同口径：锚点是账本时区的现在，晚于现在的交易不计入。"""

    NOW = datetime(2026, 11, 11, 21, 47)

    def _tx(self, paid_at: str) -> dict:
        return {"paid_at": paid_at, "amount": 10, "merchant": "测试商户", "analysis_eligible": True}

    def _scoped(self, period: str) -> list[str]:
        txs = [
            self._tx("2026-11-11T21:00:00"),  # 今天刚发生
            self._tx("2026-11-11T22:30:00"),  # 晚于现在：不计入
            self._tx("2026-11-09T08:00:00"),  # 本周一
            self._tx("2026-11-01T08:00:00"),  # 本月但不在本周
            self._tx("2026-10-31T23:59:00"),  # 上月
        ]
        with patch.object(server, "ledger_now", return_value=self.NOW):
            return [tx["paid_at"] for tx in server.scoped_transactions(txs, period)]

    def test_today(self) -> None:
        self.assertEqual(self._scoped("today"), ["2026-11-11T21:00:00"])

    def test_week(self) -> None:
        self.assertEqual(self._scoped("week"), ["2026-11-11T21:00:00", "2026-11-09T08:00:00"])

    def test_month(self) -> None:
        self.assertEqual(
            self._scoped("month"),
            ["2026-11-11T21:00:00", "2026-11-09T08:00:00", "2026-11-01T08:00:00"],
        )

    def test_all_excludes_only_future(self) -> None:
        self.assertNotIn("2026-11-11T22:30:00", self._scoped("all"))
        self.assertEqual(len(self._scoped("all")), 4)


class LedgerTimezoneExposedTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.db_path = Path(self.temp_dir.name) / "ledger-tz.sqlite"
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "create table transactions (paid_at text, status text, direction text, amount real,"
            " category text, merchant text, product text, thing text)"
        )
        conn.execute(
            "insert into transactions values ('2026-11-11T00:10:00', 'success', 'outflow', 18.0,"
            " 'food_delivery', '凌晨夜宵', '', '')"
        )
        conn.commit()
        conn.close()

    def test_orientation_context_reports_ledger_today_and_timezone(self) -> None:
        with patch.object(server, "ledger_now", return_value=datetime(2026, 11, 11, 0, 30)):
            with server.use_ledger(server.Ledger(self.db_path.parent, db_file=self.db_path)):
                context = server.get_orientation_context("today", {})
        self.assertEqual(context["today"], "2026-11-11")
        self.assertEqual(context["timezone"], ledger_time.ledger_tz_name())
        self.assertEqual(context["current_period_summary"]["outflow_transaction_count"], 1)

    def test_snapshot_payload_carries_ledger_timezone(self) -> None:
        snapshot_db = Path(self.temp_dir.name) / "snapshot.sqlite"
        conn = sqlite3.connect(snapshot_db)
        bill_store.ensure_bill_tables(conn)
        conn.close()
        payload = generate_snapshot.build_payload(snapshot_db)
        self.assertEqual(payload["ledger_timezone"], ledger_time.ledger_tz_name())
        generated = datetime.fromisoformat(payload["generated_at"])
        self.assertIsNone(generated.tzinfo)
        self.assertLess(abs(generated - ledger_time.ledger_now()), timedelta(seconds=5))


if __name__ == "__main__":
    unittest.main()
