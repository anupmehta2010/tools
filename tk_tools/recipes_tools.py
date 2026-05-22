"""Recipes: save and run multi-step pipelines as JSON.

A recipe is JSON like:

    {
      "name": "photo-cleanup",
      "description": "Strip bg, resize, compress",
      "steps": [
        {"id": "n1", "tool": "image-pro:rembg",  "argv": ["{{input}}", "step1.png"]},
        {"id": "n2", "tool": "image:resize",     "argv": ["step1.png", "--width", "1200", "-o", "step2.png"], "depends": ["n1"]},
        {"id": "n3", "tool": "image:compress",   "argv": ["step2.png", "-o", "{{output}}", "--quality", "80"], "depends": ["n2"]}
      ]
    }

Steps run in topological order. Variables: any `{{name}}` token in argv strings
is substituted from the `vars` dict supplied at run time. Step IDs are arbitrary
strings.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _common import (
    recipe_save, recipe_load, recipe_list, recipe_delete, emit, validate_recipe,
)


COMMANDS = {
    "list":   "List saved recipes",
    "show":   "Show a saved recipe (pretty JSON)",
    "save":   "Save a recipe from a JSON file",
    "delete": "Delete a saved recipe",
    "run":    "Run a saved recipe by name (with --var key=value pairs)",
    "exec":   "Run a recipe directly from a JSON file (no save)",
    "scaffold": "Print a starter recipe JSON to stdout",
    "validate": "Validate a recipe JSON file (structure, refs, cycles)",
}


# ---------------------------------------------------------------- execution

def _expand(value, variables: dict, step_outputs: dict) -> str:
    """Substitute {{var}} and {{steps.ID.output}} placeholders in a string."""
    if not isinstance(value, str):
        return value
    out = value
    # steps.<id>.output / .stdout
    import re
    for m in re.finditer(r"\{\{steps\.([\w\-]+)\.(\w+)\}\}", value):
        sid, field = m.group(1), m.group(2)
        if sid in step_outputs and field in step_outputs[sid]:
            out = out.replace(m.group(0), str(step_outputs[sid][field]))
    # plain {{key}}
    for k, v in variables.items():
        out = out.replace("{{" + k + "}}", str(v))
    return out


def _topo_sort(steps: list[dict]) -> list[dict]:
    """Kahn's algorithm. Steps without depends come first."""
    ids = [s.get("id", f"s{i}") for i, s in enumerate(steps)]
    by_id = {s.get("id", f"s{i}"): s for i, s in enumerate(steps)}
    in_deg = {sid: 0 for sid in ids}
    children: dict[str, list[str]] = {sid: [] for sid in ids}
    for s in steps:
        sid = s.get("id")
        for d in s.get("depends", []) or []:
            in_deg[sid] = in_deg.get(sid, 0) + 1
            children.setdefault(d, []).append(sid)
    q = deque([sid for sid in ids if in_deg.get(sid, 0) == 0])
    order = []
    while q:
        sid = q.popleft()
        order.append(by_id[sid])
        for c in children.get(sid, []):
            in_deg[c] -= 1
            if in_deg[c] == 0:
                q.append(c)
    if len(order) != len(steps):
        raise ValueError("recipe has a dependency cycle")
    return order


