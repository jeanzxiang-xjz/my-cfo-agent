"""常用分类排序控件的静态契约。

原来两枚按钮都借用 categoryIcon("transfer")——那是一枚双向箭头，再靠 CSS 旋转
±90° 凑方向。旋转一个双向符号得到的还是双向符号：两枚长得一模一样，每次都得先
猜哪个是上、哪个是下；而且头尾那一端明明无处可去，按钮却照样是可点的样子。
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTROLLER = ROOT / "web_app" / "src" / "legacy-controller.js"
STYLES = ROOT / "web_app" / "styles.css"


class CategoryOrderControlTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = CONTROLLER.read_text(encoding="utf-8")
        self.styles = STYLES.read_text(encoding="utf-8")

    def test_arrows_point_one_way_each(self) -> None:
        self.assertIn("const ORDER_ARROWS = {", self.source)
        block = self.source[self.source.index("const ORDER_ARROWS = {") :][:400]
        # 值是 Phosphor 图标名（"arrow-up" / "arrow-down"），上下两枚必须是不同的单向箭头
        up = re.search(r"up:\s*[\"']([^\"']+)", block).group(1)
        down = re.search(r"down:\s*[\"']([^\"']+)", block).group(1)
        self.assertNotEqual(up, down, "上下两枚不能是同一个图标")

    def test_reorder_no_longer_borrows_the_category_glyph(self) -> None:
        row = self.source[self.source.index("function renderCategoryRow(") :][:2400]
        self.assertNotIn('categoryIcon("transfer")', row)
        self.assertIn('orderArrow("up")', row)
        self.assertIn('orderArrow("down")', row)

    def test_ends_are_disabled_not_dead(self) -> None:
        row = self.source[self.source.index("function renderCategoryRow(") :][:2400]
        self.assertIn("index === 0", row)
        self.assertIn("index === total - 1", row)

    def test_css_rotation_hack_is_gone(self) -> None:
        # 旋转 hack 留着就会和真箭头叠加，方向反而更乱。
        self.assertNotIn(".category-row-order button:last-child svg", self.styles)
        self.assertNotIn(".category-row-order button:first-child svg", self.styles)
        self.assertIn(".category-row-order button[disabled]", self.styles)

    def test_reorder_animates_with_a_forced_reflow(self) -> None:
        """换位是整段重画的，只能靠 FLIP 把新旧位置接上。

        两个地方一错就会「看着像没动效」：倒推与归零之间不强制回流，浏览器会认为
        值没变、根本不启动过渡；以及动效期间若放行重画，正在滑动的行会被换成新节点，
        动画断在半路。
        """
        flip = self.source[self.source.index("function playCategoryReorder(") :][:1500]
        self.assertIn("void document.getElementById(\"categoryList\")?.offsetHeight", flip)
        self.assertIn("state.categoryReorderAnimating = true", flip)
        manager = self.source[self.source.index("function renderCategoryManager(") :][:600]
        self.assertIn("if (!state.categoryReorderAnimating) renderCategoryList();", manager)

    def test_focus_survives_reaching_the_end(self) -> None:
        # 移到头之后同方向那枚会变禁用，焦点得转交给反方向那枚，不能掉在地上。
        handler = self.source[self.source.index('const move = event.target.closest("[data-category-move]")') :][:1500]
        self.assertIn("same && !same.disabled ? same", handler)


if __name__ == "__main__":
    unittest.main()
