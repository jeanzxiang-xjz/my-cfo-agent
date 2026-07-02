from __future__ import annotations

import argparse
import html
import http.cookies
import json
import os
import secrets
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from generate_snapshot import build_payload


WEB_DIR = Path(__file__).resolve().parent
ROOT_DIR = WEB_DIR.parents[0]
FRONTEND_DIR = WEB_DIR / "dist" if (WEB_DIR / "dist" / "index.html").exists() else WEB_DIR
DB_PATH = ROOT_DIR / "data" / "cfo.sqlite"


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

from mail_sync import DEFAULT_SUBJECT, connect_imap, process_mailbox_once_detailed, safe_logout

PROMPT_PATH = ROOT_DIR / "prompts" / "cfo_system_prompt.md"
DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash")
DEEPSEEK_THINKING = os.environ.get("DEEPSEEK_THINKING", "disabled")
DEEPSEEK_REASONING_EFFORT = os.environ.get("DEEPSEEK_REASONING_EFFORT", "high")
CHAT_TIMEOUT_SECONDS = float(os.environ.get("CFO_CHAT_TIMEOUT_SECONDS", "45"))
MAX_CONTEXT_TRANSACTIONS = 40
SYNC_TIMEOUT_SECONDS = float(os.environ.get("CFO_MAIL_SYNC_TIMEOUT_SECONDS", "90"))
SYNC_MAX_CANDIDATES = int(os.environ.get("CFO_MAIL_SYNC_MAX_CANDIDATES", "20"))
CFO_ACCESS_TOKEN = os.environ.get("CFO_ACCESS_TOKEN", "").strip()
AUTH_COOKIE_NAME = "cfo_session"
MAX_REQUEST_BODY_BYTES = int(os.environ.get("CFO_MAX_REQUEST_BODY_BYTES", "12000"))
MAX_CHAT_MESSAGE_CHARS = int(os.environ.get("CFO_MAX_CHAT_MESSAGE_CHARS", "600"))

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "query_spending_summary",
            "description": (
                "按时间区间查询支出汇总统计。支持按分类、日、周、月聚合。"
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
                        "enum": ["category", "day", "week", "month"],
                        "description": "聚合维度。不传只返回总计；category 按分类拆分；day/week/month 按时间段拆分。",
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
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Jeanz CFO Brain 登录</title>
    <style>
      :root {
        color-scheme: dark;
        --bg: #06100d;
        --panel: #0d1b17;
        --line: rgba(80, 255, 218, 0.22);
        --text: #effffb;
        --muted: #8cab9f;
        --accent: #48f1ce;
        --danger: #ff7b72;
      }
      * { box-sizing: border-box; }
      body {
        margin: 0;
        min-height: 100dvh;
        display: grid;
        place-items: center;
        padding: 24px;
        background:
          radial-gradient(circle at 70% 20%, rgba(72, 241, 206, 0.14), transparent 32%),
          linear-gradient(145deg, #020504, var(--bg));
        color: var(--text);
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      }
      main {
        width: min(440px, 100%);
        border: 1px solid var(--line);
        background: linear-gradient(180deg, rgba(18, 40, 34, 0.96), rgba(7, 17, 14, 0.96));
        border-radius: 8px;
        padding: 28px;
        box-shadow: 0 24px 80px rgba(0, 0, 0, 0.42);
      }
      .mark {
        width: 44px;
        height: 44px;
        display: grid;
        place-items: center;
        border: 1px solid rgba(72, 241, 206, 0.42);
        border-radius: 8px;
        color: var(--accent);
        font-weight: 800;
        margin-bottom: 18px;
      }
      h1 { margin: 0 0 8px; font-size: 28px; letter-spacing: 0; }
      p { margin: 0 0 24px; color: var(--muted); line-height: 1.7; }
      label { display: block; color: var(--muted); font-size: 13px; margin-bottom: 8px; }
      input {
        width: 100%;
        height: 48px;
        border: 1px solid var(--line);
        border-radius: 8px;
        background: #06110e;
        color: var(--text);
        padding: 0 14px;
        font-size: 16px;
        outline: none;
      }
      input:focus { border-color: rgba(72, 241, 206, 0.72); }
      button {
        width: 100%;
        height: 48px;
        margin-top: 16px;
        border: 0;
        border-radius: 8px;
        background: var(--accent);
        color: #02110d;
        font-weight: 800;
        font-size: 16px;
        cursor: pointer;
      }
      .error {
        min-height: 22px;
        margin-top: 14px;
        color: var(--danger);
        font-size: 14px;
      }
    </style>
  </head>
  <body>
    <main>
      <div class="mark">C</div>
      <h1>Jeanz CFO Brain</h1>
      <p>这是 Jeanz 的私人财务账本。请输入访问口令后继续。</p>
      <form method="post" action="/api/login">
        <label for="token">访问口令</label>
        <input id="token" name="token" type="password" autocomplete="current-password" autofocus />
        <button type="submit">进入账本</button>
      </form>
      <div class="error">{error}</div>
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


def start_of_week(value: datetime) -> datetime:
    start = value.replace(hour=0, minute=0, second=0, microsecond=0)
    return start - timedelta(days=start.isoweekday() - 1)


def scoped_transactions(transactions: list[dict], period: str) -> list[dict]:
    dated = [(tx, parse_paid_at(tx.get("paid_at"))) for tx in transactions]
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
    return transactions


def amount_value(tx: dict) -> float:
    amount = abs(float(tx.get("amount") or 0))
    return -amount if tx.get("direction") == "inflow" else amount


def category_summary(transactions: list[dict]) -> list[dict]:
    grouped: dict[str, dict] = {}
    for tx in transactions:
        category = tx.get("category") or "uncategorized"
        if category not in grouped:
            grouped[category] = {"category": category, "amount": 0.0, "count": 0}
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
        "recent_transactions": transactions[:MAX_CONTEXT_TRANSACTIONS],
    }


def load_system_prompt() -> str:
    if PROMPT_PATH.exists():
        return PROMPT_PATH.read_text(encoding="utf-8").strip()
    return "你是 Jeanz 的个人财务 CFO Agent。请基于提供的账本数据，用中文给出简洁、具体、可执行的回答。"


PERIOD_LABELS = {
    "today": "今日",
    "week": "本周",
    "month": "本月",
    "last_month": "上月",
    "year": "今年",
    "all": "全部",
}


def compute_period_date_range(period: str) -> dict | None:
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


def get_orientation_context(period: str, budgets: dict | None = None) -> dict:
    import sqlite3 as _sqlite3
    try:
        conn = _sqlite3.connect(str(DB_PATH))
        conn.row_factory = _sqlite3.Row
        row = conn.execute(
            "SELECT MIN(paid_at) as earliest, MAX(paid_at) as latest, COUNT(*) as total "
            "FROM transactions WHERE paid_at IS NOT NULL AND COALESCE(status, '') != 'failed'"
        ).fetchone()
        cats = [r[0] for r in conn.execute(
            "SELECT DISTINCT category FROM transactions WHERE category IS NOT NULL ORDER BY category"
        ).fetchall()]
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
        "current_period_label": PERIOD_LABELS.get(period, "全部"),
        "user_budget_config": budgets or {},
        "data_range": data_range,
        "available_categories": cats,
    }

    # 预注入选中时段的权威汇总：常见问题模型可直接引用、无需再调工具（省一轮 API）。
    # 复用 _tool_query_spending_summary 保证口径与工具完全一致。
    period_range = compute_period_date_range(period)
    if period_range is None:  # "all"：回退到最早交易 ~ 明日零点
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
    if "error" not in summary:
        top_categories = grouped.get("rows", [])[:5] if "error" not in grouped else []
        context["current_period_summary"] = {
            **summary.get("summary", {}),
            "top_categories": top_categories,
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
        base_where = "paid_at >= ? AND paid_at < ? AND COALESCE(status, '') != 'failed'"
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
        return {
            "period": {"start": start_date, "end": end_date},
            "group_by": group_by,
            "total": authoritative_total,
            "rows": [
                {
                    "group": r["grp"],
                    "outflow_count": r["out_cnt"] or 0,
                    "outflow_cny": round(r["out"] or 0, 2),
                    "inflow_cny": round(r["infl"] or 0, 2),
                    "max_single_cny": round(r["max_out"] or 0, 2),
                }
                for r in rows
            ],
            "note": "区间总计请引用顶层 total（total_outflow_cny / outflow_transaction_count），勿对 rows 自行加总。",
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
        conn = _sqlite3.connect(str(DB_PATH))
        conn.row_factory = _sqlite3.Row
        conditions = ["COALESCE(status, '') != 'failed'"]
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
    if name == "search_transactions":
        return _tool_search_transactions(args)
    return {"error": f"未知工具：{name}"}


def call_deepseek(message: str, period: str, history: list[dict], budgets: dict | None = None) -> dict:
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        return {
            "ok": False,
            "code": "missing_api_key",
            "answer": "DeepSeek API Key 还没有配置。请在启动 Web 服务前设置 DEEPSEEK_API_KEY，然后刷新页面重试。",
        }

    orientation = get_orientation_context(period, budgets)
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
    before_count = transaction_count()
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

    after_count = transaction_count()
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
        "new_transactions": max(after_count - before_count, 0),
        "items": detail["items"][-12:],
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
        auth_header = self.headers.get("Authorization", "")
        if auth_header.startswith("Bearer ") and token_matches(auth_header.removeprefix("Bearer ").strip()):
            return True
        if token_matches(self.headers.get("X-CFO-Access-Token")):
            return True
        cookies = parse_cookies(self.headers.get("Cookie"))
        return token_matches(cookies.get(AUTH_COOKIE_NAME))

    def send_login_page(self, error: str = "", status: HTTPStatus = HTTPStatus.OK) -> None:
        body = LOGIN_PAGE.replace("{error}", html.escape(error)).encode("utf-8")
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

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/health":
            self.send_json({"ok": True})
            return

        if path == "/login":
            self.send_login_page()
            return

        if not access_token_configured():
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

        if not access_token_configured() or not self.is_authenticated():
            self.send_unauthorized_json()
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
            history = payload.get("history") if isinstance(payload.get("history"), list) else []
            budgets = sanitized_budgets(payload.get("budgets"))
            if not message:
                self.send_json({"ok": False, "answer": "请输入问题。"}, status=HTTPStatus.BAD_REQUEST)
                return
            if len(message) > MAX_CHAT_MESSAGE_CHARS:
                self.send_json({"ok": False, "answer": f"问题太长了，请控制在 {MAX_CHAT_MESSAGE_CHARS} 个字以内。"}, status=HTTPStatus.BAD_REQUEST)
                return
            self.send_json(call_deepseek(message, period, history, budgets))
        except json.JSONDecodeError:
            self.send_json({"ok": False, "answer": "请求格式不是合法 JSON。"}, status=HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self.send_json({"ok": False, "answer": safe_error_message("对话请求失败", exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve Jeanz CFO web app with live SQLite-backed data.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8091)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), CFORequestHandler)
    print(f"Serving CFO web app at http://{args.host}:{args.port}/")
    server.serve_forever()


if __name__ == "__main__":
    main()
