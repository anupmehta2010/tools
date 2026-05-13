"""Generators: favicons, app icons, og-images, gitignore, sitemap, robots, readme."""
from __future__ import annotations

import argparse
import urllib.error
import urllib.request
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

from _common import lazy_import, ensure_dir


_FAVICON_SIZES = [16, 32, 48, 64, 128, 192, 512]

_IOS_SIZES = [
    ("Icon-20",     20), ("Icon-20@2x",  40), ("Icon-20@3x",  60),
    ("Icon-29",     29), ("Icon-29@2x",  58), ("Icon-29@3x",  87),
    ("Icon-40",     40), ("Icon-40@2x",  80), ("Icon-40@3x", 120),
    ("Icon-60@2x", 120), ("Icon-60@3x", 180),
    ("Icon-76",     76), ("Icon-76@2x", 152),
    ("Icon-83.5@2x", 167),
    ("Icon-1024",  1024),
]

_ANDROID_SIZES = [
    ("mipmap-mdpi",     48),
    ("mipmap-hdpi",     72),
    ("mipmap-xhdpi",    96),
    ("mipmap-xxhdpi",  144),
    ("mipmap-xxxhdpi", 192),
    ("playstore",      512),
]


def _open_image(path: str):
    PIL = lazy_import("PIL", "pip install Pillow")
    from PIL import Image
    return Image.open(path).convert("RGBA")


# ---- Favicon ----

def cmd_favicon(args):
    """Image -> favicon.ico + apple-touch-icon + multiple PNG sizes."""
    img = _open_image(args.input)
    out_dir = ensure_dir(Path(args.output or "favicon_out"))
    for size in _FAVICON_SIZES:
        resized = img.resize((size, size))
        resized.save(out_dir / f"favicon-{size}x{size}.png")
    apple = img.resize((180, 180))
    apple.save(out_dir / "apple-touch-icon.png")
    ico_sizes = [(s, s) for s in (16, 32, 48)]
    img.save(out_dir / "favicon.ico", format="ICO", sizes=ico_sizes)
    print(f"Wrote {len(_FAVICON_SIZES) + 2} files to {out_dir}/")


# ---- App icon ----

def cmd_app_icon(args):
    """Image -> iOS + Android icon set."""
    img = _open_image(args.input)
    out_dir = ensure_dir(Path(args.output or "appicon_out"))
    ios_dir = ensure_dir(out_dir / "ios")
    for name, size in _IOS_SIZES:
        img.resize((size, size)).save(ios_dir / f"{name}.png")
    and_root = ensure_dir(out_dir / "android")
    for folder, size in _ANDROID_SIZES:
        sub = ensure_dir(and_root / folder)
        img.resize((size, size)).save(sub / "ic_launcher.png")
    print(f"Wrote {len(_IOS_SIZES)} iOS + {len(_ANDROID_SIZES)} Android icons to {out_dir}/")


# ---- OG image ----

