"""Audio/Video tools: ffmpeg-powered conversion, extract, trim, compress, GIF."""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))
from _common import tool_main


def _check_ffmpeg():
    if shutil.which("ffmpeg") is None:
        print("[!] ffmpeg not found in PATH.")
        print("    Install: https://ffmpeg.org/download.html")
        sys.exit(2)


def _run(cmd) -> int:
    print("$", " ".join(str(c) for c in cmd))
    return subprocess.call(cmd)


def cmd_convert(args):
    _check_ffmpeg()
    cmd = ["ffmpeg", "-y", "-i", args.input]
    if args.bitrate:
        cmd += ["-b:a", args.bitrate]
    cmd += [args.output]
    return _run(cmd)


def cmd_extract_audio(args):
    _check_ffmpeg()
    cmd = ["ffmpeg", "-y", "-i", args.input, "-vn", "-c:a", args.codec, args.output]
    return _run(cmd)


def cmd_extract_video(args):
    _check_ffmpeg()
    cmd = ["ffmpeg", "-y", "-i", args.input, "-an", "-c:v", "copy", args.output]
    return _run(cmd)


def cmd_trim(args):
    _check_ffmpeg()
    cmd = ["ffmpeg", "-y", "-i", args.input, "-ss", str(args.start)]
    if args.end:
        cmd += ["-to", str(args.end)]
    elif args.duration:
        cmd += ["-t", str(args.duration)]
    cmd += ["-c", "copy", args.output]
    return _run(cmd)


def cmd_compress(args):
    _check_ffmpeg()
    cmd = [
        "ffmpeg", "-y", "-i", args.input,
        "-c:v", "libx264", "-crf", str(args.crf),
        "-preset", args.preset,
        "-c:a", "aac", "-b:a", "128k",
        args.output,
    ]
    return _run(cmd)


def cmd_gif(args):
    _check_ffmpeg()
    cmd = [
        "ffmpeg", "-y", "-i", args.input,
        "-vf", f"fps={args.fps},scale={args.width}:-1:flags=lanczos",
        args.output,
    ]
    return _run(cmd)


def cmd_thumbnail(args):
    _check_ffmpeg()
    cmd = ["ffmpeg", "-y", "-i", args.input, "-ss", str(args.time), "-vframes", "1", args.output]
    return _run(cmd)


def cmd_info(args):
    if shutil.which("ffprobe") is None:
        print("[!] ffprobe not found (ships with ffmpeg).")
        return 2
    cmd = ["ffprobe", "-v", "error", "-show_format", "-show_streams", args.input]
    return _run(cmd)


def cmd_concat(args):
    _check_ffmpeg()
    list_path = Path(args.output).with_suffix(".concat.txt")
    list_path.write_text(
        "\n".join(f"file '{Path(p).resolve().as_posix()}'" for p in args.inputs),
        encoding="utf-8",
    )
    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(list_path), "-c", "copy", args.output,
    ]
    rc = _run(cmd)
    list_path.unlink(missing_ok=True)
    return rc


def cmd_volume(args):
    _check_ffmpeg()
    cmd = ["ffmpeg", "-y", "-i", args.input, "-filter:a", f"volume={args.factor}", args.output]
    return _run(cmd)


def cmd_gif_from_images(args):
    _check_ffmpeg()
    src = Path(args.input_glob)
    parent = src.parent if str(src.parent) else Path(".")
    pattern = src.name
    cmd = [
        "ffmpeg", "-y",
        "-framerate", str(args.fps),
        "-pattern_type", "glob",
        "-i", str(parent / pattern),
        "-vf", f"scale={args.width}:-1:flags=lanczos",
        args.output,
    ]
    return _run(cmd)


def cmd_normalize(args):
    _check_ffmpeg()
    cmd = [
        "ffmpeg", "-y", "-i", args.input,
        "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
        "-ar", "48000", args.output,
    ]
    return _run(cmd)


def cmd_to_webp(args):
    _check_ffmpeg()
    cmd = [
        "ffmpeg", "-y", "-i", args.input,
        "-vf", f"fps={args.fps},scale={args.width}:-1:flags=lanczos",
        "-loop", "0", args.output,
    ]
    return _run(cmd)


def cmd_speed(args):
    _check_ffmpeg()
    # Audio atempo is bounded to [0.5, 2.0]; chain if outside.
    s = args.factor
    atempos = []
    while s > 2.0:
        atempos.append(2.0); s /= 2.0
    while s < 0.5:
        atempos.append(0.5); s /= 0.5
    atempos.append(s)
    audio = ",".join(f"atempo={x}" for x in atempos)
    setpts = f"setpts={1 / args.factor}*PTS"
    cmd = [
        "ffmpeg", "-y", "-i", args.input,
        "-filter_complex", f"[0:v]{setpts}[v];[0:a]{audio}[a]",
        "-map", "[v]", "-map", "[a]", args.output,
    ]
    return _run(cmd)


