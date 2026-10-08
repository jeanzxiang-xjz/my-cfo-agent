"""多账本隔离。

一个进程同时服务多个账本以后，最怕的就是串号：A 的请求读到 B 的账、A 的截图
被 B 打开、A 的分类任务把 B 的挤掉。这里守住这几条底线。
"""

from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from cfo_agent_poc import bill_store, classification_service

WEB_APP_DIR = Path(__file__).resolve().parents[1] / "web_app"
if str(WEB_APP_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_APP_DIR))

import server
from tenancy import LedgerNotBound


def bill(merchant: str, order_no: int) -> str:
    return f"""{merchant}
-12.00
{merchant}
当前状态
支付成功
支付时间
2026年07月12日 10:20:30
支付方式
零钱
交易单号
45000000000000000000{order_no:08d}"""


class TenancyIsolationTests(unittest.TestCase):
    def setUp(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        base = Path(temp_dir.name)
        self.alice = server.Ledger(base / "alice", display_name="Alice")
        self.bob = server.Ledger(base / "bob", display_name="Bob")
        for ledger in (self.alice, self.bob):
            server.ensure_ledger_schema(ledger)

    def store(self, ledger: server.Ledger, merchant: str, order_no: int) -> None:
        bill_store.store_bill_capture(
            bill(merchant, order_no), source="test", db_path=ledger.db_path, root_dir=ledger.root
        )

    def merchants(self, ledger: server.Ledger) -> set[str]:
        with server.use_ledger(ledger):
            return {tx["merchant"] for tx in server.build_payload()["transactions"]}

    def test_unbound_request_fails_instead_of_falling_back(self) -> None:
        with self.assertRaises(LedgerNotBound):
            server.build_payload()
        with self.assertRaises(LedgerNotBound):
            server.load_system_prompt()

    def test_server_has_no_module_level_ledger_globals(self) -> None:
        # 账本只能经 current_ledger() 取；模块级 DB_PATH/OWNER_NAME 一回来就可能串号
        source = (WEB_APP_DIR / "server.py").read_text(encoding="utf-8")
        self.assertNotRegex(source, r"\bDB_PATH\b")
        self.assertNotRegex(source, r"(?<!\{\{)\bOWNER_NAME\b(?!\}\})")

    def test_concurrent_writes_land_in_their_own_ledger(self) -> None:
        def write(index: int) -> None:
            ledger, name = (self.alice, "甲店") if index % 2 == 0 else (self.bob, "乙店")
            self.store(ledger, f"{name}{index}", index)

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(write, range(40)))

        alice, bob = self.merchants(self.alice), self.merchants(self.bob)
        self.assertEqual(len(alice), 20)
        self.assertEqual(len(bob), 20)
        self.assertTrue(all(name.startswith("甲店") for name in alice))
        self.assertTrue(all(name.startswith("乙店") for name in bob))

    def test_owner_name_follows_the_ledger(self) -> None:
        with server.use_ledger(self.alice):
            self.assertIn("Alice", server.load_system_prompt())
        with server.use_ledger(self.bob):
            self.assertNotIn("Alice", server.load_system_prompt())

    def test_evidence_image_of_another_ledger_is_unreachable(self) -> None:
        image = self.alice.data_dir / "captures" / "a.png"
        image.parent.mkdir(parents=True)
        image.write_bytes(b"\x89PNG fake")

        with server.use_ledger(self.alice):
            self.assertEqual(server._safe_capture_image_path("data/captures/a.png"), image.resolve())
        with server.use_ledger(self.bob):
            self.assertIsNone(server._safe_capture_image_path("data/captures/a.png"))
            self.assertIsNone(server._safe_capture_image_path(str(image)))

    def test_parallel_http_requests_each_see_their_own_ledger(self) -> None:
        self.store(self.alice, "甲店", 1)
        self.store(self.bob, "乙店", 2)
        ledgers = {"alice": self.alice, "bob": self.bob}

        class Handler(server.CFORequestHandler):
            def request_ledger(self) -> server.Ledger:
                return ledgers[self.headers.get("X-Test-Ledger", "")]

            def log_message(self, *args) -> None:
                pass

        httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        url = f"http://127.0.0.1:{httpd.server_address[1]}/data.json"

        def fetch(index: int) -> tuple[str, set[str]]:
            who = "alice" if index % 2 == 0 else "bob"
            request = urllib.request.Request(url, headers={"X-Test-Ledger": who})
            with urllib.request.urlopen(request, timeout=5) as response:
                payload = json.loads(response.read())
            return who, {tx["merchant"] for tx in payload["transactions"]}

        # 演示模式免登录，正好只测账本绑定这一层
        with patch.object(server, "DEMO_MODE", True), ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(fetch, range(24)))

        for who, merchants in results:
            self.assertEqual(merchants, {"甲店"} if who == "alice" else {"乙店"})

    def test_classification_worker_of_one_ledger_does_not_block_another(self) -> None:
        release = threading.Event()
        started: list[str] = []

        def fake_enrich(db_path, **kwargs) -> dict:
            started.append(str(db_path))
            release.wait(5)
            return {}

        with patch.object(classification_service, "enrich_pending_transactions", fake_enrich):
            self.assertTrue(classification_service.start_background_enrichment(self.alice.db_path, api_key="k"))
            self.assertTrue(classification_service.start_background_enrichment(self.bob.db_path, api_key="k"))
            # 同一账本已有 worker 在跑，就不再起第二个
            self.assertFalse(classification_service.start_background_enrichment(self.alice.db_path, api_key="k"))
            release.set()


if __name__ == "__main__":
    unittest.main()
