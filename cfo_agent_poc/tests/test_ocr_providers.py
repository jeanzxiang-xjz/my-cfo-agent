from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from cfo_agent_poc import ocr_providers
from cfo_agent_poc.bill_store import extract_field, parse_bill_text
from cfo_agent_poc.ocr_providers import (
    OCRError,
    _check_supported_format,
    lines_from_prism,
    text_from_rapidocr,
    text_from_recognize_data,
)

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"

IMAGE_HEIGHT = 2000
ROW_HEIGHT = 90
LINE_HEIGHT = 40


def word_entry(text: str, x: int, y: int) -> dict:
    """构造一条 prism_wordsInfo：pos 是顺时针四角点，像素坐标、原点左上。"""
    width = max(len(text) * 20, 20)
    return {
        "word": text,
        "pos": [
            {"x": x, "y": y},
            {"x": x + width, "y": y},
            {"x": x + width, "y": y + LINE_HEIGHT},
            {"x": x, "y": y + LINE_HEIGHT},
        ],
    }


def prism_payload(rows: list[list[str]], *, jitter: int = 0) -> dict:
    """把「每行若干个左右并排的条目」摊平成 prism_wordsInfo。

    jitter 用来模拟同一视觉行里两块文字的 y 并不严格相等的真实情况。
    """
    entries = []
    for row_index, row in enumerate(rows):
        for column_index, text in enumerate(row):
            entries.append(
                word_entry(
                    text,
                    x=60 + column_index * 400,
                    y=row_index * ROW_HEIGHT + (jitter if column_index else 0),
                )
            )
    # 打乱顺序：真实返回并不保证按阅读顺序排列，排序逻辑必须自己兜住。
    shuffled = entries[::-1]
    return {"height": IMAGE_HEIGHT, "width": 1200, "prism_wordsInfo": shuffled}


# 一张微信交易详情截图的版面：左标签、右值在同一视觉行上，各自是独立的识别条目。
WECHAT_DETAIL_ROWS = [
    ["<"],
    ["1友佳"],
    ["易友佳便利店"],
    ["主页"],
    ["• 交易详情"],
    ["-8.00"],
    ["易友佳便利店"],
    ["当前状态", "支付成功"],
    ["收单机构", "财付通支付科技有限公司"],
    ["支付时间", "2026年07月11日 20:30:49"],
    ["支付方式", "零钱"],
    ["交易单号", "4500000000000000000000000001"],
    ["经营单号", "104250000000000000000000000001"],
    ["交易服务", "对订单有疑惑"],
]


