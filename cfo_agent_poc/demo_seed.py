"""Seed a self-contained demo ledger so the project runs with zero configuration.

Usage:
    python3 demo_seed.py            # writes data/cfo-demo.sqlite
    CFO_DB_PATH=... python3 demo_seed.py

All transactions are fictional. Dates are generated relative to today so the
demo dashboard always looks alive. Re-running is idempotent: previous demo
rows are removed before inserting.
"""

from __future__ import annotations

import os
import random
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from bill_store import ensure_bill_tables

PROJECT_DIR = Path(__file__).resolve().parent
DATA_DIR = PROJECT_DIR / "data"
DB_PATH = Path(os.environ.get("CFO_DB_PATH") or DATA_DIR / "cfo-demo.sqlite")

DAYS = 90
RNG = random.Random(20260707)

# (merchant, thing, category, platform, amount range)
COFFEE = [
    ("瑞幸咖啡", "咖啡", "coffee_tea", None, (9.9, 26)),
    ("星巴克", "咖啡", "coffee_tea", None, (28, 45)),
    ("霸王茶姬", "奶茶", "coffee_tea", None, (16, 28)),
    ("茶百道", "奶茶", "coffee_tea", None, (13, 22)),
]
MEALS = [
    ("美团外卖·老乡鸡", "外卖", "food_delivery", "美团", (22, 45)),
    ("美团外卖·兰州拉面", "外卖", "food_delivery", "美团", (18, 32)),
    ("饿了么·麦当劳", "外卖", "food_delivery", "饿了么", (25, 58)),
    ("肯德基", "快餐", "food_delivery", None, (28, 52)),
    ("楼下湘菜馆", "餐饮", "food_delivery", None, (35, 88)),
    ("沙县小吃", "餐饮", "food_delivery", None, (15, 28)),
]
TRANSPORT = [
    ("滴滴出行", "打车", "transport", None, (12, 46)),
    ("城市地铁", "地铁", "transport", None, (3, 7)),
]
GROCERIES = [
    ("罗森便利店", "便利店", "groceries", None, (9, 45)),
    ("全家便利店", "便利店", "groceries", None, (8, 38)),
    ("盒马鲜生", "超市", "groceries", None, (45, 160)),
]
WEEKLY = [
    ("百果园", "水果", "fruit", None, (22, 65)),
    ("面包新语", "面包", "bakery", None, (16, 42)),
    ("特来电充电", "充电", "car_charging", None, (42, 95)),
    ("路侧停车缴费", "停车", "parking", None, (5, 20)),
]
ECOMMERCE = [
    ("京东商城", "网购", "ecommerce", "京东", (39, 299)),
    ("淘宝", "网购", "ecommerce", "淘宝", (25, 199)),
]
MONTHLY_BILLS = [
    ("国家电网电费", "电费", "utilities", None, (160, 260)),
    ("自来水公司", "水费", "utilities", None, (35, 65)),
    ("中国电信话费充值", "话费", "telecom", None, (99, 99)),
]
RARE = [
    ("大麦网", "演唱会门票", "entertainment", None, (688, 688)),
    ("京东商城", "机械键盘", "ecommerce", "京东", (1299, 1299)),
    ("益丰大药房", "药品", "healthcare", None, (32, 78)),
    ("新华书店", "图书", "books", None, (49, 96)),
]
PAYMENT_METHODS = ["零钱", "余额宝", "银行卡(demo)"]


def make_tx(day_offset: int, hour: int, minute: int, item: tuple, direction: str = "outflow") -> dict:
    merchant, thing, category, platform, (lo, hi) = item
    amount = round(RNG.uniform(lo, hi), 2) if lo != hi else float(lo)
    paid_at = (datetime.now().replace(hour=hour, minute=minute, second=RNG.randint(0, 59), microsecond=0)
               - timedelta(days=day_offset))
    return {
        "payment_app": RNG.choice(["wechat", "wechat", "alipay"]),
        "amount": amount,
        "direction": direction,
        "status": "支付成功",
        "paid_at": paid_at.isoformat(timespec="seconds"),
        "merchant": merchant,
        "platform": platform,
        "thing": thing,
        "category": category,
        "product": thing,
        "payment_method": RNG.choice(PAYMENT_METHODS),
        "confidence": round(RNG.uniform(0.78, 0.97), 2),
    }


