from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sqlite3
import unicodedata
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from cfo_agent_poc.bill_classifier import (
        ClassificationResult,
        LOCAL_CATEGORY_RULES,
        classify_locally,
        detect_category_and_thing,
    )
    from cfo_agent_poc.category_catalog import ensure_category_tables, is_enabled_category
except ModuleNotFoundError:  # Supports direct execution as cfo_agent_poc/bill_store.py.
    from bill_classifier import ClassificationResult, LOCAL_CATEGORY_RULES, classify_locally, detect_category_and_thing
    from category_catalog import ensure_category_tables, is_enabled_category


PROJECT_DIR = Path(__file__).resolve().parent
DATA_DIR = PROJECT_DIR / "data"
APP_DB = DATA_DIR / "cfo.sqlite"


def portable_image_path(image_path: str | Path | None) -> str | None:
    """Return a project-relative image reference for database persistence.

    Images already inside ``cfo_agent_poc`` are stored relative to that
    directory (for example ``data/mail_attachments/mail_123_1.png``), so the
    reference survives moving the whole project.  An image supplied from
    elsewhere is copied into ``data/evidence`` before its relative reference
    is returned.  Missing relative paths are kept as-is so old records can be
    repaired later without reintroducing an absolute machine path.
    """
    raw = str(image_path or "").strip()
    if not raw:
        return None

    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        normalized = candidate.as_posix()
        return normalized[2:] if normalized.startswith("./") else normalized

    project_root = PROJECT_DIR.resolve()
    resolved = candidate.resolve(strict=False)
    try:
        return resolved.relative_to(project_root).as_posix()
    except ValueError:
        pass

    # A manual import may point at Downloads or another temporary folder. Keep
    # the bill usable by copying the image into the project's evidence store.
    if not resolved.is_file():
        return None
    evidence_dir = DATA_DIR / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    suffix = resolved.suffix.lower() or ".png"
    digest = hashlib.sha256(resolved.read_bytes()).hexdigest()[:24]
    destination = evidence_dir / f"capture_{digest}{suffix}"
    if not destination.exists():
        shutil.copy2(resolved, destination)
    return destination.resolve().relative_to(project_root).as_posix()


FIELD_LABELS = [
    "当前状态",
    "支付时间",
    "付款方式",
    "商品",
    "商品说明",
    "支付奖励",
    "商户全称",
    "收单机构",
    "清算机构",
    "收款方全称",
    "支付方式",
    "订单号",
    "交易单号",
    "商家订单号",
    "商户单号",
    "经营单号",
    "商家小程序",
    "账单分类",
    "标签",
    "账单服务",
    "交易服务",
]


PLATFORM_HINTS = ["美团", "京东", "淘宝", "天猫", "拼多多", "饿了么", "抖音", "小红书"]
CATEGORY_RULES = [(category, thing, list(hints)) for category, thing, hints in LOCAL_CATEGORY_RULES]


@dataclass
class ParsedBill:
    transaction_uid: str
    source: str
    payment_app: str | None
    amount: float | None
    direction: str
    status: str | None
    paid_at: str | None
    merchant: str | None
    platform: str | None
    thing: str | None
    category: str
    category_confidence: float
    classification_source: str
    classification_status: str
    classification_reason: str | None
    product: str | None
    payment_method: str | None
    bank_name: str | None
    card_type: str | None
    card_last4: str | None
    acquirer: str | None
    clearing_org: str | None
    transaction_id: str | None
    merchant_order_id: str | None
    confidence: float
    raw_text: str
    parse_warnings: list[str]
    # 工商登记名（商户全称/收款方全称）。展示用的 merchant 可能是店招名，
    # 法人名单独留着，给商户记忆和别名匹配兜底。
    merchant_legal: str | None = None
    # ok / platform（平台主体，如北京三快）/ masked（支付宝打码）/ missing
    merchant_quality: str = "ok"
    # 从截图里抽到的具体商品，有它时 thing 优先用它而不是分类标签
    items: str | None = None


# 可以被人工校正、并且在重新解析时原样回放的字段。
# thing / category 不在这里：它们和商户记忆有优先级关系，单独处理。
OVERRIDABLE_TEXT_FIELDS = (
    "merchant",
    "product",
    "paid_at",
    "payment_app",
    "payment_method",
    "card_last4",
)