def run_recipe(recipe: dict, variables: dict | None = None, *, emit_event=None) -> dict:
    """Execute a recipe. `emit_event(kind, payload)` lets callers stream progress.

    Returns: {ok: bool, results: {step_id: {rc, stdout, stderr, new_files}}}
    """
    import tk  # lazy to avoid circular at import time
    variables = dict(variables or {})
    steps = _topo_sort(recipe.get("steps", []))
    out: dict[str, dict] = {}
    ok = True

    if emit_event:
        emit_event("recipe_start", {"name": recipe.get("name", "_inline"), "steps": [s.get("id") for s in steps]})

    for step in steps:
        sid = step.get("id")
        tool = step.get("tool", "")
        if ":" not in tool:
            ok = False
            out[sid] = {"rc": 1, "stdout": "", "stderr": f"step '{sid}': bad tool '{tool}'", "new_files": []}
            if emit_event:
                emit_event("node_error", {"id": sid, "error": "bad tool"})
            break
        cat, _, cmd = tool.partition(":")

        # Build argv. Either step["argv"] (list of raw strings) or step["args"]
        # (dict converted to flags).
        if "argv" in step:
            argv = [_expand(str(x), variables, out) for x in step["argv"]]
        elif "args" in step:
            argv = []
            for k, v in step["args"].items():
                if isinstance(v, bool):
                    if v:
                        argv.append(f"--{k}" if len(k) > 1 else f"-{k}")
                elif isinstance(v, list):
                    argv.append(f"--{k}")
                    argv.extend(_expand(str(x), variables, out) for x in v)
                else:
                    # Positional vs flag: heuristic — flag if not a bare filename and key matches arg name
                    sv = _expand(str(v), variables, out)
                    if k in ("input", "inputs", "src", "output", "path") and not k.startswith("-"):
                        argv.append(sv)
                    else:
                        argv.append(f"--{k}" if len(k) > 1 else f"-{k}")
                        argv.append(sv)
        else:
            ok = False
            out[sid] = {"rc": 1, "stdout": "", "stderr": f"step '{sid}': need 'argv' or 'args'", "new_files": []}
            if emit_event:
                emit_event("node_error", {"id": sid, "error": "no argv"})
            break

        if emit_event:
            emit_event("node_start", {"id": sid, "tool": tool, "argv": argv})

        # Capture stdout/stderr around the call.
        import contextlib, io, os, traceback
        from _common import ROOT
        ws = ROOT / "web_workspace"
        ws.mkdir(exist_ok=True)
        before = {p.name for p in ws.iterdir() if p.is_file()}
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        cwd_before = os.getcwd()
        try:
            os.chdir(ws)
            with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stderr_buf):
                try:
                    rc = tk.run_category(cat, [cmd] + argv) or 0
                except SystemExit as e:
                    rc = e.code if isinstance(e.code, int) else 1
                except Exception as e:
                    stderr_buf.write(f"{e}\n{traceback.format_exc()}")
                    rc = 1
        finally:
            os.chdir(cwd_before)
        after = {p.name for p in ws.iterdir() if p.is_file()}
        new_files = sorted(after - before)
        step_result = {
            "rc": rc,
            "stdout": stdout_buf.getvalue(),
            "stderr": stderr_buf.getvalue(),
            "new_files": new_files,
            "output": new_files[0] if new_files else "",
        }
        out[sid] = step_result
        if emit_event:
            kind = "node_done" if rc == 0 else "node_error"
            emit_event(kind, {"id": sid, **step_result})
        if rc != 0:
            ok = False
            break

    if emit_event:
        emit_event("recipe_done", {"ok": ok, "results": out})
    return {"ok": ok, "results": out}


# ---------------------------------------------------------------- commands

def cmd_list(args):
    rows = recipe_list()
    if args.json:
        emit({"recipes": rows}, as_json=True)
        return 0
    if not rows:
        print("No recipes saved.")
        return 0
    for r in rows:
        n_steps = len(r.get("steps", []))
        desc = r.get("description", "")
        print(f"  {r['name']:<22s}  {n_steps:>2d} step(s)  {desc}")
    return 0


def cmd_show(args):
    r = recipe_load(args.name)
    if not r:
        print(f"Recipe '{args.name}' not found.")
        return 1
    print(json.dumps(r, indent=2))
    return 0


def cmd_save(args):
    data = json.loads(Path(args.file).read_text(encoding="utf-8"))
    name = args.name or data.get("name") or Path(args.file).stem
    path = recipe_save(name, data)
    print(f"Saved recipe '{name}' -> {path}")
    return 0


