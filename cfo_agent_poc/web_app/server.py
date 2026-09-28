from __future__ import annotations

import argparse
import hashlib
import html
import http.cookies
import json
import mimetypes
import os
import secrets
import sqlite3
import statistics
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

from generate_snapshot import build_payload as build_snapshot_payload, correction_fields


WEB_DIR = Path(__file__).resolve().parent
ROOT_DIR = WEB_DIR.parents[0]
FRONTEND_DIR = WEB_DIR / "dist" if (WEB_DIR / "dist" / "index.html").exists() else WEB_DIR


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env_file(ROOT_DIR / ".env")
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

DB_PATH = Path(os.environ.get("CFO_DB_PATH") or ROOT_DIR / "data" / "cfo.sqlite")
DEMO_MODE = os.environ.get("CFO_DEMO") == "1"
OWNER_NAME = os.environ.get("CFO_OWNER_NAME", "").strip() or "用户"
# 链路耗时追踪。默认关闭：这些日志会把工具调用参数打到标准输出，
# 而参数里带着用户的查询内容，不该在别人跑这个项目时默认刷屏。
DEBUG_TRACE = os.environ.get("CFO_DEBUG") == "1"

from mail_sync import DEFAULT_SUBJECT, connect_imap, process_mailbox_once_detailed, safe_logout
from bill_store import capture_overrides, ensure_bill_tables, remember_merchant_alias
from classification_service import settle_stuck_transactions, start_background_enrichment
from custom_prompts import (
    create_prompt,
    delete_prompt,
    ensure_prompt_tables,
    list_prompts,
    patch_prompt,
    set_prompt_order,
)
from category_catalog import (
    CategoryError,
    category_labels,
    category_version,
    create_category,
    delete_category,
    ensure_category_tables,
    get_catalog,
    patch_category,
    set_primary_order,
)

PROMPT_PATH = ROOT_DIR / "prompts" / "cfo_system_prompt.md"
PROFILE_REPORT_PROMPT_PATH = ROOT_DIR / "prompts" / "profile_report_prompt.md"
PROFILE_REPORT_VERSION = "profile-v5"
DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash")
DEEPSEEK_THINKING = os.environ.get("DEEPSEEK_THINKING", "disabled")
DEEPSEEK_REASONING_EFFORT = os.environ.get("DEEPSEEK_REASONING_EFFORT", "high")
CHAT_TIMEOUT_SECONDS = float(os.environ.get("CFO_CHAT_TIMEOUT_SECONDS", "45"))
PROFILE_REPORT_TIMEOUT_SECONDS = float(os.environ.get("CFO_PROFILE_REPORT_TIMEOUT_SECONDS", "90"))
MAX_CONTEXT_TRANSACTIONS = 40
SYNC_TIMEOUT_SECONDS = float(os.environ.get("CFO_MAIL_SYNC_TIMEOUT_SECONDS", "90"))
SYNC_MAX_CANDIDATES = int(os.environ.get("CFO_MAIL_SYNC_MAX_CANDIDATES", "20"))
CFO_ACCESS_TOKEN = os.environ.get("CFO_ACCESS_TOKEN", "").strip()
AUTH_COOKIE_NAME = "cfo_session"
MAX_REQUEST_BODY_BYTES = int(os.environ.get("CFO_MAX_REQUEST_BODY_BYTES", "12000"))
MAX_CHAT_MESSAGE_CHARS = int(os.environ.get("CFO_MAX_CHAT_MESSAGE_CHARS", "600"))
CLASSIFICATION_TIMEOUT_SECONDS = float(os.environ.get("CFO_CLASSIFICATION_TIMEOUT_SECONDS", "12"))
ANALYSIS_ELIGIBLE_SQL = (
    "paid_at IS NOT NULL AND amount IS NOT NULL AND amount > 0 "
    "AND merchant IS NOT NULL AND TRIM(merchant) != ''"
)
READY_FOOD_DRINK_CATEGORIES = {"food_delivery", "coffee_tea", "bakery"}
FOOD_PATTERN_RULES = (
    {
        "key": "barbecue_grill",
        "label": "烧烤/烤串线索",
        "keywords": ("烧烤", "烤串", "串串", "烤肉", "炭火烤", "烤翅", "烧肉"),
    },
    {
        "key": "fried_fast_food",
        "label": "炸物/快餐线索",
        "keywords": (
            "炸鸡", "炸串", "汉堡", "薯条", "披萨", "方便面", "泡面", "鸡柳",
            "肯德基", "麦当劳", "汉堡王", "华莱士",
        ),
    },
    {
        "key": "sweet_drinks_desserts",
        "label": "甜饮/甜品线索",
        "keywords": (
            "奶茶", "果茶", "可乐", "汽水", "冰淇淋", "甜品", "蛋糕", "沪上阿姨",
            "果呀呀", "喜茶", "奈雪", "茶百道", "古茗", "蜜雪冰城", "益禾堂", "一点点",
        ),
    },
    {
        "key": "rich_flavor_takeout",
        "label": "重口外食线索",
        "keywords": (
            "盖码饭", "拌饭", "小炒", "黄焖鸡", "辣椒炒肉", "海底捞", "湘菜",
            "炒肉", "鸡柳", "抓饭", "泡面",
        ),
    },
)

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "query_spending_summary",
            "description": (
                "按时间区间查询支出汇总统计。支持按分类、消费时段、日、周、月聚合。"
                "用于回答花了多少、哪个分类最多、对比两个时段等问题。"
                "可多次调用以对比不同时段（如本月 vs 上月）。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": {
                        "type": "string",
                        "description": "查询开始日期（含），格式 YYYY-MM-DD 或 YYYY-MM-DDTHH:MM:SS",
                    },
                    "end_date": {
                        "type": "string",
                        "description": "查询结束日期（不含），格式 YYYY-MM-DD 或 YYYY-MM-DDTHH:MM:SS",
                    },
                    "group_by": {
                        "type": "string",
                        "enum": ["category", "time_slot", "day", "week", "month"],
                        "description": "聚合维度。不传只返回总计；category 按分类拆分；time_slot 按早餐前/白天/晚间/深夜拆分；day/week/month 按日期拆分。",
                    },
                },
                "required": ["start_date", "end_date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_lifestyle_health_signals",
            "description": (
                "按时间区间提取饮食付款时段、夜间餐饮，以及烧烤、炸物快餐、甜饮甜品等消费线索。"
                "用于消费分析中推测作息与饮食习惯。返回的是账单线索而非医学结论。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": {
                        "type": "string",
                        "description": "查询开始日期（含），格式 YYYY-MM-DD 或 YYYY-MM-DDTHH:MM:SS",
                    },
                    "end_date": {
                        "type": "string",
                        "description": "查询结束日期（不含），格式 YYYY-MM-DD 或 YYYY-MM-DDTHH:MM:SS",
                    },
                },
                "required": ["start_date", "end_date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_transactions",
            "description": "搜索具体的账单记录。用于查找某笔交易、某商户的消费记录、最大单笔等需要查看原始记录的问题。",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "关键词，模糊匹配商户名(merchant)、商品说明(product)或品类描述(thing)",
                    },
                    "category": {
                        "type": "string",
                        "description": "按分类过滤，如 food_delivery、coffee_tea、transport 等",
                    },
                    "start_date": {"type": "string", "description": "开始日期（含），格式 YYYY-MM-DD"},
                    "end_date": {"type": "string", "description": "结束日期（不含），格式 YYYY-MM-DD"},
                    "min_amount": {"type": "number", "description": "最小金额（元）"},
                    "max_amount": {"type": "number", "description": "最大金额（元）"},
                    "limit": {
                        "type": "integer",
                        "description": "返回条数上限，默认 20，最大 50",
                        "default": 20,
                    },
                },
                "required": [],
            },
        },
    },
]
LOGIN_PAGE = """<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
    <meta name="theme-color" content="#0a0e0d" />
    <meta name="robots" content="noindex, nofollow" />
    <title>Jeanz CFO · 登录</title>
    <link
      rel="icon"
      href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='9' fill='%230f1413'/%3E%3Cpath d='M21.5 11.2a6.6 6.6 0 1 0 0 9.6' fill='none' stroke='%2358cda4' stroke-width='2.4' stroke-linecap='round'/%3E%3Cpath d='M9 22.6h14' stroke='%233a4844' stroke-width='1.8' stroke-linecap='round'/%3E%3C/svg%3E"
    />
    <style>
      /* 与 web_app/styles.css 使用同一套墨绿中性色 + 玉色强调色 */
      :root {
        color-scheme: dark;
        --ink-0: #070a09;
        --ink-1: #0a0e0d;
        --ink-2: #0f1413;
        --ink-3: #141a18;
        --line: #202a27;
        --line-strong: #2b3733;
        --text: #d7dedb;
        --text-strong: #f1f5f3;
        --muted: #8a9793;
        --muted-dim: #75837f;
        --jade-7: #3bb48d;
        --jade-8: #58cda4;
        --jade-line: #23453b;
        --rose-8: #e58379;
      }
      * { box-sizing: border-box; }
      body {
        margin: 0;
        min-height: 100dvh;
        display: grid;
        place-items: center;
        padding: 24px;
        background:
          radial-gradient(120% 80% at 88% -10%, rgba(46, 158, 123, 0.1), transparent 58%),
          linear-gradient(180deg, var(--ink-1), var(--ink-0));
        color: var(--text);
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
          "Hiragino Sans GB", "Microsoft YaHei", "Noto Sans SC", sans-serif;
        font-size: 14.5px;
        line-height: 1.65;
      }
      main {
        width: min(400px, 100%);
        padding: 32px;
        border: 1px solid var(--line);
        border-radius: 22px;
        background: var(--ink-2);
        box-shadow:
          0 10px 24px rgba(3, 6, 5, 0.46),
          0 56px 110px -28px rgba(3, 6, 5, 0.78),
          inset 0 1px 0 rgba(255, 255, 255, 0.04);
      }
      .mark { display: block; width: 36px; height: 36px; margin-bottom: 22px; }
      h1 {
        margin: 0 0 6px;
        color: var(--text-strong);
        font-size: 22px;
        font-weight: 600;
        letter-spacing: -0.018em;
      }
      .lede { margin: 0 0 26px; color: var(--muted); font-size: 13px; }
      label {
        display: block;
        margin-bottom: 7px;
        color: var(--muted);
        font-size: 11px;
        font-weight: 500;
        letter-spacing: 0.05em;
      }
      input {
        width: 100%;
        height: 44px;
        padding: 0 14px;
        border: 1px solid var(--line);
        border-radius: 10px;
        background: var(--ink-1);
        color: var(--text-strong);
        font: inherit;
        font-size: 16px;
        outline: 0;
        transition: border-color 200ms cubic-bezier(0.16, 1, 0.3, 1), box-shadow 200ms cubic-bezier(0.16, 1, 0.3, 1);
      }
      input:focus {
        border-color: var(--jade-line);
        box-shadow: 0 0 0 3px rgba(46, 158, 123, 0.12);
      }
      button {
        width: 100%;
        height: 44px;
        margin-top: 14px;
        border: 0;
        border-radius: 10px;
        background: var(--jade-8);
        color: var(--ink-0);
        font: inherit;
        font-size: 14px;
        font-weight: 600;
        cursor: pointer;
        transition: background 200ms cubic-bezier(0.16, 1, 0.3, 1), transform 120ms;
      }
      button:hover { background: #93e4c4; }
      button:active { transform: translateY(1px); }
      button:focus-visible {
        outline: 0;
        box-shadow: 0 0 0 2px var(--ink-2), 0 0 0 4px var(--jade-7);
      }
      .error:not(:empty) {
        margin-top: 14px;
        padding: 9px 12px;
        border: 1px solid #b8564b;
        border-radius: 10px;
        background: #241110;
        color: var(--rose-8);
        font-size: 13px;
      }
      .foot {
        margin: 22px 0 0;
        padding-top: 18px;
        border-top: 1px solid var(--line);
        color: var(--muted-dim);
        font-size: 11px;
        line-height: 1.6;
      }
      @media (prefers-reduced-motion: reduce) {
        * { transition-duration: 0.01ms !important; }
      }
    </style>
  </head>
  <body>
    <main>
      <svg class="mark" viewBox="0 0 32 32" aria-hidden="true">
        <rect x="0.75" y="0.75" width="30.5" height="30.5" rx="9" fill="#141a18" stroke="#2b3733" />
        <path d="M21.5 11.2a6.6 6.6 0 1 0 0 9.6" fill="none" stroke="#58cda4" stroke-width="2" stroke-linecap="round" />
        <path d="M9 22.6h14" stroke="#3a4844" stroke-width="1.6" stroke-linecap="round" />
      </svg>
      <h1>Jeanz CFO</h1>
      <p class="lede">这是 {owner} 的私人财务账本，输入访问口令后继续。</p>
      <form method="post" action="/api/login">
        <label for="token">访问口令</label>
        <input id="token" name="token" type="password" autocomplete="current-password" autofocus />
        <button type="submit">进入账本</button>
      </form>
      <div class="error" role="alert">{error}</div>
      <p class="foot">账本与账单截图都存放在这台机器上，不会上传到第三方服务。</p>
    </main>
  </body>
</html>"""


