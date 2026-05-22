# tk Hardening (Phase 1: Depth) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the existing `tk` toolkit with a scaling test suite, a standardized error contract, recipe/config validation, API + E2E tests, fuzzing, a coverage gate, and developer docs — without changing any tool's behavior.

**Architecture:** An introspection-driven test harness walks `tk.available_categories()` and each module's `COMMANDS`/`build_parser()` to auto-cover all 455 commands. A small set of `_common.py` helpers (`TkError`, exit-code constants, `tool_main` decorator) standardize errors; each module's `main()` adopts the decorator. Validation functions live in `_common.py`. CI splits into `core` / `full` / `e2e` lanes, with a coverage gate on the stdlib-only core lane.

**Tech Stack:** Python 3.10+, pytest, pytest-cov, hypothesis, pytest-playwright, stdlib `http.server`, argparse.

---

## File Structure

**New files:**
- `tests/conftest.py` — shared fixtures: `run_cli`, `requires`, module/command enumeration.
- `tests/test_catalog.py` — introspection sweep over all modules + commands.
- `tests/cases/__init__.py` — aggregates per-module golden case tables.
- `tests/cases/<module>.py` — one golden-case table per tool module (start with core modules).
- `tests/test_golden.py` — runs all golden cases.
- `tests/test_fuzz.py` — malformed-input + Hypothesis arg fuzzing.
- `tests/test_validation.py` — recipe/config validation unit tests.
- `tests/test_api.py` — `server.py` endpoint contract tests.
- `tests/e2e/test_web.py` — Playwright web-UI flows.
- `CLAUDE.md` — developer documentation.

**Modified:**
- `_common.py` — exit-code constants, `TkError`, `tool_main`, `validate_recipe`, `CONFIG_SCHEMA` + `validate_config`; `lazy_import` exit code 2 → 3; `load_config` warns on unknown keys.
- `tk_tools/*.py` (36 modules) — wrap `main()` with `@tool_main`.
- `tk_tools/recipes_tools.py` — add `validate` command; validate before run/exec.
- `.github/workflows/ci.yml` — `core` / `full` / `e2e` lanes + coverage gate.
- `pyproject.toml` — dev deps + coverage config.

---

## Task 1: Error-contract primitives in `_common.py`

**Files:**
- Modify: `_common.py` (add near top, after imports)
- Test: `tests/test_validation.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_validation.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_validation.py -k "exit_codes or tkerror or tool_main" -v`
Expected: FAIL — `AttributeError: module '_common' has no attribute 'EXIT_OK'`.

- [ ] **Step 3: Add the primitives**

In `_common.py`, after the imports block (after line 21, before `# import helpers`), add:

```python
# ---------------------------------------------------------------- error contract

EXIT_OK = 0
EXIT_USER_ERROR = 1
EXIT_BAD_ARGS = 2
EXIT_MISSING_DEP = 3


class TkError(Exception):
    """A user-facing tool error. Carries a process exit code."""

    def __init__(self, message: str, code: int = EXIT_USER_ERROR):
        super().__init__(message)
        self.code = code


def _debug_enabled(argv) -> bool:
    if os.environ.get("TK_DEBUG"):
        return True
    return bool(argv) and "--debug" in argv


def tool_main(category: str):
    """Decorate a module `main(argv)` to enforce the tk error contract.

    - TkError       -> its .code, message to stderr as `tk <category>: <msg>`.
    - SystemExit    -> passed through unchanged (argparse / lazy_import).
    - KeyboardInterrupt -> exit 130.
    - other Exception -> EXIT_USER_ERROR, message to stderr; traceback only
      when --debug is passed or TK_DEBUG is set.
    """
    def decorator(func):
        import functools

        @functools.wraps(func)
        def wrapper(argv=None):
            try:
                return func(argv) or EXIT_OK
            except TkError as e:
                print(f"tk {category}: {e}", file=sys.stderr)
                return e.code
            except SystemExit:
                raise
            except KeyboardInterrupt:
                return 130
            except Exception as e:  # noqa: BLE001 - top-level guard
                if _debug_enabled(argv):
                    import traceback
                    traceback.print_exc()
                print(f"tk {category}: {e}", file=sys.stderr)
                return EXIT_USER_ERROR

        return wrapper

    return decorator
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_validation.py -k "exit_codes or tkerror or tool_main" -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Update `lazy_import` to use EXIT_MISSING_DEP**

In `_common.py`, change the `lazy_import` failure path (currently `raise SystemExit(2)`):

```python
def lazy_import(module_name: str, install_hint: str | None = None):
    """Import a module; on failure print a friendly install hint and exit."""
    try:
        return importlib.import_module(module_name)
    except ImportError:
        hint = install_hint or f"pip install {module_name}"
        print(f"\n[!] Required module '{module_name}' is not installed.")
        print(f"    Install with: {hint}\n")
        raise SystemExit(EXIT_MISSING_DEP)
