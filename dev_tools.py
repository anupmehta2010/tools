"""Dev utilities: regex tester, color converter, lorem ipsum, base, calc, timestamp, slug, curl-to-Python."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import random
import re
import shlex
import sys
import unicodedata


# ---- Regex ----

def cmd_regex(args):
    flags = 0
    if args.ignore_case:
        flags |= re.IGNORECASE
    if args.multiline:
        flags |= re.MULTILINE
    if args.dotall:
        flags |= re.DOTALL
    pat = re.compile(args.pattern, flags)
    text = args.text or sys.stdin.read()
    matches = list(pat.finditer(text))
    print(f"{len(matches)} match(es)")
    for i, m in enumerate(matches[: args.limit], 1):
        print(f"  [{i}] {m.group(0)!r}  span={m.span()}")
        if m.groups():
            for gi, g in enumerate(m.groups(), 1):
                print(f"      group {gi}: {g!r}")
        if m.groupdict():
            for name, val in m.groupdict().items():
                print(f"      {name}: {val!r}")


def cmd_regex_replace(args):
    flags = re.IGNORECASE if args.ignore_case else 0
    text = args.text or sys.stdin.read()
    out, n = re.subn(args.pattern, args.replacement, text, flags=flags)
    print(out)
    print(f"\n[{n} replacement(s)]", file=sys.stderr)


# ---- Color ----

def _hex_to_rgb(s):
    s = s.lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    if len(s) != 6:
        raise ValueError(f"Bad hex color: #{s}")
    return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))


def _rgb_to_hex(rgb):
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def _rgb_to_hsl(r, g, b):
    r, g, b = r / 255.0, g / 255.0, b / 255.0
    mx, mn = max(r, g, b), min(r, g, b)
    l = (mx + mn) / 2
    if mx == mn:
        return 0.0, 0.0, l * 100
    d = mx - mn
    s = d / (2 - mx - mn) if l > 0.5 else d / (mx + mn)
    if mx == r:
        h = (g - b) / d + (6 if g < b else 0)
    elif mx == g:
        h = (b - r) / d + 2
    else:
        h = (r - g) / d + 4
    return h * 60, s * 100, l * 100


def cmd_color(args):
    s = args.color.strip()
    try:
        if s.startswith("rgb"):
            nums = re.findall(r"\d+", s)
            rgb = tuple(int(x) for x in nums[:3])
        else:
            rgb = _hex_to_rgb(s)
    except Exception as e:
        print(f"Could not parse color: {e}")
        return 1
    h, sa, l = _rgb_to_hsl(*rgb)
    print(f"HEX:  {_rgb_to_hex(rgb)}")
    print(f"RGB:  rgb({rgb[0]}, {rgb[1]}, {rgb[2]})")
    print(f"HSL:  hsl({h:.0f}, {sa:.0f}%, {l:.0f}%)")


# ---- Lorem ipsum ----

LOREM = (
    "lorem ipsum dolor sit amet consectetur adipiscing elit sed do eiusmod tempor "
    "incididunt ut labore et dolore magna aliqua ut enim ad minim veniam quis nostrud "
    "exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat duis aute "
    "irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla "
    "pariatur excepteur sint occaecat cupidatat non proident sunt in culpa qui officia "
    "deserunt mollit anim id est laborum"
).split()


def cmd_lorem(args):
    rng = random.Random(args.seed)
    if args.unit == "words":
        out = " ".join(rng.choice(LOREM) for _ in range(args.count))
    elif args.unit == "sentences":
        sentences = []
        for _ in range(args.count):
            n = rng.randint(8, 18)
            s = " ".join(rng.choice(LOREM) for _ in range(n))
            sentences.append(s.capitalize() + ".")
        out = " ".join(sentences)
    else:
        paragraphs = []
        for _ in range(args.count):
            sents = []
            for _ in range(rng.randint(4, 8)):
                n = rng.randint(8, 18)
                s = " ".join(rng.choice(LOREM) for _ in range(n))
                sents.append(s.capitalize() + ".")
            paragraphs.append(" ".join(sents))
        out = "\n\n".join(paragraphs)
    print(out)


# ---- Base conversion ----

def cmd_base(args):
    n = int(args.number, args.from_base)
    if args.to_base == 2:
        print(bin(n)[2:])
    elif args.to_base == 8:
        print(oct(n)[2:])
    elif args.to_base == 10:
        print(n)
    elif args.to_base == 16:
        print(hex(n)[2:])
    else:
        digits = "0123456789abcdefghijklmnopqrstuvwxyz"
        if args.to_base > len(digits):
            print(f"to-base must be <= {len(digits)}")
            return 1
        if n == 0:
            print("0")
            return
        out = ""
        nn = abs(n)
        while nn:
            out = digits[nn % args.to_base] + out
            nn //= args.to_base
        print(("-" if n < 0 else "") + out)


# ---- Calculator ----

def cmd_calc(args):
    expr = " ".join(args.expression)
    allowed = {k: getattr(math, k) for k in dir(math) if not k.startswith("_")}
    allowed.update({"abs": abs, "round": round, "min": min, "max": max,
                    "sum": sum, "pow": pow, "int": int, "float": float})
    try:
        result = eval(expr, {"__builtins__": {}}, allowed)
        print(result)
    except Exception as e:
        print(f"Error: {e}")
        return 1


# ---- Timestamps ----

def cmd_timestamp(args):
    if args.value is None:
        now = dt.datetime.now(dt.timezone.utc)
        print(f"Now (UTC):       {now.isoformat()}")
        print(f"Now (local):     {now.astimezone().isoformat()}")
        print(f"Unix:            {int(now.timestamp())}")
        print(f"Unix (ms):       {int(now.timestamp() * 1000)}")
        return
    val = args.value.strip()
    try:
        if val.lstrip("-").isdigit():
            ts = int(val)
            if abs(ts) > 10_000_000_000:
                ts //= 1000
            d = dt.datetime.fromtimestamp(ts, tz=dt.timezone.utc)
        else:
            d = dt.datetime.fromisoformat(val.replace("Z", "+00:00"))
            if d.tzinfo is None:
                d = d.replace(tzinfo=dt.timezone.utc)
    except (ValueError, OverflowError) as e:
        print(f"Could not parse: {e}")
        return 1
    print(f"UTC:        {d.isoformat()}")
    print(f"Local:      {d.astimezone().isoformat()}")
    print(f"Unix:       {int(d.timestamp())}")
    print(f"Unix (ms):  {int(d.timestamp() * 1000)}")


# ---- Slugify ----

def cmd_slug(args):
    s = unicodedata.normalize("NFKD", args.text)
    s = s.encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^a-zA-Z0-9\s\-]", "", s).strip().lower()
    s = re.sub(r"[\s\-]+", "-", s)
    print(s)


# ---- curl -> Python ----

def cmd_curl_to_python(args):
    cmd = " ".join(args.curl)
    tokens = shlex.split(cmd)
    method = "GET"
    url = ""
    headers: list[str] = []
    data = None
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t in ("-X", "--request"):
            method = tokens[i + 1]; i += 2
        elif t in ("-H", "--header"):
            headers.append(tokens[i + 1]); i += 2
        elif t in ("-d", "--data", "--data-raw"):
            data = tokens[i + 1]; i += 2
            if method == "GET":
                method = "POST"
        elif t.startswith("http://") or t.startswith("https://"):
            url = t; i += 1
        elif t == "curl":
            i += 1
        else:
            i += 1
    print("import urllib.request")
    print()
    if data:
        print(f"data = {data!r}.encode()")
    suffix = ", data=data" if data else ""
    print(f"req = urllib.request.Request({url!r}, method={method!r}{suffix})")
    for h in headers:
        if ":" in h:
            k, v = h.split(":", 1)
            print(f"req.add_header({k.strip()!r}, {v.strip()!r})")
    print("with urllib.request.urlopen(req) as r:")
    print("    print(r.read().decode())")


# ---- IP/CIDR helper ----

def cmd_cidr(args):
    import ipaddress
    net = ipaddress.ip_network(args.cidr, strict=False)
    print(f"Network:    {net.network_address}")
    print(f"Broadcast:  {net.broadcast_address}")
    print(f"Netmask:    {net.netmask}")
    print(f"Prefix len: /{net.prefixlen}")
    print(f"Hosts:      {net.num_addresses - (2 if net.version == 4 and net.prefixlen < 31 else 0):,}")
    if args.list:
        for ip in net.hosts():
            print(ip)


# ---- Number stats ----

def cmd_stats(args):
    nums = []
    for tok in args.numbers:
        try:
            nums.append(float(tok))
        except ValueError:
            pass
    if not nums:
        print("No numbers.")
        return 1
    nums.sort()
    n = len(nums)
    mean = sum(nums) / n
    var = sum((x - mean) ** 2 for x in nums) / n
    median = nums[n // 2] if n % 2 else (nums[n // 2 - 1] + nums[n // 2]) / 2
    print(f"Count:    {n}")
    print(f"Sum:      {sum(nums)}")
    print(f"Min:      {nums[0]}")
    print(f"Max:      {nums[-1]}")
    print(f"Mean:     {mean}")
    print(f"Median:   {median}")
    print(f"Stdev:    {math.sqrt(var)}")


def cmd_ulid(args):
    """Generate ULIDs (Crockford Base32, 26 chars, time-sortable)."""
    import os, time
    ENC = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

    def encode(n, length):
        s = ""
        for _ in range(length):
            s = ENC[n & 0x1F] + s
            n >>= 5
        return s

    for _ in range(args.count):
        ts = int(time.time() * 1000)
        rand = int.from_bytes(os.urandom(10), "big")
        print(encode(ts, 10) + encode(rand, 16))


def cmd_semver_bump(args):
    """Bump semver: major / minor / patch."""
    m = re.match(r"^v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\+([0-9A-Za-z.-]+))?$", args.version.strip())
    if not m:
        print(f"Not a valid semver: {args.version}")
        return 1
    major, minor, patch = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if args.bump == "major":
        major, minor, patch = major + 1, 0, 0
    elif args.bump == "minor":
        minor, patch = minor + 1, 0
    else:
        patch += 1
    out = f"{major}.{minor}.{patch}"
    if args.pre:
        out += "-" + args.pre
    print(out)


_MOCK_FIRST = ["Alice", "Bob", "Charlie", "Diana", "Eve", "Frank", "Grace",
               "Henry", "Iris", "Jack", "Kate", "Leo", "Maya", "Noah", "Olivia"]
_MOCK_LAST  = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia",
               "Miller", "Davis", "Rodriguez", "Martinez", "Hernandez", "Lopez"]
_MOCK_DOMAINS = ["example.com", "demo.io", "test.org", "sample.dev", "fake.email"]
_MOCK_CITIES = ["Paris", "Tokyo", "London", "New York", "Mumbai", "Berlin", "Sydney", "Cairo"]


def cmd_mock(args):
    import random as _r
    rng = _r.Random(args.seed)
    rows = []
    for i in range(args.count):
        first = rng.choice(_MOCK_FIRST)
        last = rng.choice(_MOCK_LAST)
        rows.append({
            "id":      i + 1,
            "name":    f"{first} {last}",
            "email":   f"{first.lower()}.{last.lower()}@{rng.choice(_MOCK_DOMAINS)}",
            "city":    rng.choice(_MOCK_CITIES),
            "age":     rng.randint(18, 80),
            "score":   round(rng.uniform(0, 100), 2),
            "active":  rng.choice([True, False]),
        })
    if args.format == "json":
        out = json.dumps(rows, indent=2)
    elif args.format == "csv":
        import csv as _csv, io as _io
        buf = _io.StringIO()
        w = _csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
        out = buf.getvalue()
    else:
        out = "\n".join(f"{r['name']:<24}  {r['email']:<40}  {r['city']:<10}  {r['age']:>3}" for r in rows)
    if args.output:
        from pathlib import Path as _P
        _P(args.output).write_text(out, encoding="utf-8")
        print(f"Wrote {args.count} records -> {args.output}")
    else:
        print(out)


def cmd_regex_explain(args):
    """Try to compile regex and label each token."""
    try:
        re.compile(args.pattern)
    except re.error as e:
        print(f"Invalid: {e}")
        return 1
    tokens = []
    rules = [
        (r"\(\?P<[^>]+>", "named capture group"),
        (r"\(\?:", "non-capturing group"),
        (r"\(\?=", "lookahead"),
        (r"\(\?!", "negative lookahead"),
        (r"\(", "capture group ("), (r"\)", "group close )"),
        (r"\[\^[^\]]*\]", "negated character class"),
        (r"\[[^\]]*\]", "character class"),
        (r"\\d", "digit"), (r"\\D", "non-digit"),
        (r"\\w", "word char"), (r"\\W", "non-word"),
        (r"\\s", "whitespace"), (r"\\S", "non-whitespace"),
        (r"\\b", "word boundary"), (r"\\B", "non-boundary"),
        (r"\\.", "literal ."), (r"\.", "any char"),
        (r"\*\?", "lazy *"), (r"\+\?", "lazy +"),
        (r"\*", "0 or more (greedy)"), (r"\+", "1 or more (greedy)"),
        (r"\?", "optional / lazy"),
        (r"\{\d+,?\d*\}", "exact / range quantifier"),
        (r"\|", "alternation"),
        (r"\^", "start anchor"), (r"\$", "end anchor"),
    ]
    pat = args.pattern
    i = 0
    while i < len(pat):
        matched = None
        for r, label in rules:
            m = re.match(r, pat[i:])
            if m:
                matched = (m.group(0), label)
                tokens.append(matched)
                i += len(m.group(0))
                break
        if not matched:
            tokens.append((pat[i], "literal"))
            i += 1
    print(f"Pattern: {args.pattern}")
    print(f"Tokens ({len(tokens)}):")
    for tok, label in tokens:
        print(f"  {tok!r:<10}  {label}")


COMMANDS = {
    "regex":          "test a regex pattern",
    "regex-replace":  "regex search-and-replace",
    "color":          "convert color (hex/rgb/hsl)",
    "lorem":          "generate lorem ipsum (words/sentences/paragraphs)",
    "base":           "base conversion (2/8/10/16/...)",
    "calc":           "evaluate a math expression",
    "timestamp":      "now / convert between unix and ISO",
    "slug":           "slugify text",
    "curl-to-python": "convert a curl command to Python urllib code",
    "cidr":           "CIDR network info (and --list hosts)",
    "stats":          "min/max/mean/median/stdev of numbers",
    "ulid":           "generate ULIDs (time-sortable, 26 chars)",
    "semver-bump":    "bump semver version (major/minor/patch)",
    "mock":           "generate fake person/data records (json/csv/table)",
    "regex-explain":  "label each token in a regex pattern",
}


def build_parser(parser=None):
    parser = parser or argparse.ArgumentParser(prog="dev_tools", description="Dev utilities")
    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("regex", help=COMMANDS["regex"])
    p.add_argument("pattern"); p.add_argument("text", nargs="?")
    p.add_argument("--ignore-case", action="store_true")
    p.add_argument("--multiline", action="store_true")
    p.add_argument("--dotall", action="store_true")
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(func=cmd_regex)

    p = sub.add_parser("regex-replace", help=COMMANDS["regex-replace"])
    p.add_argument("pattern"); p.add_argument("replacement")
    p.add_argument("text", nargs="?")
    p.add_argument("--ignore-case", action="store_true")
    p.set_defaults(func=cmd_regex_replace)

    p = sub.add_parser("color", help=COMMANDS["color"])
    p.add_argument("color")
    p.set_defaults(func=cmd_color)

    p = sub.add_parser("lorem", help=COMMANDS["lorem"])
    p.add_argument("count", type=int, default=3, nargs="?")
    p.add_argument("--unit", choices=["words", "sentences", "paragraphs"], default="paragraphs")
    p.add_argument("--seed", type=int, default=None)
    p.set_defaults(func=cmd_lorem)

    p = sub.add_parser("base", help=COMMANDS["base"])
    p.add_argument("number")
    p.add_argument("--from-base", type=int, default=10, dest="from_base")
    p.add_argument("--to-base", type=int, required=True, dest="to_base")
    p.set_defaults(func=cmd_base)

    p = sub.add_parser("calc", help=COMMANDS["calc"])
    p.add_argument("expression", nargs="+")
    p.set_defaults(func=cmd_calc)

    p = sub.add_parser("timestamp", help=COMMANDS["timestamp"])
    p.add_argument("value", nargs="?")
    p.set_defaults(func=cmd_timestamp)

    p = sub.add_parser("slug", help=COMMANDS["slug"])
    p.add_argument("text")
    p.set_defaults(func=cmd_slug)

    p = sub.add_parser("curl-to-python", help=COMMANDS["curl-to-python"])
    p.add_argument("curl", nargs="+")
    p.set_defaults(func=cmd_curl_to_python)

    p = sub.add_parser("cidr", help=COMMANDS["cidr"])
    p.add_argument("cidr")
    p.add_argument("--list", action="store_true")
    p.set_defaults(func=cmd_cidr)

    p = sub.add_parser("stats", help=COMMANDS["stats"])
    p.add_argument("numbers", nargs="+")
    p.set_defaults(func=cmd_stats)

    p = sub.add_parser("ulid", help=COMMANDS["ulid"])
    p.add_argument("--count", type=int, default=1)
    p.set_defaults(func=cmd_ulid)

    p = sub.add_parser("semver-bump", help=COMMANDS["semver-bump"])
    p.add_argument("version")
    p.add_argument("--bump", choices=["major", "minor", "patch"], default="patch")
    p.add_argument("--pre", help="optional pre-release tag, e.g. 'rc1'")
    p.set_defaults(func=cmd_semver_bump)

    p = sub.add_parser("mock", help=COMMANDS["mock"])
    p.add_argument("--count", type=int, default=10)
    p.add_argument("--format", choices=["json", "csv", "table"], default="table")
    p.add_argument("--seed", type=int)
    p.add_argument("-o", "--output")
    p.set_defaults(func=cmd_mock)

    p = sub.add_parser("regex-explain", help=COMMANDS["regex-explain"])
    p.add_argument("pattern")
    p.set_defaults(func=cmd_regex_explain)

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
