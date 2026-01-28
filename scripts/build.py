#!/usr/bin/env python3
"""Build script for AutoGLM-GUI.

This script builds the frontend and copies the dist files to the package.
Run this before publishing to PyPI.

Usage:
    uv run python scripts/build.py          # Build frontend only
    uv run python scripts/build.py --pack   # Build frontend and create package
"""

import argparse
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
FRONTEND_DIR = ROOT_DIR / "frontend"
STATIC_DIR = ROOT_DIR / "AutoGLM_GUI" / "static"


def get_backend_version() -> str:
    """读取后端版本号（用于前端构建注入）。"""
    pyproject_path = ROOT_DIR / "pyproject.toml"
    try:
        with pyproject_path.open("rb") as file:
            data = tomllib.load(file)
        return str(data.get("project", {}).get("version") or "unknown")
    except Exception:
        return "unknown"


def build_frontend() -> bool:
    """Build the frontend using pnpm."""
    print("Building frontend...")

    # Resolve pnpm executable
    pnpm_exe = shutil.which("pnpm")
    if not pnpm_exe:
        print("Error: pnpm is not installed. Please install pnpm first.")
        return False

    # Install dependencies
    print("Installing frontend dependencies...")
    result = subprocess.run([pnpm_exe, "install"], cwd=FRONTEND_DIR)
    if result.returncode != 0:
        print("Error: Failed to install frontend dependencies.")
        return False

    # Build
    print("Building frontend...")
    env = os.environ.copy()
    env["VITE_BACKEND_VERSION"] = get_backend_version()
    print(f"Frontend build version: {env['VITE_BACKEND_VERSION']}")
    result = subprocess.run([pnpm_exe, "build"], cwd=FRONTEND_DIR, env=env)
    if result.returncode != 0:
        print("Error: Failed to build frontend.")
        return False

    return True


def copy_static_files() -> bool:
    """Copy frontend dist to package static directory."""
    print("Copying static files to package...")

    dist_dir = FRONTEND_DIR / "dist"
    if not dist_dir.exists():
        print(f"Error: Frontend dist directory not found: {dist_dir}")
        return False

    # Remove existing static directory
    if STATIC_DIR.exists():
        shutil.rmtree(STATIC_DIR)

    # Copy dist to static
    shutil.copytree(dist_dir, STATIC_DIR)

    print(f"Static files copied to: {STATIC_DIR}")
    return True


def build_package() -> bool:
    """Build the Python package using uv."""
    print("Building Python package...")

    # Remove old dist
    dist_dir = ROOT_DIR / "dist"
    if dist_dir.exists():
        shutil.rmtree(dist_dir)

    result = subprocess.run(["uv", "build"], cwd=ROOT_DIR)
    if result.returncode != 0:
        print("Error: Failed to build package.")
        return False

    return True


def main() -> int:
    """Main build process."""
    parser = argparse.ArgumentParser(description="Build AutoGLM-GUI for distribution")
    parser.add_argument(
        "--pack", action="store_true", help="Also build Python package after frontend"
    )
    args = parser.parse_args()

    print("=" * 50)
    print("AutoGLM-GUI Build Script")
    print("=" * 50)

    if not build_frontend():
        return 1

    if not copy_static_files():
        return 1

    if args.pack:
        if not build_package():
            return 1

    print()
    print("=" * 50)
    print("Build completed successfully!")
    print()
    if args.pack:
        print("Package built in: dist/")
        print()
        print("Next steps:")
        print("  1. Test: uvx --from dist/autoglm_gui-*.whl autoglm-gui")
        print("  2. Publish: uv publish")
    else:
        print("Next steps:")
        print("  1. Test locally: uv run autoglm-gui")
        print("  2. Build package: uv run python scripts/build.py --pack")
        print("  3. Publish to PyPI: uv publish")
    print("=" * 50)

    return 0


if __name__ == "__main__":
    sys.exit(main())
