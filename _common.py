"""Shared helpers for the tools suite.

Includes:
- lazy_import / confirm / human_size / ensure_dir   (originals, unchanged API)
- config           — load / save TOML config
- history          — sqlite-backed run log
- presets          — save / load / list argument presets
- plugins          — discover external tool modules from ~/.tk/plugins or ./plugins
"""
from __future__ import annotations

import functools
import importlib
import importlib.util
import json
import os
import sqlite3
import sys
import time
from collections import deque
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable


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


def _debug_enabled(argv: list[str] | None) -> bool:
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


# ---------------------------------------------------------------- import helpers

def lazy_import(module_name: str, install_hint: str | None = None):
    """Import a module; on failure print a friendly install hint and exit."""
    try:
        return importlib.import_module(module_name)
    except ImportError:
        hint = install_hint or f"pip install {module_name}"
        print(f"\n[!] Required module '{module_name}' is not installed.")
        print(f"    Install with: {hint}\n")
        raise SystemExit(EXIT_MISSING_DEP)


def have_module(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def have_binary(name: str) -> bool:
    """Check if an external binary is on PATH."""
    from shutil import which
    return which(name) is not None


# ---------------------------------------------------------------- I/O helpers

def confirm(prompt: str, default: bool = False) -> bool:
    yn = "Y/n" if default else "y/N"
    try:
        ans = input(f"{prompt} [{yn}]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    if not ans:
        return default
    return ans in ("y", "yes")


def human_size(n: int | float) -> str:
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}PB"


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


# ---------------------------------------------------------------- locations

ROOT = Path(__file__).parent
HOME_DIR = ensure_dir(Path(os.path.expanduser("~")) / ".tk")
PRESETS_DIR = ensure_dir(HOME_DIR / "presets")
RECIPES_DIR = ensure_dir(HOME_DIR / "recipes")
HOOKS_DIR   = ensure_dir(HOME_DIR / "hooks")
PLUGINS_DIR = ensure_dir(HOME_DIR / "plugins")
LOCAL_PLUGINS_DIR = ROOT / "plugins"
HISTORY_DB = HOME_DIR / "history.db"
CONFIG_FILE = HOME_DIR / "config.toml"


# ---------------------------------------------------------------- config (TOML)

DEFAULT_CONFIG: dict[str, Any] = {
    "theme": "dark",
    "workspace": str(ROOT / "web_workspace"),
    "server_host": "127.0.0.1",
    "server_port": 8765,
    "open_browser": True,
    "ollama_host": "http://localhost:11434",
    "ollama_model": "llama3.2",
    "ffmpeg_path": "ffmpeg",
    "history_enabled": True,
    "history_keep": 500,
}


def load_config() -> dict[str, Any]:
    cfg = dict(DEFAULT_CONFIG)
    if CONFIG_FILE.exists():
        try:
            import tomllib  # py311+
        except ImportError:
            try:
                tomllib = importlib.import_module("tomli")
            except ImportError:
                return cfg
        try:
            with open(CONFIG_FILE, "rb") as f:
                cfg.update(tomllib.load(f))
        except Exception:
            pass
    return cfg


def save_config(cfg: dict[str, Any]) -> None:
    lines = []
    for k, v in cfg.items():
        if isinstance(v, bool):
            lines.append(f"{k} = {'true' if v else 'false'}")
        elif isinstance(v, (int, float)):
            lines.append(f"{k} = {v}")
        else:
            esc = str(v).replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'{k} = "{esc}"')
    CONFIG_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- history

@contextmanager
def _db():
    conn = sqlite3.connect(HISTORY_DB)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _init_history():
    with _db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                ts           REAL NOT NULL,
                category     TEXT NOT NULL,
                command      TEXT NOT NULL,
                args_json    TEXT NOT NULL,
                rc           INTEGER NOT NULL,
                duration_ms  INTEGER NOT NULL,
                stdout       TEXT,
                stderr       TEXT
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS ix_runs_ts ON runs(ts DESC)")


def log_run(
    category: str,
    command: str,
    args: list[str],
    rc: int,
    duration_ms: int,
    stdout: str = "",
    stderr: str = "",
) -> int:
    """Append a run record. Returns the new row id."""
    _init_history()
    with _db() as conn:
        cur = conn.execute(
            "INSERT INTO runs(ts, category, command, args_json, rc, duration_ms, stdout, stderr) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                time.time(),
                category,
                command,
                json.dumps(args),
                rc,
                duration_ms,
                stdout[-4000:],
                stderr[-4000:],
            ),
        )
        # Cap history size.
        cfg = load_config()
        keep = int(cfg.get("history_keep", 500))
        conn.execute(
            "DELETE FROM runs WHERE id IN (SELECT id FROM runs ORDER BY ts DESC LIMIT -1 OFFSET ?)",
            (keep,),
        )
        return cur.lastrowid


def recent_runs(limit: int = 50) -> list[dict]:
    if not HISTORY_DB.exists():
        return []
    _init_history()
    with _db() as conn:
        rows = conn.execute(
            "SELECT id, ts, category, command, args_json, rc, duration_ms FROM runs ORDER BY ts DESC LIMIT ?",
            (limit,),
        ).fetchall()
    out = []
    for r in rows:
        out.append({
            "id": r["id"],
            "ts": r["ts"],
            "category": r["category"],
            "command": r["command"],
            "args": json.loads(r["args_json"]),
            "rc": r["rc"],
            "duration_ms": r["duration_ms"],
        })
    return out


