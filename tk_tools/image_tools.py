"""Image tools: format convert, resize, compress, watermark, rotate, ASCII art, info."""
from __future__ import annotations

import argparse
from pathlib import Path

from _common import lazy_import, tool_main


def _open(p):
    lazy_import("PIL", install_hint="pip install pillow")
    from PIL import Image
    return Image.open(p)


def cmd_convert(args):
    img = _open(args.input)
    out = Path(args.output)
    fmt = (args.format or out.suffix.lstrip(".") or "png").upper()
    if fmt in ("JPG", "JPEG") and img.mode in ("RGBA", "P", "LA"):
        img = img.convert("RGB")
    save_kwargs = {}
    if args.quality is not None:
        save_kwargs["quality"] = args.quality
    img.save(out, format=fmt, **save_kwargs)
    print(f"{args.input} -> {out} ({fmt})")


def cmd_resize(args):
    from PIL import Image
    img = _open(args.input)
    w, h = img.size
    if args.width and args.height:
        new = (args.width, args.height)
    elif args.width:
        new = (args.width, max(1, int(h * args.width / w)))
    elif args.height:
        new = (max(1, int(w * args.height / h)), args.height)
    elif args.scale:
        new = (max(1, int(w * args.scale)), max(1, int(h * args.scale)))
    else:
        print("Specify --width, --height, or --scale")
        return 1
    out = img.resize(new, Image.LANCZOS)
    out.save(args.output)
    print(f"{img.size} -> {out.size} -> {args.output}")


def cmd_compress(args):
    img = _open(args.input)
    if img.mode in ("RGBA", "P", "LA"):
        img = img.convert("RGB")
    img.save(args.output, "JPEG", quality=args.quality, optimize=True)
    src = Path(args.input).stat().st_size
    dst = Path(args.output).stat().st_size
    pct = 100 * (src - dst) / src if src else 0
    print(f"{src:,} -> {dst:,} bytes ({pct:.1f}% smaller)")


def cmd_rotate(args):
    img = _open(args.input)
    out = img.rotate(-args.degrees, expand=True)
    out.save(args.output)
    print(f"Rotated {args.degrees} deg -> {args.output}")


def cmd_grayscale(args):
    img = _open(args.input).convert("L")
    img.save(args.output)
    print(f"Wrote {args.output}")


def cmd_thumbnail(args):
    img = _open(args.input)
    img.thumbnail((args.size, args.size))
    img.save(args.output)
    print(f"Thumbnail {img.size} -> {args.output}")


