from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parent
DATA_DIR = PROJECT_DIR / "data"
APP_DB = DATA_DIR / "cfo.sqlite"


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
    "商家小程序",
    "账单分类",
    "标签",
    "账单服务",
]


CATEGORY_RULES = [
    ("education", "证券考试", ["证券行业专业人员水平评价", "考试", "报名", "中国证券业协会"]),
    ("books", "图书", ["新华书店", "湖南省新华书店", "书店", "图书", "教材", "书籍"]),
    ("property", "物业服务", ["物业", "碧桂园生活服务", "生活服务集团", "物业费", "物业服务"]),
    ("telecom", "通信充值", ["手机充值", "手机话费", "话费", "中国电信", "中国移动", "中国联通", "全渠道运营中心"]),
    ("entertainment", "演出票务", ["大麦", "大麦网", "演出", "赛事票品", "票品", "电影票", "演唱会"]),
    ("credit_repayment", "信用借还", ["花呗自动还款", "还款到", "信用借还", "账单还款", "还款成功"]),
    ("utilities", "水电燃缴费", ["缴费说明", "电费", "水费", "燃气费", "供电分公司", "长沙供电", "户号"]),
    ("parking", "停车缴费", ["停车缴费", "停车费", "停车"]),
    ("car_charging", "车辆充电", ["充电桩充值", "充电桩", "华自充电", "特来电", "星星充电", "小桔充电"]),
    ("auto", "爱车养车", ["爱车养车", "特斯拉", "TESLA", "Tesla", "加油", "洗车", "汽车保养", "车险"]),
    ("groceries", "超市便利", ["超市", "便利店", "购物超市", "连锁便利店", "便利店-消费", "新佳宜", "乐尔乐", "罗森", "全家", "美宜佳", "芙蓉兴盛"]),
    ("fruit", "水果", ["水果", "鲜果", "果川", "鲜果优品"]),
    ("bakery", "烘焙", ["面包", "烘焙", "蛋糕", "鹭岛面包", "面包店"]),
    ("coffee_tea", "奶茶", ["沪上阿姨", "精选茶饮", "奶茶", "茶饮", "喜茶", "奈雪", "茶百道", "霸王茶姬"]),
    ("coffee_tea", "咖啡", ["咖啡", "瑞幸", "星巴克", "Manner", "manner"]),
    ("food_delivery", "饭", ["外卖", "餐饮", "美食", "饭", "粉大厨", "猪肉粉", "米粉", "盖码饭", "湘菜", "海鲜", "徐记海鲜", "饿了么", "麦当劳", "肯德基"]),
    ("transport", "打车", ["滴滴", "打车", "曹操出行", "高德打车"]),
    ("transport", "交通", ["地铁", "公交", "火车", "机票", "高铁"]),
    ("stationery", "文具用品", ["学生用品", "文具", "记号笔", "辉煌学生用品店"]),
    ("ecommerce", "网购", ["京东", "淘宝", "天猫", "拼多多", "抖音商城", "小红书"]),
    ("investment", "理财", ["基金", "理财", "定投", "申购", "赎回", "证券"]),
    ("healthcare", "医疗", ["医院", "门诊", "药房", "体检"]),
]


PLATFORM_HINTS = ["美团", "京东", "淘宝", "天猫", "拼多多", "饿了么", "抖音", "小红书"]


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
            created_at text not null
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
        },
    )
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
    return conn


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("−", "-").replace("－", "-").replace("—", "-")
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


def extract_field(text: str, label: str) -> str | None:
    label_pattern = re.escape(label)
    next_labels = [re.escape(item) for item in FIELD_LABELS if item != label]
    pattern = rf"(?m)^\s*{label_pattern}\s*$\n(.*?)(?=\n\s*(?:{'|'.join(next_labels)})\s*$|\Z)"
    match = re.search(pattern, text, flags=re.S | re.M)
    if not match:
        return None
    value = match.group(1).strip()
    value = re.sub(r"\n+", " ", value)
    value = re.sub(r"\s{2,}", " ", value)
    return value.strip(" ：:>＞")


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
    haystack = f"{product or ''} {text}"
    for hint in PLATFORM_HINTS:
        if hint in haystack:
            return hint
    return None


