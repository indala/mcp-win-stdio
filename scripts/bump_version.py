#!/usr/bin/env python3
"""
Script to bump version across root and all 9 subpackages using rglob with UTF-8 safety.
"""

import re
import sys
from pathlib import Path

if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            getattr(sys.stdout, "reconfigure")(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            getattr(sys.stderr, "reconfigure")(encoding="utf-8", errors="replace")
    except Exception:
        pass

NEW_VERSION = "0.2.5"
ROOT_DIR = Path(__file__).resolve().parent.parent


def bump_all():
    print(f"Bumping version to {NEW_VERSION} across all packages...")

    # 1. Update pyproject.toml files
    for p in ROOT_DIR.rglob("pyproject.toml"):
        text = p.read_text(encoding="utf-8")
        new_text = re.sub(r'version = "[0-9]+\.[0-9]+\.[0-9]+"', f'version = "{NEW_VERSION}"', text)
        new_text = re.sub(r'("mcp-win-stdio(?:-[a-z0-9-]+)?>=)[0-9]+\.[0-9]+\.[0-9]+', rf"\g<1>{NEW_VERSION}", new_text)
        p.write_text(new_text, encoding="utf-8")
        print(f"  • Updated {p.relative_to(ROOT_DIR)}")

    # 2. Update __init__.py files
    for p in ROOT_DIR.rglob("__init__.py"):
        text = p.read_text(encoding="utf-8")
        if "__version__" in text:
            new_text = re.sub(r'__version__ = "[0-9]+\.[0-9]+\.[0-9]+"', f'__version__ = "{NEW_VERSION}"', text)
            p.write_text(new_text, encoding="utf-8")
            print(f"  • Updated {p.relative_to(ROOT_DIR)}")

    # 3. Update README.md
    readme_path = ROOT_DIR / "README.md"
    if readme_path.exists():
        text = readme_path.read_text(encoding="utf-8")
        new_text = re.sub(r"\(v[0-9]+\.[0-9]+\.[0-9]+\)", f"(v{NEW_VERSION})", text)
        readme_path.write_text(new_text, encoding="utf-8")
        print("  • Updated README.md")

    print(f"\nAll packages bumped to {NEW_VERSION} successfully!")


if __name__ == "__main__":
    bump_all()
