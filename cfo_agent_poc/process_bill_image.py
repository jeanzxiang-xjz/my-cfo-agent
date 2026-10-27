from __future__ import annotations

import argparse
from pathlib import Path

from bill_store import DATA_DIR, parsed_to_json, store_bill_capture
from ocr_providers import ocr_image
from tenancy import Ledger


PROJECT_DIR = Path(__file__).resolve().parent
OCR_TEXT_DIR = DATA_DIR / "ocr_texts"

__all__ = ["ocr_image", "process_image", "main"]


def process_image(
    image_path: str,
    source: str = "email_screenshot",
    source_hint: str | None = None,
    captured_at: str | None = None,
    *,
    ledger: Ledger | None = None,
    evidence_path: str | None = None,
):
    """OCR 一张截图并入库。``ledger`` 省略时写本地单账本（命令行用法）。

    ``evidence_path`` 是长期留底的证据图（截图直传时是转好的 WebP）：OCR 永远读原图
    ``image_path``，库里记的是证据图，原图识别完就可以删。省略时两者是同一张。"""
    ocr_text = ocr_image(image_path)
    text_dir = ledger.ocr_text_dir if ledger is not None else OCR_TEXT_DIR
    text_dir.mkdir(parents=True, exist_ok=True)
    text_path = text_dir / (Path(image_path).stem + ".txt")
    text_path.write_text(ocr_text, encoding="utf-8")
    return store_bill_capture(
        ocr_text,
        source=source,
        source_hint=source_hint,
        image_path=evidence_path or image_path,
        captured_at=captured_at,
        db_path=ledger.db_path if ledger is not None else None,
        root_dir=ledger.root if ledger is not None else None,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="OCR a bill screenshot image and store a transaction.")
    parser.add_argument("image_path")
    parser.add_argument("--source", default="email_screenshot")
    parser.add_argument("--source-hint")
    parser.add_argument("--captured-at")
    parser.add_argument("--ledger-dir", help="账本根目录（含 data/cfo.sqlite），默认是 cfo_agent_poc 本身")
    args = parser.parse_args()

    parsed = process_image(
        args.image_path,
        source=args.source,
        source_hint=args.source_hint,
        captured_at=args.captured_at,
        ledger=Ledger(Path(args.ledger_dir).resolve()) if args.ledger_dir else None,
    )
    print(parsed_to_json(parsed))


if __name__ == "__main__":
    main()