def parse_paid_at(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def build_payload() -> dict:
    """Use the server's active database, including tests that patch DB_PATH."""
    return build_snapshot_payload(DB_PATH)


def is_analysis_eligible(tx: dict) -> bool:
    return not correction_fields(tx)


def start_of_week(value: datetime) -> datetime:
    start = value.replace(hour=0, minute=0, second=0, microsecond=0)
    return start - timedelta(days=start.isoweekday() - 1)


def scoped_transactions(transactions: list[dict], period: str) -> list[dict]:
    dated = [
        (tx, parse_paid_at(tx.get("paid_at")))
        for tx in transactions
        if tx.get("analysis_eligible", is_analysis_eligible(tx))
    ]
    dates = sorted((paid_at for _, paid_at in dated if paid_at), reverse=True)
    if not dates:
        return []

    anchor = dates[0]
    if period == "today":
        return [tx for tx, paid_at in dated if paid_at and paid_at.date() == anchor.date()]
    if period == "week":
        start = start_of_week(anchor)
        end = start + timedelta(days=7)
        return [tx for tx, paid_at in dated if paid_at and start <= paid_at < end]
    if period == "month":
        return [tx for tx, paid_at in dated if paid_at and paid_at.year == anchor.year and paid_at.month == anchor.month]
    return [tx for tx, paid_at in dated if paid_at]


def amount_value(tx: dict) -> float:
    amount = abs(float(tx.get("amount") or 0))
    return -amount if tx.get("direction") == "inflow" else amount


def category_summary(transactions: list[dict]) -> list[dict]:
    labels = category_labels(DB_PATH)
    grouped: dict[str, dict] = {}
    for tx in transactions:
        category = tx.get("category") or "uncategorized"
        if category not in grouped:
            grouped[category] = {
                "category": category,
                "category_name": labels.get(category, category),
                "amount": 0.0,
                "count": 0,
            }
        grouped[category]["amount"] += max(amount_value(tx), 0)
        grouped[category]["count"] += 1

    return sorted(grouped.values(), key=lambda item: item["amount"], reverse=True)


def sanitized_budgets(value: object) -> dict:
    if not isinstance(value, dict):
        return {}
    result = {}
    for key in ("day", "week", "month"):
        try:
            amount = float(value.get(key, 0))
        except (TypeError, ValueError):
            amount = 0
        if amount > 0:
            result[key] = round(amount, 2)
    return result


def access_token_configured() -> bool:
    return bool(CFO_ACCESS_TOKEN)


def parse_cookies(header: str | None) -> dict[str, str]:
    if not header:
        return {}
    cookies = http.cookies.SimpleCookie()
    try:
        cookies.load(header)
    except http.cookies.CookieError:
        return {}
    return {key: morsel.value for key, morsel in cookies.items()}


def token_matches(value: str | None) -> bool:
    if not access_token_configured() or not value:
        return False
    return secrets.compare_digest(value, CFO_ACCESS_TOKEN)


def safe_error_message(prefix: str, exc: Exception) -> str:
    return f"{prefix}：{type(exc).__name__}。请检查本机服务日志或配置后重试。"


def is_public_static_path(path: str) -> bool:
    if path.startswith("/assets/"):
        return True
    return path in {
        "/",
        "/index.html",
        "/favicon.ico",
    }


def chat_context(period: str, budgets: dict | None = None) -> dict:
    payload = build_payload()
    transactions = payload.get("transactions", [])
    labels = category_labels(DB_PATH)
    selected = scoped_transactions(transactions, period)
    largest = max(selected, key=lambda tx: amount_value(tx), default=None)
    selected_total = sum(amount_value(tx) for tx in selected)
    month = scoped_transactions(transactions, "month")

    return {
        "generated_at": payload.get("generated_at"),
        "selected_period": period,
        "user_budget_config": budgets or {},
        "selected_period_stats": {
            "transaction_count": len(selected),
            "total_spend_cny": round(selected_total, 2),
            "category_summary": category_summary(selected),
            "largest_transaction": largest,
        },
        "month_stats": {
            "transaction_count": len(month),
            "total_spend_cny": round(sum(amount_value(tx) for tx in month), 2),
            "category_summary": category_summary(month),
        },
        "recent_transactions": [
            {**tx, "category_name": labels.get(tx.get("category") or "uncategorized", tx.get("category") or "未分类")}
            for tx in transactions
            if tx.get("analysis_eligible", is_analysis_eligible(tx))
        ][:MAX_CONTEXT_TRANSACTIONS],
    }


def load_system_prompt() -> str:
    if PROMPT_PATH.exists():
        prompt = PROMPT_PATH.read_text(encoding="utf-8").strip()
    else:
        prompt = "你是 {{OWNER_NAME}} 的个人财务 CFO Agent。请基于提供的账本数据，用中文给出简洁、具体、可执行的回答。"
    return prompt.replace("{{OWNER_NAME}}", OWNER_NAME)


def load_profile_report_prompt() -> str:
    if PROFILE_REPORT_PROMPT_PATH.exists():
        prompt = PROFILE_REPORT_PROMPT_PATH.read_text(encoding="utf-8").strip()
    else:
        prompt = "请根据账本聚合特征生成有趣、克制且有证据的消费人格报告，并只返回 JSON。"
    return prompt.replace("{{OWNER_NAME}}", OWNER_NAME)


def _profile_outflows() -> list[dict]:
    rows = []
    for tx in build_payload().get("transactions", []):
        if (
            not tx.get("analysis_eligible", is_analysis_eligible(tx))
            or tx.get("direction") == "inflow"
            or tx.get("status") == "failed"
        ):
            continue
        paid_at = parse_paid_at(tx.get("paid_at"))
        try:
            amount = abs(float(tx.get("amount") or 0))
        except (TypeError, ValueError):
            amount = 0
        if paid_at is None or amount <= 0:
            continue
        rows.append({**tx, "_paid_at": paid_at, "_amount": round(amount, 2)})
    return sorted(rows, key=lambda item: (item["_paid_at"], item.get("transaction_uid") or ""))


def build_lifestyle_health_features(transactions: list[dict]) -> dict:
    """把付款时间与餐饮类型组合成可核对的生活健康线索。

    这里不直接判断健康状况：付款时间未必等于进食时间，商户名和商品词也不能
    代替营养成分。函数只负责提供给模型可复核的时段、频次和关键词证据。
    """
    labels = category_labels(DB_PATH)
    slots = {
        "breakfast_reference": {"label": "早餐参考时段（5-10点）", "count": 0, "amount_cny": 0.0},
        "lunch_reference": {"label": "午餐参考时段（10-15点）", "count": 0, "amount_cny": 0.0},
        "afternoon": {"label": "下午（15-17点）", "count": 0, "amount_cny": 0.0},
        "dinner_reference": {"label": "晚餐参考时段（17-21点）", "count": 0, "amount_cny": 0.0},
        "late_night": {"label": "夜间（21-次日5点）", "count": 0, "amount_cny": 0.0},
    }
    pattern_groups = {
        rule["key"]: {
            "key": rule["key"],
            "label": rule["label"],
            "count": 0,
            "amount_cny": 0.0,
            "late_night_count": 0,
            "examples": [],
        }
        for rule in FOOD_PATTERN_RULES
    }
    food_rows = []
    late_rows = []
    pattern_matched_indexes: set[int] = set()
    active_days = set()

    for index, tx in enumerate(transactions):
        if tx.get("direction") == "inflow" or tx.get("status") == "failed":
            continue
        paid_at = tx.get("_paid_at")
        if not isinstance(paid_at, datetime):
            paid_at = parse_paid_at(tx.get("paid_at"))
        try:
            amount = abs(float(tx.get("_amount", tx.get("amount", 0)) or 0))
        except (TypeError, ValueError):
            amount = 0
        if paid_at is None or amount <= 0:
            continue

        category = tx.get("category") or "uncategorized"
        merchant = str(tx.get("merchant") or "").strip()
        product = str(tx.get("product") or tx.get("thing") or "").strip()
        searchable = " ".join(part for part in (merchant, product) if part).lower()
        matched_rules = [
            rule
            for rule in FOOD_PATTERN_RULES
            if searchable and any(keyword.lower() in searchable for keyword in rule["keywords"])
        ]
        is_ready_food_drink = category in READY_FOOD_DRINK_CATEGORIES or bool(matched_rules)
        if not is_ready_food_drink:
            continue

        hour = paid_at.hour
        if hour < 5 or hour >= 21:
            slot_key = "late_night"
        elif hour < 10:
            slot_key = "breakfast_reference"
        elif hour < 15:
            slot_key = "lunch_reference"
        elif hour < 17:
            slot_key = "afternoon"
        else:
            slot_key = "dinner_reference"

        row = {
            "paid_at": paid_at.isoformat(timespec="minutes"),
            "merchant": merchant or product or "未知商户",
            "category": labels.get(category, category),
            "amount_cny": round(amount, 2),
        }
        food_rows.append(row)
        active_days.add(paid_at.date().isoformat())
        slots[slot_key]["count"] += 1
        slots[slot_key]["amount_cny"] += amount
        if slot_key == "late_night":
            late_rows.append(row)

        for rule in matched_rules:
            group = pattern_groups[rule["key"]]
            group["count"] += 1
            group["amount_cny"] += amount
            if slot_key == "late_night":
                group["late_night_count"] += 1
            example = merchant or product
            if example and example not in group["examples"] and len(group["examples"]) < 3:
                group["examples"].append(example)
            pattern_matched_indexes.add(index)

    food_count = len(food_rows)
    food_total = round(sum(row["amount_cny"] for row in food_rows), 2)
    for slot in slots.values():
        slot["amount_cny"] = round(slot["amount_cny"], 2)
        slot["count_share_percent"] = round(slot["count"] / food_count * 100, 1) if food_count else 0

    food_type_signals = []
    for group in pattern_groups.values():
        if not group["count"]:
            continue
        group["amount_cny"] = round(group["amount_cny"], 2)
        group["count_share_percent"] = round(group["count"] / food_count * 100, 1) if food_count else 0
        food_type_signals.append(group)
    food_type_signals.sort(key=lambda item: (item["count"], item["amount_cny"]), reverse=True)

    active_day_count = len(active_days)
    if food_count >= 20 and active_day_count >= 10:
        sample_confidence = "较高"
    elif food_count >= 6 and active_day_count >= 3:
        sample_confidence = "中"
    else:
        sample_confidence = "低"

    late_count = len(late_rows)
    return {
        "ready_food_drink_payment_count": food_count,
        "ready_food_drink_total_cny": food_total,
        "active_day_count": active_day_count,
        "sample_confidence": sample_confidence,
        "payment_time_distribution": list(slots.values()),
        "late_food_drink_payments": {
            "count": late_count,
            "amount_cny": round(sum(row["amount_cny"] for row in late_rows), 2),
            "count_share_percent": round(late_count / food_count * 100, 1) if food_count else 0,
            "examples": late_rows[-4:],
        },
        "food_type_signals": food_type_signals,
        "potential_less_balanced_food_share": {
            "matched_transaction_count": len(pattern_matched_indexes),
            "count_share_percent": round(len(pattern_matched_indexes) / food_count * 100, 1) if food_count else 0,
            "note": "仅按商户/商品关键词识别烧烤、炸物快餐、甜饮甜品和重口外食线索，不等同于营养成分判断。",
        },
        "inference_limits": [
            "付款时间不等于实际进食、入睡或起床时间。",
            "外卖、商户名称和商品关键词只能提供饮食线索，不能直接定义为垃圾食品。",
        ],
    }


def profile_ledger_fingerprint(
    transactions: list[dict] | None = None, *, catalog_version: int = 1
) -> str:
    rows = transactions if transactions is not None else _profile_outflows()
    material = [
        {
            "uid": tx.get("transaction_uid") or "",
            "paid_at": tx.get("paid_at") or "",
            "amount": tx.get("_amount", 0),
            "merchant": tx.get("merchant") or "",
            "product": tx.get("product") or tx.get("thing") or "",
            "category": tx.get("category") or "uncategorized",
            "status": tx.get("status") or "",
            "classification_status": tx.get("classification_status") or "",
        }
        for tx in rows
    ]
    encoded = json.dumps(
        {"catalog_version": catalog_version, "transactions": material},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_profile_features(transactions: list[dict] | None = None) -> dict:
    rows = transactions if transactions is not None else _profile_outflows()
    labels = category_labels(DB_PATH)
    if not rows:
        return {
            "coverage": {"start_date": None, "end_date": None, "transaction_count": 0, "total_outflow_cny": 0, "active_days": 0, "active_months": 0},
            "amount_profile": {"average_cny": 0, "median_cny": 0, "max_single_cny": 0},
            "categories": [],
            "merchants": [],
            "weekday_distribution": [],
            "time_distribution": [],
            "monthly_distribution": [],
            "representative_transactions": [],
            "lifestyle_health_features": build_lifestyle_health_features([]),
        }

    category_groups: dict[str, dict] = {}
    merchant_groups: dict[str, dict] = {}
    weekday_groups = {label: {"label": label, "amount_cny": 0.0, "count": 0} for label in ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]}
    time_groups = {
        "早餐前": {"label": "早餐前（0-8点）", "amount_cny": 0.0, "count": 0},
        "白天": {"label": "白天（8-18点）", "amount_cny": 0.0, "count": 0},
        "晚间": {"label": "晚间（18-22点）", "amount_cny": 0.0, "count": 0},
        "深夜": {"label": "深夜（22-24点）", "amount_cny": 0.0, "count": 0},
    }
    monthly_groups: dict[str, dict] = {}
    active_days = set()
    amounts = []

    for tx in rows:
        paid_at = tx["_paid_at"]
        amount = tx["_amount"]
        amounts.append(amount)
        active_days.add(paid_at.date().isoformat())

        category = tx.get("category") or "uncategorized"
        category_item = category_groups.setdefault(category, {
            "key": category,
            "label": labels.get(category, category),
            "amount_cny": 0.0,
            "count": 0,
        })
        category_item["amount_cny"] += amount
        category_item["count"] += 1

        merchant = (tx.get("merchant") or tx.get("product") or tx.get("thing") or "").strip()
        if merchant:
            merchant_item = merchant_groups.setdefault(merchant, {
                "merchant": merchant,
                "category": labels.get(category, category),
                "amount_cny": 0.0,
                "count": 0,
            })
            merchant_item["amount_cny"] += amount
            merchant_item["count"] += 1

        weekday_item = weekday_groups[list(weekday_groups)[paid_at.weekday()]]
        weekday_item["amount_cny"] += amount
        weekday_item["count"] += 1

        hour = paid_at.hour
        time_key = "早餐前" if hour < 8 else "白天" if hour < 18 else "晚间" if hour < 22 else "深夜"
        time_groups[time_key]["amount_cny"] += amount
        time_groups[time_key]["count"] += 1

        month_key = paid_at.strftime("%Y-%m")
        month_item = monthly_groups.setdefault(month_key, {"month": month_key, "amount_cny": 0.0, "count": 0})
        month_item["amount_cny"] += amount
        month_item["count"] += 1

    total = round(sum(amounts), 2)

    def finalize(items: list[dict], limit: int | None = None, key: str = "amount_cny") -> list[dict]:
        ordered = sorted(items, key=lambda item: (item.get(key, 0), item.get("count", 0)), reverse=True)
        if limit is not None:
            ordered = ordered[:limit]
        for item in ordered:
            if "amount_cny" in item:
                item["amount_cny"] = round(item["amount_cny"], 2)
                item["share_percent"] = round(item["amount_cny"] / total * 100, 1) if total else 0
        return ordered

    top_merchants = finalize(list(merchant_groups.values()), 10)
    largest_rows = sorted(rows, key=lambda item: item["_amount"], reverse=True)[:6]
    representative = []
    seen_uids = set()
    for tx in largest_rows:
        uid = tx.get("transaction_uid") or f"{tx.get('paid_at')}-{tx.get('_amount')}"
        if uid in seen_uids:
            continue
        seen_uids.add(uid)
        representative.append({
            "paid_at": tx.get("paid_at"),
            "merchant": tx.get("merchant") or tx.get("product") or tx.get("thing") or "未知商户",
            "category": labels.get(tx.get("category") or "uncategorized", tx.get("category") or "未分类"),
            "amount_cny": tx["_amount"],
        })

    return {
        "coverage": {
            "start_date": rows[0]["_paid_at"].date().isoformat(),
            "end_date": rows[-1]["_paid_at"].date().isoformat(),
            "transaction_count": len(rows),
            "total_outflow_cny": total,
            "active_days": len(active_days),
            "active_months": len(monthly_groups),
        },
        "amount_profile": {
            "average_cny": round(statistics.fmean(amounts), 2),
            "median_cny": round(statistics.median(amounts), 2),
            "max_single_cny": round(max(amounts), 2),
        },
        "categories": finalize(list(category_groups.values()), 10),
        "merchants": top_merchants,
        "weekday_distribution": finalize(list(weekday_groups.values())),
        "time_distribution": finalize(list(time_groups.values())),
        "monthly_distribution": sorted(finalize(list(monthly_groups.values())), key=lambda item: item["month"])[-36:],
        "representative_transactions": representative,
        "lifestyle_health_features": build_lifestyle_health_features(rows),
    }


def _report_text(value: object, max_length: int) -> str:
    text = " ".join(str(value or "").strip().split())
    return text[:max_length]


def normalize_profile_report(raw: object, features: dict) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("报告不是 JSON 对象")
    persona = raw.get("persona") if isinstance(raw.get("persona"), dict) else {}
    title = _report_text(persona.get("title"), 24)
    subtitle = _report_text(persona.get("subtitle"), 48)
    intro = _report_text(persona.get("intro") or persona.get("summary"), 64)
    if not title or not intro:
        raise ValueError("报告缺少人格标题或短导语")

    def normalize_items(name: str, minimum: int, maximum: int, fields: tuple[tuple[str, int], ...]) -> list[dict]:
        source = raw.get(name) if isinstance(raw.get(name), list) else []
        items = []
        for source_item in source[:maximum]:
            if not isinstance(source_item, dict):
                continue
            item = {field: _report_text(source_item.get(field), length) for field, length in fields}
            if all(item.values()):
                items.append(item)
        if len(items) < minimum:
            raise ValueError(f"报告的 {name} 数量不足")
        return items

    def normalize_nested_items(source: object, minimum: int, maximum: int, fields: tuple[tuple[str, int], ...]) -> list[dict]:
        items = []
        for source_item in (source if isinstance(source, list) else [])[:maximum]:
            if not isinstance(source_item, dict):
                continue
            item = {field: _report_text(source_item.get(field), length) for field, length in fields}
            if all(item.values()):
                items.append(item)
        if len(items) < minimum:
            raise ValueError("报告的分段要点数量不足")
        return items

    traits = normalize_nested_items(
        persona.get("traits"),
        2,
        3,
        (("emoji", 4), ("label", 12), ("text", 54), ("evidence", 56)),
    )
    tags = normalize_items("tags", 3, 5, (("emoji", 4), ("label", 12), ("reason", 54), ("evidence", 56)))
    highlights = normalize_items("highlights", 3, 3, (("emoji", 4), ("value", 24), ("label", 20), ("context", 54)))

    moments_source = raw.get("moments") if isinstance(raw.get("moments"), list) else []
    moments = []
    for source_item in moments_source[:3]:
        if not isinstance(source_item, dict):
            continue
        lines = [
            _report_text(line, 56)
            for line in (source_item.get("lines") if isinstance(source_item.get("lines"), list) else [])[:2]
            if _report_text(line, 56)
        ]
        if not lines and _report_text(source_item.get("detail"), 56):
            lines = [_report_text(source_item.get("detail"), 56)]
        moment = {
            "emoji": _report_text(source_item.get("emoji"), 4),
            "title": _report_text(source_item.get("title"), 28),
            "lines": lines,
            "evidence": _report_text(source_item.get("evidence"), 64),
        }
        if moment["emoji"] and moment["title"] and moment["lines"] and moment["evidence"]:
            moments.append(moment)
    if len(moments) < 2:
        raise ValueError("报告的 moments 数量不足")

    wellbeing_source = raw.get("wellbeing") if isinstance(raw.get("wellbeing"), dict) else {}

    def normalize_confidence(value: object) -> str:
        text = _report_text(value, 8)
        if text in {"较高", "高"}:
            return "较高"
        if text in {"中", "中等"}:
            return "中"
        return "低"

    wellbeing_headline = _report_text(wellbeing_source.get("headline"), 48)
    wellbeing_summary = _report_text(wellbeing_source.get("summary"), 96)
    wellbeing_reminder = _report_text(wellbeing_source.get("reminder"), 72)
    wellbeing_disclaimer = _report_text(wellbeing_source.get("disclaimer"), 96)
    wellbeing_signals = []
    for source_item in (wellbeing_source.get("signals") if isinstance(wellbeing_source.get("signals"), list) else [])[:3]:
        if not isinstance(source_item, dict):
            continue
        signal = {
            "label": _report_text(source_item.get("label"), 16),
            "inference": _report_text(source_item.get("inference"), 64),
            "evidence": _report_text(source_item.get("evidence"), 72),
            "confidence": normalize_confidence(source_item.get("confidence")),
        }
        if signal["label"] and signal["inference"] and signal["evidence"]:
            wellbeing_signals.append(signal)
    if (
        not wellbeing_headline
        or not wellbeing_summary
        or len(wellbeing_signals) < 2
        or not wellbeing_reminder
        or not wellbeing_disclaimer
    ):
        raise ValueError("报告缺少生活健康画像")

    cfo = raw.get("cfo") if isinstance(raw.get("cfo"), dict) else {}
    headline = _report_text(cfo.get("headline") or cfo.get("verdict"), 64)
    takeaways = normalize_nested_items(
        cfo.get("takeaways"),
        2,
        2,
        (("emoji", 4), ("label", 12), ("text", 64)),
    )
    suggestions = [_report_text(item, 64) for item in (cfo.get("suggestions") or []) if _report_text(item, 64)][:2]
    if not headline or not suggestions:
        raise ValueError("报告缺少 CFO 总结")

    return {
        "persona": {"title": title, "subtitle": subtitle, "intro": intro, "traits": traits},
        "tags": tags,
        "highlights": highlights,
        "moments": moments,
        "wellbeing": {
            "headline": wellbeing_headline,
            "summary": wellbeing_summary,
            "confidence": normalize_confidence(wellbeing_source.get("confidence")),
            "signals": wellbeing_signals,
            "reminder": wellbeing_reminder,
            "disclaimer": wellbeing_disclaimer,
        },
        "cfo": {"headline": headline, "takeaways": takeaways, "suggestions": suggestions},
        "coverage": features["coverage"],
    }


def _parse_profile_json(content: str) -> dict:
    candidate = content.strip()
    if candidate.startswith("```"):
        lines = candidate.splitlines()
        candidate = "\n".join(lines[1:-1]).strip()
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start >= 0 and end > start:
            return json.loads(candidate[start:end + 1])
        raise


def call_profile_report_deepseek(features: dict) -> dict:
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        return {"ok": False, "code": "missing_api_key", "answer": "DeepSeek API Key 还没有配置，暂时无法生成账单人格报告。"}

    request_body: dict = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": load_profile_report_prompt()},
            {"role": "user", "content": "以下是本机基于全部有效支出生成的统计特征：\n" + json.dumps(features, ensure_ascii=False)},
        ],
        "temperature": 0.72,
        "response_format": {"type": "json_object"},
        "stream": False,
    }
    body = json.dumps(request_body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{DEEPSEEK_BASE_URL}/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=PROFILE_REPORT_TIMEOUT_SECONDS) as response:
            data = json.loads(response.read().decode("utf-8"))
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        report = normalize_profile_report(_parse_profile_json(content), features)
        return {"ok": True, "model": data.get("model", DEEPSEEK_MODEL), "report": report}
    except urllib.error.HTTPError as exc:
        return {"ok": False, "code": "deepseek_http_error", "answer": f"DeepSeek 返回 HTTP {exc.code}，请检查模型配置后重试。"}
    except (json.JSONDecodeError, ValueError, KeyError) as exc:
        return {"ok": False, "code": "profile_report_invalid", "answer": f"这次画像没有整理成可展示的结构：{exc}。请重新生成。"}
    except Exception as exc:
        return {"ok": False, "code": "deepseek_request_failed", "answer": safe_error_message("账单人格报告生成失败", exc)}


