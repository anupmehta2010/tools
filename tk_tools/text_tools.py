"""Text tools: encode/decode, hash, case conversion, format, diff, count."""
from __future__ import annotations

import argparse
import base64
import binascii
import difflib
import hashlib
import html
import json
import re
import sys
import urllib.parse
from pathlib import Path

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))
from _common import tool_main


def _read_input(args) -> str:
    if getattr(args, "text", None) is not None:
        return args.text
    if getattr(args, "input", None):
        return Path(args.input).read_text(encoding="utf-8")
    return sys.stdin.read()


def _write_output(args, data: str) -> None:
    if getattr(args, "output", None):
        Path(args.output).write_text(data, encoding="utf-8")
        print(f"Wrote {args.output}")
    else:
        print(data)


# ---- Encoding ----

def cmd_b64encode(args):
    _write_output(args, base64.b64encode(_read_input(args).encode("utf-8")).decode())


def cmd_b64decode(args):
    s = _read_input(args).strip()
    _write_output(args, base64.b64decode(s).decode("utf-8", errors="replace"))


def cmd_urlencode(args):
    _write_output(args, urllib.parse.quote(_read_input(args)))


def cmd_urldecode(args):
    _write_output(args, urllib.parse.unquote(_read_input(args)))


def cmd_htmlencode(args):
    _write_output(args, html.escape(_read_input(args)))


def cmd_htmldecode(args):
    _write_output(args, html.unescape(_read_input(args)))


def cmd_hexencode(args):
    _write_output(args, _read_input(args).encode().hex())


def cmd_hexdecode(args):
    _write_output(args, binascii.unhexlify(_read_input(args).strip()).decode("utf-8", errors="replace"))


# ---- Hashing ----

def cmd_hash(args):
    h = hashlib.new(args.algo)
    if getattr(args, "input", None):
        with open(args.input, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
    else:
        h.update(_read_input(args).encode("utf-8"))
    _write_output(args, h.hexdigest())


# ---- Case ----

def cmd_upper(args):
    _write_output(args, _read_input(args).upper())


def cmd_lower(args):
    _write_output(args, _read_input(args).lower())


def cmd_title(args):
    _write_output(args, _read_input(args).title())


def cmd_capitalize(args):
    _write_output(args, _read_input(args).capitalize())


def cmd_snake(args):
    s = _read_input(args).strip()
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s)
    s = re.sub(r"[\s\-]+", "_", s)
    _write_output(args, s.lower())


def cmd_kebab(args):
    s = _read_input(args).strip()
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", s)
    s = re.sub(r"[\s_]+", "-", s)
    _write_output(args, s.lower())


def cmd_camel(args):
    parts = re.split(r"[\s\-_]+", _read_input(args).strip())
    parts = [p for p in parts if p]
    if not parts:
        return _write_output(args, "")
    _write_output(args, parts[0].lower() + "".join(p.capitalize() for p in parts[1:]))


def cmd_pascal(args):
    parts = re.split(r"[\s\-_]+", _read_input(args).strip())
    parts = [p for p in parts if p]
    _write_output(args, "".join(p.capitalize() for p in parts))


# ---- Formatting ----

def cmd_json_format(args):
    data = json.loads(_read_input(args))
    out = json.dumps(data, indent=args.indent, sort_keys=args.sort, ensure_ascii=False)
    _write_output(args, out)


def cmd_json_minify(args):
    data = json.loads(_read_input(args))
    _write_output(args, json.dumps(data, separators=(",", ":"), ensure_ascii=False))


def cmd_json_validate(args):
    try:
        json.loads(_read_input(args))
        print("OK: valid JSON")
    except json.JSONDecodeError as e:
        print(f"INVALID: {e}")
        return 1


# ---- Diff ----

def cmd_diff(args):
    a = Path(args.a).read_text(encoding="utf-8").splitlines(keepends=True)
    b = Path(args.b).read_text(encoding="utf-8").splitlines(keepends=True)
    out = "".join(difflib.unified_diff(a, b, fromfile=args.a, tofile=args.b))
    if not out:
        print("(no differences)")
        return
    if args.output:
        Path(args.output).write_text(out, encoding="utf-8")
        print(f"Wrote {args.output}")
    else:
        sys.stdout.write(out)


# ---- Stats ----

def cmd_count(args):
    text = _read_input(args)
    print(f"Lines:      {len(text.splitlines())}")
    print(f"Words:      {len(text.split())}")
    print(f"Characters: {len(text)}")
    print(f"Bytes:      {len(text.encode('utf-8'))}")


# ---- Reverse / sort lines ----

def cmd_reverse(args):
    _write_output(args, _read_input(args)[::-1])


def cmd_sort_lines(args):
    lines = _read_input(args).splitlines()
    lines.sort(reverse=args.reverse, key=str.casefold if args.ci else None)
    if args.unique:
        seen = set(); out_lines = []
        for ln in lines:
            key = ln.casefold() if args.ci else ln
            if key not in seen:
                seen.add(key); out_lines.append(ln)
        lines = out_lines
    _write_output(args, "\n".join(lines))


