# tools — Personal Toolkit

Swiss-army box of CLI tools for everyday tasks. One **all-in-one** entry point
(`tk.py`), 12 standalone modules, **and a polished web UI**.

## Quick start

```bash
python tk.py                                    # interactive menu
python tk.py ui                                 # open the web UI in your browser
python tk.py list                               # show every command
python tk.py text hash --algo sha256 -i x.txt   # run a command directly
```

The web UI (default `http://127.0.0.1:8765/`) gives you:

- searchable command catalog (Ctrl+K) across all 12 categories
- dynamic forms generated from each command's argparse spec
- file workspace with drag-and-drop upload + per-tool file picker
- inline previews for images, videos, audio, PDF, text/code outputs
- live `python tk.py …` command preview as you fill out the form
- dark/light theme toggle
- runs on pure stdlib — no Flask/FastAPI/anything else

Each module also runs standalone:

```bash
python pdf_tools.py merge a.pdf b.pdf -o out.pdf
python image_tools.py convert photo.jpg photo.webp
python media_tools.py compress big.mp4 small.mp4 --crf 28
```

## Categories

| Category | Module             | What it does |
|----------|--------------------|--------------|
| pdf      | `pdf_tools.py`     | merge, split, extract text/images, info, md→pdf, html→pdf, img→pdf, compress, encrypt/decrypt |
| image    | `image_tools.py`   | format convert, resize, compress, rotate, crop, grayscale, watermark, ASCII art, info |
| media    | `media_tools.py`   | ffmpeg-powered audio/video convert, extract audio/video, trim, compress, GIF, thumbnail, concat |
| text     | `text_tools.py`    | base64/url/hex/html encode-decode, hashes, case (snake/kebab/camel/pascal), JSON format/minify, diff, count, sort, reverse |
| data     | `data_tools.py`    | CSV ↔ JSON ↔ Excel, YAML ↔ JSON, XML/TOML → JSON, csv-view |
| archive  | `archive_tools.py` | zip/unzip, tar/untar (gz/bz2/xz), auto-extract |
| crypto   | `crypto_tools.py`  | password gen, UUID, file hash, JWT decode, Fernet keygen/encrypt/decrypt, random bytes |
| net      | `net_tools.py`     | HTTP request, download, DNS, reverse DNS, ping, port scan, my-ip, whois, URL check |
| fs       | `fs_tools.py`      | bulk regex rename, dedupe, search, disk usage, sysinfo, tree, count |
| dev      | `dev_tools.py`     | regex test/replace, color converter, lorem ipsum, base conv, calc, timestamp, slugify, curl→Python |
| qr       | `qr_tools.py`      | generate QR (PNG/SVG/ASCII), decode QR from image |
| oled     | `oled_tools.py`    | image/video → C arrays for SSD1306/SSD1351/ILI9341/ST7789/etc, BMP, preview, optimize-video for embedded |

## Web UI

```bash
python tk.py ui                # opens http://127.0.0.1:8765 in your browser
python tk.py ui --port 9000    # custom port
python tk.py ui --no-browser   # don't auto-open browser
```

Files uploaded through the UI live in `web_workspace/` and are visible to every
tool. Output files are listed below the form with inline previews.

## Optional dependencies

Each tool imports its dependencies lazily — install only what you actually use.

```bash
pip install -r requirements.txt    # everything
pip install pypdf pillow           # just PDF + images
```

External binary needed for the `media` category:

- **ffmpeg** — install from <https://ffmpeg.org> and ensure it is on `PATH`.

For QR decoding, `pyzbar` needs the `libzbar` runtime DLL on Windows.

## Examples

```bash
# Open the web UI
python tk.py ui

# Generate 4 strong passwords with symbols
python tk.py crypto password --length 24 --count 4 --symbols

# Bulk rename: IMG_(\d+).jpg -> photo_$1.jpg
python tk.py fs rename ./photos "IMG_(\d+).jpg" "photo_\1.jpg" --execute

# Watermark an image
python tk.py image watermark in.png out.png --text "(c) Anup"

# Convert markdown to a styled PDF (uses generate_build_guide_pdf.py)
python tk.py pdf md2pdf README.md -o README.pdf

# Compress a video
python tk.py media compress big.mp4 out.mp4 --crf 28

# CSV -> Excel and back
python tk.py data csv2xlsx data.csv data.xlsx
python tk.py data xlsx2csv data.xlsx data.csv

# Decode a JWT (no signature verification)
python tk.py crypto jwt eyJhbGciOiJIUzI1NiJ9...

# QR code in the terminal
python tk.py qr gen "https://anthropic.com"

# Find duplicate files
python tk.py fs dedupe ./Downloads

# Test a regex
python tk.py dev regex "(\w+)@(\w+)" "alice@example.com bob@gmail.com"

# OLED: convert image to RGB565 C array for an ST7789 240x240
python tk.py oled image-to-c logo.png -o logo.h --display st7789 --varname logo

# OLED: extract video frames as a C array animation for SSD1306 (mono)
python tk.py oled video-to-c clip.mp4 -o anim.h --display ssd1306 --fps 15 --frames 30 --dither

# OLED: render a preview of what an image will look like on a tiny mono screen
python tk.py oled preview photo.jpg preview.png --display ssd1306 --dither --scale 6

# OLED: re-encode a video to play on an MCU-driven 320x240 screen via MJPEG
python tk.py oled optimize-video bigfile.mp4 small.mp4 --display ili9341 --fps 12 --quality 6 --no-audio

# List built-in display profiles
python tk.py oled displays
```

## Files

```text
tk.py                            all-in-one launcher (interactive + dispatch)
server.py                        web UI server (stdlib http.server)
_common.py                       shared helpers (lazy_import, human_size, ...)
pdf_tools.py ... oled_tools.py   12 category modules (each runnable standalone)
generate_build_guide_pdf.py      original markdown -> styled PDF (kept as-is)
web/                             single-page web UI (HTML/CSS/JS, no build step)
web_workspace/                   uploaded files & tool outputs (created on demand)
requirements.txt                 optional deps grouped by category
```