def latest_profile_report() -> dict:
    transactions = _profile_outflows()
    fingerprint = profile_ledger_fingerprint(transactions, catalog_version=category_version(DB_PATH))
    features = build_profile_features(transactions)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "select report_json, ledger_fingerprint, model, generated_at from profile_reports where prompt_version = ? order by generated_at desc limit 1",
            (PROFILE_REPORT_VERSION,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return {"ok": True, "has_report": False, "stale": False, "fingerprint": fingerprint, "coverage": features["coverage"]}
    try:
        report = json.loads(row["report_json"])
    except json.JSONDecodeError:
        return {"ok": True, "has_report": False, "stale": False, "fingerprint": fingerprint, "coverage": features["coverage"]}
    return {
        "ok": True,
        "has_report": True,
        "stale": row["ledger_fingerprint"] != fingerprint,
        "fingerprint": fingerprint,
        "report": report,
        "model": row["model"],
        "generated_at": row["generated_at"],
    }


def generate_profile_report(force: bool = False) -> dict:
    transactions = _profile_outflows()
    features = build_profile_features(transactions)
    fingerprint = profile_ledger_fingerprint(transactions, catalog_version=category_version(DB_PATH))
    if not transactions:
        return {"ok": False, "code": "empty_ledger", "answer": "账本里还没有可用于生成画像的支出记录。"}

    if not force:
        cached = latest_profile_report()
        if cached.get("has_report") and not cached.get("stale"):
            return {**cached, "cached": True}

    generated = call_profile_report_deepseek(features)
    if not generated.get("ok"):
        return generated

    generated_at = datetime.now().isoformat(timespec="seconds")
    report = {**generated["report"], "generated_at": generated_at}
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            """
            insert into profile_reports (ledger_fingerprint, prompt_version, report_json, model, generated_at)
            values (?, ?, ?, ?, ?)
            on conflict(ledger_fingerprint, prompt_version) do update set
                report_json = excluded.report_json,
                model = excluded.model,
                generated_at = excluded.generated_at
            """,
            (fingerprint, PROFILE_REPORT_VERSION, json.dumps(report, ensure_ascii=False), generated.get("model"), generated_at),
        )
        conn.commit()
    finally:
        conn.close()
    return {
        "ok": True,
        "has_report": True,
        "stale": False,
        "cached": False,
        "fingerprint": fingerprint,
        "report": report,
        "model": generated.get("model"),
        "generated_at": generated_at,
    }


