"""Bundle: ship the whole tk toolkit as a single self-contained artifact.

Modes:
    tk bundle zipapp -o tk.pyz           # single-file Python zipapp (run with `python tk.pyz`)
    tk bundle zip    -o tk.zip           # plain portable zip of the project
    tk bundle pyinstaller -o dist/       # single native binary (requires PyInstaller)

zipapp produces a single .pyz file containing every module, the web UI,
plugins, and recipes. `python tk.pyz` works on any machine with Python 3.10+
— no install required. Web UI also works because web/* is bundled inside the zip
and the server serves it via importlib.resources.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import sys as _sys
import tempfile
import zipapp
import zipfile
from pathlib import Path
from pathlib import Path as _Path

_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))
from _common import tool_main

ROOT = Path(__file__).resolve().parent.parent


COMMANDS = {
    "zipapp":      "Build a single-file Python zipapp (.pyz)",
    "zip":         "Build a portable .zip of the whole project",
    "pyinstaller": "Build a native binary with PyInstaller (needs `pip install pyinstaller`)",
    "info":        "Report bundle sizes and what would be included",
}


def _project_files() -> list[Path]:
    """Every file that should ship in a bundle."""
    skips = {"__pycache__", ".git", ".github", "dist", "build", "node_modules", ".venv", "venv"}
    skip_files = {"history.db"}
    out: list[Path] = []
    for p in ROOT.rglob("*"):
        if any(part in skips for part in p.relative_to(ROOT).parts):
            continue
        if not p.is_file():
            continue
        if p.name in skip_files:
            continue
        # Skip the workspace dir's user files (keep only .gitkeep).
        rel = p.relative_to(ROOT)
        if rel.parts and rel.parts[0] == "web_workspace" and p.name != ".gitkeep":
            continue
        if rel.parts and rel.parts[0] == "tests":
            continue
        out.append(p)
    return out


def cmd_info(args):
    files = _project_files()
    total = sum(f.stat().st_size for f in files)
    by_ext: dict[str, int] = {}
    for f in files:
        by_ext[f.suffix] = by_ext.get(f.suffix, 0) + f.stat().st_size
    print(f"Bundle contents: {len(files)} files, {total/1024:.1f} KB total")
    for ext, sz in sorted(by_ext.items(), key=lambda x: -x[1]):
        print(f"  {ext or '(noext)':<10s}  {sz/1024:>8.1f} KB")
    return 0


# ---------------------------------------------------------------- zipapp (.pyz)

ENTRY_TEMPLATE = """\
# Auto-generated entry point for the tk zipapp.
import sys
from pathlib import Path

# Inside a .pyz, __file__ is the archive; sys.path already includes it.
# Add it explicitly so subprocess-launched children see the modules too.
ZIP = Path(__file__).resolve().parent
if str(ZIP) not in sys.path:
    sys.path.insert(0, str(ZIP))

import tk
raise SystemExit(tk.main(sys.argv[1:]))
"""


def cmd_zipapp(args):
    out = Path(args.output).resolve()
    if out.is_dir():
        out = out / "tk.pyz"
    out.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "src"
        src.mkdir()
        for f in _project_files():
            rel = f.relative_to(ROOT)
            dst = src / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dst)
        (src / "__main__.py").write_text(ENTRY_TEMPLATE, encoding="utf-8")
        zipapp.create_archive(
            src, target=str(out),
            interpreter="/usr/bin/env python3",
            compressed=True,
        )

    size = out.stat().st_size
    print(f"Built {out}  ({size/1024:.1f} KB)")
    print(f"Run with:  python {out.name}")
    return 0


# ---------------------------------------------------------------- portable zip

def cmd_zip(args):
    out = Path(args.output).resolve()
    if out.is_dir():
        out = out / "tk-portable.zip"
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for f in _project_files():
            arc = f.relative_to(ROOT)
            zf.write(f, arc.as_posix())
    print(f"Built {out}  ({out.stat().st_size/1024:.1f} KB)")
    return 0


# ---------------------------------------------------------------- pyinstaller

def cmd_pyinstaller(args):
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("PyInstaller not installed. Install with:  pip install pyinstaller")
        return 2

    out_dir = Path(args.output).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    # Build a one-file binary; bundle web/ as a data folder.
    sep = ";" if sys.platform.startswith("win") else ":"
    add_data = [f"web{sep}web"]
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean",
        "--onefile",
        "--name", "tk",
        "--distpath", str(out_dir),
        "--workpath", str(out_dir / "_build"),
        "--specpath", str(out_dir / "_spec"),
        *sum((["--add-data", d] for d in add_data), []),
        # Hidden imports — every tool module so they're not stripped.
        *sum((["--hidden-import", m] for m in _hidden_imports()), []),
        str(ROOT / "tk.py"),
    ]
    print("Running PyInstaller:", " ".join(cmd))
    rc = subprocess.run(cmd, check=False).returncode
    if rc == 0:
        bin_name = "tk.exe" if sys.platform.startswith("win") else "tk"
        print(f"\nBuilt {out_dir / bin_name}")
    return rc


def _hidden_imports() -> list[str]:
    """Modules PyInstaller might miss because they're dynamically imported."""
    import tk
    return [m for m, _, _ in tk.CATEGORIES.values()]


# ---------------------------------------------------------------- argparse

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="bundle", description="Ship tk as one artifact")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("zipapp", help=COMMANDS["zipapp"])
    sp.add_argument("-o", "--output", default="tk.pyz")
    sp.set_defaults(func=cmd_zipapp)

    sp = sub.add_parser("zip", help=COMMANDS["zip"])
    sp.add_argument("-o", "--output", default="tk-portable.zip")
    sp.set_defaults(func=cmd_zip)

    sp = sub.add_parser("pyinstaller", help=COMMANDS["pyinstaller"])
    sp.add_argument("-o", "--output", default="dist")
    sp.set_defaults(func=cmd_pyinstaller)

    sp = sub.add_parser("info", help=COMMANDS["info"])
    sp.set_defaults(func=cmd_info)

    return p


@tool_main("bundle")
def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args) or 0


if __name__ == "__main__":
    raise SystemExit(main())
