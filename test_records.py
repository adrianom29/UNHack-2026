import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
import records


class RecordTests(unittest.TestCase):
    def test_regular_menu_without_sales_and_restore(self):
        records.save_item("Soup", price=6, cost=2)
        records.save_item("Bread", price=3, cost=1)
        self.assertEqual(records.list_records(), [])
        self.assertEqual(len(records.list_items()), 2)
        records.save_item("Soup", False)
        self.assertEqual(
            next(i for i in records.list_items() if i["item"] == "Soup")["active"], 0
        )
        records.save_record("2026-01-01", "Soup", 20, 10)
        self.assertEqual(
            next(i for i in records.list_items() if i["item"] == "Soup")["active"], 0
        )
        records.save_item("Soup", True)
        self.assertEqual(
            next(i for i in records.list_items() if i["item"] == "Soup")["active"], 1
        )
        self.assertEqual(len(records.list_records()), 1)
        records.save_item(" Soup ")
        self.assertEqual(len(records.list_items()), 2)
        for item in ["", " " * 3, "x" * 81]:
            with self.assertRaises(ValueError):
                records.save_item(item, price=1, cost=1)
        with self.assertRaises(ValueError):
            records.save_item("Cake")

    def test_existing_records_seed_menu(self):
        records.save_record("2026-01-01", "Existing soup", 20, 10)
        self.assertEqual(
            records.list_items(),
            [{"item": "Existing soup", "active": 1, "price": None, "cost": None}],
        )

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.original = records.DB_PATH
        records.DB_PATH = Path(self.tmp.name) / "test.sqlite3"

    def tearDown(self):
        records.DB_PATH = self.original
        self.tmp.cleanup()

    def test_persistence_edit_and_summary(self):
        records.save_record("2026-01-01", "Soup", 100, 80)
        records.save_record("2026-01-02", "Soup", 100, 100)
        records.save_record("2026-01-03", "Soup", 0, 0)
        records.save_record("2026-01-01", "Sandwich", 500, 400)
        s = records.summary("Soup")
        self.assertEqual(s["count"], 2)
        self.assertEqual(s["excluded_zero_prepared"], 1)
        self.assertEqual(s["possible_stockouts"], 1)
        self.assertEqual(s["average_sold"], 90)
        self.assertAlmostEqual(s["sales_std"], 14.1421356237)
        self.assertEqual(s["baseline"], 100)
        row = next(
            r
            for r in records.list_records()
            if r["item"] == "Soup" and r["day"] == "2026-01-01"
        )
        records.save_record("2026-01-01", "Soup", 110, 90, "corrected", row["id"])
        self.assertEqual(records.summary("Soup")["average_sold"], 95)
        self.assertEqual(len(records.list_records()), 4)

    def test_invalid_and_duplicate(self):
        for args in [
            ("bad", "Soup", 10, 5),
            ("2026-01-01", "", 10, 5),
            ("2026-01-01", "Soup", 10, 11),
            ("2026-01-01", "Soup", 10.5, 5),
            ("2026-01-01", "Soup", -1, 0),
            ("2026-01-01", "Soup", True, 0),
        ]:
            with self.assertRaises(ValueError):
                records.save_record(*args)
        records.save_record("2026-01-01", "Soup", 10, 5)
        with self.assertRaises(ValueError):
            records.save_record("2026-01-01", "Soup", 10, 6)
        self.assertEqual(records.list_records()[0]["sold"], 5)

    def test_small_sample(self):
        self.assertIsNone(records.summary("Soup")["average_sold"])
        records.save_record("2026-01-01", "Soup", 10, 5)
        self.assertIsNone(records.summary("Soup")["sales_std"])

    def test_batch_updates_and_atomic_validation(self):
        records.save_record("2026-01-01", "Soup", 100, 80, "Keep this note")
        records.save_batch(
            "2026-01-01",
            [
                dict(item="Soup", prepared=90, sold=85),
                dict(item="Bread", prepared=20, sold=10),
            ],
        )
        self.assertEqual(len(records.list_records()), 2)
        soup = next(r for r in records.list_records() if r["item"] == "Soup")
        self.assertEqual(soup["notes"], "Keep this note")
        self.assertEqual(soup["sold"], 85)
        with self.assertRaises(ValueError):
            records.save_batch(
                "2026-01-01",
                [
                    dict(item="Soup", prepared=200, sold=100),
                    dict(item="Bread", prepared=1, sold=10),
                ],
            )
        self.assertEqual(
            next(r for r in records.list_records() if r["item"] == "Soup")["sold"], 85
        )
        with self.assertRaises(ValueError):
            records.save_batch(
                "2026-01-01", [dict(item="Soup", prepared=10, sold=5)] * 2
            )

    def test_import_adds_replaces_and_is_atomic(self):
        records.save_item("Soup", price=6, cost=2)
        records.save_record("2026-01-01", "Soup", 100, 80, "old note")
        result = records.import_records(
            [
                dict(day="2026-01-01", item="Soup", prepared=90, sold=85, notes="new"),
                dict(day="2026-01-02", item="Soup", prepared=90, sold=90),
                dict(day="2026-01-02", item="Bread", prepared=20, sold=10, notes=""),
            ]
        )
        self.assertEqual(
            (result["added"], result["replaced"], result["new_items"]), (2, 1, 1)
        )
        soup = next(r for r in records.list_records() if r["day"] == "2026-01-01")
        self.assertEqual((soup["sold"], soup["notes"]), (85, "new"))
        self.assertEqual(
            records.get_item("Bread"),
            {"item": "Bread", "active": 1, "price": None, "cost": None},
        )
        for bad in [
            [dict(day="2026-01-03", item="Soup", prepared=1, sold=1),
             dict(day="2026-01-04", item="Soup", prepared=1, sold=2)],
            [dict(day="2026-01-03", item="Soup", prepared=1, sold=1)] * 2,
            [dict(day="01/03/2026", item="Soup", prepared=1, sold=1)],
            [dict(day="2026-01-03", item="Soup", prepared=1, sold=1, waste=0)],
            [],
        ]:
            with self.assertRaises(ValueError):
                records.import_records(bad)
        self.assertEqual(len(records.list_records()), 3)
        with self.assertRaisesRegex(ValueError, "Record 2"):
            records.import_records([
                dict(day="2026-01-03", item="Soup", prepared=1, sold=1),
                dict(day="2026-01-04", item="", prepared=1, sold=1),
            ])

    def test_delete_all_records_keeps_menu(self):
        records.save_item("Soup", price=6, cost=2)
        records.save_record("2026-01-01", "Soup", 10, 5)
        records.save_record("2026-01-02", "Bread", 10, 5)
        for bad in [False, "yes", 1]:
            with self.assertRaises(ValueError):
                records.delete_all_records(bad)
        self.assertEqual(len(records.list_records()), 2)
        self.assertEqual(records.delete_all_records(True)["deleted_records"], 2)
        self.assertEqual(records.list_records(), [])
        self.assertEqual(
            [i["item"] for i in records.list_items()], ["Bread", "Soup"]
        )
        self.assertEqual(records.get_item("Soup")["price"], 6)

    def test_menu_price_and_cost_edits(self):
        records.save_item("Soup", price=12, cost=5)
        for price, cost in [(-1, 5), (12, float("nan")), ("12", 5), (12, True)]:
            with self.assertRaises(ValueError):
                records.save_item("Soup", price=price, cost=cost)
        records.save_record("2026-01-01", "Soup", 100, 80)
        records.save_item("Soup", price=13, cost=5.5)
        s = records.summary("Soup")
        self.assertEqual((s["price"], s["cost"]), (13, 5.5))
        # Hiding keeps the price.
        records.save_item("Soup", False)
        self.assertEqual(records.get_item("Soup")["price"], 13)
        # The menu table saves one field at a time; the other is kept.
        records.save_item("Soup", False, price=14)
        records.save_item("Soup", False, cost=6)
        self.assertEqual(
            records.get_item("Soup"),
            {"item": "Soup", "active": 0, "price": 14, "cost": 6},
        )
        self.assertEqual(len(records.list_items()), 1)

    def test_old_database_gets_menu_prices(self):
        import sqlite3

        db = sqlite3.connect(records.DB_PATH)
        db.execute("""CREATE TABLE daily_records (
            id INTEGER PRIMARY KEY, day TEXT NOT NULL, item TEXT NOT NULL,
            prepared INTEGER NOT NULL, sold INTEGER NOT NULL,
            price REAL, cost REAL,
            notes TEXT NOT NULL DEFAULT '', UNIQUE(day,item))""")
        db.execute("""CREATE TABLE regular_items (
            item TEXT PRIMARY KEY, active INTEGER NOT NULL DEFAULT 1)""")
        db.executemany(
            "INSERT INTO daily_records(day,item,prepared,sold,price,cost) VALUES(?,?,?,?,?,?)",
            [
                ("2026-01-01", "Soup", 10, 5, 10, 4),
                ("2026-01-02", "Soup", 10, 6, 12, 5),
                ("2026-01-01", "Bread", 10, 6, None, None),
            ],
        )
        db.commit()
        db.close()
        self.assertEqual(records.summary("Soup")["price"], 12)
        self.assertEqual(records.summary("Soup")["cost"], 5)
        self.assertIsNone(records.summary("Bread")["price"])
        self.assertNotIn("price", records.list_records()[0])
        records.save_record("2026-01-03", "Bread", 10, 7)

    def test_forecast(self):
        from smartprep import forecast

        target = date(2026, 1, 3)
        with self.assertRaises(ValueError):
            forecast("Soup", target=target)
        records.save_record("2026-01-01", "Soup", 100, 70)
        records.save_record("2026-01-02", "Soup", 100, 90)
        with self.assertRaisesRegex(ValueError, "Manage menu"):
            forecast("Soup", target=target)
        records.save_item("Soup", price=12, cost=5)
        r = forecast("Soup", target=target)
        self.assertEqual(r["target_day"], "2026-01-03")
        self.assertTrue(70 < r["predicted_demand"] < 90)
        self.assertTrue(r["provisional"])
        self.assertEqual((r["days_used"], r["sellouts_adjusted"]), (2, 0))
        self.assertEqual(r["backtest"]["days"], [])
        self.assertEqual(r["last_quantity"], 100)
        self.assertLess(r["recommended_quantity"], 100)
        # Actual past averages: waste (30+10)/2, profit (12*70-500 + 12*90-500)/2.
        self.assertEqual(r["previous_waste"], 20)
        self.assertEqual(r["previous_profit"], 460)
        self.assertLess(r["predicted_waste"], 20)
        self.assertGreater(r["predicted_profit"], 460)
        self.assertGreaterEqual(
            forecast("Soup", 0.95, target)["recommended_quantity"],
            r["recommended_quantity"],
        )
        # Records older than the history window are not used.
        with self.assertRaisesRegex(ValueError, "within the last"):
            forecast("Soup", target=date(2027, 1, 1))

    def test_plan_combines_items(self):
        from smartprep import plan

        self.assertEqual(plan()["items"], [])
        self.assertIsNone(plan()["totals"]["waste_reduction_pct"])
        records.save_item("Soup", price=12, cost=5)
        records.save_item("Bread", price=4, cost=1)
        records.save_item("Cake", price=6, cost=2)
        records.save_item("Old pie", False, price=6, cost=2)
        for day, soup, bread in [("2026-01-01", 70, 30), ("2026-01-02", 90, 34)]:
            records.save_record(day, "Soup", 100, soup)
            records.save_record(day, "Bread", 40, bread)
            records.save_record(day, "Old pie", 10, 5)
        r = plan(target=date(2026, 1, 3))
        self.assertEqual([i["item"] for i in r["items"]], ["Bread", "Soup"])
        # Too little history to check against past days: model estimate.
        self.assertEqual(r["totals"]["source"], "estimate")
        self.assertEqual([w["item"] for w in r["waiting"]], ["Cake"])
        t = r["totals"]
        self.assertEqual(t["previous_waste"], 20 + 8)
        self.assertAlmostEqual(
            t["predicted_waste"], sum(i["predicted_waste"] for i in r["items"])
        )
        self.assertAlmostEqual(
            t["waste_reduction_pct"],
            100 * (t["previous_waste"] - t["predicted_waste"]) / t["previous_waste"],
        )
        self.assertAlmostEqual(
            t["profit_increase_pct"],
            100 * (t["predicted_profit"] - t["previous_profit"]) / t["previous_profit"],
        )
        self.assertGreater(t["waste_reduction_pct"], 0)
        self.assertGreater(t["profit_increase_pct"], 0)

    def test_percent_change_needs_positive_base(self):
        from smartprep import percent_change

        self.assertEqual(percent_change(200, 250), 25)
        self.assertIsNone(percent_change(0, 10))
        self.assertIsNone(percent_change(-50, 10))

    def test_delete_item_and_day(self):
        records.save_item("Soup", price=12, cost=5)
        records.save_item("Bread", price=4, cost=1)
        records.save_record("2026-01-01", "Soup", 10, 5)
        records.save_record("2026-01-02", "Soup", 10, 6)
        records.save_record("2026-01-01", "Bread", 10, 7)
        result = records.delete_item("Soup")
        self.assertEqual(result["deleted_records"], 2)
        # Deleted items do not come back from their records.
        self.assertEqual([i["item"] for i in records.list_items()], ["Bread"])
        self.assertEqual([r["item"] for r in records.list_records()], ["Bread"])
        with self.assertRaises(ValueError):
            records.delete_item("Soup")
        records.save_record("2026-01-01", "Cake", 10, 4)
        records.save_record("2026-01-02", "Bread", 10, 8)
        self.assertEqual(records.delete_day("2026-01-01")["deleted_records"], 2)
        self.assertEqual(
            [(r["day"], r["item"]) for r in records.list_records()],
            [("2026-01-02", "Bread")],
        )
        # Menu items stay; only that day's records go.
        self.assertEqual(
            [i["item"] for i in records.list_items()], ["Bread", "Cake"]
        )
        for bad in ["2026-01-01", "", None, 20260102]:
            with self.assertRaises(ValueError):
                records.delete_day(bad)

    def test_http_roundtrip(self):
        import json
        import threading
        from urllib.request import Request, urlopen
        from urllib.error import HTTPError
        from smartprep import Handler, ThreadingHTTPServer

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        base = f"http://127.0.0.1:{server.server_port}"

        def post(path, data):
            request = Request(
                base + path,
                json.dumps(data).encode(),
                {"Content-Type": "application/json"},
            )
            with urlopen(request) as response:
                return json.load(response)

        try:
            post("/items", dict(item="Soup", price=12, cost=5, active=True))
            recent = [(date.today() - timedelta(days=n)).isoformat() for n in (2, 1)]
            for day, sold in zip(recent, (80, 100)):
                post("/records", dict(day=day, item="Soup", prepared=100, sold=sold))
            with urlopen(base + "/plan?service_level=0") as response:
                result = json.load(response)
            soup = result["items"][0]
            # The sold-out day means demand was above what sold.
            self.assertGreater(soup["predicted_demand"], 90)
            self.assertEqual(soup["sellouts_adjusted"], 1)
            with self.assertRaises(HTTPError) as failure:
                urlopen(base + "/plan?service_level=2")
            self.assertEqual(failure.exception.code, 400)
            failure.exception.close()
            first = post("/records", dict(day="2026-01-03", item="Soup", prepared=5, sold=5))
            self.assertEqual(
                post("/records/delete-day", dict(day="2026-01-03"))["deleted_records"],
                1,
            )
            post("/items", dict(item="Cake", price=6, cost=2, active=True))
            self.assertEqual(
                [i["item"] for i in post("/items/delete", dict(item="Cake"))["items"]],
                ["Soup"],
            )
            with self.assertRaises(HTTPError) as failure:
                post(
                    "/records",
                    dict(
                        day="2026-01-03",
                        item="Soup",
                        prepared=10,
                        sold=11,
                    ),
                )
            self.assertEqual(failure.exception.code, 400)
            with urlopen(base + "/records") as response:
                self.assertEqual(len(json.load(response)["records"]), 2)
            imported = post(
                "/records/import",
                dict(rows=[dict(day="2026-01-05", item="Soup", prepared=9, sold=7)]),
            )
            self.assertEqual((imported["added"], len(imported["records"])), (1, 3))
        finally:
            server.shutdown()
            server.server_close()
            worker.join()


if __name__ == "__main__":
    unittest.main()
