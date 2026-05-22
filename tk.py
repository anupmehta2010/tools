"""tk -- Personal Toolkit. All-in-one CLI launcher and web UI.

Usage:
    python tk.py                         # interactive menu
    python tk.py ui                      # launch the web UI in a browser
    python tk.py list                    # list every command across all categories
    python tk.py <category>              # show category subcommands
    python tk.py <category> <cmd> ...    # run a command

Meta commands:
    tk doctor                            # check optional deps and external tools
    tk history                           # show recent runs
    tk preset save NAME <cat> <cmd> ...  # save a command preset
    tk preset list                       # list saved presets
    tk preset run  NAME                  # re-run a saved preset
    tk preset delete NAME                # delete a preset
    tk pipe <cat:cmd args> >> <cat:cmd args> >> ...   # chain tools (workspace-relative)
    tk plugins                           # list discovered plugins
    tk version                           # print version

Built-in categories: pdf, image, media, text, data, archive, crypto, net, fs,
dev, qr, oled, convert, ai, doc, code, gen, time, finance, db, image-pro,
audio-pro, video-pro, pdf-pro, geo, steg, net-pro, crypto-pro, forensic,
embedded, ml, 3d.
"""
from __future__ import annotations

import importlib
import json
import shlex
import sys
import time
from pathlib import Path

# Local-module imports work regardless of CWD.
sys.path.insert(0, str(Path(__file__).parent))

# UTF-8 console on Windows.
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


__version__ = "0.3.2"


# Built-in categories. Keys are stable URL/CLI slugs; values describe + map.
CATEGORIES: dict[str, tuple[str, str, str]] = {
    # key:         (module,             label / desc,                                 icon)
    "pdf":         ("tk_tools.pdf_tools",        "PDF: merge, split, extract, md/img/html->pdf, compress", "📄"),
    "image":       ("tk_tools.image_tools",      "Image: convert, resize, compress, watermark, ASCII art", "🖼️"),
    "media":       ("tk_tools.media_tools",      "Audio/Video via ffmpeg: convert, trim, GIF, thumbnail",  "🎬"),
    "text":        ("tk_tools.text_tools",       "Encoding, hashes, case conversion, JSON format, diff",   "✍️"),
    "data":        ("tk_tools.data_tools",       "CSV/JSON/Excel/YAML/XML/TOML conversions",               "📊"),
    "archive":     ("tk_tools.archive_tools",    "Archives: zip/tar create + extract",                     "📦"),
    "crypto":      ("tk_tools.crypto_tools",     "Passwords, UUIDs, file hash, JWT, Fernet encrypt",       "🔐"),
    "net":         ("tk_tools.net_tools",        "HTTP, DNS, ping, port-scan, download, my-ip, whois",     "🌐"),
    "dl":          ("tk_tools.dl_tools",         "Download video/audio/any URL via yt-dlp (YouTube +1800)", "⬇️"),
    "fs":          ("tk_tools.fs_tools",         "Bulk rename, dedupe, search, disk usage, sysinfo",       "📁"),
    "dev":         ("tk_tools.dev_tools",        "Regex, color, lorem, base, calc, timestamp, slug",       "⚙️"),
    "qr":          ("tk_tools.qr_tools",         "QR codes: generate and decode",                          "📱"),
    "oled":        ("tk_tools.oled_tools",       "OLED & embedded: img/video -> C arrays, BMP, opt",       "💡"),
    "convert":     ("tk_tools.convert_tools",    "Universal converter: auto-route by file extension",      "🔄"),
    # New advanced categories (added in v0.2)
    "ai":          ("tk_tools.ai_tools",         "Local AI: summarize, chat (ollama), STT, TTS, rembg, embed", "🤖"),
    "doc":         ("tk_tools.doc_tools",        "Documents: md/docx/html/pdf/epub conversions (pandoc)",  "📝"),
    "code":        ("tk_tools.code_tools",       "Code: format, sloc, complexity, secrets-scan, deps",     "</>"),
    "gen":         ("tk_tools.gen_tools",        "Generators: favicon, app-icon, og-image, gitignore, sitemap, readme", "✨"),
    "time":        ("tk_tools.time_tools",       "Time: tz convert, cron explain, ics gen, duration calc", "⏱️"),
    "finance":     ("tk_tools.finance_tools",    "Finance: currency convert, invoice, tax, loan, compound", "💰"),
    "db":          ("tk_tools.db_tools",         "SQLite: query, csv import/export, schema, vacuum",        "🗃️"),
    "image-pro":   ("tk_tools.imagepro_tools",   "Image-pro: rembg, EXIF, palette, smart-crop, upscale, panorama, HDR", "🎨"),
    "audio-pro":   ("tk_tools.audiopro_tools",   "Audio-pro: normalize, denoise, BPM, spectrogram, stems",  "🎚️"),
    "video-pro":   ("tk_tools.videopro_tools",   "Video-pro: scene split, subtitle burn/auto, stabilize",   "🎞️"),
    "pdf-pro":     ("tk_tools.pdfpro_tools",     "PDF-pro: OCR, redact, sign, tables, forms, compare",      "📑"),
    "geo":         ("tk_tools.geo_tools",        "Geo: gpx/kml, distance, geocode, exif-gps, bbox",         "🗺️"),
    "steg":        ("tk_tools.steg_tools",       "Steganography: LSB image/audio embed/extract",            "🕵️"),
    "net-pro":     ("tk_tools.netpro_tools",     "Net-pro: SSL, headers, JWT verify, HAR, traceroute, speedtest", "🛰️"),
    "crypto-pro":  ("tk_tools.cryptopro_tools",  "Crypto-pro: age, GPG, SSH keygen, BIP39, ECDSA, X.509, TOTP", "🔏"),
    "forensic":    ("tk_tools.forensic_tools",   "Forensic: magic, entropy, strings, hexdump, carve, PE",   "🔬"),
    "embedded":    ("tk_tools.embedded_tools",   "Embedded: hex, intel-hex, bin↔C, font→bmp, serial, CRC",  "🔌"),
    "ml":          ("tk_tools.ml_tools",         "ML: ONNX run, classify, embed, tokenize, vector search", "🧠"),
    "3d":          ("tk_tools.threed_tools",     "3D: obj/stl/ply, gcode info, decimate, voxelize, bbox",   "🧊"),
    "completions": ("tk_tools.completions_tools", "Shell completions: bash, zsh, pwsh, fish", "📜"),
    "watch":       ("tk_tools.watch_tools",      "Folder watcher: trigger a tool on new/changed files",     "👁️"),
    "recipes":     ("tk_tools.recipes_tools",    "Recipes: save and run multi-step JSON pipelines",         "🧬"),
    "bundle":      ("tk_tools.bundle_tools",     "Bundle: build single-file .pyz / zip / native binary",    "📦"),
}


