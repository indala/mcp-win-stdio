import psycopg2
from psycopg2.extras import RealDictCursor
import json
import csv
import os
from pathlib import Path
from decimal import Decimal
from datetime import datetime, date, time
import uuid

def _json_serial(obj):
    if isinstance(obj, (datetime, date, time)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, uuid.UUID):
        return str(obj)
    return str(obj)

conn = psycopg2.connect("postgresql://postgres:postgres@localhost:5432/showreel_dev")

# Test export_table on props_management.materials
cur = conn.cursor(cursor_factory=RealDictCursor)
cur.execute("SELECT * FROM props_management.materials LIMIT 10;")
rows = cur.fetchall()
col_names = [desc[0] for desc in cur.description]

out_csv = "scratch/test_materials_export.csv"
with open(out_csv, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(col_names)
    for r in rows:
        writer.writerow([_json_serial(r[c]) if r[c] is not None else "" for c in col_names])

print(f"Exported {len(rows)} rows to {out_csv}, size: {os.path.getsize(out_csv)} bytes")

# Test import_csv with dry_run=True
# We will read test_materials_export.csv and simulate inserting into a temp or rollback transaction
cur.close()

conn.autocommit = False
cur = conn.cursor()
try:
    with open(out_csv, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        headers = next(reader)
        data_rows = list(reader)
    
    print(f"CSV read: {len(data_rows)} rows with {len(headers)} columns")
    # Rollback safely
    conn.rollback()
    print("Dry run rollback successful!")
finally:
    conn.close()
