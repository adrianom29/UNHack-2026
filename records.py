"""Persistent daily logs for one local business; each item is analyzed separately."""

import math
import sqlite3
from datetime import date
from pathlib import Path
from statistics import mean, stdev

DB_PATH = Path(__file__).with_name("smartprep.sqlite3")


def connect():
    db = sqlite3.connect(DB_PATH, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("""CREATE TABLE IF NOT EXISTS daily_records (
        id INTEGER PRIMARY KEY, day TEXT NOT NULL, item TEXT NOT NULL,
        prepared INTEGER NOT NULL CHECK(prepared>=0),
        sold INTEGER NOT NULL CHECK(sold>=0 AND sold<=prepared),
        notes TEXT NOT NULL DEFAULT '', UNIQUE(day,item))""")
    db.execute(
        """CREATE TABLE IF NOT EXISTS regular_items (
        item TEXT PRIMARY KEY, active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
        price REAL, cost REAL)"""
    )
    # Older databases were created before menu items had a price and cost.
    item_columns = {r["name"] for r in db.execute("PRAGMA table_info(regular_items)")}
    for column in ("price", "cost"):
        if column not in item_columns:
            db.execute(f"ALTER TABLE regular_items ADD COLUMN {column} REAL")
    # Seed existing products without reactivating products the owner has hidden.
    db.execute(
        "INSERT OR IGNORE INTO regular_items(item) SELECT DISTINCT item FROM daily_records"
    )
    # A briefly released version stored price and cost on each daily record.
    # Carry the latest of those onto menu items that do not have a price yet.
    record_columns = {r["name"] for r in db.execute("PRAGMA table_info(daily_records)")}
    if {"price", "cost"} <= record_columns:
        db.execute("""UPDATE regular_items SET (price, cost) = (
            SELECT r.price, r.cost FROM daily_records r
            WHERE r.item = regular_items.item AND r.price IS NOT NULL
            ORDER BY r.day DESC, r.id DESC LIMIT 1)
            WHERE price IS NULL AND EXISTS (
            SELECT 1 FROM daily_records r
            WHERE r.item = regular_items.item AND r.price IS NOT NULL)""")
    db.commit()
    return db


def list_items():
    db = connect()
    try:
        return [
            dict(r)
            for r in db.execute(
                "SELECT item,active,price,cost FROM regular_items ORDER BY item"
            )
        ]
    finally:
        db.close()


def clean_name(item):
    if not isinstance(item, str) or not 1 <= len(item.strip()) <= 80:
        raise ValueError("Enter an item name of 1–80 characters.")
    return item.strip()


def check_amount(value):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not 0 <= value <= 1_000_000
    ):
        raise ValueError("Price and cost must be amounts between 0 and 1,000,000.")


def save_item(item, active=True, price=None, cost=None):
    """Add or change a menu item. Price and cost left as None are kept."""
    item = clean_name(item)
    if type(active) is not bool:
        raise ValueError("Active must be true or false.")
    for value in (price, cost):
        if value is not None:
            check_amount(value)
    db = connect()

    try:
        with db:
            exists = db.execute(
                "SELECT 1 FROM regular_items WHERE item=?", (item,)
            ).fetchone()
            if not exists and (price is None or cost is None):
                raise ValueError("Enter a price and cost for the new item.")
            db.execute(
                """INSERT INTO regular_items(item,active,price,cost) VALUES(?,?,?,?)
                ON CONFLICT(item) DO UPDATE SET active=excluded.active,
                price=COALESCE(excluded.price,price),
                cost=COALESCE(excluded.cost,cost)""",
                (item, int(active), price, cost),
            )
    finally:
        db.close()
    return {"items": list_items()}


