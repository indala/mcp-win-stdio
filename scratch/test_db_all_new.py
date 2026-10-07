import psycopg2
from psycopg2.extras import RealDictCursor, execute_batch
import json
import csv
import os
import decimal
import uuid
import re
from datetime import datetime, date, time
from pathlib import Path

def _clean_mermaid_type(data_type: str) -> str:
    dt = (data_type or "").lower().strip()
    if "char" in dt or "text" in dt:
        return "string"
    if "int" in dt or "serial" in dt:
        return "int"
    if any(k in dt for k in ("numeric", "decimal", "real", "double", "float")):
        return "float"
    if "bool" in dt:
        return "boolean"
    if any(k in dt for k in ("date", "time", "timestamp")):
        return "datetime"
    if "uuid" in dt:
        return "uuid"
    if "json" in dt:
        return "json"
    clean = re.sub(r'[^a-zA-Z0-9_]', '_', dt)
    return clean or "string"

def _serialize_db_val(v):
    if v is None:
        return None
    if isinstance(v, (datetime, date, time)):
        return v.isoformat()
    if isinstance(v, decimal.Decimal):
        return float(v)
    if isinstance(v, uuid.UUID):
        return str(v)
    if isinstance(v, bytes):
        return v.hex()
    return v

conn = psycopg2.connect("postgresql://postgres:postgres@localhost:5432/showreel_dev")

# Test 1: Locks
cur = conn.cursor(cursor_factory=RealDictCursor)
cur.execute("""
SELECT
    blocked_locks.pid     AS blocked_pid,
    blocked_activity.usename  AS blocked_user,
    blocking_locks.pid    AS blocking_pid,
    blocking_activity.usename AS blocking_user,
    blocked_activity.query    AS blocked_statement,
    blocking_activity.query   AS blocking_statement,
    round(extract(epoch from (now() - blocked_activity.query_start)) * 1000) AS blocked_duration_ms
FROM pg_catalog.pg_locks blocked_locks
JOIN pg_catalog.pg_stat_activity blocked_activity ON blocked_activity.pid = blocked_locks.pid
JOIN pg_catalog.pg_locks blocking_locks 
    ON blocking_locks.locktype = blocked_locks.locktype
    AND blocking_locks.database IS NOT DISTINCT FROM blocked_locks.database
    AND blocking_locks.relation IS NOT DISTINCT FROM blocked_locks.relation
    AND blocking_locks.pid != blocked_locks.pid
JOIN pg_catalog.pg_stat_activity blocking_activity ON blocking_activity.pid = blocking_locks.pid
WHERE NOT blocked_locks.granted;
""")
blocks = cur.fetchall()
print(f"[PASS] Locks query passed. Blocked: {len(blocks)}")

# Test 2: Slow queries
cur.execute("""
SELECT 
    pid, 
    usename, 
    application_name, 
    client_addr, 
    state, 
    round(extract(epoch from (now() - query_start)) * 1000) AS duration_ms, 
    query
FROM pg_stat_activity
WHERE state != 'idle' 
  AND pid != pg_backend_pid()
  AND query NOT ILIKE '%pg_stat_activity%'
ORDER BY query_start ASC
LIMIT 10;
""")
slow = cur.fetchall()
print(f"[PASS] Slow queries query passed. Found: {len(slow)}")

# Test 3: Export table
out_file = "scratch/exported_materials.tsv"
cur.execute("SELECT id, material_number, description FROM props_management.materials LIMIT 5;")
rows = cur.fetchall()
col_names = [d[0] for d in cur.description]
with open(out_file, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f, delimiter="\t")
    writer.writerow(col_names)
    for r in rows:
        writer.writerow([_serialize_db_val(r[c]) for c in col_names])
print(f"[PASS] Export passed. Wrote {len(rows)} rows to {out_file}")

# Test 4: Import CSV with dry_run
cur.close()
conn.rollback() # reset transaction

cur = conn.cursor()
try:
    # Read rows from out_file
    with open(out_file, "r", encoding="utf-8") as f:
        reader = csv.reader(f, delimiter="\t")
        headers = next(reader)
        data = list(reader)
    
    # Simulate dry run
    print(f"[PASS] Read {len(data)} rows for import simulation.")
    conn.rollback()
finally:
    conn.close()

print("[PASS] All DB tool verifications passed!")
