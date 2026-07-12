from __future__ import annotations

import json
import os
import sqlite3
import threading
import urllib.request
from pathlib import Path
from typing import Callable

try:
    from cfo_agent_poc.bill_classifier import FIXED_TAXONOMY
    from cfo_agent_poc.bill_store import ensure_bill_tables, remember_merchant_classification
except ModuleNotFoundError:  # Supports direct execution from cfo_agent_poc.
    from bill_classifier import FIXED_TAXONOMY
    from bill_store import ensure_bill_tables, remember_merchant_classification


ALLOWED_INPUT_FIELDS = ("merchant", "product", "platform", "payment_app")
MODEL_CATEGORIES = tuple(category for category in FIXED_TAXONOMY if category != "uncategorized")
_WORKER_LOCK = threading.Lock()


def build_deepseek_request(items: list[dict], *, model: str) -> dict:
    safe_items = [
        {
            "item_id": index,
            **{field: item.get(field) for field in ALLOWED_INPUT_FIELDS},
        }
        for index, item in enumerate(items)
    ]
    taxonomy = {key: FIXED_TAXONOMY[key] for key in MODEL_CATEGORIES}
    system_prompt = (
        "你是私人账本的消费分类器。只能根据给定商户、商品、平台和支付应用分类；"
        "不得推断或修改金额、时间、交易号等事实。必须返回 JSON 对象，格式为 "
        '{"results":[{"item_id":0,"category":"类别ID","thing":"简短中文消费内容",'
        '"confidence":0.0,"reason":"简短理由"}]}。category 必须来自给定分类表。'
    )
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": json.dumps({"taxonomy": taxonomy, "items": safe_items}, ensure_ascii=False),
            },
        ],
        "temperature": 0,
        "stream": False,
    }


def _json_content(value: str) -> dict:
    content = value.strip()
    if content.startswith("```"):
        lines = content.splitlines()
        content = "\n".join(lines[1:-1]) if len(lines) >= 3 else content
    parsed = json.loads(content)
    if not isinstance(parsed, dict):
        raise ValueError("classification response is not an object")
    return parsed


def parse_deepseek_response(response: dict, *, item_count: int) -> list[dict]:
    try:
        content = response["choices"][0]["message"]["content"]
        payload = _json_content(content)
    except (KeyError, IndexError, TypeError, json.JSONDecodeError, ValueError):
        return []

    results: list[dict] = []
    seen_ids: set[int] = set()
    for item in payload.get("results", []):
        if not isinstance(item, dict):
            continue
        item_id = item.get("item_id")
        category = item.get("category")
        try:
            confidence = float(item.get("confidence", 0))
        except (TypeError, ValueError):
            continue
        if not isinstance(item_id, int) or item_id in seen_ids or not 0 <= item_id < item_count:
            continue
        if category not in MODEL_CATEGORIES or not 0 <= confidence <= 1:
            continue
        thing = str(item.get("thing") or FIXED_TAXONOMY[category]).strip()[:40]
        reason = str(item.get("reason") or "DeepSeek 分类").strip()[:80]
        results.append({
            "item_id": item_id,
            "category": category,
            "thing": thing,
            "confidence": confidence,
            "reason": reason,
        })
        seen_ids.add(item_id)
    return results


def request_deepseek_classifications(
    items: list[dict],
    *,
    api_key: str,
    base_url: str,
    model: str,
    timeout: float,
) -> list[dict]:
    body = json.dumps(build_deepseek_request(items, model=model), ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return parse_deepseek_response(payload, item_count=len(items))


def enrich_pending_transactions(
    db_path: str | Path,
    *,
    classifier: Callable[[list[dict]], list[dict]] | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
    timeout: float | None = None,
    limit: int = 10,
) -> dict:
    conn = sqlite3.connect(Path(db_path))
    conn.row_factory = sqlite3.Row
    ensure_bill_tables(conn)
    rows = conn.execute(
        """
        select transaction_uid, merchant, product, platform, payment_app
        from transactions
        where classification_status = 'pending'
        order by paid_at desc, created_at desc
        limit ?
        """,
        (max(1, min(limit, 10)),),
    ).fetchall()
    if not rows:
        conn.close()
        return {"selected": 0, "resolved": 0, "pending": 0}

    safe_items = [{field: row[field] for field in ALLOWED_INPUT_FIELDS} for row in rows]
    if classifier is None:
        resolved_api_key = api_key or os.environ.get("DEEPSEEK_API_KEY", "")
        if not resolved_api_key:
            conn.close()
            return {"selected": len(rows), "resolved": 0, "pending": len(rows), "error": "missing_api_key"}

        def classifier(items: list[dict]) -> list[dict]:
            return request_deepseek_classifications(
                items,
                api_key=resolved_api_key,
                base_url=base_url or os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
                model=model or os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash"),
                timeout=timeout or float(os.environ.get("CFO_CLASSIFICATION_TIMEOUT_SECONDS", "12")),
            )

    try:
        classifications = classifier(safe_items)
    except Exception as exc:
        conn.executemany(
            "update transactions set classification_reason = ? where transaction_uid = ? and classification_status = 'pending'",
            [(f"deepseek_error:{type(exc).__name__}", row["transaction_uid"]) for row in rows],
        )
        conn.commit()
        conn.close()
        return {"selected": len(rows), "resolved": 0, "pending": len(rows), "error": type(exc).__name__}

    resolved = 0
    for result in classifications:
        if float(result.get("confidence", 0)) < 0.75:
            continue
        item_id = result["item_id"]
        if not isinstance(item_id, int) or not 0 <= item_id < len(rows):
            continue
        row = rows[item_id]
        has_override = conn.execute(
            "select 1 from transaction_overrides where raw_capture_hash = "
            "(select raw_capture_hash from transactions where transaction_uid = ?) and field = 'category'",
            (row["transaction_uid"],),
        ).fetchone()
        if has_override:
            continue
        cursor = conn.execute(
            """
            update transactions
            set category = ?, thing = ?, classification_source = 'deepseek',
                classification_confidence = ?, classification_status = 'resolved', classification_reason = ?
            where transaction_uid = ? and classification_status = 'pending'
            """,
            (
                result["category"],
                result["thing"],
                result["confidence"],
                result["reason"],
                row["transaction_uid"],
            ),
        )
        if cursor.rowcount:
            resolved += 1
            remember_merchant_classification(
                conn,
                merchant=row["merchant"],
                category=result["category"],
                thing=result["thing"],
                confidence=result["confidence"],
                source="deepseek",
            )
    conn.commit()
    conn.close()
    return {"selected": len(rows), "resolved": resolved, "pending": len(rows) - resolved}


def start_background_enrichment(db_path: str | Path, **kwargs) -> bool:
    if not (kwargs.get("api_key") or os.environ.get("DEEPSEEK_API_KEY")):
        return False
    if not _WORKER_LOCK.acquire(blocking=False):
        return False

    def run() -> None:
        try:
            enrich_pending_transactions(db_path, **kwargs)
        finally:
            _WORKER_LOCK.release()

    threading.Thread(target=run, name="cfo-classification", daemon=True).start()
    return True
