from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from bill_store import DATA_DIR, parsed_to_json, store_bill_capture


PROJECT_DIR = Path(__file__).resolve().parent
OCR_SCRIPT = PROJECT_DIR / "ocr_image.swift"
OCR_TEXT_DIR = DATA_DIR / "ocr_texts"


def ocr_image(image_path: str) -> str:
    result = subprocess.run(
        ["swift", str(OCR_SCRIPT), image_path],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def process_image(
    image_path: str,
    source: str = "email_screenshot",
    source_hint: str | None = None,
    captured_at: str | None = None,
):
    ocr_text = ocr_image(image_path)
    OCR_TEXT_DIR.mkdir(parents=True, exist_ok=True)
    text_path = OCR_TEXT_DIR / (Path(image_path).stem + ".txt")
    text_path.write_text(ocr_text, encoding="utf-8")
    return store_bill_capture(
        ocr_text,
        source=source,
        source_hint=source_hint,
        image_path=image_path,
        captured_at=captured_at,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="OCR a bill screenshot image and store a transaction.")
    parser.add_argument("image_path")
    parser.add_argument("--source", default="email_screenshot")
    parser.add_argument("--source-hint")
    parser.add_argument("--captured-at")
    args = parser.parse_args()

    parsed = process_image(
        args.image_path,
        source=args.source,
        source_hint=args.source_hint,
        captured_at=args.captured_at,
    )
    print(parsed_to_json(parsed))


if __name__ == "__main__":
    main()

