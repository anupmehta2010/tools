"""Code utilities: format, secrets-scan, sloc, complexity, deps, license-scan, todo-find."""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from _common import lazy_import


# ---- Format ----

_FORMATTERS = {
    ".py":  ("black",    ["{file}"]),
    ".js":  ("prettier", ["--write", "{file}"]),
    ".jsx": ("prettier", ["--write", "{file}"]),
    ".ts":  ("prettier", ["--write", "{file}"]),
    ".tsx": ("prettier", ["--write", "{file}"]),
    ".css": ("prettier", ["--write", "{file}"]),
    ".html":("prettier", ["--write", "{file}"]),
    ".json":("prettier", ["--write", "{file}"]),
    ".md":  ("prettier", ["--write", "{file}"]),
    ".go":  ("gofmt",    ["-w", "{file}"]),
    ".rs":  ("rustfmt",  ["{file}"]),
}


def cmd_format(args):
    """Auto-format file by extension."""
    path = Path(args.input)
    ext = path.suffix.lower()
    if ext not in _FORMATTERS:
        print(f"[!] No formatter mapped for {ext}")
        return 1
    binary, template = _FORMATTERS[ext]
    if not shutil.which(binary):
        print(f"[!] '{binary}' not on PATH. Install it first.")
        return 2
    cmd = [binary] + [t.format(file=str(path)) for t in template]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        print(f"[!] {binary} failed:\n{proc.stderr}")
        return proc.returncode
    print(f"Formatted {path}")


# ---- Secrets scan ----

_SECRET_PATTERNS = [
    ("AWS access key",     re.compile(r"AKIA[0-9A-Z]{16}")),
    ("AWS secret key",     re.compile(r"(?i)aws[_\- ]?secret[_\- ]?(access)?[_\- ]?key[\"'\s:=]+([A-Za-z0-9/+=]{40})")),
    ("GitHub PAT",         re.compile(r"ghp_[A-Za-z0-9]{36}")),
    ("GitHub OAuth",       re.compile(r"gho_[A-Za-z0-9]{36}")),
    ("GitHub app",         re.compile(r"(ghu|ghs|ghr)_[A-Za-z0-9]{36}")),
    ("JWT",                re.compile(r"eyJ[A-Za-z0-9_\-]+\.eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+")),
    ("OpenAI key",         re.compile(r"sk-[A-Za-z0-9]{20,}")),
    ("Slack token",        re.compile(r"xox[abprs]-[A-Za-z0-9\-]{10,}")),
    ("Google API key",     re.compile(r"AIza[0-9A-Za-z_\-]{35}")),
    ("Generic api_key",    re.compile(r"(?i)(api[_\-]?key|apikey)[\"'\s:=]+([A-Za-z0-9_\-]{16,})")),
    ("Password literal",   re.compile(r"(?i)password[\"'\s:=]+([A-Za-z0-9!@#\$%\^&\*_\-]{6,})")),
    ("PEM block",          re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
]

_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".idea", ".vscode"}


def _iter_files(root: Path):
    if root.is_file():
        yield root
        return
    for p in root.rglob("*"):
        if p.is_file() and not any(part in _SKIP_DIRS for part in p.parts):
            yield p


def _redact(s: str) -> str:
    if len(s) <= 8:
        return "*" * len(s)
    return s[:4] + "*" * (len(s) - 8) + s[-4:]


def cmd_secrets_scan(args):
    """Scan file or dir for common secret patterns."""
    root = Path(args.path)
    if not root.exists():
        print(f"[!] Not found: {root}")
        return 1
    hits = 0
    for fp in _iter_files(root):
        try:
            text = fp.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for label, pat in _SECRET_PATTERNS:
                m = pat.search(line)
                if m:
                    sample = m.group(0)
                    print(f"{fp}:{lineno}: [{label}] {_redact(sample)}")
                    hits += 1
    print(f"\n[{hits} potential secret(s) found]")
    return 0 if hits == 0 else 1


# ---- SLOC ----

