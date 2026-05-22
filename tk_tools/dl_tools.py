"""Download tools: video/audio/any URL via yt-dlp (YouTube + 1800 sites + direct)."""
from __future__ import annotations

import argparse
import json
import sys as _sys
from pathlib import Path
from pathlib import Path as _Path

_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))
from _common import EXIT_USER_ERROR, TkError, lazy_import, tool_main

# ---- shared yt-dlp helpers ----

def _ydl(opts):
    """Construct a yt_dlp.YoutubeDL with sane defaults merged over opts."""
    yt_dlp = lazy_import("yt_dlp", "pip install yt-dlp")
    base = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
    }
    base.update(opts)
    return yt_dlp.YoutubeDL(base)


def _outtmpl(output):
    """Output template rooted at output dir (default cwd)."""
    d = Path(output) if output else Path.cwd()
    d.mkdir(parents=True, exist_ok=True)
    return str(d / "%(title)s.%(ext)s")


def _format_for_quality(quality):
    """Map a --quality choice to a yt-dlp format selector."""
    if quality in (None, "best"):
        return "bestvideo*+bestaudio/best"
    if quality == "audio":
        return "bestaudio/best"
    # numeric height cap, e.g. 1080/720/480
    return f"bestvideo[height<=?{quality}]+bestaudio/best[height<=?{quality}]"


def _run_download(url, opts, label="download"):
    """Run a download, translating yt-dlp errors into the tk error contract."""
    yt_dlp = lazy_import("yt_dlp", "pip install yt-dlp")
    try:
        with _ydl(opts) as ydl:
            return ydl.download([url])
    except yt_dlp.utils.DownloadError as e:
        raise TkError(f"{label} failed: {e}", code=EXIT_USER_ERROR) from e


# ---- commands ----

def cmd_video(args):
    fmt = args.format or _format_for_quality(args.quality)
    opts = {"format": fmt, "outtmpl": _outtmpl(args.output)}
    _run_download(args.url, opts, "video download")
    print(f"Downloaded video: {args.url}")
    return 0


def cmd_audio(args):
    opts = {
        "format": "bestaudio/best",
        "outtmpl": _outtmpl(args.output),
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": args.format,
            "preferredquality": args.quality or "192",
        }],
    }
    _run_download(args.url, opts, "audio extract")
    print(f"Extracted audio ({args.format}): {args.url}")
    return 0


def cmd_formats(args):
    with _ydl({}) as ydl:
        info = ydl.extract_info(args.url, download=False)
    fmts = info.get("formats", [])
    if not fmts:
        raise TkError("no formats found", code=EXIT_USER_ERROR)
    print(f"{'ID':<8} {'EXT':<5} {'RES':<11} {'NOTE'}")
    for f in fmts:
        res = f.get("resolution") or (f"{f.get('height','')}p" if f.get("height") else "audio")
        note = f.get("format_note", "") or ""
        print(f"{str(f.get('format_id','')):<8} {str(f.get('ext','')):<5} {str(res):<11} {note}")
    return 0


def cmd_info(args):
    with _ydl({}) as ydl:
        info = ydl.extract_info(args.url, download=False)
    fields = {
        "title": info.get("title"),
        "uploader": info.get("uploader"),
        "duration": info.get("duration"),
        "view_count": info.get("view_count"),
        "upload_date": info.get("upload_date"),
        "webpage_url": info.get("webpage_url"),
    }
    if args.json:
        print(json.dumps(fields, indent=2))
    else:
        for k, v in fields.items():
            print(f"{k:<12} {v}")
    return 0


def cmd_batch(args):
    path = Path(args.file)
    if not path.is_file():
        raise TkError(f"file not found: {args.file}", code=EXIT_USER_ERROR)
    urls = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.strip().startswith("#")]
    if not urls:
        raise TkError("no URLs in file", code=EXIT_USER_ERROR)
    ok = 0
    for u in urls:
        if args.audio:
            opts = {
                "format": "bestaudio/best",
                "outtmpl": _outtmpl(args.output),
                "postprocessors": [{"key": "FFmpegExtractAudio",
                                    "preferredcodec": "mp3", "preferredquality": "192"}],
            }
        else:
            opts = {"format": _format_for_quality(args.quality),
                    "outtmpl": _outtmpl(args.output)}
        try:
            _run_download(u, opts, "batch item")
            ok += 1
            print(f"[ok] {u}")
        except TkError as e:
            print(f"[fail] {u}: {e}")
    print(f"Batch done: {ok}/{len(urls)} succeeded")
    return 0 if ok else EXIT_USER_ERROR


def cmd_direct(args):
    # Generic extractor handles plain file URLs (and falls back for unknown sites).
    opts = {"outtmpl": _outtmpl(args.output), "format": "best"}
    _run_download(args.url, opts, "direct download")
    print(f"Downloaded: {args.url}")
    return 0


COMMANDS = {
    "video":   "download video (YouTube + 1800 sites); --quality best/1080/720/480",
    "audio":   "download audio only and extract to mp3/m4a (needs ffmpeg)",
    "formats": "list available formats/qualities for a URL (no download)",
    "info":    "show metadata for a URL: title, duration, uploader, views",
    "batch":   "download every URL listed in a text file (one per line)",
    "direct":  "download any direct file URL",
}


def build_parser(parser=None):
    parser = parser or argparse.ArgumentParser(prog="dl_tools", description="Downloaders (yt-dlp)")
    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("video", help=COMMANDS["video"])
    p.add_argument("url")
    p.add_argument("-q", "--quality", default="best",
                   help="best | 1080 | 720 | 480 | audio")
    p.add_argument("-f", "--format", help="raw yt-dlp format selector (overrides --quality)")
    p.add_argument("-o", "--output", help="output directory (default: cwd)")
    p.set_defaults(func=cmd_video)

    p = sub.add_parser("audio", help=COMMANDS["audio"])
    p.add_argument("url")
    p.add_argument("-f", "--format", default="mp3", choices=["mp3", "m4a", "opus", "wav", "flac"])
    p.add_argument("-q", "--quality", help="audio bitrate, e.g. 192 (default) or 320")
    p.add_argument("-o", "--output", help="output directory (default: cwd)")
    p.set_defaults(func=cmd_audio)

    p = sub.add_parser("formats", help=COMMANDS["formats"])
    p.add_argument("url")
    p.set_defaults(func=cmd_formats)

    p = sub.add_parser("info", help=COMMANDS["info"])
    p.add_argument("url")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_info)

    p = sub.add_parser("batch", help=COMMANDS["batch"])
    p.add_argument("file", help="text file of URLs (one per line; # comments allowed)")
    p.add_argument("--audio", action="store_true", help="extract audio (mp3) instead of video")
    p.add_argument("-q", "--quality", default="best", help="video quality when not --audio")
    p.add_argument("-o", "--output", help="output directory (default: cwd)")
    p.set_defaults(func=cmd_batch)

    p = sub.add_parser("direct", help=COMMANDS["direct"])
    p.add_argument("url")
    p.add_argument("-o", "--output", help="output directory (default: cwd)")
    p.set_defaults(func=cmd_direct)

    return parser


@tool_main("dl")
def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 1
    return args.func(args) or 0


if __name__ == "__main__":
    raise SystemExit(main())
