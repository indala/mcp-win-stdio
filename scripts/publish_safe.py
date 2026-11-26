#!/usr/bin/env python3
"""
Rate-limit-safe, package-by-package PyPI publisher for the mcp-win-stdio suite.

Features:
- Dynamic version detection from pyproject.toml / mcp_win_stdio.__version__.
- Package-by-package upload to prevent PyPI 429 Too Many Requests bursts.
- Skip-if-exists check against PyPI JSON API (resumable if interrupted).
- Optional --build flag to compile all wheels/sdists prior to publishing.
- Optional --only flag to selectively publish a specific package.
- Exponential backoff and retry pacing on rate limits.
- Sub-packages uploaded first, followed by root mcp-win-stdio orchestrator.
"""

import argparse
import getpass
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import List, Optional, Tuple

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

# Upload order: sub-packages first, then root orchestrator package
PACKAGE_ORDER: List[Tuple[str, str]] = [
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


def detect_version() -> str:
    """Read the current suite version from pyproject.toml or src/mcp_win_stdio/__init__.py."""
    pyproj = ROOT_DIR / "pyproject.toml"
    if pyproj.exists():
        match = re.search(r'version\s*=\s*"([0-9]+\.[0-9]+\.[0-9]+)"', pyproj.read_text(encoding="utf-8"))
        if match:
            return match.group(1)

    init_file = ROOT_DIR / "src" / "mcp_win_stdio" / "__init__.py"
    if init_file.exists():
        match = re.search(r'__version__\s*=\s*"([0-9]+\.[0-9]+\.[0-9]+)"', init_file.read_text(encoding="utf-8"))
        if match:
            return match.group(1)

    return "0.3.1"


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


def _normalize_dist_name(name: str) -> str:
    """Normalize a Python distribution name per PEP 503."""
    return re.sub(r"[-_.]+", "_", name).lower()


def get_artifacts_for_package(pkg_prefix: str, version: str) -> List[Path]:
    """
    Find wheel (.whl) and source distribution (.tar.gz) files for a package.
    Matches normalized distribution name and exact version string cleanly.
    """
    if not DIST_DIR.exists():
        return []

    target_norm = _normalize_dist_name(pkg_prefix)
    matched_artifacts: List[Path] = []
    for file in DIST_DIR.iterdir():
        if not file.is_file():
            continue
        fname = file.name
        parsed_name: Optional[str] = None
        parsed_ver: Optional[str] = None

        if fname.endswith(".whl"):
            # PEP 427 wheel filename: {distribution}-{version}(-{build tag})?-{python tag}-{abi tag}-{platform tag}.whl
            parts = fname[:-4].split("-")
            if len(parts) >= 5:
                parsed_name = parts[0]
                parsed_ver = parts[1]
        elif fname.endswith(".tar.gz"):
            # Sdist filename: {name}-{version}.tar.gz
            stem = fname[:-7]
            if "-" in stem:
                parsed_name, parsed_ver = stem.rsplit("-", 1)

        if parsed_name and parsed_ver:
            if _normalize_dist_name(parsed_name) == target_norm and parsed_ver == version:
                matched_artifacts.append(file)

    # Sort wheel first, then tar.gz
    return sorted(matched_artifacts, key=lambda f: f.suffix, reverse=True)


def get_twine_command() -> List[str]:
    """Find the best command to invoke twine in the current environment."""
    # 1. Try python -m twine
    check = subprocess.run([sys.executable, "-m", "twine", "--version"], capture_output=True, text=True)
    if check.returncode == 0:
        return [sys.executable, "-m", "twine"]

    # 2. Try uv run twine
    if shutil.which("uv"):
        check_uv = subprocess.run(["uv", "run", "twine", "--version"], capture_output=True, text=True)
        if check_uv.returncode == 0:
            return ["uv", "run", "twine"]

    # 3. Direct twine executable on PATH
    twine_bin = shutil.which("twine")
    if twine_bin:
        return [twine_bin]

    return [sys.executable, "-m", "twine"]


def upload_single_package(
    files: List[Path],
    token: str,
    twine_cmd: List[str],
    max_retries: int = 4,
    retry_delay: int = 15,
) -> bool:
    """Upload files for a single package with exponential backoff on 429 rate limit."""
    env = os.environ.copy()
    env["TWINE_USERNAME"] = "__token__"
    env["TWINE_PASSWORD"] = token

    cmd = twine_cmd + [
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
    detected_ver = detect_version()
    parser = argparse.ArgumentParser(description="Rate-limit-safe package publisher for mcp-win-stdio")
    parser.add_argument("--version", default=detected_ver, help=f"Package version to publish (default: {detected_ver})")
    parser.add_argument("--delay", type=float, default=4.0, help="Seconds to pause between packages (default: 4.0s)")
    parser.add_argument("--dry-run", action="store_true", help="Check status without uploading")
    parser.add_argument("--build", action="store_true", help="Run scripts/build_all.py to build all packages before uploading")
    parser.add_argument("--only", help="Publish only a single package (e.g. 'arch', 'excel', 'mcp-win-stdio-ssh')")
    args = parser.parse_args()

    version = args.version

    # 1. Run build if requested
    if args.build:
        print("\n🔨 Building all packages first...")
        build_script = ROOT_DIR / "scripts" / "build_all.py"
        res = subprocess.run([sys.executable, str(build_script)], check=True)
        if res.returncode != 0:
            print("Error: Build failed. Aborting publish.", file=sys.stderr)
            sys.exit(1)

    # 2. Filter package list if --only is passed
    target_packages = PACKAGE_ORDER
    if args.only:
        clean_target = args.only.lower().replace("_", "-")
        target_packages = [
            (pypi, prefix) for pypi, prefix in PACKAGE_ORDER
            if clean_target in pypi or clean_target in prefix
        ]
        if not target_packages:
            print(f"Error: No package matches filter '{args.only}'. Available: {[p[0] for p in PACKAGE_ORDER]}", file=sys.stderr)
            sys.exit(1)

    token = os.environ.get("TWINE_PASSWORD")
    if not token and not args.dry_run:
        print("\n🔑 PyPI Authentication Required:")
        token = getpass.getpass("Enter PyPI API Token (pypi-...): ").strip()
        if not token:
            print("Error: No token provided. Aborting.", file=sys.stderr)
            sys.exit(1)

    twine_cmd = get_twine_command()

    print("\n" + "=" * 76)
    print(f"   🚀  PyPI Rate-Limit Safe Publisher (v{version})")
    print("=" * 76)
    print(f" Artifacts directory: {DIST_DIR}")
    print(f" Pacing delay:        {args.delay}s between packages")
    print(f" Target packages:     {len(target_packages)}")
    print(f" Twine runner:        {' '.join(twine_cmd)}")
    print("-" * 76)

    success_count = 0
    skipped_count = 0
    dry_run_count = 0
    failed_packages = []

    for idx, (pypi_name, file_prefix) in enumerate(target_packages, 1):
        print(f"\n[{idx:02d}/{len(target_packages):02d}] {pypi_name} (v{version})")

        # 1. Check if already live on PyPI
        if check_is_published(pypi_name, version):
            print(f"   ✅ [ALREADY PUBLISHED] Version {version} is already live on PyPI. Skipping.")
            skipped_count += 1
            continue

        # 2. Locate artifacts
        artifacts = get_artifacts_for_package(file_prefix, version)
        if not artifacts:
            print(f"   ⚠️  [MISSING] No artifacts found for {file_prefix} in dist/!")
            print("       Run 'python scripts/build_all.py' or pass '--build' to compile packages.")
            failed_packages.append(pypi_name)
            continue

        for a in artifacts:
            print(f"   📦 {a.name} ({a.stat().st_size / 1024:.1f} KB)")

        if args.dry_run:
            print("   🔍 [DRY RUN] Validated artifacts; no upload performed.")
            dry_run_count += 1
            continue

        # 3. Upload with retry and backoff
        print("   ⬆️  Uploading to PyPI...")
        ok = upload_single_package(artifacts, token, twine_cmd)
        if ok:
            print(f"   ✅ Successfully uploaded {pypi_name}!")
            success_count += 1
        else:
            print(f"   ❌ Failed to upload {pypi_name}")
            failed_packages.append(pypi_name)

        # 4. Pacing delay to avoid PyPI rate limiting
        if idx < len(target_packages) and not args.dry_run:
            print(f"   ⏳ Pacing pause ({args.delay}s)...", end="", flush=True)
            time.sleep(args.delay)
            print(" done.")

    print("\n" + "=" * 76)
    print("   📊  Dry Run Summary" if args.dry_run else "   📊  Publishing Summary")
    print("=" * 76)
    if args.dry_run:
        print(f" Ready for upload:       {dry_run_count}")
        print(f" Already up to date:     {skipped_count}")
        print(f" Missing / Failed:       {len(failed_packages)}")
        if failed_packages:
            print(f" Missing/Failed pkgs: {', '.join(failed_packages)}")
            sys.exit(1)
        else:
            print("\n🔍 [DRY RUN COMPLETE] All checked packages are valid/ready. No packages were uploaded to PyPI.\n")
    else:
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