PERIOD_LABELS = {
    "today": "今日",
    "week": "本周",
    "month": "本月",
    "last_month": "上月",
    "year": "今年",
    "all": "全部",
}


def parse_custom_range(custom_range: dict | None) -> dict | None:
    """
    前端传来的是闭区间日期（YYYY-MM-DD），这里转成和其余周期一致的半开区间
    [start 00:00, end+1 天 00:00)。任何解析不出来或首尾颠倒的输入都返回 None，
    交给调用方退回「全部」口径，而不是抛错让整轮对话失败。
    """
    if not isinstance(custom_range, dict):
        return None
    try:
        start = date.fromisoformat(str(custom_range.get("start", "")).strip()[:10])
        end = date.fromisoformat(str(custom_range.get("end", "")).strip()[:10])
    except ValueError:
        return None
    if end < start:
        return None
    return {
        "start": datetime.combine(start, datetime.min.time()).isoformat(timespec="seconds"),
        "end": datetime.combine(end + timedelta(days=1), datetime.min.time()).isoformat(timespec="seconds"),
    }


def custom_period_label(custom_range: dict | None) -> str:
    """把闭区间日期读成中文；首尾同一天就只说那一天。"""
    if not isinstance(custom_range, dict):
        return "全部"
    try:
        start = date.fromisoformat(str(custom_range.get("start", "")).strip()[:10])
        end = date.fromisoformat(str(custom_range.get("end", "")).strip()[:10])
    except ValueError:
        return "全部"
    if start > end:
        start, end = end, start
    if start == end:
        return f"{start.month}月{start.day}日"
    return f"{start.month}月{start.day}日–{end.month}月{end.day}日"


def compute_period_date_range(period: str, custom_range: dict | None = None) -> dict | None:
    if period == "custom":
        return parse_custom_range(custom_range)
    now = datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "today":
        return {
            "start": today_start.isoformat(timespec="seconds"),
            "end": (today_start + timedelta(days=1)).isoformat(timespec="seconds"),
        }
    if period == "week":
        week_start = today_start - timedelta(days=today_start.isoweekday() - 1)
        return {
            "start": week_start.isoformat(timespec="seconds"),
            "end": (week_start + timedelta(days=7)).isoformat(timespec="seconds"),
        }
    if period == "month":
        month_start = today_start.replace(day=1)
        next_month = (month_start + timedelta(days=32)).replace(day=1)
        return {
            "start": month_start.isoformat(timespec="seconds"),
            "end": next_month.isoformat(timespec="seconds"),
        }
    if period == "last_month":
        this_month_start = today_start.replace(day=1)
        last_month_start = (this_month_start - timedelta(days=1)).replace(day=1)
        return {
            "start": last_month_start.isoformat(timespec="seconds"),
            "end": this_month_start.isoformat(timespec="seconds"),
        }
    if period == "year":
        year_start = today_start.replace(month=1, day=1)
        next_year = year_start.replace(year=year_start.year + 1)
        return {
            "start": year_start.isoformat(timespec="seconds"),
            "end": next_year.isoformat(timespec="seconds"),
        }
    return None  # "all" 或未知，表示不限时间范围


def get_orientation_context(period: str, budgets: dict | None = None, custom_range: dict | None = None) -> dict:
    import sqlite3 as _sqlite3
    try:
        conn = _sqlite3.connect(str(DB_PATH))
        conn.row_factory = _sqlite3.Row
        row = conn.execute(
            "SELECT MIN(paid_at) as earliest, MAX(paid_at) as latest, COUNT(*) as total "
            f"FROM transactions WHERE {ANALYSIS_ELIGIBLE_SQL} AND COALESCE(status, '') != 'failed'"
        ).fetchone()
        catalog_names = category_labels(DB_PATH, enabled_only=True)
        cats = [
            {"id": r[0], "name": catalog_names.get(r[0], r[0])}
            for r in conn.execute(
                "SELECT DISTINCT category FROM transactions WHERE category IS NOT NULL ORDER BY category"
            ).fetchall()
            if r[0] in catalog_names
        ]
        conn.close()
        data_range = {
            "earliest_transaction": row["earliest"],
            "latest_transaction": row["latest"],
            "total_transaction_count": row["total"],
        }
    except Exception:
        data_range = {}
        cats = []

    context: dict = {
        "today": datetime.now().date().isoformat(),
        "ui_selected_period": period,
        "current_period_label": (
            custom_period_label(custom_range) if period == "custom" else PERIOD_LABELS.get(period, "全部")
        ),
        "user_budget_config": budgets or {},
        "data_range": data_range,
        "available_categories": cats,
    }

    # 预注入选中时段的权威汇总：常见问题模型可直接引用、无需再调工具（省一轮 API）。
    # 复用 _tool_query_spending_summary 保证口径与工具完全一致。
    period_range = compute_period_date_range(period, custom_range)
    if period_range is None:  # "all"、非法自定义区间：回退到最早交易 ~ 明日零点
        tomorrow = (datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
                    + timedelta(days=1)).isoformat(timespec="seconds")
        period_range = {
            "start": data_range.get("earliest_transaction") or "1970-01-01T00:00:00",
            "end": tomorrow,
        }
    context["current_period_date_range"] = period_range

    query_args = {"start_date": period_range["start"], "end_date": period_range["end"]}
    summary = _tool_query_spending_summary(query_args)
    grouped = _tool_query_spending_summary({**query_args, "group_by": "category"})
    time_grouped = _tool_query_spending_summary({**query_args, "group_by": "time_slot"})
    lifestyle_health = _tool_query_lifestyle_health_signals(query_args)
    if "error" not in summary:
        top_categories = grouped.get("rows", [])[:5] if "error" not in grouped else []
        time_distribution = time_grouped.get("rows", []) if "error" not in time_grouped else []
        context["current_period_summary"] = {
            **summary.get("summary", {}),
            "top_categories": top_categories,
            "time_distribution": time_distribution,
            "lifestyle_health_features": lifestyle_health.get("features", {}) if "error" not in lifestyle_health else {},
        }
    return context