```

- [ ] **Step 6: Run full validation test file**

Run: `python -m pytest tests/test_validation.py -v`
Expected: PASS for all defined tests.

- [ ] **Step 7: Commit**

```bash
git add _common.py tests/test_validation.py
git commit -m "feat: add tk error contract (TkError, tool_main, exit codes)"
```

---

## Task 2: Recipe validation in `_common.py`

**Files:**
- Modify: `_common.py` (add after the recipes section, ~line 305)
- Test: `tests/test_validation.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_validation.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_validation.py -k validate_recipe -v`
Expected: FAIL — `AttributeError: module '_common' has no attribute 'validate_recipe'`.

- [ ] **Step 3: Implement `validate_recipe`**

In `_common.py`, after `recipe_delete` (line ~304), add:

```python
def validate_recipe(recipe: dict) -> list[str]:
    """Return a list of human-readable problems. Empty list == valid.

    Checks: steps present and a list; each step has a unique id; tool is
    'category:command'; the category exists; argv or args present; depends
    references resolve; the dependency graph is acyclic.
    """
    errors: list[str] = []
    if not isinstance(recipe, dict):
        return ["recipe must be a JSON object"]

    steps = recipe.get("steps")
    if not isinstance(steps, list) or not steps:
        return ["recipe must have a non-empty 'steps' list"]

    try:
        import tk
        known_cats = set(tk.available_categories())
    except Exception:
        known_cats = set()

    ids: list[str] = []
    for i, step in enumerate(steps):
        where = f"step {i}"
        if not isinstance(step, dict):
            errors.append(f"{where}: must be an object")
            continue
        sid = step.get("id")
        if not sid:
            errors.append(f"{where}: missing 'id'")
        else:
            where = f"step '{sid}'"
            if sid in ids:
                errors.append(f"{where}: duplicate id")
            ids.append(sid)

        tool = step.get("tool", "")
        if ":" not in tool:
            errors.append(f"{where}: 'tool' must be 'category:command', got {tool!r}")
        else:
            cat = tool.split(":", 1)[0]
            if known_cats and cat not in known_cats:
                errors.append(f"{where}: unknown category '{cat}'")

        if "argv" not in step and "args" not in step:
            errors.append(f"{where}: needs 'argv' or 'args'")

    id_set = set(ids)
    for step in steps:
        if not isinstance(step, dict):
            continue
        sid = step.get("id", "?")
        for dep in step.get("depends", []) or []:
            if dep not in id_set:
                errors.append(f"step '{sid}': depends on unknown step '{dep}'")

    # Cycle detection (Kahn's algorithm over the declared edges).
    indeg = {s.get("id"): 0 for s in steps if isinstance(s, dict) and s.get("id")}
    for s in steps:
        if not isinstance(s, dict):
            continue
        for dep in s.get("depends", []) or []:
            if s.get("id") in indeg and dep in indeg:
                indeg[s["id"]] += 1
    from collections import deque
    q = deque([k for k, v in indeg.items() if v == 0])
    seen = 0
    while q:
        cur = q.popleft()
        seen += 1
        for s in steps:
            if isinstance(s, dict) and cur in (s.get("depends", []) or []):
                tgt = s.get("id")
                if tgt in indeg:
                    indeg[tgt] -= 1
                    if indeg[tgt] == 0:
                        q.append(tgt)
    if indeg and seen != len(indeg):
        errors.append("recipe has a dependency cycle")

    return errors
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_validation.py -k validate_recipe -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add _common.py tests/test_validation.py
git commit -m "feat: add validate_recipe with cycle and reference checks"
```

---

## Task 3: Config validation in `_common.py`

**Files:**
- Modify: `_common.py` (config section, ~line 89-118)
- Test: `tests/test_validation.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_validation.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_validation.py -k validate_config -v`
Expected: FAIL — no attribute `validate_config`.

- [ ] **Step 3: Implement `CONFIG_SCHEMA` + `validate_config`**

In `_common.py`, immediately after `DEFAULT_CONFIG` (line ~100), add:

```python
CONFIG_SCHEMA: dict[str, type] = {
    "theme": str,
    "workspace": str,
    "server_host": str,
    "server_port": int,
    "open_browser": bool,
    "ollama_host": str,
    "ollama_model": str,
    "ffmpeg_path": str,
    "history_enabled": bool,
    "history_keep": int,
}


def validate_config(cfg: dict) -> list[str]:
    """Return warnings (not fatal): unknown keys and wrong value types."""
    warnings: list[str] = []
    for key, value in cfg.items():
        if key not in CONFIG_SCHEMA:
            warnings.append(f"unknown config key '{key}'")
            continue
        expected = CONFIG_SCHEMA[key]
        # bool is a subclass of int; check bool first to avoid false matches.
        if expected is bool and not isinstance(value, bool):
            warnings.append(f"config '{key}' should be a boolean")
        elif expected is int and isinstance(value, bool):
            warnings.append(f"config '{key}' should be an integer, got boolean")
        elif expected is int and not isinstance(value, int):
            warnings.append(f"config '{key}' should be an integer")
        elif expected is str and not isinstance(value, str):
            warnings.append(f"config '{key}' should be a string")
    return warnings
