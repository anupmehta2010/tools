"""Shared test fixtures for the tk suite."""
from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _module_names() -> list[str]:
    """Tool module dotted-paths, derived from tk's live category registry."""
    import tk
    names = []
    for _key, (mod_name, _label, _icon) in tk.available_categories().items():
        if mod_name.startswith("tk_tools."):
            names.append(mod_name)
    return sorted(set(names))


@pytest.fixture(scope="session")
def all_tool_modules() -> list[str]:
    return _module_names()


@pytest.fixture
def run_cli():
    """Invoke `python tk.py <args>` and return (rc, stdout, stderr)."""
    def _run(args: list[str], stdin: str | None = None, timeout: int = 60):
        proc = subprocess.run(
            [sys.executable, str(ROOT / "tk.py"), *args],
            input=stdin, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout,
        )
        return proc.returncode, proc.stdout, proc.stderr
    return _run


@pytest.fixture
def requires():
    """Return a predicate; tests call `requires('ffmpeg')` to gate themselves.

    Returns True when the dependency (python module OR binary on PATH) is
    available, False otherwise.
    """
    import _common

    def _check(dep: str) -> bool:
        try:
            if _common.have_module(dep):
                return True
        except (ModuleNotFoundError, ValueError):
            pass
        return _common.have_binary(dep)
    return _check
