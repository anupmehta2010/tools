"""QR code tools: generate (PNG/SVG/ASCII) and decode."""
from __future__ import annotations

import argparse
from pathlib import Path

from _common import lazy_import


def cmd_generate(args):
    qrcode = lazy_import("qrcode", install_hint="pip install qrcode[pil]")
    qr = qrcode.QRCode(
        error_correction=getattr(qrcode.constants, f"ERROR_CORRECT_{args.error.upper()}"),
        box_size=args.box_size,
        border=args.border,
    )
    qr.add_data(args.text)
    qr.make(fit=True)

    if args.output:
        out = Path(args.output)
        ext = out.suffix.lower()
        if ext == ".svg":
            from qrcode.image.svg import SvgImage
            img = qr.make_image(image_factory=SvgImage)
            img.save(str(out))
        else:
            img = qr.make_image(fill_color=args.fg, back_color=args.bg)
            img.save(str(out))
        print(f"Wrote {out}")
    else:
        qr.print_ascii(invert=True)


def cmd_wifi(args):
    """Generate a WiFi credential QR (auto-connect on most phones)."""
    s = args.ssid.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
    p = (args.password or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
    payload = f"WIFI:T:{args.security};S:{s};P:{p};{'H:true;' if args.hidden else ''};"
    args.text = payload
    return cmd_generate(args)


def cmd_vcard(args):
    """Generate a vCard QR for a contact."""
    lines = ["BEGIN:VCARD", "VERSION:3.0", f"FN:{args.name}"]
    if args.org: lines.append(f"ORG:{args.org}")
    if args.title: lines.append(f"TITLE:{args.title}")
    if args.phone: lines.append(f"TEL:{args.phone}")
    if args.email: lines.append(f"EMAIL:{args.email}")
    if args.url: lines.append(f"URL:{args.url}")
    if args.address: lines.append(f"ADR:;;{args.address};;;;")
    lines.append("END:VCARD")
    args.text = "\r\n".join(lines)
    return cmd_generate(args)


def cmd_batch(args):
    """Generate one QR per line of an input text file."""
    qrcode = lazy_import("qrcode", install_hint="pip install qrcode[pil]")
    out_dir = Path(args.outdir)
    out_dir.mkdir(parents=True, exist_ok=True)
    lines = Path(args.input).read_text(encoding="utf-8").splitlines()
    n = 0
    for i, line in enumerate(lines, 1):
        line = line.strip()
        if not line:
            continue
        qr = qrcode.QRCode(box_size=args.box_size, border=args.border)
        qr.add_data(line)
        qr.make(fit=True)
        img = qr.make_image()
        img.save(str(out_dir / f"qr_{i:04d}.png"))
        n += 1
    print(f"Generated {n} QR codes -> {out_dir}/")


def cmd_decode(args):
    lazy_import("pyzbar", install_hint="pip install pyzbar pillow")
    lazy_import("PIL", install_hint="pip install pillow")
    from PIL import Image
    from pyzbar.pyzbar import decode

    img = Image.open(args.input)
    results = decode(img)
    if not results:
        print("No QR codes found.")
        return 1
    for r in results:
        print(f"[{r.type}] {r.data.decode('utf-8', errors='replace')}")


COMMANDS = {
    "gen":    "generate QR code (ASCII to terminal, or PNG/SVG file)",
    "decode": "decode QR codes from an image",
    "wifi":   "WiFi credential QR (SSID + password)",
    "vcard":  "vCard contact QR",
    "batch":  "generate one QR per line of an input file",
}


def build_parser(parser=None):
    parser = parser or argparse.ArgumentParser(prog="qr_tools", description="QR utilities")
    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("gen", help=COMMANDS["gen"])
    p.add_argument("text")
    p.add_argument("-o", "--output", help="image path (.png/.svg); omit for ASCII")
    p.add_argument("--box-size", type=int, default=10)
    p.add_argument("--border", type=int, default=4)
    p.add_argument("--error", choices=["l", "m", "q", "h"], default="m")
    p.add_argument("--fg", default="black")
    p.add_argument("--bg", default="white")
    p.set_defaults(func=cmd_generate)

    p = sub.add_parser("decode", help=COMMANDS["decode"])
    p.add_argument("input")
    p.set_defaults(func=cmd_decode)

    p = sub.add_parser("wifi", help=COMMANDS["wifi"])
    p.add_argument("ssid"); p.add_argument("--password")
    p.add_argument("--security", choices=["WPA", "WEP", "nopass"], default="WPA")
    p.add_argument("--hidden", action="store_true")
    p.add_argument("-o", "--output")
    p.add_argument("--box-size", type=int, default=10)
    p.add_argument("--border", type=int, default=4)
    p.add_argument("--error", choices=["l", "m", "q", "h"], default="m")
    p.add_argument("--fg", default="black")
    p.add_argument("--bg", default="white")
    p.set_defaults(func=cmd_wifi)

    p = sub.add_parser("vcard", help=COMMANDS["vcard"])
    p.add_argument("name")
    p.add_argument("--org"); p.add_argument("--title")
    p.add_argument("--phone"); p.add_argument("--email")
    p.add_argument("--url"); p.add_argument("--address")
    p.add_argument("-o", "--output")
    p.add_argument("--box-size", type=int, default=10)
    p.add_argument("--border", type=int, default=4)
    p.add_argument("--error", choices=["l", "m", "q", "h"], default="m")
    p.add_argument("--fg", default="black")
    p.add_argument("--bg", default="white")
    p.set_defaults(func=cmd_vcard)

    p = sub.add_parser("batch", help=COMMANDS["batch"])
    p.add_argument("input"); p.add_argument("-d", "--outdir", required=True)
    p.add_argument("--box-size", type=int, default=10)
    p.add_argument("--border", type=int, default=4)
    p.set_defaults(func=cmd_batch)

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