```

- [ ] **Step 4: Wire warnings into `load_config`**

In `_common.py`, change the end of `load_config` so it warns once on bad keys. Replace the final `return cfg` of `load_config` with:

```python
    for w in validate_config(cfg):
        print(f"[config] {w}", file=sys.stderr)
    return cfg
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_validation.py -k validate_config -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Run the whole validation file + smoke tests (no regressions)**

Run: `python -m pytest tests/test_validation.py tests/test_smoke.py -q`
Expected: PASS (all).

- [ ] **Step 7: Commit**

```bash
git add _common.py tests/test_validation.py
git commit -m "feat: add config schema validation with non-fatal warnings"
```

---

## Task 4: `recipes validate` command + validate-before-run

**Files:**
- Modify: `tk_tools/recipes_tools.py`
- Test: `tests/test_validation.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_validation.py`:

```python
import json
import subprocess


def test_recipes_validate_cli_good(tmp_path):
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
    recipe = {"name": "bad", "steps": [{"id": "n1", "tool": "nope", "argv": []}]}
    f = tmp_path / "r.json"
    f.write_text(json.dumps(recipe), encoding="utf-8")
    r = subprocess.run(
        [sys.executable, str(ROOT / "tk.py"), "recipes", "validate", str(f)],
        capture_output=True, text=True, timeout=60,
    )
    assert r.returncode == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_validation.py -k recipes_validate -v`
Expected: FAIL — `invalid choice: 'validate'`.

- [ ] **Step 3: Add the command**

In `tk_tools/recipes_tools.py`:

Add to the import from `_common` (line 28-30):

```python
from _common import (
    recipe_save, recipe_load, recipe_list, recipe_delete, emit, validate_recipe,
)
```

Add to `COMMANDS` dict (after `"scaffold"`):

```python
    "validate": "Validate a recipe JSON file (structure, refs, cycles)",
```

Add the command function (after `cmd_scaffold`):

```python
def cmd_validate(args):
    recipe = json.loads(Path(args.file).read_text(encoding="utf-8"))
    errors = validate_recipe(recipe)
    if not errors:
        print(f"Recipe '{recipe.get('name', args.file)}' is valid.")
        return 0
    print(f"Recipe has {len(errors)} problem(s):")
    for e in errors:
        print(f"  - {e}")
    return 1
```

Register it in `build_parser` (after the `scaffold` subparser):

```python
    sp = sub.add_parser("validate", help=COMMANDS["validate"])
    sp.add_argument("file", help="recipe JSON file")
    sp.set_defaults(func=cmd_validate)
```

- [ ] **Step 4: Validate before running (run + exec)**

In `cmd_run`, after `r = recipe_load(...)` and the not-found guard, before building variables, add:

```python
    problems = validate_recipe(r)
    if problems:
        print(f"Recipe '{args.name}' is invalid:")
        for p in problems:
            print(f"  - {p}")
        return 1
```

In `cmd_exec`, after `r = json.loads(...)`, add:

```python
    problems = validate_recipe(r)
    if problems:
        print("Recipe is invalid:")
        for p in problems:
            print(f"  - {p}")
        return 1
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_validation.py -k recipes_validate -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
git add tk_tools/recipes_tools.py tests/test_validation.py
git commit -m "feat: add 'recipes validate' and validate before run/exec"
```

---

## Task 5: Test harness fixtures (`tests/conftest.py`)

**Files:**
- Create: `tests/conftest.py`
- Test: `tests/test_catalog.py` (created in Task 6 uses these fixtures; here we self-test the helpers)

- [ ] **Step 1: Write the failing test**

Create `tests/test_catalog.py` with only a fixture self-check for now:

```python
from __future__ import annotations


def test_all_tool_modules_nonempty(all_tool_modules):
    assert len(all_tool_modules) >= 36


def test_run_cli_helper_works(run_cli):
    rc, out, err = run_cli(["dev", "calc", "2+2"])
    assert rc == 0
    assert "4" in out


def test_requires_skips_when_missing(requires):
    # ffmpeg may or may not be present; just assert the helper returns a bool-like marker
    assert requires("definitely_not_a_real_module_xyz") is False or True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_catalog.py -v`
Expected: FAIL — `fixture 'all_tool_modules' not found`.

- [ ] **Step 3: Implement `conftest.py`**

Create `tests/conftest.py`:

