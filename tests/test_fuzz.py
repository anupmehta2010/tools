from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from conftest import _module_names

GARBAGE_ARGS = [
    ["--no-such-flag"],
    ["nonexistent-subcommand-xyz"],
    [""],
]


@pytest.mark.parametrize("mod_name", _module_names())
@pytest.mark.parametrize("junk", GARBAGE_ARGS)
def test_garbage_args_no_traceback(mod_name, junk):
    """Junk args must produce a clean exit, never an uncaught traceback."""
    mod = importlib.import_module(mod_name)
    try:
        rc = mod.main(junk)
    except SystemExit as e:
        rc = e.code if isinstance(e.code, int) else 1
    except Exception as e:  # noqa: BLE001
        pytest.fail(f"{mod_name}.main({junk!r}) raised {type(e).__name__}: {e}")
    assert isinstance(rc, int)


def test_calc_rejects_malicious_input(run_cli):
    """The eval-based calculator must not execute arbitrary code."""
    rc, out, err = run_cli(["dev", "calc", "__import__('os').system('echo pwned')"])
    assert "pwned" not in out
    assert rc != 0 or "Error" in out or "error" in (out + err).lower()


from hypothesis import given, settings, strategies as st


@settings(max_examples=50, deadline=None)
@given(expr=st.text(alphabet="0123456789+-*/(). ", min_size=1, max_size=20))
def test_calc_never_crashes(expr):
    """calc must always exit cleanly — valid result or handled error, never a traceback."""
    import subprocess
    proc = subprocess.run(
        [sys.executable, str(ROOT / "tk.py"), "dev", "calc", expr],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
    )
    # rc 0 = valid result, rc 1 = calc caught an error.
    # rc 2 is tolerated because an expr that begins with '-' is parsed by argparse
    # as an unknown flag (a CLI-quoting artifact, not a calc bug). The real
    # robustness guarantee is the no-Traceback assertion below.
    assert proc.returncode in (0, 1, 2), f"expr={expr!r} rc={proc.returncode} stderr={proc.stderr}"
    assert "Traceback" not in proc.stderr


def test_calc_blocks_dunder_escape(run_cli):
    """eval sandbox escape via attribute traversal must be blocked."""
    rc, out, err = run_cli(["dev", "calc", "(1).__class__.__bases__[0].__subclasses__()"])
    assert "subclasses" not in out.lower()
    assert "wrap_close" not in out.lower()
    assert "<class" not in out
    assert rc == 1


def test_calc_blocks_attribute_access(run_cli):
    rc, out, err = run_cli(["dev", "calc", "().__class__"])
    assert "<class" not in out
    assert "type" not in out.lower() or rc == 1
    assert rc == 1


def test_calc_still_does_real_math(run_cli):
    rc, out, err = run_cli(["dev", "calc", "2 + 2 * 5"])
    assert rc == 0 and "12" in out
    rc, out, err = run_cli(["dev", "calc", "sqrt(16)"])
    assert rc == 0 and "4" in out
    rc, out, err = run_cli(["dev", "calc", "pi"])
    assert rc == 0 and "3.14" in out
    rc, out, err = run_cli(["dev", "calc", "max(3, 7, 1)"])
    assert rc == 0 and "7" in out


def test_calc_rejects_huge_exponent(run_cli):
    """Unbounded ** is a DoS (reachable via /api/run); large exponents must be rejected fast."""
    rc, out, err = run_cli(["dev", "calc", "9**9**9"], )
    assert rc == 1
    assert "Traceback" not in err
    rc, out, err = run_cli(["dev", "calc", "2**999999"])
    assert rc == 1


def test_calc_allows_reasonable_exponent(run_cli):
    rc, out, err = run_cli(["dev", "calc", "2**10"])
    assert rc == 0 and "1024" in out
    rc, out, err = run_cli(["dev", "calc", "2**1000"])
    assert rc == 0  # ~302 digits, fine