def _tool_query_spending_summary(args: dict) -> dict:
    import sqlite3 as _sqlite3
    start_date = args.get("start_date", "")
    end_date = args.get("end_date", "")
    group_by = args.get("group_by")
    if not start_date or not end_date:
        return {"error": "start_date 和 end_date 为必填项"}
    try:
        conn = _sqlite3.connect(str(DB_PATH))
        conn.row_factory = _sqlite3.Row
        base_where = (
            f"{ANALYSIS_ELIGIBLE_SQL} AND paid_at >= ? AND paid_at < ? "
            "AND COALESCE(status, '') != 'failed'"
        )
        params: list = [start_date, end_date]

        # 权威区间总计：所有分组/无分组场景共用，避免模型自行求和
        total_row = conn.execute(
            f"SELECT "
            f"SUM(CASE WHEN direction='outflow' THEN 1 ELSE 0 END) as out_cnt, "
            f"SUM(CASE WHEN direction='inflow' THEN 1 ELSE 0 END) as in_cnt, "
            f"COUNT(*) as total_cnt, "
            f"SUM(CASE WHEN direction='outflow' THEN amount ELSE 0 END) as total_out, "
            f"SUM(CASE WHEN direction='inflow' THEN amount ELSE 0 END) as total_in, "
            f"MAX(CASE WHEN direction='outflow' THEN amount ELSE NULL END) as max_out "
            f"FROM transactions WHERE {base_where}",
            params,
        ).fetchone()
        authoritative_total = {
            "outflow_transaction_count": total_row["out_cnt"] or 0,
            "inflow_transaction_count": total_row["in_cnt"] or 0,
            "total_transaction_count": total_row["total_cnt"] or 0,
            "total_outflow_cny": round(total_row["total_out"] or 0, 2),
            "total_inflow_cny": round(total_row["total_in"] or 0, 2),
            "max_single_outflow_cny": round(total_row["max_out"] or 0, 2),
        }

        if group_by == "category":
            group_expr = "category"
            select_col = "category"
        elif group_by == "time_slot":
            time_slot_expr = (
                "CASE "
                "WHEN strftime('%H', paid_at) IS NULL THEN '时间未知' "
                "WHEN CAST(strftime('%H', paid_at) AS INTEGER) < 8 THEN '早餐前（0-8点）' "
                "WHEN CAST(strftime('%H', paid_at) AS INTEGER) < 18 THEN '白天（8-18点）' "
                "WHEN CAST(strftime('%H', paid_at) AS INTEGER) < 22 THEN '晚间（18-22点）' "
                "ELSE '深夜（22-24点）' END"
            )
            group_expr = time_slot_expr
            select_col = time_slot_expr
        elif group_by == "day":
            group_expr = "date(paid_at)"
            select_col = "date(paid_at)"
        elif group_by == "week":
            group_expr = "strftime('%Y-W%W', paid_at)"
            select_col = "strftime('%Y-W%W', paid_at)"
        elif group_by == "month":
            group_expr = "strftime('%Y-%m', paid_at)"
            select_col = "strftime('%Y-%m', paid_at)"
        else:
            conn.close()
            return {
                "period": {"start": start_date, "end": end_date},
                "summary": authoritative_total,
                "note": "消费口径请使用 outflow_transaction_count 与 total_outflow_cny，请直接引用勿自行加总。",
            }

        rows = conn.execute(
            f"SELECT {select_col} as grp, "
            f"SUM(CASE WHEN direction='outflow' THEN 1 ELSE 0 END) as out_cnt, "
            f"SUM(CASE WHEN direction='outflow' THEN amount ELSE 0 END) as out, "
            f"SUM(CASE WHEN direction='inflow' THEN amount ELSE 0 END) as infl, "
            f"MAX(CASE WHEN direction='outflow' THEN amount ELSE NULL END) as max_out "
            f"FROM transactions WHERE {base_where} GROUP BY {group_expr} ORDER BY out DESC",
            params,
        ).fetchall()
        conn.close()
        result_rows = [
            {
                "group": r["grp"],
                "outflow_count": r["out_cnt"] or 0,
                "outflow_cny": round(r["out"] or 0, 2),
                "inflow_cny": round(r["infl"] or 0, 2),
                "max_single_cny": round(r["max_out"] or 0, 2),
            }
            for r in rows
        ]
        if group_by == "category":
            labels = category_labels(DB_PATH)
            for item in result_rows:
                item["group_name"] = labels.get(item["group"] or "uncategorized", item["group"] or "未分类")
        return {
            "period": {"start": start_date, "end": end_date},
            "group_by": group_by,
            "total": authoritative_total,
            "rows": result_rows,
            "note": "区间总计请引用顶层 total（total_outflow_cny / outflow_transaction_count），勿对 rows 自行加总。",
        }
    except Exception as exc:
        return {"error": str(exc)}


def _tool_query_lifestyle_health_signals(args: dict) -> dict:
    import sqlite3 as _sqlite3
    start_date = args.get("start_date", "")
    end_date = args.get("end_date", "")
    if not start_date or not end_date:
        return {"error": "start_date 和 end_date 为必填项"}
    try:
        conn = _sqlite3.connect(str(DB_PATH))
        conn.row_factory = _sqlite3.Row
        rows = conn.execute(
            "SELECT paid_at, merchant, product, thing, category, amount, direction, status "
            "FROM transactions "
            "WHERE paid_at >= ? AND paid_at < ? "
            f"AND {ANALYSIS_ELIGIBLE_SQL} "
            "AND direction = 'outflow' AND COALESCE(status, '') != 'failed' "
            "ORDER BY paid_at ASC",
            [start_date, end_date],
        ).fetchall()
        conn.close()
        labels = category_labels(DB_PATH)
        return {
            "period": {"start": start_date, "end": end_date},
            "features": build_lifestyle_health_features([dict(row) for row in rows]),
            "note": "这是基于付款时间和消费类型的生活健康线索，不是医学诊断；推断时必须同时展示证据与可信度。",
        }
    except Exception as exc:
        return {"error": str(exc)}


def _tool_search_transactions(args: dict) -> dict:
    import sqlite3 as _sqlite3
    keyword = args.get("keyword")
    category = args.get("category")
    start_date = args.get("start_date")
    end_date = args.get("end_date")
    min_amount = args.get("min_amount")
    max_amount = args.get("max_amount")
    limit = min(int(args.get("limit", 20)), 50)
    try:
        labels = category_labels(DB_PATH)
        conn = _sqlite3.connect(str(DB_PATH))
        conn.row_factory = _sqlite3.Row
        conditions = [ANALYSIS_ELIGIBLE_SQL, "COALESCE(status, '') != 'failed'"]
        params: list = []
        if start_date:
            conditions.append("paid_at >= ?")
            params.append(start_date)
        if end_date:
            conditions.append("paid_at < ?")
            params.append(end_date)
        if category:
            conditions.append("category = ?")
            params.append(category)
        if min_amount is not None:
            conditions.append("amount >= ?")
            params.append(min_amount)
        if max_amount is not None:
            conditions.append("amount <= ?")
            params.append(max_amount)
        if keyword:
            conditions.append("(merchant LIKE ? OR product LIKE ? OR thing LIKE ?)")
            pattern = f"%{keyword}%"
            params.extend([pattern, pattern, pattern])
        where_clause = " AND ".join(conditions)
        rows = conn.execute(
            f"SELECT paid_at, merchant, thing, category, amount, direction, status, platform, product "
            f"FROM transactions WHERE {where_clause} ORDER BY paid_at DESC LIMIT ?",
            params + [limit],
        ).fetchall()
        conn.close()
        return {
            "transaction_count": len(rows),
            "transactions": [
                {
                    "paid_at": r["paid_at"],
                    "merchant": r["merchant"],
                    "thing": r["thing"],
                    "category": r["category"],
                    "category_name": labels.get(r["category"] or "uncategorized", r["category"] or "未分类"),
                    "amount_cny": r["amount"],
                    "direction": r["direction"],
                    "status": r["status"],
                    "platform": r["platform"],
                    "product": r["product"],
                }
                for r in rows
            ],
        }
    except Exception as exc:
        return {"error": str(exc)}


def execute_tool(name: str, args: dict) -> dict:
    if name == "query_spending_summary":
        return _tool_query_spending_summary(args)
    if name == "query_lifestyle_health_signals":
        return _tool_query_lifestyle_health_signals(args)
    if name == "search_transactions":
        return _tool_search_transactions(args)
    return {"error": f"未知工具：{name}"}


def _demo_lifestyle_tip(features: dict) -> str:
    """用演示账本的组合线索给出一条克制提醒，不把推测写成诊断。"""
    late = features.get("late_food_drink_payments") or {}
    if late.get("count", 0) > 0:
        return (
            f"🌿 生活提醒：本期有 {late['count']} 笔餐饮或饮品付款落在夜间；"
            "若多为即时消费，可以尝试把最后一餐或最后一杯提前。"
        )

    signals = features.get("food_type_signals") or []
    if not signals:
        return ""
    signal = signals[0]
    return f"🌿 生活提醒：账单里有 {signal['count']} 笔{signal['label']}；下次点单时给清淡、少糖或少油的选项留一个位置。"


def demo_answer(message: str, period: str, custom_range: dict | None = None) -> dict:
    """Demo 模式且未配置 LLM Key 时的兜底回答：直接查询演示账本并模板化输出。"""
    period_range = compute_period_date_range(period, custom_range)
    if period_range is None:
        tomorrow = (datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
                    + timedelta(days=1)).isoformat(timespec="seconds")
        period_range = {"start": "1970-01-01T00:00:00", "end": tomorrow}
    query_args = {"start_date": period_range["start"], "end_date": period_range["end"]}
    summary = _tool_query_spending_summary(query_args).get("summary", {})
    grouped = _tool_query_spending_summary({**query_args, "group_by": "category"})
    lifestyle_health = _tool_query_lifestyle_health_signals(query_args)
    label = custom_period_label(custom_range) if period == "custom" else PERIOD_LABELS.get(period, "全部")

    lines = []
    count = summary.get("outflow_transaction_count", 0)
    total = summary.get("total_outflow_cny", 0)
    lines.append(f"{label}共消费 {count} 笔，合计 ¥{total:.2f}。")

    rows = grouped.get("rows", []) if "error" not in grouped else []
    tops = [
        f"{row.get('group_name') or row['group'] or '未分类'} ¥{row['outflow_cny']:.2f}（{row['outflow_count']} 笔）"
        for row in rows[:3]
        if row.get("outflow_cny")
    ]
    if tops:
        lines.append("支出最高的场景：" + "、".join(tops) + "。")

    max_out = summary.get("max_single_outflow_cny", 0)
    if max_out:
        hits = _tool_search_transactions({**query_args, "min_amount": max_out, "limit": 1}).get("transactions", [])
        if hits:
            tx = hits[0]
            paid_day = (tx.get("paid_at") or "")[:10]
            lines.append(f"最大单笔：¥{max_out:.2f}，{tx.get('merchant') or tx.get('thing') or '未知商户'}（{paid_day}）。")

    if any(keyword in message for keyword in ("分析", "消费情况", "消费习惯", "消费健康", "生活")):
        lifestyle_tip = _demo_lifestyle_tip(lifestyle_health.get("features", {})) if "error" not in lifestyle_health else ""
        if lifestyle_tip:
            lines.append(lifestyle_tip)

    lines.append("——以上是 Demo 模式的内置分析（当前展示的均为虚构数据）。配置 DEEPSEEK_API_KEY 后，可用自然语言向真实 LLM 追问任何账本问题。")
    return {
        "ok": True,
        "model": "demo",
        "answer": "\n\n".join(lines),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }


