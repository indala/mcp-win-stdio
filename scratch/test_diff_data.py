import psycopg2
from psycopg2.extras import RealDictCursor
import json

conn = psycopg2.connect("postgresql://postgres:postgres@localhost:5432/showreel_dev")
cur = conn.cursor(cursor_factory=RealDictCursor)

# Let's test diffing materials with themselves (10 rows vs 10 rows)
cur.execute("SELECT id, material_number, description, base_uom_id FROM props_management.materials LIMIT 10;")
rows1 = cur.fetchall()

# Simulate a second dataset with 1 row changed, 1 row added, 1 row removed
rows2 = [dict(r) for r in rows1]
rows2[0]["description"] = "MODIFIED DESCRIPTION"
removed = rows2.pop()
rows2.append({"id": "99999999-9999-9999-9999-999999999999", "material_number": "NEW99", "description": "NEW ITEM", "base_uom_id": None})

key_cols = ["id"]
map1 = {tuple(str(r[k]) for k in key_cols): r for r in rows1}
map2 = {tuple(str(r[k]) for k in key_cols): r for r in rows2}

keys1 = set(map1.keys())
keys2 = set(map2.keys())

missing_in_target = [map1[k] for k in (keys1 - keys2)]
missing_in_source = [map2[k] for k in (keys2 - keys1)]

modified = []
identical = 0
for k in (keys1 & keys2):
    r1 = map1[k]
    r2 = map2[k]
    diffs = {}
    for col in set(list(r1.keys()) + list(r2.keys())):
        v1 = str(r1.get(col)) if r1.get(col) is not None else None
        v2 = str(r2.get(col)) if r2.get(col) is not None else None
        if v1 != v2:
            diffs[col] = {"source": v1, "target": v2}
    if diffs:
        modified.append({"key": list(k), "diffs": diffs})
    else:
        identical += 1

print(f"Identical: {identical}")
print(f"Modified: {len(modified)}")
print(f"Missing in target: {len(missing_in_target)}")
print(f"Missing in source: {len(missing_in_source)}")
print("Sample modified:", json.dumps(modified, indent=2))
