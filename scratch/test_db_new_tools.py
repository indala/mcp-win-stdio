import psycopg2
from psycopg2.extras import RealDictCursor
import json

conn = psycopg2.connect("postgresql://postgres:postgres@localhost:5432/showreel_dev")
cur = conn.cursor(cursor_factory=RealDictCursor)

# Test 1: ERD generation for props_management
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

# Table columns
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

print(f"Total FKs: {len(fks)}, Total Columns: {len(cols)}")
table_cols = {}
for c in cols:
    t = c["table_name"]
    table_cols.setdefault(t, []).append(c)

# Generate sample Mermaid
lines = ["erDiagram"]
for fk in fks[:5]:
    lines.append(f'    {fk["foreign_table_name"]} ||--o{{ {fk["table_name"]} : "{fk["column_name"]}"')

for t in ["materials", "props_inventory"]:
    if t in table_cols:
        lines.append(f"    {t} {{")
        for c in table_cols[t][:5]:
            pk_suffix = " PK" if c["is_pk"] else ""
            lines.append(f"        {c['data_type']} {c['column_name']}{pk_suffix}")
        lines.append("    }")

mermaid_text = "\n".join(lines)
print("\n--- SAMPLE MERMAID ERD ---")
print(mermaid_text)