def call_deepseek(
    message: str,
    period: str,
    history: list[dict],
    budgets: dict | None = None,
    custom_range: dict | None = None,
) -> dict:
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        if DEMO_MODE:
            return demo_answer(message, period, custom_range)
        return {
            "ok": False,
            "code": "missing_api_key",
            "answer": "DeepSeek API Key 还没有配置。请在启动 Web 服务前设置 DEEPSEEK_API_KEY，然后刷新页面重试。",
        }

    orientation = get_orientation_context(period, budgets, custom_range)
    compact_history = [
        {"role": item.get("role"), "content": str(item.get("content", ""))[:1200]}
        for item in history[-8:]
        if item.get("role") in {"user", "assistant"} and item.get("content")
    ]
    messages: list[dict] = [
        {"role": "system", "content": load_system_prompt()},
        {
            "role": "user",
            "content": "账本元信息（用于确定查询范围，具体数据请通过工具获取）：\n"
                       + json.dumps(orientation, ensure_ascii=False, indent=2),
        },
        *compact_history,
        {"role": "user", "content": message},
    ]

    import time as _time
    t_total_start = _time.monotonic()
    MAX_TOOL_ROUNDS = 5
    for round_idx in range(MAX_TOOL_ROUNDS):
        request_body: dict = {
            "model": DEEPSEEK_MODEL,
            "messages": messages,
            "temperature": 0.35,
            "tools": TOOL_DEFINITIONS,
            "stream": False,
        }
        if DEEPSEEK_THINKING == "enabled":
            request_body["thinking"] = {"type": DEEPSEEK_THINKING}
            request_body["reasoning_effort"] = DEEPSEEK_REASONING_EFFORT

        body = json.dumps(request_body, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            f"{DEEPSEEK_BASE_URL}/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        t_api_start = _time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=CHAT_TIMEOUT_SECONDS) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            return {
                "ok": False,
                "code": "deepseek_http_error",
                "answer": f"DeepSeek 返回 HTTP {exc.code}，请检查模型名、API Key 或账户状态。",
                "detail": error_body[:1200],
            }
        except Exception as exc:
            return {
                "ok": False,
                "code": "deepseek_request_failed",
                "answer": f"DeepSeek 请求失败：{exc}",
            }
        t_api_elapsed = _time.monotonic() - t_api_start

        choice = data.get("choices", [{}])[0]
        finish_reason = choice.get("finish_reason", "stop")
        assistant_message = choice.get("message", {})
        usage = data.get("usage", {})
        if DEBUG_TRACE:
            print(
                f"[CFO] round={round_idx+1} api={t_api_elapsed:.2f}s "
                f"finish={finish_reason} "
                f"prompt_tokens={usage.get('prompt_tokens','-')} "
                f"completion_tokens={usage.get('completion_tokens','-')}",
                flush=True,
            )
        messages.append(assistant_message)

        if finish_reason != "tool_calls":
            answer = (assistant_message.get("content") or "").strip()
            if DEBUG_TRACE:
                print(f"[CFO] total={_time.monotonic()-t_total_start:.2f}s rounds={round_idx+1}", flush=True)
            return {
                "ok": True,
                "model": data.get("model", DEEPSEEK_MODEL),
                "answer": answer or "DeepSeek 没有返回可展示内容。",
                "generated_at": datetime.now().isoformat(timespec="seconds"),
            }

        for tc in assistant_message.get("tool_calls", []):
            tool_name = tc.get("function", {}).get("name", "")
            try:
                tool_args = json.loads(tc.get("function", {}).get("arguments", "{}"))
            except json.JSONDecodeError:
                tool_args = {}
            t_tool_start = _time.monotonic()
            result = execute_tool(tool_name, tool_args)
            if DEBUG_TRACE:
                print(f"[CFO] tool={tool_name} args={tool_args} took={_time.monotonic()-t_tool_start:.3f}s", flush=True)
            messages.append({
                "role": "tool",
                "tool_call_id": tc.get("id", ""),
                "content": json.dumps(result, ensure_ascii=False),
            })

    return {
        "ok": False,
        "code": "tool_loop_exceeded",
        "answer": "工具调用轮次超限，请简化问题后重试。",
    }


def transaction_count() -> int:
    return len(build_payload().get("transactions", []))


def _safe_capture_image_path(image_path: str | None) -> Path | None:
    if not image_path:
        return None
    candidate = Path(image_path).expanduser()
    if not candidate.is_absolute():
        candidate = ROOT_DIR / candidate
    try:
        resolved = candidate.resolve(strict=True)
        data_root = (ROOT_DIR / "data").resolve(strict=True)
        resolved.relative_to(data_root)
    except (FileNotFoundError, OSError, ValueError):
        return None
    return resolved if resolved.is_file() else None


def transaction_evidence(transaction_uid: str) -> dict | None:
    if not transaction_uid:
        return None
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            """
            select t.*, c.ocr_text, c.image_path, c.captured_at
            from transactions t
            left join raw_bill_captures c on c.capture_hash = t.raw_capture_hash
            where t.transaction_uid = ?
            limit 1
            """,
            (transaction_uid,),
        ).fetchone()
        edited_fields = sorted(capture_overrides(conn, row["raw_capture_hash"])) if row and row["raw_capture_hash"] else []
    finally:
        conn.close()
    if row is None:
        return None

    record = dict(row)
    raw_warnings = record.pop("parse_warnings", "[]")
    try:
        warnings = json.loads(raw_warnings or "[]")
    except json.JSONDecodeError:
        warnings = [str(raw_warnings)] if raw_warnings else []
    if not isinstance(warnings, list):
        warnings = [str(warnings)]

    image_path = _safe_capture_image_path(record.pop("image_path", None))
    capture_ocr_text = record.pop("ocr_text", None)
    transaction_raw_text = record.pop("raw_text", "")
    ocr_text = capture_ocr_text or transaction_raw_text
    record.pop("raw_capture_hash", None)
    missing = correction_fields(record)
    record["correction_fields"] = missing
    record["analysis_eligible"] = not missing
    active_warnings = [
        warning
        for warning in warnings
        if not any(
            warning in {f"missing_{field}", f"invalid_{field}"} and field not in missing
            for field in ("amount", "paid_at", "merchant")
        )
    ]
    return {
        "ok": True,
        "transaction": record,
        "ocr_text": ocr_text,
        "parse_warnings": active_warnings,
        "original_parse_warnings": warnings,
        "edited_fields": edited_fields,
        "editable": not DEMO_MODE,
        "image_url": f"/api/transaction-evidence-image?uid={quote(transaction_uid)}" if image_path else None,
    }


# ---------------------------- 解析字段人工校正 ----------------------------
# OCR 会认错，规则会解析歪。这里给一条兜底通道：人工改过的字段写进
# transaction_overrides，重新解析同一张截图时由 apply_persisted_classification 回放，
# 所以校正不会被下一次同步冲掉。

MAX_EDIT_AMOUNT = 1_000_000.0
PAYMENT_APP_LABELS = {"wechat": "微信", "alipay": "支付宝"}


class FieldError(ValueError):
    """字段没通过校验，message 直接给用户看。"""


def _edit_text(value: object, label: str, limit: int) -> str | None:
    text = " ".join(str(value or "").split())
    if len(text) > limit:
        raise FieldError(f"{label}最多 {limit} 个字符。")
    return text or None


def _edit_amount(value: object) -> float:
    try:
        amount = float(str(value).strip())
    except (TypeError, ValueError):
        raise FieldError("金额要填一个数字。") from None
    if not amount == amount or amount in (float("inf"), float("-inf")):
        raise FieldError("金额要填一个数字。")
    if amount <= 0:
        raise FieldError("金额要大于 0。")
    if amount > MAX_EDIT_AMOUNT:
        raise FieldError(f"金额看起来不对，上限是 {MAX_EDIT_AMOUNT:,.0f}。")
    return round(amount, 2)


def _edit_paid_at(value: object) -> str:
    text = str(value or "").strip().replace("/", "-").replace(" ", "T")
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        raise FieldError("交易时间格式不对，应该像 2026-08-10T13:01。") from None
    if not 2000 <= moment.year <= 2100:
        raise FieldError("交易时间超出了合理范围。")
    return moment.replace(microsecond=0).isoformat(timespec="seconds")


def _edit_category(value: object) -> str:
    category = str(value or "").strip()
    if category not in category_labels(DB_PATH):
        raise FieldError("这个分类不在可选范围里。")
    return category


def _edit_payment_app(value: object) -> str | None:
    app = str(value or "").strip().lower()
    if not app:
        return None
    if app not in PAYMENT_APP_LABELS:
        raise FieldError("支付渠道只能是微信或支付宝。")
    return app


def _edit_card_last4(value: object) -> str | None:
    digits = str(value or "").strip()
    if not digits:
        return None
    if not (len(digits) == 4 and digits.isdigit()):
        raise FieldError("卡片尾号要填 4 位数字。")
    return digits


EDITABLE_FIELDS = {
    "amount": _edit_amount,
    "paid_at": _edit_paid_at,
    "merchant": lambda v: _edit_text(v, "商户", 60),
    "thing": lambda v: _edit_text(v, "消费内容", 40),
    "category": _edit_category,
    "payment_app": _edit_payment_app,
    "payment_method": lambda v: _edit_text(v, "支付方式", 30),
    "card_last4": _edit_card_last4,
}


def _same_field(new_value: object, stored: object) -> bool:
    """空串和 NULL 视为同一件事；金额按分比较，避免 10 和 10.0 被当成改动。"""
    if new_value is None and (stored is None or stored == ""):
        return True
    if isinstance(new_value, float) or isinstance(stored, float):
        try:
            return round(float(new_value), 2) == round(float(stored), 2)
        except (TypeError, ValueError):
            return False
    return str(new_value) == str(stored or "")


def update_transaction_fields(transaction_uid: str, fields: dict) -> dict:
    if DEMO_MODE:
        return {"ok": False, "code": "demo_readonly", "answer": "演示模式下账本是只读的，不能修改交易。"}
    if not transaction_uid:
        return {"ok": False, "code": "missing_uid", "answer": "缺少交易编号。"}
    if not isinstance(fields, dict) or not fields:
        return {"ok": False, "code": "empty_payload", "answer": "没有需要保存的改动。"}

    unknown = set(fields) - set(EDITABLE_FIELDS)
    if unknown:
        return {"ok": False, "code": "unknown_field", "answer": f"不支持修改这些字段：{'、'.join(sorted(unknown))}。"}

    cleaned: dict[str, object] = {}
    try:
        for name, raw in fields.items():
            cleaned[name] = EDITABLE_FIELDS[name](raw)
    except FieldError as exc:
        return {"ok": False, "code": "invalid_field", "answer": str(exc)}

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "select * from transactions where transaction_uid = ? limit 1",
            (transaction_uid,),
        ).fetchone()
        if row is None:
            return {"ok": False, "code": "not_found", "answer": "找不到这笔交易。"}
        capture_hash = row["raw_capture_hash"]

        # 只记录真正被改动的字段。表单每次都会把 8 个字段整份提交，
        # 全部当成「人工校正」会让「已校正」标记失去意义。
        changed = {name: value for name, value in cleaned.items() if not _same_field(value, row[name])}
        reviewed_at = datetime.now().isoformat(timespec="seconds")

        # 打开证据面板对着截图按了保存，本身就是一次人工核对——哪怕一个字都没改。
        # 解析置信低不等于解析错了，「看过，没问题」必须能让这笔不再挂在待核实。
        if not changed:
            conn.execute(
                "update transactions set reviewed_at = ? where transaction_uid = ?",
                (reviewed_at, transaction_uid),
            )
            conn.commit()
            evidence = transaction_evidence(transaction_uid)
            evidence["saved_fields"] = []
            evidence["persisted"] = bool(capture_hash)
            return evidence

        if "category" in changed and changed["category"] not in category_labels(DB_PATH, enabled_only=True):
            return {"ok": False, "code": "disabled_category", "answer": "这个分类已停用，不能再用于新的校正。"}

        assignments = dict(changed)
        assignments["reviewed_at"] = reviewed_at
        # 只有分类被改动时才动分类元数据，改个金额不该把分类来源写成人工。
        # 人工定了商户，就不再排队让模型补抽商户，免得被模型结果盖掉
        if "merchant" in changed:
            assignments.update({"merchant_quality": "ok", "extraction_status": "done"})
        if "category" in changed:
            assignments.update({
                "classification_source": "manual_override",
                "classification_confidence": 1.0,
                "classification_status": "resolved",
                "classification_reason": "capture_override",
            })

        columns = ", ".join(f"{name} = ?" for name in assignments)
        conn.execute(
            f"update transactions set {columns} where transaction_uid = ?",
            (*assignments.values(), transaction_uid),
        )

        # 同一家店下次再来，直接用人工改过的名字。平台主体、打码名不会被记成别名。
        if "merchant" in changed:
            remember_merchant_alias(conn, alias=row["merchant"], merchant=changed["merchant"])

        # 持久层：截图重新解析时靠它回放。没有截图的记录（手工/演示）只改行。
        if capture_hash:
            now = datetime.now().isoformat(timespec="seconds")
            for name, value in changed.items():
                conn.execute(
                    """
                    insert into transaction_overrides (raw_capture_hash, field, value, created_at)
                    values (?, ?, ?, ?)
                    on conflict(raw_capture_hash, field) do update set value = excluded.value, created_at = excluded.created_at
                    """,
                    (capture_hash, name, None if value is None else str(value), now),
                )
        conn.commit()
    finally:
        conn.close()

    evidence = transaction_evidence(transaction_uid)
    if evidence is None:
        return {"ok": False, "code": "not_found", "answer": "保存后读不到这笔交易了。"}
    evidence["saved_fields"] = sorted(changed)
    evidence["persisted"] = bool(capture_hash)
    return evidence


