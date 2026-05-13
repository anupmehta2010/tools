"""Document conversion: pandoc wrappers, epub info, word counting."""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from _common import lazy_import


def _need_pandoc() -> bool:
    if shutil.which("pandoc"):
        return True
    print("[!] pandoc is not installed or not on PATH.")
    print("    Install: https://pandoc.org/installing.html")
    print("    Windows: choco install pandoc   |   macOS: brew install pandoc")
    return False


def _pandoc(input_path: str, output_path: str, extra: list[str] | None = None) -> int:
    if not _need_pandoc():
        return 2
    cmd = ["pandoc", input_path, "-o", output_path] + (extra or [])
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        print(f"[!] pandoc failed:\n{proc.stderr}")
        return proc.returncode
    print(f"Wrote {output_path}")
    return 0


# ---- Command implementations ----

def cmd_md2docx(args):
    return _pandoc(args.input, args.output or str(Path(args.input).with_suffix(".docx")))


def cmd_docx2md(args):
    return _pandoc(args.input, args.output or str(Path(args.input).with_suffix(".md")))


def cmd_md2html(args):
    out = args.output or str(Path(args.input).with_suffix(".html"))
    extra = ["--standalone"] if args.standalone else []
    return _pandoc(args.input, out, extra)


def cmd_html2md(args):
    return _pandoc(args.input, args.output or str(Path(args.input).with_suffix(".md")))


def cmd_md2epub(args):
    return _pandoc(args.input, args.output or str(Path(args.input).with_suffix(".epub")))


def cmd_docx2pdf(args):
    return _pandoc(args.input, args.output or str(Path(args.input).with_suffix(".pdf")))


def cmd_epub_info(args):
    """Read EPUB metadata via stdlib zipfile + xml."""
    path = Path(args.input)
    if not path.exists():
        print(f"[!] Not found: {path}")
        return 1
    ns = {
        "opf": "http://www.idpf.org/2007/opf",
        "dc":  "http://purl.org/dc/elements/1.1/",
        "cn":  "urn:oasis:names:tc:opendocument:xmlns:container",
    }
    with zipfile.ZipFile(path) as z:
        try:
            container = z.read("META-INF/container.xml").decode("utf-8")
        except KeyError:
            print("[!] Not a valid EPUB (no META-INF/container.xml)")
            return 1
        root = ET.fromstring(container)
        rootfile = root.find(".//cn:rootfile", ns)
        opf_path = rootfile.attrib["full-path"] if rootfile is not None else "OEBPS/content.opf"
        opf = z.read(opf_path).decode("utf-8")
        opf_root = ET.fromstring(opf)
        meta = opf_root.find("opf:metadata", ns)
        if meta is None:
            print("[!] No metadata block found")
            return 1
        for tag in ("title", "creator", "language", "publisher", "date", "identifier", "description"):
            el = meta.find(f"dc:{tag}", ns)
            if el is not None and el.text:
                print(f"{tag.capitalize():<12} {el.text.strip()}")
        manifest = opf_root.find("opf:manifest", ns)
        if manifest is not None:
            items = manifest.findall("opf:item", ns)
            print(f"{'Items:':<12} {len(items)}")


def cmd_wordcount(args):
    """Count words/chars/lines/paragraphs in md/docx/txt."""
    path = Path(args.input)
    ext = path.suffix.lower()
    if ext == ".docx":
        docx = lazy_import("docx", "pip install python-docx")
        doc = docx.Document(str(path))
        paragraphs = [p.text for p in doc.paragraphs]
        text = "\n".join(paragraphs)
    else:
        text = path.read_text(encoding="utf-8", errors="replace")
        paragraphs = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    words = len(text.split())
    chars = len(text)
    chars_no_ws = len(re.sub(r"\s", "", text))
    lines = len(text.splitlines())
    print(f"File:           {path.name}")
    print(f"Words:          {words}")
    print(f"Characters:     {chars}")
    print(f"Chars (no ws):  {chars_no_ws}")
    print(f"Lines:          {lines}")
    print(f"Paragraphs:     {len(paragraphs)}")


# ---- COMMANDS dict ----
COMMANDS = {
    "md2docx":   "Markdown -> DOCX (pandoc)",
    "docx2md":   "DOCX -> Markdown (pandoc)",
    "md2html":   "Markdown -> HTML (pandoc)",
    "html2md":   "HTML -> Markdown (pandoc)",
    "md2epub":   "Markdown -> EPUB (pandoc)",
    "docx2pdf":  "DOCX -> PDF (pandoc)",
    "epub-info": "show EPUB metadata",
    "wordcount": "count words/chars/lines/paragraphs",
}


def _add_io(p, with_standalone=False):
    p.add_argument("input")
    p.add_argument("-o", "--output")
    if with_standalone:
        p.add_argument("--standalone", action="store_true")


def build_parser(parser=None):
    parser = parser or argparse.ArgumentParser(prog="doc_tools", description="Document conversion")
    sub = parser.add_subparsers(dest="cmd")

    for name, fn in [
        ("md2docx", cmd_md2docx), ("docx2md", cmd_docx2md),
        ("html2md", cmd_html2md), ("md2epub", cmd_md2epub),
        ("docx2pdf", cmd_docx2pdf),
    ]:
        p = sub.add_parser(name, help=COMMANDS[name])
        _add_io(p)
        p.set_defaults(func=fn)

    p = sub.add_parser("md2html", help=COMMANDS["md2html"])
    _add_io(p, with_standalone=True)
    p.set_defaults(func=cmd_md2html)

    p = sub.add_parser("epub-info", help=COMMANDS["epub-info"])
    p.add_argument("input")
    p.set_defaults(func=cmd_epub_info)

    p = sub.add_parser("wordcount", help=COMMANDS["wordcount"])
    p.add_argument("input")
    p.set_defaults(func=cmd_wordcount)

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
