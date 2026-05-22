# CLAUDE.md — tk Developer & Architecture Guide

`tk` is a personal all-in-one CLI toolkit and web UI: 36 built-in tool categories, a stdlib HTTP server, an MCP server, and a plugin system.

---

## Architecture

```
tk.py              Entry point, CATEGORIES registry, routing, meta-commands
tk_tools/          One module per category: <name>_tools.py
_common.py         Shared infra: error contract, config, history, plugins, recipes
server.py          Stdlib HTTP web UI + JSON API
mcp_server.py      MCP stdio server (JSON-RPC 2.0 over stdin/stdout)
tests/             Pytest suite (catalog, golden, fuzz, API, validation, smoke, e2e)
.github/workflows/ CI lanes (lint, core, full, e2e, build-binary)
```

### `tk.py` — entry point and CATEGORIES

`CATEGORIES` is a `dict[str, tuple[str, str, str]]` mapping a stable CLI/URL slug to `(module_dotted_path, label, icon)`. There are **36 built-in categories** (lines 50–89). Example:

```python
CATEGORIES = {
    "dev":  ("tk_tools.dev_tools",  "Regex, color, lorem, base, calc, timestamp, slug", "⚙️"),
    "text": ("tk_tools.text_tools", "Encoding, hashes, case conversion, JSON format, diff", "✍️"),
    # ... 34 more
}
```

`run_category(category, argv)` loads the module via `importlib`, calls `mod.main(argv)`, catches `SystemExit` / `KeyboardInterrupt`, logs to history, and returns an integer exit code.

`available_categories()` returns built-ins merged with plugins discovered by `discover_plugins()`.

### `tk_tools/` — tool modules

Each file is `tk_tools/<name>_tools.py`. The slug used in `CATEGORIES` is the key (e.g. `"dev"`), **not** derived from the filename.

### `_common.py` — shared infrastructure

- Error contract (exit codes, `TkError`, `tool_main`, `lazy_import`)
- Config: `load_config()` / `save_config()` with TOML at `~/.tk/config.toml`
- History: SQLite at `~/.tk/history.db`
- Presets, recipes, webhooks
- Plugin discovery

### `server.py` — web UI and JSON API

Pure-stdlib `http.server`-based web UI. Serves `web/` as static files and exposes a REST JSON API. Also supports async jobs (SSE), batch runs, file workspace, presets, history, config, and webhooks.

### `mcp_server.py` — MCP server

Exposes every category/command as an MCP tool over JSON-RPC 2.0 on stdio. Supports `initialize`, `tools/list`, `tools/call`, `resources/list`, `resources/read`. Configure in an MCP client (e.g. Claude Desktop) as:

```json
{
  "mcpServers": {
    "tk": {
      "command": "python",
      "args": ["c:/path/to/tools/mcp_server.py"]
    }
  }
}
```

---

## Module Contract

Every `tk_tools/<name>_tools.py` **must** expose:

| Symbol | Type | Purpose |
|---|---|---|
| `COMMANDS` | `dict[str, str]` | Maps command name → one-line help string |
| `build_parser()` | `() -> ArgumentParser` | Returns the top-level argparse parser |
| `main(argv)` | decorated callable | Entry point; **must** be wrapped with `@tool_main("<slug>")` |

The `slug` passed to `@tool_main` must match the key in `tk.CATEGORIES` — it is used to format error messages as `tk <slug>: <message>`.

Example:

```python
from _common import tool_main

COMMANDS = {"calc": "Evaluate a math expression"}

def build_parser():
    ...

@tool_main("dev")          # slug matches CATEGORIES key, not filename
def main(argv=None):
    ...
```

`test_catalog.py::test_all_mains_wrapped` enforces `hasattr(mod.main, "__wrapped__")` for every module.

---

## Error Contract

### Exit codes