# ---------------------------------------------------------------- module loading

def _load(module_name: str):
    return importlib.import_module(module_name)


def available_categories() -> dict[str, tuple[str, str, str]]:
    """Built-in + plugin categories, merged."""
    from _common import discover_plugins
    out = dict(CATEGORIES)
    for key, info in discover_plugins().items():
        if key not in out:
            out[key] = (info["module"], info["label"], info["icon"])
    return out


def run_category(category: str, argv: list[str]) -> int:
    cats = available_categories()
    if category not in cats:
        print(f"Unknown category: {category}")
        print(f"Categories: {', '.join(cats)}")
        return 1
    mod_name, _, _ = cats[category]
    try:
        mod = _load(mod_name)
    except Exception as e:
        print(f"Could not import module '{mod_name}': {e}")
        return 1
    if not hasattr(mod, "main"):
        print(f"Module {mod_name} has no main() entry.")
        return 1

    # Run + log to history.
    from _common import load_config, log_run
    cfg = load_config()
    cmd = argv[0] if argv else ""
    t0 = time.time()
    try:
        rc = mod.main(argv) or 0
    except SystemExit as e:
        rc = e.code if isinstance(e.code, int) else 1
    except KeyboardInterrupt:
        rc = 130
    except Exception as e:
        print(f"Error: {e}")
        rc = 1
    dt = int((time.time() - t0) * 1000)
    if cfg.get("history_enabled", True):
        try:
            log_run(category, cmd, argv[1:], rc, dt)
        except Exception:
            pass
    return rc


def list_all(as_json: bool = False) -> None:
    cats = available_categories()
    if as_json:
        out = []
        for key, (mod_name, desc, icon) in cats.items():
            cmds = []
            try:
                mod = _load(mod_name)
                if hasattr(mod, "COMMANDS"):
                    for n, info in mod.COMMANDS.items():
                        cmds.append({"name": n, "help": info if isinstance(info, str) else ""})
            except Exception:
                pass
            out.append({"key": key, "module": mod_name, "label": desc, "icon": icon, "commands": cmds})
        print(json.dumps({"categories": out}, indent=2))
        return

    print()
    for cat, (mod_name, desc, icon) in cats.items():
        print(f"{icon}  [{cat}] {desc}  ({mod_name}.py)")
        try:
            mod = _load(mod_name)
            if hasattr(mod, "COMMANDS"):
                for name, info in mod.COMMANDS.items():
                    cmd_desc = info if isinstance(info, str) else (info[1] if len(info) > 1 else "")
                    print(f"    {name:<20s} {cmd_desc}")
        except Exception as e:
            print(f"    (could not load: {e})")
        print()


