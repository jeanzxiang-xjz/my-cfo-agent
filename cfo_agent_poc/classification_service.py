from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
import urllib.request
from pathlib import Path
from typing import Callable

try:
    from cfo_agent_poc.bill_classifier import FIXED_TAXONOMY, INDUSTRY_CATEGORY_RULES, LOCAL_CATEGORY_RULES
    from cfo_agent_poc.bill_store import (
        ensure_bill_tables,
        is_masked_merchant,
        is_platform_entity,
        remember_merchant_classification,
    )
    from cfo_agent_poc.category_catalog import ensure_category_tables, model_taxonomy
except ModuleNotFoundError:  # Supports direct execution from cfo_agent_poc.
    from bill_classifier import FIXED_TAXONOMY, INDUSTRY_CATEGORY_RULES, LOCAL_CATEGORY_RULES
    from bill_store import ensure_bill_tables, is_masked_merchant, is_platform_entity, remember_merchant_classification
    from category_catalog import ensure_category_tables, model_taxonomy


# ocr_excerpt 是已经脱敏过的截图文字（见 redact_ocr），只在本地解析没把握时才带上。
ALLOWED_INPUT_FIELDS = ("merchant", "product", "platform", "payment_app", "ocr_excerpt")
# 分类标签式的 thing（饭、超市便利…）。模型给了更具体的内容时可以替换掉它们。
GENERIC_THINGS = (
    set(FIXED_TAXONOMY.values())
    | {thing for _, thing, _ in LOCAL_CATEGORY_RULES}
    | {thing for _, thing, _ in INDUSTRY_CATEGORY_RULES}
)
OCR_EXCERPT_LIMIT = 600
HISTORY_EXAMPLE_LIMIT = 5
MODEL_CATEGORIES = tuple(category for category in FIXED_TAXONOMY if category != "uncategorized")
_WORKER_LOCK = threading.Lock()

# 分类状态机的三个阈值。
#
# 关键约束：pending 必须是**过渡态**，不能是归宿。之前只有一条 >=0.75 的硬线，
# 低于线就 `continue`——既不写库也不计数，那一行就永远停在「识别中」。
# 现在分三段落地，且每跑一轮都记一次 attempts，到上限强制结案。
ACCEPT_CONFIDENCE = 0.75   # 直接采信
LOW_CONFIDENCE_FLOOR = 0.45  # 采信但标记存疑，交给「待核实」复核
MAX_ATTEMPTS = 3           # 试满就落「未分类」，终态


def redact_ocr(raw_text: str | None, limit: int = OCR_EXCERPT_LIMIT) -> str | None:
    """
    把截图 OCR 文字脱敏后截短，给模型看版面上下文（店招、菜品、小票）。
    订单号/交易号这类长串、手机号、邮箱、卡号尾号一律替换成 #；状态栏的时间电量丢掉。
    """
    if not raw_text:
        return None
    kept: list[str] = []
    for line in raw_text.splitlines():
        line = line.strip()
        if not line or re.fullmatch(r"[\d:：.%$令<>\s]{1,6}|\d{1,2}:\d{2}\S{0,2}", line):
            continue
        line = re.sub(r"[\w.+-]+@[\w-]+\.[\w.]+", "#", line)
        line = re.sub(r"(?<!\d)1[3-9]\d{9}(?!\d)", "#", line)
        line = re.sub(r"[（(]\s*\d{4}\s*[)）]", "(#)", line)
        # 含 6 位以上数字的长串基本都是单号、流水号、户号
        line = re.sub(r"[A-Za-z0-9_-]*\d[A-Za-z0-9_-]*", lambda m: "#" if sum(c.isdigit() for c in m.group()) >= 6 else m.group(), line)
        kept.append(line)
    excerpt = " | ".join(kept)
    return excerpt[:limit] or None


def history_examples(conn: sqlite3.Connection, limit: int = HISTORY_EXAMPLE_LIMIT) -> list[dict]:
    """用户最近人工校正过商户/消费内容的几笔，作为 few-shot，让模型学这个人的叫法。"""
    rows = conn.execute(
        """
        select t.merchant, t.product, t.thing, t.category
        from transactions t
        where t.raw_capture_hash in (
            select raw_capture_hash from transaction_overrides where field in ('merchant', 'thing')
        )
        and t.merchant is not null and t.thing is not null
        order by coalesce(t.reviewed_at, t.created_at) desc
        limit ?
        """,
        (limit,),
    ).fetchall()
    return [
        {"merchant": row[0], "product": redact_ocr(row[1], 80), "thing": row[2], "category": row[3]}
        for row in rows
    ]


