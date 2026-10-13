"""截图直传：落盘 → 排队 → OCR + 解析入账。

快捷指令（或网页）把截图 POST 上来，服务端先把图片按内容哈希存进账本目录
``data/captures/``，再在 ``capture_jobs`` 表里登记一个任务，最后交给后台线程池
跑 OCR 和 ``store_bill_capture``。图片先落盘再处理，所以进程重启也不丢：启动时把
没跑完的任务捡回来继续。

同一张图重复上传是幂等的（同一个哈希只有一个任务）；失败会自动重试几次。
"""

from __future__ import annotations

import hashlib
import sqlite3
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable

import process_bill_image
from tenancy import Ledger


MAX_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 30.0
CAPTURE_DIR_NAME = "captures"

# 只收 PNG / JPEG：iPhone 截屏本来就是 PNG，阿里云 OCR 不认 HEIC
_SIGNATURES = (
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\xff\xd8\xff", "jpg"),
)
_HEIF_BRANDS = (b"heic", b"heix", b"hevc", b"heim", b"heis", b"mif1", b"msf1", b"avif")


class CaptureRejected(ValueError):
    def __init__(self, message: str, *, code: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


def sniff_image(data: bytes) -> str:
    """按文件头判断格式，不信任文件名和 Content-Type。"""
    for signature, kind in _SIGNATURES:
        if data.startswith(signature):
            return kind
    if data[4:8] == b"ftyp" and data[8:12] in _HEIF_BRANDS:
        raise CaptureRejected(
            "收到的是 HEIC 图片，暂不支持。请在快捷指令里加一步「转换图像 → JPEG」后再上传。",
            code="unsupported_heic",
            status=415,
        )
    raise CaptureRejected("只支持 PNG 或 JPEG 格式的截图。", code="unsupported_image", status=415)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _connect(ledger: Ledger) -> sqlite3.Connection:
    conn = sqlite3.connect(ledger.db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    ensure_capture_tables(conn)
    return conn


def ensure_capture_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        create table if not exists capture_jobs (
            id integer primary key autoincrement,
            image_sha text not null unique,
            image_path text not null,
            source text not null,
            status text not null default 'queued',
            attempts integer not null default 0,
            error text,
            transaction_uid text,
            amount real,
            merchant text,
            paid_at text,
            created_at text not null,
            updated_at text not null,
            finished_at text
        )
        """
    )
    conn.execute("create index if not exists capture_jobs_status on capture_jobs(status)")
    conn.commit()


def _row(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row is not None else None


def save_capture(ledger: Ledger, data: bytes, *, source: str) -> tuple[dict, bool]:
    """存图并登记任务。返回 (任务, 是否新建)；同一张图再传一次拿到的是原来那个任务。"""
    kind = sniff_image(data)
    sha = hashlib.sha256(data).hexdigest()
    relative = Path("data") / CAPTURE_DIR_NAME / f"cap_{sha[:24]}.{kind}"
    target = ledger.root / relative
    conn = _connect(ledger)
    try:
        existing = conn.execute("select * from capture_jobs where image_sha = ?", (sha,)).fetchone()
        if existing is not None:
            if existing["status"] == "failed":
                # 之前失败过的图又传了一次：当作用户想重试
                conn.execute(
                    "update capture_jobs set status = 'queued', attempts = 0, error = null, updated_at = ? where id = ?",
                    (_now(), existing["id"]),
                )
                conn.commit()
                existing = conn.execute("select * from capture_jobs where id = ?", (existing["id"],)).fetchone()
            return _row(existing), False
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            temp = target.with_suffix(target.suffix + ".part")
            temp.write_bytes(data)
            temp.replace(target)
        now = _now()
        try:
            cursor = conn.execute(
                """
                insert into capture_jobs (image_sha, image_path, source, created_at, updated_at)
                values (?, ?, ?, ?, ?)
                """,
                (sha, relative.as_posix(), source, now, now),
            )
        except sqlite3.IntegrityError:
            # 同一张图被并发上传了两次，另一个请求先登记了
            return _row(conn.execute("select * from capture_jobs where image_sha = ?", (sha,)).fetchone()), False
        conn.commit()
        return _row(conn.execute("select * from capture_jobs where id = ?", (cursor.lastrowid,)).fetchone()), True
    finally:
        conn.close()


def get_job(ledger: Ledger, job_id: int) -> dict | None:
    conn = _connect(ledger)
    try:
        return _row(conn.execute("select * from capture_jobs where id = ?", (job_id,)).fetchone())
    finally:
        conn.close()


def recent_jobs(ledger: Ledger, limit: int = 8) -> list[dict]:
    conn = _connect(ledger)
    try:
        # 已入账但交易被手动删掉的不再列出：点开只会看到「找不到证据」
        rows = conn.execute(
            """
            select * from capture_jobs j
            where j.status != 'done'
               or exists (select 1 from transactions t where t.transaction_uid = j.transaction_uid)
            order by j.id desc limit ?
            """,
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def unfinished_job_ids(ledger: Ledger) -> list[int]:
    """进程上次退出时还没跑完的任务。processing 说明当时正跑到一半，放回队列。"""
    if not ledger.db_path.exists():
        return []
    conn = _connect(ledger)
    try:
        conn.execute("update capture_jobs set status = 'queued', updated_at = ? where status = 'processing'", (_now(),))
        conn.commit()
        return [row[0] for row in conn.execute("select id from capture_jobs where status = 'queued' order by id")]
    finally:
        conn.close()


_LEDGER_LOCKS: dict[str, threading.Lock] = {}
_LEDGER_LOCKS_GUARD = threading.Lock()


def _ledger_lock(ledger: Ledger) -> threading.Lock:
    key = str(ledger.db_path.resolve())
    with _LEDGER_LOCKS_GUARD:
        return _LEDGER_LOCKS.setdefault(key, threading.Lock())


def process_job(ledger: Ledger, job_id: int) -> dict:
    """跑一个任务：OCR → 解析 → 入账。同一账本的任务串行，避免并发写同一个库。"""
    with _ledger_lock(ledger):
        conn = _connect(ledger)
        try:
            claimed = conn.execute(
                """
                update capture_jobs set status = 'processing', attempts = attempts + 1, updated_at = ?
                where id = ? and status = 'queued'
                """,
                (_now(), job_id),
            ).rowcount
            conn.commit()
            job = _row(conn.execute("select * from capture_jobs where id = ?", (job_id,)).fetchone())
        finally:
            conn.close()
        if not claimed or job is None:
            return job or {}

        try:
            parsed = process_bill_image.process_image(
                str(ledger.root / job["image_path"]),
                source=job["source"],
                captured_at=job["created_at"],
                ledger=ledger,
            )
        except Exception as exc:  # OCR 超时、网络抖动、解析异常都在这里兜住
            final = job["attempts"] >= MAX_ATTEMPTS
            message = str(exc).strip() or type(exc).__name__
            print(f"[CFO] 截图任务 {job_id} 第 {job['attempts']} 次失败：{type(exc).__name__}: {message[:200]}")
            update = (
                "update capture_jobs set status = ?, error = ?, updated_at = ?, finished_at = ? where id = ?",
                ("failed" if final else "queued", message[:300], _now(), _now() if final else None, job_id),
            )
        else:
            update = (
                """
                update capture_jobs set status = 'done', error = null, transaction_uid = ?, amount = ?,
                merchant = ?, paid_at = ?, updated_at = ?, finished_at = ? where id = ?
                """,
                (parsed.transaction_uid, parsed.amount, parsed.merchant, parsed.paid_at, _now(), _now(), job_id),
            )
        conn = _connect(ledger)
        try:
            conn.execute(*update)
            conn.commit()
            return _row(conn.execute("select * from capture_jobs where id = ?", (job_id,)).fetchone())
        finally:
            conn.close()


class CaptureWorker:
    """后台线程池。``on_stored(ledger)`` 在入账成功后调用，用来触发后台分类。"""

    def __init__(
        self,
        max_workers: int = 2,
        *,
        on_stored: Callable[[Ledger], None] | None = None,
        retry_delay: float = RETRY_DELAY_SECONDS,
    ) -> None:
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="cfo-capture")
        self._on_stored = on_stored
        self._retry_delay = retry_delay

    def submit(self, ledger: Ledger, job_id: int) -> Future:
        return self._pool.submit(self._run, ledger, job_id)

    def _run(self, ledger: Ledger, job_id: int) -> dict:
        job = process_job(ledger, job_id)
        if job.get("status") == "done" and self._on_stored is not None:
            try:
                self._on_stored(ledger)
            except Exception as exc:  # 分类没启动不影响入账结果
                print(f"[CFO] 入账后触发分类失败：{type(exc).__name__}")
        elif job.get("status") == "queued" and job.get("attempts", 0) > 0:
            timer = threading.Timer(self._retry_delay, self.submit, args=(ledger, job_id))
            timer.daemon = True
            timer.start()
        return job

    def resume(self, ledgers: Iterable[Ledger]) -> int:
        count = 0
        for ledger in ledgers:
            for job_id in unfinished_job_ids(ledger):
                self.submit(ledger, job_id)
                count += 1
        return count
