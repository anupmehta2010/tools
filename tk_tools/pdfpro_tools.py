"""Advanced PDF tools: ocr, redact, sign, table-extract, form fill/extract, compare, bookmarks, linearize, pages-reorder."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from _common import ensure_dir, lazy_import, tool_main


def cmd_ocr(args):
    if shutil.which("ocrmypdf"):
        cmd = ["ocrmypdf", "--force-ocr", "--language", args.language, args.input, args.output]
        r = subprocess.run(cmd, check=False, capture_output=True, text=True)
        print(r.stdout); print(r.stderr, file=sys.stderr)
        if r.returncode == 0:
            print(f"OCR -> {args.output}")
            return 0
        print("[!] ocrmypdf failed; falling back to pdf2image + pytesseract")
    pdf2image = lazy_import("pdf2image", install_hint="pip install pdf2image (also needs poppler)")
    pytesseract = lazy_import("pytesseract", install_hint="pip install pytesseract (also needs Tesseract OCR)")
    if shutil.which("tesseract") is None:
        print("[!] tesseract binary not found in PATH. https://github.com/tesseract-ocr/tesseract")
        return 2
    images = pdf2image.convert_from_path(args.input, dpi=args.dpi)
    out = Path(args.output)
    if out.suffix.lower() == ".pdf":
        # Build a searchable pdf by concatenating per-page pdfs from pytesseract
        page_pdfs = []
        for i, img in enumerate(images, 1):
            print(f"  OCR page {i}/{len(images)}")
            page_pdfs.append(pytesseract.image_to_pdf_or_hocr(img, extension="pdf", lang=args.language))
        # Merge with pypdf
        pypdf = lazy_import("pypdf", install_hint="pip install pypdf")
        writer = pypdf.PdfWriter()
        import io
        for pb in page_pdfs:
            reader = pypdf.PdfReader(io.BytesIO(pb))
            for page in reader.pages:
                writer.add_page(page)
        with open(out, "wb") as f:
            writer.write(f)
    else:
        text_parts = []
        for i, img in enumerate(images, 1):
            print(f"  OCR page {i}/{len(images)}")
            text_parts.append(pytesseract.image_to_string(img, lang=args.language))
        out.write_text("\n\n".join(text_parts), encoding="utf-8")
    print(f"OCR -> {out}")


def cmd_redact(args):
    fitz = lazy_import("fitz", install_hint="pip install pymupdf")
    doc = fitz.open(args.input)
    x, y, w, h = [float(v) for v in args.rect.split(",")]
    page = doc[args.page - 1]
    rect = fitz.Rect(x, y, x + w, y + h)
    page.add_redact_annot(rect, fill=(0, 0, 0))
    page.apply_redactions()
    doc.save(args.output)
    doc.close()
    print(f"Redacted {args.rect} on page {args.page} -> {args.output}")


def cmd_sign(args):
    lazy_import("PIL", install_hint="pip install pillow")
    try:
        import pyhanko  # noqa: F401
        from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
        from pyhanko.sign import signers
        # Cryptographic signing path
        if not args.cert:
            print("[!] --cert required for cryptographic sign with pyhanko; doing visible-stamp only")
            raise ImportError
        signer = signers.SimpleSigner.load_pkcs12(args.cert, passphrase=args.passphrase.encode() if args.passphrase else None)
        with open(args.input, "rb") as f:
            w = IncrementalPdfFileWriter(f)
            meta = signers.PdfSignatureMetadata(field_name="Signature1")
            with open(args.output, "wb") as outf:
                signers.sign_pdf(w, meta, signer=signer, output=outf)
        print(f"Cryptographically signed -> {args.output}")
        return 0
    except ImportError:
        pass
    # Fallback: stamp the signature image visibly with PyMuPDF
    fitz = lazy_import("fitz", install_hint="pip install pymupdf")
    doc = fitz.open(args.input)
    page = doc[args.page - 1]
    x, y = args.x, args.y
    rect = fitz.Rect(x, y, x + args.width, y + args.height)
    page.insert_image(rect, filename=args.signature)
    doc.save(args.output)
    doc.close()
    print(f"Stamped signature image -> {args.output}")


def cmd_table_extract(args):
    out_dir = ensure_dir(Path(args.output))
    # try camelot first
    try:
        camelot = __import__("camelot")
        tables = camelot.read_pdf(args.input, pages=args.pages, flavor=args.flavor)
        for i, t in enumerate(tables):
            csv = out_dir / f"table_{i:03d}.csv"
            t.to_csv(str(csv))
            print(f"  Wrote {csv}")
        print(f"{len(tables)} tables -> {out_dir}")
        return 0
    except ImportError:
        pass
    pdfplumber = lazy_import("pdfplumber", install_hint="pip install pdfplumber  (or: pip install camelot-py[base])")
    import csv as _csv
    n = 0
    with pdfplumber.open(args.input) as pdf:
        for pi, page in enumerate(pdf.pages, 1):
            for ti, table in enumerate(page.extract_tables() or []):
                fn = out_dir / f"page{pi:03d}_table{ti}.csv"
                with open(fn, "w", newline="", encoding="utf-8") as f:
                    w = _csv.writer(f)
                    for row in table:
                        w.writerow(row)
                print(f"  Wrote {fn}")
                n += 1
    print(f"{n} tables -> {out_dir}")


def cmd_forms_fill(args):
    pypdf = lazy_import("pypdf", install_hint="pip install pypdf")
    data = json.loads(Path(args.data).read_text(encoding="utf-8"))
    reader = pypdf.PdfReader(args.input)
    writer = pypdf.PdfWriter(clone_from=reader)
    for page in writer.pages:
        writer.update_page_form_field_values(page, data)
    with open(args.output, "wb") as f:
        writer.write(f)
    print(f"Filled {len(data)} fields -> {args.output}")


def cmd_forms_extract(args):
    pypdf = lazy_import("pypdf", install_hint="pip install pypdf")
    reader = pypdf.PdfReader(args.input)
    fields = reader.get_form_text_fields() or {}
    full = reader.get_fields() or {}
    out = {}
    for k, v in full.items():
        if isinstance(v, dict):
            out[k] = v.get("/V")
        else:
            out[k] = fields.get(k)
    text = json.dumps(out, indent=2, default=str)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"Wrote {args.output}")
    else:
        print(text)


def cmd_compare(args):
    pdf2image = lazy_import("pdf2image", install_hint="pip install pdf2image (also needs poppler)")
    lazy_import("PIL", install_hint="pip install pillow")
    from PIL import Image, ImageChops
    a_imgs = pdf2image.convert_from_path(args.a, dpi=args.dpi)
    b_imgs = pdf2image.convert_from_path(args.b, dpi=args.dpi)
    out_dir = ensure_dir(Path(args.output))
    n = max(len(a_imgs), len(b_imgs))
    diffs = 0
    for i in range(n):
        ai = a_imgs[i] if i < len(a_imgs) else Image.new("RGB", b_imgs[i].size, "white")
        bi = b_imgs[i] if i < len(b_imgs) else Image.new("RGB", a_imgs[i].size, "white")
        if ai.size != bi.size:
            bi = bi.resize(ai.size)
        d = ImageChops.difference(ai.convert("RGB"), bi.convert("RGB"))
        bbox = d.getbbox()
        if bbox:
            diffs += 1
            d.save(out_dir / f"diff_page{i + 1:03d}.png")
            # side-by-side
            cw = ai.width + bi.width + d.width + 20
            comp = Image.new("RGB", (cw, max(ai.height, bi.height, d.height)), "white")
            comp.paste(ai, (0, 0)); comp.paste(bi, (ai.width + 10, 0))
            comp.paste(d, (ai.width + bi.width + 20, 0))
            comp.save(out_dir / f"compare_page{i + 1:03d}.png")
    print(f"{diffs}/{n} pages differ -> {out_dir}")


def cmd_bookmark_list(args):
    pypdf = lazy_import("pypdf", install_hint="pip install pypdf")
    reader = pypdf.PdfReader(args.input)
    def walk(items, depth=0):
        for it in items:
            if isinstance(it, list):
                walk(it, depth + 1)
            else:
                try:
                    page = reader.get_destination_page_number(it) + 1
                except Exception:
                    page = "?"
                print("  " * depth + f"- [{page}] {it.title}")
    walk(reader.outline)


def cmd_bookmark_add(args):
    pypdf = lazy_import("pypdf", install_hint="pip install pypdf")
    reader = pypdf.PdfReader(args.input)
    writer = pypdf.PdfWriter(clone_from=reader)
    writer.add_outline_item(args.title, args.page - 1)
    with open(args.output, "wb") as f:
        writer.write(f)
    print(f"Added bookmark '{args.title}' at page {args.page} -> {args.output}")


def cmd_linearize(args):
    if shutil.which("qpdf") is None:
        print("[!] qpdf not found in PATH. https://github.com/qpdf/qpdf")
        return 2
    cmd = ["qpdf", "--linearize", args.input, args.output]
    r = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if r.returncode == 0:
        print(f"Linearized -> {args.output}")
    else:
        print(r.stderr or r.stdout)
    return r.returncode


def cmd_pages_reorder(args):
    pypdf = lazy_import("pypdf", install_hint="pip install pypdf")
    reader = pypdf.PdfReader(args.input)
    order = [int(x) for x in args.order.split(",")]
    writer = pypdf.PdfWriter()
    for idx in order:
        writer.add_page(reader.pages[idx - 1])
    with open(args.output, "wb") as f:
        writer.write(f)
    print(f"Reordered to {order} -> {args.output}")


COMMANDS = {
    "ocr":            "OCR a PDF (ocrmypdf preferred, fallback pdf2image+pytesseract)",
    "redact":         "Black out a rectangle on a page (PyMuPDF)",
    "sign":           "Visible signature stamp (and crypto sign via pyhanko if available)",
    "table-extract":  "Extract tables to CSV (camelot or pdfplumber)",
    "forms-fill":     "Fill PDF form fields from JSON",
    "forms-extract":  "Read PDF form fields to JSON",
    "compare":        "Render and diff two PDFs page-by-page",
    "bookmark-list":  "List outline/bookmarks",
    "bookmark-add":   "Add a bookmark at a page",
    "linearize":      "Web-optimize via qpdf",
    "pages-reorder":  "Reorder pages by 1-based comma list",
}


def build_parser(parser=None):
    parser = parser or argparse.ArgumentParser(prog="pdfpro_tools", description="Advanced PDF tools")
    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("ocr", help=COMMANDS["ocr"])
    p.add_argument("input"); p.add_argument("output")
    p.add_argument("--language", default="eng")
    p.add_argument("--dpi", type=int, default=300)
    p.set_defaults(func=cmd_ocr)

    p = sub.add_parser("redact", help=COMMANDS["redact"])
    p.add_argument("input"); p.add_argument("output")
    p.add_argument("--page", type=int, required=True)
    p.add_argument("--rect", required=True, help="x,y,w,h in points")
    p.set_defaults(func=cmd_redact)

    p = sub.add_parser("sign", help=COMMANDS["sign"])
    p.add_argument("input"); p.add_argument("output")
    p.add_argument("--signature", required=True, help="signature image path")
    p.add_argument("--page", type=int, default=1)
    p.add_argument("--x", type=float, default=400)
    p.add_argument("--y", type=float, default=700)
    p.add_argument("--width", type=float, default=150)
    p.add_argument("--height", type=float, default=50)
    p.add_argument("--cert", help="PKCS12 (.p12) cert for cryptographic sign")
    p.add_argument("--passphrase")
    p.set_defaults(func=cmd_sign)

    p = sub.add_parser("table-extract", help=COMMANDS["table-extract"])
    p.add_argument("input"); p.add_argument("-o", "--output", default="tables_out")
    p.add_argument("--pages", default="all")
    p.add_argument("--flavor", default="lattice", choices=["lattice", "stream"])
    p.set_defaults(func=cmd_table_extract)

    p = sub.add_parser("forms-fill", help=COMMANDS["forms-fill"])
    p.add_argument("input"); p.add_argument("output")
    p.add_argument("--data", required=True, help="JSON file with {field: value}")
    p.set_defaults(func=cmd_forms_fill)

    p = sub.add_parser("forms-extract", help=COMMANDS["forms-extract"])
    p.add_argument("input"); p.add_argument("-o", "--output")
    p.set_defaults(func=cmd_forms_extract)

    p = sub.add_parser("compare", help=COMMANDS["compare"])
    p.add_argument("a"); p.add_argument("b")
    p.add_argument("-o", "--output", default="pdf_diff_out")
    p.add_argument("--dpi", type=int, default=150)
    p.set_defaults(func=cmd_compare)

    p = sub.add_parser("bookmark-list", help=COMMANDS["bookmark-list"])
    p.add_argument("input")
    p.set_defaults(func=cmd_bookmark_list)

    p = sub.add_parser("bookmark-add", help=COMMANDS["bookmark-add"])
    p.add_argument("input"); p.add_argument("output")
    p.add_argument("--title", required=True)
    p.add_argument("--page", type=int, required=True)
    p.set_defaults(func=cmd_bookmark_add)

    p = sub.add_parser("linearize", help=COMMANDS["linearize"])
    p.add_argument("input"); p.add_argument("output")
    p.set_defaults(func=cmd_linearize)

    p = sub.add_parser("pages-reorder", help=COMMANDS["pages-reorder"])
    p.add_argument("input"); p.add_argument("output")
    p.add_argument("--order", required=True, help="e.g. 3,1,2,4")
    p.set_defaults(func=cmd_pages_reorder)

    return parser


@tool_main("pdf-pro")
def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 1
    return args.func(args) or 0


if __name__ == "__main__":
    raise SystemExit(main())