def build_deepseek_request(
    items: list[dict],
    *,
    model: str,
    taxonomy: dict[str, str] | None = None,
    examples: list[dict] | None = None,
) -> dict:
    safe_items = [
        {
            "item_id": index,
            **{field: item.get(field) for field in ALLOWED_INPUT_FIELDS if item.get(field) is not None},
        }
        for index, item in enumerate(items)
    ]
    resolved_taxonomy = taxonomy or {key: FIXED_TAXONOMY[key] for key in MODEL_CATEGORIES}
    system_prompt = (
        "你是私人账本的消费分类和信息抽取器。根据给定商户、商品、平台、支付应用，以及可能附带的"
        "脱敏截图文字 ocr_excerpt（# 是被隐去的号码），给出分类、真实商户和消费内容；"
        "不得推断或修改金额、时间、交易号等事实。"
        "merchant 填真正卖东西的店名或品牌（如「粉大厨」「吉野家」），不要填北京三快、美团平台商户、"
        "财付通这类平台或收单公司，也不要带分店括号；看不出来就填 null。"
        "thing 填具体买了什么（如「米粉」「鲜花」「ChatGPT会员」），不超过 12 个字；"
        "截图里没有商品信息时，给一个简短概括（如「饭」「咖啡」）。"
        "examples 是这个用户以前亲手校正过的记录，照着他们的叫法来。必须返回 JSON 对象，格式为 "
        '{"results":[{"item_id":0,"category":"类别ID","merchant":"店名或null","thing":"简短中文消费内容",'
        '"confidence":0.0,"reason":"简短理由"}]}。category 必须来自给定分类表。'
    )
    user_payload: dict = {"taxonomy": resolved_taxonomy, "items": safe_items}
    if examples:
        user_payload["examples"] = examples
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
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


