"""PDF tools: merge, split, extract, md/img/html -> pdf, compress, encrypt, info."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from _common import lazy_import, tool_main


# ---- Merge / Split ----

def cmd_merge(args):
    pypdf = lazy_import("pypdf")
    writer = pypdf.PdfWriter()
    for src in args.inputs:
        reader = pypdf.PdfReader(src)
        for page in reader.pages:
            writer.add_page(page)
    with open(args.output, "wb") as f:
        writer.write(f)
    print(f"Merged {len(args.inputs)} PDFs -> {args.output}")


def cmd_split(args):
    pypdf = lazy_import("pypdf")
    reader = pypdf.PdfReader(args.input)
    out_dir = Path(args.outdir or Path(args.input).with_suffix(""))
    out_dir.mkdir(parents=True, exist_ok=True)
    for i, page in enumerate(reader.pages):
        writer = pypdf.PdfWriter()
        writer.add_page(page)
        outp = out_dir / f"page_{i + 1:04d}.pdf"
        with open(outp, "wb") as f:
            writer.write(f)
    print(f"Split {len(reader.pages)} pages -> {out_dir}/")


# ---- Extract ----

def cmd_extract_text(args):
    pypdf = lazy_import("pypdf")
    reader = pypdf.PdfReader(args.input)
    text = []
    for page in reader.pages:
        text.append(page.extract_text() or "")
    out = "\n\n".join(text)
    if args.output:
        Path(args.output).write_text(out, encoding="utf-8")
        print(f"Wrote text -> {args.output}")
    else:
        print(out)


def cmd_extract_images(args):
    pypdf = lazy_import("pypdf")
    reader = pypdf.PdfReader(args.input)
    out_dir = Path(args.outdir)
    out_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for page_num, page in enumerate(reader.pages, 1):
        for image_file in page.images:
            target = out_dir / f"p{page_num:03d}_{image_file.name}"
            target.write_bytes(image_file.data)
            count += 1
    print(f"Extracted {count} images -> {out_dir}/")


# ---- Info ----

def cmd_info(args):
    pypdf = lazy_import("pypdf")
    reader = pypdf.PdfReader(args.input)
    print(f"File:    {args.input}")
    print(f"Pages:   {len(reader.pages)}")
    print(f"Encrypted: {reader.is_encrypted}")
    md = reader.metadata or {}
    for k, v in md.items():
        print(f"  {k}: {v}")


# ---- Build PDF ----

def cmd_img2pdf(args):
    lazy_import("PIL", install_hint="pip install pillow")
    from PIL import Image
    images = [Image.open(p).convert("RGB") for p in args.inputs]
    if not images:
        print("No images.")
        return 1
    images[0].save(args.output, save_all=True, append_images=images[1:])
    print(f"Wrote {args.output}")


def cmd_md2pdf(args):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    try:
        from generate_build_guide_pdf import build_pdf
    except Exception as e:
        print(f"Could not import generate_build_guide_pdf: {e}")
        print("Make sure reportlab is installed: pip install reportlab")
        return 1
    build_pdf(Path(args.input), Path(args.output))
    print(f"Wrote {args.output}")


def cmd_html2pdf(args):
    lazy_import("xhtml2pdf", install_hint="pip install xhtml2pdf")
    from xhtml2pdf import pisa
    src = Path(args.input).read_text(encoding="utf-8")
    with open(args.output, "wb") as f:
        result = pisa.CreatePDF(src, dest=f)
    if result.err:
        print("Errors during conversion.")
        return 1
    print(f"Wrote {args.output}")


# ---- Compress ----

def cmd_compress(args):
    pypdf = lazy_import("pypdf")
    reader = pypdf.PdfReader(args.input)
    writer = pypdf.PdfWriter(clone_from=reader)
    for page in writer.pages:
        page.compress_content_streams()
    with open(args.output, "wb") as f:
        writer.write(f)
    src_size = Path(args.input).stat().st_size
    dst_size = Path(args.output).stat().st_size
    pct = 100 * (src_size - dst_size) / src_size if src_size else 0
    print(f"{src_size:,} -> {dst_size:,} bytes ({pct:.1f}% smaller)")


# ---- Encrypt / Decrypt ----

def cmd_encrypt(args):
    pypdf = lazy_import("pypdf")
    reader = pypdf.PdfReader(args.input)
    writer = pypdf.PdfWriter(clone_from=reader)
    writer.encrypt(user_password=args.password, owner_password=args.password)
    with open(args.output, "wb") as f:
        writer.write(f)
    print(f"Encrypted -> {args.output}")


def cmd_decrypt(args):
    pypdf = lazy_import("pypdf")
    reader = pypdf.PdfReader(args.input)
    if reader.is_encrypted:
        reader.decrypt(args.password)
    writer = pypdf.PdfWriter(clone_from=reader)
    with open(args.output, "wb") as f:
        writer.write(f)
    print(f"Decrypted -> {args.output}")


# ---- Pages: rotate / extract range ----

def cmd_watermark(args):
    pypdf = lazy_import("pypdf")
    lazy_import("reportlab", install_hint="pip install reportlab")
    from reportlab.pdfgen.canvas import Canvas
    from reportlab.lib.pagesizes import A4
    import io as _io
    buf = _io.BytesIO()
    c = Canvas(buf, pagesize=A4)
    c.setFillGray(0.7, alpha=0.35)
    c.setFont("Helvetica-Bold", args.size)
    c.translate(A4[0] / 2, A4[1] / 2)
    c.rotate(args.angle)
    c.drawCentredString(0, 0, args.text)
    c.save()
    buf.seek(0)
    wm_page = pypdf.PdfReader(buf).pages[0]
    reader = pypdf.PdfReader(args.input)
    writer = pypdf.PdfWriter()
    for page in reader.pages:
        page.merge_page(wm_page)
        writer.add_page(page)
    with open(args.output, "wb") as f:
        writer.write(f)
    print(f"Watermarked {len(reader.pages)} pages -> {args.output}")


def cmd_rotate_all(args):
    pypdf = lazy_import("pypdf")
    reader = pypdf.PdfReader(args.input)
    writer = pypdf.PdfWriter(clone_from=reader)
    for page in writer.pages:
        page.rotate(args.degrees)
    with open(args.output, "wb") as f:
        writer.write(f)
    print(f"Rotated {len(writer.pages)} pages by {args.degrees} deg -> {args.output}")


def cmd_to_images(args):
    fitz = lazy_import("fitz", install_hint="pip install pymupdf")
    doc = fitz.open(args.input)
    out_dir = Path(args.outdir)
    out_dir.mkdir(parents=True, exist_ok=True)
    fmt = args.format.lower()
    for i, page in enumerate(doc):
        pix = page.get_pixmap(dpi=args.dpi)
        pix.save(str(out_dir / f"page_{i + 1:04d}.{fmt}"))
    print(f"Wrote {len(doc)} page image(s) -> {out_dir}/")


def cmd_pages(args):
    pypdf = lazy_import("pypdf")
    reader = pypdf.PdfReader(args.input)
    n = len(reader.pages)
    indices = []
    for spec in args.ranges:
        if "-" in spec:
            a, b = spec.split("-", 1)
            a = int(a) if a else 1
            b = int(b) if b else n
            indices.extend(range(a - 1, b))
        else:
            indices.append(int(spec) - 1)
    writer = pypdf.PdfWriter()
    for i in indices:
        if 0 <= i < n:
            page = reader.pages[i]
            if args.rotate:
                page.rotate(args.rotate)
            writer.add_page(page)
    with open(args.output, "wb") as f:
        writer.write(f)
    print(f"Wrote {len(indices)} page(s) -> {args.output}")


COMMANDS = {
    "merge":          "merge multiple PDFs into one",
    "split":          "split a PDF into individual pages",
    "extract-text":   "extract text from a PDF",
    "extract-images": "extract embedded images",
    "info":           "show metadata and page count",
    "img2pdf":        "combine images into a PDF",
    "md2pdf":         "convert markdown to PDF",
    "html2pdf":       "convert HTML file to PDF",
    "compress":       "re-save PDF with content compression",
    "encrypt":        "encrypt a PDF with a password",
    "decrypt":        "decrypt a PDF with a password",
    "pages":          "extract page ranges (and optionally rotate)",
    "watermark":      "stamp diagonal text watermark on every page",
    "rotate-all":     "rotate every page by N degrees",
    "to-images":      "rasterize each page to PNG/JPG (needs pymupdf)",
}


def build_parser(parser=None):
    parser = parser or argparse.ArgumentParser(prog="pdf_tools", description="PDF utilities")
    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("merge", help=COMMANDS["merge"])
    p.add_argument("inputs", nargs="+")
    p.add_argument("-o", "--output", required=True)
    p.set_defaults(func=cmd_merge)

    p = sub.add_parser("split", help=COMMANDS["split"])
    p.add_argument("input")
    p.add_argument("-d", "--outdir")
    p.set_defaults(func=cmd_split)

    p = sub.add_parser("extract-text", help=COMMANDS["extract-text"])
    p.add_argument("input")
    p.add_argument("-o", "--output")
    p.set_defaults(func=cmd_extract_text)

    p = sub.add_parser("extract-images", help=COMMANDS["extract-images"])
    p.add_argument("input")
    p.add_argument("-d", "--outdir", required=True)
    p.set_defaults(func=cmd_extract_images)

    p = sub.add_parser("info", help=COMMANDS["info"])
    p.add_argument("input")
    p.set_defaults(func=cmd_info)

    p = sub.add_parser("img2pdf", help=COMMANDS["img2pdf"])
    p.add_argument("inputs", nargs="+")
    p.add_argument("-o", "--output", required=True)
    p.set_defaults(func=cmd_img2pdf)

    p = sub.add_parser("md2pdf", help=COMMANDS["md2pdf"])
    p.add_argument("input")
    p.add_argument("-o", "--output", required=True)
    p.set_defaults(func=cmd_md2pdf)

    p = sub.add_parser("html2pdf", help=COMMANDS["html2pdf"])
    p.add_argument("input")
    p.add_argument("-o", "--output", required=True)
    p.set_defaults(func=cmd_html2pdf)

    p = sub.add_parser("compress", help=COMMANDS["compress"])
    p.add_argument("input")
    p.add_argument("-o", "--output", required=True)
    p.set_defaults(func=cmd_compress)

    p = sub.add_parser("encrypt", help=COMMANDS["encrypt"])
    p.add_argument("input")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("-p", "--password", required=True)
    p.set_defaults(func=cmd_encrypt)

    p = sub.add_parser("decrypt", help=COMMANDS["decrypt"])
    p.add_argument("input")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("-p", "--password", required=True)
    p.set_defaults(func=cmd_decrypt)

    p = sub.add_parser("pages", help=COMMANDS["pages"])
    p.add_argument("input")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("ranges", nargs="+", help='e.g. 1 3-5 7- (1-based)')
    p.add_argument("--rotate", type=int, choices=[90, 180, 270])
    p.set_defaults(func=cmd_pages)

    p = sub.add_parser("watermark", help=COMMANDS["watermark"])
    p.add_argument("input")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--text", required=True)
    p.add_argument("--size", type=int, default=60)
    p.add_argument("--angle", type=float, default=45)
    p.set_defaults(func=cmd_watermark)

    p = sub.add_parser("rotate-all", help=COMMANDS["rotate-all"])
    p.add_argument("input")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--degrees", type=int, choices=[90, 180, 270], required=True)
    p.set_defaults(func=cmd_rotate_all)

    p = sub.add_parser("to-images", help=COMMANDS["to-images"])
    p.add_argument("input")
    p.add_argument("-d", "--outdir", required=True)
    p.add_argument("--format", choices=["png", "jpg"], default="png")
    p.add_argument("--dpi", type=int, default=144)
    p.set_defaults(func=cmd_to_images)

    return parser


@tool_main("pdf")
def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 1
    return args.func(args) or 0


if __name__ == "__main__":
    raise SystemExit(main())
