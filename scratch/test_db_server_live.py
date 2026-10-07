import sys
import os
from pathlib import Path

# Add packages to path
for p in Path("packages").glob("*/src"):
    sys.path.insert(0, str(p.resolve()))

import json
from mcp_win_stdio.db.server import (
    generate_erd,
    diff_data,
    list_slow_queries,
    get_locks,
    export_table,
    import_csv
)

print("1. Testing generate_erd...")
erd = generate_erd(schema="props_management", tables=["materials", "props_inventory"])
print("   ERD status:", erd.get("foreign_keys_count"), "FKs,", erd.get("tables_count"), "tables")
assert "mermaid" in erd

print("2. Testing diff_data...")
diff = diff_data(
    table1="materials",
    schema1="props_management"
)
print("   Diff status: total source rows:", diff.get("total_source_rows"), "identical:", diff.get("identical_rows_count"))
assert diff.get("identical_rows_count") == diff.get("total_source_rows")

print("3. Testing list_slow_queries...")
slow = list_slow_queries()
print("   Slow queries source:", slow.get("source"), "queries count:", slow.get("queries_count"))
assert slow.get("source") is not None

print("4. Testing get_locks...")
locks = get_locks()
print("   Locks status:", locks.get("status"), "active locks count:", len(locks.get("active_locks_summary", [])))
assert locks.get("status") in ("healthy", "blocking_detected")

print("5. Testing export_table...")
exp = export_table(
    table_or_query="SELECT id, material_number, description FROM props_management.materials LIMIT 3;",
    output_path="scratch/live_export_test.csv",
    format="csv",
    is_query=True
)
print("   Export rows:", exp.get("rows_exported"), "file size:", exp.get("file_size_bytes"))
assert exp.get("rows_exported") == 3

print("6. Testing import_csv with dry_run and on_conflict='ignore'...")
imp = import_csv(
    table_name="materials",
    csv_path="scratch/live_export_test.csv",
    schema="props_management",
    on_conflict="ignore",
    dry_run=True
)
print("   Import dry-run status:", imp.get("status"), "rows validated:", imp.get("rows_validated"))
assert imp.get("dry_run") is True

print("\n>>> ALL 6 NEW DB TOOLS VERIFIED WITH 100% SUCCESS! <<<")
