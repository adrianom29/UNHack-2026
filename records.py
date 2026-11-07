"""Persistent daily logs for one local business; each item is analyzed separately."""
import sqlite3
from datetime import date
from pathlib import Path
from statistics import mean, stdev

DB_PATH = Path(__file__).with_name('smartprep.sqlite3')

def connect():
    db = sqlite3.connect(DB_PATH, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute('''CREATE TABLE IF NOT EXISTS daily_records (
        id INTEGER PRIMARY KEY, day TEXT NOT NULL, item TEXT NOT NULL,
        prepared INTEGER NOT NULL CHECK(prepared>=0),
        sold INTEGER NOT NULL CHECK(sold>=0 AND sold<=prepared),
        notes TEXT NOT NULL DEFAULT '', UNIQUE(day,item))''')
    db.execute('''CREATE TABLE IF NOT EXISTS regular_items (
        item TEXT PRIMARY KEY, active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)))''')
    # Seed existing products without reactivating products the owner has hidden.
    db.execute('INSERT OR IGNORE INTO regular_items(item) SELECT DISTINCT item FROM daily_records')
    db.commit()
    return db

def list_items():
    db=connect()
    try:
        return [dict(r) for r in db.execute('SELECT item,active FROM regular_items ORDER BY item')]
    finally:
        db.close()

def save_item(item, active=True):
    if not isinstance(item,str) or not 1<=len(item.strip())<=80:
        raise ValueError('Enter an item name of 1–80 characters.')
    if type(active) is not bool:
        raise ValueError('Active must be true or false.')
    db=connect()
    try:
        with db:
            db.execute('''INSERT INTO regular_items(item,active) VALUES(?,?)
                ON CONFLICT(item) DO UPDATE SET active=excluded.active''',(item.strip(),int(active)))
    finally:
        db.close()
    return {'items':list_items()}

def list_records():
    db=connect()
    try:
        return [dict(r) for r in db.execute('SELECT * FROM daily_records ORDER BY day DESC,id DESC')]
    finally:
        db.close()

def validate_record(day, item, prepared, sold, notes='', id=None):
    if not isinstance(day,str) or date.fromisoformat(day).isoformat()!=day:
        raise ValueError('Enter a valid date in YYYY-MM-DD format.')
    if day>date.today().isoformat():
        raise ValueError('Daily records cannot be dated in the future.')
    if not isinstance(item,str) or not 1<=len(item.strip())<=80:
        raise ValueError('Enter an item name of 1–80 characters.')
    item=item.strip()
    for value in (prepared,sold):
        if type(value) is not int or not 0<=value<=1_000_000:
            raise ValueError('Prepared and sold must be whole portions between 0 and 1,000,000.')
    if sold>prepared:
        raise ValueError('Sold cannot exceed prepared. Include all batches in prepared.')
    if not isinstance(notes,str) or len(notes)>500:
        raise ValueError('Notes must be at most 500 characters.')
    if id is not None and (type(id) is not int or id<1):
        raise ValueError('Invalid record ID.')
    return item

def save_record(day, item, prepared, sold, notes='', id=None):
    item=validate_record(day,item,prepared,sold,notes,id)
    db=connect()
    try:
        with db:
            if id is None:
                db.execute('INSERT INTO daily_records(day,item,prepared,sold,notes) VALUES(?,?,?,?,?)',
                           (day,item,prepared,sold,notes))
            else:
                cur=db.execute('UPDATE daily_records SET day=?,item=?,prepared=?,sold=?,notes=? WHERE id=?',
                               (day,item,prepared,sold,notes,id))
                if cur.rowcount!=1:
                    raise ValueError('Record no longer exists. Refresh the records.')
    except sqlite3.IntegrityError as exc:
        raise ValueError('This item already has a record for that date. Edit the existing row.') from exc
    finally:
        db.close()
    return {'records':list_records()}

def save_batch(day, rows):
    if not isinstance(rows,list) or not 1<=len(rows)<=200:
        raise ValueError('Enter between 1 and 200 items per save.')
    clean=[]
    names=set()
    for row in rows:
        if not isinstance(row,dict) or set(row)!={'item','prepared','sold'}:
            raise ValueError('Each row needs item, prepared and sold.')
        name=validate_record(day,**row)
        if name in names:
            raise ValueError('Each item can appear only once per day.')
        names.add(name)
        clean.append((day,name,row['prepared'],row['sold']))
    db=connect()
    try:
        with db:
            db.executemany('''INSERT INTO daily_records(day,item,prepared,sold) VALUES(?,?,?,?)
                ON CONFLICT(day,item) DO UPDATE SET prepared=excluded.prepared,sold=excluded.sold''',clean)
    finally:
        db.close()
    return {'records':list_records(),'saved':len(clean)}

def summary(item):
    rows=[r for r in list_records() if r['item']==item]
    # Zero-preparation days cannot reveal demand, even if recorded as zero sales.
    usable=[r for r in rows if r['prepared']>0]
    sales=[r['sold'] for r in usable]
    return dict(item=item, count=len(usable), total_records=len(rows),
                excluded_zero_prepared=len(rows)-len(usable),
                possible_stockouts=sum(r['sold']==r['prepared'] for r in usable),
                mu=mean(sales) if sales else None,
                sigma=stdev(sales) if len(sales)>=2 else None,
                baseline=usable[0]['prepared'] if usable else None,
                first_day=usable[-1]['day'] if usable else None,
                last_day=usable[0]['day'] if usable else None)
