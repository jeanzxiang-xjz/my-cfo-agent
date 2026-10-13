"""截图直传：上传密钥、幂等、格式与体积校验、超时回执、失败、账本隔离、重启续跑。

OCR 用假函数顶替，测的是从 HTTP 进来到入账出去的整条链路。
"""

from __future__ import annotations

import http.client
import json
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from cfo_agent_poc.tests.test_accounts import Browser, LiveServerCase

WEB_APP_DIR = Path(__file__).resolve().parents[1] / "web_app"
if str(WEB_APP_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_APP_DIR))

import server  # noqa: E402  (先让 server 把 cfo_agent_poc 放进 sys.path)
import capture_queue  # noqa: E402
import process_bill_image  # noqa: E402


BILL = """示例便利店
-8.00
示例便利店
当前状态
支付成功
支付时间
2026年07月12日 10:20:30
支付方式
零钱
交易单号
4500000000000000000000000101"""

INCOMPLETE = "@交易详情\n-8.00"


def png(tag: str | None = None) -> bytes:
    """内容各不相同的「PNG」：只要文件头对，OCR 是假的，不需要真图。"""
    return b"\x89PNG\r\n\x1a\n" + (tag or uuid.uuid4().hex).encode()


class CaptureUploadTests(LiveServerCase):
    def setUp(self) -> None:
        super().setUp()
        self.ocr_text = BILL
        ocr = patch.object(process_bill_image, "ocr_image", lambda path: self.ocr_text)
        ocr.start()
        self.addCleanup(ocr.stop)

    def upload(self, data: bytes, token: str | None, *, browser: Browser | None = None, content_type: str = "image/png"):
        browser = browser or self.browser()
        headers = {"Content-Type": content_type}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        status, _, raw = browser.request("POST", "/api/v1/captures", headers=headers, body=data)
        return status, json.loads(raw or b"{}")

    def connected_user(self, email: str = "alice@example.com", invite: str = "") -> tuple[Browser, str]:
        browser = self.register(email, invite)
        status, payload = browser.json("POST", "/api/v1/upload-token")
        self.assertEqual(status, 201)
        return browser, payload["token"]

    def transactions(self, browser: Browser) -> list[dict]:
        return json.loads(browser.request("GET", "/data.json")[2])["transactions"]

    def test_capture_upload_with_token_books_the_bill(self) -> None:
        alice, token = self.connected_user()
        self.assertTrue(token.startswith("cfo_up_"))

        status, payload = self.upload(png(), token)
        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "done")
        self.assertEqual(payload["message"], "已记账 ¥8.00 · 示例便利店")
        self.assertFalse(payload["needs_correction"])

        txs = self.transactions(alice)
        self.assertEqual(len(txs), 1)
        uid = txs[0]["transaction_uid"]
        status, _, image = alice.request("GET", f"/api/transaction-evidence-image?uid={uid}")
        self.assertEqual(status, 200)
        self.assertTrue(image.startswith(b"\x89PNG"))
        recent = alice.json("GET", "/api/v1/captures")[1]["captures"]
        self.assertEqual(recent[0]["source"], "shortcut_upload")

    def test_capture_same_image_twice_is_idempotent(self) -> None:
        alice, token = self.connected_user()
        image = png("same")
        self.upload(image, token)
        status, payload = self.upload(image, token)
        self.assertEqual(status, 200)
        self.assertTrue(payload["duplicate"])
        self.assertIn("记过了", payload["message"])
        self.assertEqual(len(alice.json("GET", "/api/v1/captures")[1]["captures"]), 1)

    def test_capture_multipart_form_is_accepted(self) -> None:
        _, token = self.connected_user()
        boundary = "----cfoBoundary"
        body = (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"note\"\r\n\r\nhi\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"shot.png\"\r\n"
            "Content-Type: image/png\r\n\r\n"
        ).encode() + png() + f"\r\n--{boundary}--\r\n".encode()
        status, payload = self.upload(body, token, content_type=f"multipart/form-data; boundary={boundary}")
        self.assertEqual(status, 200, payload)
        self.assertEqual(payload["status"], "done")

    def test_capture_rejects_bad_formats_and_sizes(self) -> None:
        _, token = self.connected_user()
        heic = b"\x00\x00\x00\x18ftypheic" + b"\x00" * 16
        self.assertEqual(self.upload(heic, token)[1]["code"], "unsupported_heic")
        self.assertEqual(self.upload(b"hello", token, content_type="text/plain")[0], 415)
        self.assertEqual(self.upload(b"", token)[0], 400)
        with patch.object(server, "MAX_UPLOAD_BYTES", 32):
            status, payload = self.upload(png("x" * 64), token)
        self.assertEqual(status, 413)
        self.assertEqual(payload["code"], "payload_too_large")

    def test_capture_token_is_write_only_and_revocable(self) -> None:
        alice, token = self.connected_user()
        reader = self.browser()
        status, _, _ = reader.request("GET", "/data.json", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(status, 401, "上传密钥不能拿来读账")

        status, settings = alice.json("GET", "/api/v1/upload-token")
        self.assertTrue(settings["token_status"]["active"])
        self.assertIsNone(settings["token"], "明文密钥只在生成那一次给出")
        self.assertEqual(settings["token_status"]["last4"], token[-4:])
        self.assertTrue(settings["upload_url"].endswith("/api/v1/captures"))

        new_token = alice.json("POST", "/api/v1/upload-token")[1]["token"]
        self.assertEqual(self.upload(png(), token)[0], 401, "换新密钥后旧的立即失效")
        self.assertEqual(self.upload(png(), new_token)[0], 200)
        alice.json("DELETE", "/api/v1/upload-token")
        status, payload = self.upload(png(), new_token)
        self.assertEqual(status, 401)
        self.assertIn("重新生成", payload["message"])
        self.assertEqual(self.upload(png(), "cfo_up_made-up")[0], 401)
        self.assertEqual(self.upload(png(), None)[0], 401)

    def test_capture_rejection_reaches_phone_after_full_upload(self) -> None:
        """旧密钥传一张真实大小的截图：服务端得把图收完再回 401，
        否则手机还在发就被断开，快捷指令只会报网络错误，看不到提示。"""
        self.connected_user()
        big = png("x" * (4 * 1024 * 1024))
        conn = http.client.HTTPConnection(self.base.removeprefix("http://"), timeout=10)
        conn.request(
            "POST",
            "/api/v1/captures",
            body=big,
            headers={"Authorization": "Bearer cfo_up_revoked", "Content-Type": "image/png"},
        )
        response = conn.getresponse()
        payload = json.loads(response.read())
        conn.close()
        self.assertEqual(response.status, 401)
        self.assertIn("记一笔 → 连接 iPhone", payload["message"])

    def test_capture_goes_to_the_token_owners_ledger_only(self) -> None:
        alice, alice_token = self.connected_user("alice@example.com")
        bob, bob_token = self.connected_user("bob@example.com", self.store.create_invite(None)["code"])
        self.upload(png(), bob_token)
        self.assertEqual(len(self.transactions(bob)), 1)
        self.assertEqual(self.transactions(alice), [])
        self.assertEqual(alice.json("GET", "/api/v1/captures")[1]["captures"], [])

    def test_deleting_transaction_clears_its_uploads(self) -> None:
        """同一笔账截了两次再手动删掉：两张截图、OCR 原文、上传记录一起清掉，
        「记一笔」里不再列出；之后同一张图再传，会重新识别入账，而不是「记过了」。"""
        alice, token = self.connected_user()
        ledger = self.store.ledger_for(self.store.find_user_by_email("alice@example.com"))
        first, second = png("shot-1"), png("shot-2")
        self.upload(first, token)
        self.upload(second, token)
        self.assertEqual(len(alice.json("GET", "/api/v1/captures")[1]["captures"]), 2)
        uid = self.transactions(alice)[0]["transaction_uid"]

        status, result = alice.json("POST", "/api/transaction-delete", {"uid": uid})
        self.assertEqual(status, 200, result)
        self.assertEqual(alice.json("GET", "/api/v1/captures")[1]["captures"], [])
        self.assertEqual(list((ledger.data_dir / "captures").iterdir()), [])
        conn = sqlite3.connect(ledger.db_path)
        self.assertEqual(conn.execute("select count(*) from raw_bill_captures").fetchone()[0], 0)
        self.assertEqual(conn.execute("select count(*) from capture_jobs").fetchone()[0], 0)
        conn.close()

        status, payload = self.upload(first, token)
        self.assertEqual(payload["message"], "已记账 ¥8.00 · 示例便利店")
        self.assertEqual(len(self.transactions(alice)), 1)

    def test_recent_uploads_hide_transactions_deleted_earlier(self) -> None:
        """修复前就删掉的交易，上传记录还留在库里：列表里也不该再出现。"""
        alice, token = self.connected_user()
        ledger = self.store.ledger_for(self.store.find_user_by_email("alice@example.com"))
        self.upload(png(), token)
        conn = sqlite3.connect(ledger.db_path)
        conn.execute("delete from transactions")
        conn.commit()
        conn.close()
        self.assertEqual(alice.json("GET", "/api/v1/captures")[1]["captures"], [])

    def test_capture_incomplete_bill_asks_for_correction(self) -> None:
        _, token = self.connected_user()
        self.ocr_text = INCOMPLETE
        status, payload = self.upload(png(), token)
        self.assertEqual(status, 200)
        self.assertTrue(payload["needs_correction"])
        self.assertIn("没认出来", payload["message"])

    def test_capture_slow_ocr_returns_receipt_then_finishes(self) -> None:
        alice, token = self.connected_user()
        release = threading.Event()

        def slow_ocr(path: str) -> str:
            release.wait(5)
            return BILL

        with patch.object(process_bill_image, "ocr_image", slow_ocr), patch.object(server, "CAPTURE_WAIT_SECONDS", 0.2):
            status, payload = self.upload(png(), token)
            self.assertEqual(status, 202)
            self.assertIn("正在识别", payload["message"])
            release.set()
            for _ in range(50):
                captures = alice.json("GET", "/api/v1/captures")[1]["captures"]
                if captures[0]["status"] == "done":
                    break
                time.sleep(0.1)
        self.assertEqual(captures[0]["status"], "done")
        self.assertEqual(len(self.transactions(alice)), 1)

    def test_capture_ocr_failure_is_reported(self) -> None:
        alice, token = self.connected_user()

        def broken_ocr(path: str) -> str:
            raise RuntimeError("OCR 服务暂时不可用")

        with patch.object(process_bill_image, "ocr_image", broken_ocr), patch.object(capture_queue, "MAX_ATTEMPTS", 1):
            status, payload = self.upload(png(), token)
        self.assertEqual(status, 422)
        self.assertEqual(payload["message"], "识别失败：OCR 服务暂时不可用")
        self.assertEqual(self.transactions(alice), [])

    def test_capture_web_upload_uses_session_and_checks_origin(self) -> None:
        alice = self.register("alice@example.com")
        status, payload = self.upload(png(), None, browser=alice)
        self.assertEqual(status, 200)
        self.assertEqual(payload["source"], "web_upload")
        status, _, _ = alice.request(
            "POST", "/api/v1/captures", headers={"Content-Type": "image/png", "Origin": "https://evil.example"}, body=png()
        )
        self.assertEqual(status, 403)


class CaptureQueueTests(unittest.TestCase):
    def test_unfinished_jobs_are_picked_up_after_restart(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            ledger = server.Ledger(Path(temp))
            server.ensure_ledger_schema(ledger)
            job, created = capture_queue.save_capture(ledger, png(), source="shortcut_upload")
            self.assertTrue(created)
            self.assertTrue((ledger.root / job["image_path"]).is_file())
            conn = capture_queue._connect(ledger)
            conn.execute("update capture_jobs set status = 'processing' where id = ?", (job["id"],))
            conn.commit()
            conn.close()

            # 「重启」：processing 被放回队列，再跑一遍就入账
            self.assertEqual(capture_queue.unfinished_job_ids(ledger), [job["id"]])
            with patch.object(process_bill_image, "ocr_image", lambda path: BILL):
                done = capture_queue.process_job(ledger, job["id"])
            self.assertEqual(done["status"], "done")
            self.assertTrue((ledger.ocr_text_dir / f"{Path(job['image_path']).stem}.txt").is_file())


if __name__ == "__main__":
    unittest.main()
