"""
Pytest configuration for mcp-win-stdio test suite.
Ensures root src/ and all packages/*/src paths are resolved on sys.path.
"""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent

# 1. Add all subpackages to sys.path
for p in (ROOT_DIR / "packages").glob("*/src"):
    p_str = str(p.resolve())
    if p_str not in sys.path:
        sys.path.insert(0, p_str)

# 2. Add root orchestrator src to sys.path
root_src = str((ROOT_DIR / "src").resolve())
if root_src not in sys.path:
    sys.path.insert(0, root_src)