def extract_header_merchant(text: str) -> str | None:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    ignored = {
        "账单",
        "全部账单",
        "账单详情",
        "当前状态",
        "支付成功",
        "交易成功",
    }
    for idx, line in enumerate(lines):
        if re.fullmatch(r"[-+￥¥]?\s*\d+\.\d{1,2}\s*(?:元)?", line):
            for previous in reversed(lines[max(0, idx - 4):idx]):
                if previous in ignored:
                    continue
                if re.search(r"\d{1,2}:\d{2}|[A-Za-z]{2,}|[>＞]|[！!×]", previous):
                    continue
                return previous
    return None


def detect_merchant(text: str, product: str | None, platform: str | None) -> str | None:
    merchant_full = first_field(text, ["商户全称"])
    if merchant_full:
        return merchant_full

    header_merchant = extract_header_merchant(text)
    if not product:
        return header_merchant or first_field(text, ["收款方全称", "收款方"])

    first_part = re.split(r"\s*-\s*", product, maxsplit=1)[0]
    first_part = re.sub(r"(App|小程序)$", "", first_part).strip()
    if "·" in first_part:
        return first_part.split("·", 1)[0].strip()
    if "（" in first_part:
        return first_part.split("（", 1)[0].strip()
    if platform and first_part == platform:
        return header_merchant or platform
    return header_merchant or (first_part[:40] if first_part else None)


def detect_category_and_thing(text: str, product: str | None) -> tuple[str, str | None]:
    haystack = f"{product or ''} {text}"
    for category, thing, hints in CATEGORY_RULES:
        if any(hint in haystack for hint in hints):
            return category, thing
    return "uncategorized", None


def normalize_order_id(value: str | None) -> str | None:
    if not value:
        return None
    value = re.sub(r"\s+", "", value)
    if re.search(r"扫码|退款|查询|点击|查看", value):
        return None
    return value or None


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
    product = clean_product(first_field(text, ["商品说明", "商品"]))
    platform = detect_platform(text, product)
    merchant = detect_merchant(text, product, platform)
    category, thing = detect_category_and_thing(text, product)
    payment_app = detect_payment_app(text, source_hint=source_hint or source)
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
        "thing": thing,
        "category": category,
        "product": product,
        "payment_method": payment_method,
        "bank_name": bank_name,
        "card_type": card_type,
        "card_last4": card_last4,
        "acquirer": extract_field(text, "收单机构"),
        "clearing_org": extract_field(text, "清算机构"),
        "transaction_id": normalize_order_id(first_field(text, ["交易单号", "订单号"])),
        "merchant_order_id": normalize_order_id(first_field(text, ["商户单号", "商家订单号"])),
    }

    confidence = 0.35
    for key in ["amount", "status", "paid_at", "product", "payment_method", "transaction_id"]:
        if parsed.get(key):
            confidence += 0.1
    if parsed.get("merchant"):
        confidence += 0.08
    if parsed.get("category") != "uncategorized":
        confidence += 0.07
    parsed["confidence"] = min(confidence, 0.99)
    parsed["transaction_uid"] = build_transaction_uid(parsed)
    parsed["raw_text"] = text

    return ParsedBill(**parsed)


def store_bill_capture(
    ocr_text: str,
    source: str = "ios_shortcut",
    source_hint: str | None = None,
    image_path: str | None = None,
    captured_at: str | None = None,
) -> ParsedBill:
    parsed = parse_bill_text(ocr_text, source=source, source_hint=source_hint)
    capture_hash = hashlib.sha256(f"{source}|{ocr_text}|{image_path or ''}".encode("utf-8")).hexdigest()[:32]
    now = datetime.now().isoformat(timespec="seconds")

    conn = connect()
    conn.execute(
        """
        insert or ignore into raw_bill_captures
        (capture_hash, source, ocr_text, image_path, captured_at, created_at)
        values (?, ?, ?, ?, ?, ?)
        """,
        (capture_hash, source, normalize_text(ocr_text), image_path, captured_at, now),
    )
    conn.execute(
        """
        insert into transactions
        (transaction_uid, source, payment_app, amount, direction, status, paid_at, merchant, platform,
         thing, category, product, payment_method, bank_name, card_type, card_last4, acquirer, clearing_org,
         transaction_id, merchant_order_id,
         confidence, raw_capture_hash, raw_text, created_at)
        values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            merchant_order_id = excluded.merchant_order_id,
            confidence = excluded.confidence,
            raw_capture_hash = excluded.raw_capture_hash,
            raw_text = excluded.raw_text
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
        ),
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
