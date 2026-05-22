# tk Hardening (Phase 1: Depth) — Design Spec

**Date:** 2026-05-22
**Status:** Approved, ready for implementation planning
**Scope level:** Max (tests + validation + API + E2E + coverage gate + fuzzing + dev docs)

## Context

`tk` is a personal toolkit at v0.3.1: 36 tool modules in `tk_tools/`, 455 commands, a stdlib HTTP web UI (`server.py`), an MCP server (`mcp_server.py`), a single-file `.pyz` bundle, shell completions, a browser extension, and CI (3 OS × 3 Python). The codebase is feature-complete with zero `NotImplementedError` stubs.

The weakness is depth, not breadth. Current testing is 12 smoke tests in `tests/test_smoke.py` — imports + a handful of CLI flows. There are no per-command tests, no API contract tests, no web E2E tests, no recipe/config validation, no standardized error handling, and no developer documentation.

This is Phase 1 of a 4-phase roadmap (Depth → Reach → UX → Breadth). Each phase gets its own spec/plan/build cycle. This spec covers Depth only.

## Goals

- Real, scaling test coverage of all 455 commands across 36 modules.
- A coverage gate with teeth on stdlib-only ("core") code.
- Standardized error contract across every `main()`.
- Recipe and config validation.
- API contract tests for all `server.py` endpoints.
- Web UI E2E tests for key flows.
- Edge-case / fuzz testing for robustness.
- Developer documentation (`CLAUDE.md`).

## Non-goals

- No new tool modules or commands (that is Phase 4: Breadth).
- No distribution/packaging work (Phase 2: Reach).
- No UX/web redesign (Phase 3: UX).
- No refactor of working tool logic beyond what the error contract migration requires.

## Architecture

### Test strategy: introspection-driven (Approach A)

The codebase already exposes a uniform module contract: each module has a `COMMANDS` dict, a `build_parser()`, and a `main(argv)`. Tests exploit this rather than hand-writing 455 cases.

**`tests/conftest.py`** — shared fixtures and capability detection.
- `requires(*deps)` pytest marker / helper that skips a test when an optional dependency is absent.
- Capability detection reuses the existing `doctor` logic from `_common.py` (single source of truth for "is ffmpeg/pandoc/tesseract/ollama/<ml lib> available").
- A `run_tk(args, stdin=None)` fixture that invokes a command in-process and captures exit code, stdout, stderr.

**`tests/test_catalog.py`** — introspection sweep, parametrized over all 36 modules and every command in each `COMMANDS`:
- module imports clean
- `build_parser()` returns a parser
- every command has a subparser and `--help` exits 0
- `main([])` and `main(["<cmd>", "--bad-arg"])` produce a clean exit (proper code + stderr), never an uncaught traceback

New tools are covered automatically — no new test code needed when a module is added.

**`tests/cases/<module>.py`** — golden I/O tables, one per module:
```python
CASES = [
    {"cmd": "text hash --algo sha256", "stdin": "abc", "expect": "ba7816bf..."},
    {"cmd": "embedded crc16", "args": [...], "expect": "..."},
]
```
Cases needing optional deps carry `requires=["ffmpeg"]` and auto-skip when absent.

**`tests/test_golden.py`** — runs all golden cases. Adding real-I/O coverage is one dict entry, not a new function.

### Error contract (`_common.py`)

Standardize every module's `main()`:

| Exit code | Meaning |
|-----------|---------|
| 0 | success |
| 1 | user error (bad input, file not found, runtime failure) |
| 2 | bad arguments (argparse) |
| 3 | missing optional dependency |

- Errors print to stderr, format `tk <cat> <cmd>: <message>`.
- No traceback shown unless `--debug` is passed.
- Missing optional dep → exit 3 with an install hint (e.g. `pip install tk[image]` / `install ffmpeg`).

Add to `_common.py`:
- `tk_error(message, code=1)` helper.
- `@tool_main` decorator wrapping a module's run function: catches exceptions, maps known cases to exit codes, formats stderr, honors `--debug`.

Migrate all 36 modules to use the wrapper/helper.

### Validation (`_common.py`)