COMMANDS = {
    "convert":       "convert audio/video to any format",
    "extract-audio": "extract audio track",
    "extract-video": "extract video without audio",
    "trim":          "trim/cut media by time",
    "compress":      "re-encode video (H.264 + AAC)",
    "gif":           "convert video to GIF",
    "thumbnail":     "extract a frame as image",
    "concat":        "concatenate media files (same codec)",
    "info":          "ffprobe info about media",
    "volume":        "change audio volume by factor",
    "speed":         "change playback speed (video + audio)",
    "gif-from-images": "build animated GIF from glob of images",
    "normalize":     "loudness normalization (loudnorm)",
    "to-webp":       "convert video to animated WebP",
}


def build_parser(parser=None):
    parser = parser or argparse.ArgumentParser(prog="media_tools", description="ffmpeg media utilities")
    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("convert", help=COMMANDS["convert"])
    p.add_argument("input"); p.add_argument("output"); p.add_argument("--bitrate")
    p.set_defaults(func=cmd_convert)

    p = sub.add_parser("extract-audio", help=COMMANDS["extract-audio"])
    p.add_argument("input"); p.add_argument("output")
    p.add_argument("--codec", default="libmp3lame")
    p.set_defaults(func=cmd_extract_audio)

    p = sub.add_parser("extract-video", help=COMMANDS["extract-video"])
    p.add_argument("input"); p.add_argument("output")
    p.set_defaults(func=cmd_extract_video)

    p = sub.add_parser("trim", help=COMMANDS["trim"])
    p.add_argument("input"); p.add_argument("output")
    p.add_argument("--start", required=True)
    p.add_argument("--end")
    p.add_argument("--duration")
    p.set_defaults(func=cmd_trim)

    p = sub.add_parser("compress", help=COMMANDS["compress"])
    p.add_argument("input"); p.add_argument("output")
    p.add_argument("--crf", type=int, default=23)
    p.add_argument("--preset", default="medium",
                   choices=["ultrafast", "superfast", "veryfast", "faster", "fast",
                            "medium", "slow", "slower", "veryslow"])
    p.set_defaults(func=cmd_compress)

    p = sub.add_parser("gif", help=COMMANDS["gif"])
    p.add_argument("input"); p.add_argument("output")
    p.add_argument("--fps", type=int, default=12)
    p.add_argument("--width", type=int, default=480)
    p.set_defaults(func=cmd_gif)

    p = sub.add_parser("thumbnail", help=COMMANDS["thumbnail"])
    p.add_argument("input"); p.add_argument("output")
    p.add_argument("--time", default="00:00:01")
    p.set_defaults(func=cmd_thumbnail)

    p = sub.add_parser("concat", help=COMMANDS["concat"])
    p.add_argument("inputs", nargs="+")
    p.add_argument("-o", "--output", required=True)
    p.set_defaults(func=cmd_concat)

    p = sub.add_parser("info", help=COMMANDS["info"])
    p.add_argument("input")
    p.set_defaults(func=cmd_info)

    p = sub.add_parser("volume", help=COMMANDS["volume"])
    p.add_argument("input"); p.add_argument("output")
    p.add_argument("--factor", type=float, required=True, help="e.g. 0.5 = half, 2.0 = double")
    p.set_defaults(func=cmd_volume)

    p = sub.add_parser("speed", help=COMMANDS["speed"])
    p.add_argument("input"); p.add_argument("output")
    p.add_argument("--factor", type=float, required=True, help="e.g. 1.5 = 1.5x speed")
    p.set_defaults(func=cmd_speed)

    p = sub.add_parser("gif-from-images", help=COMMANDS["gif-from-images"])
    p.add_argument("input_glob", help="e.g. frames/*.png")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--fps", type=int, default=12)
    p.add_argument("--width", type=int, default=480)
    p.set_defaults(func=cmd_gif_from_images)

    p = sub.add_parser("normalize", help=COMMANDS["normalize"])
    p.add_argument("input"); p.add_argument("output")
    p.set_defaults(func=cmd_normalize)

    p = sub.add_parser("to-webp", help=COMMANDS["to-webp"])
    p.add_argument("input"); p.add_argument("output")
    p.add_argument("--fps", type=int, default=12)
    p.add_argument("--width", type=int, default=480)
    p.set_defaults(func=cmd_to_webp)

    return parser


@tool_main("media")
def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 1
    return args.func(args) or 0


if __name__ == "__main__":
    raise SystemExit(main())