def _safe_related_ocr_path(image_path: str | None) -> Path | None:
    image = _safe_capture_image_path(image_path)
    if image is None:
        return None
    candidate = ROOT_DIR / "data" / "ocr_texts" / f"{image.stem}.txt"
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to((ROOT_DIR / "data").resolve(strict=True))
    except (FileNotFoundError, OSError, ValueError):
        return None
    return resolved if resolved.is_file() else None


def delete_transaction(transaction_uid: str) -> dict:
    if DEMO_MODE:
        return {"ok": False, "code": "demo_readonly", "answer": "演示模式下账本是只读的，不能删除交易。"}
    if not transaction_uid:
        return {"ok": False, "code": "missing_uid", "answer": "缺少交易编号。"}

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    deleted_files: list[str] = []
    try:
        row = conn.execute(
            """
            select t.raw_capture_hash, c.image_path
            from transactions t
            left join raw_bill_captures c on c.capture_hash = t.raw_capture_hash
            where t.transaction_uid = ? limit 1
            """,
            (transaction_uid,),
        ).fetchone()
        if row is None:
            return {"ok": False, "code": "not_found", "answer": "找不到这笔交易。"}

        capture_hash = row["raw_capture_hash"]
        image_path = row["image_path"]
        conn.execute("delete from transactions where transaction_uid = ?", (transaction_uid,))
        capture_is_orphaned = bool(capture_hash) and not conn.execute(
            "select 1 from transactions where raw_capture_hash = ? limit 1", (capture_hash,)
        ).fetchone()
        if capture_is_orphaned:
            # 先删本地工件；若文件系统拒绝操作，数据库事务不会提交，记录仍可追溯。
            for artifact in (_safe_capture_image_path(image_path), _safe_related_ocr_path(image_path)):
                if artifact is not None:
                    artifact.unlink()
                    deleted_files.append(str(artifact))
            conn.execute("delete from transaction_overrides where raw_capture_hash = ?", (capture_hash,))
            conn.execute("delete from raw_bill_captures where capture_hash = ?", (capture_hash,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return {
        "ok": True,
        "deleted_uid": transaction_uid,
        "deleted_capture": bool(capture_is_orphaned),
        "deleted_file_count": len(deleted_files),
    }


def transaction_evidence_image_path(transaction_uid: str) -> Path | None:
    if not transaction_uid:
        return None
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute(
            """
            select c.image_path
            from transactions t
            join raw_bill_captures c on c.capture_hash = t.raw_capture_hash
            where t.transaction_uid = ?
            limit 1
            """,
            (transaction_uid,),
        ).fetchone()
    finally:
        conn.close()
    return _safe_capture_image_path(row[0] if row else None)


def ensure_database_schema() -> None:
    conn = sqlite3.connect(DB_PATH)
    try:
        ensure_bill_tables(conn)
        ensure_category_tables(conn)
        ensure_prompt_tables(conn)
        conn.execute(
            """
            create table if not exists profile_reports (
                id integer primary key autoincrement,
                ledger_fingerprint text not null,
                prompt_version text not null,
                report_json text not null,
                model text,
                generated_at text not null,
                unique (ledger_fingerprint, prompt_version)
            )
            """
        )
        # AI 推荐提问已改为前端内置问题库，这张缓存表不再有人读写。
        conn.execute("drop table if exists suggested_questions")
        conn.commit()
    finally:
        conn.close()


def trigger_background_classification() -> bool:
    if DEMO_MODE:
        return False
    return start_background_enrichment(
        DB_PATH,
        api_key=os.environ.get("DEEPSEEK_API_KEY"),
        base_url=DEEPSEEK_BASE_URL,
        model=DEEPSEEK_MODEL,
        timeout=CLASSIFICATION_TIMEOUT_SECONDS,
    )


def sync_mail_once() -> dict:
    host = os.environ.get("CFO_MAIL_IMAP_HOST", "imap.qq.com")
    user = os.environ.get("CFO_MAIL_USER")
    password = os.environ.get("CFO_MAIL_PASSWORD")
    mailbox = os.environ.get("CFO_MAIL_MAILBOX", "INBOX")
    subject = os.environ.get("CFO_MAIL_SUBJECT", DEFAULT_SUBJECT)
    max_candidates = SYNC_MAX_CANDIDATES

    if not user or not password:
        return {
            "ok": False,
            "code": "missing_mail_credentials",
            "answer": "邮箱同步缺少配置。请在 cfo_agent_poc/.env 中设置 CFO_MAIL_USER 和 CFO_MAIL_PASSWORD。",
        }

    started_at = datetime.now()
    before_payload = build_payload()
    before_uids = {tx.get("transaction_uid") for tx in before_payload.get("transactions", [])}
    before_count = len(before_uids)
    client = None
    try:
        client = connect_imap(host, user, password, mailbox, timeout=SYNC_TIMEOUT_SECONDS)
        detail = process_mailbox_once_detailed(
            client,
            subject=subject,
            mark_seen=True,
            include_seen=False,
            max_candidates=max_candidates,
        )
    finally:
        safe_logout(client)

    after_payload = build_payload()
    after_transactions = after_payload.get("transactions", [])
    after_by_uid = {tx.get("transaction_uid"): tx for tx in after_transactions}
    new_transactions = [tx for tx in after_transactions if tx.get("transaction_uid") not in before_uids]
    annotated_items = []
    for item in detail["items"][-12:]:
        stored = after_by_uid.get(item.get("transaction_uid"), item)
        missing = stored.get("correction_fields") or correction_fields(stored)
        annotated_items.append({
            **item,
            "correction_fields": missing,
            "analysis_eligible": not missing,
        })
    after_count = len(after_transactions)
    classification_started = trigger_background_classification()
    finished_at = datetime.now()
    return {
        "ok": True,
        "started_at": started_at.isoformat(timespec="seconds"),
        "finished_at": finished_at.isoformat(timespec="seconds"),
        "duration_seconds": round((finished_at - started_at).total_seconds(), 2),
        "host": host,
        "mailbox": mailbox,
        "subject": subject,
        "max_candidates": max_candidates,
        "candidate_count": detail["candidate_count"],
        "matched_messages": detail["matched_messages"],
        "processed_attachments": detail["processed_attachments"],
        "transactions_before": before_count,
        "transactions_after": after_count,
        "new_transactions": len(new_transactions),
        "new_correction_count": sum(1 for tx in new_transactions if not tx.get("analysis_eligible", True)),
        "correction_pending_count": after_payload.get("correction_pending_count", 0),
        "classification_started": classification_started,
        "items": annotated_items,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }


class CFORequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(FRONTEND_DIR), **kwargs)

    def end_headers(self) -> None:
        path = urlparse(self.path).path
        if path.startswith("/assets/"):
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")
        else:
            self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def is_authenticated(self) -> bool:
        if DEMO_MODE:
            return True
        auth_header = self.headers.get("Authorization", "")
        if auth_header.startswith("Bearer ") and token_matches(auth_header.removeprefix("Bearer ").strip()):
            return True
        if token_matches(self.headers.get("X-CFO-Access-Token")):
            return True
        cookies = parse_cookies(self.headers.get("Cookie"))
        return token_matches(cookies.get(AUTH_COOKIE_NAME))

    def send_login_page(self, error: str = "", status: HTTPStatus = HTTPStatus.OK) -> None:
        body = (
            LOGIN_PAGE
            .replace("{owner}", html.escape(OWNER_NAME))
            .replace("{error}", html.escape(error))
        ).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def redirect_to_root(self) -> None:
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", "/")
        self.end_headers()

    def set_auth_cookie(self) -> None:
        secure_flag = "Secure; " if self.headers.get("X-Forwarded-Proto", "").lower() == "https" else ""
        self.send_header(
            "Set-Cookie",
            f"{AUTH_COOKIE_NAME}={CFO_ACCESS_TOKEN}; HttpOnly; {secure_flag}SameSite=Lax; Path=/; Max-Age=2592000",
        )

    def clear_auth_cookie(self) -> None:
        self.send_header("Set-Cookie", f"{AUTH_COOKIE_NAME}=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0")

    def send_unauthorized_json(self) -> None:
        self.send_json({"ok": False, "code": "unauthorized", "answer": "请先登录后再访问。"}, status=HTTPStatus.UNAUTHORIZED)

    def send_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length > MAX_REQUEST_BODY_BYTES:
            raise CategoryError("请求内容过长。", code="payload_too_large", status=413)
        payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        if not isinstance(payload, dict):
            raise CategoryError("请求格式必须是 JSON 对象。", code="invalid_json")
        return payload

    def category_error(self, error: CategoryError) -> None:
        self.send_json(
            {"ok": False, "code": error.code, "answer": str(error), **error.detail},
            status=HTTPStatus(error.status),
        )

    def allow_category_write(self, subject: str = "分类") -> bool:
        if DEMO_MODE:
            self.send_json(
                {"ok": False, "code": "demo_readonly", "answer": f"演示模式只能查看{subject}，不能修改。"},
                status=HTTPStatus.FORBIDDEN,
            )
            return False
        if not access_token_configured() or not self.is_authenticated():
            self.send_unauthorized_json()
            return False
        return True

    def do_GET(self) -> None:
        parsed_url = urlparse(self.path)
        path = parsed_url.path
        if path == "/health":
            self.send_json({"ok": True})
            return

        if path == "/login":
            self.send_login_page()
            return

        if not access_token_configured() and not DEMO_MODE:
            self.send_login_page("服务端还没有配置 CFO_ACCESS_TOKEN，暂时不能公网访问。", status=HTTPStatus.SERVICE_UNAVAILABLE)
            return

        if not self.is_authenticated():
            if path == "/" or path.endswith(".html"):
                self.send_login_page()
            else:
                self.send_unauthorized_json()
            return

        if path == "/data.json":
            try:
                self.send_json(build_payload())
            except Exception as exc:
                self.send_json({"ok": False, "error": safe_error_message("账本读取失败", exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        if path == "/api/categories":
            try:
                self.send_json(get_catalog(DB_PATH, demo=DEMO_MODE))
            except Exception as exc:
                self.send_json({"ok": False, "answer": safe_error_message("分类目录读取失败", exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        if path == "/api/custom-prompts":
            try:
                self.send_json(list_prompts(DB_PATH))
            except Exception as exc:
                self.send_json({"ok": False, "answer": safe_error_message("我的常问读取失败", exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        if path == "/api/profile-report":
            try:
                self.send_json(latest_profile_report())
            except Exception as exc:
                self.send_json({"ok": False, "answer": safe_error_message("账单人格报告读取失败", exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        if path == "/api/transaction-evidence":
            transaction_uid = parse_qs(parsed_url.query).get("uid", [""])[0]
            try:
                payload = transaction_evidence(transaction_uid)
                if payload is None:
                    self.send_json({"ok": False, "answer": "没有找到这笔交易。"}, status=HTTPStatus.NOT_FOUND)
                else:
                    self.send_json(payload)
            except Exception as exc:
                self.send_json({"ok": False, "answer": safe_error_message("交易证据读取失败", exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        if path == "/api/transaction-evidence-image":
            transaction_uid = parse_qs(parsed_url.query).get("uid", [""])[0]
            image_path = transaction_evidence_image_path(transaction_uid)
            if image_path is None:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            content = image_path.read_bytes()
            mime_type = mimetypes.guess_type(image_path.name)[0] or "application/octet-stream"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", mime_type)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return

        if not is_public_static_path(path):
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        super().do_GET()

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/login":
            if not access_token_configured():
                self.send_login_page("服务端还没有配置 CFO_ACCESS_TOKEN，暂时不能公网访问。", status=HTTPStatus.SERVICE_UNAVAILABLE)
                return
            length = min(int(self.headers.get("Content-Length", "0")), MAX_REQUEST_BODY_BYTES)
            raw_body = self.rfile.read(length).decode("utf-8", errors="replace")
            submitted = ""
            for piece in raw_body.split("&"):
                key, _, value = piece.partition("=")
                if key == "token":
                    from urllib.parse import unquote_plus

                    submitted = unquote_plus(value)
                    break
            if token_matches(submitted):
                self.send_response(HTTPStatus.SEE_OTHER)
                self.send_header("Location", "/")
                self.set_auth_cookie()
                self.end_headers()
                return
            self.send_login_page("访问口令不正确。", status=HTTPStatus.UNAUTHORIZED)
            return

        if path == "/api/logout":
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", "/login")
            self.clear_auth_cookie()
            self.end_headers()
            return

        if not DEMO_MODE and (not access_token_configured() or not self.is_authenticated()):
            self.send_unauthorized_json()
            return

        if path == "/api/categories":
            if DEMO_MODE:
                self.send_json({"ok": False, "code": "demo_readonly", "answer": "演示模式只能查看分类，不能新建。"}, status=HTTPStatus.FORBIDDEN)
                return
            try:
                item = create_category(DB_PATH, self.read_json_body())
                self.send_json({"ok": True, "category": item}, status=HTTPStatus.CREATED)
            except CategoryError as exc:
                self.category_error(exc)
            except json.JSONDecodeError:
                self.send_json({"ok": False, "answer": "请求格式不是合法 JSON。"}, status=HTTPStatus.BAD_REQUEST)
            except Exception as exc:
                self.send_json({"ok": False, "answer": safe_error_message("新建分类失败", exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        if path == "/api/custom-prompts":
            if not self.allow_category_write("我的常问"):
                return
            try:
                item = create_prompt(DB_PATH, self.read_json_body())
                self.send_json({"ok": True, "prompt": item}, status=HTTPStatus.CREATED)
            except CategoryError as exc:
                self.category_error(exc)
            except json.JSONDecodeError:
                self.send_json({"ok": False, "answer": "请求格式不是合法 JSON。"}, status=HTTPStatus.BAD_REQUEST)
            except Exception as exc:
                self.send_json({"ok": False, "answer": safe_error_message("新建常问失败", exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        if path == "/api/sync-mail":
            try:
                self.send_json(sync_mail_once())
            except Exception as exc:
                self.send_json({
                    "ok": False,
                    "code": "mail_sync_failed",
                    "answer": safe_error_message("邮箱同步失败", exc),
                }, status=HTTPStatus.INTERNAL_SERVER_ERROR)
            return


        if path == "/api/transaction-edit":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length > MAX_REQUEST_BODY_BYTES:
                    self.send_json({"ok": False, "answer": "请求内容过长。"}, status=HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
                    return
                payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
                result = update_transaction_fields(str(payload.get("uid", "")).strip(), payload.get("fields"))
                status = HTTPStatus.OK if result.get("ok") else HTTPStatus.BAD_REQUEST
                if result.get("code") == "not_found":
                    status = HTTPStatus.NOT_FOUND
                elif result.get("code") == "demo_readonly":
                    status = HTTPStatus.FORBIDDEN
                self.send_json(result, status=status)
            except json.JSONDecodeError:
                self.send_json({"ok": False, "answer": "请求格式不是合法 JSON。"}, status=HTTPStatus.BAD_REQUEST)
            except Exception as exc:
                self.send_json({"ok": False, "answer": safe_error_message("保存交易改动失败", exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        if path == "/api/transaction-delete":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length > MAX_REQUEST_BODY_BYTES:
                    self.send_json({"ok": False, "answer": "请求内容过长。"}, status=HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
                    return
                payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
                result = delete_transaction(str(payload.get("uid", "")).strip())
                status = HTTPStatus.OK if result.get("ok") else HTTPStatus.BAD_REQUEST
                if result.get("code") == "not_found":
                    status = HTTPStatus.NOT_FOUND
                elif result.get("code") == "demo_readonly":
                    status = HTTPStatus.FORBIDDEN
                self.send_json(result, status=status)
            except json.JSONDecodeError:
                self.send_json({"ok": False, "answer": "请求格式不是合法 JSON。"}, status=HTTPStatus.BAD_REQUEST)
            except Exception as exc:
                self.send_json({"ok": False, "answer": safe_error_message("删除交易失败", exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        if path == "/api/profile-report":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length > MAX_REQUEST_BODY_BYTES:
                    self.send_json({"ok": False, "answer": "请求内容过长。"}, status=HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
                    return
                raw_body = self.rfile.read(length).decode("utf-8")
                payload = json.loads(raw_body or "{}")
                result = generate_profile_report(force=bool(payload.get("force")))
                self.send_json(result, status=HTTPStatus.OK if result.get("ok") else HTTPStatus.BAD_GATEWAY)
            except json.JSONDecodeError:
                self.send_json({"ok": False, "answer": "请求格式不是合法 JSON。"}, status=HTTPStatus.BAD_REQUEST)
            except Exception as exc:
                self.send_json({"ok": False, "answer": safe_error_message("账单人格报告生成失败", exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        if path != "/api/chat":
            self.send_json({"error": "not found"}, status=HTTPStatus.NOT_FOUND)
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length > MAX_REQUEST_BODY_BYTES:
                self.send_json({"ok": False, "answer": "请求内容过长，请缩短问题后重试。"}, status=HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
                return
            raw_body = self.rfile.read(length).decode("utf-8")
            payload = json.loads(raw_body or "{}")
            message = str(payload.get("message", "")).strip()
            period = str(payload.get("period", "today"))
            # 自定义区间的闭区间日期，校验交给 parse_custom_range，非法值退回「全部」。
            custom_range = {
                "start": str(payload.get("start_date", ""))[:32],
                "end": str(payload.get("end_date", ""))[:32],
            }
            history = payload.get("history") if isinstance(payload.get("history"), list) else []
            budgets = sanitized_budgets(payload.get("budgets"))
            if not message:
                self.send_json({"ok": False, "answer": "请输入问题。"}, status=HTTPStatus.BAD_REQUEST)
                return
            if len(message) > MAX_CHAT_MESSAGE_CHARS:
                self.send_json({"ok": False, "answer": f"问题太长了，请控制在 {MAX_CHAT_MESSAGE_CHARS} 个字以内。"}, status=HTTPStatus.BAD_REQUEST)
                return
            self.send_json(call_deepseek(message, period, history, budgets, custom_range))
        except json.JSONDecodeError:
            self.send_json({"ok": False, "answer": "请求格式不是合法 JSON。"}, status=HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self.send_json({"ok": False, "answer": safe_error_message("对话请求失败", exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_PATCH(self) -> None:
        path = urlparse(self.path).path
        prompt_prefix = "/api/custom-prompts/"
        if path.startswith(prompt_prefix) and path[len(prompt_prefix):]:
            if not self.allow_category_write("我的常问"):
                return
            try:
                item = patch_prompt(DB_PATH, path[len(prompt_prefix):], self.read_json_body())
                self.send_json({"ok": True, "prompt": item})
            except CategoryError as exc:
                self.category_error(exc)
            except json.JSONDecodeError:
                self.send_json({"ok": False, "answer": "请求格式不是合法 JSON。"}, status=HTTPStatus.BAD_REQUEST)
            except Exception as exc:
                self.send_json({"ok": False, "answer": safe_error_message("保存常问失败", exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        prefix = "/api/categories/"
        if not path.startswith(prefix) or not path[len(prefix):]:
            self.send_json({"error": "not found"}, status=HTTPStatus.NOT_FOUND)
            return
        if not self.allow_category_write():
            return
        try:
            item = patch_category(DB_PATH, path[len(prefix):], self.read_json_body())
            self.send_json({"ok": True, "category": item})
        except CategoryError as exc:
            self.category_error(exc)
        except json.JSONDecodeError:
            self.send_json({"ok": False, "answer": "请求格式不是合法 JSON。"}, status=HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self.send_json({"ok": False, "answer": safe_error_message("保存分类失败", exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_PUT(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/custom-prompts/order":
            if not self.allow_category_write("我的常问"):
                return
            try:
                items = set_prompt_order(DB_PATH, self.read_json_body().get("prompt_ids"))
                self.send_json({"ok": True, "prompts": items})
            except CategoryError as exc:
                self.category_error(exc)
            except json.JSONDecodeError:
                self.send_json({"ok": False, "answer": "请求格式不是合法 JSON。"}, status=HTTPStatus.BAD_REQUEST)
            except Exception as exc:
                self.send_json({"ok": False, "answer": safe_error_message("保存常问顺序失败", exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        if path != "/api/categories/primary-order":
            self.send_json({"error": "not found"}, status=HTTPStatus.NOT_FOUND)
            return
        if not self.allow_category_write():
            return
        try:
            payload = self.read_json_body()
            items = set_primary_order(DB_PATH, payload.get("category_ids"))
            self.send_json({"ok": True, "categories": items})
        except CategoryError as exc:
            self.category_error(exc)
        except json.JSONDecodeError:
            self.send_json({"ok": False, "answer": "请求格式不是合法 JSON。"}, status=HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self.send_json({"ok": False, "answer": safe_error_message("保存常用顺序失败", exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_DELETE(self) -> None:
        path = urlparse(self.path).path
        prompt_prefix = "/api/custom-prompts/"
        if path.startswith(prompt_prefix) and path[len(prompt_prefix):]:
            if not self.allow_category_write("我的常问"):
                return
            try:
                self.send_json(delete_prompt(DB_PATH, path[len(prompt_prefix):]))
            except CategoryError as exc:
                self.category_error(exc)
            except Exception as exc:
                self.send_json({"ok": False, "answer": safe_error_message("删除常问失败", exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        prefix = "/api/categories/"
        if not path.startswith(prefix) or not path[len(prefix):]:
            self.send_json({"error": "not found"}, status=HTTPStatus.NOT_FOUND)
            return
        if not self.allow_category_write():
            return
        try:
            self.send_json(delete_category(DB_PATH, path[len(prefix):]))
        except CategoryError as exc:
            self.category_error(exc)
        except Exception as exc:
            self.send_json({"ok": False, "answer": safe_error_message("删除分类失败", exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve Jeanz CFO web app with live SQLite-backed data.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8091)
    args = parser.parse_args()

    ensure_database_schema()
    # 上次进程可能是在分类跑到一半时挂的，那些行会一直停在 pending。
    # 启动时先收一次尾，保证界面上不会留着「识别中」。
    if not DEMO_MODE:
        try:
            settled = settle_stuck_transactions(DB_PATH)
            if settled:
                print(f"[CFO] 结案 {settled} 笔滞留的待分类交易")
        except Exception as exc:  # 清扫失败不该挡住启动
            print(f"[CFO] 待分类交易清扫跳过：{type(exc).__name__}")
    trigger_background_classification()
    server = ThreadingHTTPServer((args.host, args.port), CFORequestHandler)
    print(f"Serving CFO web app at http://{args.host}:{args.port}/")
    server.serve_forever()


if __name__ == "__main__":
    main()