- **Recipe validation:** JSON schema for recipe structure (steps, each step's `tool` + `args` + inter-step refs), DAG cycle detection, unknown-tool check against the live category/command registry. Exposed as `recipes validate <file>` and invoked automatically before `recipes run`/`exec`.
- **Config validation:** schema for `config.toml` keys and their types; validate on load; warn (not fail) on unknown keys.

### API contract tests (`tests/test_api.py`)

Spin `server.py` on an ephemeral port (fixture), then exercise all 28 endpoints:
- `/api/categories`, `/api/schema/<cat>/<cmd>` — response shape.
- `/api/run` (sync), `/api/run-async` + `/api/jobs/<id>/events` (SSE stream reaches a terminal state).
- preset CRUD, `/api/history`, `/api/doctor`, `/api/themes`, `/api/config`.
- file ops (`/api/files/*`, `/api/upload`, `/api/clear`).
- 4xx on malformed input.

### Web E2E (`tests/e2e/`)

`pytest-playwright`, headless Chromium. Key flows:
- search (Ctrl+K) → fill auto-generated form → run → see result
- theme switch persists
- file upload → inline preview
- preset save → load
- recipe run from pipeline editor

Tagged `e2e`; runs in a dedicated CI job (heavier deps).

### Coverage gate + CI lanes

- `pytest-cov` measures coverage.
- Gate the **core lane** (stdlib-only tool code) at **85%**. Optional-dependency code paths excluded from the denominator via `# pragma: no cover` on lazy-import guards, so an absent dep never tanks the number.
- CI lanes:
  - **core** — no optional deps; full catalog + golden + fuzz + API tests; coverage gate enforced; existing 3 OS × 3 Python matrix.
  - **full** — ffmpeg/pandoc/tesseract/ML libs installed; runs dep-tagged cases; best-effort (no gate).
  - **e2e** — Playwright flows.

### Edge-case fuzzing (`tests/test_fuzz.py`)

Feed each command malformed inputs: empty files, oversized files, binary garbage where text expected, bad encodings, junk argument values. Assert a clean exit code and that the process never crashes with an uncaught traceback or hangs. Use Hypothesis for argument fuzzing against parsers.

### Developer docs (`CLAUDE.md`)

Architecture overview; the module contract (`COMMANDS` / `build_parser()` / `main()`); the error contract; how to add a new tool; how to add a golden test case; the plugin API; the CI lanes and how to run each locally.

## Deliverables

**New files:**
- `tests/conftest.py`
- `tests/test_catalog.py`
- `tests/test_golden.py`
- `tests/test_api.py`
- `tests/test_fuzz.py`
- `tests/cases/*.py` (one per module)
- `tests/e2e/*`
- `CLAUDE.md`

**Modified:**
- `_common.py` — error helpers (`tk_error`, `@tool_main`), recipe validation, config validation.
- All 36 `tk_tools/*.py` — migrate to error contract.
- `tk_tools/recipes_tools.py` — wire in `recipes validate`.
- `.github/workflows/ci.yml` — core / full / e2e lanes + coverage gate.
- `pyproject.toml` — dev dependencies (pytest-cov, pytest-playwright, hypothesis), coverage config.

## Implementation sequence

1. Error contract in `_common.py` (`tk_error`, `@tool_main`).
2. Migrate 36 modules to the error contract.
3. Test harness: `conftest.py` + `test_catalog.py`.
4. Golden cases (`tests/cases/*.py`) + `test_golden.py`.
5. Fuzz tests (`test_fuzz.py`).
6. Recipe + config validation in `_common.py`; wire `recipes validate`.
7. API contract tests (`test_api.py`).
8. Coverage gate + CI lanes (`ci.yml`, `pyproject.toml`).
9. Web E2E (`tests/e2e/`).
10. `CLAUDE.md`.

## Risks / open questions

- **Windows-primary environment:** E2E and the `full` dep lane are heaviest on CI; local dev is Windows. E2E may run only on Linux CI to start.
- **Coverage threshold 85%** is a starting target; may adjust once the core-lane baseline is measured.
- **Error-contract migration touches 36 files** — mechanical but broad; do it first so the harness tests the final contract.