def cmd_strip(args):
    lines = _read_input(args).splitlines()
    out = []
    for ln in lines:
        if args.empty and not ln.strip():
            continue
        out.append(ln.strip() if args.whitespace else ln)
    _write_output(args, "\n".join(out))


def cmd_replace(args):
    text = _read_input(args)
    out = text.replace(args.find, args.replacement)
    _write_output(args, out)


# ---- Ciphers / encoding ----

def cmd_rot13(args):
    import codecs
    _write_output(args, codecs.encode(_read_input(args), "rot_13"))


def cmd_normalize(args):
    import unicodedata
    _write_output(args, unicodedata.normalize(args.form, _read_input(args)))


def cmd_unicode_info(args):
    import unicodedata
    text = _read_input(args)
    lines = []
    for ch in text[: args.limit]:
        cp = ord(ch)
        try:
            name = unicodedata.name(ch)
        except ValueError:
            name = "<no name>"
        cat = unicodedata.category(ch)
        lines.append(f"{ch!r:>8}  U+{cp:04X}  {cat:>3}  {name}")
    _write_output(args, "\n".join(lines))


# ---- Markdown <-> HTML (no external deps) ----

_MD_INLINE = [
    (r"`([^`]+)`",          r"<code>\1</code>"),
    (r"\*\*(.+?)\*\*",      r"<strong>\1</strong>"),
    (r"__(.+?)__",          r"<strong>\1</strong>"),
    (r"\*(.+?)\*",          r"<em>\1</em>"),
    (r"_(.+?)_",            r"<em>\1</em>"),
    (r"~~(.+?)~~",          r"<del>\1</del>"),
    (r"!\[([^\]]*)\]\(([^)]+)\)", r'<img src="\2" alt="\1">'),
    (r"\[([^\]]+)\]\(([^)]+)\)",  r'<a href="\2">\1</a>'),
]


def _md_inline(s):
    for pat, repl in _MD_INLINE:
        s = re.sub(pat, repl, s)
    return s


def cmd_md_to_html(args):
    src = _read_input(args)
    out = []
    in_code = False
    in_list = False
    for line in src.splitlines():
        if line.startswith("```"):
            if in_code:
                out.append("</code></pre>")
                in_code = False
            else:
                out.append("<pre><code>")
                in_code = True
            continue
        if in_code:
            out.append(html.escape(line))
            continue
        m = re.match(r"^(#{1,6})\s+(.+)$", line)
        if m:
            if in_list:
                out.append("</ul>"); in_list = False
            n = len(m.group(1))
            out.append(f"<h{n}>{_md_inline(html.escape(m.group(2)))}</h{n}>")
            continue
        if re.match(r"^\s*[-*+]\s+", line):
            if not in_list:
                out.append("<ul>"); in_list = True
            item = re.sub(r"^\s*[-*+]\s+", "", line)
            out.append(f"  <li>{_md_inline(html.escape(item))}</li>")
            continue
        if in_list:
            out.append("</ul>"); in_list = False
        if line.strip() == "":
            out.append("")
        else:
            out.append(f"<p>{_md_inline(html.escape(line))}</p>")
    if in_list:
        out.append("</ul>")
    if in_code:
        out.append("</code></pre>")
    _write_output(args, "\n".join(out))


