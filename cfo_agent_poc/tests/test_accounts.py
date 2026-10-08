"""账户体系：注册、登录、会话、邀请码，以及账户之间互相看不到对方的账。

HTTP 用例起一个真实的服务端，走和浏览器一样的表单提交与 cookie。
"""

from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from cfo_agent_poc import bill_store
from cfo_agent_poc.accounts import AccountError, AccountStore, LoginThrottle, hash_password, verify_password

WEB_APP_DIR = Path(__file__).resolve().parents[1] / "web_app"
if str(WEB_APP_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_APP_DIR))

import server


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


class AccountStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        self.store = AccountStore(Path(temp_dir.name))

    def test_password_hash_round_trip(self) -> None:
        stored = hash_password("correct horse")
        self.assertTrue(verify_password("correct horse", stored))
        self.assertFalse(verify_password("wrong horse", stored))
        self.assertNotIn("correct horse", stored)

    def test_first_user_is_admin_and_needs_no_invite(self) -> None:
        self.assertFalse(self.store.needs_invite())
        user = self.store.register("Boss@Example.com", "password1", "老板")
        self.assertTrue(user["is_admin"])
        self.assertEqual(user["email"], "boss@example.com")
        self.assertTrue(self.store.ledger_for(user).data_dir.is_dir())
        self.assertTrue(self.store.needs_invite())

    def test_later_users_need_a_single_use_invite(self) -> None:
        admin = self.store.register("a@example.com", "password1")
        with self.assertRaises(AccountError) as ctx:
            self.store.register("b@example.com", "password1")
        self.assertEqual(ctx.exception.code, "invite_required")

        code = self.store.create_invite(admin["id"])["code"]
        user = self.store.register("b@example.com", "password1", "", code.lower())
        self.assertFalse(user["is_admin"])
        self.assertNotEqual(self.store.ledger_for(user).root, self.store.ledger_for(admin).root)
        with self.assertRaises(AccountError) as ctx:
            self.store.register("c@example.com", "password1", "", code)
        self.assertEqual(ctx.exception.code, "invalid_invite")

    def test_duplicate_email_and_weak_password_are_rejected(self) -> None:
        self.store.register("a@example.com", "password1")
        code = self.store.create_invite(None)["code"]
        with self.assertRaises(AccountError):
            self.store.register("A@example.com", "password1", "", code)
        with self.assertRaises(AccountError):
            self.store.register("b@example.com", "short", "", code)

    def test_sessions_are_stored_hashed_and_revocable(self) -> None:
        user = self.store.register("a@example.com", "password1")
        token = self.store.create_session(user["id"])
        self.assertEqual(self.store.session_user(token)["id"], user["id"])
        conn = self.store.connect()
        stored = [row[0] for row in conn.execute("select token_hash from sessions")]
        conn.close()
        self.assertNotIn(token, stored)
        self.store.revoke_session(token)
        self.assertIsNone(self.store.session_user(token))

    def test_changing_password_logs_out_other_devices_only(self) -> None:
        user = self.store.register("a@example.com", "password1")
        here = self.store.create_session(user["id"])
        elsewhere = self.store.create_session(user["id"])
        with self.assertRaises(AccountError):
            self.store.change_password(user["id"], "nope", "password2", keep_session=here)
        self.store.change_password(user["id"], "password1", "password2", keep_session=here)
        self.assertIsNotNone(self.store.session_user(here))
        self.assertIsNone(self.store.session_user(elsewhere))
        self.store.authenticate("a@example.com", "password2")

    def test_budgets_are_per_user(self) -> None:
        a = self.store.register("a@example.com", "password1")
        b = self.store.create_user("b@example.com", "password1")
        self.assertIsNone(self.store.get_budgets(a["id"]))
        self.store.set_budgets(a["id"], {"day": 50, "week": 300, "month": "1200"})
        self.assertEqual(self.store.get_budgets(a["id"]), {"day": 50.0, "week": 300.0, "month": 1200.0})
        self.assertIsNone(self.store.get_budgets(b["id"]))
        with self.assertRaises(AccountError):
            self.store.set_budgets(a["id"], {"day": -1})

    def test_throttle_blocks_after_repeated_failures(self) -> None:
        throttle = LoginThrottle(max_failures=3)
        for _ in range(3):
            self.assertFalse(throttle.blocked("ip:1"))
            throttle.fail("ip:1")
        self.assertTrue(throttle.blocked("ip:1", "email:x"))
        self.assertFalse(throttle.blocked("ip:2"))


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class Browser:
    """一个只认 cfo_session 的极简浏览器：不跟随跳转，自己存 cookie。"""

    def __init__(self, base: str) -> None:
        self.base = base
        self.session: str | None = None
        self.opener = urllib.request.build_opener(NoRedirect)

    def request(self, method: str, path: str, *, form: dict | None = None, data: dict | None = None, headers: dict | None = None):
        body = None
        merged = dict(headers or {})
        if form is not None:
            body = urllib.parse.urlencode(form).encode()
            merged["Content-Type"] = "application/x-www-form-urlencoded"
        elif data is not None:
            body = json.dumps(data).encode()
            merged["Content-Type"] = "application/json"
        if self.session:
            merged["Cookie"] = f"cfo_session={self.session}"
        req = urllib.request.Request(self.base + path, data=body, method=method, headers=merged)
        try:
            response = self.opener.open(req, timeout=10)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            raw = response.read()
            status = response.status if hasattr(response, "status") else response.code
            for cookie in response.headers.get_all("Set-Cookie") or []:
                name, _, rest = cookie.partition("=")
                if name == "cfo_session":
                    value = rest.split(";", 1)[0]
                    self.session = value or None
            return status, response.headers, raw

    def json(self, method: str, path: str, data: dict | None = None, headers: dict | None = None) -> tuple[int, dict]:
        status, _, raw = self.request(method, path, data=data, headers=headers)
        return status, json.loads(raw or b"{}")


class AccountHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        # 用 server 自己导入的那份 accounts 模块，异常类型才对得上 server 里的 except
        self.store = server.AccountStore(Path(temp_dir.name))
        for item in (
            patch.object(server, "ACCOUNTS", self.store),
            patch.object(server, "LOGIN_THROTTLE", server.LoginThrottle()),
            patch.object(server, "DEMO_MODE", False),
        ):
            item.start()
            self.addCleanup(item.stop)

        class QuietHandler(server.CFORequestHandler):
            def log_message(self, *args) -> None:
                pass

        httpd = ThreadingHTTPServer(("127.0.0.1", 0), QuietHandler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        self.base = f"http://127.0.0.1:{httpd.server_address[1]}"

    def browser(self) -> Browser:
        return Browser(self.base)

    def register(self, email: str, invite: str = "") -> Browser:
        browser = self.browser()
        status, headers, _ = browser.request(
            "POST", "/api/v1/register",
            form={"email": email, "password": "password1", "display_name": email.split("@")[0], "invite": invite},
        )
        self.assertEqual(status, 303, "注册成功应跳回首页")
        self.assertEqual(headers["Location"], "/")
        self.assertIsNotNone(browser.session)
        return browser

    def test_empty_install_sends_visitors_to_register(self) -> None:
        status, headers, _ = self.browser().request("GET", "/")
        self.assertEqual(status, 303)
        self.assertEqual(headers["Location"], "/register")

    def test_register_login_logout_flow(self) -> None:
        alice = self.register("alice@example.com")
        status, me = alice.json("GET", "/api/v1/me")
        self.assertEqual(status, 200)
        self.assertTrue(me["user"]["is_admin"])
        self.assertEqual(alice.request("GET", "/data.json")[0], 200)

        alice.request("POST", "/api/v1/logout")
        self.assertIsNone(alice.session)
        self.assertEqual(self.browser().request("GET", "/data.json")[0], 401)

        status, _, body = alice.request("POST", "/api/v1/login", form={"email": "alice@example.com", "password": "bad-pass"})
        self.assertEqual(status, 401)
        self.assertIn("邮箱或密码不正确".encode(), body)
        self.assertIn(b'value="alice@example.com"', body, "出错后应把邮箱带回表单")
        status, headers, _ = alice.request("POST", "/api/v1/login", form={"email": "Alice@Example.com", "password": "password1"})
        self.assertEqual(status, 303)
        self.assertEqual(alice.json("GET", "/api/v1/me")[1]["user"]["email"], "alice@example.com")

    def test_logged_out_session_cookie_no_longer_works(self) -> None:
        alice = self.register("alice@example.com")
        stolen = alice.session
        alice.request("POST", "/api/v1/logout")
        thief = self.browser()
        thief.session = stolen
        self.assertEqual(thief.request("GET", "/data.json")[0], 401)

    def test_second_user_needs_invite_from_admin(self) -> None:
        admin = self.register("admin@example.com")
        status, _, body = self.browser().request(
            "POST", "/api/v1/register", form={"email": "b@example.com", "password": "password1"}
        )
        self.assertEqual(status, 403)
        self.assertIn("邀请码".encode(), body)

        status, payload = admin.json("POST", "/api/v1/invites")
        self.assertEqual(status, 201)
        bob = self.register("bob@example.com", payload["invite"]["code"])
        self.assertFalse(bob.json("GET", "/api/v1/me")[1]["user"]["is_admin"])
        self.assertEqual(bob.json("POST", "/api/v1/invites")[0], 403, "普通用户不能发邀请码")
        invites = admin.json("GET", "/api/v1/invites")[1]["invites"]
        self.assertEqual(invites[0]["used_by_email"], "bob@example.com")

    def test_users_only_see_their_own_ledger(self) -> None:
        alice = self.register("alice@example.com")
        code = self.store.create_invite(None)["code"]
        bob = self.register("bob@example.com", code)

        alice_ledger = self.store.ledger_for(self.store.find_user_by_email("alice@example.com"))
        parsed = bill_store.store_bill_capture(
            BILL, source="test", db_path=alice_ledger.db_path, root_dir=alice_ledger.root
        )

        alice_tx = json.loads(alice.request("GET", "/data.json")[2])["transactions"]
        bob_tx = json.loads(bob.request("GET", "/data.json")[2])["transactions"]
        self.assertEqual([tx["transaction_uid"] for tx in alice_tx], [parsed.transaction_uid])
        self.assertEqual(bob_tx, [])

        path = f"/api/transaction-evidence?uid={parsed.transaction_uid}"
        self.assertEqual(alice.json("GET", path)[0], 200)
        self.assertEqual(bob.json("GET", path)[0], 404)
        status, _ = bob.json("POST", "/api/transaction-delete", {"uid": parsed.transaction_uid})
        self.assertEqual(status, 404)
        self.assertEqual(len(json.loads(alice.request("GET", "/data.json")[2])["transactions"]), 1)

    def test_budgets_round_trip_per_user(self) -> None:
        alice = self.register("alice@example.com")
        self.assertIsNone(alice.json("GET", "/api/v1/settings/budgets")[1]["budgets"])
        status, payload = alice.json("PUT", "/api/v1/settings/budgets", {"budgets": {"day": 88, "week": 500, "month": 2000}})
        self.assertEqual(status, 200)
        self.assertEqual(alice.json("GET", "/api/v1/settings/budgets")[1]["budgets"]["day"], 88)

        bob = self.register("bob@example.com", self.store.create_invite(None)["code"])
        self.assertIsNone(bob.json("GET", "/api/v1/settings/budgets")[1]["budgets"])
        self.assertEqual(bob.json("PUT", "/api/v1/settings/budgets", {"budgets": {"day": -5}})[0], 400)

    def test_display_name_feeds_the_agent_prompt(self) -> None:
        alice = self.register("alice@example.com")
        status, payload = alice.json("PATCH", "/api/v1/me", {"display_name": "小爱"})
        self.assertEqual(status, 200)
        self.assertEqual(payload["user"]["display_name"], "小爱")
        user = self.store.find_user_by_email("alice@example.com")
        with server.use_ledger(self.store.ledger_for(user)):
            self.assertIn("小爱", server.load_system_prompt())

    def test_cross_site_writes_are_rejected(self) -> None:
        alice = self.register("alice@example.com")
        status, payload = alice.json(
            "PUT", "/api/v1/settings/budgets", {"budgets": {"day": 1}}, headers={"Origin": "https://evil.example"}
        )
        self.assertEqual(status, 403)
        self.assertEqual(payload["code"], "cross_site")
        same_origin = {"Origin": self.base}
        self.assertEqual(alice.json("PUT", "/api/v1/settings/budgets", {"budgets": {"day": 1}}, headers=same_origin)[0], 200)

    def test_repeated_wrong_passwords_are_throttled(self) -> None:
        self.register("alice@example.com")
        browser = self.browser()
        for _ in range(10):
            browser.request("POST", "/api/v1/login", form={"email": "alice@example.com", "password": "wrong-pass"})
        status, _, _ = browser.request("POST", "/api/v1/login", form={"email": "alice@example.com", "password": "password1"})
        self.assertEqual(status, 429)

    def test_mail_sync_is_retired(self) -> None:
        alice = self.register("alice@example.com")
        status, payload = alice.json("POST", "/api/sync-mail")
        self.assertEqual(status, 410)
        self.assertEqual(payload["code"], "mail_sync_retired")


if __name__ == "__main__":
    unittest.main()
