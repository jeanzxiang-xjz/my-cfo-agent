"""账本上下文：一次请求只服务一个账本。

多用户共用一个进程以后，「当前是谁的账本」不能再是模块级全局变量。每个账本是一个
目录，布局和 ``cfo_agent_poc/`` 一样（``data/cfo.sqlite``、``data/evidence`` ……），
所以库里存的 ``data/...`` 相对路径直接相对账本根目录解析，老账本整目录拷过来就能用。

Web 层在认证之后用 ``use_ledger()`` 绑定账本，业务代码用 ``current_ledger()`` 取。
没绑定就直接报错，不回退到默认库——宁可请求失败，也不能读到别人的账。
"""

from __future__ import annotations

import contextlib
import contextvars
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path


DEFAULT_DISPLAY_NAME = "用户"


@dataclass(frozen=True)
class Ledger:
    root: Path
    display_name: str = DEFAULT_DISPLAY_NAME
    # 演示库等场景下数据库不在 root/data/cfo.sqlite，允许单独指定
    db_file: Path | None = field(default=None)

    @property
    def data_dir(self) -> Path:
        return self.root / "data"

    @property
    def db_path(self) -> Path:
        return self.db_file if self.db_file is not None else self.data_dir / "cfo.sqlite"

    @property
    def ocr_text_dir(self) -> Path:
        return self.data_dir / "ocr_texts"

    @property
    def evidence_dir(self) -> Path:
        return self.data_dir / "evidence"


class LedgerNotBound(RuntimeError):
    pass


_CURRENT: contextvars.ContextVar[Ledger | None] = contextvars.ContextVar("cfo_ledger", default=None)


def current_ledger() -> Ledger:
    ledger = _CURRENT.get()
    if ledger is None:
        raise LedgerNotBound("当前请求没有绑定账本")
    return ledger


@contextlib.contextmanager
def use_ledger(ledger: Ledger) -> Iterator[Ledger]:
    token = _CURRENT.set(ledger)
    try:
        yield ledger
    finally:
        _CURRENT.reset(token)