def ensure_bill_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        create table if not exists raw_bill_captures (
            capture_hash text primary key,
            source text not null,
            ocr_text text not null,
            image_path text,
            captured_at text,
            created_at text not null
        )
        """
    )
    conn.execute(
        """
        create table if not exists transactions (
            transaction_uid text primary key,
            source text not null,
            payment_app text,
            amount real,
            direction text not null,
            status text,
            paid_at text,
            merchant text,
            platform text,
            thing text,
            category text not null,
            product text,
            payment_method text,
            bank_name text,
            card_type text,
            card_last4 text,
            acquirer text,
            clearing_org text,
            transaction_id text,
            merchant_order_id text,
            confidence real not null,
            raw_capture_hash text,
            raw_text text not null,
            created_at text not null,
            classification_source text not null default 'legacy',
            classification_confidence real not null default 0,
            classification_status text not null default 'resolved',
            classification_reason text,
            parse_warnings text not null default '[]'
        )
        """
    )
    ensure_columns(
        conn,
        "transactions",
        {
            "bank_name": "text",
            "card_type": "text",
            "card_last4": "text",
            "clearing_org": "text",
            "classification_source": "text not null default 'legacy'",
            "classification_confidence": "real not null default 0",
            "classification_status": "text not null default 'resolved'",
            "classification_reason": "text",
            # 试过几次。到上限还没结论就落成「未分类」，不能永远挂在 pending。
            "classification_attempts": "integer not null default 0",
            "parse_warnings": "text not null default '[]'",
            # 人工在证据面板核对过的时间。解析置信低不代表解析错了，
            # 人看过截图确认后就不该再出现在「待核实」里。
            "reviewed_at": "text",
            "merchant_legal": "text",
            "merchant_quality": "text not null default 'ok'",
            # 本地解析商户质量差时置 pending，由后台模型结合脱敏截图补商户和消费内容
            "extraction_status": "text not null default 'done'",
            "extraction_attempts": "integer not null default 0",
        },
    )
    conn.execute(
        """
        create table if not exists merchant_category_memory (
            merchant_key text primary key,
            merchant text not null,
            category text not null,
            thing text,
            confidence real not null,
            source text not null,
            updated_at text not null
        )
        """
    )
    conn.execute(
        """
        create table if not exists transaction_overrides (
            raw_capture_hash text not null,
            field text not null,
            value text,
            created_at text not null,
            primary key (raw_capture_hash, field)
        )
        """
    )
    conn.execute(
        """
        create table if not exists merchant_alias (
            alias_key text primary key,
            alias text not null,
            merchant text not null,
            updated_at text not null
        )
        """
    )
    conn.execute(
        """
        update transactions
        set classification_source = 'none', classification_status = 'pending'
        where category = 'uncategorized' and classification_source = 'legacy'
        """
    )
    purge_unstable_merchant_memory(conn)
    conn.commit()


def ensure_columns(conn: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
    existing = {row[1] for row in conn.execute(f"pragma table_info({table})")}
    for column, column_type in columns.items():
        if column not in existing:
            try:
                conn.execute(f"alter table {table} add column {column} {column_type}")
            except sqlite3.OperationalError as exc:
                if "duplicate column name" not in str(exc):
                    raise


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(APP_DB)
    ensure_bill_tables(conn)
    ensure_category_tables(conn)
    conn.commit()
    return conn


# 平台主体：它们是收单/撮合方，不是真正卖东西的店。美团单在支付宝里商户全称
# 全是「北京三快在线科技有限公司」，拿它当商户既看不出吃了哪家，又会让商户记忆
# 把所有美团单绑到同一个分类上。
PLATFORM_ENTITY_NAMES = {
    "美团", "美团平台商户", "美团外卖", "大众点评", "饿了么", "财付通", "支付宝", "微信支付",
}
PLATFORM_ENTITY_MARKERS = ("三快在线", "三快科技", "三快小额", "拉扎斯", "钱袋宝")
# 能当商户展示，但一个名字底下什么都卖，不能沉淀成「商户→分类」记忆。
MULTI_CATEGORY_MERCHANTS = {"淘宝闪购", "闪购", "淘宝", "天猫", "京东", "拼多多", "抖音", "抖音商城", "美团闪购"}

UNSTABLE_MERCHANT_MARKERS = (
    "交易详情",
    "账单详情",
    "美团平台商户",
    "扫码二维码付款",
    "扫二维码付款",
    "财付通",
    "支付宝",
    "微信支付",
    "未知商户",
)


def normalize_merchant_key(merchant: str | None) -> str | None:
    if not merchant:
        return None
    normalized = unicodedata.normalize("NFKC", merchant).lower()
    normalized = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", normalized)
    return normalized or None


def is_platform_entity(merchant: str | None) -> bool:
    key = normalize_merchant_key(merchant)
    if not key:
        return False
    return key in PLATFORM_ENTITY_NAMES or any(marker in key for marker in PLATFORM_ENTITY_MARKERS)


def is_masked_merchant(merchant: str | None) -> bool:
    return "*" in (merchant or "")


def is_stable_merchant(merchant: str | None) -> bool:
    key = normalize_merchant_key(merchant)
    if not key or len(key) < 3:
        return False
    if is_platform_entity(merchant) or is_masked_merchant(merchant) or key in MULTI_CATEGORY_MERCHANTS:
        return False
    compact = compact_text(merchant or "")
    return not any(marker in compact for marker in UNSTABLE_MERCHANT_MARKERS)


def purge_unstable_merchant_memory(conn: sqlite3.Connection) -> int:
    """清掉早先写进去的平台主体记忆（如 北京三快→按摩SPA），否则所有美团单都会被它带偏。"""
    stale = [
        key
        for key, merchant in conn.execute("select merchant_key, merchant from merchant_category_memory")
        if not is_stable_merchant(merchant)
    ]
    conn.executemany("delete from merchant_category_memory where merchant_key = ?", [(key,) for key in stale])
    return len(stale)


def remember_merchant_alias(conn: sqlite3.Connection, *, alias: str | None, merchant: str | None) -> bool:
    """
    人工把商户 A 改成 B 时记一笔别名：下次同一家店的截图直接用 B。
    平台主体、打码名不记——「美团」底下可能是任何一家店。
    """
    if not merchant or not is_stable_merchant(alias):
        return False
    key = normalize_merchant_key(alias)
    if key == normalize_merchant_key(merchant):
        return False
    conn.execute(
        """
        insert into merchant_alias (alias_key, alias, merchant, updated_at)
        values (?, ?, ?, ?)
        on conflict(alias_key) do update set merchant = excluded.merchant, updated_at = excluded.updated_at
        """,
        (key, alias, merchant, datetime.now().isoformat(timespec="seconds")),
    )
    return True


def lookup_merchant_alias(conn: sqlite3.Connection, *names: str | None) -> str | None:
    for name in names:
        key = normalize_merchant_key(name)
        if not key:
            continue
        row = conn.execute("select merchant from merchant_alias where alias_key = ?", (key,)).fetchone()
        if row:
            return row[0]
    return None


def remember_merchant_classification(
    conn: sqlite3.Connection,
    *,
    merchant: str | None,
    category: str,
    thing: str | None,
    confidence: float,
    source: str,
) -> bool:
    if (
        not is_stable_merchant(merchant)
        or category in {"uncategorized", "personal_transfer"}
        or not is_enabled_category(conn, category)
    ):
        return False
    key = normalize_merchant_key(merchant)
    existing = conn.execute(
        "select category from merchant_category_memory where merchant_key = ?",
        (key,),
    ).fetchone()
    if existing and existing[0] != category:
        return False
    conn.execute(
        """
        insert into merchant_category_memory
        (merchant_key, merchant, category, thing, confidence, source, updated_at)
        values (?, ?, ?, ?, ?, ?, ?)
        on conflict(merchant_key) do update set
            merchant = excluded.merchant,
            thing = coalesce(excluded.thing, merchant_category_memory.thing),
            confidence = max(merchant_category_memory.confidence, excluded.confidence),
            source = excluded.source,
            updated_at = excluded.updated_at
        """,
        (key, merchant, category, thing, confidence, source, datetime.now().isoformat(timespec="seconds")),
    )
    return True


def merchant_memory_result(conn: sqlite3.Connection, merchant: str | None) -> ClassificationResult | None:
    if not is_stable_merchant(merchant):
        return None
    key = normalize_merchant_key(merchant)
    row = conn.execute(
        "select category, thing, confidence from merchant_category_memory where merchant_key = ?",
        (key,),
    ).fetchone()
    if not row:
        return None
    if not is_enabled_category(conn, row[0]):
        return None
    return ClassificationResult(
        category=row[0],
        thing=row[1],
        confidence=float(row[2]),
        source="merchant_memory",
        status="resolved",
        reason=f"merchant_memory:{key}",
    )


def capture_overrides(conn: sqlite3.Connection, raw_capture_hash: str) -> dict[str, str | None]:
    rows = conn.execute(
        "select field, value from transaction_overrides where raw_capture_hash = ?",
        (raw_capture_hash,),
    ).fetchall()
    return {row[0]: row[1] for row in rows}


def apply_capture_overrides(parsed: ParsedBill, overrides: dict[str, str | None]) -> None:
    """把人工校正过的字段盖回解析结果，让重新解析同一张截图不会把改动冲掉。"""
    for field in OVERRIDABLE_TEXT_FIELDS:
        if field in overrides:
            setattr(parsed, field, overrides[field] or None)

    if "amount" in overrides:
        try:
            parsed.amount = round(float(overrides["amount"]), 2)
        except (TypeError, ValueError):
            pass


def apply_persisted_classification(
    conn: sqlite3.Connection,
    parsed: ParsedBill,
    raw_capture_hash: str,
) -> ParsedBill:
    overrides = capture_overrides(conn, raw_capture_hash)
    apply_capture_overrides(parsed, overrides)
    if "merchant" in overrides:
        parsed.merchant_quality = "ok" if parsed.merchant else "missing"
    else:
        alias = lookup_merchant_alias(conn, parsed.merchant, parsed.merchant_legal)
        if alias:
            parsed.merchant = alias
            parsed.merchant_quality = "ok"

    if "category" in overrides:
        parsed.category = overrides["category"] or "uncategorized"
        parsed.thing = overrides.get("thing", parsed.thing)
        parsed.category_confidence = 1.0
        parsed.classification_source = "manual_override"
        parsed.classification_status = "resolved"
        parsed.classification_reason = "capture_override"
        return parsed

    memory = merchant_memory_result(conn, parsed.merchant) or merchant_memory_result(conn, parsed.merchant_legal)
    if memory:
        parsed.category = memory.category
        # 截图里抽到了具体商品就用商品，记忆里的 thing 只是这家店上一次的笼统说法
        parsed.thing = overrides.get("thing", parsed.items or memory.thing)
        parsed.category_confidence = memory.confidence
        parsed.classification_source = memory.source
        parsed.classification_status = memory.status
        parsed.classification_reason = memory.reason
        return parsed

    if "thing" in overrides:
        parsed.thing = overrides["thing"]
    return parsed


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("−", "-").replace("－", "-").replace("—", "-")
    # OCR 后端对标点宽度的判断不一致：Apple Vision 给半角冒号，阿里云在时间里给全角。
    # 不归一的话「2026年07月11日20：30：49」会让支付时间整个抽不出来。
    text = text.replace("：", ":")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def compact_text(text: str) -> str:
    return re.sub(r"\s+", "", text)


def extract_amount(text: str) -> float | None:
    match = re.search(r"(?m)^\s*[-+]\s*(\d+(?:\.\d{1,2})?)\s*$", text)
    if match:
        return float(match.group(1))

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for index, line in enumerate(lines):
        match = re.fullmatch(r"[￥¥]?\s*(\d+\.\d{1,2})\s*(?:元)?", line)
        if not match:
            continue

        before = lines[max(0, index - 4):index]
        after = lines[index + 1:index + 4]
        has_bill_context = any("账单" in item or "详情" in item for item in before)
        has_status_after = any(item in {"交易成功", "支付成功"} for item in after)
        has_payment_label_after = any(item in {"支付时间", "付款方式", "支付方式"} for item in after)
        if has_status_after or (has_bill_context and has_payment_label_after):
            return float(match.group(1))

    compact = compact_text(text)
    match = re.search(r"(?:实付金额|付款金额|支付金额|消费金额|订单金额|金额)[^0-9+-]{0,10}[-+￥¥]?(\d+(?:\.\d{1,2})?)", compact)
    if match:
        return float(match.group(1))

    match = re.search(r"[￥¥]\s*(\d+(?:\.\d{1,2})?)", text)
    if not match:
        return None
    return float(match.group(1))


def extract_paid_at(text: str) -> str | None:
    compact = compact_text(text)
    match = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日(\d{1,2}:\d{2}(?::\d{2})?)", compact)
    if match:
        year, month, day, clock = match.groups()
        if clock.count(":") == 1:
            clock += ":00"
        dt = datetime.strptime(f"{year}-{int(month):02d}-{int(day):02d} {clock}", "%Y-%m-%d %H:%M:%S")
        return dt.isoformat(timespec="seconds")

    match = re.search(r"(\d{4})[-–—](\d{1,2})[-–—](\d{1,2})\s*(\d{1,2}:\d{2}(?::\d{2})?)", text)
    if not match:
        return None
    year, month, day, clock = match.groups()
    if clock.count(":") == 1:
        clock += ":00"
    dt = datetime.strptime(f"{year}-{int(month):02d}-{int(day):02d} {clock}", "%Y-%m-%d %H:%M:%S")
    return dt.isoformat(timespec="seconds")


def extract_status(text: str) -> str | None:
    if "支付成功" in text or "交易成功" in text:
        return "paid"
    if "退款" in text or "已退" in text:
        return "refunded"
    if "交易关闭" in text or "支付失败" in text:
        return "failed"
    return None


# 支付宝详情页字段之间夹着的运营位、按钮文案。它们不是字段标签，
# 以前字段值会一路吞到下一个标签为止，于是商户名后面挂着「更多√ 账单管理
# 你因这笔消费解锁了…贴纸」。碰到这些行就截断。
FIELD_NOISE_LINE = re.compile(
    r"^(?:更多|账单管理|推荐服务|推荐.{0,1}务|为.{0,1}推荐|你因这笔消费|已解锁|你有\d+张|去领取|进入小程序|"
    r"版务详情|服务详情|交易详情|关联记录|查看关联记录|计入收支|使用记账本|查看往来记录|AA收款|联系收款方|"
    r"发起群收款|在此商户的交易|对订单有疑惑|查看购物详情|扣款说明|往来流水证明)"
)
CJK_GAP = re.compile(r"(?<=[\u4e00-\u9fff（）()])\s+(?=[\u4e00-\u9fff（）()])")


def extract_field(text: str, label: str) -> str | None:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.strip() != label:
            continue
        values: list[str] = []
        for following in lines[index + 1:]:
            stripped = following.strip()
            if (stripped in FIELD_LABELS and stripped != label) or FIELD_NOISE_LINE.match(compact_text(stripped)):
                break
            values.append(stripped)
        value = " ".join(item for item in values if item)
        value = re.sub(r"\s{2,}", " ", value)
        # OCR 会把一个词拆开：「个体工 商户」「美 团 外 卖」。汉字之间的空格没有意义。
        value = CJK_GAP.sub("", value)
        return value.strip(" ：:>＞") or None
    return None


def first_field(text: str, labels: list[str]) -> str | None:
    for label in labels:
        value = extract_field(text, label)
        if value:
            return value
    return None


def clean_product(product: str | None) -> str | None:
    if not product:
        return None
    product = product.replace(" App", "App")
    product = re.sub(r"\s+", " ", product).strip()
    if product.lower() in {"product", "商品说明"}:
        return None
    return product


def detect_payment_app(text: str, source_hint: str | None = None) -> str | None:
    hint = (source_hint or "").lower()
    if "wechat" in hint or "微信" in text:
        return "wechat"
    if "alipay" in hint or "支付宝" in text:
        return "alipay"
    if "apple" in hint or "wallet" in hint:
        return "wallet"
    if "账单详情" in text or ("订单号" in text and "清算机构" in text):
        return "alipay"
    if "财付通" in text or "当前状态" in text:
        return "wechat"
    # The "账单/全部账单" screen shape is common in WeChat Pay screenshots.
    if "账单" in text and "交易单号" in text and "商户单号" in text:
        return "wechat"
    return None


def detect_platform(text: str, product: str | None) -> str | None:
    haystack = compact_text(f"{product or ''} {text}")
    for hint in PLATFORM_HINTS:
        if hint in haystack:
            return hint
    return None


AMOUNT_LINE = re.compile(r"[-+￥¥]?\s*\d+\.\d{1,2}\s*(?:元)?")

# 金额附近常见、但绝不是商户的行。回溯里被误选成商户的有：订单金额、优惠金额、
# 关联记录、等待确认收货、自动扣款成功、支付有礼、x1。
REJECTED_MERCHANT_LINE = re.compile(
    r"^(?:数量)?[xX×]\d+$|"
    r"^(?:订单金额|优惠金额|订单原价|关联记录|查看关联记录|等待确认收货|等待对方确认收钱|自动扣款成功|"
    r"支付有礼.*|合计|商品总价|打包费|运费.*|交易成功|支付成功|订单状态|月付.*|管理免密支付|.*免密支付|"
    r"进店.*|现在|外卖|小程序|服务|特价外卖团购|全部账单|收钱码收款|经营码交易)$|"
    r"会员专属|准时宝|赔付|预计送达|优惠券|领取.*积分"
)


def is_rejected_merchant_candidate(line: str) -> bool:
    compact = compact_text(line)
    return (
        len(compact) < 2
        or is_generic_merchant_label(line)
        or bool(REJECTED_MERCHANT_LINE.search(compact))
        or bool(AMOUNT_LINE.fullmatch(line.strip()))
        or bool(re.search(r"\d{1,2}:\d{2}", compact))
        # 「关注进度>>」「进入小程序＞」这类是按钮，不是店名
        or compact.endswith((">>", "＞＞", "》"))
    )


def is_generic_merchant_label(line: str) -> bool:
    compact = compact_text(line)
    if compact in {"账单", "全部账单", "账单详情", "交易详情", "当前状态", "支付成功", "交易成功", "主页", "留言"}:
        return True
    return bool(re.fullmatch(r".?(?:交易详情|账单详情|全部账单|账单)", compact))


def score_header_merchant_candidates(text: str) -> tuple[str | None, list[str]]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    # 只锚定第一个金额（主金额）。以前每个金额都当锚点，「优惠金额 -1.73」
    # 这类小字就会把旁边的标签拉进候选。
    amount_indexes = [index for index, line in enumerate(lines) if AMOUNT_LINE.fullmatch(line)][:1]
    nearby_candidates = [
        (amount_index, candidate_index, lines[candidate_index])
        for amount_index in amount_indexes
        for candidate_index in range(max(0, amount_index - 4), min(len(lines), amount_index + 5))
        if candidate_index != amount_index
    ]
    occurrences = Counter(compact_text(candidate) for _, _, candidate in nearby_candidates)
    warnings: list[str] = []
    scored_candidates: list[tuple[int, str]] = []

    for amount_index, candidate_index, candidate in nearby_candidates:
        compact = compact_text(candidate)
        if is_generic_merchant_label(candidate):
            warning = f"rejected_generic_merchant_candidate:{candidate}"
            if warning not in warnings:
                warnings.append(warning)

        distance = abs(candidate_index - amount_index)
        score = (12 if candidate_index > amount_index else 9) - (2 * distance)
        score += 8 * (occurrences[compact] - 1)
        if re.search(r"店|公司|商户|商行|体彩|便利|餐饮|个体工商户", candidate):
            score += 8
        if 2 <= len(compact) <= 60:
            score += 2
        if candidate in FIELD_LABELS or is_generic_merchant_label(candidate):
            score -= 100
        elif REJECTED_MERCHANT_LINE.search(compact):
            score -= 100
        if re.fullmatch(r"[-+￥¥]?\s*\d+\.\d{1,2}\s*(?:元)?", candidate):
            score -= 100
        if re.search(r"\d{1,2}:\d{2}|[>＞]|[！!×]", candidate):
            score -= 50
        if "<" in candidate:
            score -= 30
        scored_candidates.append((score, candidate))

    if not scored_candidates:
        return None, warnings
    score, candidate = max(scored_candidates, key=lambda item: item[0])
    return (candidate if score > 0 else None), warnings


def extract_header_merchant(text: str) -> str | None:
    merchant, _ = score_header_merchant_candidates(text)
    return merchant


def detect_merchant(text: str, product: str | None, platform: str | None) -> str | None:
    merchant, _ = detect_merchant_with_warnings(text, product, platform)
    return merchant


def detect_merchant_with_warnings(text: str, product: str | None, platform: str | None) -> tuple[str | None, list[str]]:
    merchant_full = first_field(text, ["商户全称"])
    if merchant_full and not is_platform_entity(merchant_full):
        return merchant_full, []

    recipient = first_field(text, ["收款方全称", "收款方"])
    if recipient:
        return recipient, []

    header_merchant, warnings = score_header_merchant_candidates(text)
    if not product:
        return header_merchant or first_field(text, ["收款方全称", "收款方"]), warnings

    first_part = re.split(r"\s*-\s*", product, maxsplit=1)[0]
    first_part = re.sub(r"(App|小程序)$", "", first_part).strip()
    # 括号里通常是门店名（「丑师傅白辣椒炒肉（顺天财富店）」），去掉才是商户主体。
    # 全角半角都要认：不同 OCR 后端对同一张截图给出的括号宽度并不一致。
    #
    # 这条要排在间隔号规则前面。「暖燕·姨妈热饮·现炖燕窝（滨江店）」里的间隔号是店名
    # 自身的一部分，先切间隔号只会剩下「暖燕」；按括号切才拿到完整商户主体。
    if re.search(r"[（(]", first_part):
        return re.split(r"[（(]", first_part, maxsplit=1)[0].strip(), warnings
    if "·" in first_part:
        return first_part.split("·", 1)[0].strip(), warnings
    if platform and first_part == platform:
        return header_merchant or platform, warnings
    return header_merchant or (first_part[:40] if first_part else None), warnings


# ---------------------------- 按版式抽商户 / 商品 ----------------------------
# 同一个字段在不同 App 的详情页里位置不一样，通吃的打分规则总会在某个版式上翻车。
# 先认版式，再按版式取：支付宝标题在「账单详情」和主金额之间；美团月付店名在
# 「消费详情」下面；微信沿用原来的金额邻近打分。

LAYOUT_ALIPAY = "alipay_detail"
LAYOUT_WECHAT = "wechat_detail"
LAYOUT_MEITUAN_MONTHLY = "meituan_monthly"
LAYOUT_MEITUAN_ORDER = "meituan_order"

# 「粉大厨（猪肉粉.长沙店）-美团App-2606…」「聚味瞿记·龙虾堂-大众点评App-…」
# 「徐记海鲜（麓谷店）外卖订单」（淘宝闪购）
PLATFORM_ORDER_STORE = re.compile(
    r"^(?P<store>.+?)[)）\s]*-(?:美团|大众点评)(?:a\s*p\s*p|微信小程序|小程序)|^(?P<takeout>.+?)外卖订单",
    re.I,
)
GENERIC_PLATFORM_STORES = {"团购", "美团订单", "美团跑腿", "外卖", "外卖订单"}
QR_PAYEE_PREFIX = re.compile(r"^(?:扫二维码付款|扫码付款|二维码付款)-?给")


def detect_layout(lines: list[str]) -> str:
    compact_lines = [compact_text(line) for line in lines]
    if "消费详情" in compact_lines and "订单状态" in compact_lines:
        return LAYOUT_MEITUAN_MONTHLY
    if any(line.startswith("进店") for line in compact_lines):
        return LAYOUT_MEITUAN_ORDER
    if any(re.fullmatch(r".?账单详情", line) for line in compact_lines):
        return LAYOUT_ALIPAY
    return LAYOUT_WECHAT


def strip_branch(name: str | None) -> str | None:
    """
    去掉店名后面的分店括号：「Super Model超模厨房(长沙岳麓店)」→「Super Model超模厨房」。
    OCR 常多认一个括号或截断括号，所以从第一个左括号起整段切掉；整串都是括号时返回 None。
    """
    if not name:
        return None
    stripped = re.sub(r"\s*[（(].*$", "", name).strip(" -·•")
    return stripped or None


def store_from_platform_product(product: str | None) -> str | None:
    if not product:
        return None
    # 去掉汉字旁边的空格，保留英文单词之间的（「Super Model」）
    normalized = re.sub(r"\s+(?=[^A-Za-z\s])|(?<=[^A-Za-z\s])\s+", "", product)
    match = PLATFORM_ORDER_STORE.match(normalized)
    if not match:
        return None
    store = strip_branch(match.group("store") or match.group("takeout"))
    if not store:
        return None
    if store in GENERIC_PLATFORM_STORES or is_platform_entity(store):
        return None
    return store


def _first_amount_index(lines: list[str], start: int = 0) -> int | None:
    for index in range(start, len(lines)):
        if AMOUNT_LINE.fullmatch(lines[index]):
            return index
    return None


def _label_index(lines: list[str], pattern: str) -> int | None:
    for index, line in enumerate(lines):
        if re.fullmatch(pattern, compact_text(line)):
            return index
    return None


def _is_parenthetical(line: str) -> bool:
    return bool(re.fullmatch(r"[（(].*[)）]?", compact_text(line)))


def alipay_header_merchant(lines: list[str]) -> str | None:
    start = _label_index(lines, r".?账单详情")
    end = _first_amount_index(lines, start + 1) if start is not None else None
    if start is None or end is None or end - start > 7:
        return None
    candidates = [
        line
        for line in lines[start + 1:end]
        if not is_rejected_merchant_candidate(line) and not _is_parenthetical(line)
    ]
    if not candidates:
        return None
    # 支付宝标题区常是「图标字 + 店名 + 店名」，重复出现的那个最可信
    occurrences = Counter(compact_text(line) for line in candidates)
    repeated = [line for line in candidates if occurrences[compact_text(line)] > 1]
    return (repeated or candidates)[-1]


def meituan_monthly_header_merchant(lines: list[str]) -> str | None:
    start = _label_index(lines, r"消费详情")
    end = _first_amount_index(lines, start + 1) if start is not None else None
    if start is None or end is None:
        return None
    candidates = [
        line
        for line in lines[start + 1:end]
        if not is_rejected_merchant_candidate(line) and not _is_parenthetical(line)
    ]
    return strip_branch(candidates[-1]) if candidates else None


def meituan_order_header_merchant(lines: list[str]) -> str | None:
    shop_index = next((i for i, line in enumerate(lines) if compact_text(line).startswith("进店")), None)
    if shop_index is None:
        return None
    for line in reversed(lines[max(0, shop_index - 3):shop_index]):
        if not is_rejected_merchant_candidate(line):
            return strip_branch(re.sub(r"(?:\.{2,}|…|⋯)$", "", line))
    return None


def clean_merchant(name: str | None) -> str | None:
    if not name:
        return None
    name = CJK_GAP.sub("", name.strip())
    # 微信经营码：「扫二维码付款-给石榴」里真正的商户是「石榴」
    payee = QR_PAYEE_PREFIX.sub("", name)
    if payee != name:
        payee = re.sub(r"\s*[（(]\d{1,2}:\d{2}.*$", "", payee).strip()
        return payee or None
    return name


SHOP_NAME_CHARS = re.compile(r"店|馆|铺|行|厅|坊|屋|房|吧|院|社|部|庄|园|超市|公司|餐|面|粉|饭|菜|果|花|彩")


def looks_like_person_name(name: str | None) -> bool:
    return bool(name) and bool(re.fullmatch(r"[\u4e00-\u9fff]{2,3}", name)) and not SHOP_NAME_CHARS.search(name)


def merchant_quality(merchant: str | None) -> str:
    if not merchant:
        return "missing"
    if is_platform_entity(merchant):
        return "platform"
    if is_masked_merchant(merchant):
        return "masked"
    return "ok"


def resolve_merchant(
    text: str,
    lines: list[str],
    layout: str,
    product: str | None,
    platform: str | None,
) -> tuple[str | None, str | None, str, list[str]]:
    """返回 (展示商户, 工商名, 质量, 告警)。"""
    legal = clean_merchant(first_field(text, ["商户全称", "收款方全称", "收款方"]))
    store = store_from_platform_product(product)
    warnings: list[str] = []
    if layout == LAYOUT_ALIPAY:
        ordered = [store, alipay_header_merchant(lines), legal]
    elif layout == LAYOUT_MEITUAN_MONTHLY:
        ordered = [store, meituan_monthly_header_merchant(lines)]
    elif layout == LAYOUT_MEITUAN_ORDER:
        ordered = [store, meituan_order_header_merchant(lines)]
    else:
        detected, warnings = detect_merchant_with_warnings(text, product, platform)
        ordered = [store, detected]

    present = [name for name in (clean_merchant(item) for item in ordered) if name]
    # 按质量挑：真实店名 > 打码名（tb**5）> 平台主体（北京三快）。同档取靠前的。
    rank = {"ok": 0, "masked": 1, "platform": 2}
    merchant = min(present, key=lambda name: rank[merchant_quality(name)]) if present else None
    return merchant, legal, merchant_quality(merchant), warnings


def extract_items(lines: list[str], layout: str) -> str | None:
    """从截图里抽具体买了什么。抽不到就返回 None，让 thing 回退到分类标签。"""
    items: list[str] = []
    if layout == LAYOUT_MEITUAN_MONTHLY:
        start = next((i for i, line in enumerate(lines) if "美团商品订单" in compact_text(line)), None)
        end = _label_index(lines, r"订单原价|商品总价")
        if start is not None and end is not None and end > start:
            for line in lines[start + 1:end]:
                compact = compact_text(line)
                if compact.startswith("查看") or re.fullmatch(r"[xX×]\d+|【.*】|[（(].*[)）]|[.>›。]*", compact):
                    continue
                items.append(line)
    elif layout == LAYOUT_ALIPAY:
        # 淘宝/天猫：「交易详情」和「共N件」之间是商品标题，取汉字最多的那行
        start = _label_index(lines, r"交易详情")
        end = _label_index(lines, r"共\d+件")
        if start is not None and end is not None and 0 < end - start <= 8:
            block = [line for line in lines[start + 1:end] if not is_rejected_merchant_candidate(line)]
            if block:
                items.append(max(block, key=lambda line: len(re.findall(r"[\u4e00-\u9fff]", line))))
    else:
        # 微信经营码的小票：「紫米芋泥肉松等2个付款项>」
        receipt = _label_index(lines, r"小票")
        if receipt is not None and receipt + 1 < len(lines):
            item = re.sub(r"等\d+个付款项.*$|[>＞]+$", "", lines[receipt + 1]).strip()
            if item:
                items.append(item)
    joined = "、".join(items[:2]).strip()
    return joined[:20] or None


def extract_platform_category(lines: list[str]) -> str | None:
    index = _label_index(lines, r"账单分类")
    if index is None or index + 1 >= len(lines):
        return None
    return re.sub(r"[>〉＞)）]+$", "", compact_text(lines[index + 1])) or None


def normalize_order_id(value: str | None) -> str | None:
    if not value:
        return None
    if re.fullmatch(r"[\d\s]+", value):
        reconstructed = compact_text(value)
        return reconstructed if len(reconstructed) >= 6 else None
    candidates = re.findall(r"(?<![A-Za-z0-9])([A-Za-z0-9][A-Za-z0-9_-]{5,})(?![A-Za-z0-9])", value)
    return candidates[-1] if candidates else None


def build_parse_warnings(parsed: dict[str, Any], merchant_warnings: list[str], text: str) -> list[str]:
    warnings = list(merchant_warnings)
    for field in ("amount", "status", "paid_at", "merchant"):
        if parsed.get(field) is None:
            warnings.append(f"missing_{field}")

    transaction_raw = first_field(text, ["交易单号", "订单号"])
    if parsed.get("transaction_id") is None:
        warnings.append("invalid_transaction_id" if transaction_raw else "missing_transaction_id")

    merchant_order_raw = first_field(text, ["商户单号", "商家订单号", "经营单号"])
    if merchant_order_raw and parsed.get("merchant_order_id") is None:
        warnings.append("invalid_merchant_order_id")

    paid_at_raw = first_field(text, ["支付时间"])
    if paid_at_raw and parsed.get("paid_at") is None:
        warnings.remove("missing_paid_at")
        warnings.append("invalid_paid_at")
    return list(dict.fromkeys(warnings))


def parse_payment_method(value: str | None) -> tuple[str | None, str | None, str | None]:
    if not value:
        return None, None, None
    normalized = value.replace("（", "(").replace("）", ")")
    card_last4 = None
    match = re.search(r"\((\d{4})\)", normalized)
    if match:
        card_last4 = match.group(1)
    card_type = None
    if "信用卡" in normalized:
        card_type = "信用卡"
    elif "储蓄卡" in normalized:
        card_type = "储蓄卡"
    bank_name = normalized
    bank_name = re.sub(r"(信用卡|储蓄卡|借记卡).*", "", bank_name).strip()
    return bank_name or None, card_type, card_last4


def build_transaction_uid(parsed: dict[str, Any]) -> str:
    transaction_id = parsed.get("transaction_id")
    if transaction_id:
        return f"wechat_txn_{transaction_id}" if parsed.get("payment_app") == "wechat" else f"txn_{transaction_id}"
    basis = "|".join(
        str(parsed.get(key) or "")
        for key in ["source", "payment_app", "amount", "paid_at", "product", "payment_method"]
    )
    return "bill_" + hashlib.sha256(basis.encode("utf-8")).hexdigest()[:24]


def parse_bill_text(text: str, source: str = "ios_shortcut", source_hint: str | None = None) -> ParsedBill:
    text = normalize_text(text)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    layout = detect_layout(lines)
    product = clean_product(first_field(text, ["商品说明", "商品"]))
    platform = detect_platform(text, product)
    merchant, merchant_legal, quality, merchant_warnings = resolve_merchant(text, lines, layout, product, platform)
    items = extract_items(lines, layout)
    payment_app = detect_payment_app(text, source_hint=source_hint or source)
    classify_product = " ".join(part for part in (product, items) if part) or None
    # 支付宝的「账单分类」按收款主体给：美团单的收款方是北京三快，类目就成了「文化休闲」。
    # 收款方是平台主体时这个类目不可信，不用。
    platform_category = (
        extract_platform_category(lines)
        if layout == LAYOUT_ALIPAY and not is_platform_entity(merchant_legal)
        else None
    )
    classification = classify_locally(
        merchant=merchant,
        product=classify_product,
        platform=platform,
        payment_app=payment_app,
        text=text,
        platform_category=platform_category,
    )
    # 微信经营码收款人像个人名字（2~3 个汉字、不带店铺字眼）、又没有小票明细时，
    # 按个人转账处理；否则留给模型结合截图判断。没配模型时不至于全掉进「未分类」。
    if (
        classification.status == "pending"
        and re.search(r"(?:扫二维码付款|扫码付款|二维码付款)-?给", compact_text(text))
        and not items
        and looks_like_person_name(merchant)
    ):
        classification = ClassificationResult(
            category="personal_transfer",
            thing="个人转账",
            confidence=0.8,
            source="local_rule",
            status="resolved",
            reason="local_rule:personal_transfer:qr_person_name",
        )
    # 展示名没撞上规则时，再拿工商名撞一次（「步步高」→「步步高商业连锁股份有限公司」）
    if (
        classification.status == "pending"
        and merchant_legal
        and merchant_legal != merchant
        and not is_platform_entity(merchant_legal)
    ):
        classification = classify_locally(
            merchant=merchant_legal,
            product=classify_product,
            platform=platform,
            payment_app=payment_app,
            text=text,
            platform_category=platform_category,
        )
    amount = extract_amount(text)
    status = extract_status(text)
    paid_at = extract_paid_at(text)
    direction = "outflow"
    if status == "refunded":
        direction = "inflow"
    elif re.search(r"[-]\s*\d", compact_text(text)):
        direction = "outflow"

    payment_method = first_field(text, ["支付方式", "付款方式"])
    bank_name, card_type, card_last4 = parse_payment_method(payment_method)

    parsed: dict[str, Any] = {
        "source": source,
        "payment_app": payment_app,
        "amount": amount,
        "direction": direction,
        "status": status,
        "paid_at": paid_at,
        "merchant": merchant,
        "platform": platform,
        "thing": items or classification.thing,
        "category": classification.category,
        "category_confidence": classification.confidence,
        "classification_source": classification.source,
        "classification_status": classification.status,
        "classification_reason": classification.reason,
        "product": product,
        "payment_method": payment_method,
        "bank_name": bank_name,
        "card_type": card_type,
        "card_last4": card_last4,
        "acquirer": extract_field(text, "收单机构"),
        "clearing_org": extract_field(text, "清算机构"),
        "transaction_id": normalize_order_id(first_field(text, ["交易单号", "订单号"])),
        "merchant_order_id": normalize_order_id(first_field(text, ["商户单号", "商家订单号", "经营单号"])),
    }

    confidence = 0.35
    for key in ["amount", "status", "paid_at", "product", "payment_method", "transaction_id"]:
        if parsed.get(key):
            confidence += 0.1
    if parsed.get("merchant"):
        confidence += 0.08
    parsed["confidence"] = round(min(confidence, 0.99), 2)
    parsed["transaction_uid"] = build_transaction_uid(parsed)
    parsed["raw_text"] = text
    parsed["parse_warnings"] = build_parse_warnings(parsed, merchant_warnings, text)
    parsed["merchant_legal"] = merchant_legal
    parsed["merchant_quality"] = quality
    parsed["items"] = items

    return ParsedBill(**parsed)


def extraction_status_for(parsed: ParsedBill) -> str:
    """
    本地商户质量差（平台主体 / 打码 / 缺失）时交给模型补抽。分类本身 pending 的行
    模型反正要看，届时会顺带回填商户和消费内容，这里不必重复排队。
    """
    return "pending" if parsed.merchant_quality != "ok" else "done"


def store_bill_capture(
    ocr_text: str,
    source: str = "ios_shortcut",
    source_hint: str | None = None,
    image_path: str | None = None,
    captured_at: str | None = None,
) -> ParsedBill:
    parsed = parse_bill_text(ocr_text, source=source, source_hint=source_hint)
    stored_image_path = portable_image_path(image_path)
    capture_hash = hashlib.sha256(f"{source}|{ocr_text}|{stored_image_path or ''}".encode("utf-8")).hexdigest()[:32]
    # 没有平台交易号时，解析字段本身不足以稳定去重：两张缺时间、缺商户且
    # 金额相同的截图会生成同一个 UID，后来的记录会把前一条覆盖。此时让
    # 原始捕获成为身份来源；同一捕获重复处理仍然幂等，不同截图则都能追溯。
    if not parsed.transaction_id:
        parsed.transaction_uid = f"capture_{capture_hash[:24]}"
    now = datetime.now().isoformat(timespec="seconds")

    conn = connect()
    conn.execute(
        """
        insert or ignore into raw_bill_captures
        (capture_hash, source, ocr_text, image_path, captured_at, created_at)
        values (?, ?, ?, ?, ?, ?)
        """,
        (capture_hash, source, normalize_text(ocr_text), stored_image_path, captured_at, now),
    )
    parsed = apply_persisted_classification(conn, parsed, capture_hash)
    if (
        parsed.classification_source in {"local_rule", "local_industry", "platform_category"}
        and not is_enabled_category(conn, parsed.category)
    ):
        parsed.category = "uncategorized"
        parsed.thing = None
        parsed.category_confidence = 0
        parsed.classification_source = "none"
        parsed.classification_status = "pending"
        parsed.classification_reason = "disabled_local_category"
    conn.execute(
        """
        insert into transactions
        (transaction_uid, source, payment_app, amount, direction, status, paid_at, merchant, platform,
         thing, category, product, payment_method, bank_name, card_type, card_last4, acquirer, clearing_org,
         transaction_id, merchant_order_id,
         confidence, raw_capture_hash, raw_text, created_at, classification_source,
         classification_confidence, classification_status, classification_reason, parse_warnings,
         merchant_legal, merchant_quality, extraction_status, extraction_attempts)
        values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
        on conflict(transaction_uid) do update set
            source = excluded.source,
            payment_app = excluded.payment_app,
            amount = excluded.amount,
            direction = excluded.direction,
            status = excluded.status,
            paid_at = excluded.paid_at,
            merchant = excluded.merchant,
            platform = excluded.platform,
            thing = excluded.thing,
            category = excluded.category,
            product = excluded.product,
            payment_method = excluded.payment_method,
            bank_name = excluded.bank_name,
            card_type = excluded.card_type,
            card_last4 = excluded.card_last4,
            acquirer = excluded.acquirer,
            clearing_org = excluded.clearing_org,
            transaction_id = excluded.transaction_id,
            merchant_order_id = excluded.merchant_order_id,
            confidence = excluded.confidence,
            raw_capture_hash = excluded.raw_capture_hash,
            raw_text = excluded.raw_text,
            classification_source = excluded.classification_source,
            classification_confidence = excluded.classification_confidence,
            classification_status = excluded.classification_status,
            classification_reason = excluded.classification_reason,
            parse_warnings = excluded.parse_warnings,
            merchant_legal = excluded.merchant_legal,
            merchant_quality = excluded.merchant_quality,
            extraction_status = excluded.extraction_status,
            extraction_attempts = 0
        """,
        (
            parsed.transaction_uid,
            parsed.source,
            parsed.payment_app,
            parsed.amount,
            parsed.direction,
            parsed.status,
            parsed.paid_at,
            parsed.merchant,
            parsed.platform,
            parsed.thing,
            parsed.category,
            parsed.product,
            parsed.payment_method,
            parsed.bank_name,
            parsed.card_type,
            parsed.card_last4,
            parsed.acquirer,
            parsed.clearing_org,
            parsed.transaction_id,
            parsed.merchant_order_id,
            parsed.confidence,
            capture_hash,
            parsed.raw_text,
            now,
            parsed.classification_source,
            parsed.category_confidence,
            parsed.classification_status,
            parsed.classification_reason,
            json.dumps(parsed.parse_warnings, ensure_ascii=False),
            parsed.merchant_legal,
            parsed.merchant_quality,
            extraction_status_for(parsed),
        ),
    )
    if parsed.classification_status == "resolved" and parsed.classification_source == "local_rule":
        remember_merchant_classification(
            conn,
            merchant=parsed.merchant,
            category=parsed.category,
            thing=parsed.thing,
            confidence=parsed.category_confidence,
            source=parsed.classification_source,
        )
    conn.commit()
    conn.close()
    return parsed


def parsed_to_json(parsed: ParsedBill) -> str:
    return json.dumps(asdict(parsed), ensure_ascii=False, indent=2)


def read_text_arg(path: str | None) -> str:
    if path:
        return Path(path).read_text(encoding="utf-8")
    import sys

    return sys.stdin.read()


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse and store OCR text from a payment bill screenshot.")
    parser.add_argument("--file", help="Text file containing OCR output. Reads stdin if omitted.")
    parser.add_argument("--source", default="manual")
    parser.add_argument("--source-hint")
    parser.add_argument("--image-path")
    parser.add_argument("--captured-at")
    parser.add_argument("--no-store", action="store_true")
    args = parser.parse_args()

    text = read_text_arg(args.file)
    if args.no_store:
        parsed = parse_bill_text(text, source=args.source, source_hint=args.source_hint)
    else:
        parsed = store_bill_capture(
            text,
            source=args.source,
            source_hint=args.source_hint,
            image_path=args.image_path,
            captured_at=args.captured_at,
        )
    print(parsed_to_json(parsed))


if __name__ == "__main__":
    main()
