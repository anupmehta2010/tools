from __future__ import annotations


def test_all_tool_modules_nonempty(all_tool_modules):
    assert len(all_tool_modules) >= 36


def test_run_cli_helper_works(run_cli):
    rc, out, err = run_cli(["dev", "calc", "2+2"])
    assert rc == 0
    assert "4" in out


def test_requires_returns_bool(requires):
    assert requires("definitely_not_a_real_module_xyz") is False
    # A stdlib module that definitely exists:
    assert requires("json") is True


def test_run_cli_handles_emoji_output(run_cli):
    """`tk list` prints emoji icons; run_cli must not crash decoding them."""
    rc, out, err = run_cli(["list"])
    assert rc == 0
    assert out  # got some output, no UnicodeDecodeError


def test_requires_safe_for_dotted_name(requires):
    assert requires("nonexistent_parent_xyz.child") is False
