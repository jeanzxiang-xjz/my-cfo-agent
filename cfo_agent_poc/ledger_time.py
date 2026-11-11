"""
账本时区：系统里所有不带时区的时间字符串（paid_at、统计区间边界、记录时间戳等）
都按这个时区的墙上时间理解。

支付宝/微信截图上显示的是北京时间，所以默认 Asia/Shanghai，可用 CFO_LEDGER_TZ 改；
与服务器进程、浏览器所在时区都无关——这样截图时间、Chat 的今日/本周/本月、
前端 Dashboard 永远是同一个"今天"。
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone, tzinfo
from functools import lru_cache

DEFAULT_LEDGER_TZ = "Asia/Shanghai"


@lru_cache(maxsize=1)
def _resolve() -> tuple[str, tzinfo]:
    # 惰性解析：server.py 启动时先读 .env，第一次用到时才取环境变量
    name = (os.environ.get("CFO_LEDGER_TZ") or "").strip() or DEFAULT_LEDGER_TZ
    try:
        from zoneinfo import ZoneInfo

        return name, ZoneInfo(name)
    except Exception:
        pass
    if name != DEFAULT_LEDGER_TZ:
        print(f"[ledger_time] CFO_LEDGER_TZ={name!r} 无法识别，退回 {DEFAULT_LEDGER_TZ}", file=sys.stderr)
    try:
        from zoneinfo import ZoneInfo

        return DEFAULT_LEDGER_TZ, ZoneInfo(DEFAULT_LEDGER_TZ)
    except Exception:
        # 系统缺 tzdata：北京时间没有夏令时，固定 +08:00 与之等价，不让服务起不来
        return DEFAULT_LEDGER_TZ, timezone(timedelta(hours=8), DEFAULT_LEDGER_TZ)


def reset_ledger_tz_cache() -> None:
    """测试或运行期改了 CFO_LEDGER_TZ 后调用，重新解析。"""
    _resolve.cache_clear()


def ledger_tz_name() -> str:
    return _resolve()[0]


def ledger_now() -> datetime:
    """账本时区的当前墙上时间（naive），与 paid_at 同口径，可直接比较、拼 SQL 区间。"""
    return datetime.now(_resolve()[1]).replace(tzinfo=None, microsecond=0)


def ledger_now_iso() -> str:
    return ledger_now().isoformat(timespec="seconds")