def cmd_delete(args):
    ok = recipe_delete(args.name)
    print("Deleted." if ok else "Not found.")
    return 0 if ok else 1


def _parse_vars(pairs: list[str] | None) -> dict:
    vars_dict = {}
    for p in pairs or []:
        if "=" in p:
            k, _, v = p.partition("=")
            vars_dict[k.strip()] = v.strip()
    return vars_dict


def cmd_run(args):
    r = recipe_load(args.name)
    if not r:
        print(f"Recipe '{args.name}' not found.")
        return 1
    problems = validate_recipe(r)
    if problems:
        print(f"Recipe '{args.name}' is invalid:")
        for p in problems:
            print(f"  - {p}")
        return 1
    variables = _parse_vars(args.var)
    result = run_recipe(r, variables, emit_event=_print_event)
    return 0 if result["ok"] else 1


def cmd_exec(args):
    r = json.loads(Path(args.file).read_text(encoding="utf-8"))
    problems = validate_recipe(r)
    if problems:
        print("Recipe is invalid:")
        for p in problems:
            print(f"  - {p}")
        return 1
    variables = _parse_vars(args.var)
    result = run_recipe(r, variables, emit_event=_print_event)
    return 0 if result["ok"] else 1


def _print_event(kind: str, payload: dict):
    if kind == "node_start":
        print(f"\n[run] {payload['id']}: {payload['tool']}  {' '.join(payload.get('argv', []))}")
    elif kind == "node_done":
        files = ", ".join(payload.get("new_files", []))
        print(f"  ✔ ok  ({files})" if files else "  ✔ ok")
    elif kind == "node_error":
        print(f"  ✘ error: {payload.get('error') or payload.get('stderr', '')[:200]}")
    elif kind == "recipe_done":
        print(f"\n[recipe] {'OK' if payload.get('ok') else 'FAILED'}")


def cmd_scaffold(args):
    sample = {
        "name": "example",
        "description": "Resize, then compress.",
        "steps": [
            {"id": "n1", "tool": "image:resize",
             "argv": ["{{input}}", "--width", "1200", "-o", "step1.png"]},
            {"id": "n2", "tool": "image:compress",
             "argv": ["step1.png", "-o", "{{output}}", "--quality", "82"],
             "depends": ["n1"]},
        ],
    }
    print(json.dumps(sample, indent=2))
    return 0


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


# ---------------------------------------------------------------- argparse

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="recipes", description="Multi-step pipeline recipes")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("list", help=COMMANDS["list"])
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_list)

    sp = sub.add_parser("show", help=COMMANDS["show"])
    sp.add_argument("name")
    sp.set_defaults(func=cmd_show)

    sp = sub.add_parser("save", help=COMMANDS["save"])
    sp.add_argument("file", help="recipe JSON file")
    sp.add_argument("--name", help="override the recipe name")
    sp.set_defaults(func=cmd_save)

    sp = sub.add_parser("delete", help=COMMANDS["delete"])
    sp.add_argument("name")
    sp.set_defaults(func=cmd_delete)

    sp = sub.add_parser("run", help=COMMANDS["run"])
    sp.add_argument("name")
    sp.add_argument("--var", action="append", help="key=value, repeatable")
    sp.set_defaults(func=cmd_run)

    sp = sub.add_parser("exec", help=COMMANDS["exec"])
    sp.add_argument("file", help="recipe JSON file")
    sp.add_argument("--var", action="append", help="key=value, repeatable")
    sp.set_defaults(func=cmd_exec)

    sp = sub.add_parser("scaffold", help=COMMANDS["scaffold"])
    sp.set_defaults(func=cmd_scaffold)

    sp = sub.add_parser("validate", help=COMMANDS["validate"])
    sp.add_argument("file", help="recipe JSON file")
    sp.set_defaults(func=cmd_validate)

    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args) or 0


if __name__ == "__main__":
    raise SystemExit(main())
