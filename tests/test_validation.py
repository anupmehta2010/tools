from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def test_exit_codes_defined():
    import _common
    assert _common.EXIT_OK == 0
    assert _common.EXIT_USER_ERROR == 1
    assert _common.EXIT_BAD_ARGS == 2
    assert _common.EXIT_MISSING_DEP == 3


def test_tkerror_carries_code():
    import _common
    err = _common.TkError("boom", code=3)
    assert err.code == 3
    assert str(err) == "boom"


def test_tool_main_formats_tkerror(capsys):
    import _common

    @_common.tool_main("demo")
    def main(argv=None):
        raise _common.TkError("bad thing", code=1)

    rc = main([])
    captured = capsys.readouterr()
    assert rc == 1
    assert captured.err.strip() == "tk demo: bad thing"


def test_tool_main_passes_through_success(capsys):
    import _common

    @_common.tool_main("demo")
    def main(argv=None):
        print("hello")
        return 0

    assert main([]) == 0
    assert capsys.readouterr().out.strip() == "hello"


def test_tool_main_hides_traceback_by_default(capsys):
    import _common

    @_common.tool_main("demo")
    def main(argv=None):
        raise ValueError("kaboom")

    rc = main([])
    captured = capsys.readouterr()
    assert rc == 1
    assert "Traceback" not in captured.err
    assert "tk demo:" in captured.err


def test_tool_main_shows_traceback_with_debug(capsys, monkeypatch):
    import _common
    monkeypatch.setenv("TK_DEBUG", "1")

    @_common.tool_main("demo")
    def main(argv=None):
        raise ValueError("kaboom")

    rc = main([])
    assert rc == 1
    assert "Traceback" in capsys.readouterr().err


def test_tool_main_shows_traceback_with_debug_argv(capsys):
    import _common

    @_common.tool_main("demo")
    def main(argv=None):
        raise ValueError("kaboom")

    rc = main(["--debug"])
    assert rc == 1
    assert "Traceback" in capsys.readouterr().err