def cmd_og_image(args):
    """1200x630 OG image: text on solid bg."""
    PIL = lazy_import("PIL", "pip install Pillow")
    from PIL import Image, ImageDraw, ImageFont
    W, H = 1200, 630
    bg = args.bg_color
    if bg.startswith("#"):
        bg_rgb = tuple(int(bg.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    else:
        bg_rgb = (30, 41, 59)
    img = Image.new("RGB", (W, H), bg_rgb)
    draw = ImageDraw.Draw(img)
    font = None
    if args.font:
        try:
            font = ImageFont.truetype(args.font, args.font_size)
        except OSError:
            print(f"[!] Could not load font {args.font}, using default")
    if font is None:
        try:
            font = ImageFont.truetype("arial.ttf", args.font_size)
        except OSError:
            font = ImageFont.load_default()
    # wrap text
    words = args.text.split()
    lines, cur = [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        bbox = draw.textbbox((0, 0), trial, font=font)
        if bbox[2] - bbox[0] > W - 160 and cur:
            lines.append(cur); cur = w
        else:
            cur = trial
    if cur:
        lines.append(cur)
    line_h = (draw.textbbox((0, 0), "Ag", font=font)[3] -
              draw.textbbox((0, 0), "Ag", font=font)[1]) + 12
    total_h = line_h * len(lines)
    y = (H - total_h) // 2
    for ln in lines:
        bbox = draw.textbbox((0, 0), ln, font=font)
        w_px = bbox[2] - bbox[0]
        x = (W - w_px) // 2
        draw.text((x, y), ln, fill=(255, 255, 255), font=font)
        y += line_h
    out = args.output or "og-image.png"
    img.save(out)
    print(f"Wrote {out}")


# ---- gitignore ----

def cmd_gitignore(args):
    """Fetch a .gitignore template from github/gitignore."""
    cache_dir = Path.home() / ".cache" / "gen_tools_gitignore"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache = cache_dir / f"{args.language}.gitignore"
    if cache.exists() and not args.refresh:
        body = cache.read_text(encoding="utf-8")
    else:
        url = f"https://raw.githubusercontent.com/github/gitignore/main/{args.language.capitalize()}.gitignore"
        try:
            with urllib.request.urlopen(url, timeout=15) as r:
                body = r.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            print(f"[!] Could not fetch '{args.language}': {e}")
            print(f"    Tried {url}")
            return 1
        cache.write_text(body, encoding="utf-8")
    if args.output:
        Path(args.output).write_text(body, encoding="utf-8")
        print(f"Wrote {args.output}")
    else:
        print(body)


# ---- sitemap ----

def cmd_sitemap(args):
    """Dir of HTML files -> sitemap.xml."""
    root = Path(args.path)
    base = args.base_url.rstrip("/")
    urls = []
    for fp in root.rglob("*.html"):
        rel = fp.relative_to(root).as_posix()
        if rel.endswith("index.html"):
            rel = rel[: -len("index.html")]
        urls.append(f"{base}/{rel}".rstrip("/") or base + "/")
    out_lines = ['<?xml version="1.0" encoding="UTF-8"?>',
                 '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u in urls:
        out_lines.append(f"  <url><loc>{xml_escape(u)}</loc></url>")
    out_lines.append("</urlset>")
    xml = "\n".join(out_lines)
    out = args.output or "sitemap.xml"
    Path(out).write_text(xml, encoding="utf-8")
    print(f"Wrote {out} ({len(urls)} URLs)")


# ---- robots ----

def cmd_robots(args):
    """Generate robots.txt."""
    lines = [f"User-agent: {args.user_agent}"]
    for path in args.allow or []:
        lines.append(f"Allow: {path}")
    for path in args.disallow or []:
        lines.append(f"Disallow: {path}")
    if args.sitemap:
        lines.append("")
        lines.append(f"Sitemap: {args.sitemap}")
    body = "\n".join(lines) + "\n"
    out = args.output or "robots.txt"
    Path(out).write_text(body, encoding="utf-8")
    print(f"Wrote {out}")


# ---- README scaffold ----

_README_TEMPLATE = """# {title}

{description}

## Install

```bash
{install}
```

## Usage

```bash
{usage}
```

## License

{license}
"""


def cmd_readme(args):
    body = _README_TEMPLATE.format(
        title=args.title,
        description=args.description or "TODO: project description",
        install=args.install or "pip install <name>",
        usage=args.usage or "<name> --help",
        license=args.license or "MIT",
    )
    out = args.output or "README.md"
    Path(out).write_text(body, encoding="utf-8")
    print(f"Wrote {out}")


# ---- COMMANDS dict ----
COMMANDS = {
    "favicon":   "image -> favicon.ico + apple-touch + PNG sizes",
    "app-icon":  "image -> iOS + Android icon set",
    "og-image":  "1200x630 OG image with centered text",
    "gitignore": "fetch a .gitignore template from github/gitignore",
    "sitemap":   "dir of HTML files -> sitemap.xml",
    "robots":    "generate robots.txt",
    "readme":    "scaffold README.md",
}


def build_parser(parser=None):
    parser = parser or argparse.ArgumentParser(prog="gen_tools", description="Generators")
    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("favicon", help=COMMANDS["favicon"])
    p.add_argument("input")
    p.add_argument("-o", "--output")
    p.set_defaults(func=cmd_favicon)

    p = sub.add_parser("app-icon", help=COMMANDS["app-icon"])
    p.add_argument("input")
    p.add_argument("-o", "--output")
    p.set_defaults(func=cmd_app_icon)

    p = sub.add_parser("og-image", help=COMMANDS["og-image"])
    p.add_argument("text")
    p.add_argument("--bg-color", default="#1e293b")
    p.add_argument("--font")
    p.add_argument("--font-size", type=int, default=72)
    p.add_argument("-o", "--output")
    p.set_defaults(func=cmd_og_image)

    p = sub.add_parser("gitignore", help=COMMANDS["gitignore"])
    p.add_argument("language")
    p.add_argument("--refresh", action="store_true")
    p.add_argument("-o", "--output")
    p.set_defaults(func=cmd_gitignore)

    p = sub.add_parser("sitemap", help=COMMANDS["sitemap"])
    p.add_argument("path")
    p.add_argument("--base-url", required=True)
    p.add_argument("-o", "--output")
    p.set_defaults(func=cmd_sitemap)

    p = sub.add_parser("robots", help=COMMANDS["robots"])
    p.add_argument("--user-agent", default="*")
    p.add_argument("--allow", action="append")
    p.add_argument("--disallow", action="append")
    p.add_argument("--sitemap")
    p.add_argument("-o", "--output")
    p.set_defaults(func=cmd_robots)

    p = sub.add_parser("readme", help=COMMANDS["readme"])
    p.add_argument("title")
    p.add_argument("--description")
    p.add_argument("--install")
    p.add_argument("--usage")
    p.add_argument("--license")
    p.add_argument("-o", "--output")
    p.set_defaults(func=cmd_readme)

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
