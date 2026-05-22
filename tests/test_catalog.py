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


import importlib

import pytest

from conftest import _module_names


def _commands_for(mod_name):
    mod = importlib.import_module(mod_name)
    cmds = getattr(mod, "COMMANDS", {})
    return [(mod_name, cmd) for cmd in cmds]


def _all_module_command_pairs():
    pairs = []
    for m in _module_names():
        pairs.extend(_commands_for(m))
    return pairs


# Commands that legitimately cannot support `<cmd> --help` introspection.
# Add (module, cmd): "reason" entries ONLY with a documented justification.
KNOWN_NO_HELP: dict = {}


@pytest.mark.parametrize("mod_name", _module_names())
def test_module_contract(mod_name):
    mod = importlib.import_module(mod_name)
    assert hasattr(mod, "COMMANDS"), f"{mod_name} missing COMMANDS"
    assert isinstance(mod.COMMANDS, dict) and mod.COMMANDS
    assert hasattr(mod, "build_parser"), f"{mod_name} missing build_parser"
    assert hasattr(mod, "main"), f"{mod_name} missing main"
    assert mod.build_parser() is not None


@pytest.mark.parametrize("mod_name", _module_names())
def test_main_empty_argv_no_traceback(mod_name):
    """main([]) must exit cleanly (help or arg error), never raise an unexpected exception."""
    mod = importlib.import_module(mod_name)
    try:
        rc = mod.main([])
    except SystemExit as e:
        rc = e.code if isinstance(e.code, int) else 1
    except Exception as e:  # noqa: BLE001
        pytest.fail(f"{mod_name}.main([]) raised {type(e).__name__}: {e}")
    assert rc in (0, 1, 2)


@pytest.mark.parametrize("mod_name,cmd", _all_module_command_pairs())
def test_command_help_exits_zero(mod_name, cmd):
    """`<cmd> --help` must print help and exit 0 for every command."""
    if (mod_name, cmd) in KNOWN_NO_HELP:
        pytest.skip(KNOWN_NO_HELP[(mod_name, cmd)])
    mod = importlib.import_module(mod_name)
    with pytest.raises(SystemExit) as exc:
        mod.main([cmd, "--help"])
    assert exc.value.code == 0, f"{mod_name} {cmd} --help exited {exc.value.code}"