def cmd_watermark(args):
    from PIL import Image, ImageDraw, ImageFont
    img = _open(args.input).convert("RGBA")
    txt = Image.new("RGBA", img.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(txt)
    font = None
    for candidate in ("arial.ttf", "Arial.ttf", "DejaVuSans.ttf"):
        try:
            font = ImageFont.truetype(candidate, args.size)
            break
        except Exception:
            continue
    if font is None:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), args.text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    pos = {
        "top-left":     (10, 10),
        "top-right":    (img.width - tw - 10, 10),
        "bottom-left":  (10, img.height - th - 10),
        "bottom-right": (img.width - tw - 10, img.height - th - 10),
        "center":       ((img.width - tw) // 2, (img.height - th) // 2),
    }[args.position]
    color_map = {"white": (255, 255, 255), "black": (0, 0, 0), "red": (255, 0, 0)}
    rgb = color_map.get(args.color, (255, 255, 255))
    draw.text(pos, args.text, fill=(*rgb, args.opacity), font=font)
    out = Image.alpha_composite(img, txt).convert("RGB")
    out.save(args.output)
    print(f"Watermarked -> {args.output}")


def cmd_ascii(args):
    img = _open(args.input).convert("L")
    chars = " .:-=+*#%@"
    aspect = 0.55
    new_w = args.width
    new_h = max(1, int(img.height * new_w / img.width * aspect))
    img = img.resize((new_w, new_h))
    pixels = list(img.getdata())
    n = len(chars) - 1
    rows = []
    for r in range(new_h):
        row = pixels[r * new_w:(r + 1) * new_w]
        rows.append("".join(chars[int(p * n / 255)] for p in row))
    out = "\n".join(rows)
    if args.output:
        Path(args.output).write_text(out, encoding="utf-8")
        print(f"Wrote {args.output}")
    else:
        print(out)


def cmd_info(args):
    img = _open(args.input)
    print(f"File:   {args.input}")
    print(f"Size:   {img.width} x {img.height}")
    print(f"Mode:   {img.mode}")
    print(f"Format: {img.format}")
    if hasattr(img, "_getexif"):
        try:
            if img._getexif():
                print("EXIF:   present")
        except Exception:
            pass


def cmd_crop(args):
    img = _open(args.input)
    box = (args.x, args.y, args.x + args.width, args.y + args.height)
    out = img.crop(box)
    out.save(args.output)
    print(f"Cropped -> {args.output}")


def cmd_flip(args):
    from PIL import ImageOps
    img = _open(args.input)
    out = ImageOps.mirror(img) if args.axis == "h" else ImageOps.flip(img)
    out.save(args.output)
    print(f"Flipped ({args.axis}) -> {args.output}")


def cmd_ico(args):
    """Multi-size ICO favicon."""
    from PIL import Image
    img = _open(args.input).convert("RGBA")
    sizes = [(s, s) for s in args.sizes]
    img.save(args.output, sizes=sizes)
    print(f"Wrote ICO with sizes {args.sizes} -> {args.output}")


def cmd_exif_show(args):
    from PIL import Image
    from PIL.ExifTags import TAGS, GPSTAGS
    img = _open(args.input)
    exif = getattr(img, "_getexif", lambda: None)()
    if not exif:
        print("(no EXIF data)")
        return
    for tag_id, val in exif.items():
        name = TAGS.get(tag_id, tag_id)
        if name == "GPSInfo" and isinstance(val, dict):
            for gid, gv in val.items():
                gname = GPSTAGS.get(gid, gid)
                print(f"  GPS.{gname:<24} {gv}")
        else:
            text = repr(val) if isinstance(val, bytes) else str(val)
            if len(text) > 100:
                text = text[:97] + "..."
            print(f"  {str(name):<28} {text}")


def cmd_exif_strip(args):
    from PIL import Image
    img = _open(args.input)
    data = list(img.getdata())
    clean = Image.new(img.mode, img.size)
    clean.putdata(data)
    clean.save(args.output)
    print(f"Stripped EXIF -> {args.output}")


def cmd_palette(args):
    from PIL import Image
    img = _open(args.input).convert("RGB")
    pal = img.quantize(colors=args.colors)
    palette = pal.getpalette()[: args.colors * 3]
    counts = pal.getcolors() or []
    counts.sort(reverse=True)
    rows = []
    for cnt, idx in counts:
        if idx * 3 + 2 >= len(palette):
            continue
        r, g, b = palette[idx * 3], palette[idx * 3 + 1], palette[idx * 3 + 2]
        pct = 100 * cnt / (img.width * img.height)
        rows.append(f"  #{r:02X}{g:02X}{b:02X}  rgb({r:>3}, {g:>3}, {b:>3})  {pct:5.1f}%")
    print(f"Top {len(rows)} colors:")
    print("\n".join(rows))
    if args.output:
        # render a swatch image
        sw = 64
        canvas = Image.new("RGB", (sw * len(counts), sw))
        for i, (cnt, idx) in enumerate(counts):
            if idx * 3 + 2 >= len(palette):
                continue
            r, g, b = palette[idx * 3], palette[idx * 3 + 1], palette[idx * 3 + 2]
            for x in range(i * sw, (i + 1) * sw):
                for y in range(sw):
                    canvas.putpixel((x, y), (r, g, b))
        canvas.save(args.output)
        print(f"Wrote swatch -> {args.output}")


def cmd_collage(args):
    """Tile multiple images into a single grid."""
    from PIL import Image
    images = [Image.open(p).convert("RGB") for p in args.inputs]
    n = len(images)
    cols = args.cols or max(1, int(n ** 0.5))
    rows = (n + cols - 1) // cols
    cell_w, cell_h = args.cell, args.cell
    canvas = Image.new("RGB", (cols * cell_w, rows * cell_h), "white")
    for i, im in enumerate(images):
        im.thumbnail((cell_w, cell_h), Image.LANCZOS)
        x = (i % cols) * cell_w + (cell_w - im.width) // 2
        y = (i // cols) * cell_h + (cell_h - im.height) // 2
        canvas.paste(im, (x, y))
    canvas.save(args.output)
    print(f"Collage {cols}x{rows} -> {args.output}")


def cmd_invert(args):
    from PIL import ImageOps
    img = _open(args.input)
    if img.mode == "RGBA":
        r, g, b, a = img.split()
        rgb = ImageOps.invert(img.convert("RGB"))
        from PIL import Image
        out = Image.merge("RGBA", (*rgb.split(), a))
    else:
        out = ImageOps.invert(img.convert("RGB"))
    out.save(args.output)
    print(f"Inverted -> {args.output}")


COMMANDS = {
    "convert":   "convert image format (any -> any)",
    "resize":    "resize by width/height/scale",
    "compress":  "save as compressed JPEG",
    "rotate":    "rotate by degrees",
    "crop":      "crop a rectangle",
    "grayscale": "convert to grayscale",
    "thumbnail": "create square-bound thumbnail",
    "watermark": "add a text watermark",
    "ascii":     "render as ASCII art",
    "flip":      "flip horizontally or vertically",
    "invert":    "invert colors",
    "info":      "show image info",
    "ico":       "create multi-size favicon ICO",
    "exif-show": "show EXIF metadata",
    "exif-strip":"remove EXIF metadata",
    "palette":   "extract dominant colors (and optional swatch image)",
    "collage":   "tile multiple images into a grid",
}


def build_parser(parser=None):
    parser = parser or argparse.ArgumentParser(prog="image_tools", description="Image utilities")
    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("convert", help=COMMANDS["convert"])
    p.add_argument("input"); p.add_argument("output")
    p.add_argument("-f", "--format")
    p.add_argument("-q", "--quality", type=int)
    p.set_defaults(func=cmd_convert)

    p = sub.add_parser("resize", help=COMMANDS["resize"])
    p.add_argument("input"); p.add_argument("output")
    p.add_argument("--width", type=int)
    p.add_argument("--height", type=int)
    p.add_argument("--scale", type=float)
    p.set_defaults(func=cmd_resize)

    p = sub.add_parser("compress", help=COMMANDS["compress"])
    p.add_argument("input"); p.add_argument("output")
    p.add_argument("-q", "--quality", type=int, default=80)
    p.set_defaults(func=cmd_compress)

    p = sub.add_parser("rotate", help=COMMANDS["rotate"])
    p.add_argument("input"); p.add_argument("output")
    p.add_argument("--degrees", type=float, required=True)
    p.set_defaults(func=cmd_rotate)

    p = sub.add_parser("crop", help=COMMANDS["crop"])
    p.add_argument("input"); p.add_argument("output")
    p.add_argument("--x", type=int, required=True)
    p.add_argument("--y", type=int, required=True)
    p.add_argument("--width", type=int, required=True)
    p.add_argument("--height", type=int, required=True)
    p.set_defaults(func=cmd_crop)

    p = sub.add_parser("grayscale", help=COMMANDS["grayscale"])
    p.add_argument("input"); p.add_argument("output")
    p.set_defaults(func=cmd_grayscale)

    p = sub.add_parser("thumbnail", help=COMMANDS["thumbnail"])
    p.add_argument("input"); p.add_argument("output")
    p.add_argument("--size", type=int, default=256)
    p.set_defaults(func=cmd_thumbnail)

    p = sub.add_parser("watermark", help=COMMANDS["watermark"])
    p.add_argument("input"); p.add_argument("output")
    p.add_argument("--text", required=True)
    p.add_argument("--size", type=int, default=36)
    p.add_argument("--opacity", type=int, default=128)
    p.add_argument("--color", default="white", choices=["white", "black", "red"])
    p.add_argument("--position", default="bottom-right",
                   choices=["top-left", "top-right", "bottom-left", "bottom-right", "center"])
    p.set_defaults(func=cmd_watermark)

    p = sub.add_parser("ascii", help=COMMANDS["ascii"])
    p.add_argument("input")
    p.add_argument("-o", "--output")
    p.add_argument("--width", type=int, default=80)
    p.set_defaults(func=cmd_ascii)

    p = sub.add_parser("flip", help=COMMANDS["flip"])
    p.add_argument("input"); p.add_argument("output")
    p.add_argument("--axis", choices=["h", "v"], default="h")
    p.set_defaults(func=cmd_flip)

    p = sub.add_parser("invert", help=COMMANDS["invert"])
    p.add_argument("input"); p.add_argument("output")
    p.set_defaults(func=cmd_invert)

    p = sub.add_parser("info", help=COMMANDS["info"])
    p.add_argument("input")
    p.set_defaults(func=cmd_info)

    p = sub.add_parser("ico", help=COMMANDS["ico"])
    p.add_argument("input"); p.add_argument("output")
    p.add_argument("--sizes", type=int, nargs="+", default=[16, 32, 48, 64, 128, 256])
    p.set_defaults(func=cmd_ico)

    p = sub.add_parser("exif-show", help=COMMANDS["exif-show"])
    p.add_argument("input")
    p.set_defaults(func=cmd_exif_show)

    p = sub.add_parser("exif-strip", help=COMMANDS["exif-strip"])
    p.add_argument("input"); p.add_argument("output")
    p.set_defaults(func=cmd_exif_strip)

    p = sub.add_parser("palette", help=COMMANDS["palette"])
    p.add_argument("input")
    p.add_argument("-o", "--output")
    p.add_argument("--colors", type=int, default=8)
    p.set_defaults(func=cmd_palette)

    p = sub.add_parser("collage", help=COMMANDS["collage"])
    p.add_argument("inputs", nargs="+")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--cols", type=int)
    p.add_argument("--cell", type=int, default=200)
    p.set_defaults(func=cmd_collage)

    return parser


@tool_main("image")
def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 1
    return args.func(args) or 0


if __name__ == "__main__":
    raise SystemExit(main())
