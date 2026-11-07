import tempfile
import unittest
from pathlib import Path
import records


class RecordTests(unittest.TestCase):
    def test_regular_menu_without_sales_and_restore(self):
        records.save_item("Soup")
        records.save_item("Bread")
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
                records.save_item(item)

    def test_existing_records_seed_menu(self):
        records.save_record("2026-01-01", "Existing soup", 20, 10)
        self.assertEqual(records.list_items(), [{"item": "Existing soup", "active": 1}])

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
        self.assertEqual(s["mu"], 90)
        self.assertAlmostEqual(s["sigma"], 14.1421356237)
        self.assertEqual(s["baseline"], 100)
        row = next(
            r
            for r in records.list_records()
            if r["item"] == "Soup" and r["day"] == "2026-01-01"
        )
        records.save_record("2026-01-01", "Soup", 110, 90, "corrected", row["id"])
        self.assertEqual(records.summary("Soup")["mu"], 95)
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
        self.assertIsNone(records.summary("Soup")["mu"])
        records.save_record("2026-01-01", "Soup", 10, 5)
        self.assertIsNone(records.summary("Soup")["sigma"])

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
            for day, sold in [("2026-01-01", 80), ("2026-01-02", 100)]:
                post("/records", dict(day=day, item="Soup", prepared=100, sold=sold))
            with urlopen(base + "/history-summary?item=Soup") as response:
                s = json.load(response)
            result = post(
                "/calculate",
                dict(p=12, c=5, mu=s["mu"], sigma=s["sigma"], baseline=s["baseline"]),
            )
            self.assertEqual(result["inputs"]["mean"], 90)
            self.assertEqual(s["possible_stockouts"], 1)
            with self.assertRaises(HTTPError) as failure:
                post(
                    "/records",
                    dict(day="2026-01-03", item="Soup", prepared=10, sold=11),
                )
            self.assertEqual(failure.exception.code, 400)
            with urlopen(base + "/records") as response:
                self.assertEqual(len(json.load(response)["records"]), 2)
        finally:
            server.shutdown()
            server.server_close()
            worker.join()


if __name__ == "__main__":
    unittest.main()
