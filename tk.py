"""tk - Personal Toolkit. All-in-one CLI launcher (and web UI).

Usage:
    python tk.py                         # interactive menu
    python tk.py ui                      # launch the web UI in a browser
    python tk.py list                    # list every command across all categories
    python tk.py <category>              # show category subcommands
    python tk.py <category> <cmd> ...    # run a command

Categories:
    pdf      PDF: merge, split, extract, md/img/html -> pdf, compress, encrypt
    image    Images: convert formats, resize, compress, watermark, ASCII, ...
    media    Audio/Video (ffmpeg): convert, extract audio, trim, GIF, thumbnail
    text     Encoding (b64/url/hex/html), hashes, case, JSON format, diff, ...
    data     CSV/JSON/Excel/YAML/XML/TOML conversions
    archive  ZIP/TAR/auto-extract
    crypto   Passwords, UUID, file hash, JWT decode, Fernet encrypt/decrypt
    net      HTTP, download, DNS, ping, port-scan, my-ip, whois, URL check
    fs       Bulk rename, dedupe, search, disk usage, sysinfo, tree
    dev      Regex, color, lorem, base, calc, timestamp, slug, curl-to-Python
    qr       QR codes: generate (PNG/SVG/ASCII) and decode
    oled     OLED & embedded: image/video -> C arrays, BMP, optimize for tiny screens

Each tool also runs standalone: `python pdf_tools.py merge a.pdf b.pdf -o c.pdf`.
"""
from __future__ import annotations

import importlib
import shlex
import sys
from pathlib import Path

# Make local module imports work regardless of CWD.
sys.path.insert(0, str(Path(__file__).parent))

# UTF-8 console on Windows so box chars / arrows render.
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


CATEGORIES: dict[str, tuple[str, str]] = {
    "pdf":     ("pdf_tools",     "PDF: merge, split, extract, md/img/html->pdf, compress"),
    "image":   ("image_tools",   "Image: convert, resize, compress, watermark, ASCII art"),
    "media":   ("media_tools",   "Audio/Video via ffmpeg: convert, trim, GIF, thumbnail"),
    "text":    ("text_tools",    "Encoding, hashes, case conversion, JSON format, diff"),
    "data":    ("data_tools",    "CSV/JSON/Excel/YAML/XML/TOML conversions"),
    "archive": ("archive_tools", "Archives: zip/tar create + extract"),
    "crypto":  ("crypto_tools",  "Passwords, UUIDs, file hash, JWT, Fernet encrypt"),
    "net":     ("net_tools",     "HTTP, DNS, ping, port-scan, download, my-ip, whois"),
    "fs":      ("fs_tools",      "Bulk rename, dedupe, search, disk usage, sysinfo"),
    "dev":     ("dev_tools",     "Regex, color, lorem, base, calc, timestamp, slug"),
    "qr":      ("qr_tools",      "QR codes: generate and decode"),
    "oled":    ("oled_tools",    "OLED & embedded: img/video -> C arrays, BMP, opt"),
    "convert": ("convert_tools", "Universal converter: auto-route by file extension"),
}


def _load(module_name: str):
    return importlib.import_module(module_name)


def run_category(category: str, argv: list[str]) -> int:
    mod_name, _ = CATEGORIES[category]
    mod = _load(mod_name)
    if hasattr(mod, "main"):
        return mod.main(argv) or 0
    print(f"Module {mod_name} has no main() entry.")
    return 1


def list_all() -> None:
    print()
    for cat, (mod_name, desc) in CATEGORIES.items():
        print(f"[{cat}] {desc}  ({mod_name}.py)")
        try:
            mod = _load(mod_name)
            if hasattr(mod, "COMMANDS"):
                for name, info in mod.COMMANDS.items():
                    cmd_desc = info if isinstance(info, str) else (info[1] if len(info) > 1 else "")
                    print(f"    {name:<16s} {cmd_desc}")
        except Exception as e:
            print(f"    (could not load: {e})")
        print()


def menu() -> int:
    print()
    print("==========================================================")
    print("   tk -- Personal Toolkit                                 ")
    print("==========================================================")
    keys = list(CATEGORIES.keys())

    while True:
        print()
        for i, key in enumerate(keys, 1):
            _, desc = CATEGORIES[key]
            print(f"  {i:2d}. {key:<8s}  {desc}")
        print("   l. List every available command")
        print("   u. Launch web UI (browser)")
        print("   q. Quit")
        print()
        try:
            sel = input("Category: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if sel in ("q", "quit", "exit", ""):
            return 0
        if sel in ("l", "list"):
            list_all()
            continue
        if sel in ("u", "ui", "web"):
            import server
            return server.main([])
        if sel.isdigit() and 1 <= int(sel) <= len(keys):
            cat = keys[int(sel) - 1]
        elif sel in keys:
            cat = sel
        else:
            print(f"  Unknown: {sel!r}")
            continue

        try:
            cmd_str = input(f"  $ {cat} ").strip()
        except (EOFError, KeyboardInterrupt):
            return 0

        argv = shlex.split(cmd_str) if cmd_str else ["--help"]
        try:
            run_category(cat, argv)
        except SystemExit:
            pass
        except KeyboardInterrupt:
            print("  (interrupted)")
        except Exception as e:
            print(f"  Error: {e}")


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        return menu()
    if argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        list_all()
        return 0
    if argv[0] == "list":
        list_all()
        return 0
    if argv[0] in ("ui", "web", "server"):
        import server
        return server.main(argv[1:])
    cat = argv[0]
    if cat not in CATEGORIES:
        print(f"Unknown category: {cat}")
        print(f"Categories: {', '.join(CATEGORIES)}")
        return 1
    return run_category(cat, argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