| Constant | Value | Meaning |
|---|---|---|
| `EXIT_OK` | 0 | Success |
| `EXIT_USER_ERROR` | 1 | Bad input, file not found, runtime failure |
| `EXIT_BAD_ARGS` | 2 | Invalid CLI arguments |
| `EXIT_MISSING_DEP` | 3 | Optional dependency not installed |

### `TkError`

```python
raise TkError("file not found", code=EXIT_USER_ERROR)
```

Raise from inside `main()`. The `tool_main` decorator catches it, prints `tk <slug>: <message>` to stderr, and returns `e.code`.

### `tool_main(category)` decorator behaviour

- `TkError` → print `tk <slug>: <msg>` to stderr, return `e.code`
- `SystemExit` → re-raised unchanged (argparse help, `lazy_import`)
- `KeyboardInterrupt` → returns 130
- Any other `Exception` → print `tk <slug>: <msg>` to stderr, return `EXIT_USER_ERROR`; full traceback only when `--debug` is in `argv` **or** `TK_DEBUG` env var is set

### `lazy_import(module_name, install_hint=None)`

```python
pypdf = lazy_import("pypdf", "pip install pypdf")
```

On `ImportError`: prints a friendly install message and raises `SystemExit(EXIT_MISSING_DEP)`. Use this at the top of any function that needs an optional dependency.

---

## Adding a New Tool Module

1. **Create** `tk_tools/<name>_tools.py` with `COMMANDS`, `build_parser()`, and a `@tool_main("<slug>")`-decorated `main(argv=None)`.

2. **Register** the slug in `tk.CATEGORIES`:
   ```python
   "mycat": ("tk_tools.mycat_tools", "Short description", "🔧"),
   ```
   The slug is the stable CLI/URL key — keep it short and lowercase.

3. **Decorate** `main` with `@tool_main("mycat")` — the slug must match step 2.

4. **Add golden test cases** in `tests/cases/mycat_tools.py` (see below).

The catalog sweep in `test_catalog.py` automatically covers: `COMMANDS` present, `build_parser()` works, `main` is wrapped, `main([])` doesn't traceback, and every command's `--help` is parseable.

---

## Adding a Golden Test Case

Append a dict to `CASES` in `tests/cases/<module>_tools.py`:

```python
CASES = [
    {
        "args":     ["mycat", "mycommand", "--flag", "value"],
        "stdin":    None,            # optional: string fed to stdin
        "contains": ["expected"],   # substrings that must appear in stdout
        "rc":       0,              # expected exit code (default 0)
        "requires": ["pypdf"],      # optional: auto-skip if dep missing
    },
]
```

`requires`-gated cases are automatically skipped via `pytest.skip` when the dep (Python module or binary on PATH) is absent. Cases are loaded by `tests/cases/__init__.py::load_all_cases()` and parametrised in `test_golden.py`.

---

## Recipe Validation

`_common.validate_recipe(recipe)` returns a list of human-readable error strings (empty = valid). It checks:

- `steps` is a non-empty list
- Each step has a unique `id` (synthesised as `s0`, `s1`, ... when omitted)
- `tool` is in `"category:command"` format and the category exists
- Each step has `argv` or `args`
- `depends` references resolve to real step ids
- The dependency graph is acyclic (Kahn's algorithm)

`_common.validate_config(cfg)` checks the config dict against `CONFIG_SCHEMA` — unknown keys and wrong value types produce warnings (non-fatal, printed to stderr, deduped per process).

### CLI validation

```bash
python tk.py recipes validate path/to/recipe.json
```

`recipes run` and `recipes exec` also validate before executing.

---

## Web Server

### Starting the server

```bash
# Default port 8765, opens browser
python tk.py server

# Headless, custom port
python tk.py server --port 9000 --no-browser

# Aliases: "ui" and "web" are equivalent to "server"
python tk.py ui --no-browser
```

Flags: `--host` (default `127.0.0.1`), `--port` (default `8765`), `--no-browser`.

### `/api/run` — synchronous tool execution

**Request:**
```json
POST /api/run
Content-Type: application/json

{
  "category": "dev",
  "command":  "calc",
  "args":     ["2+2"]
}
```

**Response (200):**
```json
{
  "rc":        0,
  "stdout":    "4\n",
  "stderr":    "",
  "new_files": [],
  "new_dirs":  []
}
```

Unknown category → HTTP 400 `{"error": "unknown category"}`. Non-list `args` → HTTP 400 `{"error": "args must be a list"}`.

Other API endpoints: `/api/run-async` (SSE jobs), `/api/batch`, `/api/categories`, `/api/schema/<cat>/<cmd>`, `/api/files`, `/api/upload`, `/api/presets`, `/api/history`, `/api/config`, `/api/doctor`, `/api/themes`, `/api/version`.

---

## Tests and CI

### Running tests locally

```bash
# Core suite (catalog / golden / fuzz / api / validation / smoke) — no optional deps needed
python -m pytest tests/ --ignore=tests/e2e -q

# E2E (Playwright) — install deps first
pip install pytest-playwright && python -m playwright install chromium
python -m pytest tests/e2e -q

# Core with coverage report
python -m pytest tests/ --ignore=tests/e2e --cov --cov-report=term-missing
```

### Test files

| File | What it tests |
|---|---|
| `tests/conftest.py` | Fixtures: `all_tool_modules`, `run_cli`, `requires` |
| `test_smoke.py` | Basic imports and CLI invocation |
| `test_catalog.py` | Contract sweep: `COMMANDS`, `build_parser`, `main` wrapped, `main([])`, per-command `--help` |
| `test_golden.py` | Parametrised I/O table from `tests/cases/*.py` |
| `test_fuzz.py` | Garbage args per module, `dev calc` AST sandbox, Hypothesis property tests |
| `test_validation.py` | `validate_recipe` and `validate_config` logic |
| `test_api.py` | Live server: `/api/run`, `/api/categories`, `/api/schema`, `/api/doctor`, etc. |
| `tests/e2e/test_web.py` | Playwright browser tests (importorskip-guarded) |

### CI lanes (`.github/workflows/ci.yml`)

| Lane | Trigger | Matrix | Notes |
|---|---|---|---|
| `lint` | every push/PR | ubuntu, py3.12 | `ruff check` + format check |
| `core` | every push/PR | 3 OS × py3.10/3.11/3.12 | `--cov-fail-under=25` (coverage gate) |
| `full` | every push/PR | ubuntu, py3.12 | optional deps installed; `continue-on-error: true` |
| `e2e` | every push/PR | ubuntu, py3.12 | Playwright; `continue-on-error: true` |
| `build-binary` | tag `v*` only | 3 OS | PyInstaller `--onefile`; needs lint+core to pass |

**Coverage source:** `tk_tools`, `_common`, `tk`, `server`. Current gate: **25% minimum** — this is a floor to raise once optional-dep lanes contribute coverage. Do not lower it.

---

## Security

**`dev calc` uses an AST-whitelist evaluator — never `eval` or `exec` on user input.**

The `calc` command parses the expression with Python's `ast` module and walks the tree, only allowing literal values and safe arithmetic operators. This prevents arbitrary code execution.

`calc` is reachable via the web API at `/api/run` with `{"category": "dev", "command": "calc", ...}`. The AST whitelist must be maintained; never reintroduce `eval`/`exec` for user-supplied expressions anywhere in the codebase.

---

## Plugins

Drop a `<name>_tools.py` file (same contract as built-in modules: `COMMANDS`, `build_parser()`, `@tool_main("<slug>")`-decorated `main`) into either:

- `~/.tk/plugins/` — user-global plugins
- `./plugins/` — project-local plugins

`discover_plugins()` in `_common.py` scans both directories for `*_tools.py` files and loads them. `available_categories()` merges discovered plugins into the built-in registry. The category key is derived from the filename stem with `_tools` stripped (e.g. `mycat_tools.py` → slug `mycat`). Optionally define `LABEL` and `ICON` module-level variables to customise the display name and icon (defaults: title-cased slug and 🧩).
