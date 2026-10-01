"""现金流趋势弹窗的下钻视图契约。

柱子选「哪一期」，下钻区把那一期摊开（月 → 日历，周 → 七天，日 → 当天流水），
右栏给当日明细。这里锁住几条容易被改坏、肉眼又不一定看得出来的规则：

1. 下钻区的数字必须和柱子、账本同一个口径——待订正的交易不计入。
2. 弹窗里点交易会把证据抽屉叠在上面：Esc 要先关抽屉，不能越过它把弹窗关掉。
3. 在抽屉里校正完一笔，数据刷新后人还停在刚才那一期，而不是被弹回本月。
4. 旧的「逐期明细」列表已被下钻区取代，不该再回来。

弹窗住在 legacy-controller.js 里，仓库没有 JS 测试框架，这里把关键写法当数据读出来。
"""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTROLLER = ROOT / "web_app" / "src" / "legacy-controller.js"
APP = ROOT / "web_app" / "src" / "App.jsx"


def function_body(source: str, name: str, length: int = 1600) -> str:
    return source[source.index(f"function {name}(") :][:length]


class TrendDetailContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = CONTROLLER.read_text(encoding="utf-8")
        self.app = APP.read_text(encoding="utf-8")

    def test_drilldown_stats_exclude_correction_transactions(self) -> None:
        # transactionsBetween 走 analysisTransactions，待订正的交易天然不在里面；
        # 换成 state.transactions 直接筛，日历上的数就会和柱子、账本对不上。
        stats = function_body(self.source, "trendPeriodStats")
        self.assertIn("transactionsBetween(item.start, item.end)", stats)
        self.assertNotIn("state.transactions", stats)
        self.assertIn("normalizeAmount(tx)", stats)

    def test_escape_closes_evidence_drawer_before_modal(self) -> None:
        handler = self.source[self.source.index('if (event.key === "Escape")') :][:1200]
        drawer = handler.index('$("evidenceDrawer").hidden')
        modal = handler.index("topmostOpenModal()")
        self.assertLess(drawer, modal)

    def test_data_refresh_keeps_the_period_being_inspected(self) -> None:
        self.assertNotIn('if (!$("trendModal").hidden) renderTrendModal();', self.source)
        self.assertGreaterEqual(self.source.count("renderTrendModal({ preserveSelection: true })"), 5)
        render = function_body(self.source, "renderTrendModal")
        self.assertIn("trendIndexOf(previous.start)", render)

    def test_shift_out_of_window_does_not_toggle_selection_off(self) -> None:
        # 窗口平移后序列整个换了，旧下标恰好等于新下标时会被当成「再点一次」取消掉。
        shift = function_body(self.source, "shiftTrendPeriod", 1800)
        self.assertIn("state.trendSelected = null", shift)
        self.assertIn("rebuildTrendSeries()", shift)

    def test_window_never_reaches_into_the_future(self) -> None:
        shift = function_body(self.source, "shiftTrendPeriod", 1800)
        self.assertIn("state.trendWindowEnd = end >= today ? null : end", shift)
        can_shift = function_body(self.source, "trendCanShift", 600)
        self.assertIn("target <= startOfDay(getAnchorDate())", can_shift)

    def test_breakdown_list_is_replaced_by_drilldown(self) -> None:
        self.assertNotIn("renderTrendBreakdown", self.source)
        self.assertNotIn("trendBreakdown", self.app)
        self.assertIn('id="trendDetail"', self.app)
        self.assertIn('id="trendSidePanel"', self.app)


if __name__ == "__main__":
    unittest.main()