# ---------------------------------------------------------------- presets

def preset_save(name: str, category: str, command: str, args: list[str]) -> Path:
    safe = "".join(c for c in name if c.isalnum() or c in "-_") or "preset"
    path = PRESETS_DIR / f"{safe}.json"
    path.write_text(json.dumps({
        "name": name,
        "category": category,
        "command": command,
        "args": list(args),
        "ts": time.time(),
    }, indent=2), encoding="utf-8")
    return path


def preset_load(name: str) -> dict | None:
    p = PRESETS_DIR / f"{name}.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def preset_list() -> list[dict]:
    out = []
    for p in sorted(PRESETS_DIR.glob("*.json")):
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            continue
    return out


def preset_delete(name: str) -> bool:
    p = PRESETS_DIR / f"{name}.json"
    if p.exists():
        p.unlink()
        return True
    return False


# ---------------------------------------------------------------- recipes (pipelines)

def _safe_filename(name: str) -> str:
    return "".join(c for c in name if c.isalnum() or c in "-_") or "recipe"


def recipe_save(name: str, recipe: dict) -> Path:
    """Persist a recipe JSON. Recipe shape: {name, description?, steps: [...], layout?}."""
    recipe = dict(recipe)
    recipe.setdefault("name", name)
    recipe["saved_at"] = time.time()
    path = RECIPES_DIR / f"{_safe_filename(name)}.json"
    path.write_text(json.dumps(recipe, indent=2), encoding="utf-8")
    return path


def recipe_load(name: str) -> dict | None:
    p = RECIPES_DIR / f"{_safe_filename(name)}.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def recipe_list() -> list[dict]:
    out = []
    for p in sorted(RECIPES_DIR.glob("*.json")):
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            continue
    return out


def recipe_delete(name: str) -> bool:
    p = RECIPES_DIR / f"{_safe_filename(name)}.json"
    if p.exists():
        p.unlink()
        return True
    return False


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

        tool = step.get("tool") or ""
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


# ---------------------------------------------------------------- webhooks

import secrets as _secrets


def hook_save(name: str, recipe_name: str, token: str | None = None) -> dict:
    """Bind a webhook token to a saved recipe."""
    token = token or _secrets.token_urlsafe(24)
    rec = {
        "name":   name,
        "recipe": recipe_name,
        "token":  token,
        "created_at": time.time(),
    }
    (HOOKS_DIR / f"{_safe_filename(name)}.json").write_text(json.dumps(rec, indent=2), encoding="utf-8")
    return rec


def hook_list() -> list[dict]:
    out = []
    for p in sorted(HOOKS_DIR.glob("*.json")):
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            continue
    return out


def hook_by_token(token: str) -> dict | None:
    for h in hook_list():
        if h.get("token") == token:
            return h
    return None


def hook_delete(name: str) -> bool:
    p = HOOKS_DIR / f"{_safe_filename(name)}.json"
    if p.exists():
        p.unlink()
        return True
    return False


# ---------------------------------------------------------------- plugins

def discover_plugins() -> dict[str, dict]:
    """Scan ~/.tk/plugins and ./plugins for *_tools.py files.

    A plugin file should expose `COMMANDS` dict and `main(argv)` and `build_parser()`,
    matching the built-in module shape. Returns mapping category-key -> info.
    """
    found: dict[str, dict] = {}
    for d in (PLUGINS_DIR, LOCAL_PLUGINS_DIR):
        if not d.exists():
            continue
        for f in d.glob("*_tools.py"):
            key = f.stem.replace("_tools", "")
            try:
                spec = importlib.util.spec_from_file_location(f.stem, f)
                if spec is None or spec.loader is None:
                    continue
                mod = importlib.util.module_from_spec(spec)
                sys.modules[f.stem] = mod
                spec.loader.exec_module(mod)
            except Exception as e:
                print(f"[plugin] failed to load {f}: {e}", file=sys.stderr)
                continue
            found[key] = {
                "module": f.stem,
                "label": getattr(mod, "LABEL", key.title()),
                "icon": getattr(mod, "ICON", "🧩"),
                "path": str(f),
            }
    return found


# ---------------------------------------------------------------- output helpers

def write_json(data: Any, output: Path | str | None = None) -> None:
    text = json.dumps(data, indent=2, default=str)
    if output:
        Path(output).write_text(text, encoding="utf-8")
        print(f"Wrote {output}")
    else:
        print(text)


def emit(data: Any, output: Path | str | None = None, as_json: bool = False) -> None:
    """Print or write either pretty text or json (if as_json)."""
    if as_json:
        write_json(data, output)
        return
    if isinstance(data, (dict, list)):
        text = json.dumps(data, indent=2, default=str)
    else:
        text = str(data)
    if output:
        Path(output).write_text(text, encoding="utf-8")
        print(f"Wrote {output}")
    else:
        print(text)


def progress(it: Iterable, total: int | None = None, label: str = ""):
    """Cheap progress printer. Updates one line. No deps."""
    n = 0
    last = 0
    start = time.time()
    for x in it:
        yield x
        n += 1
        now = time.time()
        if total:
            pct = n * 100 // max(total, 1)
            if pct != last:
                sys.stderr.write(f"\r{label} {pct:3d}%  ({n}/{total})")
                sys.stderr.flush()
                last = pct
        elif now - start > 0.5:
            sys.stderr.write(f"\r{label} {n} done…")
            sys.stderr.flush()
    sys.stderr.write("\n")