def parse_deepseek_response(
    response: dict, *, item_count: int, taxonomy: dict[str, str] | None = None
) -> list[dict]:
    resolved_taxonomy = taxonomy or {key: FIXED_TAXONOMY[key] for key in MODEL_CATEGORIES}
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
        if category not in resolved_taxonomy or not 0 <= confidence <= 1:
            continue
        thing = str(item.get("thing") or resolved_taxonomy[category]).strip()[:40]
        reason = str(item.get("reason") or "DeepSeek 分类").strip()[:80]
        merchant = str(item.get("merchant") or "").strip()[:40]
        if merchant.lower() in {"null", "none", "未知"} or is_platform_entity(merchant) or is_masked_merchant(merchant):
            merchant = ""
        results.append({
            "item_id": item_id,
            "category": category,
            "merchant": merchant or None,
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
    taxonomy: dict[str, str] | None = None,
    examples: list[dict] | None = None,
) -> list[dict]:
    body = json.dumps(
        build_deepseek_request(items, model=model, taxonomy=taxonomy, examples=examples), ensure_ascii=False
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return parse_deepseek_response(payload, item_count=len(items), taxonomy=taxonomy)


def settle_transactions(conn: sqlite3.Connection, uids: list[str], *, reason: str) -> int:
    """
    把这些 pending 行就地落成「未分类」终态。
    分类没结论是可以接受的，一直显示「识别中」不行——前者是个结论，后者是个卡死。
    """
    if not uids:
        return 0
    cursor = conn.executemany(
        """
        update transactions
        set category = case when category is null or category = '' then 'uncategorized' else category end,
            classification_status = 'resolved',
            classification_source = case when classification_source = 'none' then 'unresolved' else classification_source end,
            classification_reason = ?
        where transaction_uid = ? and classification_status = 'pending'
        """,
        [(reason, uid) for uid in uids],
    )
    return cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else len(uids)


def settle_exhausted_transactions(conn: sqlite3.Connection, *, max_attempts: int = MAX_ATTEMPTS) -> int:
    """兜底清扫：试满 max_attempts 还没结论的行一律结案。"""
    uids = [
        row[0]
        for row in conn.execute(
            "select transaction_uid from transactions "
            "where classification_status = 'pending' and classification_attempts >= ?",
            (max_attempts,),
        )
    ]
    if not uids:
        return 0
    return settle_transactions(conn, uids, reason=f"exhausted:{max_attempts}_attempts")


def settle_stuck_transactions(db_path: str | Path, *, max_attempts: int = MAX_ATTEMPTS) -> int:
    """可独立调用的清扫入口，给启动时和运维脚本用。"""
    conn = sqlite3.connect(Path(db_path))
    conn.row_factory = sqlite3.Row
    ensure_bill_tables(conn)
    ensure_category_tables(conn)
    conn.commit()
    settled = settle_exhausted_transactions(conn, max_attempts=max_attempts)
    conn.commit()
    conn.close()
    return settled


def settle_exhausted_extractions(conn: sqlite3.Connection, *, max_attempts: int = MAX_ATTEMPTS) -> int:
    """补抽商户同样不能无限排队：试满次数就放弃，保留本地解析结果。"""
    cursor = conn.execute(
        "update transactions set extraction_status = 'failed' "
        "where extraction_status = 'pending' and extraction_attempts >= ?",
        (max_attempts,),
    )
    return max(cursor.rowcount or 0, 0)


def _overridden_fields(conn: sqlite3.Connection, transaction_uid: str) -> set[str]:
    rows = conn.execute(
        "select field from transaction_overrides where raw_capture_hash = "
        "(select raw_capture_hash from transactions where transaction_uid = ?)",
        (transaction_uid,),
    ).fetchall()
    return {row[0] for row in rows}


def _result_updates(row: sqlite3.Row, result: dict, overridden: set[str]) -> tuple[dict, bool, bool]:
    """
    把一条模型结果换算成要写回的列。返回 (updates, 是否完成分类, 是否高置信)。
    人工校正过的字段一律不碰；商户只在本地解析质量差时才换。
    """
    confidence = float(result.get("confidence", 0))
    updates: dict[str, object] = {}
    if row["extraction_status"] == "pending":
        updates["extraction_status"] = "done"
    if confidence < LOW_CONFIDENCE_FLOOR:
        # 模型自己都没把握到这个程度，不如留给下一轮/兜底，别写进账本
        return updates, False, False

    if result.get("merchant") and row["merchant_quality"] != "ok" and "merchant" not in overridden:
        updates.update({"merchant": result["merchant"], "merchant_quality": "ok"})

    confident = confidence >= ACCEPT_CONFIDENCE
    classified = False
    if row["classification_status"] == "pending":
        if "category" not in overridden:
            # 0.45~0.75 之间照样采信：给个能用的分类，同时打上存疑标记，
            # 好过把答案丢掉、让这一行永远停在「识别中」。
            updates.update({
                "category": result["category"],
                "classification_source": "deepseek" if confident else "deepseek_low",
                "classification_confidence": confidence,
                "classification_status": "resolved",
                "classification_reason": result["reason"] if confident else f"low_confidence:{result['reason']}",
            })
            if "thing" not in overridden:
                updates["thing"] = result["thing"]
            classified = True
    elif (
        "thing" not in overridden
        and "category" not in overridden
        and result.get("thing")
        and (not row["thing"] or (row["thing"] in GENERIC_THINGS and result["thing"] not in GENERIC_THINGS))
    ):
        # 分类早已确定，只是消费内容还停在「饭」「超市便利」这类标签上
        updates["thing"] = result["thing"]
    return updates, classified, confident


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
    ensure_category_tables(conn)
    conn.commit()
    active_taxonomy = model_taxonomy(db_path)
    # 每轮开头先收尸：把试满次数还没结论的行落成终态，
    # 这样即使 worker 中途崩了，界面也不会一直停在「识别中」。
    swept = settle_exhausted_transactions(conn)
    settle_exhausted_extractions(conn)
    # 分类没结论的优先；同档按尝试次数升序取，保证积压时老行也能轮到。
    rows = conn.execute(
        """
        select transaction_uid, merchant, product, platform, payment_app, raw_text, thing,
               merchant_quality, classification_status, extraction_status
        from transactions
        where classification_status = 'pending' or extraction_status = 'pending'
        order by classification_status = 'pending' desc,
                 classification_attempts + extraction_attempts asc, paid_at desc, created_at desc
        limit ?
        """,
        (max(1, min(limit, 50)),),
    ).fetchall()
    if not rows:
        conn.commit()
        conn.close()
        return {"selected": 0, "resolved": 0, "pending": 0, "settled": swept}

    # 先把这一轮的尝试次数记上。后面无论成功、失败还是模型压根没返回这一条，
    # 计数都已经落库了——这是「不会无限 pending」的根本保证。
    conn.executemany(
        """
        update transactions
        set classification_attempts = classification_attempts + (classification_status = 'pending'),
            extraction_attempts = extraction_attempts + (extraction_status = 'pending')
        where transaction_uid = ?
        """,
        [(row["transaction_uid"],) for row in rows],
    )
    conn.commit()
    classify_uids = [row["transaction_uid"] for row in rows if row["classification_status"] == "pending"]

    # 进到这里的都是本地解析没把握的行，按用户授权附上脱敏后的截图文字
    safe_items = [
        {
            **{field: row[field] for field in ("merchant", "product", "platform", "payment_app")},
            "ocr_excerpt": redact_ocr(row["raw_text"]),
        }
        for row in rows
    ]
    if classifier is None:
        resolved_api_key = api_key or os.environ.get("DEEPSEEK_API_KEY", "")
        if not resolved_api_key:
            # 没配 key 就永远等不到模型，直接结案，别让界面挂着「识别中」。
            settled = settle_transactions(conn, classify_uids, reason="no_classifier:missing_api_key")
            conn.commit()
            conn.close()
            return {
                "selected": len(rows),
                "resolved": 0,
                "pending": 0,
                "settled": swept + settled,
                "error": "missing_api_key",
            }
        examples = history_examples(conn)

        def classifier(items: list[dict]) -> list[dict]:
            return request_deepseek_classifications(
                items,
                api_key=resolved_api_key,
                base_url=base_url or os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
                model=model or os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash"),
                timeout=timeout or float(os.environ.get("CFO_CLASSIFICATION_TIMEOUT_SECONDS", "12")),
                taxonomy=active_taxonomy,
                examples=examples,
            )

    try:
        classifications = classifier(safe_items)
    except Exception as exc:
        # 记下失败原因；试满次数的行顺手结案，其余留到下一轮重试。
        conn.executemany(
            "update transactions set classification_reason = ? where transaction_uid = ? and classification_status = 'pending'",
            [(f"deepseek_error:{type(exc).__name__}", uid) for uid in classify_uids],
        )
        settled = settle_exhausted_transactions(conn)
        settle_exhausted_extractions(conn)
        conn.commit()
        conn.close()
        return {
            "selected": len(rows),
            "resolved": 0,
            "pending": len(classify_uids) - settled,
            "settled": swept + settled,
            "error": type(exc).__name__,
        }

    resolved = extracted = 0
    for result in classifications:
        if result.get("category") not in active_taxonomy:
            continue
        item_id = result["item_id"]
        if not isinstance(item_id, int) or not 0 <= item_id < len(rows):
            continue
        row = rows[item_id]
        updates, classified, confident = _result_updates(row, result, _overridden_fields(conn, row["transaction_uid"]))
        if not updates:
            continue
        columns = ", ".join(f"{name} = ?" for name in updates)
        conn.execute(
            f"update transactions set {columns} where transaction_uid = ?",
            (*updates.values(), row["transaction_uid"]),
        )
        resolved += classified
        extracted += "merchant" in updates or "thing" in updates
        # 只有高置信的分类结论才值得沉淀成商户记忆，存疑的不污染记忆表
        if classified and confident:
            remember_merchant_classification(
                conn,
                merchant=updates.get("merchant", row["merchant"]),
                category=result["category"],
                thing=result["thing"],
                confidence=float(result["confidence"]),
                source="deepseek",
            )

    # 这一轮仍没结论、且已经试满的，就地落成「未分类」终态
    settled = settle_exhausted_transactions(conn)
    settle_exhausted_extractions(conn)
    conn.commit()
    conn.close()
    return {
        "selected": len(rows),
        "resolved": resolved,
        "extracted": extracted,
        "pending": max(0, len(classify_uids) - resolved - settled),
        "settled": swept + settled,
    }


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
