"""Universal converter: detects extensions and routes to the right tool.

Usage:
    python tk.py convert auto INPUT OUTPUT      # auto-detect and convert
    python tk.py convert list                   # show every supported route
    python tk.py convert help INPUT             # what can I convert this to?
"""
from __future__ import annotations

import argparse
import importlib
from pathlib import Path

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))
from _common import tool_main

# Direct routing table.  (src_ext, dst_ext) -> (module, command, args_template)
ROUTES: dict[tuple[str, str], tuple[str, str, list[str]]] = {
    # PDF / docs
    ("pdf",  "txt"):   ("pdf_tools",  "extract-text",  ["{input}", "-o", "{output}"]),
    ("md",   "pdf"):   ("pdf_tools",  "md2pdf",        ["{input}", "-o", "{output}"]),
    ("html", "pdf"):   ("pdf_tools",  "html2pdf",      ["{input}", "-o", "{output}"]),
    # Data
    ("csv",  "json"):  ("data_tools", "csv2json",      ["{input}", "{output}"]),
    ("json", "csv"):   ("data_tools", "json2csv",      ["{input}", "{output}"]),
    ("csv",  "xlsx"):  ("data_tools", "csv2xlsx",      ["{input}", "{output}"]),
    ("xlsx", "csv"):   ("data_tools", "xlsx2csv",      ["{input}", "{output}"]),
    ("xlsx", "json"):  ("data_tools", "xlsx2json",     ["{input}", "{output}"]),
    ("json", "xlsx"):  ("data_tools", "json2xlsx",     ["{input}", "{output}"]),
    ("json", "yaml"):  ("data_tools", "json2yaml",     ["{input}", "{output}"]),
    ("yaml", "json"):  ("data_tools", "yaml2json",     ["{input}", "{output}"]),
    ("yml",  "json"):  ("data_tools", "yaml2json",     ["{input}", "{output}"]),
    ("xml",  "json"):  ("data_tools", "xml2json",      ["{input}", "{output}"]),
    ("toml", "json"):  ("data_tools", "toml2json",     ["{input}", "{output}"]),
    ("csv",  "md"):    ("data_tools", "markdown-table",["{input}", "{output}"]),
    # Markdown / HTML
    ("md",   "html"):  ("text_tools", "md-to-html",    ["{input}", "-o", "{output}"]),
    ("html", "md"):    ("text_tools", "html-to-md",    ["{input}", "-o", "{output}"]),
    # Encoding-style "files" (text-in/text-out)
    ("txt",  "b64"):   ("text_tools", "b64encode",     ["-i", "{input}", "-o", "{output}"]),
    ("b64",  "txt"):   ("text_tools", "b64decode",     ["-i", "{input}", "-o", "{output}"]),
}

IMAGE_EXTS = {"png", "jpg", "jpeg", "webp", "bmp", "gif", "tiff", "tif", "ico", "svg"}
AUDIO_EXTS = {"mp3", "wav", "flac", "ogg", "aac", "m4a", "wma", "opus"}
VIDEO_EXTS = {"mp4", "mkv", "mov", "avi", "webm", "flv", "wmv"}


def _run(mod_name: str, command: str, args_list: list[str]) -> int:
    mod = importlib.import_module(mod_name)
    return mod.main([command] + list(args_list)) or 0


def _route(s: str, d: str, src: str, dst: str) -> int | None:
    if (s, d) in ROUTES:
        mod_name, cmd, tmpl = ROUTES[(s, d)]
        cli_args = [t.format(input=src, output=dst) for t in tmpl]
        print(f"-> {mod_name} {cmd}")
        return _run(mod_name, cmd, cli_args)
    if s in IMAGE_EXTS and d in IMAGE_EXTS:
        print("-> image_tools convert")
        return _run("image_tools", "convert", [src, dst])
    if (s in AUDIO_EXTS | VIDEO_EXTS) and (d in AUDIO_EXTS | VIDEO_EXTS):
        print("-> media_tools convert")
        return _run("media_tools", "convert", [src, dst])
    if s in IMAGE_EXTS and d == "pdf":
        print("-> pdf_tools img2pdf")
        return _run("pdf_tools", "img2pdf", [src, "-o", dst])
    if s == "pdf" and d in IMAGE_EXTS:
        print("-> pdf_tools to-images")
        return _run("pdf_tools", "to-images", [src, "-d", "."])
    return None


def cmd_auto(args):
    src, dst = Path(args.input), Path(args.output)
    s = src.suffix.lstrip(".").lower()
    d = dst.suffix.lstrip(".").lower()
    if not s or not d:
        print("Both input and output need extensions to auto-detect.")
        return 1
    rc = _route(s, d, str(src), str(dst))
    if rc is None:
        print(f"No automatic converter from .{s} to .{d}.")
        print("Run `tk convert list` to see supported routes.")
        return 1
    return rc


def cmd_list(args):
    print("=== Direct converters (extension-driven) ===")
    for (s, d), (mod, cmd, _) in sorted(ROUTES.items()):
        print(f"  .{s:<6} -> .{d:<6}  via  {mod}.{cmd}")
    print()
    print("=== Auto-routed format families ===")
    print(f"  Images: {' '.join(sorted(IMAGE_EXTS))}")
    print(f"  Audio:  {' '.join(sorted(AUDIO_EXTS))}")
    print(f"  Video:  {' '.join(sorted(VIDEO_EXTS))}")
    print(f"  Cross:  image -> pdf, pdf -> image (rasterize)")
    print()
    print("Run: python tk.py convert auto INPUT OUTPUT")


def cmd_help(args):
    src = Path(args.input)
    s = src.suffix.lstrip(".").lower()
    if not s:
        print("Cannot infer format (no extension on input).")
        return 1
    print(f"Possible conversions for .{s}:")
    targets = []
    for (a, b), (mod, cmd, _) in sorted(ROUTES.items()):
        if a == s:
            targets.append((b, f"{mod}.{cmd}"))
    if s in IMAGE_EXTS:
        for ext in sorted(IMAGE_EXTS - {s}):
            targets.append((ext, "image_tools.convert"))
        targets.append(("pdf", "pdf_tools.img2pdf"))
    if s in AUDIO_EXTS | VIDEO_EXTS:
        for ext in sorted((AUDIO_EXTS | VIDEO_EXTS) - {s}):
            targets.append((ext, "media_tools.convert"))
    if s == "pdf":
        for ext in sorted(IMAGE_EXTS):
            targets.append((ext, "pdf_tools.to-images"))
    if not targets:
        print("  (none registered for this extension)")
        return 1
    for ext, via in targets:
        print(f"  -> .{ext:<6}  ({via})")


COMMANDS = {
    "auto": "auto-detect input/output extensions and convert",
    "list": "list every supported conversion route",
    "help": "show possible conversions for a given input file",
}


def build_parser(parser=None):
    parser = parser or argparse.ArgumentParser(prog="convert_tools",
                                               description="Universal converter")
    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("auto", help=COMMANDS["auto"])
    p.add_argument("input"); p.add_argument("output")
    p.set_defaults(func=cmd_auto)

    p = sub.add_parser("list", help=COMMANDS["list"])
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("help", help=COMMANDS["help"])
    p.add_argument("input")
    p.set_defaults(func=cmd_help)

    return parser


@tool_main("convert")
def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 1
    return args.func(args) or 0


if __name__ == "__main__":
    raise SystemExit(main())
