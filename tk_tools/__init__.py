"""tk_tools — unified package containing every built-in tool module.

Each submodule exposes:
    COMMANDS      dict[str, str]
    build_parser  -> argparse.ArgumentParser
    main(argv)    int

Categories are organized by domain. The category registry lives in `tk.py`.

Submodule paths follow `tk_tools.<name>_tools`, e.g.:
    from tk_tools.pdf_tools import main as pdf_main

External code (the launcher tk.py, the web server, the MCP server) imports
submodules dynamically via importlib so no hard-coded list lives here.
"""
from __future__ import annotations

# Logical grouping (display only — tk.py owns the canonical registry).
DOMAINS: dict[str, list[str]] = {
    "core":       ["pdf",     "image",      "media",     "text",     "data",
                   "archive", "crypto",     "net",       "fs",       "dev",
                   "qr",      "oled",       "convert"],
    "ai_ml":      ["ai",      "ml"],
    "documents":  ["doc",     "pdf-pro"],
    "media_pro":  ["image-pro","audio-pro", "video-pro"],
    "code_gen":   ["code",    "gen"],
    "data_db":    ["db",      "finance"],
    "spatial":    ["geo",     "time"],
    "security":   ["crypto-pro","net-pro",  "forensic",  "steg"],
    "embedded":   ["embedded","3d"],
    "system":     ["recipes", "watch",      "completions","bundle"],
}

__all__ = ["DOMAINS"]