class PrismReadingOrderTests(unittest.TestCase):
    def test_reproduces_apple_vision_line_layout(self) -> None:
        """重建结果必须与 Apple Vision 的输出逐行一致。

        关键点：同一视觉行的标签和值**各占一行**，不能拼成一行。
        bill_store 的字段抽取正则要求标签独占一行，拼起来会让解析全面失配。
        """
        expected = (FIXTURE_DIR / "wechat_transaction_detail_convenience.txt").read_text(
            encoding="utf-8"
        ).strip()

        self.assertEqual(lines_from_prism(prism_payload(WECHAT_DETAIL_ROWS)), expected)

    def test_same_row_entries_stay_on_separate_lines_and_order_left_to_right(self) -> None:
        text = lines_from_prism(prism_payload(WECHAT_DETAIL_ROWS))
        lines = text.splitlines()

        self.assertIn("支付时间", lines)
        self.assertEqual(lines[lines.index("支付时间") + 1], "2026年07月11日 20:30:49")
        self.assertNotIn("支付时间 2026年07月11日 20:30:49", lines)

    def test_tolerates_slight_y_drift_within_a_row(self) -> None:
        """同一行左右两块的 y 略有偏差时，仍应判为同一行并按 x 排序。"""
        drifted = lines_from_prism(prism_payload(WECHAT_DETAIL_ROWS, jitter=8))

        self.assertEqual(drifted, lines_from_prism(prism_payload(WECHAT_DETAIL_ROWS)))

    def test_reconstructed_text_feeds_the_bill_parser(self) -> None:
        """重建出的文本要能被既有解析器正常抽字段——这才是排序工作的意义。"""
        text = lines_from_prism(prism_payload(WECHAT_DETAIL_ROWS))

        self.assertEqual(extract_field(text, "支付时间"), "2026年07月11日 20:30:49")
        self.assertEqual(extract_field(text, "支付方式"), "零钱")
        self.assertEqual(extract_field(text, "交易单号"), "4500000000000000000000000001")
        self.assertEqual(extract_field(text, "收单机构"), "财付通支付科技有限公司")

    def test_full_width_colon_from_aliyun_still_yields_paid_at(self) -> None:
        """阿里云实测会把时间里的冒号识别成全角，且丢掉日期与时间之间的空格。

        归一化不到位的话 paid_at 会整个抽空——这是实测中唯一影响解析结果的差异。
        """
        rows = [row[:] for row in WECHAT_DETAIL_ROWS]
        rows[9] = ["支付时间", "2026年07月11日20：30：49"]

        parsed = parse_bill_text(lines_from_prism(prism_payload(rows)), source_hint="wechat")

        self.assertEqual(parsed.paid_at, "2026-07-11T20:30:49")

    def test_half_width_parens_still_strip_the_store_suffix_from_merchant(self) -> None:
        """实测：同一张截图，Vision 给全角括号、阿里云给半角。

        只认全角的话商户会退化成页面顶部的平台泛称（「美团平台商户」），
        而不是真正的门店主体。
        """
        merchants = []
        for left, right in [("（", "）"), ("(", ")")]:
            rows = [
                ["美团平台商户"],
                ["-21.00"],
                ["当前状态", "支付成功"],
                ["支付时间", "2026年7月19日 18:47:04"],
                ["商品", f"丑师傅白辣椒炒肉{left}顺天财富店{right}-大众点评App"],
                ["支付方式", "零钱"],
            ]
            merchants.append(
                parse_bill_text(lines_from_prism(prism_payload(rows)), source_hint="wechat").merchant
            )

        self.assertEqual(merchants, ["丑师傅白辣椒炒肉", "丑师傅白辣椒炒肉"])

    def test_interpunct_inside_a_brand_name_is_not_a_split_point(self) -> None:
        """实测：Vision 把间隔号识别成 •，阿里云识别成 ·。

        「暖燕·姨妈热饮·现炖燕窝（滨江店）」里的间隔号是店名自身的一部分，
        先按间隔号切会只剩「暖燕」。带门店后缀时应当按括号切。
        """
        merchants = []
        for dot, left, right in [("•", "（", "）"), ("·", "(", ")")]:
            rows = [
                ["-20.80"],
                ["当前状态", "支付成功"],
                ["支付时间", "2026年7月6日 12:00:00"],
                ["商品", f"暖燕{dot}姨妈热饮{dot}现炖燕窝{left}滨江店{right}-美团App"],
                ["支付方式", "零钱"],
            ]
            merchants.append(
                parse_bill_text(lines_from_prism(prism_payload(rows)), source_hint="wechat").merchant
            )

        self.assertEqual(merchants[0], "暖燕•姨妈热饮•现炖燕窝")
        self.assertEqual(merchants[1], "暖燕·姨妈热饮·现炖燕窝")

    def test_falls_back_to_content_when_word_boxes_are_missing(self) -> None:
        payload = {"height": IMAGE_HEIGHT, "content": "账单详情\n支付成功", "prism_wordsInfo": []}

        self.assertEqual(lines_from_prism(payload), "账单详情\n支付成功")

    def test_uses_flat_xy_fields_when_pos_is_absent(self) -> None:
        payload = {
            "height": IMAGE_HEIGHT,
            "prism_wordsInfo": [
                {"word": "支付成功", "x": 400, "y": 100, "height": LINE_HEIGHT},
                {"word": "当前状态", "x": 60, "y": 100, "height": LINE_HEIGHT},
                {"word": "-8.00", "x": 60, "y": 10, "height": LINE_HEIGHT},
            ],
        }

        self.assertEqual(lines_from_prism(payload), "-8.00\n当前状态\n支付成功")

    def test_survives_missing_image_height(self) -> None:
        payload = prism_payload(WECHAT_DETAIL_ROWS)
        payload.pop("height")

        self.assertEqual(lines_from_prism(payload), lines_from_prism(prism_payload(WECHAT_DETAIL_ROWS)))