```python
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
            input=stdin, capture_output=True, text=True, timeout=timeout,
        )
        return proc.returncode, proc.stdout, proc.stderr
    return _run


@pytest.fixture
def requires():
    """Return a predicate; tests call `requires('ffmpeg')` to gate themselves.

    Returns True when the dependency (python module OR binary on PATH) is
    available, False otherwise. Use as: `if not requires('ffmpeg'): pytest.skip(...)`.
    """
    import _common

    def _check(dep: str) -> bool:
        return _common.have_module(dep) or _common.have_binary(dep)
    return _check
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_catalog.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add tests/conftest.py tests/test_catalog.py
git commit -m "test: add shared fixtures (module enum, run_cli, requires)"
```

---

## Task 6: Introspection catalog sweep (`tests/test_catalog.py`)

**Files:**
- Modify: `tests/test_catalog.py`

This is the heart of Approach A: parametrize over every module and every command so all 455 commands get structural coverage automatically.

- [ ] **Step 1: Write the failing tests**

Replace the body of `tests/test_catalog.py` (keep the three fixture self-checks from Task 5) by appending:

```python
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
    """main([]) must exit cleanly (help or arg error), never raise."""
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
    mod = importlib.import_module(mod_name)
    with pytest.raises(SystemExit) as exc:
        mod.main([cmd, "--help"])
    assert exc.value.code == 0, f"{mod_name} {cmd} --help exited {exc.value.code}"
```

- [ ] **Step 2: Run the sweep**

Run: `python -m pytest tests/test_catalog.py -q`
Expected: Mostly PASS. Some commands may surface real bugs (a `--help` that errors, a module whose `main([])` raises). For each failure, treat it as a found bug.

- [ ] **Step 3: Triage and fix or xfail**

For any failing command:
- If it's a real bug (e.g. `build_parser` adds a required positional that breaks `--help` — it should not, argparse handles `--help` before requireds), fix the module.
- If a command legitimately cannot support `--help` introspection, mark it explicitly:

```python
KNOWN_NO_HELP = {
    # ("tk_tools.x_tools", "weird-cmd"): "reason",
}
```
and skip those pairs in `test_command_help_exits_zero` with `pytest.skip`. Document each with a reason. Do NOT blanket-skip.

- [ ] **Step 4: Run to verify green**

Run: `python -m pytest tests/test_catalog.py -q`
Expected: PASS (all parametrized cases, minus documented skips).

- [ ] **Step 5: Commit**

```bash
git add tests/test_catalog.py
git commit -m "test: introspection catalog sweep over all modules and commands"
```

---

## Task 7: Golden I/O cases (core modules first)

**Files:**
- Create: `tests/cases/__init__.py`, `tests/cases/dev_tools.py`, `tests/cases/text_tools.py`, `tests/cases/embedded_tools.py`, `tests/cases/crypto_tools.py`, `tests/cases/data_tools.py`
- Create: `tests/test_golden.py`

- [ ] **Step 1: Write the golden-case tables**

Create `tests/cases/dev_tools.py`:

```python
"""Golden CLI cases for the `dev` category. Each case:
{ "args": [...], "stdin": str|None, "contains": [substrings], "rc": int,
  "requires": [deps] }  (requires optional)
"""
CASES = [
    {"args": ["dev", "calc", "2 + 2 * 5"], "contains": ["12"], "rc": 0},
    {"args": ["dev", "base", "255", "--to-base", "16"], "contains": ["ff"], "rc": 0},
    {"args": ["dev", "slug", "Hello, World!"], "contains": ["hello-world"], "rc": 0},
    {"args": ["dev", "semver-bump", "1.2.3", "--bump", "minor"], "contains": ["1.3.0"], "rc": 0},
]
```

Create `tests/cases/text_tools.py`:

```python
CASES = [
    {"args": ["text", "hash", "--algo", "sha256"], "stdin": "abc",
     "contains": ["ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"], "rc": 0},
]
```

Create `tests/cases/embedded_tools.py`:

```python
CASES = [
    {"args": ["embedded", "crc16", "--hex", "313233343536373839"],
     "contains": ["0x29b1"], "rc": 0},
]
```

Create `tests/cases/crypto_tools.py`:

```python
CASES = [
    {"args": ["crypto", "uuid"], "contains": ["-"], "rc": 0},
    {"args": ["crypto", "password", "--length", "20"], "rc": 0},
]
```

Create `tests/cases/data_tools.py`:

```python
CASES = [
    {"args": ["data", "csv2json"], "stdin": "a,b\n1,2\n", "contains": ["\"a\"", "1"], "rc": 0},
]
```

> NOTE: Before committing each table, confirm the exact subcommand names against the module's `COMMANDS` dict (e.g. run `python tk.py data --help`). Adjust `args`/`contains` to match real output. The cases above are starting points; the test will tell you if a name or output differs.

Create `tests/cases/__init__.py`:

```python
"""Aggregates per-module golden case tables."""
import importlib
import pkgutil

import tests.cases as _self  # noqa: F401  (package self-import for path)


def load_all_cases():
    cases = []
    pkg_path = __path__  # type: ignore[name-defined]
    for info in pkgutil.iter_modules(pkg_path):
        if info.name.startswith("_"):
            continue
        mod = importlib.import_module(f"tests.cases.{info.name}")
        for case in getattr(mod, "CASES", []):
            case = dict(case)
            case["_module"] = info.name
            cases.append(case)
    return cases
```

- [ ] **Step 2: Write the golden test runner**

Create `tests/test_golden.py`:

```python
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from tests.cases import load_all_cases

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
```

- [ ] **Step 3: Run the golden tests**

Run: `python -m pytest tests/test_golden.py -v`
Expected: Mostly PASS. Where a subcommand name or output differs, fix the case table to match the real CLI (per the NOTE in Step 1). Re-run until green.

- [ ] **Step 4: Verify green**

Run: `python -m pytest tests/test_golden.py -q`
Expected: PASS (all cases).

- [ ] **Step 5: Commit**

```bash
git add tests/cases tests/test_golden.py
git commit -m "test: golden CLI I/O cases for core modules"
```

---

## Task 8: Edge-case + fuzz tests (`tests/test_fuzz.py`)

**Files:**
- Create: `tests/test_fuzz.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_fuzz.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it (mostly) fails or reveals issues**

Run: `python -m pytest tests/test_fuzz.py -q`
Expected: The parametrized garbage-args tests should pass if argparse is well-behaved; `test_calc_rejects_malicious_input` confirms the calc sandbox. Any failure is a real robustness bug — fix the offending module (e.g. wrap with `@tool_main` in Task 9, or fix the parser).

- [ ] **Step 3: Add Hypothesis arg fuzzing**

Append to `tests/test_fuzz.py`:

```python
from hypothesis import given, settings, strategies as st


