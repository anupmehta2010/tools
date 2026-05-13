"""Filesystem tools: bulk rename, dedupe, search, disk usage, sysinfo, tree, count."""
from __future__ import annotations

import argparse
import hashlib
import os
import platform
import re
import shutil
from collections import defaultdict
from pathlib import Path

from _common import human_size


def _walk(root, follow_symlinks=False):
    for dirpath, dirnames, filenames in os.walk(root, followlinks=follow_symlinks):
        for name in filenames:
            yield Path(dirpath) / name


# ---- Bulk rename ----

def cmd_rename(args):
    pat = re.compile(args.pattern)
    repl = args.replacement
    base = Path(args.dir)
    if args.glob:
        candidates = list(base.glob(args.glob))
    elif args.recursive:
        candidates = list(_walk(base))
    else:
        candidates = [p for p in base.iterdir()] if base.is_dir() else []
    plan = []
    for p in candidates:
        if not p.is_file():
            continue
        new_name = pat.sub(repl, p.name)
        if new_name != p.name:
            plan.append((p, p.with_name(new_name)))
    print(f"{len(plan)} file(s) would be renamed.")
    for src, dst in plan[:20]:
        print(f"  {src.name}  ->  {dst.name}")
    if len(plan) > 20:
        print(f"  ... and {len(plan) - 20} more")
    if not plan:
        return
    if not args.execute:
        print("\nDry run. Pass --execute to apply.")
        return
    done = 0
    for src, dst in plan:
        if dst.exists():
            print(f"  skip (exists): {dst}")
            continue
        src.rename(dst)
        done += 1
    print(f"Renamed {done} file(s).")


# ---- Dedupe ----

def cmd_dedupe(args):
    by_size: dict[int, list[Path]] = defaultdict(list)
    for p in _walk(args.dir):
        if p.is_file():
            try:
                by_size[p.stat().st_size].append(p)
            except OSError:
                pass
    by_hash: dict[str, list[Path]] = defaultdict(list)
    for size, files in by_size.items():
        if len(files) < 2:
            continue
        for p in files:
            try:
                h = hashlib.sha256()
                with open(p, "rb") as f:
                    for chunk in iter(lambda: f.read(8192), b""):
                        h.update(chunk)
                by_hash[h.hexdigest()].append(p)
            except OSError:
                pass
    groups = [(d, paths) for d, paths in by_hash.items() if len(paths) > 1]
    if not groups:
        print("No duplicates found.")
        return
    total_wasted = 0
    for digest, paths in groups:
        size = paths[0].stat().st_size
        wasted = size * (len(paths) - 1)
        total_wasted += wasted
        print(f"\n{digest[:12]}  ({len(paths)} copies, {human_size(size)} each, wastes {human_size(wasted)})")
        for p in paths:
            print(f"  {p}")
    print(f"\nTotal wasted: {human_size(total_wasted)}")


# ---- Search ----

def cmd_search(args):
    pat = re.compile(args.pattern, re.IGNORECASE if args.ignore_case else 0)
    matches = 0
    for p in _walk(args.dir):
        if not p.is_file():
            continue
        if args.content:
            try:
                with open(p, "r", encoding="utf-8", errors="ignore") as f:
                    for ln_no, line in enumerate(f, 1):
                        if pat.search(line):
                            print(f"{p}:{ln_no}: {line.rstrip()}")
                            matches += 1
                            if args.limit and matches >= args.limit:
                                return
            except OSError:
                pass
        else:
            if pat.search(p.name):
                print(p)
                matches += 1
                if args.limit and matches >= args.limit:
                    return
    if matches == 0:
        print("(no matches)")


# ---- Disk usage ----

def cmd_disk(args):
    root = Path(args.dir)
    if not root.is_dir():
        print(f"Not a directory: {root}")
        return 1
    sizes: dict[Path, int] = {}
    for p in root.iterdir():
        if p.is_dir():
            total = 0
            try:
                for f in _walk(p):
                    if f.is_file():
                        try:
                            total += f.stat().st_size
                        except OSError:
                            pass
            except OSError:
                pass
            sizes[p] = total
        elif p.is_file():
            try:
                sizes[p] = p.stat().st_size
            except OSError:
                pass
    items = sorted(sizes.items(), key=lambda kv: kv[1], reverse=True)
    print(f"{'Size':>10}  Path")
    print("-" * 60)
    for path, size in items[: args.limit]:
        suffix = "/" if path.is_dir() else ""
        print(f"{human_size(size):>10}  {path.name}{suffix}")
    print(f"\nTotal: {human_size(sum(sizes.values()))}")