class RecognizeDataCoercionTests(unittest.TestCase):
    def test_accepts_data_as_json_string(self) -> None:
        payload = prism_payload(WECHAT_DETAIL_ROWS)

        self.assertEqual(
            text_from_recognize_data(json.dumps(payload, ensure_ascii=False)),
            lines_from_prism(payload),
        )

    def test_accepts_data_as_dict(self) -> None:
        payload = prism_payload(WECHAT_DETAIL_ROWS)

        self.assertEqual(text_from_recognize_data(payload), lines_from_prism(payload))

    def test_rejects_empty_data(self) -> None:
        with self.assertRaises(OCRError):
            text_from_recognize_data(None)

    def test_rejects_malformed_json(self) -> None:
        with self.assertRaises(OCRError):
            text_from_recognize_data("{not json")


def rapidocr_result(rows: list[list[str]], *, jitter: int = 0) -> SimpleNamespace:
    """同一份版面换成 RapidOCR 的返回形状：boxes 是像素四角点，txts 与之一一对应。"""
    payload = prism_payload(rows, jitter=jitter)
    boxes = [[[point["x"], point["y"]] for point in item["pos"]] for item in payload["prism_wordsInfo"]]
    txts = tuple(item["word"] for item in payload["prism_wordsInfo"])
    image = SimpleNamespace(shape=(payload["height"], payload["width"], 3))
    return SimpleNamespace(boxes=boxes, txts=txts, scores=tuple(1.0 for _ in txts), img=image)


class RapidOCRReadingOrderTests(unittest.TestCase):
    def test_same_layout_reads_exactly_like_aliyun(self) -> None:
        """同一张截图，RapidOCR 和阿里云重建出的文本必须逐行一致，下游解析器才无感。"""
        self.assertEqual(
            text_from_rapidocr(rapidocr_result(WECHAT_DETAIL_ROWS)),
            lines_from_prism(prism_payload(WECHAT_DETAIL_ROWS)),
        )

    def test_label_and_value_stay_on_separate_lines_despite_drift(self) -> None:
        lines = text_from_rapidocr(rapidocr_result(WECHAT_DETAIL_ROWS, jitter=8)).splitlines()

        self.assertEqual(lines[lines.index("支付时间") + 1], "2026年07月11日 20:30:49")

    def test_empty_result_yields_empty_text(self) -> None:
        empty = SimpleNamespace(boxes=None, txts=None, scores=None, img=None)

        self.assertEqual(text_from_rapidocr(empty), "")