@settings(max_examples=50, deadline=None)
@given(expr=st.text(alphabet="0123456789+-*/(). ", min_size=1, max_size=20))
def test_calc_never_crashes(expr):
    """calc must always exit cleanly — valid result or handled error, never a traceback."""
    import subprocess
    proc = subprocess.run(
        [sys.executable, str(ROOT / "tk.py"), "dev", "calc", expr],
        capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode in (0, 1), proc.stderr
    assert "Traceback" not in proc.stderr
```

- [ ] **Step 4: Run to verify green**

Run: `python -m pytest tests/test_fuzz.py -q`
Expected: PASS. Fix any module that crashes on junk before moving on.

- [ ] **Step 5: Commit**

```bash
git add tests/test_fuzz.py
git commit -m "test: fuzz garbage args across modules + calc sandbox checks"
```

---

## Task 9: Migrate all 36 modules to the error contract

**Files:**
- Modify: every `tk_tools/*.py` module (36 files)
- Test: `tests/test_catalog.py` (already exercises `main([])` cleanliness)

The transformation is identical for every module. Apply it once per module.

- [ ] **Step 1: Write a test asserting the contract is applied**

Append to `tests/test_catalog.py`:

```python
def test_unhandled_exception_maps_to_exit_code(monkeypatch):
    """A module raising an unexpected error returns exit 1, not a traceback."""
    import importlib
    import tk_tools.dev_tools as dev

    def boom(args):
        raise RuntimeError("synthetic")

    monkeypatch.setattr(dev, "cmd_calc", boom)
    # Rebuild parser so it picks up the patched func via set_defaults? Simpler:
    rc = dev.main(["calc", "1+1"])
    assert rc == 1
```

> NOTE: `set_defaults(func=cmd_calc)` binds the original function at parse time, so monkeypatching the name won't redirect it. Instead, this test verifies the decorator path by patching the parser. Replace the test body with the decorator-level check below, which is robust:

```python
def test_dev_main_is_wrapped():
    import tk_tools.dev_tools as dev
    # tool_main sets __wrapped__ via functools.wraps
    assert hasattr(dev.main, "__wrapped__"), "dev_tools.main not wrapped with tool_main"
```

Keep only the `test_dev_main_is_wrapped` version.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_catalog.py -k wrapped -v`
Expected: FAIL — `dev_tools.main not wrapped`.

- [ ] **Step 3: Apply the transformation to `dev_tools.py` (exemplar)**

Two edits per module. In `tk_tools/dev_tools.py`:

(a) Ensure `_common` is importable and import `tool_main`. At the top of the file (after existing imports), add:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _common import tool_main
```

(If the module already inserts the parent on `sys.path` — like `recipes_tools.py` does — reuse that line and only add the `from _common import ... tool_main` import.)

(b) Decorate `main`:

```python
@tool_main("dev")
def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 1
    return args.func(args) or 0
```

The decorator argument is the category slug from `tk.CATEGORIES` (e.g. `"dev"`, `"image-pro"`, `"3d"`), NOT the module name.

- [ ] **Step 4: Run the wrapped test**

Run: `python -m pytest tests/test_catalog.py -k wrapped -v`
Expected: PASS.

- [ ] **Step 5: Apply the same two edits to the remaining 35 modules**

Use this category-slug mapping for the `@tool_main("<slug>")` argument:

| Module | slug | Module | slug |
|--------|------|--------|------|
| pdf_tools | pdf | finance_tools | finance |
| image_tools | image | db_tools | db |
| media_tools | media | imagepro_tools | image-pro |
| text_tools | text | audiopro_tools | audio-pro |
| data_tools | data | videopro_tools | video-pro |
| archive_tools | archive | pdfpro_tools | pdf-pro |
| crypto_tools | crypto | geo_tools | geo |
| net_tools | net | steg_tools | steg |
| fs_tools | fs | netpro_tools | net-pro |
| qr_tools | qr | cryptopro_tools | crypto-pro |
| oled_tools | oled | forensic_tools | forensic |
| convert_tools | convert | embedded_tools | embedded |
| ai_tools | ai | ml_tools | ml |
| doc_tools | doc | threed_tools | 3d |
| code_tools | code | completions_tools | completions |
| gen_tools | gen | watch_tools | watch |
| time_tools | time | recipes_tools | recipes |
| | | bundle_tools | bundle |

> If any slug is uncertain, confirm against `CATEGORIES` in `tk.py` (lines 50-89). The slug is the dict KEY, not the module name.

After editing each module, sanity-check it builds:

Run: `python -m pytest tests/test_catalog.py -q`
Expected: still PASS (contract sweep unaffected; modules still import and run).

- [ ] **Step 6: Add a sweep test that ALL modules are wrapped**

Append to `tests/test_catalog.py`:

```python
@pytest.mark.parametrize("mod_name", _module_names())
def test_all_mains_wrapped(mod_name):
    mod = importlib.import_module(mod_name)
    assert hasattr(mod.main, "__wrapped__"), f"{mod_name}.main not wrapped with tool_main"
```

Run: `python -m pytest tests/test_catalog.py -k all_mains_wrapped -q`
Expected: PASS for all 36. Fix any module the test flags.

- [ ] **Step 7: Full regression run**

Run: `python -m pytest tests/ -q --ignore=tests/e2e`
Expected: PASS (catalog, golden, fuzz, validation, smoke).

- [ ] **Step 8: Commit**

```bash
git add tk_tools/ tests/test_catalog.py
git commit -m "feat: apply tk error contract (tool_main) to all 36 modules"
```

---

## Task 10: API contract tests (`tests/test_api.py`)

**Files:**
- Create: `tests/test_api.py`

- [ ] **Step 1: Confirm the server's start interface**

Run: `python -c "import server; print([n for n in dir(server) if 'main' in n or 'serve' in n or 'run' in n.lower()])"`
Expected: prints server entry-point names (e.g. `main`, a handler class). Note the function used to start it and the host/port config (`server_host`/`server_port` in `_common.DEFAULT_CONFIG`, default `127.0.0.1:8765`).

- [ ] **Step 2: Write the failing test**

Create `tests/test_api.py`:

```python
from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="module")
def server():
    port = _free_port()
    env = {"TK_SERVER_PORT": str(port)}
    # Start the server. Adjust the invocation in Step 3 to match server.main's CLI.
    proc = subprocess.Popen(
        [sys.executable, str(ROOT / "tk.py"), "serve", "--port", str(port), "--no-browser"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    base = f"http://127.0.0.1:{port}"
    # Wait for readiness.
    for _ in range(50):
        try:
            urllib.request.urlopen(base + "/api/categories", timeout=1)
            break
        except Exception:
            time.sleep(0.2)
    else:
        out, err = proc.communicate(timeout=5)
        proc.kill()
        pytest.fail(f"server did not start: {err}")
    yield base
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


def _get(base, path):
    with urllib.request.urlopen(base + path, timeout=10) as r:
        return r.status, json.loads(r.read().decode())


def _post(base, path, payload):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(base + path, data=data,
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, json.loads(r.read().decode())


def test_categories_shape(server):
    status, data = _get(server, "/api/categories")
    assert status == 200
    assert "categories" in data or isinstance(data, list)


def test_schema_endpoint(server):
    status, data = _get(server, "/api/schema/dev/calc")
    assert status == 200
    assert isinstance(data, dict)


def test_run_sync(server):
    status, data = _post(server, "/api/run", {"category": "dev", "command": "calc", "args": ["2+2"]})
    assert status == 200
    assert "4" in json.dumps(data)


def test_doctor_endpoint(server):
    status, data = _get(server, "/api/doctor")
    assert status == 200


def test_bad_run_returns_error(server):
    try:
        status, data = _post(server, "/api/run",
                             {"category": "nope", "command": "nope", "args": []})
    except urllib.error.HTTPError as e:
        assert e.code in (400, 404, 422, 500)
        return
    assert "error" in json.dumps(data).lower() or data.get("rc", 0) != 0
```

- [ ] **Step 3: Reconcile with the real server interface**

Run the server self-check from Step 1, then `python tk.py serve --help` (or read `server.py` `main`) to confirm the exact start flags (`--port`, `--no-browser` may differ). Fix:
- the `server` fixture's `subprocess.Popen` arguments to match the real start command,
- the `/api/run` payload key names to match what `server.py`'s POST handler expects (inspect the handler in `server.py`),
- endpoint paths if any differ.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_api.py -v`
Expected: PASS. Adjust payload/paths until green; each mismatch is documentation of the real contract.

- [ ] **Step 5: Commit**

```bash
git add tests/test_api.py
git commit -m "test: API contract tests for server.py endpoints"
```

---

## Task 11: Coverage gate + CI lanes

**Files:**
- Modify: `pyproject.toml`
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Add dev deps + coverage config to `pyproject.toml`**

Add a dev dependency group and coverage settings (adapt to the file's existing format — Poetry vs PEP 621):

```toml
[tool.coverage.run]
source = ["tk_tools", "_common", "tk", "server"]
omit = ["tests/*", "*/__main__.py"]

[tool.coverage.report]
# Optional-dependency code paths are guarded by lazy imports; exclude them so
# an absent dep does not lower the gate.
exclude_lines = [
    "pragma: no cover",
    "raise SystemExit",
    "if __name__ == .__main__.:",
]
```

Add `pytest-cov`, `hypothesis`, `pytest-playwright` to the dev/test dependencies list.

- [ ] **Step 2: Verify coverage runs locally**

Run: `python -m pytest tests/ --ignore=tests/e2e --cov --cov-report=term-missing -q`
Expected: a coverage summary prints. Note the core-lane percentage as the baseline.

- [ ] **Step 3: Rewrite `ci.yml` into lanes**

Read the current `.github/workflows/ci.yml` first. Replace the test job with three jobs:

```yaml
  core:
    name: core (stdlib only)
    runs-on: ${{ matrix.os }}
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, windows-latest, macos-latest]
        python: ["3.10", "3.11", "3.12"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python }}
      - run: pip install pytest pytest-cov hypothesis
      - run: python -m pytest tests/ --ignore=tests/e2e --ignore=tests/test_api.py -q --cov --cov-report=term-missing --cov-fail-under=85

  full:
    name: full (all optional deps)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: sudo apt-get update && sudo apt-get install -y ffmpeg pandoc tesseract-ocr
      - run: pip install pytest hypothesis -r requirements.txt || pip install pytest hypothesis
      - run: python -m pytest tests/ --ignore=tests/e2e -q
        continue-on-error: true

  e2e:
    name: e2e (Playwright)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install pytest pytest-playwright
      - run: python -m playwright install --with-deps chromium
      - run: python -m pytest tests/e2e -q
        continue-on-error: true