# ---------------------------------------------------------------- meta: doctor

def cmd_doctor() -> int:
    from _common import CONFIG_FILE, HISTORY_DB, HOME_DIR, have_binary, have_module
    print()
    print("tk doctor — environment check")
    print("=" * 50)
    print(f"Python:           {sys.version.split()[0]}  ({sys.executable})")
    print(f"Platform:         {sys.platform}")
    print(f"tk home:          {HOME_DIR}")
    print(f"  config:         {CONFIG_FILE.exists()}  ({CONFIG_FILE})")
    print(f"  history db:     {HISTORY_DB.exists()}  ({HISTORY_DB})")
    print()

    py_mods = [
        ("pypdf", "PDF reading/writing"),
        ("PIL", "Pillow — image processing"),
        ("reportlab", "PDF generation"),
        ("markdown", "Markdown → HTML"),
        ("openpyxl", "Excel files"),
        ("yaml", "PyYAML — YAML"),
        ("tomli", "TOML reader (py<3.11)"),
        ("cryptography", "Fernet, X.509, signing"),
        ("requests", "Optional HTTP"),
        ("dns", "dnspython — DNS"),
        ("jwt", "PyJWT — JWT verify/sign"),
        ("qrcode", "QR generation"),
        ("pyzbar", "QR decode"),
        ("librosa", "Audio analysis"),
        ("rembg", "Background removal"),
        ("cv2", "OpenCV — image/video pro"),
        ("onnxruntime", "ONNX inference"),
        ("sentence_transformers", "Text embeddings"),
        ("faster_whisper", "Speech-to-text"),
        ("serial", "pyserial — serial port"),
        ("croniter", "Cron next-fire"),
        ("dateutil", "Date parsing"),
        ("camelot", "PDF table extract"),
        ("ocrmypdf", "PDF OCR"),
        ("pytesseract", "Tesseract wrapper"),
    ]
    bins = ["ffmpeg", "ffprobe", "pandoc", "tesseract", "gpg", "age", "qpdf"]

    print("Optional Python modules:")
    for mod, desc in py_mods:
        mark = "✔" if have_module(mod) else "·"
        print(f"  {mark}  {mod:<25s} {desc}")
    print()
    print("Optional external binaries:")
    for b in bins:
        mark = "✔" if have_binary(b) else "·"
        print(f"  {mark}  {b}")
    print()
    print("(✔ = installed, · = missing — install only what you need.)")
    return 0


# ---------------------------------------------------------------- meta: history

def cmd_history(limit: int, as_json: bool) -> int:
    from _common import recent_runs
    rows = recent_runs(limit)
    if as_json:
        print(json.dumps(rows, indent=2))
        return 0
    if not rows:
        print("No runs logged yet.")
        return 0
    print(f"{'#':>4}  {'when':<20s}  {'cat':<10s}  {'cmd':<14s}  rc  ms     args")
    print("-" * 110)
    for r in rows:
        t = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(r["ts"]))
        args = " ".join(r["args"])[:60]
        print(f"{r['id']:>4}  {t:<20s}  {r['category']:<10s}  {r['command']:<14s}  "
              f"{r['rc']:>2d}  {r['duration_ms']:>5d}  {args}")
    return 0


# ---------------------------------------------------------------- meta: preset

