"""截图直传：上传密钥、幂等、格式与体积校验、超时回执、失败、账本隔离、重启续跑、原图转 WebP 留底。

OCR 用假函数顶替，测的是从 HTTP 进来到入账出去的整条链路。
"""

from __future__ import annotations

import http.client
import io
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

from PIL import Image, ImageCms

from cfo_agent_poc.tests.test_accounts import Browser, LiveServerCase

WEB_APP_DIR = Path(__file__).resolve().parents[1] / "web_app"
if str(WEB_APP_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_APP_DIR))

import server  # noqa: E402  (先让 server 把 cfo_agent_poc 放进 sys.path)
import capture_queue  # noqa: E402
import evidence_image  # noqa: E402
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


_TINY_PNG = io.BytesIO()
Image.new("RGB", (6, 12), "white").save(_TINY_PNG, "PNG")


def png(tag: str | None = None) -> bytes:
    """内容各不相同的真 PNG：OCR 是假的，但转 WebP 要能解开。
    区分用的标记挂在 IEND 之后，解码器会忽略它，哈希却各不相同。"""
    return _TINY_PNG.getvalue() + (tag or uuid.uuid4().hex).encode()


def fake_png(tag: str | None = None) -> bytes:
    """只有文件头对的「PNG」，解不开，用来测转 WebP 失败的兜底。"""
    return b"\x89PNG\r\n\x1a\n" + (tag or uuid.uuid4().hex).encode()


def stored_files(directory: Path) -> list[str]:
    return sorted(path.relative_to(directory).as_posix() for path in directory.rglob("*") if path.is_file())


class CaptureUploadTests(LiveServerCase):
    def setUp(self) -> None:
        super().setUp()
        self.ocr_text = BILL
        self.ocr_paths: list[str] = []
        ocr = patch.object(process_bill_image, "ocr_image", self.fake_ocr)
        ocr.start()
        self.addCleanup(ocr.stop)

    def fake_ocr(self, path: str) -> str:
        self.ocr_paths.append(path)
        return self.ocr_text

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
        self.assertEqual((image[:4], image[8:12]), (b"RIFF", b"WEBP"))
        recent = alice.json("GET", "/api/v1/captures")[1]["captures"]
        self.assertEqual(recent[0]["source"], "shortcut_upload")

    def test_capture_keeps_webp_not_the_original(self) -> None:
        """OCR 读的是原图；入账后原图删掉，库里和磁盘上只剩同尺寸的 WebP。"""
        alice, token = self.connected_user()
        ledger = self.store.ledger_for(self.store.find_user_by_email("alice@example.com"))
        original = png()
        self.assertEqual(self.upload(original, token)[1]["status"], "done")

        self.assertEqual(len(self.ocr_paths), 1)
        self.assertEqual(Path(self.ocr_paths[0]).suffix, ".png")
        self.assertEqual(Path(self.ocr_paths[0]).parent.name, "inbox")
        stem = Path(self.ocr_paths[0]).stem
        self.assertEqual(stored_files(ledger.data_dir / "captures"), [f"{stem}.webp"])
        conn = sqlite3.connect(ledger.db_path)
        self.assertEqual(
            conn.execute("select image_path from raw_bill_captures").fetchone()[0], f"data/captures/{stem}.webp"
        )
        self.assertEqual(conn.execute("select image_path from capture_jobs").fetchone()[0], f"data/captures/{stem}.webp")
        conn.close()

        uid = self.transactions(alice)[0]["transaction_uid"]
        status, headers, image = alice.request("GET", f"/api/transaction-evidence-image?uid={uid}")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "image/webp")
        self.assertIn("max-age", headers["Cache-Control"])
        with Image.open(io.BytesIO(image)) as webp, Image.open(io.BytesIO(original)) as source:
            self.assertEqual(webp.format, "WEBP")
            self.assertEqual(webp.size, source.size)

    def test_capture_undecodable_image_still_books_with_original(self) -> None:
        """转不了 WebP（坏图 / 没装 Pillow）不挡记账，原图原样留底。"""
        alice, token = self.connected_user()
        ledger = self.store.ledger_for(self.store.find_user_by_email("alice@example.com"))
        self.assertEqual(self.upload(fake_png(), token)[1]["status"], "done")
        with patch.object(evidence_image, "_write_webp", side_effect=ImportError("No module named 'PIL'")):
            self.assertEqual(self.upload(png(), token)[1]["status"], "done")

        files = stored_files(ledger.data_dir / "captures")
        self.assertEqual(len(files), 2)
        self.assertTrue(all(name.endswith(".png") and "/" not in name for name in files), files)
        uid = self.transactions(alice)[0]["transaction_uid"]
        status, headers, image = alice.request("GET", f"/api/transaction-evidence-image?uid={uid}")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "image/png")

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
        self.assertEqual(stored_files(ledger.data_dir / "captures"), [])
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
            self.assertEqual(Path(done["image_path"]).suffix, ".webp")

    def test_original_survives_retries_and_is_dropped_after_final_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            ledger = server.Ledger(Path(temp))
            server.ensure_ledger_schema(ledger)
            image = png()
            job, _ = capture_queue.save_capture(ledger, image, source="shortcut_upload")
            raw = ledger.root / job["image_path"]

            def broken_ocr(path: str) -> str:
                raise RuntimeError("OCR 服务暂时不可用")

            with patch.object(process_bill_image, "ocr_image", broken_ocr), patch.object(capture_queue, "MAX_ATTEMPTS", 2):
                retry = capture_queue.process_job(ledger, job["id"])
                self.assertEqual(retry["status"], "queued")
                self.assertTrue(raw.is_file(), "还要重试，原图得留着")

                failed = capture_queue.process_job(ledger, job["id"])
            self.assertEqual(failed["status"], "failed")
            self.assertFalse(raw.exists())
            self.assertEqual(stored_files(ledger.data_dir / "captures"), [f"{raw.stem}.webp"])
            self.assertEqual(failed["image_path"], f"data/captures/{raw.stem}.webp")

            # 失败后又把同一张图传了一次：用这次传上来的原图重新识别
            requeued, created = capture_queue.save_capture(ledger, image, source="shortcut_upload")
            self.assertFalse(created)
            self.assertEqual(requeued["status"], "queued")
            self.assertTrue(raw.is_file())
            ocr_paths: list[str] = []
            with patch.object(process_bill_image, "ocr_image", lambda path: ocr_paths.append(path) or BILL):
                done = capture_queue.process_job(ledger, job["id"])
            self.assertEqual(done["status"], "done")
            self.assertEqual(ocr_paths, [str(raw)])
            self.assertFalse(raw.exists())

    def test_restart_sweeps_unclaimed_originals_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            ledger = server.Ledger(Path(temp))
            server.ensure_ledger_schema(ledger)
            job, _ = capture_queue.save_capture(ledger, png(), source="shortcut_upload")
            inbox = ledger.data_dir / "captures" / "inbox"
            (inbox / "cap_orphan.png").write_bytes(png())
            (inbox / "cap_halfway.png.part").write_bytes(b"\x89PNG")

            self.assertEqual(capture_queue.unfinished_job_ids(ledger), [job["id"]])
            self.assertEqual(stored_files(inbox), [Path(job["image_path"]).name])

    def test_queued_job_from_before_upgrade_is_left_as_is(self) -> None:
        """升级前就排队的任务，原图在 data/captures/ 下：照旧入账，不转存也不删。"""
        with tempfile.TemporaryDirectory() as temp:
            ledger = server.Ledger(Path(temp))
            server.ensure_ledger_schema(ledger)
            job, _ = capture_queue.save_capture(ledger, png(), source="shortcut_upload")
            legacy = ledger.data_dir / "captures" / Path(job["image_path"]).name
            (ledger.root / job["image_path"]).replace(legacy)
            conn = capture_queue._connect(ledger)
            conn.execute("update capture_jobs set image_path = ? where id = ?", (f"data/captures/{legacy.name}", job["id"]))
            conn.commit()
            conn.close()

            with patch.object(process_bill_image, "ocr_image", lambda path: BILL):
                done = capture_queue.process_job(ledger, job["id"])
            self.assertEqual(done["status"], "done")
            self.assertEqual(done["image_path"], f"data/captures/{legacy.name}")
            self.assertEqual(stored_files(ledger.data_dir / "captures"), [legacy.name])