class ProviderSelectionTests(unittest.TestCase):
    def test_rapidocr_when_configured_or_left_blank(self) -> None:
        for configured in ("rapidocr", "RapidOCR", " rapidocr ", ""):
            with patch.dict(os.environ, {"CFO_OCR_PROVIDER": configured}):
                self.assertEqual(ocr_providers.provider_name(), "rapidocr")

    def test_aliyun_and_vision_only_when_asked_for(self) -> None:
        for configured in ("aliyun", "vision"):
            with patch.dict(os.environ, {"CFO_OCR_PROVIDER": configured}):
                self.assertEqual(ocr_providers.provider_name(), configured)

    def test_auto_is_no_longer_accepted(self) -> None:
        # auto 以前在 Linux 上意味着阿里云；现在要求写明后端，旧配置启动预热时就报出来
        with patch.dict(os.environ, {"CFO_OCR_PROVIDER": "auto"}), self.assertRaises(OCRError) as ctx:
            ocr_providers.warm_up()

        self.assertIn("rapidocr / vision / aliyun", str(ctx.exception))

    def test_unknown_provider_lists_the_choices(self) -> None:
        with patch.dict(os.environ, {"CFO_OCR_PROVIDER": "tesseract"}), self.assertRaises(OCRError) as ctx:
            ocr_providers.ocr_image("/tmp/a.png")

        self.assertIn("rapidocr", str(ctx.exception))

    def test_missing_rapidocr_explains_how_to_install(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".png") as image, patch.object(ocr_providers, "_rapidocr", None), \
                patch.dict(sys.modules, {"rapidocr": None}), self.assertRaises(OCRError) as ctx:
            ocr_providers._ocr_rapidocr(image.name)

        self.assertIn("requirements.txt", str(ctx.exception))

    def test_thread_count_defaults_to_cpu_count(self) -> None:
        with patch.dict(os.environ, {"CFO_OCR_THREADS": ""}):
            self.assertEqual(ocr_providers._rapidocr_threads(), os.cpu_count() or 1)
        with patch.dict(os.environ, {"CFO_OCR_THREADS": "2"}):
            self.assertEqual(ocr_providers._rapidocr_threads(), 2)


CJK_FONTS = [
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc",
]
CJK_FONT = next((font for font in CJK_FONTS if Path(font).is_file()), None)


@unittest.skipUnless(importlib.util.find_spec("rapidocr") and CJK_FONT, "没装 RapidOCR 或没有中文字体")
class RapidOCRModelTests(unittest.TestCase):
    """真模型跑一张现画的微信账单：识别 → 解析，金额、时间、单号都要对。"""

    def test_recognizes_a_rendered_wechat_bill(self) -> None:
        from PIL import Image, ImageDraw, ImageFont

        font = ImageFont.truetype(CJK_FONT, 40)
        image = Image.new("RGB", (1206, 1400), "white")
        draw = ImageDraw.Draw(image)
        draw.text((420, 80), "示例便利店", font=font, fill="black")
        draw.text((470, 180), "-38.50", font=ImageFont.truetype(CJK_FONT, 80), fill="black")
        rows = [("当前状态", "支付成功"), ("支付时间", "2026年07月12日 10:20:30"),
                ("支付方式", "零钱"), ("交易单号", "4200002345202607121234567890")]
        for index, (label, value) in enumerate(rows):
            draw.text((80, 400 + index * 120), label, font=font, fill=(120, 120, 120))
            draw.text((380, 400 + index * 120), value, font=font, fill="black")
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "bill.png"
            image.save(path)
            with patch.dict(os.environ, {"CFO_OCR_PROVIDER": "rapidocr"}):
                parsed = parse_bill_text(ocr_providers.ocr_image(str(path)), source_hint="wechat")

        self.assertEqual(parsed.amount, 38.5)
        self.assertEqual(parsed.paid_at, "2026-07-12T10:20:30")
        self.assertEqual(parsed.transaction_id, "4200002345202607121234567890")
        self.assertEqual(parsed.payment_method, "零钱")


class FormatGuardTests(unittest.TestCase):
    def test_rejects_heic_with_actionable_message(self) -> None:
        with self.assertRaises(OCRError) as ctx:
            _check_supported_format("/tmp/mail_1_1.heic")

        self.assertIn("HEIC", str(ctx.exception))

    def test_allows_screenshot_formats(self) -> None:
        for name in ["a.png", "b.JPG", "c.jpeg", "d.webp"]:
            _check_supported_format(f"/tmp/{name}")


if __name__ == "__main__":
    unittest.main()
