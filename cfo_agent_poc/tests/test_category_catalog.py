from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from cfo_agent_poc.bill_store import ensure_bill_tables
from cfo_agent_poc.category_catalog import (
    CategoryError,
    create_category,
    delete_category,
    ensure_category_tables,
    get_catalog,
    model_taxonomy,
    patch_category,
    set_primary_order,
)


class CategoryCatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "cfo.sqlite"
        conn = sqlite3.connect(self.db_path)
        ensure_bill_tables(conn)
        ensure_category_tables(conn)
        conn.commit()
        conn.close()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_initialization_is_idempotent_and_keeps_stable_ids(self) -> None:
        first = get_catalog(self.db_path)
        conn = sqlite3.connect(self.db_path)
        ensure_category_tables(conn)
        ensure_category_tables(conn)
        conn.commit()
        count = conn.execute("select count(*) from category_catalog").fetchone()[0]
        conn.close()
        self.assertEqual(count, len(first["categories"]))
        self.assertIn("coffee_tea", {item["id"] for item in first["categories"]})
        self.assertIn("uncategorized", {item["id"] for item in first["categories"]})

    def test_create_rejects_duplicate_name_and_invalid_appearance(self) -> None:
        created = create_category(self.db_path, {
            "display_name": " 宠物 ", "icon_key": "pet", "color_token": "cat-7"
        })
        self.assertEqual(created["display_name"], "宠物")
        self.assertEqual(created["icon_key"], "pet")
        self.assertTrue(created["id"].startswith("custom_"))
        with self.assertRaises(CategoryError) as duplicate:
            create_category(self.db_path, {"display_name": "宠物", "icon_key": "heart", "color_token": "cat-7"})
        self.assertEqual(duplicate.exception.code, "duplicate_name")
        with self.assertRaises(CategoryError) as invalid:
            create_category(self.db_path, {"display_name": "健身", "icon_key": "emoji", "color_token": "cat-1"})
        self.assertEqual(invalid.exception.code, "invalid_icon")

    def test_supports_expanded_semantic_icon_set(self) -> None:
        catalog = get_catalog(self.db_path)
        expanded_icons = {"pet", "medicine", "parcel", "beauty", "delivery", "apparel"}
        self.assertTrue(expanded_icons.issubset(set(catalog["allowed_icons"])))
        for index, icon_key in enumerate(sorted(expanded_icons)):
            with self.subTest(icon_key=icon_key):
                created = create_category(self.db_path, {
                    "display_name": f"图标分类{index}",
                    "icon_key": icon_key,
                    "color_token": "cat-1",
                })
                self.assertEqual(created["icon_key"], icon_key)

    def test_primary_limit_and_atomic_order_validation(self) -> None:
        before = [
            item["id"] for item in get_catalog(self.db_path)["categories"] if item["is_primary"]
        ]
        with self.assertRaises(CategoryError):
            set_primary_order(self.db_path, before + ["coffee_tea"])
        after = [
            item["id"] for item in get_catalog(self.db_path)["categories"] if item["is_primary"]
        ]
        self.assertEqual(before, after)
        reversed_ids = list(reversed(before))
        set_primary_order(self.db_path, reversed_ids)
        ordered = sorted(
            (item for item in get_catalog(self.db_path)["categories"] if item["is_primary"]),
            key=lambda item: item["primary_order"],
        )
        self.assertEqual([item["id"] for item in ordered], reversed_ids)

    def test_reserved_and_system_category_guards(self) -> None:
        with self.assertRaises(CategoryError) as reserved:
            patch_category(self.db_path, "uncategorized", {"display_name": "其他"})
        self.assertEqual(reserved.exception.code, "reserved_category")
        with self.assertRaises(CategoryError) as system:
            delete_category(self.db_path, "books")
        self.assertEqual(system.exception.code, "system_category")

    def test_disable_removes_category_from_model_taxonomy_but_keeps_history(self) -> None:
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """
            insert into transactions
                (transaction_uid, source, amount, direction, paid_at, category, confidence, raw_text, created_at)
            values ('tx-books', 'test', 12, 'outflow', '2026-08-01T12:00:00', 'books', 1, '', datetime('now'))
            """
        )
        conn.commit()
        conn.close()
        patch_category(self.db_path, "books", {"is_enabled": False})
        item = next(item for item in get_catalog(self.db_path)["categories"] if item["id"] == "books")
        self.assertFalse(item["is_enabled"])
        self.assertEqual(item["transaction_count"], 1)
        self.assertNotIn("books", model_taxonomy(self.db_path))

    def test_custom_category_can_only_be_deleted_without_references(self) -> None:
        created = create_category(self.db_path, {
            "display_name": "宠物", "icon_key": "heart", "color_token": "cat-7"
        })
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """
            insert into transactions
                (transaction_uid, source, amount, direction, paid_at, category, confidence, raw_text, created_at)
            values ('tx-pet', 'test', 88, 'outflow', '2026-08-02T12:00:00', ?, 1, '', datetime('now'))
            """,
            (created["id"],),
        )
        conn.commit()
        conn.close()
        with self.assertRaises(CategoryError) as in_use:
            delete_category(self.db_path, created["id"])
        self.assertEqual(in_use.exception.code, "category_in_use")
        patch_category(self.db_path, created["id"], {"is_enabled": False})
        conn = sqlite3.connect(self.db_path)
        conn.execute("delete from transactions where transaction_uid = 'tx-pet'")
        conn.commit()
        conn.close()
        self.assertTrue(delete_category(self.db_path, created["id"])["ok"])


if __name__ == "__main__":
    unittest.main()
