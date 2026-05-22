# tk — Personal All-in-One Toolkit

[![CI](https://github.com/anupmehta2010/tools/actions/workflows/ci.yml/badge.svg)](https://github.com/anupmehta2010/tools/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

One command-line entry point (`tk.py`) exposing **37 tool categories** and **375
commands** — PDF, image, audio/video, text, data, crypto, networking, downloads,
forensics, embedded, ML, 3D and more. The same registry powers four interfaces:

| Interface | Entry point | Use it for |
|---|---|---|
| **CLI** | `python tk.py <category> <command> …` | scripting, terminals, pipes |
| **Web UI** | `python tk.py server` | forms, file workspace, previews |
| **MCP server** | `python mcp_server.py` | Claude Desktop / any MCP client |
| **Plugins** | drop `*_tools.py` in `~/.tk/plugins/` | your own categories |

Pure standard library at the core — no Flask/FastAPI. Optional features
(image/audio/PDF/AI/etc.) lazy-import their deps and tell you exactly what to
`pip install` when missing.

---

## Quick start

```bash
git clone https://github.com/anupmehta2010/tools.git
cd tools

python tk.py                                    # interactive menu
python tk.py list                               # list every command
python tk.py dev calc "2 + 2 * 5"               # run a command directly
python tk.py text hash --algo sha256 -i x.txt   # hash a file
python tk.py server                             # open the web UI
python tk.py doctor                             # report which optional deps are present
python tk.py version                            # 0.3.1
```

No install step is required to run from source — only Python 3.10+. To install
as a `tk` console script:

```bash
pip install -e .                # core
pip install -e ".[download]"    # + yt-dlp for the dl category
pip install -e ".[dev]"         # + test/lint toolchain
```

---

## Categories

37 built-in categories (command counts in parentheses). Run
`python tk.py <category>` for that category's help, or `python tk.py list` for
everything.

| Cat | Slug | Cmds | What it does |
|---|---|---:|---|
| 📄 | `pdf` | 15 | merge, split, extract, md/img/html→pdf, compress |
| 🖼️ | `image` | 17 | convert, resize, compress, watermark, ASCII art |
| 🎬 | `media` | 14 | audio/video via ffmpeg: convert, trim, GIF, thumbnail |
| ✍️ | `text` | 31 | encoding, hashes, case conversion, JSON format, diff |
| 📊 | `data` | 18 | CSV/JSON/Excel/YAML/XML/TOML conversions |
| 📦 | `archive` | 6 | zip/tar create + extract |
| 🔐 | `crypto` | 14 | passwords, UUIDs, file hash, JWT, Fernet encrypt |
| 🌐 | `net` | 13 | HTTP, DNS, ping, port-scan, download, my-ip, whois |
| ⬇️ | `dl` | 6 | download video/audio/any URL via yt-dlp (YouTube +1800 sites) |
| 📁 | `fs` | 11 | bulk rename, dedupe, search, disk usage, sysinfo |
| ⚙️ | `dev` | 15 | regex, color, lorem, base, calc, timestamp, slug |
| 📱 | `qr` | 5 | QR codes: generate and decode |
| 💡 | `oled` | 10 | OLED/embedded: img/video → C arrays, BMP, opt |
| 🔄 | `convert` | 3 | universal converter: auto-route by file extension |
| 🤖 | `ai` | 6 | local AI: summarize, chat (ollama), STT, TTS, rembg, embed |
| 📝 | `doc` | 8 | documents: md/docx/html/pdf/epub conversions (pandoc) |
| `</>` | `code` | 7 | format, sloc, complexity, secrets-scan, deps |
| ✨ | `gen` | 7 | generators: favicon, app-icon, og-image, gitignore, sitemap, readme |
| ⏱️ | `time` | 8 | tz convert, cron explain, ics gen, duration calc |
| 💰 | `finance` | 6 | currency convert, invoice, tax, loan, compound |
| 🗃️ | `db` | 7 | SQLite: query, csv import/export, schema, vacuum |
| 🎨 | `image-pro` | 11 | rembg, EXIF, palette, smart-crop, upscale, panorama, HDR |
| 🎚️ | `audio-pro` | 10 | normalize, denoise, BPM, spectrogram, stems |
| 🎞️ | `video-pro` | 14 | scene split, subtitle burn/auto, stabilize |
| 📑 | `pdf-pro` | 11 | OCR, redact, sign, tables, forms, compare |
| 🗺️ | `geo` | 10 | gpx/kml, distance, geocode, exif-gps, bbox |
| 🕵️ | `steg` | 7 | steganography: LSB image/audio embed/extract |
| 🛰️ | `net-pro` | 10 | SSL, headers, JWT verify, HAR, traceroute, speedtest |
| 🔏 | `crypto-pro` | 17 | age, GPG, SSH keygen, BIP39, ECDSA, X.509, TOTP |
| 🔬 | `forensic` | 10 | magic, entropy, strings, hexdump, carve, PE |
| 🔌 | `embedded` | 12 | hex, intel-hex, bin↔C, font→bmp, serial, CRC |
| 🧠 | `ml` | 9 | ONNX run, classify, embed, tokenize, vector search |
| 🧊 | `3d` | 9 | obj/stl/ply, gcode info, decimate, voxelize, bbox |
| 📜 | `completions` | 4 | shell completions: bash, zsh, pwsh, fish |
| 👁️ | `watch` | 2 | folder watcher: trigger a tool on new/changed files |
| 🧬 | `recipes` | 8 | save and run multi-step JSON pipelines |
| 📦 | `bundle` | 4 | build single-file .pyz / zip / native binary |

---

## Downloading media — `tk dl`

A CLI/web equivalent of the [media-downloader](https://github.com/mhogomchungu/media-downloader)
GUI, backed by [yt-dlp](https://github.com/yt-dlp/yt-dlp) (YouTube + ~1800 sites
plus direct file URLs).

```bash
pip install yt-dlp                       # required; ffmpeg also needed for `dl audio`

python tk.py dl video "<url>" -q 1080 -o downloads   # video at ≤1080p
python tk.py dl video "<url>" -q best                # best available
python tk.py dl audio "<url>" -f mp3                 # audio only → mp3
python tk.py dl formats "<url>"                      # list formats (no download)
python tk.py dl info "<url>"                          # title/duration/uploader/views
python tk.py dl batch urls.txt --audio               # every URL in a file
python tk.py dl direct "https://host/file.zip"       # plain file download
```

| Command | Purpose | Key flags |
|---|---|---|
| `video` | download video | `-q best\|1080\|720\|480\|audio`, `-f <selector>`, `-o DIR` |
| `audio` | audio-only, extracted via ffmpeg | `-f mp3\|m4a\|opus\|wav\|flac`, `-q <bitrate>`, `-o DIR` |
| `formats` | list available formats, no download | — |
| `info` | print metadata | `--json` |
| `batch` | download every URL in a text file | `--audio`, `-q`, `-o DIR` |
| `direct` | download any direct file URL | `-o DIR` |

Missing yt-dlp exits `3` with an install hint; a bad URL exits `1`.

---

## Web UI

```bash
python tk.py server                       # http://127.0.0.1:8765, opens browser
python tk.py server --port 9000 --no-browser
python tk.py ui          # alias
python tk.py web         # alias
```

- searchable command catalog (Ctrl+K) across all 37 categories
- dynamic forms generated from each command's argparse spec
- file workspace: drag-and-drop upload, per-tool file picker, previews for
  images, video, audio, PDF, and text/code
- live `python tk.py …` command preview as you fill the form
- presets save/load, run-history viewer, async jobs streamed over SSE
- multiple themes (dark, light, OLED, dracula, catppuccin, solarized, nord, gruvbox, system)
- pure stdlib `http.server` — no web framework

### JSON API

```http
POST /api/run
Content-Type: application/json

{ "category": "dev", "command": "calc", "args": ["2+2"] }
```

```json
{ "rc": 0, "stdout": "4\n", "stderr": "", "new_files": [], "new_dirs": [] }
```

Other endpoints: `/api/run-async` (SSE), `/api/batch`, `/api/categories`,
`/api/schema/<cat>/<cmd>`, `/api/files`, `/api/upload`, `/api/presets`,
`/api/history`, `/api/config`, `/api/doctor`, `/api/themes`, `/api/version`.

---

## MCP server

Every category/command is exposed as an MCP tool over JSON-RPC 2.0 on stdio.
Configure in an MCP client such as Claude Desktop:

```json
{
  "mcpServers": {
    "tk": {
      "command": "python",
      "args": ["c:/path/to/tools/mcp_server.py"]
    }
  }
}
```

Supports `initialize`, `tools/list`, `tools/call`, `resources/list`,
`resources/read`.

---

## Recipes (pipelines)

Chain commands into a saved multi-step pipeline (JSON), with dependencies between
steps.

```bash
python tk.py recipes validate path/to/recipe.json
python tk.py recipes run path/to/recipe.json
python tk.py recipes list
```

`validate` checks structure, unique step ids, `category:command` tool format,
dependency references, and that the dependency graph is acyclic. `run`/`exec`
validate before executing.

---

## Configuration, history, presets

- **Config:** TOML at `~/.tk/config.toml` (`python tk.py config …`)
- **History:** SQLite at `~/.tk/history.db` — every run is logged (`python tk.py history`)
- **Presets:** saved argument sets, usable from CLI and web
- **Plugins:** `~/.tk/plugins/` (global) or `./plugins/` (project-local)

---

## Error contract

| Exit code | Meaning |
|---:|---|
| 0 | success |
| 1 | bad input, file not found, runtime failure |
| 2 | invalid CLI arguments |
| 3 | optional dependency not installed |

Errors print as `tk <category>: <message>` to stderr. Pass `--debug` (or set
`TK_DEBUG`) for a full traceback.

---

## Plugins

Drop a `<name>_tools.py` file into `~/.tk/plugins/` (global) or `./plugins/`
(project-local). It must expose the same contract as a built-in module:

```python
from _common import tool_main

COMMANDS = {"hello": "say hello"}

def build_parser():
    ...

@tool_main("mycat")          # slug == filename stem minus _tools
def main(argv=None):
    ...
```

Optionally set module-level `LABEL` and `ICON`. The category is auto-merged into
the CLI, web UI, and MCP server.

---

## Development

```bash
# core suite — no optional deps needed
python -m pytest tests/ --ignore=tests/e2e -q

# with coverage
python -m pytest tests/ --ignore=tests/e2e --cov --cov-report=term-missing

# E2E (Playwright)
pip install pytest-playwright && python -m playwright install chromium
python -m pytest tests/e2e -q

# lint
ruff check .
```

| Test file | Covers |
|---|---|
| `test_smoke.py` | basic imports + CLI invocation |
| `test_catalog.py` | contract sweep: `COMMANDS`, `build_parser`, wrapped `main`, per-command `--help` |
| `test_golden.py` | parametrised I/O table from `tests/cases/*.py` |
| `test_fuzz.py` | garbage args per module + `dev calc` AST sandbox + Hypothesis |
| `test_validation.py` | `validate_recipe` / `validate_config` |
| `test_api.py` | live server endpoints |
| `tests/e2e/test_web.py` | Playwright browser tests |

CI runs five lanes: **lint** (ruff), **core** (3 OS × py3.10/3.11/3.12, 25%
coverage gate), **full** (optional deps, best-effort), **e2e** (Playwright,
best-effort), and **build-binary** (PyInstaller `--onefile`, on `v*` tags).

See [CLAUDE.md](CLAUDE.md) for the full architecture and module contract.

---

## Security

`dev calc` evaluates expressions with an **AST-whitelist** evaluator — never
`eval`/`exec` on user input. It is reachable over the web API at `/api/run`, so
the whitelist must be maintained. The codebase contains no `eval`, `exec`, or
`shell=True` on user-supplied input.

---

## License

[MIT](LICENSE) © Anup Mehta