def generate_transactions() -> list[dict]:
    txs: list[dict] = []
    for offset in range(DAYS):
        date = datetime.now().date() - timedelta(days=offset)
        weekday = date.isoweekday()

        if RNG.random() < (0.42 if weekday <= 5 else 0.22):
            txs.append(make_tx(offset, RNG.randint(8, 10), RNG.randint(0, 59), RNG.choice(COFFEE)))
        if RNG.random() < 0.30:
            txs.append(make_tx(offset, RNG.randint(11, 13), RNG.randint(0, 59), RNG.choice(MEALS)))
        if RNG.random() < 0.20:
            txs.append(make_tx(offset, RNG.randint(18, 20), RNG.randint(0, 59), RNG.choice(MEALS)))
        if RNG.random() < 0.14:
            txs.append(make_tx(offset, RNG.randint(8, 22), RNG.randint(0, 59), RNG.choice(TRANSPORT)))
        if offset % 3 == 0 and RNG.random() < 0.5:
            txs.append(make_tx(offset, RNG.randint(19, 21), RNG.randint(0, 59), RNG.choice(GROCERIES)))
        if weekday == 6 and RNG.random() < 0.8:
            txs.append(make_tx(offset, RNG.randint(10, 17), RNG.randint(0, 59), RNG.choice(WEEKLY)))
        if RNG.random() < 0.05:
            txs.append(make_tx(offset, RNG.randint(12, 22), RNG.randint(0, 59), RNG.choice(ECOMMERCE)))

        # monthly bills land近月初
        if date.day in (2, 3) and offset < DAYS - 5:
            for bill in MONTHLY_BILLS:
                if RNG.random() < 0.85:
                    txs.append(make_tx(offset, RNG.randint(9, 20), RNG.randint(0, 59), bill))

    # 少量大额/低频事件与退款收入
    for offset, item in zip((12, 33, 47, 61), RARE):
        txs.append(make_tx(offset, RNG.randint(10, 20), RNG.randint(0, 59), item))
    txs.append(make_tx(9, 14, 20, ("淘宝退款", "网购退款", "ecommerce", "淘宝", (89, 89)), direction="inflow"))

    # 保证「今日」视图不为空
    txs.append(make_tx(0, 9, 12, COFFEE[0]))
    txs.append(make_tx(0, 12, 24, MEALS[0]))

    txs.sort(key=lambda t: t["paid_at"])
    return txs


def seed(db_path: Path = DB_PATH) -> int:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    ensure_bill_tables(conn)
    conn.execute("delete from transactions where transaction_uid like 'demo-%'")

    now = datetime.now().isoformat(timespec="seconds")
    txs = generate_transactions()
    for index, tx in enumerate(txs):
        conn.execute(
            """
            insert into transactions
            (transaction_uid, source, payment_app, amount, direction, status, paid_at, merchant, platform,
             thing, category, product, payment_method, bank_name, card_type, card_last4, acquirer, clearing_org,
             transaction_id, merchant_order_id, confidence, raw_capture_hash, raw_text, created_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(transaction_uid) do nothing
            """,
            (
                f"demo-{index:04d}",
                "demo_seed",
                tx["payment_app"],
                tx["amount"],
                tx["direction"],
                tx["status"],
                tx["paid_at"],
                tx["merchant"],
                tx["platform"],
                tx["thing"],
                tx["category"],
                tx["product"],
                tx["payment_method"],
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                tx["confidence"],
                None,
                f"[DEMO] 虚构演示数据：{tx['merchant']} ¥{tx['amount']}",
                now,
            ),
        )
    conn.commit()
    count = conn.execute("select count(*) from transactions").fetchone()[0]
    conn.close()
    return count


def main() -> None:
    count = seed()
    print(f"seeded demo ledger at {DB_PATH} ({count} transactions, all fictional)")


if __name__ == "__main__":
    main()