def cmd_html_to_md(args):
    s = _read_input(args)
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"<h([1-6])[^>]*>(.*?)</h\1>",
               lambda m: "\n" + "#" * int(m.group(1)) + " " + m.group(2) + "\n", s, flags=re.I | re.S)
    s = re.sub(r"<(strong|b)[^>]*>(.*?)</\1>", r"**\2**", s, flags=re.I | re.S)
    s = re.sub(r"<(em|i)[^>]*>(.*?)</\1>",     r"*\2*", s, flags=re.I | re.S)
    s = re.sub(r"<code[^>]*>(.*?)</code>",     r"`\1`", s, flags=re.I | re.S)
    s = re.sub(r'<a [^>]*href="([^"]+)"[^>]*>(.*?)</a>', r"[\2](\1)", s, flags=re.I | re.S)
    s = re.sub(r'<img [^>]*src="([^"]+)"[^>]*alt="([^"]*)"[^>]*>', r"![\2](\1)", s, flags=re.I)
    s = re.sub(r"<li[^>]*>(.*?)</li>", r"- \1", s, flags=re.I | re.S)
    s = re.sub(r"</?(ul|ol|p|div)[^>]*>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s)
    s = re.sub(r"\n{3,}", "\n\n", s).strip() + "\n"
    _write_output(args, s)


COMMANDS = {
    "b64encode":     "Base64 encode",
    "b64decode":     "Base64 decode",
    "urlencode":     "URL encode",
    "urldecode":     "URL decode",
    "htmlencode":    "HTML escape",
    "htmldecode":    "HTML unescape",
    "hexencode":     "Hex encode",
    "hexdecode":     "Hex decode",
    "hash":          "MD5/SHA hash of text or file",
    "upper":         "to UPPERCASE",
    "lower":         "to lowercase",
    "title":         "to Title Case",
    "capitalize":    "First letter uppercase",
    "snake":         "to snake_case",
    "kebab":         "to kebab-case",
    "camel":         "to camelCase",
    "pascal":        "to PascalCase",
    "json-format":   "pretty-print JSON",
    "json-minify":   "minify JSON",
    "json-validate": "validate JSON",
    "diff":          "unified diff between two files",
    "count":         "count lines/words/chars/bytes",
    "reverse":       "reverse the input string",
    "sort-lines":    "sort lines (with --unique, --reverse, --ci)",
    "strip":         "strip whitespace and/or empty lines",
    "replace":       "literal find/replace",
    "rot13":         "ROT13 transform",
    "normalize":     "Unicode normalization (NFC/NFD/NFKC/NFKD)",
    "unicode-info":  "show codepoint, category, name for each character",
    "md-to-html":    "Markdown -> HTML (no external deps)",
    "html-to-md":    "HTML -> Markdown (basic stripper)",
}


def _add_io(p):
    p.add_argument("text", nargs="?")
    p.add_argument("-i", "--input")
    p.add_argument("-o", "--output")


def build_parser(parser=None):
    parser = parser or argparse.ArgumentParser(prog="text_tools", description="Text utilities")
    sub = parser.add_subparsers(dest="cmd")

    simple_io = [
        ("b64encode", cmd_b64encode), ("b64decode", cmd_b64decode),
        ("urlencode", cmd_urlencode), ("urldecode", cmd_urldecode),
        ("htmlencode", cmd_htmlencode), ("htmldecode", cmd_htmldecode),
        ("hexencode", cmd_hexencode), ("hexdecode", cmd_hexdecode),
        ("upper", cmd_upper), ("lower", cmd_lower), ("title", cmd_title),
        ("capitalize", cmd_capitalize), ("snake", cmd_snake),
        ("kebab", cmd_kebab), ("camel", cmd_camel), ("pascal", cmd_pascal),
        ("count", cmd_count), ("reverse", cmd_reverse),
        ("json-validate", cmd_json_validate),
    ]
    for name, fn in simple_io:
        p = sub.add_parser(name, help=COMMANDS[name])
        _add_io(p)
        p.set_defaults(func=fn)

    p = sub.add_parser("hash", help=COMMANDS["hash"])
    _add_io(p)
    p.add_argument("--algo", default="sha256",
                   choices=["md5", "sha1", "sha224", "sha256", "sha384", "sha512", "blake2b", "blake2s"])
    p.set_defaults(func=cmd_hash)

    p = sub.add_parser("json-format", help=COMMANDS["json-format"])
    _add_io(p)
    p.add_argument("--indent", type=int, default=2)
    p.add_argument("--sort", action="store_true")
    p.set_defaults(func=cmd_json_format)

    p = sub.add_parser("json-minify", help=COMMANDS["json-minify"])
    _add_io(p)
    p.set_defaults(func=cmd_json_minify)

    p = sub.add_parser("diff", help=COMMANDS["diff"])
    p.add_argument("a"); p.add_argument("b")
    p.add_argument("-o", "--output")
    p.set_defaults(func=cmd_diff)

    p = sub.add_parser("sort-lines", help=COMMANDS["sort-lines"])
    _add_io(p)
    p.add_argument("--reverse", action="store_true")
    p.add_argument("--ci", action="store_true", help="case-insensitive")
    p.add_argument("--unique", action="store_true")
    p.set_defaults(func=cmd_sort_lines)

    p = sub.add_parser("strip", help=COMMANDS["strip"])
    _add_io(p)
    p.add_argument("--whitespace", action="store_true")
    p.add_argument("--empty", action="store_true")
    p.set_defaults(func=cmd_strip)

    p = sub.add_parser("replace", help=COMMANDS["replace"])
    _add_io(p)
    p.add_argument("--find", required=True)
    p.add_argument("--replacement", required=True)
    p.set_defaults(func=cmd_replace)

    p = sub.add_parser("rot13", help=COMMANDS["rot13"])
    _add_io(p)
    p.set_defaults(func=cmd_rot13)

    p = sub.add_parser("normalize", help=COMMANDS["normalize"])
    _add_io(p)
    p.add_argument("--form", choices=["NFC", "NFD", "NFKC", "NFKD"], default="NFC")
    p.set_defaults(func=cmd_normalize)

    p = sub.add_parser("unicode-info", help=COMMANDS["unicode-info"])
    _add_io(p)
    p.add_argument("--limit", type=int, default=64)
    p.set_defaults(func=cmd_unicode_info)

    p = sub.add_parser("md-to-html", help=COMMANDS["md-to-html"])
    _add_io(p)
    p.set_defaults(func=cmd_md_to_html)

    p = sub.add_parser("html-to-md", help=COMMANDS["html-to-md"])
    _add_io(p)
    p.set_defaults(func=cmd_html_to_md)

    return parser


@tool_main("text")
def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 1
    return args.func(args) or 0


if __name__ == "__main__":
    raise SystemExit(main())
