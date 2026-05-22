"""SQLite database helpers: query, csv import/export, schema, info, vacuum."""
from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
from pathlib import Path

from _common import human_size, tool_main


def _connect(path: str) -> sqlite3.Connection:
    p = Path(path)
    if not p.exists():
        print(f"[!] Database not found: {path}")
        raise SystemExit(1)
    return sqlite3.connect(str(p))


def _print_table(cols: list[str], rows: list[tuple], limit: int | None = None) -> None:
    if not rows:
        print("(no rows)")
        return
    str_rows = [[("" if v is None else str(v)) for v in r] for r in rows]
    widths = [max(len(c), *(len(r[i]) for r in str_rows)) for i, c in enumerate(cols)]
    sep = "-+-".join("-" * w for w in widths)
    print(" | ".join(c.ljust(w) for c, w in zip(cols, widths)))
    print(sep)
    shown = str_rows[: limit] if limit else str_rows
    for r in shown:
        print(" | ".join(v.ljust(w) for v, w in zip(r, widths)))
    if limit and len(str_rows) > limit:
        print(f"... ({len(str_rows) - limit} more rows)")


# ---- Command implementations ----

def cmd_query(args):
    """Run SQL and print a table."""
    sql = args.sql if args.sql else (Path(args.input).read_text(encoding="utf-8") if args.input else sys.stdin.read())
    con = _connect(args.db)
    try:
        cur = con.execute(sql)
        if cur.description is None:
            con.commit()
            print(f"OK ({cur.rowcount} affected)")
            return
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
        if args.format == "csv":
            w = csv.writer(sys.stdout if not args.output else open(args.output, "w", newline="", encoding="utf-8"))
            w.writerow(cols)
            w.writerows(rows)
            if args.output:
                print(f"Wrote {args.output}")
        else:
            _print_table(cols, rows, args.limit)
    finally:
        con.close()


def cmd_csv2sqlite(args):
    """Import CSV into a SQLite table (table name from filename)."""
    src = Path(args.input)
    table = args.table or src.stem.replace("-", "_").replace(" ", "_")
    con = sqlite3.connect(args.db)
    try:
        with src.open("r", newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            try:
                header = next(reader)
            except StopIteration:
                print("[!] Empty CSV")
                return 1
            cols = [f'"{c.strip() or f"col{i}"}"' for i, c in enumerate(header)]
            if args.replace:
                con.execute(f'DROP TABLE IF EXISTS "{table}"')
            con.execute(f'CREATE TABLE IF NOT EXISTS "{table}" ({", ".join(c + " TEXT" for c in cols)})')
            placeholders = ", ".join("?" for _ in cols)
            n = 0
            for row in reader:
                if len(row) < len(cols):
                    row = row + [""] * (len(cols) - len(row))
                elif len(row) > len(cols):
                    row = row[: len(cols)]
                con.execute(f'INSERT INTO "{table}" VALUES ({placeholders})', row)
                n += 1
        con.commit()
        print(f"Imported {n} rows into table '{table}' in {args.db}")
    finally:
        con.close()


def cmd_sqlite2csv(args):
    """Export a SQLite table to CSV."""
    con = _connect(args.db)
    try:
        cur = con.execute(f'SELECT * FROM "{args.table}"')
        cols = [d[0] for d in cur.description]
        out = args.output or f"{args.table}.csv"
        with open(out, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(cols)
            n = 0
            for row in cur:
                w.writerow(row)
                n += 1
        print(f"Wrote {n} rows to {out}")
    finally:
        con.close()


def cmd_schema(args):
    """Dump schema of a SQLite db."""
    con = _connect(args.db)
    try:
        cur = con.execute(
            "SELECT type, name, sql FROM sqlite_master "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
        )
        out_lines = []
        for type_, name, sql in cur:
            if sql:
                out_lines.append(f"-- {type_}: {name}")
                out_lines.append(sql.strip() + ";")
                out_lines.append("")
        body = "\n".join(out_lines) or "(empty schema)"
        if args.output:
            Path(args.output).write_text(body, encoding="utf-8")
            print(f"Wrote {args.output}")
        else:
            print(body)
    finally:
        con.close()


def cmd_tables(args):
    """List tables in a SQLite db."""
    con = _connect(args.db)
    try:
        cur = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
        names = [r[0] for r in cur]
        for n in names:
            print(n)
        if not names:
            print("(no tables)")
    finally:
        con.close()


def cmd_info(args):
    """Row counts and size per table."""
    con = _connect(args.db)
    try:
        cur = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
        names = [r[0] for r in cur]
        db_size = Path(args.db).stat().st_size
        print(f"Database:   {args.db}")
        print(f"File size:  {human_size(db_size)}")
        print(f"Tables:     {len(names)}")
        print()
        rows_out = []
        for name in names:
            n = con.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
            rows_out.append((name, n))
        _print_table(["Table", "Rows"], [(n, str(c)) for n, c in rows_out])
    finally:
        con.close()


def cmd_vacuum(args):
    """VACUUM the database."""
    con = _connect(args.db)
    try:
        before = Path(args.db).stat().st_size
        con.execute("VACUUM")
        con.commit()
        after = Path(args.db).stat().st_size
        print(f"Before: {human_size(before)}")
        print(f"After:  {human_size(after)}")
        print(f"Saved:  {human_size(before - after)}")
    finally:
        con.close()


# ---- COMMANDS dict ----
COMMANDS = {
    "query":       "run SQL against a SQLite db",
    "csv2sqlite":  "import CSV into a SQLite table",
    "sqlite2csv":  "export a SQLite table to CSV",
    "schema":      "dump schema of a SQLite db",
    "tables":      "list tables in a SQLite db",
    "info":        "row counts + size per table",
    "vacuum":      "VACUUM the database",
}


def build_parser(parser=None):
    parser = parser or argparse.ArgumentParser(prog="db_tools", description="SQLite helpers")
    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("query", help=COMMANDS["query"])
    p.add_argument("db")
    p.add_argument("sql", nargs="?")
    p.add_argument("-i", "--input")
    p.add_argument("-o", "--output")
    p.add_argument("--format", choices=["table", "csv"], default="table")
    p.add_argument("--limit", type=int, default=100)
    p.set_defaults(func=cmd_query)

    p = sub.add_parser("csv2sqlite", help=COMMANDS["csv2sqlite"])
    p.add_argument("db")
    p.add_argument("input", help="CSV file")
    p.add_argument("--table", help="defaults to filename stem")
    p.add_argument("--replace", action="store_true", help="drop table if exists")
    p.set_defaults(func=cmd_csv2sqlite)

    p = sub.add_parser("sqlite2csv", help=COMMANDS["sqlite2csv"])
    p.add_argument("db")
    p.add_argument("table")
    p.add_argument("-o", "--output")
    p.set_defaults(func=cmd_sqlite2csv)

    p = sub.add_parser("schema", help=COMMANDS["schema"])
    p.add_argument("db")
    p.add_argument("-o", "--output")
    p.set_defaults(func=cmd_schema)

    p = sub.add_parser("tables", help=COMMANDS["tables"])
    p.add_argument("db")
    p.set_defaults(func=cmd_tables)

    p = sub.add_parser("info", help=COMMANDS["info"])
    p.add_argument("db")
    p.set_defaults(func=cmd_info)

    p = sub.add_parser("vacuum", help=COMMANDS["vacuum"])
    p.add_argument("db")
    p.set_defaults(func=cmd_vacuum)

    return parser


@tool_main("db")
def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 1
    return args.func(args) or 0


if __name__ == "__main__":
    raise SystemExit(main())