def get_item(item):
    db = connect()
    try:
        row = db.execute(
            "SELECT item,active,price,cost FROM regular_items WHERE item=?", (item,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        db.close()


def delete_item(item):
    """Remove an item from the menu together with all of its daily records."""
    item = clean_name(item)
    db = connect()
    try:
        with db:
            removed = db.execute(
                "DELETE FROM daily_records WHERE item=?", (item,)
            ).rowcount
            if db.execute("DELETE FROM regular_items WHERE item=?", (item,)).rowcount != 1:
                raise ValueError("That item is no longer on the menu. Refresh the page.")
    finally:
        db.close()
    return {"items": list_items(), "records": list_records(), "deleted_records": removed}


def delete_day(day):
    """Remove every item's record for one date."""
    if not isinstance(day, str):
        raise ValueError("Enter a valid date in YYYY-MM-DD format.")
    db = connect()
    try:
        with db:
            removed = db.execute("DELETE FROM daily_records WHERE day=?", (day,)).rowcount
            if not removed:
                raise ValueError("There are no records for that day. Refresh the records.")
    finally:
        db.close()
    return {"records": list_records(), "deleted_records": removed}


def delete_all_records(confirm=False):
    """Remove every daily record. Menu items, prices and costs are kept."""
    if confirm is not True:
        raise ValueError("Confirm that all records should be deleted.")
    db = connect()
    try:
        with db:
            removed = db.execute("DELETE FROM daily_records").rowcount
    finally:
        db.close()
    return {"records": [], "deleted_records": removed}


def list_records():
    db = connect()
    try:
        return [
            dict(r)
            for r in db.execute(
                """SELECT id,day,item,prepared,sold,notes FROM daily_records
                ORDER BY day DESC,id DESC"""
            )
        ]
    finally:
        db.close()


def validate_record(day, item, prepared, sold, notes="", id=None):
    if not isinstance(day, str) or date.fromisoformat(day).isoformat() != day:
        raise ValueError("Enter a valid date in YYYY-MM-DD format.")
    if day > date.today().isoformat():
        raise ValueError("Daily records cannot be dated in the future.")
    item = clean_name(item)
    for value in (prepared, sold):
        if type(value) is not int or not 0 <= value <= 1_000_000:
            raise ValueError(
                "Prepared and sold must be whole portions between 0 and 1,000,000."
            )
    if sold > prepared:
        raise ValueError(
            "Sold cannot exceed prepared. Include all batches in prepared."
        )
    if not isinstance(notes, str) or len(notes) > 500:
        raise ValueError("Notes must be at most 500 characters.")
    if id is not None and (type(id) is not int or id < 1):
        raise ValueError("Invalid record ID.")
    return item


def save_record(day, item, prepared, sold, notes="", id=None):
    item = validate_record(day, item, prepared, sold, notes, id)
    db = connect()
    try:
        with db:
            if id is None:
                db.execute(
                    "INSERT INTO daily_records(day,item,prepared,sold,notes) VALUES(?,?,?,?,?)",
                    (day, item, prepared, sold, notes),
                )
            else:
                cur = db.execute(
                    "UPDATE daily_records SET day=?,item=?,prepared=?,sold=?,notes=? WHERE id=?",
                    (day, item, prepared, sold, notes, id),
                )
                if cur.rowcount != 1:
                    raise ValueError("Record no longer exists. Refresh the records.")
    except sqlite3.IntegrityError as exc:
        raise ValueError(
            "This item already has a record for that date. Edit the existing row."
        ) from exc
    finally:
        db.close()
    return {"records": list_records()}


def save_batch(day, rows):
    if not isinstance(rows, list) or not 1 <= len(rows) <= 200:
        raise ValueError("Enter between 1 and 200 items per save.")
    clean = []
    names = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"item", "prepared", "sold"}:
            raise ValueError("Each row needs item, prepared and sold.")
        name = validate_record(day, **row)
        if name in names:
            raise ValueError("Each item can appear only once per day.")
        names.add(name)
        clean.append((day, name, row["prepared"], row["sold"]))
    db = connect()
    try:
        with db:
            db.executemany(
                """INSERT INTO daily_records(day,item,prepared,sold) VALUES(?,?,?,?)
                ON CONFLICT(day,item) DO UPDATE SET prepared=excluded.prepared,sold=excluded.sold""",
                clean,
            )
    finally:
        db.close()
    return {"records": list_records(), "saved": len(clean)}


IMPORT_LIMIT = 20_000


def import_records(rows):
    """Add many days of records at once, e.g. from an exported CSV file.

    Each row needs day, item, prepared and sold; notes are optional. A row for
    a day and item that is already saved replaces it. Nothing is saved unless
    every row is valid. Items not yet on the menu are added without a price.
    """
    if not isinstance(rows, list) or not 1 <= len(rows) <= IMPORT_LIMIT:
        raise ValueError(f"Import between 1 and {IMPORT_LIMIT:,} records at a time.")
    clean = {}
    for number, row in enumerate(rows, 1):
        try:
            if not isinstance(row, dict) or not (
                {"day", "item", "prepared", "sold"} <= set(row)
                <= {"day", "item", "prepared", "sold", "notes"}
            ):
                raise ValueError("Each record needs day, item, prepared and sold.")
            notes = row.get("notes", "")
            name = validate_record(
                row["day"], row["item"], row["prepared"], row["sold"], notes
            )
        except ValueError as exc:
            raise ValueError(f"Record {number}: {exc}") from exc
        key = (row["day"], name)
        if key in clean:
            raise ValueError(
                f"Record {number}: {name} appears more than once on {row['day']}."
            )
        clean[key] = (row["day"], name, row["prepared"], row["sold"], notes)
    db = connect()
    try:
        with db:
            existing = {
                (r["day"], r["item"])
                for r in db.execute("SELECT day,item FROM daily_records")
            }
            db.executemany(
                """INSERT INTO daily_records(day,item,prepared,sold,notes) VALUES(?,?,?,?,?)
                ON CONFLICT(day,item) DO UPDATE SET prepared=excluded.prepared,
                sold=excluded.sold,notes=excluded.notes""",
                clean.values(),
            )
            new_items = db.execute(
                "INSERT OR IGNORE INTO regular_items(item) SELECT DISTINCT item FROM daily_records"
            ).rowcount
    finally:
        db.close()
    replaced = len(clean.keys() & existing)
    return {
        "records": list_records(),
        "added": len(clean) - replaced,
        "replaced": replaced,
        "new_items": new_items,
    }


def item_history(item):
    """An item's days with something made, oldest first."""
    return [
        r
        for r in reversed(list_records())
        if r["item"] == item and r["prepared"] > 0
    ]


def summary(item):
    rows = [r for r in list_records() if r["item"] == item]
    # Zero-preparation days cannot reveal demand, even if recorded as zero sales.
    usable = [r for r in rows if r["prepared"] > 0]
    sales = [r["sold"] for r in usable]
    menu = get_item(item) or {}
    price, cost = menu.get("price"), menu.get("cost")
    return dict(
        item=item,
        count=len(usable),
        total_records=len(rows),
        excluded_zero_prepared=len(rows) - len(usable),
        possible_stockouts=sum(r["sold"] == r["prepared"] for r in usable),
        # Plain sales statistics for display; forecasts use demand.estimate().
        average_sold=mean(sales) if sales else None,
        sales_std=stdev(sales) if len(sales) >= 2 else None,
        price=price,
        cost=cost,
        # Actual averages per day, valued at today's menu price and cost.
        previous_waste=mean(r["prepared"] - r["sold"] for r in usable) if usable else None,
        previous_profit=(
            mean(price * r["sold"] - cost * r["prepared"] for r in usable)
            if usable and price is not None and cost is not None
            else None
        ),
        baseline=usable[0]["prepared"] if usable else None,
        first_day=usable[-1]["day"] if usable else None,
        last_day=usable[0]["day"] if usable else None,
    )
