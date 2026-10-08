"""旧单用户实例迁移：账单一行不改、截图还能回溯、旧目录不被碰。"""

from __future__ import annotations

import hashlib
import sqlite3
import tempfile
import unittest
from pathlib import Path

from cfo_agent_poc import bill_store
from cfo_agent_poc.accounts import AccountStore
from cfo_agent_poc.migrate_instance import migrate


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


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class MigrateInstanceTests(unittest.TestCase):
    def setUp(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        base = Path(temp_dir.name)
        self.old = base / "old" / "cfo_agent_poc"
        image = self.old / "data" / "mail_attachments" / "mail_7_1.png"
        image.parent.mkdir(parents=True)
        image.write_bytes(b"\x89PNG old screenshot")
        (self.old / ".env").write_text("CFO_OWNER_NAME=小明\nCFO_ACCESS_TOKEN=secret\n", encoding="utf-8")
        self.parsed = bill_store.store_bill_capture(
            BILL, source="email_screenshot", image_path=str(image),
            db_path=self.old / "data" / "cfo.sqlite", root_dir=self.old,
        )
        self.store = AccountStore(base / "home")

    def test_migration_copies_ledger_and_evidence_unchanged(self) -> None:
        old_db = self.old / "data" / "cfo.sqlite"
        old_digest = file_digest(old_db)

        result = migrate(self.old, "ming@example.com", store=self.store, password="password1")

        user = result["user"]
        self.assertEqual(user["display_name"], "小明")
        self.assertTrue(user["is_admin"], "平台里第一个账户自动成为管理员")
        self.assertEqual(result["totals"]["transactions"], 1)
        self.assertEqual(result["images"], {"with_image": 1, "found": 1, "absolute_paths": 0, "missing": 0})
        self.assertEqual(file_digest(old_db), old_digest, "旧账本必须只读")

        ledger = self.store.ledger_for(user)
        conn = sqlite3.connect(ledger.db_path)
        image_path = conn.execute("select image_path from raw_bill_captures").fetchone()[0]
        conn.close()
        self.assertEqual(image_path, "data/mail_attachments/mail_7_1.png", "相对路径原样保留")
        self.assertTrue((ledger.root / image_path).is_file())
        self.store.authenticate("ming@example.com", "password1")

    def test_second_migration_is_not_admin_and_duplicate_is_refused(self) -> None:
        migrate(self.old, "ming@example.com", store=self.store)
        second = migrate(self.old, "hong@example.com", store=self.store, display_name="小红")
        self.assertFalse(second["user"]["is_admin"])
        self.assertEqual(second["user"]["display_name"], "小红")
        with self.assertRaises(SystemExit):
            migrate(self.old, "ming@example.com", store=self.store)


if __name__ == "__main__":
    unittest.main()
