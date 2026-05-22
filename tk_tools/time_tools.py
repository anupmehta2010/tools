"""Time/date helpers: timezone, cron, duration, ICS, timestamps."""
from __future__ import annotations

import argparse
import datetime as dt
import re
import uuid
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from _common import lazy_import, tool_main


# ---- Timezone convert ----

def cmd_tz(args):
    """Convert datetime between timezones."""
    try:
        src_tz = ZoneInfo(args.from_tz)
        dst_tz = ZoneInfo(args.to_tz)
    except ZoneInfoNotFoundError as e:
        print(f"[!] Unknown timezone: {e}")
        return 1
    if args.when:
        try:
            d = dt.datetime.fromisoformat(args.when.replace("Z", "+00:00"))
        except ValueError as e:
            print(f"[!] Could not parse '{args.when}': {e}")
            return 1
        if d.tzinfo is None:
            d = d.replace(tzinfo=src_tz)
    else:
        d = dt.datetime.now(tz=src_tz)
    converted = d.astimezone(dst_tz)
    print(f"From ({args.from_tz}): {d.isoformat()}")
    print(f"To   ({args.to_tz}): {converted.isoformat()}")


# ---- Cron ----

_CRON_NAMES = {
    "min":   ["minute (0-59)"],
    "hour":  ["hour (0-23)"],
    "dom":   ["day of month (1-31)"],
    "month": ["month (1-12)"],
    "dow":   ["day of week (0-6, Sun=0)"],
}

_MONTHS = ["", "January", "February", "March", "April", "May", "June",
           "July", "August", "September", "October", "November", "December"]
_DOWS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]


def _explain_field(value: str, label: str, lookup=None) -> str:
    if value == "*":
        return f"every {label}"
    if value.startswith("*/"):
        return f"every {value[2:]} {label}(s)"
    if "-" in value:
        a, b = value.split("-", 1)
        return f"{label} {a} through {b}"
    if "," in value:
        return f"{label} " + ", ".join(value.split(","))
    if lookup and value.isdigit():
        idx = int(value)
        if 0 <= idx < len(lookup):
            return lookup[idx]
    return f"{label} {value}"


def cmd_cron_explain(args):
    """Explain a 5-field cron expression."""
    parts = args.expression.split()
    if len(parts) != 5:
        print(f"[!] Expected 5 fields, got {len(parts)}")
        return 1
    mn, hr, dom, mon, dow = parts
    print(f"Expression: {args.expression}")
    print(f"  Minute:       {_explain_field(mn, 'minute')}")
    print(f"  Hour:         {_explain_field(hr, 'hour')}")
    print(f"  Day of Month: {_explain_field(dom, 'day-of-month')}")
    print(f"  Month:        {_explain_field(mon, 'month', _MONTHS)}")
    print(f"  Day of Week:  {_explain_field(dow, 'day-of-week', _DOWS)}")


def cmd_cron_next(args):
    """Print next N firings of a cron expression (croniter)."""
    croniter = lazy_import("croniter", "pip install croniter")
    base = dt.datetime.now()
    it = croniter.croniter(args.expression, base)
    for _ in range(args.count):
        nxt = it.get_next(dt.datetime)
        print(nxt.isoformat())


# ---- Duration math ----

_DUR_PAT = re.compile(r"(\d+(?:\.\d+)?)\s*(w|d|h|m|s|ms)", re.I)
_DUR_MULT = {"w": 604800, "d": 86400, "h": 3600, "m": 60, "s": 1, "ms": 0.001}


def _parse_duration(s: str) -> float:
    total = 0.0
    matched = False
    for m in _DUR_PAT.finditer(s):
        matched = True
        total += float(m.group(1)) * _DUR_MULT[m.group(2).lower()]
    if not matched:
        try:
            total = float(s)
        except ValueError:
            raise ValueError(f"Could not parse duration '{s}'")
    return total