_LANG_EXTS = {
    ".py": "Python", ".js": "JavaScript", ".jsx": "JavaScript", ".ts": "TypeScript",
    ".tsx": "TypeScript", ".go": "Go", ".rs": "Rust", ".java": "Java", ".c": "C",
    ".h": "C/C++ header", ".cpp": "C++", ".cc": "C++", ".cs": "C#", ".rb": "Ruby",
    ".php": "PHP", ".sh": "Shell", ".html": "HTML", ".css": "CSS", ".md": "Markdown",
    ".json": "JSON", ".yaml": "YAML", ".yml": "YAML", ".toml": "TOML", ".sql": "SQL",
    ".lua": "Lua", ".swift": "Swift", ".kt": "Kotlin", ".vue": "Vue", ".svelte": "Svelte",
}


def cmd_sloc(args):
    """Count source lines per language."""
    root = Path(args.path)
    counts: dict[str, list[int]] = {}
    for fp in _iter_files(root):
        lang = _LANG_EXTS.get(fp.suffix.lower())
        if not lang:
            continue
        try:
            lines = fp.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        files, total, code = counts.setdefault(lang, [0, 0, 0])
        non_empty = sum(1 for ln in lines if ln.strip())
        counts[lang] = [files + 1, total + len(lines), code + non_empty]
    if not counts:
        print("(no recognized source files)")
        return
    print(f"{'Language':<16}{'Files':>8}{'Lines':>10}{'Code':>10}")
    print("-" * 44)
    total_files = total_lines = total_code = 0
    for lang in sorted(counts, key=lambda k: -counts[k][2]):
        f, t, c = counts[lang]
        print(f"{lang:<16}{f:>8}{t:>10}{c:>10}")
        total_files += f; total_lines += t; total_code += c
    print("-" * 44)
    print(f"{'TOTAL':<16}{total_files:>8}{total_lines:>10}{total_code:>10}")


# ---- Complexity ----

def cmd_complexity(args):
    """Cyclomatic complexity via radon."""
    radon = lazy_import("radon.complexity", "pip install radon")
    root = Path(args.path)
    for fp in _iter_files(root):
        if fp.suffix.lower() != ".py":
            continue
        try:
            src = fp.read_text(encoding="utf-8", errors="replace")
            blocks = radon.cc_visit(src)
        except Exception:
            continue
        for b in blocks:
            if b.complexity >= args.min:
                print(f"{fp}:{b.lineno}: {b.name} (complexity={b.complexity}, rank={radon.cc_rank(b.complexity)})")


# ---- Deps ----

def cmd_deps(args):
    """Parse requirements.txt / package.json / pyproject.toml into unified JSON."""
    root = Path(args.path)
    result: dict[str, dict] = {}
    req = root / "requirements.txt"
    if req.exists():
        py = {}
        for line in req.read_text(encoding="utf-8").splitlines():
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            m = re.match(r"^([A-Za-z0-9_\-\.]+)\s*([<>=!~]=?.*)?$", line)
            if m:
                py[m.group(1)] = (m.group(2) or "").strip() or "*"
        result["python_requirements"] = py
    pkg = root / "package.json"
    if pkg.exists():
        data = json.loads(pkg.read_text(encoding="utf-8"))
        result["npm"] = {
            "dependencies":    data.get("dependencies", {}),
            "devDependencies": data.get("devDependencies", {}),
        }
    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        try:
            try:
                import tomllib as _tl
            except ImportError:
                _tl = lazy_import("tomli", "pip install tomli")
            with pyproject.open("rb") as f:
                data = _tl.load(f)
            proj = data.get("project", {})
            result["pyproject"] = {
                "name":         proj.get("name"),
                "version":      proj.get("version"),
                "dependencies": proj.get("dependencies", []),
                "optional":     proj.get("optional-dependencies", {}),
            }
        except Exception as e:
            result["pyproject_error"] = str(e)
    out = json.dumps(result, indent=2)
    if args.output:
        Path(args.output).write_text(out, encoding="utf-8")
        print(f"Wrote {args.output}")
    else:
        print(out)


# ---- License scan ----

