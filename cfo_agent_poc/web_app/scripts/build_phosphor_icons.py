"""
从 Phosphor 图标库（regular 字重）抽出系统用到的图标，生成 src/phosphor-icons.js。

    python3 cfo_agent_poc/web_app/scripts/build_phosphor_icons.py ~/Downloads/phosphor-icons

要加新图标：把名字补进 ICON_NAMES 再跑一遍。图标库从 https://phosphoricons.com 下载（MIT 协议）。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# 分类图标（含图标选择器里的备选）+ 界面功能图标
ICON_NAMES = sorted({
    # 分类默认图标
    "coffee", "fork-knife", "letter-circle-p", "charging-station", "car", "basket", "cherries", "cake",
    "student", "book-open", "package", "subway", "heartbeat", "chart-line-up", "buildings", "phone",
    "ticket", "credit-card", "drop", "pencil-simple", "cloud", "tote", "island", "clover",
    "arrows-left-right", "t-shirt", "paw-print", "scissors", "couch", "baby-carriage", "money-wavy",
    "arrow-u-up-left", "handshake", "shield-plus", "hand-heart", "devices", "tent", "club",
    "dots-three-circle",
    # 图标选择器里额外给的备选
    "broom", "beer-stein", "tooth", "game-controller", "film-strip", "headphones", "camera", "bone",
    "cat", "dog", "dice-six",
    # 界面功能图标
    "calendar-dots", "x-circle", "plus-circle", "sliders-horizontal", "user-circle", "caret-right",
    "caret-left", "caret-down", "caret-up-down", "sparkle", "eye", "receipt", "trend-up", "trend-down",
    "copy", "trash", "corners-out", "corners-in", "arrow-line-down", "arrows-clockwise", "plus",
    "arrow-right", "chat-circle-dots", "arrow-down", "arrow-up", "gear-six", "funnel", "list-bullets",
    "file-text", "tray", "warning-circle", "envelope-simple", "x", "magnifying-glass", "device-mobile",
    "heart",
    # 记一笔：触发快捷指令的四种方式
    "hand-tap", "record",
    # 记一笔弹窗
    "link", "download-simple", "key", "prohibit", "microphone", "upload-simple",
    "check-circle", "hourglass",
})

# Phosphor 里没有、按同一规格手绘的图标（256 网格、16 线宽、圆头圆角，class 规则同上）。
CUSTOM_ICONS = {
    # iPhone 操作按钮：机身左侧边线（顶部圆角拐出）+ 实心侧键 + 指向侧键的箭头，照苹果「操作按钮」图标的构图
    "action-button": (
        # 形状比较瘦，几处都放大到贴近 256 画布边缘（留出半个线宽），视觉体量才和旁边的手势图标相当
        '<path d="M180,244V96a64,64,0,0,1,64-64" class="s r"/>'
        '<rect x="140" y="96" width="40" height="80" rx="16" class="f"/>'
        '<line x1="12" y1="136" x2="108" y2="136" class="s r"/>'
        '<polyline points="64 92 108 136 64 180" class="s r"/>'
    ),
}

STROKE = re.compile(r'(?: fill="none")? stroke="currentColor"((?: stroke-[a-z]+="[^"]*")*)')
ROUND = ' stroke-linecap="round" stroke-linejoin="round"'


def convert(svg: str) -> str:
    inner = re.sub(r"^<svg[^>]*>|</svg>\s*$", "", svg.strip())
    inner = inner.replace('<rect width="256" height="256" fill="none"/>', "")

    def element(match: re.Match) -> str:
        tag, attrs = match.group(1), match.group(2)
        stroke = STROKE.search(attrs)
        if stroke:
            rest = stroke.group(1).replace(' stroke-width="16"', "")
            cls = "s r" if ROUND in rest else "s"
            rest = rest.replace(ROUND, "")
            return f'<{tag}{attrs[:stroke.start()]}{attrs[stroke.end():]} class="{cls}"{rest}/>'
        if 'fill="none"' in attrs:
            return match.group(0)
        return f'<{tag}{attrs} class="f"/>'

    return re.sub(r"<(\w+)((?:\s[^>]*?)?)/>", element, inner)


def main(library: Path) -> None:
    out = Path(__file__).resolve().parent.parent / "src" / "phosphor-icons.js"
    lines = [
        "// 由 scripts/build_phosphor_icons.py 生成，别手改。",
        "// 图标来自 Phosphor Icons（regular 字重，MIT 协议，© 2020-2024 Phosphor Icons）；末尾几个是按同一规格手绘的补充。",
        "// viewBox 是 0 0 256 256；线条用 class=\"s\"，填充用 class=\"f\"，样式在 styles.css 的 svg.ph 段。",
        "export const PHOSPHOR_ICONS = {",
    ]
    for name in ICON_NAMES:
        path = library / "SVGs" / "regular" / f"{name}.svg"
        if not path.exists():
            sys.exit(f"图标库里没有 {name}（{path}）")
        lines.append(f'  "{name}": \'{convert(path.read_text(encoding="utf-8"))}\',')
    for name, markup in sorted(CUSTOM_ICONS.items()):
        lines.append(f'  "{name}": \'{markup}\',')
    lines.append("};")
    lines.append("")
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {out} ({len(ICON_NAMES)} + {len(CUSTOM_ICONS)} custom icons, {out.stat().st_size / 1024:.1f}KB)")


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else Path.home() / "Downloads" / "phosphor-icons").expanduser())