# ---- Sysinfo ----

def cmd_sysinfo(args):
    print(f"System:    {platform.system()} {platform.release()}")
    print(f"Version:   {platform.version()}")
    print(f"Machine:   {platform.machine()}")
    print(f"Processor: {platform.processor()}")
    print(f"Python:    {platform.python_version()}")
    print(f"Hostname:  {platform.node()}")
    if hasattr(os, "cpu_count"):
        print(f"CPU count: {os.cpu_count()}")
    try:
        usage = shutil.disk_usage(".")
        print(f"Disk (cwd): {human_size(usage.used)} used / {human_size(usage.total)} total"
              f"  ({100 * usage.used / usage.total:.1f}%)")
    except Exception:
        pass


# ---- Tree ----

def cmd_tree(args):
    root = Path(args.dir)

    def walk(p, depth, prefix=""):
        if depth > args.depth:
            return
        try:
            entries = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))
        except (PermissionError, OSError):
            return
        for i, entry in enumerate(entries):
            is_last = i == len(entries) - 1
            connector = "+-- " if is_last else "|-- "
            suffix = "/" if entry.is_dir() else ""
            print(prefix + connector + entry.name + suffix)
            if entry.is_dir() and not entry.is_symlink():
                ext = "    " if is_last else "|   "
                walk(entry, depth + 1, prefix + ext)

    print(root.name + "/")
    if root.is_dir():
        walk(root, 1)


# ---- Count ----

def cmd_count(args):
    files = 0
    dirs = 0
    size = 0
    for p in Path(args.dir).rglob("*"):
        try:
            if p.is_file():
                files += 1
                size += p.stat().st_size
            elif p.is_dir():
                dirs += 1
        except OSError:
            pass
    print(f"Files: {files:,}")
    print(f"Dirs:  {dirs:,}")
    print(f"Size:  {human_size(size)}")


# ---- Empty cleanup (preview) ----

def cmd_copy(args):
    """Copy a file or directory recursively, with progress."""
    src, dst = Path(args.src), Path(args.dst)
    if src.is_file():
        shutil.copy2(src, dst)
        print(f"copied {src} -> {dst}  ({human_size(dst.stat().st_size)})")
        return
    if src.is_dir():
        files = [p for p in src.rglob("*") if p.is_file()]
        for i, p in enumerate(files, 1):
            rel = p.relative_to(src)
            target = dst / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, target)
            if i % 50 == 0 or i == len(files):
                print(f"  {i}/{len(files)}", end="\r", flush=True)
        print(f"\nCopied {len(files)} file(s) from {src}/ to {dst}/")
        return
    print(f"Not found: {src}")
    return 1


def cmd_size_by_ext(args):
    """Group files in a tree by extension and report total size."""
    by_ext: dict[str, tuple[int, int]] = {}
    for p in _walk(args.dir):
        if not p.is_file():
            continue
        try:
            sz = p.stat().st_size
        except OSError:
            continue
        ext = p.suffix.lower() or "(none)"
        cnt, total = by_ext.get(ext, (0, 0))
        by_ext[ext] = (cnt + 1, total + sz)
    rows = sorted(by_ext.items(), key=lambda kv: kv[1][1], reverse=True)
    print(f"{'Ext':<14} {'Count':>8}  {'Size':>10}")
    print("-" * 38)
    grand_count = grand_size = 0
    for ext, (cnt, sz) in rows[: args.limit]:
        print(f"{ext:<14} {cnt:>8}  {human_size(sz):>10}")
        grand_count += cnt; grand_size += sz
    print("-" * 38)
    print(f"{'Total':<14} {grand_count:>8}  {human_size(grand_size):>10}")


