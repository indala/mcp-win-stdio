"""
Build script to compile wheels and source distributions for all 8 packages.
"""

import shutil
import subprocess
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


ROOT_DIR = Path(__file__).resolve().parent.parent
DIST_DIR = ROOT_DIR / "dist"

PACKAGES = [
    ROOT_DIR,
    ROOT_DIR / "packages" / "mcp-win-stdio-excel",
    ROOT_DIR / "packages" / "mcp-win-stdio-word",
    ROOT_DIR / "packages" / "mcp-win-stdio-explorer",
    ROOT_DIR / "packages" / "mcp-win-stdio-tsc",
    ROOT_DIR / "packages" / "mcp-win-stdio-db",
    ROOT_DIR / "packages" / "mcp-win-stdio-git",
    ROOT_DIR / "packages" / "mcp-win-stdio-ssh",
    ROOT_DIR / "packages" / "mcp-win-stdio-rag",
    ROOT_DIR / "packages" / "mcp-win-stdio-excel-db",
]


def clean():
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
    DIST_DIR.mkdir(parents=True, exist_ok=True)

    for pkg in PACKAGES:
        pkg_dist = pkg / "dist"
        if pkg_dist.exists():
            shutil.rmtree(pkg_dist)


def build_all():
    clean()
    print("🚀 Building all 10 packages (root + 9 subpackages)...")

    for pkg in PACKAGES:
        rel_name = pkg.name if pkg != ROOT_DIR else "mcp-win-stdio (root)"
        print(f"\n📦 Building: {rel_name} ({pkg})...")
        res = subprocess.run([sys.executable, "-m", "build", str(pkg)], check=True)

        # Move artifacts to central dist directory
        pkg_dist = pkg / "dist"
        if pkg_dist.exists() and pkg != ROOT_DIR:
            for artifact in pkg_dist.iterdir():
                shutil.copy2(artifact, DIST_DIR / artifact.name)

    print("\n✅ All packages built successfully into dist/:")
    for item in sorted(DIST_DIR.iterdir()):
        print(f"  • {item.name} ({item.stat().st_size / 1024:.1f} KB)")


if __name__ == "__main__":
    build_all()
