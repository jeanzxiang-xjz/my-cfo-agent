from __future__ import annotations

"""
拿现有账单回归 RapidOCR：识别正确率 + 耗时。

只读：数据库按只读方式打开，不写任何账本数据。对每笔带截图的交易：

- 标准答案：transactions 表里的最终值（已含人工校正）；
- 基线：入库时保存的 OCR 原文（当时的后端，Mac 上是 Vision）用当前解析器重新解析；
- RapidOCR：现场识别截图，再用同一个解析器解析。

两边都和标准答案比对关键字段，同时记录单张识别耗时、模型冷启动耗时和进程峰值内存。
--threads 限制推理线程数，用来模拟服务器核数（默认 2）。
"""

import argparse
import json
import math
import os
import resource
import sqlite3
import statistics
import sys
import time
from pathlib import Path

try:
    from cfo_agent_poc import ocr_providers
    from cfo_agent_poc.bill_store import normalize_merchant_key, parse_bill_text
except ModuleNotFoundError:  # Supports direct execution from cfo_agent_poc.
    import ocr_providers
    from bill_store import normalize_merchant_key, parse_bill_text


FIELDS = ("amount", "direction", "paid_at", "merchant", "transaction_id", "payment_method", "payment_app")


def _plain(value: object) -> str:
    """全半角括号、空白不算差异：「招商银行信用卡(9063)」和「招商银行信用卡（9063）」是同一个值。"""
    return "".join(str(value or "").replace("（", "(").replace("）", ")").split())


def field_ok(field: str, parsed: object, golden: object) -> bool:
    if field == "amount":
        return parsed is not None and math.isclose(float(parsed), float(golden), abs_tol=0.005)
    if field == "merchant":
        left, right = normalize_merchant_key(parsed), normalize_merchant_key(golden)
        if not left or not right:
            return False
        return left == right or (min(len(left), len(right)) >= 2 and (left in right or right in left))
    return _plain(parsed) == _plain(golden)


def load_samples(ledger_root: Path) -> list[dict]:
    db = ledger_root / "data" / "cfo.sqlite"
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            f"""
            select t.transaction_uid, t.source, {", ".join(f"t.{field}" for field in FIELDS)},
                   c.ocr_text, c.image_path
            from transactions t
            join raw_bill_captures c on c.capture_hash = t.raw_capture_hash
            where c.image_path is not null and c.ocr_text is not null
            """
        ).fetchall()
    finally:
        conn.close()
    samples, seen = [], set()
    for row in rows:
        image = Path(row["image_path"])
        image = image if image.is_absolute() else ledger_root / image
        if not image.is_file() or image in seen:
            continue
        seen.add(image)
        samples.append({**dict(row), "image": image, "ledger": ledger_root.name})
    return samples


def _peak_rss_mb() -> float:
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak / 1024 / 1024 if sys.platform == "darwin" else peak / 1024


def evaluate(samples: list[dict]) -> dict:
    started = time.perf_counter()
    ocr_providers.warm_up()
    cold_start = time.perf_counter() - started

    totals = {name: {field: [0, 0] for field in FIELDS} for name in ("baseline", "rapidocr")}
    all_ok = {"baseline": 0, "rapidocr": 0}
    timings: list[dict] = []
    misses: list[dict] = []
    for index, sample in enumerate(samples, 1):
        from PIL import Image

        with Image.open(sample["image"]) as image:
            size = image.size
        tick = time.perf_counter()
        text = ocr_providers._ocr_rapidocr(str(sample["image"]))
        elapsed = time.perf_counter() - tick
        timings.append({"size": size, "seconds": elapsed})

        hint = sample["payment_app"] or sample["source"]
        parsed = {
            "baseline": parse_bill_text(sample["ocr_text"], source=sample["source"], source_hint=hint),
            "rapidocr": parse_bill_text(text, source=sample["source"], source_hint=hint),
        }
        row_miss = {}
        for name, bill in parsed.items():
            ok_all = True
            for field in FIELDS:
                golden = sample[field]
                if golden in (None, ""):
                    continue
                ok = field_ok(field, getattr(bill, field, None), golden)
                totals[name][field][0] += ok
                totals[name][field][1] += 1
                ok_all &= ok
                if not ok:
                    row_miss.setdefault(field, {"golden": golden})[name] = getattr(bill, field, None)
            all_ok[name] += ok_all
        if row_miss:
            misses.append({"image": str(sample["image"]), "size": size, "fields": row_miss, "rapidocr_text": text})
        print(f"{index}/{len(samples)} {sample['image'].name} {size[0]}×{size[1]} {elapsed:.2f}s {list(row_miss) or ''}", flush=True)

    seconds = sorted(item["seconds"] for item in timings)
    by_width: dict[str, list[float]] = {}
    for item in timings:
        by_width.setdefault(f"{item['size'][0]}×{item['size'][1]}", []).append(item["seconds"])
    return {
        "samples": len(samples),
        "threads": ocr_providers._rapidocr_threads(),
        "params": ocr_providers.RAPIDOCR_PARAMS,
        "cold_start_seconds": round(cold_start, 2),
        "peak_rss_mb": round(_peak_rss_mb(), 1),
        "latency": {
            "p50": round(statistics.median(seconds), 3),
            "p95": round(seconds[min(len(seconds) - 1, math.ceil(len(seconds) * 0.95) - 1)], 3),
            "max": round(seconds[-1], 3),
            "by_size": {key: round(statistics.median(values), 3) for key, values in by_width.items()},
        },
        "accuracy": {
            name: {field: f"{hit}/{total}" for field, (hit, total) in fields.items()} for name, fields in totals.items()
        },
        "all_fields_ok": {name: f"{count}/{len(samples)}" for name, count in all_ok.items()},
        "misses": misses,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Regress RapidOCR against stored bills (read-only).")
    parser.add_argument("ledgers", nargs="+", help="账本根目录（含 data/cfo.sqlite）")
    parser.add_argument("--threads", type=int, default=2, help="推理线程数，模拟服务器核数")
    parser.add_argument("--param", action="append", default=[], help="临时覆盖 RapidOCR 参数，如 Global.max_side_len=1600")
    parser.add_argument("--out", help="完整结果（含逐条差异）写到这个 JSON 文件")
    args = parser.parse_args()

    os.environ["CFO_OCR_PROVIDER"] = "rapidocr"
    os.environ["CFO_OCR_THREADS"] = str(args.threads)
    for item in args.param:
        key, _, raw = item.partition("=")
        try:
            value = json.loads(raw)
        except ValueError:
            value = raw
        ocr_providers.RAPIDOCR_PARAMS[key] = value

    samples = [sample for root in args.ledgers for sample in load_samples(Path(root).resolve())]
    report = evaluate(samples)
    if args.out:
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    summary = {key: value for key, value in report.items() if key != "misses"}
    summary["rows_with_misses"] = len(report["misses"])
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