def cmd_compare_dirs(args):
    """Show files only-in-A, only-in-B, and changed."""
    a_root, b_root = Path(args.a), Path(args.b)
    a_files = {p.relative_to(a_root): p for p in _walk(a_root) if p.is_file()}
    b_files = {p.relative_to(b_root): p for p in _walk(b_root) if p.is_file()}
    only_a = sorted(set(a_files) - set(b_files))
    only_b = sorted(set(b_files) - set(a_files))
    changed = []
    for rel in sorted(set(a_files) & set(b_files)):
        if a_files[rel].stat().st_size != b_files[rel].stat().st_size:
            changed.append(rel)
    print(f"only in {a_root}/  ({len(only_a)}):")
    for p in only_a[:50]: print(f"  {p}")
    if len(only_a) > 50: print(f"  ... +{len(only_a) - 50} more")
    print(f"\nonly in {b_root}/  ({len(only_b)}):")
    for p in only_b[:50]: print(f"  {p}")
    if len(only_b) > 50: print(f"  ... +{len(only_b) - 50} more")
    print(f"\nsize differs ({len(changed)}):")
    for p in changed[:50]: print(f"  {p}")


def cmd_empty_dirs(args):
    """List (and optionally remove) empty directories."""
    root = Path(args.dir)
    empties: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root, topdown=False):
        d = Path(dirpath)
        if not any(d.iterdir()):
            empties.append(d)
    if not empties:
        print("No empty directories.")
        return
    for d in empties:
        print(d)
    print(f"\n{len(empties)} empty director{'y' if len(empties) == 1 else 'ies'} found.")
    if not args.execute:
        print("Dry run. Pass --execute to remove.")
        return
    for d in empties:
        try:
            d.rmdir()
        except OSError as e:
            print(f"  cannot remove {d}: {e}")
    print("Done.")


COMMANDS = {
    "rename":     "bulk rename via regex (dry-run by default)",
    "dedupe":     "find duplicate files by sha256",
    "search":     "search files by name or content (regex)",
    "disk":       "disk usage of children",
    "sysinfo":    "system information",
    "tree":       "directory tree (limited depth)",
    "count":      "count files/dirs/size",
    "empty-dirs": "list (and optionally remove) empty directories",
    "copy":       "recursive copy with progress",
    "size-by-ext": "summarize disk usage grouped by file extension",
    "compare-dirs": "diff two directories (only-in-A, only-in-B, changed)",
}


def build_parser(parser=None):
    parser = parser or argparse.ArgumentParser(prog="fs_tools", description="Filesystem utilities")
    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("rename", help=COMMANDS["rename"])
    p.add_argument("dir")
    p.add_argument("pattern")
    p.add_argument("replacement")
    p.add_argument("--glob")
    p.add_argument("--recursive", action="store_true")
    p.add_argument("--execute", action="store_true")
    p.set_defaults(func=cmd_rename)

    p = sub.add_parser("dedupe", help=COMMANDS["dedupe"])
    p.add_argument("dir")
    p.set_defaults(func=cmd_dedupe)

    p = sub.add_parser("search", help=COMMANDS["search"])
    p.add_argument("dir"); p.add_argument("pattern")
    p.add_argument("--content", action="store_true")
    p.add_argument("--ignore-case", action="store_true")
    p.add_argument("--limit", type=int, default=0)
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("disk", help=COMMANDS["disk"])
    p.add_argument("dir")
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(func=cmd_disk)

    p = sub.add_parser("sysinfo", help=COMMANDS["sysinfo"])
    p.set_defaults(func=cmd_sysinfo)

    p = sub.add_parser("tree", help=COMMANDS["tree"])
    p.add_argument("dir", nargs="?", default=".")
    p.add_argument("--depth", type=int, default=3)
    p.set_defaults(func=cmd_tree)

    p = sub.add_parser("count", help=COMMANDS["count"])
    p.add_argument("dir", nargs="?", default=".")
    p.set_defaults(func=cmd_count)

    p = sub.add_parser("empty-dirs", help=COMMANDS["empty-dirs"])
    p.add_argument("dir")
    p.add_argument("--execute", action="store_true")
    p.set_defaults(func=cmd_empty_dirs)

    p = sub.add_parser("copy", help=COMMANDS["copy"])
    p.add_argument("src"); p.add_argument("dst")
    p.set_defaults(func=cmd_copy)

    p = sub.add_parser("size-by-ext", help=COMMANDS["size-by-ext"])
    p.add_argument("dir")
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(func=cmd_size_by_ext)

    p = sub.add_parser("compare-dirs", help=COMMANDS["compare-dirs"])
    p.add_argument("a"); p.add_argument("b")
    p.set_defaults(func=cmd_compare_dirs)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 1
    return args.func(args) or 0


if __name__ == "__main__":
    raise SystemExit(main())