_LICENSE_FINGERPRINTS = [
    ("MIT",          re.compile(r"MIT License|Permission is hereby granted, free of charge", re.I)),
    ("Apache-2.0",   re.compile(r"Apache License,?\s*Version 2\.0", re.I)),
    ("BSD-3-Clause", re.compile(r"BSD 3-Clause|Redistribution and use.*neither the name", re.I | re.S)),
    ("BSD-2-Clause", re.compile(r"BSD 2-Clause", re.I)),
    ("GPL-3.0",      re.compile(r"GNU GENERAL PUBLIC LICENSE\s+Version 3", re.I)),
    ("GPL-2.0",      re.compile(r"GNU GENERAL PUBLIC LICENSE\s+Version 2", re.I)),
    ("LGPL-3.0",     re.compile(r"GNU LESSER GENERAL PUBLIC LICENSE\s+Version 3", re.I)),
    ("AGPL-3.0",     re.compile(r"GNU AFFERO GENERAL PUBLIC LICENSE\s+Version 3", re.I)),
    ("MPL-2.0",      re.compile(r"Mozilla Public License Version 2\.0", re.I)),
    ("ISC",          re.compile(r"ISC License", re.I)),
    ("Unlicense",    re.compile(r"This is free and unencumbered software released into the public domain", re.I)),
]


def cmd_license_scan(args):
    """Detect SPDX license from LICENSE file."""
    root = Path(args.path)
    candidates = []
    if root.is_file():
        candidates = [root]
    else:
        for name in ("LICENSE", "LICENSE.txt", "LICENSE.md", "COPYING", "COPYING.txt"):
            p = root / name
            if p.exists():
                candidates.append(p)
    if not candidates:
        print("(no LICENSE file found)")
        return 1
    for lic in candidates:
        text = lic.read_text(encoding="utf-8", errors="replace")
        for spdx, pat in _LICENSE_FINGERPRINTS:
            if pat.search(text):
                print(f"{lic}: {spdx}")
                break
        else:
            print(f"{lic}: UNKNOWN")


# ---- TODO find ----

_TODO_PAT = re.compile(r"\b(TODO|FIXME|XXX|HACK|BUG|NOTE)\b[:\s]?(.*)", re.I)


def cmd_todo_find(args):
    """Grep TODO/FIXME/XXX/HACK across dir."""
    root = Path(args.path)
    hits = 0
    for fp in _iter_files(root):
        if fp.suffix.lower() not in _LANG_EXTS:
            continue
        try:
            for lineno, line in enumerate(fp.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                m = _TODO_PAT.search(line)
                if m:
                    text = m.group(2).strip()[:80]
                    print(f"{fp}:{lineno}: [{m.group(1).upper()}] {text}")
                    hits += 1
        except OSError:
            continue
    print(f"\n[{hits} marker(s)]")


# ---- COMMANDS dict ----
COMMANDS = {
    "format":       "auto-format file by extension",
    "secrets-scan": "scan for AWS/GH/JWT/OpenAI/Slack/PEM secrets",
    "sloc":         "count source lines per language",
    "complexity":   "cyclomatic complexity (radon)",
    "deps":         "unify Python/Node dependency manifests to JSON",
    "license-scan": "detect SPDX license from LICENSE file",
    "todo-find":    "list TODO/FIXME/XXX/HACK across a dir",
}


def build_parser(parser=None):
    parser = parser or argparse.ArgumentParser(prog="code_tools", description="Code utilities")
    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("format", help=COMMANDS["format"])
    p.add_argument("input")
    p.set_defaults(func=cmd_format)

    p = sub.add_parser("secrets-scan", help=COMMANDS["secrets-scan"])
    p.add_argument("path", nargs="?", default=".")
    p.set_defaults(func=cmd_secrets_scan)

    p = sub.add_parser("sloc", help=COMMANDS["sloc"])
    p.add_argument("path", nargs="?", default=".")
    p.set_defaults(func=cmd_sloc)

    p = sub.add_parser("complexity", help=COMMANDS["complexity"])
    p.add_argument("path", nargs="?", default=".")
    p.add_argument("--min", type=int, default=5, help="minimum complexity to show")
    p.set_defaults(func=cmd_complexity)

    p = sub.add_parser("deps", help=COMMANDS["deps"])
    p.add_argument("path", nargs="?", default=".")
    p.add_argument("-o", "--output")
    p.set_defaults(func=cmd_deps)

    p = sub.add_parser("license-scan", help=COMMANDS["license-scan"])
    p.add_argument("path", nargs="?", default=".")
    p.set_defaults(func=cmd_license_scan)

    p = sub.add_parser("todo-find", help=COMMANDS["todo-find"])
    p.add_argument("path", nargs="?", default=".")
    p.set_defaults(func=cmd_todo_find)

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
