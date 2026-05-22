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


def test_validate_recipe_accepts_good():
    import _common
    recipe = {
        "name": "ok",
        "steps": [
            {"id": "n1", "tool": "dev:calc", "argv": ["2+2"]},
            {"id": "n2", "tool": "dev:slug", "argv": ["hi"], "depends": ["n1"]},
        ],
    }
    assert _common.validate_recipe(recipe) == []


def test_validate_recipe_flags_missing_steps():
    import _common
    errs = _common.validate_recipe({"name": "x"})
    assert any("steps" in e for e in errs)


def test_validate_recipe_flags_bad_tool_format():
    import _common
    errs = _common.validate_recipe(
        {"name": "x", "steps": [{"id": "n1", "tool": "nocolon", "argv": []}]}
    )
    assert any("tool" in e for e in errs)


def test_validate_recipe_flags_unknown_category():
    import _common
    errs = _common.validate_recipe(
        {"name": "x", "steps": [{"id": "n1", "tool": "notacat:foo", "argv": []}]}
    )
    assert any("notacat" in e for e in errs)


def test_validate_recipe_flags_missing_argv_and_args():
    import _common
    errs = _common.validate_recipe(
        {"name": "x", "steps": [{"id": "n1", "tool": "dev:calc"}]}
    )
    assert any("argv" in e or "args" in e for e in errs)


def test_validate_recipe_flags_bad_dependency_ref():
    import _common
    errs = _common.validate_recipe(
        {"name": "x", "steps": [{"id": "n1", "tool": "dev:calc", "argv": [], "depends": ["ghost"]}]}
    )
    assert any("ghost" in e for e in errs)


def test_validate_recipe_flags_cycle():
    import _common
    errs = _common.validate_recipe({
        "name": "x",
        "steps": [
            {"id": "a", "tool": "dev:calc", "argv": [], "depends": ["b"]},
            {"id": "b", "tool": "dev:calc", "argv": [], "depends": ["a"]},
        ],
    })
    assert any("cycle" in e.lower() for e in errs)


def test_validate_recipe_handles_null_tool():
    import _common
    errs = _common.validate_recipe(
        {"name": "x", "steps": [{"id": "n1", "tool": None, "argv": []}]}
    )
    # Must not raise; must flag the bad tool.
    assert any("tool" in e for e in errs)


def test_validate_recipe_unknown_category_with_known_set(monkeypatch):
    """Environment-independent: force a known category set via tk."""
    import _common
    import tk
    monkeypatch.setattr(tk, "available_categories", lambda: {"dev": ("x", "y", "z")})
    errs = _common.validate_recipe(
        {"name": "x", "steps": [{"id": "n1", "tool": "notacat:foo", "argv": []}]}
    )
    assert any("notacat" in e for e in errs)
    errs2 = _common.validate_recipe(
        {"name": "x", "steps": [{"id": "n1", "tool": "dev:calc", "argv": ["2+2"]}]}
    )
    assert errs2 == []


def test_validate_config_accepts_defaults():
    import _common
    assert _common.validate_config(dict(_common.DEFAULT_CONFIG)) == []


def test_validate_config_flags_unknown_key():
    import _common
    cfg = dict(_common.DEFAULT_CONFIG)
    cfg["bogus_key"] = 1
    warnings = _common.validate_config(cfg)
    assert any("bogus_key" in w for w in warnings)


def test_validate_config_flags_wrong_type():
    import _common
    cfg = dict(_common.DEFAULT_CONFIG)
    cfg["server_port"] = "not-a-number"
    warnings = _common.validate_config(cfg)
    assert any("server_port" in w for w in warnings)


def test_validate_config_flags_bool_for_int_key():
    import _common
    cfg = dict(_common.DEFAULT_CONFIG)
    cfg["server_port"] = True
    warnings = _common.validate_config(cfg)
    assert any("server_port" in w and "boolean" in w for w in warnings)


def test_validate_config_flags_int_for_bool_key():
    import _common
    cfg = dict(_common.DEFAULT_CONFIG)
    cfg["open_browser"] = 1
    warnings = _common.validate_config(cfg)
    assert any("open_browser" in w and "boolean" in w for w in warnings)


def test_recipes_validate_cli_good(tmp_path):
    import json, subprocess
    recipe = {"name": "ok", "steps": [{"id": "n1", "tool": "dev:calc", "argv": ["2+2"]}]}
    f = tmp_path / "r.json"
    f.write_text(json.dumps(recipe), encoding="utf-8")
    r = subprocess.run(
        [sys.executable, str(ROOT / "tk.py"), "recipes", "validate", str(f)],
        capture_output=True, text=True, timeout=60,
    )
    assert r.returncode == 0, r.stderr
    assert "valid" in (r.stdout + r.stderr).lower()


def test_recipes_validate_cli_bad(tmp_path):
    import json, subprocess
    recipe = {"name": "bad", "steps": [{"id": "n1", "tool": "nope", "argv": []}]}
    f = tmp_path / "r.json"
    f.write_text(json.dumps(recipe), encoding="utf-8")
    r = subprocess.run(
        [sys.executable, str(ROOT / "tk.py"), "recipes", "validate", str(f)],
        capture_output=True, text=True, timeout=60,
    )
    assert r.returncode == 1
    assert "problem" in r.stdout.lower() or "invalid" in r.stdout.lower()


def test_validate_recipe_allows_missing_ids():
    """Runtime _topo_sort tolerates steps without 'id'; validation must too."""
    import _common
    recipe = {"name": "ok", "steps": [{"tool": "dev:calc", "argv": ["2+2"]}]}
    assert _common.validate_recipe(recipe) == []


def test_validate_recipe_still_flags_duplicate_explicit_ids():
    import _common
    errs = _common.validate_recipe({
        "name": "x",
        "steps": [
            {"id": "a", "tool": "dev:calc", "argv": []},
            {"id": "a", "tool": "dev:slug", "argv": ["hi"]},
        ],
    })
    assert any("duplicate" in e for e in errs)
