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
            "display_name": " 手办周边 ", "icon_key": "package", "color_token": "cat-7"
        })
        self.assertEqual(created["display_name"], "手办周边")
        self.assertEqual(created["icon_key"], "package")
        self.assertTrue(created["id"].startswith("custom_"))
        with self.assertRaises(CategoryError) as duplicate:
            create_category(self.db_path, {"display_name": "手办周边", "icon_key": "handshake", "color_token": "cat-7"})
        self.assertEqual(duplicate.exception.code, "duplicate_name")
        with self.assertRaises(CategoryError) as invalid:
            create_category(self.db_path, {"display_name": "健身", "icon_key": "emoji", "color_token": "cat-1"})
        self.assertEqual(invalid.exception.code, "invalid_icon")

    def test_supports_phosphor_icon_set(self) -> None:
        catalog = get_catalog(self.db_path)
        expanded_icons = {"paw-print", "heartbeat", "package", "scissors", "fork-knife", "t-shirt", "game-controller"}
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
            "display_name": "手办周边", "icon_key": "handshake", "color_token": "cat-7"
        })
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """
            insert into transactions
                (transaction_uid, source, amount, direction, paid_at, category, confidence, raw_text, created_at)
            values ('tx-figure', 'test', 88, 'outflow', '2026-08-02T12:00:00', ?, 1, '', datetime('now'))
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
        conn.execute("delete from transactions where transaction_uid = 'tx-figure'")
        conn.commit()
        conn.close()
        self.assertTrue(delete_category(self.db_path, created["id"])["ok"])


    def test_new_life_categories_seed_with_their_own_icons(self) -> None:
        catalog = get_catalog(self.db_path)
        by_id = {item["id"]: item for item in catalog["categories"]}
        expected = {
            "income": ("收入", "money-wavy"), "refund": ("退款", "arrow-u-up-left"),
            "red_packet": ("转账红包", "arrows-left-right"), "social_gifts": ("人情往来", "handshake"),
            "insurance": ("保险", "shield-plus"), "charity": ("公益捐赠", "hand-heart"),
            "electronics": ("数码电器", "devices"), "outdoor_gear": ("户外装备", "tent"),
            "card_games": ("打牌休闲", "club"),
        }
        for category_id, (name, icon) in expected.items():
            with self.subTest(category_id=category_id):
                self.assertEqual(by_id[category_id]["display_name"], name)
                self.assertEqual(by_id[category_id]["icon_key"], icon)
                self.assertTrue(by_id[category_id]["is_enabled"])
        self.assertEqual(by_id["fruit"]["display_name"], "水果生鲜")
        self.assertEqual(by_id["car_charging"]["display_name"], "加油充电")
        # 每个分类的图标都必须在选择器范围里，否则改颜色时校验不过
        self.assertTrue({item["icon_key"] for item in catalog["categories"]} <= set(catalog["allowed_icons"]))
        self.assertIn("charity", model_taxonomy(self.db_path))

    def test_legacy_icon_keys_are_migrated_once(self) -> None:
        conn = sqlite3.connect(self.db_path)
        conn.execute("drop table if exists category_catalog_migrations")
        conn.executemany("update category_catalog set icon_key = ? where id = ?", [
            ("car", "parking"), ("cup", "coffee_tea"), ("placeholder", "insurance"),
            ("gift", "beauty"),  # 用户自己改过的系统分类：按旧→新表就近换
        ])
        conn.execute(
            "insert into category_catalog (id, display_name, system_name, icon_key, color_token, is_enabled, is_system, created_at, updated_at)"
            " values ('custom_x', '手办', '手办', 'parcel', 'cat-7', 1, 0, 'now', 'now')"
        )
        conn.commit()
        conn.close()
        icons = {item["id"]: item["icon_key"] for item in get_catalog(self.db_path)["categories"]}
        self.assertEqual(icons["parking"], "letter-circle-p")
        self.assertEqual(icons["coffee_tea"], "coffee")
        self.assertEqual(icons["insurance"], "shield-plus")
        self.assertEqual(icons["beauty"], "handshake")
        self.assertEqual(icons["custom_x"], "package")

        # 迁移只跑一遍：之后用户主动把停车选成 car，不能又被改回去
        patch_category(self.db_path, "parking", {"icon_key": "car"})
        icons = {item["id"]: item["icon_key"] for item in get_catalog(self.db_path)["categories"]}
        self.assertEqual(icons["parking"], "car")

    def test_old_default_fruit_name_is_renamed_but_user_names_are_kept(self) -> None:
        conn = sqlite3.connect(self.db_path)
        conn.execute("update category_catalog set display_name = '水果鲜果' where id = 'fruit'")
        conn.execute("update category_catalog set display_name = '车辆充电' where id = 'car_charging'")
        conn.commit()
        conn.close()
        version_before = get_catalog(self.db_path)["version"]
        names = {item["id"]: item["display_name"] for item in get_catalog(self.db_path)["categories"]}
        self.assertEqual(names["fruit"], "水果生鲜")
        self.assertEqual(names["car_charging"], "加油充电")

        patch_category(self.db_path, "fruit", {"display_name": "我的水果"})
        names = {item["id"]: item["display_name"] for item in get_catalog(self.db_path)["categories"]}
        self.assertEqual(names["fruit"], "我的水果")
        self.assertGreater(get_catalog(self.db_path)["version"], version_before)


if __name__ == "__main__":
    unittest.main()
