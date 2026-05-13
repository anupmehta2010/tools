"""Shared helpers for the tools suite."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path


def lazy_import(module_name: str, install_hint: str | None = None):
    """Import a module; on failure print a friendly install hint and exit."""
    try:
        return importlib.import_module(module_name)
    except ImportError:
        hint = install_hint or f"pip install {module_name}"
        print(f"\n[!] Required module '{module_name}' is not installed.")
        print(f"    Install with: {hint}\n")
        raise SystemExit(2)


def confirm(prompt: str, default: bool = False) -> bool:
    yn = "Y/n" if default else "y/N"
    try:
        ans = input(f"{prompt} [{yn}]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    if not ans:
        return default
    return ans in ("y", "yes")


def human_size(n: int | float) -> str:
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}PB"


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path
