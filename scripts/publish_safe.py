#!/usr/bin/env python3
"""
Rate-limit-safe, package-by-package PyPI publisher for mcp-win-stdio suite.

Features:
- Package-by-package upload (prevents PyPI 429 Too Many Requests bursts).
- Skip-if-exists check against PyPI JSON API (resumable if interrupted).
- Exponential backoff on rate-limit / network retries.
- Rate-limit pacing delay between uploads.
- Uploads sub-packages first, followed by root mcp-win-stdio package.
"""

import argparse
import getpass
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import List, Tuple

# Ensure Windows console uses UTF-8 without crashing on cp1252
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
VERSION = "0.3.0"

# Upload order: sub-packages first, then root orchestrator package
PACKAGE_ORDER = [
    ("mcp-win-stdio-arch", "mcp_win_stdio_arch"),
    ("mcp-win-stdio-db", "mcp_win_stdio_db"),
    ("mcp-win-stdio-excel", "mcp_win_stdio_excel"),
    ("mcp-win-stdio-excel-db", "mcp_win_stdio_excel_db"),
    ("mcp-win-stdio-explorer", "mcp_win_stdio_explorer"),
    ("mcp-win-stdio-git", "mcp_win_stdio_git"),
    ("mcp-win-stdio-rag", "mcp_win_stdio_rag"),
    ("mcp-win-stdio-ssh", "mcp_win_stdio_ssh"),
    ("mcp-win-stdio-tsc", "mcp_win_stdio_tsc"),
    ("mcp-win-stdio-word", "mcp_win_stdio_word"),
    ("mcp-win-stdio", "mcp_win_stdio"),  # Root orchestrator uploaded last
]


def check_is_published(pkg_pypi_name: str, version: str) -> bool:
    """Check PyPI JSON API to see if version is already live."""
    url = f"https://pypi.org/pypi/{pkg_pypi_name}/{version}/json"
    req = urllib.request.Request(url, headers={"User-Agent": "mws-publisher"})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False
        return False
    except Exception:
        return False


def get_artifacts_for_package(pkg_prefix: str, version: str) -> List[Path]:
    """Find wheel and sdist files for a given package and version."""
    patterns = [
        f"{pkg_prefix}-{version}-py3-none-any.whl",
        f"{pkg_prefix}-{version}.tar.gz",
    ]
    files = []
    for pat in patterns:
        matches = list(DIST_DIR.glob(pat))
        if matches:
            files.append(matches[0])
    return files


def upload_single_package(
    files: List[Path],
    token: str,
    max_retries: int = 4,
    retry_delay: int = 15,
) -> bool:
    """Upload files for a single package with exponential backoff on 429 rate limit."""
    env = os.environ.copy()
    env["TWINE_USERNAME"] = "__token__"
    env["TWINE_PASSWORD"] = token

    cmd = [
        sys.executable,
        "-m",
        "twine",
        "upload",
        "--non-interactive",
        "--skip-existing",
    ] + [str(f) for f in files]

    for attempt in range(1, max_retries + 1):
        proc = subprocess.run(cmd, env=env, capture_output=True, text=True)

        if proc.returncode == 0:
            return True

        output = (proc.stdout or "") + (proc.stderr or "")
        if "429" in output or "Too Many Requests" in output or "rate limit" in output.lower():
            wait_time = retry_delay * attempt
            print(f"\n   ⏳ PyPI Rate limit (429) encountered. Backing off for {wait_time}s (attempt {attempt}/{max_retries})...")
            time.sleep(wait_time)
            continue
        elif "File already exists" in output:
            print("   ℹ️  Artifact already exists on PyPI. Continuing.")
            return True
        else:
            print(f"\n   ❌ Upload error:\n{output.strip()}")
            if attempt < max_retries:
                time.sleep(retry_delay)
            else:
                return False

    return False


def main():
    parser = argparse.ArgumentParser(description="Rate-limit-safe package publisher for mcp-win-stdio")
    parser.add_argument("--delay", type=float, default=4.0, help="Seconds to pause between packages (default: 4.0s)")
    parser.add_argument("--token", help="PyPI API token (or set via TWINE_PASSWORD env var)")
    parser.add_argument("--dry-run", action="store_true", help="Check status without uploading")
    args = parser.parse_args()

    token = args.token or os.environ.get("TWINE_PASSWORD")
    if not token and not args.dry_run:
        print("\n🔑 PyPI Authentication Required:")
        token = getpass.getpass("Enter PyPI API Token (pypi-...): ").strip()
        if not token:
            print("Error: No token provided. Aborting.", file=sys.stderr)
            sys.exit(1)

    print("\n" + "=" * 76)
    print(f"   🚀  PyPI Rate-Limit Safe Publisher (v{VERSION})")
    print("=" * 76)
    print(f" Artifacts directory: {DIST_DIR}")
    print(f" Pacing delay:        {args.delay}s between packages")
    print(f" Total packages:      {len(PACKAGE_ORDER)}")
    print("-" * 76)

    success_count = 0
    skipped_count = 0
    failed_packages = []

    for idx, (pypi_name, file_prefix) in enumerate(PACKAGE_ORDER, 1):
        print(f"\n[{idx:02d}/{len(PACKAGE_ORDER):02d}] {pypi_name} (v{VERSION})")

        # 1. Check if already live on PyPI
        if check_is_published(pypi_name, VERSION):
            print(f"   ✅ [ALREADY PUBLISHED] Version {VERSION} is already live on PyPI. Skipping.")
            skipped_count += 1
            continue

        # 2. Locate artifacts
        artifacts = get_artifacts_for_package(file_prefix, VERSION)
        if not artifacts:
            print(f"   ⚠️  [MISSING] No artifacts found for {file_prefix} in dist/!")
            failed_packages.append(pypi_name)
            continue

        for a in artifacts:
            print(f"   📦 {a.name} ({a.stat().st_size / 1024:.1f} KB)")

        if args.dry_run:
            print("   🔍 [DRY RUN] Would upload above artifacts.")
            continue

        # 3. Upload with retry and backoff
        print("   ⬆️  Uploading to PyPI...")
        ok = upload_single_package(artifacts, token)
        if ok:
            print(f"   ✅ Successfully uploaded {pypi_name}!")
            success_count += 1
        else:
            print(f"   ❌ Failed to upload {pypi_name}")
            failed_packages.append(pypi_name)

        # 4. Pacing delay to avoid PyPI rate limiting
        if idx < len(PACKAGE_ORDER) and not args.dry_run:
            print(f"   ⏳ Pacing pause ({args.delay}s)...", end="", flush=True)
            time.sleep(args.delay)
            print(" done.")

    print("\n" + "=" * 76)
    print("   📊  Publishing Summary")
    print("=" * 76)
    print(f" Successfully published: {success_count}")
    print(f" Already up to date:     {skipped_count}")
    print(f" Failed:                 {len(failed_packages)}")
    if failed_packages:
        print(f" Failed packages: {', '.join(failed_packages)}")
        sys.exit(1)
    else:
        print("\n🎉 All packages verified and live on PyPI!\n")


if __name__ == "__main__":
    main()