class EvidenceImageTests(unittest.TestCase):
    def archive(self, image: Image.Image, **save) -> tuple[Path, Image.Image]:
        temp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(temp, ignore_errors=True))
        raw = temp / "cap_test.png"
        image.save(raw, "PNG", **save)
        evidence = evidence_image.archive(raw, temp / "captures")
        self.assertTrue(raw.is_file(), "原图删不删由调用方决定")
        opened = Image.open(evidence)
        self.addCleanup(opened.close)
        return evidence, opened

    def test_keeps_phone_resolution_and_color_profile(self) -> None:
        profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
        evidence, webp = self.archive(Image.new("RGBA", (1290, 2796), (250, 250, 250, 255)), icc_profile=profile)
        self.assertEqual(evidence.suffix, ".webp")
        self.assertEqual(webp.size, (1290, 2796))
        self.assertEqual(webp.mode, "RGB")
        self.assertEqual(webp.info.get("icc_profile"), profile)

    def test_oversized_image_is_scaled_to_max_width(self) -> None:
        _, webp = self.archive(Image.new("RGB", (2048, 2732), "white"))
        self.assertEqual(webp.size, (evidence_image.MAX_WIDTH, round(2732 * evidence_image.MAX_WIDTH / 2048)))

    def test_existing_webp_is_reused(self) -> None:
        evidence, _ = self.archive(Image.new("RGB", (8, 8), "white"))
        stamp = evidence.stat().st_mtime_ns
        with patch.object(evidence_image, "_write_webp", side_effect=AssertionError("不该再转一次")):
            self.assertEqual(evidence_image.archive(evidence.parent.parent / "cap_test.png", evidence.parent), evidence)
        self.assertEqual(evidence.stat().st_mtime_ns, stamp)


if __name__ == "__main__":
    unittest.main()
