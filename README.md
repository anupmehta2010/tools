# tools — Personal Toolkit

[![CI](https://github.com/anupmehta2010/tools/actions/workflows/ci.yml/badge.svg)](https://github.com/anupmehta2010/tools/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

Swiss-army box of CLI tools for everyday tasks. One **all-in-one** entry point
(`tk.py`), **30+ standalone modules**, a **stdlib-only web UI**, async job runner,
preset/history system, plugin loader, and pipeline mode.

## Quick start

```bash
python tk.py                                    # interactive menu
python tk.py ui                                 # open the web UI in your browser
python tk.py list                               # show every command
python tk.py text hash --algo sha256 -i x.txt   # run a command directly
python tk.py doctor                             # check optional deps
python tk.py history                            # show recent runs
```

The web UI (default `http://127.0.0.1:8765/`) gives you:

- searchable command catalog (Ctrl+K) across **30+ categories**
- dynamic forms generated from each command's argparse spec
- file workspace with drag-and-drop upload + per-tool file picker
- inline previews for images, videos, audio, PDF, text/code outputs
- live `python tk.py …` command preview as you fill out the form
- presets save / load, run-history viewer, async job streaming (SSE)
- 9 themes (dark, light, OLED, dracula, catppuccin, solarized, nord, gruvbox, system)
- runs on pure stdlib — no Flask/FastAPI/anything else

Each module also runs standalone:

```bash
python pdf_tools.py merge a.pdf b.pdf -o out.pdf
python image_tools.py convert photo.jpg photo.webp
python media_tools.py compress big.mp4 small.mp4 --crf 28
```

## Categories (30+)

### Core
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
| oled     | `oled_tools.py`    | image/video → C arrays for SSD1306/SSD1351/ILI9341/ST7789/etc, BMP, preview, optimize-video |
| convert  | `convert_tools.py` | universal converter: auto-route by file extension |

### Advanced (v0.2)
| Category    | Module               | What it does |
|-------------|----------------------|--------------|
| ai          | `ai_tools.py`        | local LLM via ollama (summarize, chat), faster-whisper STT, pyttsx3/piper TTS, rembg, sentence-transformers embeddings |
| doc         | `doc_tools.py`       | md ↔ docx ↔ html ↔ pdf ↔ epub (pandoc), epub-info, wordcount |
| code        | `code_tools.py`      | format (auto-detect), sloc, complexity (radon), secrets-scan, deps parse, license detect, TODO grep |
| gen         | `gen_tools.py`       | favicon set, app-icon set, og-image, gitignore picker, sitemap, robots, readme scaffold |
| time        | `time_tools.py`      | timezone convert, cron explain/next, duration calc, ICS generator, unix/iso timestamps |
| finance     | `finance_tools.py`   | currency convert (live), rates, invoice PDF, tax, loan payment, compound interest |
| db          | `db_tools.py`        | sqlite query, csv ↔ sqlite, schema dump, vacuum |
| image-pro   | `imagepro_tools.py`  | rembg, EXIF strip/show, dominant palette, smart-crop (face), upscale, panorama, HDR, blur-face, denoise, compare |
| audio-pro   | `audiopro_tools.py`  | loudnorm, denoise, BPM, spectrogram/waveform, pitch shift, tempo, stem split (demucs), silence-trim, LUFS |
| video-pro   | `videopro_tools.py`  | scene split, subtitle burn/extract/auto, denoise, stabilize, slowmo, speedup, reverse, mux, frames |
| pdf-pro     | `pdfpro_tools.py`    | OCR, redact, sign (visible+digital), table extract, form fill/extract, compare, bookmarks, linearize, reorder |
| geo         | `geo_tools.py`       | gpx ↔ kml, gpx info/simplify, great-circle distance, geocode (Nominatim), reverse geocode, EXIF-GPS |
| steg        | `steg_tools.py`      | LSB image/audio embed/extract (text or file payload), EXIF hide |
| net-pro     | `netpro_tools.py`    | SSL cert info, security-header analyzer, JWT verify, HAR viewer, traceroute, speedtest, DNS, CORS check |
| crypto-pro  | `cryptopro_tools.py` | age, GPG, ssh-keygen, BIP39 gen/verify, ECDSA, RSA, X.509 inspect, PBKDF2, argon2, TOTP |
| forensic    | `forensic_tools.py`  | magic-byte detect, entropy, strings, hexdump, file carving, bulk hash, PE-info, metadata strip, timeline |
| embedded    | `embedded_tools.py`  | hex view, intel-hex/srec parse, bin↔C array, font→bitmap, serial list/monitor, CRC-8/16/32/Fletcher |
| ml          | `ml_tools.py`        | ONNX run/info, CLIP zero-shot classify, sentence-transformers embed, tiktoken, vector search |
| 3d          | `threed_tools.py`    | obj/stl/ply parse, gcode info, decimate, voxelize, bbox |

Every category module also runs standalone (`python <module>.py <cmd> ...`).

## Web UI

```bash
python tk.py ui                # opens http://127.0.0.1:8765
python tk.py ui --port 9000    # custom port
python tk.py ui --no-browser   # don't auto-open browser
```

Files uploaded through the UI live in `web_workspace/` and are visible to every
tool. Output files are listed below the form with inline previews.

### API endpoints (stdlib HTTP)

- `GET  /api/categories` — list everything (incl. plugins)
- `GET  /api/schema/<cat>/<cmd>` — argparse schema
- `POST /api/run` — sync run
- `POST /api/run-async` — start a background job
- `GET  /api/jobs/<id>/events` — SSE stream of stdout/stderr/state
- `POST /api/batch` — run a command over many files
- `GET/POST/DELETE /api/presets[/<name>]` — preset CRUD
- `GET  /api/history?limit=N` — recent runs
- `GET  /api/doctor` — environment report
- `GET  /api/themes`, `GET/POST /api/config`

## Meta commands

```bash
python tk.py doctor                                    # check deps + binaries
python tk.py history                                   # show recent runs
python tk.py preset save my-name <cat> <cmd> [args]    # save preset
python tk.py preset list
python tk.py preset run my-name [extra args]
python tk.py preset delete my-name
python tk.py pipe "image:resize in.png --width 800 -o a.png" >> "image:watermark a.png -o b.png --text hi"
python tk.py plugins                                   # discover plugins
python tk.py --json list                               # JSON output
python tk.py version
```

## All-in-one bundle (single file)

Ship the entire toolkit — every tool, the web UI, MCP server, recipes — as a
single 200 KB file. Runs on any machine with Python 3.10+, no install:

```bash
python tk.py bundle zipapp -o tk.pyz       # build the single .pyz
python tk.pyz                              # run interactive menu
python tk.pyz ui                           # web UI
python tk.pyz text hash -i x.txt           # any command works
python tk.py bundle pyinstaller -o dist/   # native single-binary build
python tk.py bundle zip -o tk-portable.zip # plain portable zip
python tk.py bundle info                   # report what's included
```

One-shot install (drops a `tk` shim on PATH and builds the bundle):

```bash
# Windows PowerShell
.\install.ps1

# macOS / Linux
./install.sh
```

## Recipes — visual pipelines

Save and run multi-step JSON pipelines. Steps run in topological order,
output filenames pass between steps via the workspace.

```bash
python tk.py recipes scaffold > my-recipe.json    # starter template
python tk.py recipes save my-recipe.json --name photo-cleanup
python tk.py recipes run photo-cleanup --var input=in.jpg --var output=out.jpg
python tk.py recipes list
```

The web UI includes a **node-graph editor**: drag tools onto a canvas,
connect ports, click ▶ Run. Save as recipe for reuse.

## Webhooks

Bind any recipe to an HTTPS token. POST to fire it from anything (GitHub
Actions, Zapier, n8n, IFTTT, shell scripts):

```bash
# Create a hook bound to 'photo-cleanup' recipe (token printed):
curl -X POST http://localhost:8765/api/hooks \
  -H 'Content-Type: application/json' \
  -d '{"name":"photo-hook","recipe":"photo-cleanup"}'

# Trigger it from anywhere:
curl -X POST "http://localhost:8765/api/hook/$TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"vars":{"input":"in.jpg","output":"out.jpg"}}'
```

## AI assistant

Built-in chat panel (🤖 button or `A` key). Hits a local Ollama instance and
suggests tool invocations inline (`[[run cat:cmd …]]` blocks become one-click
Run buttons). Configure host/model in `~/.tk/config.toml`:

```toml
ollama_host  = "http://localhost:11434"
ollama_model = "llama3.2"
```

## MCP server (Claude Desktop / Cursor / Cline)

Expose all 350+ commands as MCP tools:

```jsonc
// ~/Library/Application Support/Claude/claude_desktop_config.json
{
  "mcpServers": {
    "tk": {
      "command": "python",
      "args": ["c:/path/to/tools/mcp_server.py"]
    }
  }
}
```

## Folder watcher

```bash
python tk.py watch run ./inbox \
  --glob "*.jpg" \
  --tool "image-pro:rembg" \
  --arg "{file}" --arg "out/{stem}.png"
```

## Shell completion

```bash
python tk.py completions bash > ~/.local/share/bash-completion/completions/tk
python tk.py completions zsh  > ~/.zsh/completions/_tk
python tk.py completions fish > ~/.config/fish/completions/tk.fish
python tk.py completions pwsh | Out-String | Invoke-Expression
```

## Browser extension

Unpacked dev install from `extension/`:
- Chrome: `chrome://extensions` → Developer mode → Load unpacked → pick `extension/`
- Right-click any image / link / selection → "Send to tk"

## Plugin system

Drop any `<name>_tools.py` into `~/.tk/plugins/` (cross-project) or `./plugins/`
(per-project). Required shape: `COMMANDS` dict, `build_parser()`, `main(argv)`.
Optional: `LABEL`, `ICON` (emoji) for the menu / web UI.

## Config

`~/.tk/config.toml` — overrides defaults:

```toml
theme = "dracula"
workspace = "/path/to/workspace"
ollama_host = "http://localhost:11434"
ollama_model = "llama3.2"
ffmpeg_path = "ffmpeg"
history_enabled = true
history_keep = 500
```

## Optional dependencies

Each tool imports its dependencies lazily — install only what you actually use.

```bash
pip install -r requirements.txt    # everything
pip install pypdf pillow           # just PDF + images
```

External binaries needed for some categories — see top of `requirements.txt`.
Run `python tk.py doctor` for a complete environment report.

## Examples

```bash
# Open the web UI
python tk.py ui

# Generate 4 strong passwords with symbols
python tk.py crypto password --length 24 --count 4 --symbols

# Compress a video, then make a thumbnail (pipeline)
python tk.py pipe "media:compress big.mp4 small.mp4 --crf 28" >> "media:thumbnail small.mp4 thumb.png"

# Local AI summary via ollama
python tk.py ai summarize -i report.txt --model llama3.2

# OCR a PDF
python tk.py pdf-pro ocr scanned.pdf -o searchable.pdf

# Remove background from an image
python tk.py image-pro rembg photo.jpg photo-nobg.png

# Generate a complete favicon set
python tk.py gen favicon logo.png -o favicons/

# SSL certificate info for a domain
python tk.py net-pro ssl-info github.com:443

# Detect file type by magic bytes
python tk.py forensic magic mystery.bin

# BIP39 mnemonic
python tk.py crypto-pro bip39-gen --words 24

# Currency convert (live rate)
python tk.py finance currency --from USD --to INR --amount 100

# Geocode an address
python tk.py geo geocode "1600 Pennsylvania Avenue, Washington DC"

# Build a 1bpp font bitmap for an embedded display
python tk.py embedded font2bmp DejaVuSans.ttf --size 14 -o font.h --varname my_font
```

## Files

```text
tk.py                            all-in-one launcher (interactive + dispatch + meta cmds)
server.py                        web UI server (stdlib http.server, SSE jobs)
_common.py                       shared helpers + config/history/presets/plugin loader
pdf_tools.py ... 3d (30+ modules) each runnable standalone
web/                             single-page web UI (HTML/CSS/JS, no build step)
web_workspace/                   uploaded files & tool outputs (created on demand)
plugins/                         drop-in extra tool modules (auto-discovered)
~/.tk/                           per-user config, presets, history db, plugins
requirements.txt                 optional deps grouped by category
LICENSE                          MIT
.github/workflows/ci.yml         CI on push: lint + smoke test (linux/mac/win × py 3.10-3.12)
```

## Contributing

Plugin shape — just drop `myname_tools.py` into `~/.tk/plugins/` (see `dev_tools.py` for a small reference).

Pull requests welcome. CI runs ruff + smoke tests on every push.

## License

MIT — see [LICENSE](LICENSE).