def cmd_preset(argv: list[str]) -> int:
    from _common import preset_delete, preset_list, preset_load, preset_save
    if not argv:
        print("Usage: tk preset save|list|run|delete|show ...")
        return 1
    op = argv[0]
    if op == "save":
        # tk preset save NAME <cat> <cmd> [args...]
        if len(argv) < 4:
            print("Usage: tk preset save NAME <category> <command> [args...]")
            return 1
        name, cat, cmd, *rest = argv[1:]
        path = preset_save(name, cat, cmd, rest)
        print(f"Saved preset '{name}' -> {path}")
        return 0
    if op == "list":
        rows = preset_list()
        if not rows:
            print("No presets saved.")
            return 0
        for r in rows:
            args = " ".join(r["args"])
            print(f"  {r['name']:<20s}  {r['category']:<10s} {r['command']:<14s} {args}")
        return 0
    if op == "show":
        if len(argv) < 2:
            print("Usage: tk preset show NAME")
            return 1
        p = preset_load(argv[1])
        if not p:
            print(f"Preset '{argv[1]}' not found.")
            return 1
        print(json.dumps(p, indent=2))
        return 0
    if op == "run":
        if len(argv) < 2:
            print("Usage: tk preset run NAME [extra-args...]")
            return 1
        p = preset_load(argv[1])
        if not p:
            print(f"Preset '{argv[1]}' not found.")
            return 1
        full = [p["command"]] + list(p.get("args", [])) + list(argv[2:])
        return run_category(p["category"], full)
    if op == "delete":
        if len(argv) < 2:
            print("Usage: tk preset delete NAME")
            return 1
        ok = preset_delete(argv[1])
        print("Deleted." if ok else "Not found.")
        return 0 if ok else 1
    print(f"Unknown preset op: {op}")
    return 1


# ---------------------------------------------------------------- meta: pipe

def cmd_pipe(argv: list[str]) -> int:
    """Run multiple tools sequentially. Steps separated by '>>'.

    Each step: '<category>:<command> [args...]'
    Example: tk pipe "image:resize in.png --width 800 -o a.png" >> "image:watermark a.png -o b.png --text hi"
    """
    if not argv:
        print('Usage: tk pipe "<cat>:<cmd> args" >> "<cat>:<cmd> args" ...')
        return 1
    full = " ".join(argv)
    steps = [s.strip() for s in full.split(">>") if s.strip()]
    rc = 0
    for i, step in enumerate(steps, 1):
        tokens = shlex.split(step)
        head = tokens[0]
        if ":" not in head:
            print(f"[pipe] step {i}: expected 'cat:cmd', got '{head}'")
            return 1
        cat, _, cmd = head.partition(":")
        print(f"\n[pipe {i}/{len(steps)}] {cat} {cmd} {' '.join(tokens[1:])}")
        rc = run_category(cat, [cmd] + tokens[1:])
        if rc != 0:
            print(f"[pipe] step {i} failed (rc={rc}); stopping.")
            return rc
    print(f"\n[pipe] all {len(steps)} steps OK.")
    return 0


# ---------------------------------------------------------------- meta: plugins

def cmd_plugins() -> int:
    from _common import LOCAL_PLUGINS_DIR, PLUGINS_DIR, discover_plugins
    plugins = discover_plugins()
    print(f"Plugin search dirs:\n  {PLUGINS_DIR}\n  {LOCAL_PLUGINS_DIR}\n")
    if not plugins:
        print("No plugins found.")
        return 0
    for key, info in plugins.items():
        print(f"  {info['icon']}  {key:<14s} {info['label']}  ({info['path']})")
    return 0


# ---------------------------------------------------------------- menu

def menu() -> int:
    print()
    print("==========================================================")
    print(f"   tk -- Personal Toolkit  v{__version__}")
    print("==========================================================")
    cats = available_categories()
    keys = list(cats.keys())
    while True:
        print()
        for i, key in enumerate(keys, 1):
            _, desc, icon = cats[key]
            print(f"  {i:2d}. {icon}  {key:<11s}  {desc}")
        print("   l. List every available command")
        print("   u. Launch web UI")
        print("   d. Doctor (check deps)")
        print("   h. Show history")
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
        if sel == "d":
            cmd_doctor()
            continue
        if sel == "h":
            cmd_history(20, False)
            continue
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


# ---------------------------------------------------------------- entry

def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])

    # Global --json flag for list output
    as_json = False
    if "--json" in argv:
        as_json = True
        argv.remove("--json")

    if not argv:
        return menu()

    head = argv[0]
    if head in ("-h", "--help", "help"):
        print(__doc__)
        list_all(as_json)
        return 0
    if head in ("-v", "--version", "version"):
        print(f"tk {__version__}")
        return 0
    if head == "list":
        list_all(as_json)
        return 0
    if head in ("ui", "web", "server"):
        import server
        return server.main(argv[1:])
    if head == "doctor":
        return cmd_doctor()
    if head == "history":
        limit = 50
        for a in argv[1:]:
            if a.isdigit():
                limit = int(a)
        return cmd_history(limit, as_json)
    if head == "preset":
        return cmd_preset(argv[1:])
    if head == "pipe":
        return cmd_pipe(argv[1:])
    if head == "plugins":
        return cmd_plugins()

    return run_category(head, argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