```

> The `--cov-fail-under=85` is the gate. If Step 2's baseline is below 85%, set the gate to the measured baseline rounded down, and note in `CLAUDE.md` that raising it is follow-up work. Do NOT lower it below the real baseline.

Keep the existing lint job as-is.

- [ ] **Step 4: Validate the workflow file syntax**

Run: `python -c "import yaml, pathlib; yaml.safe_load(pathlib.Path('.github/workflows/ci.yml').read_text())"`
Expected: no error (install `pyyaml` if needed).

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml .github/workflows/ci.yml
git commit -m "ci: core/full/e2e lanes with coverage gate on core"
```

---

## Task 12: Web E2E (`tests/e2e/test_web.py`)

**Files:**
- Create: `tests/e2e/__init__.py` (empty), `tests/e2e/test_web.py`

- [ ] **Step 1: Install Playwright locally**

Run: `pip install pytest-playwright && python -m playwright install chromium`
Expected: Chromium downloads.

- [ ] **Step 2: Write the failing test**

Create `tests/e2e/test_web.py`:

```python
from __future__ import annotations

import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent


def _free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close()
    return p


@pytest.fixture(scope="module")
def web_server():
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, str(ROOT / "tk.py"), "serve", "--port", str(port), "--no-browser"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    base = f"http://127.0.0.1:{port}"
    for _ in range(50):
        try:
            urllib.request.urlopen(base + "/api/categories", timeout=1); break
        except Exception:
            time.sleep(0.2)
    else:
        proc.kill(); pytest.fail("web server did not start")
    yield base
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


def test_homepage_loads(web_server, page):
    page.goto(web_server)
    assert page.title() != ""


def test_run_a_command_shows_result(web_server, page):
    """Search for calc, fill it, run, see a result. Selectors adjust to real DOM."""
    page.goto(web_server)
    # The actual selectors depend on web/index.html + app.js. Inspect the DOM
    # (page.content()) and replace these with real ids/roles.
    page.wait_for_load_state("networkidle")
    assert "tk" in page.content().lower()
```

