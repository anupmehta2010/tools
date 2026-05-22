from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from cases import load_all_cases

CASES = load_all_cases()


def _case_id(case):
    return case.get("_module", "?") + ":" + " ".join(case.get("args", []))


@pytest.mark.parametrize("case", CASES, ids=[_case_id(c) for c in CASES])
def test_golden_case(case, run_cli, requires):
    for dep in case.get("requires", []):
        if not requires(dep):
            pytest.skip(f"missing dependency: {dep}")
    rc, out, err = run_cli(case["args"], stdin=case.get("stdin"))
    assert rc == case.get("rc", 0), f"rc={rc} stderr={err}"
    for sub in case.get("contains", []):
        assert sub in out, f"{sub!r} not in output:\n{out}"
