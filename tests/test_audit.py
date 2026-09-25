import decimal
import uuid
from datetime import datetime, date, time
import pandas as pd
import numpy as np
import pathspec

def test_excel_clean_records():
    from mcp_win_stdio.excel.server import _df_to_clean_records
    df = pd.DataFrame({
        "dates": [pd.Timestamp("2026-01-01 12:00:00"), pd.NaT],
        "nums": [10.5, np.nan],
        "texts": ["hello", None]
    })
    records = _df_to_clean_records(df)
    assert len(records) == 2
    assert records[0]["dates"] == "2026-01-01T12:00:00"
    assert records[1]["dates"] is None
    assert records[0]["nums"] == 10.5
    assert records[1]["nums"] is None
    assert records[0]["texts"] == "hello"
    assert records[1]["texts"] is None
    print("[PASS] Excel clean records test passed.")

def test_explorer_gitignore():
    from mcp_win_stdio.explorer.server import _matches_gitignore
    patterns = ["node_modules/", "dist/", "*.pyc", "temp_dir/"]
    spec = pathspec.PathSpec.from_lines("gitwildmatch", patterns)
    assert _matches_gitignore(spec, "node_modules", is_dir=True) is True
    assert _matches_gitignore(spec, "dist", is_dir=True) is True
    assert _matches_gitignore(spec, "src/foo.pyc", is_dir=False) is True
    assert _matches_gitignore(spec, "src/foo.py", is_dir=False) is False
    print("[PASS] Explorer gitignore test passed.")

def test_tsc_safety():
    from mcp_win_stdio.tsc.server import find_tsconfigs, is_home_or_root_dir
    assert is_home_or_root_dir("C:\\") is True
    # Should not crash or crawl home/root
    configs = find_tsconfigs("C:\\")
    assert isinstance(configs, list)
    print("[PASS] TSC safety test passed.")

def test_db_truncate_cell():
    import json
    from mcp_win_stdio.db.server import _truncate_cell
    d = decimal.Decimal("123.456")
    u = uuid.uuid4()
    now = datetime.now()
    mem = memoryview(b"binary_payload")
    
    cleaned = {
        "decimal": _truncate_cell(d),
        "uuid": _truncate_cell(u),
        "datetime": _truncate_cell(now),
        "mem": _truncate_cell(mem),
        "long_str": _truncate_cell("a" * 600, max_chars=100)
    }
    # Verify strict JSON serializability
    serialized = json.dumps(cleaned)
    assert "123.456" in serialized
    assert "<binary data: 14 bytes>" in serialized
    assert "... [truncated 500 chars]" in serialized
    print("[PASS] DB truncate cell serialization test passed.")

if __name__ == "__main__":
    test_excel_clean_records()
    test_explorer_gitignore()
    test_tsc_safety()
    test_db_truncate_cell()
    print("ALL AUDIT TESTS PASSED!")