def _humanize_seconds(total: float) -> str:
    sign = "-" if total < 0 else ""
    total = abs(total)
    parts = []
    for label, sec in (("w", 604800), ("d", 86400), ("h", 3600), ("m", 60)):
        if total >= sec:
            v = int(total // sec)
            parts.append(f"{v}{label}")
            total -= v * sec
    if total or not parts:
        if total == int(total):
            parts.append(f"{int(total)}s")
        else:
            parts.append(f"{total:.3f}s")
    return sign + "".join(parts)


def cmd_duration(args):
    """Sum / subtract human durations like '1h30m + 2h15m'."""
    expr = " ".join(args.parts)
    tokens = re.split(r"\s*([+-])\s*", expr)
    total = 0.0
    op = "+"
    for tok in tokens:
        tok = tok.strip()
        if not tok:
            continue
        if tok in ("+", "-"):
            op = tok
            continue
        try:
            v = _parse_duration(tok)
        except ValueError as e:
            print(f"[!] {e}")
            return 1
        total = total + v if op == "+" else total - v
    print(f"Total seconds: {total}")
    print(f"Human:         {_humanize_seconds(total)}")


# ---- ICS ----

def cmd_ics(args):
    """Generate a single-event .ics calendar file."""
    try:
        start = dt.datetime.fromisoformat(args.start.replace("Z", "+00:00"))
        end = dt.datetime.fromisoformat(args.end.replace("Z", "+00:00"))
    except ValueError as e:
        print(f"[!] Could not parse datetime: {e}")
        return 1
    fmt = "%Y%m%dT%H%M%SZ"
    if start.tzinfo:
        start = start.astimezone(dt.timezone.utc)
    if end.tzinfo:
        end = end.astimezone(dt.timezone.utc)
    now = dt.datetime.now(dt.timezone.utc)
    uid = f"{uuid.uuid4()}@time_tools"
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//tools//time_tools//EN",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{now.strftime(fmt)}",
        f"DTSTART:{start.strftime(fmt)}",
        f"DTEND:{end.strftime(fmt)}",
        f"SUMMARY:{args.summary}",
    ]
    if args.description:
        lines.append(f"DESCRIPTION:{args.description}")
    if args.location:
        lines.append(f"LOCATION:{args.location}")
    lines += ["END:VEVENT", "END:VCALENDAR"]
    body = "\r\n".join(lines) + "\r\n"
    out = args.output or "event.ics"
    Path(out).write_text(body, encoding="utf-8")
    print(f"Wrote {out}")


# ---- Now ----

def cmd_unix_now(args):
    """Current unix timestamp (with optional ms/us)."""
    now = dt.datetime.now(dt.timezone.utc)
    if args.unit == "ms":
        print(int(now.timestamp() * 1000))
    elif args.unit == "us":
        print(int(now.timestamp() * 1_000_000))
    else:
        print(int(now.timestamp()))


def cmd_iso_now(args):
    """Current ISO 8601 timestamp."""
    if args.tz:
        try:
            zone = ZoneInfo(args.tz)
        except ZoneInfoNotFoundError as e:
            print(f"[!] Unknown timezone: {e}")
            return 1
        print(dt.datetime.now(tz=zone).isoformat())
    else:
        print(dt.datetime.now(dt.timezone.utc).isoformat())


def cmd_parse(args):
    """Parse a free-form datetime string via dateutil."""
    parser_mod = lazy_import("dateutil.parser", "pip install python-dateutil")
    try:
        d = parser_mod.parse(args.value)
    except (ValueError, TypeError) as e:
        print(f"[!] Could not parse: {e}")
        return 1
    print(f"ISO:      {d.isoformat()}")
    if d.tzinfo:
        print(f"UTC:      {d.astimezone(dt.timezone.utc).isoformat()}")
    print(f"Unix:     {int(d.timestamp()) if d.tzinfo else '(naive, no tz)'}")


# ---- COMMANDS dict ----
COMMANDS = {
    "tz":           "convert datetime between timezones",
    "cron-explain": "explain a cron expression in English",
    "cron-next":    "print next N firings of a cron expression",
    "duration":     "human duration math (1h30m + 2h15m)",
    "ics":          "generate a single-event .ics file",
    "unix-now":     "current unix timestamp (s/ms/us)",
    "iso-now":      "current ISO 8601 timestamp",
    "parse":        "parse free-form datetime via dateutil",
}


def build_parser(parser=None):
    parser = parser or argparse.ArgumentParser(prog="time_tools", description="Time/date helpers")
    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("tz", help=COMMANDS["tz"])
    p.add_argument("--from-tz", required=True, dest="from_tz")
    p.add_argument("--to-tz", required=True, dest="to_tz")
    p.add_argument("--when", help="ISO datetime; omit for now")
    p.set_defaults(func=cmd_tz)

    p = sub.add_parser("cron-explain", help=COMMANDS["cron-explain"])
    p.add_argument("expression")
    p.set_defaults(func=cmd_cron_explain)

    p = sub.add_parser("cron-next", help=COMMANDS["cron-next"])
    p.add_argument("expression")
    p.add_argument("--count", type=int, default=5)
    p.set_defaults(func=cmd_cron_next)

    p = sub.add_parser("duration", help=COMMANDS["duration"])
    p.add_argument("parts", nargs="+")
    p.set_defaults(func=cmd_duration)

    p = sub.add_parser("ics", help=COMMANDS["ics"])
    p.add_argument("--summary", required=True)
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    p.add_argument("--description")
    p.add_argument("--location")
    p.add_argument("-o", "--output")
    p.set_defaults(func=cmd_ics)

    p = sub.add_parser("unix-now", help=COMMANDS["unix-now"])
    p.add_argument("--unit", choices=["s", "ms", "us"], default="s")
    p.set_defaults(func=cmd_unix_now)

    p = sub.add_parser("iso-now", help=COMMANDS["iso-now"])
    p.add_argument("--tz")
    p.set_defaults(func=cmd_iso_now)

    p = sub.add_parser("parse", help=COMMANDS["parse"])
    p.add_argument("value")
    p.set_defaults(func=cmd_parse)

    return parser


@tool_main("time")
def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 1
    return args.func(args) or 0


if __name__ == "__main__":
    raise SystemExit(main())
