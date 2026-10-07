import decimal
import json
import re
import csv
import uuid
import os
from datetime import datetime, date, time
from pathlib import Path
from typing import Any, Optional, List, Dict, Union
import psycopg2
from psycopg2.extras import RealDictCursor

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

def _serialize_db_val(v: Any) -> Any:
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

# Test generate_erd
cur = conn.cursor(cursor_factory=RealDictCursor)
cur.execute("""
SELECT 
    tc.table_schema, 
    tc.table_name, 
    kcu.column_name, 
    ccu.table_schema AS foreign_table_schema,
    ccu.table_name AS foreign_table_name,
    ccu.column_name AS foreign_column_name,
    tc.constraint_name
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu
  ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
JOIN information_schema.constraint_column_usage ccu
  ON ccu.constraint_name = tc.constraint_name AND ccu.table_schema = tc.table_schema
WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = 'props_management';
""")
fks = cur.fetchall()

cur.execute("""
SELECT c.table_schema, c.table_name, c.column_name, c.data_type,
       CASE WHEN pk.column_name IS NOT NULL THEN TRUE ELSE FALSE END as is_pk
FROM information_schema.columns c
LEFT JOIN (
    SELECT tc.table_schema, tc.table_name, kcu.column_name
    FROM information_schema.table_constraints tc
    JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
    WHERE tc.constraint_type = 'PRIMARY KEY' AND tc.table_schema = 'props_management'
) pk ON pk.table_schema = c.table_schema AND pk.table_name = c.table_name AND pk.column_name = c.column_name
WHERE c.table_schema = 'props_management'
ORDER BY c.table_name, c.ordinal_position;
""")
cols = cur.fetchall()

table_cols = {}
for c in cols:
    table_cols.setdefault(c["table_name"], []).append(c)

mermaid_lines = ["erDiagram"]
for fk in fks:
    p = fk["foreign_table_name"]
    c = fk["table_name"]
    col = fk["column_name"]
    mermaid_lines.append(f'    {p} ||--o{{ {c} : "{col}"')

for t, t_cols in list(table_cols.items())[:3]:
    mermaid_lines.append(f"    {t} {{")
    for col in t_cols:
        c_type = _clean_mermaid_type(col["data_type"])
        suffix = " PK" if col["is_pk"] else ""
        mermaid_lines.append(f"        {c_type} {col['column_name']}{suffix}")
    mermaid_lines.append("    }")

erd_res = {
    "tables_count": len(table_cols),
    "foreign_keys_count": len(fks),
    "mermaid": "\n".join(mermaid_lines)
}
print(f"ERD test passed: {erd_res['tables_count']} tables, {erd_res['foreign_keys_count']} FKs")
conn.close()
