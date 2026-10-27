"""
Pytest configuration for mcp-win-stdio test suite.
Ensures root src/ and all packages/*/src paths are resolved on sys.path and mcp_win_stdio namespace.
"""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent

# 1. Add all subpackages to sys.path
subpkg_paths = []
for p in (ROOT_DIR / "packages").glob("*/src"):
    p_str = str(p.resolve())
    subpkg_paths.append(p_str)
    if p_str not in sys.path:
        sys.path.insert(0, p_str)

# 2. Add root orchestrator src to sys.path
root_src = str((ROOT_DIR / "src").resolve())
if root_src not in sys.path:
    sys.path.insert(0, root_src)

# 3. Unload any pre-imported site-packages mcp_win_stdio modules so local ones load
for mod_name in list(sys.modules.keys()):
    if mod_name == "mcp_win_stdio" or mod_name.startswith("mcp_win_stdio."):
        sys.modules.pop(mod_name, None)

# 4. Set namespace __path__ to workspace subpackages
import mcp_win_stdio
mcp_win_stdio.__path__ = [str((ROOT_DIR / "src" / "mcp_win_stdio").resolve())] + [
    str((ROOT_DIR / "packages" / pkg.name / "src" / "mcp_win_stdio").resolve())
    for pkg in (ROOT_DIR / "packages").iterdir()
    if (ROOT_DIR / "packages" / pkg.name / "src" / "mcp_win_stdio").exists()
]
