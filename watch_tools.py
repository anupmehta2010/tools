"""Watch tools: poll a folder for new/changed files and run a tk command on each.

Examples:
    # Compress every new image dropped into ./inbox.
    python tk.py watch run ./inbox --glob "*.jpg" --tool "image-pro:rembg" --arg "{file}" --arg "out/{stem}.png"

    # Auto-OCR every PDF added.
    python tk.py watch run ./scans --glob "*.pdf" --tool "pdf-pro:ocr" --arg "{file}" --arg "-o" --arg "out/{stem}.ocr.pdf"

    # Just list events without doing anything.
    python tk.py watch dry ./inbox --glob "*"
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


COMMANDS = {
    "run": "Watch DIR for new/changed files and run a tk command for each",
    "dry": "Watch DIR and print events without running anything",
}


def _snapshot(root: Path, pattern: str) -> dict[str, float]:
    out = {}
    try:
        for p in root.glob(pattern):
            if p.is_file():
                out[str(p)] = p.stat().st_mtime
    except FileNotFoundError:
        pass
    return out


def _expand(template: str, file: Path) -> str:
    return (template
            .replace("{file}", str(file))
            .replace("{name}", file.name)
            .replace("{stem}", file.stem)
            .replace("{ext}",  file.suffix.lstrip(".")))


def _run_tool(tool: str, args: list[str], file: Path) -> int:
    if ":" not in tool:
        print(f"[watch] tool must be cat:cmd  (got '{tool}')")
        return 1
    cat, _, cmd = tool.partition(":")
    import tk
    final_args = [_expand(a, file) for a in args]
    print(f"  $ tk {cat} {cmd} {' '.join(final_args)}")
    return tk.run_category(cat, [cmd] + final_args)


def cmd_run(args):
    return _watch(args, args.tool, list(args.arg or []))


def cmd_dry(args):
    return _watch(args, None, [])


def _watch(args, tool: str | None, tool_args: list[str]) -> int:
    root = Path(args.dir).resolve()
    if not root.exists():
        print(f"[watch] dir not found: {root}")
        return 1
    pattern = args.glob
    interval = max(0.3, float(args.interval))
    print(f"[watch] {root}  glob={pattern}  interval={interval}s"
          f"{' (dry-run)' if tool is None else ''}")
    seen = _snapshot(root, pattern) if not args.process_existing else {}
    try:
        while True:
            time.sleep(interval)
            now = _snapshot(root, pattern)
            changed = []
            for path, mtime in now.items():
                if seen.get(path) != mtime:
                    changed.append(Path(path))
            seen = now
            for p in changed:
                print(f"[watch] event: {p.name}")
                if tool is None:
                    continue
                rc = _run_tool(tool, tool_args, p)
                if rc != 0 and not args.continue_on_error:
                    print(f"[watch] command failed (rc={rc}); stopping (use --continue-on-error to keep going).")
                    return rc
                if args.once:
                    return 0
    except KeyboardInterrupt:
        print("\n[watch] stopped.")
        return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="watch", description="Folder watcher for tk")
    sub = p.add_subparsers(dest="cmd", required=True)

    common = lambda sp: (
        sp.add_argument("dir", help="directory to watch"),
        sp.add_argument("--glob", default="*", help="glob pattern (default '*')"),
        sp.add_argument("--interval", type=float, default=1.0, help="poll interval seconds"),
        sp.add_argument("--process-existing", action="store_true",
                        help="also fire for files that exist when watch starts"),
        sp.add_argument("--once", action="store_true",
                        help="exit after the first event is processed"),
        sp.add_argument("--continue-on-error", action="store_true",
                        help="don't stop the loop when a tool returns non-zero"),
    )

    sp = sub.add_parser("run", help=COMMANDS["run"])
    common(sp)
    sp.add_argument("--tool", required=True,
                    help="tk tool to invoke as 'cat:cmd' (e.g. image-pro:rembg)")
    sp.add_argument("--arg", action="append",
                    help="argument to pass; can repeat; placeholders: {file} {name} {stem} {ext}")
    sp.set_defaults(func=cmd_run)

    sp = sub.add_parser("dry", help=COMMANDS["dry"])
    common(sp)
    sp.set_defaults(func=cmd_dry)

    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args) or 0


if __name__ == "__main__":
    raise SystemExit(main())