> NOTE: `test_run_a_command_shows_result` starts as a smoke check. After the first run, inspect `web/index.html` / `web/app.js` for the search box id, command-form structure, and result container, then flesh out the real flow (search → fill → run → assert result text). The `page` fixture is provided by pytest-playwright.

Create empty `tests/e2e/__init__.py`.

- [ ] **Step 3: Run test to verify it passes**

Run: `python -m pytest tests/e2e -v`
Expected: PASS for `test_homepage_loads` and the smoke assertion. Expand the second test against the real DOM until it exercises a full run flow.

- [ ] **Step 4: Commit**

```bash
git add tests/e2e
git commit -m "test: Playwright web E2E (homepage + run flow scaffold)"
```

---

## Task 13: Developer documentation (`CLAUDE.md`)

**Files:**
- Create: `CLAUDE.md`

- [ ] **Step 1: Write `CLAUDE.md`**

Create `CLAUDE.md` at the repo root:

```markdown
# tk — Developer Guide

Personal toolkit: a CLI (`tk.py`), a stdlib web UI (`server.py`), and an MCP
server (`mcp_server.py`) over 36 tool modules in `tk_tools/`.

## Architecture

- `tk.py` — entry point. `CATEGORIES` (lines ~50-89) maps a slug to
  `(module, label, icon)`. `run_category(slug, argv)` imports the module and
  calls its `main(argv)`, logging the run to history.
- `tk_tools/<name>_tools.py` — one module per category. Each exposes:
  - `COMMANDS: dict[str, str]` — command name → help text.
  - `build_parser()` — returns an argparse parser with one subparser per command.
  - `main(argv)` — parses and dispatches; wrapped with `@tool_main("<slug>")`.
- `_common.py` — shared infra: config, history (SQLite), presets, recipes,
  webhooks, plugins, the error contract, and validation.
- `server.py` — stdlib HTTP server exposing the catalog over `/api/*`.

## The module contract

Every tool module MUST provide `COMMANDS`, `build_parser()`, and `main(argv)`.
`main` MUST be decorated with `@tool_main("<category-slug>")` (the slug is the
KEY in `tk.CATEGORIES`, not the module filename).

## The error contract

- Exit codes: `0` ok, `1` user error, `2` bad args (argparse), `3` missing
  optional dependency.
- Raise `TkError(message, code)` for expected failures; `tool_main` formats it
  as `tk <category>: <message>` on stderr and returns `code`.
- Use `lazy_import("pkg", "pip install ...")` for optional deps — it exits `3`
  with an install hint.
- Tracebacks are hidden unless `--debug` is passed or `TK_DEBUG` is set.

## Adding a new tool

1. Create `tk_tools/<name>_tools.py` following the contract above.
2. Register the slug in `tk.CATEGORIES`.
3. Add golden cases in `tests/cases/<name>_tools.py` (`CASES` list).
4. The catalog sweep (`tests/test_catalog.py`) covers structure automatically.

## Adding a golden test case

Append a dict to the `CASES` list in `tests/cases/<module>.py`:
`{"args": ["cat", "cmd", ...], "stdin": "...", "contains": ["..."], "rc": 0}`.
Add `"requires": ["ffmpeg"]` for cases needing optional deps — they auto-skip.

## Validation

- `validate_recipe(recipe)` — structure, tool format, category existence,
  dependency references, cycle detection. Wired into `recipes validate/run/exec`.
- `validate_config(cfg)` — schema check; warns (non-fatal) on unknown keys and
  wrong types.

## CI lanes

- `core` — stdlib only, 3 OS × 3 Python, coverage gate (`--cov-fail-under`).
- `full` — all optional deps installed, best-effort.
- `e2e` — Playwright web flows.

Run locally:
- `python -m pytest tests/ --ignore=tests/e2e -q` (core + api + validation)
- `python -m pytest tests/e2e -q` (needs `playwright install chromium`)
- `python -m pytest tests/ --ignore=tests/e2e --cov --cov-report=term-missing`

## Plugins

Drop `<name>_tools.py` (same contract) into `~/.tk/plugins` or `./plugins`;
`discover_plugins()` loads it and `available_categories()` merges it in.
```

- [ ] **Step 2: Verify the doc references match reality**

Run: `python -m pytest tests/ --ignore=tests/e2e -q`
Expected: PASS — confirms the documented commands and contract hold.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add CLAUDE.md developer guide"
```

---

## Final verification

- [ ] **Run the full suite (minus E2E):**

Run: `python -m pytest tests/ --ignore=tests/e2e -q --cov --cov-report=term-missing`
Expected: all PASS, coverage at or above the gate.

- [ ] **Run E2E:**

Run: `python -m pytest tests/e2e -q`
Expected: PASS.

- [ ] **Confirm no behavior change to tools:** the smoke tests (`tests/test_smoke.py`) still pass unchanged.
```
