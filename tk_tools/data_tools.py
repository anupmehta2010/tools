"""Data conversion: CSV/JSON/Excel/YAML/XML/TOML and a CSV viewer."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import re
from _common import lazy_import


def _read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def _write_csv(path, rows):
    if not rows:
        Path(path).write_text("", encoding="utf-8")
        return
    keys = list(rows[0].keys()) if isinstance(rows[0], dict) else None
    with open(path, "w", newline="", encoding="utf-8") as f:
        if keys:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            w.writerows(rows)
        else:
            w = csv.writer(f)
            for r in rows:
                w.writerow(r)


# ---- CSV / JSON ----

def cmd_csv2json(args):
    rows = _read_csv(args.input)
    Path(args.output).write_text(
        json.dumps(rows, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"{len(rows)} rows -> {args.output}")


def cmd_json2csv(args):
    data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        print("JSON must be a list of objects (or a single object).")
        return 1
    _write_csv(args.output, data)
    print(f"{len(data)} rows -> {args.output}")


# ---- Excel ----

def cmd_csv2xlsx(args):
    openpyxl = lazy_import("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    with open(args.input, newline="", encoding="utf-8") as f:
        for row in csv.reader(f):
            ws.append(row)
    wb.save(args.output)
    print(f"Wrote {args.output}")


def cmd_xlsx2csv(args):
    openpyxl = lazy_import("openpyxl")
    wb = openpyxl.load_workbook(args.input, data_only=True)
    ws = wb[args.sheet] if args.sheet else wb.active
    with open(args.output, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        for row in ws.iter_rows(values_only=True):
            w.writerow(["" if v is None else v for v in row])
    print(f"Wrote {args.output}")


def cmd_xlsx2json(args):
    openpyxl = lazy_import("openpyxl")
    wb = openpyxl.load_workbook(args.input, data_only=True)
    out = {}
    for ws in wb.worksheets:
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            out[ws.title] = []
            continue
        headers = list(rows[0])
        data = [dict(zip(headers, r)) for r in rows[1:]]
        out[ws.title] = data
    Path(args.output).write_text(
        json.dumps(out, indent=2, default=str, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Wrote {args.output}")


def cmd_json2xlsx(args):
    openpyxl = lazy_import("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = [data]
    if data and isinstance(data[0], dict):
        headers = list(data[0].keys())
        ws.append(headers)
        for row in data:
            ws.append([row.get(h, "") for h in headers])
    else:
        for row in data:
            ws.append(row if isinstance(row, list) else [row])
    wb.save(args.output)
    print(f"Wrote {args.output}")


# ---- YAML / TOML / XML ----

def cmd_yaml2json(args):
    yaml = lazy_import("yaml", install_hint="pip install pyyaml")
    data = yaml.safe_load(Path(args.input).read_text(encoding="utf-8"))
    Path(args.output).write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Wrote {args.output}")


def cmd_json2yaml(args):
    yaml = lazy_import("yaml", install_hint="pip install pyyaml")
    data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    Path(args.output).write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    print(f"Wrote {args.output}")


def cmd_xml2json(args):
    import xml.etree.ElementTree as ET

    def elem_to(elem):
        d = {}
        if elem.attrib:
            d["@attrs"] = dict(elem.attrib)
        children = list(elem)
        if children:
            children_dict = {}
            for child in children:
                cd = elem_to(child)
                if child.tag in children_dict:
                    if not isinstance(children_dict[child.tag], list):
                        children_dict[child.tag] = [children_dict[child.tag]]
                    children_dict[child.tag].append(cd)
                else:
                    children_dict[child.tag] = cd
            d.update(children_dict)
        elif elem.text and elem.text.strip():
            return elem.text.strip() if not d else dict(d, **{"#text": elem.text.strip()})
        return d

    tree = ET.parse(args.input)
    root = tree.getroot()
    out = {root.tag: elem_to(root)}
    Path(args.output).write_text(
        json.dumps(out, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Wrote {args.output}")


def cmd_toml2json(args):
    try:
        import tomllib  # Python 3.11+
    except ImportError:
        tomllib = lazy_import("tomli", install_hint="pip install tomli (or upgrade Python)")
    with open(args.input, "rb") as f:
        data = tomllib.load(f)
    Path(args.output).write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Wrote {args.output}")


# ---- View ----

def _deep_merge(a, b):
    if isinstance(a, dict) and isinstance(b, dict):
        out = dict(a)
        for k, v in b.items():
            out[k] = _deep_merge(a.get(k), v) if k in a else v
        return out
    if isinstance(a, list) and isinstance(b, list):
        return a + b
    return b


def cmd_json_merge(args):
    merged = None
    for path in args.inputs:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        merged = d if merged is None else _deep_merge(merged, d)
    text = json.dumps(merged, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"Merged {len(args.inputs)} -> {args.output}")
    else:
        print(text)


def _json_diff(a, b, path=""):
    diffs = []
    if type(a) is not type(b):
        diffs.append(f"~ {path or '<root>'}: {a!r}  ->  {b!r}")
        return diffs
    if isinstance(a, dict):
        keys = set(a) | set(b)
        for k in sorted(keys):
            sub = f"{path}.{k}" if path else k
            if k not in a:
                diffs.append(f"+ {sub}: {b[k]!r}")
            elif k not in b:
                diffs.append(f"- {sub}: {a[k]!r}")
            else:
                diffs.extend(_json_diff(a[k], b[k], sub))
    elif isinstance(a, list):
        n = max(len(a), len(b))
        for i in range(n):
            sub = f"{path}[{i}]"
            if i >= len(a):
                diffs.append(f"+ {sub}: {b[i]!r}")
            elif i >= len(b):
                diffs.append(f"- {sub}: {a[i]!r}")
            else:
                diffs.extend(_json_diff(a[i], b[i], sub))
    elif a != b:
        diffs.append(f"~ {path or '<root>'}: {a!r}  ->  {b!r}")
    return diffs


def cmd_json_diff(args):
    a = json.loads(Path(args.a).read_text(encoding="utf-8"))
    b = json.loads(Path(args.b).read_text(encoding="utf-8"))
    diffs = _json_diff(a, b)
    if not diffs:
        print("(no differences)")
        return
    out = "\n".join(diffs)
    if args.output:
        Path(args.output).write_text(out, encoding="utf-8")
        print(f"{len(diffs)} differences -> {args.output}")
    else:
        print(out)


def cmd_markdown_table(args):
    rows = _read_csv(args.input)
    if not rows:
        print("(empty)")
        return
    headers = list(rows[0].keys())
    lines = ["| " + " | ".join(headers) + " |",
             "|" + "|".join(["---"] * len(headers)) + "|"]
    for r in rows:
        cells = [str(r.get(h, "")).replace("|", "\\|") for h in headers]
        lines.append("| " + " | ".join(cells) + " |")
    out = "\n".join(lines)
    Path(args.output).write_text(out + "\n", encoding="utf-8")
    print(f"{len(rows)} rows -> {args.output}")


def cmd_csv_stats(args):
    rows = _read_csv(args.input)
    if not rows:
        print("(empty)")
        return
    headers = list(rows[0].keys())
    print(f"Rows: {len(rows)}, Columns: {len(headers)}")
    print()
    for h in headers:
        values = [r.get(h, "") for r in rows]
        non_null = [v for v in values if v not in ("", None)]
        nums = []
        for v in non_null:
            try:
                nums.append(float(v))
            except (ValueError, TypeError):
                pass
        unique = len(set(values))
        print(f"  {h}")
        print(f"     non-null: {len(non_null)}/{len(values)}, unique: {unique}")
        if nums and len(nums) == len(non_null):
            mn, mx = min(nums), max(nums)
            mean = sum(nums) / len(nums)
            print(f"     numeric: min={mn} max={mx} mean={mean:.4g}")
        else:
            sample = ", ".join(repr(v) for v in list(set(values))[:3])
            print(f"     sample: {sample}")


def cmd_sqlite_query(args):
    import sqlite3
    conn = sqlite3.connect(args.database)
    try:
        cur = conn.execute(args.sql)
        cols = [d[0] for d in cur.description] if cur.description else []
        rows = cur.fetchall()
        if args.output and args.output.endswith(".csv"):
            with open(args.output, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f); w.writerow(cols); w.writerows(rows)
            print(f"Wrote {len(rows)} rows -> {args.output}")
        elif args.output:
            data = [dict(zip(cols, r)) for r in rows]
            Path(args.output).write_text(json.dumps(data, indent=2, default=str, ensure_ascii=False),
                                         encoding="utf-8")
            print(f"Wrote {len(rows)} rows -> {args.output}")
        else:
            print(" | ".join(cols))
            print("-+-".join(["-" * max(3, len(c)) for c in cols]))
            for r in rows[:50]:
                print(" | ".join(str(v) for v in r))
            if len(rows) > 50:
                print(f"... ({len(rows) - 50} more)")
    finally:
        conn.close()


def cmd_sqlite_tables(args):
    import sqlite3
    conn = sqlite3.connect(args.database)
    try:
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        for (name,) in cur:
            count = conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
            print(f"  {name}  ({count:,} rows)")
    finally:
        conn.close()


def cmd_jsonpath(args):
    """Tiny JSONPath: $.a.b.c, $.list[0].field, $.list[*].field"""
    data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    parts = re.findall(r"\.([^.\[]+)|\[(\d+|\*)\]", args.path)
    cur = [data]
    for name, idx in parts:
        nxt = []
        for v in cur:
            if name:
                if isinstance(v, dict) and name in v:
                    nxt.append(v[name])
            elif idx == "*":
                if isinstance(v, list):
                    nxt.extend(v)
            else:
                if isinstance(v, list) and 0 <= int(idx) < len(v):
                    nxt.append(v[int(idx)])
        cur = nxt
    out = json.dumps(cur if len(cur) != 1 else cur[0], indent=2, default=str, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(out, encoding="utf-8")
    else:
        print(out)


def cmd_csv_view(args):
    rows = _read_csv(args.input)
    if not rows:
        print("(empty)")
        return
    headers = list(rows[0].keys())
    widths = {h: max(len(h), max(len(str(r.get(h, ""))) for r in rows)) for h in headers}
    print(" | ".join(h.ljust(widths[h]) for h in headers))
    print("-+-".join("-" * widths[h] for h in headers))
    for r in rows[: args.limit]:
        print(" | ".join(str(r.get(h, "")).ljust(widths[h]) for h in headers))
    if len(rows) > args.limit:
        print(f"... ({len(rows) - args.limit} more rows)")


COMMANDS = {
    "csv2json":  "CSV -> JSON",
    "json2csv":  "JSON (list of objects) -> CSV",
    "csv2xlsx":  "CSV -> Excel",
    "xlsx2csv":  "Excel sheet -> CSV",
    "xlsx2json": "Excel workbook -> JSON (all sheets)",
    "json2xlsx": "JSON list -> Excel",
    "yaml2json": "YAML -> JSON",
    "json2yaml": "JSON -> YAML",
    "xml2json":  "XML -> JSON",
    "toml2json": "TOML -> JSON",
    "csv-view":  "preview CSV in terminal",
    "csv-stats": "per-column statistics for a CSV",
    "markdown-table": "CSV -> markdown table",
    "json-merge": "deep-merge multiple JSON files",
    "json-diff":  "show structural diff of two JSON files",
    "jsonpath":   "tiny JSONPath query (e.g. $.users[*].name)",
    "sqlite-query":  "run a SELECT against a SQLite DB",
    "sqlite-tables": "list tables and row counts in a SQLite DB",
}


def build_parser(parser=None):
    parser = parser or argparse.ArgumentParser(prog="data_tools", description="Data conversions")
    sub = parser.add_subparsers(dest="cmd")

    in_out = [
        ("csv2json", cmd_csv2json),
        ("json2csv", cmd_json2csv),
        ("csv2xlsx", cmd_csv2xlsx),
        ("yaml2json", cmd_yaml2json),
        ("json2yaml", cmd_json2yaml),
        ("xml2json", cmd_xml2json),
        ("toml2json", cmd_toml2json),
        ("xlsx2json", cmd_xlsx2json),
        ("json2xlsx", cmd_json2xlsx),
    ]
    for name, fn in in_out:
        p = sub.add_parser(name, help=COMMANDS[name])
        p.add_argument("input"); p.add_argument("output")
        p.set_defaults(func=fn)

    p = sub.add_parser("xlsx2csv", help=COMMANDS["xlsx2csv"])
    p.add_argument("input"); p.add_argument("output")
    p.add_argument("--sheet")
    p.set_defaults(func=cmd_xlsx2csv)

    p = sub.add_parser("csv-view", help=COMMANDS["csv-view"])
    p.add_argument("input")
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(func=cmd_csv_view)

    p = sub.add_parser("csv-stats", help=COMMANDS["csv-stats"])
    p.add_argument("input")
    p.set_defaults(func=cmd_csv_stats)

    p = sub.add_parser("markdown-table", help=COMMANDS["markdown-table"])
    p.add_argument("input"); p.add_argument("output")
    p.set_defaults(func=cmd_markdown_table)

    p = sub.add_parser("json-merge", help=COMMANDS["json-merge"])
    p.add_argument("inputs", nargs="+")
    p.add_argument("-o", "--output")
    p.set_defaults(func=cmd_json_merge)

    p = sub.add_parser("json-diff", help=COMMANDS["json-diff"])
    p.add_argument("a"); p.add_argument("b")
    p.add_argument("-o", "--output")
    p.set_defaults(func=cmd_json_diff)

    p = sub.add_parser("jsonpath", help=COMMANDS["jsonpath"])
    p.add_argument("input")
    p.add_argument("path", help='e.g. $.users[0].name or $.users[*].email')
    p.add_argument("-o", "--output")
    p.set_defaults(func=cmd_jsonpath)

    p = sub.add_parser("sqlite-query", help=COMMANDS["sqlite-query"])
    p.add_argument("database")
    p.add_argument("sql")
    p.add_argument("-o", "--output")
    p.set_defaults(func=cmd_sqlite_query)

    p = sub.add_parser("sqlite-tables", help=COMMANDS["sqlite-tables"])
    p.add_argument("database")
    p.set_defaults(func=cmd_sqlite_tables)

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
