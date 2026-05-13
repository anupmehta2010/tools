"""Advanced video tools: scene split, subtitles, denoise, stabilize, slowmo, reverse, loop, crop-auto, framerate, mux, frames."""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

from _common import lazy_import, human_size, ensure_dir, confirm


def _check_ffmpeg():
    if shutil.which("ffmpeg") is None:
        print("[!] ffmpeg not found in PATH.")
        print("    Install: https://ffmpeg.org/download.html")
        sys.exit(2)


def _run(cmd, capture: bool = False):
    print("$", " ".join(str(c) for c in cmd))
    if capture:
        return subprocess.run(cmd, check=False, capture_output=True, text=True)
    return subprocess.run(cmd, check=False)


def cmd_scene_split(args):
    _check_ffmpeg()
    out_dir = ensure_dir(Path(args.output))
    pattern = str(out_dir / "scene_%03d.mp4")
    cmd = [
        "ffmpeg", "-y", "-i", args.input,
        "-vf", f"select='gt(scene,{args.threshold})',showinfo",
        "-f", "segment", "-reset_timestamps", "1",
        "-segment_time", "0.1",
        pattern,
    ]
    # Simpler & more reliable: use scene-change segment_times via ffprobe
    # First, detect scenes with ffmpeg select filter and parse pts_time.
    probe = subprocess.run(
        ["ffmpeg", "-i", args.input, "-vf", f"select='gt(scene,{args.threshold})',showinfo",
         "-f", "null", "-"],
        check=False, capture_output=True, text=True,
    )
    times = []
    for line in (probe.stderr or "").splitlines():
        m = re.search(r"pts_time:([\d.]+)", line)
        if m:
            times.append(m.group(1))
    if not times:
        print("(no scene changes detected; copying as scene_000)")
        out = out_dir / "scene_000.mp4"
        return _run(["ffmpeg", "-y", "-i", args.input, "-c", "copy", str(out)]).returncode
    segs = ",".join(times)
    cmd = [
        "ffmpeg", "-y", "-i", args.input,
        "-f", "segment", "-segment_times", segs, "-reset_timestamps", "1",
        "-c", "copy",
        str(out_dir / "scene_%03d.mp4"),
    ]
    r = _run(cmd)
    print(f"Scenes -> {out_dir}")
    return r.returncode


def cmd_subtitle_burn(args):
    _check_ffmpeg()
    srt = str(Path(args.srt).resolve()).replace("\\", "/").replace(":", "\\:")
    cmd = ["ffmpeg", "-y", "-i", args.input, "-vf", f"subtitles='{srt}'", args.output]
    return _run(cmd).returncode


def cmd_subtitle_extract(args):
    _check_ffmpeg()
    cmd = ["ffmpeg", "-y", "-i", args.input, "-map", f"0:s:{args.index}", args.output]
    return _run(cmd).returncode


def cmd_auto_subtitle(args):
    fw = lazy_import("faster_whisper", install_hint="pip install faster-whisper")
    from faster_whisper import WhisperModel
    model = WhisperModel(args.model, device=args.device, compute_type=args.compute_type)
    segments, info = model.transcribe(args.input, language=args.language, vad_filter=True)
    out = Path(args.output)
    lines = []
    for i, seg in enumerate(segments, 1):
        lines.append(str(i))
        lines.append(f"{_srt_ts(seg.start)} --> {_srt_ts(seg.end)}")
        lines.append(seg.text.strip())
        lines.append("")
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {out} (lang={info.language})")


def _srt_ts(t: float) -> str:
    if t < 0: t = 0
    h = int(t // 3600); m = int((t % 3600) // 60)
    s = int(t % 60); ms = int(round((t - int(t)) * 1000))
    if ms == 1000:
        s += 1; ms = 0
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def cmd_denoise_video(args):
    _check_ffmpeg()
    cmd = ["ffmpeg", "-y", "-i", args.input, "-vf", f"hqdn3d={args.luma}:{args.chroma}:{args.tluma}:{args.tchroma}", args.output]
    return _run(cmd).returncode


def cmd_stabilize(args):
    _check_ffmpeg()
    tmp = Path(args.output).with_suffix(".trf")
    r1 = _run([
        "ffmpeg", "-y", "-i", args.input,
        "-vf", f"vidstabdetect=result={tmp.as_posix()}:shakiness={args.shakiness}",
        "-f", "null", "-",
    ])
    if r1.returncode != 0:
        return r1.returncode
    r2 = _run([
        "ffmpeg", "-y", "-i", args.input,
        "-vf", f"vidstabtransform=input={tmp.as_posix()}:smoothing={args.smoothing}",
        args.output,
    ])
    tmp.unlink(missing_ok=True)
    return r2.returncode


def cmd_slowmo(args):
    _check_ffmpeg()
    setpts = f"setpts={args.factor}*PTS"
    af = f"atempo={1 / args.factor if args.factor >= 0.5 else 0.5}" if args.keep_audio else None
    if args.keep_audio:
        cmd = [
            "ffmpeg", "-y", "-i", args.input,
            "-filter_complex", f"[0:v]{setpts}[v];[0:a]{af}[a]",
            "-map", "[v]", "-map", "[a]", args.output,
        ]
    else:
        cmd = ["ffmpeg", "-y", "-i", args.input, "-filter:v", setpts, "-an", args.output]
    return _run(cmd).returncode


def cmd_speedup(args):
    _check_ffmpeg()
    setpts = f"setpts={1 / args.factor}*PTS"
    s = args.factor
    chain = []
    while s > 2.0:
        chain.append(2.0); s /= 2.0
    while s < 0.5:
        chain.append(0.5); s /= 0.5
    chain.append(s)
    af = ",".join(f"atempo={x}" for x in chain)
    cmd = [
        "ffmpeg", "-y", "-i", args.input,
        "-filter_complex", f"[0:v]{setpts}[v];[0:a]{af}[a]",
        "-map", "[v]", "-map", "[a]", args.output,
    ]
    return _run(cmd).returncode


def cmd_reverse(args):
    _check_ffmpeg()
    cmd = [
        "ffmpeg", "-y", "-i", args.input,
        "-vf", "reverse", "-af", "areverse", args.output,
    ]
    return _run(cmd).returncode


def cmd_loop(args):
    _check_ffmpeg()
    cmd = [
        "ffmpeg", "-y", "-stream_loop", str(args.count - 1),
        "-i", args.input, "-c", "copy", args.output,
    ]
    return _run(cmd).returncode


def cmd_crop_auto(args):
    _check_ffmpeg()
    probe = subprocess.run(
        ["ffmpeg", "-i", args.input, "-vf", "cropdetect=24:16:0",
         "-frames:v", str(args.frames), "-f", "null", "-"],
        check=False, capture_output=True, text=True,
    )
    crop = None
    for line in (probe.stderr or "").splitlines():
        m = re.search(r"crop=(\d+:\d+:\d+:\d+)", line)
        if m:
            crop = m.group(1)
    if not crop:
        print("[!] cropdetect found no crop.")
        return 1
    print(f"Detected crop: {crop}")
    cmd = ["ffmpeg", "-y", "-i", args.input, "-vf", f"crop={crop}", args.output]
    return _run(cmd).returncode


def cmd_framerate(args):
    _check_ffmpeg()
    cmd = ["ffmpeg", "-y", "-i", args.input, "-r", str(args.fps), args.output]
    return _run(cmd).returncode


def cmd_mux(args):
    _check_ffmpeg()
    cmd = [
        "ffmpeg", "-y", "-i", args.video, "-i", args.audio,
        "-c:v", "copy", "-c:a", "aac", "-shortest", args.output,
    ]
    return _run(cmd).returncode


def cmd_frames(args):
    _check_ffmpeg()
    # Get duration
    p = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", args.input],
        check=False, capture_output=True, text=True,
    )
    try:
        dur = float(p.stdout.strip())
    except ValueError:
        print("[!] could not get duration")
        return 1
    out_dir = ensure_dir(Path(args.output))
    step = dur / (args.count + 1)
    for i in range(args.count):
        t = step * (i + 1)
        out = out_dir / f"frame_{i:03d}.png"
        _run(["ffmpeg", "-y", "-ss", str(t), "-i", args.input, "-frames:v", "1", str(out)])
    print(f"Extracted {args.count} frames -> {out_dir}")
    return 0


COMMANDS = {
    "scene-split":      "Split at scene cuts (ffmpeg scene detect)",
    "subtitle-burn":    "Burn .srt subtitles into video",
    "subtitle-extract": "Extract embedded subtitle stream",
    "auto-subtitle":    "STT via faster-whisper -> .srt",
    "denoise-video":    "Spatial+temporal denoise (hqdn3d)",
    "stabilize":        "Video stabilization (vidstab)",
    "slowmo":           "Slow motion (setpts)",
    "speedup":          "Fast forward (setpts + atempo)",
    "reverse":          "Reverse video and audio",
    "loop":             "Loop N times",
    "crop-auto":        "Auto-detect black bars and crop",
    "framerate":        "Change framerate",
    "mux":              "Mux a video file + an audio file",
    "frames":           "Extract N frames evenly distributed",
}


def build_parser(parser=None):
    parser = parser or argparse.ArgumentParser(prog="videopro_tools", description="Advanced video tools")
    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("scene-split", help=COMMANDS["scene-split"])
    p.add_argument("input"); p.add_argument("-o", "--output", default="scenes_out")
    p.add_argument("--threshold", type=float, default=0.4)
    p.set_defaults(func=cmd_scene_split)

    p = sub.add_parser("subtitle-burn", help=COMMANDS["subtitle-burn"])
    p.add_argument("input"); p.add_argument("output")
    p.add_argument("--srt", required=True)
    p.set_defaults(func=cmd_subtitle_burn)

    p = sub.add_parser("subtitle-extract", help=COMMANDS["subtitle-extract"])
    p.add_argument("input"); p.add_argument("output")
    p.add_argument("--index", type=int, default=0)
    p.set_defaults(func=cmd_subtitle_extract)

    p = sub.add_parser("auto-subtitle", help=COMMANDS["auto-subtitle"])
    p.add_argument("input"); p.add_argument("output")
    p.add_argument("--model", default="base")
    p.add_argument("--device", default="cpu", choices=["cpu", "cuda", "auto"])
    p.add_argument("--compute-type", default="int8")
    p.add_argument("--language")
    p.set_defaults(func=cmd_auto_subtitle)

    p = sub.add_parser("denoise-video", help=COMMANDS["denoise-video"])
    p.add_argument("input"); p.add_argument("output")
    p.add_argument("--luma", type=float, default=4)
    p.add_argument("--chroma", type=float, default=3)
    p.add_argument("--tluma", type=float, default=6)
    p.add_argument("--tchroma", type=float, default=4.5)
    p.set_defaults(func=cmd_denoise_video)

    p = sub.add_parser("stabilize", help=COMMANDS["stabilize"])
    p.add_argument("input"); p.add_argument("output")
    p.add_argument("--shakiness", type=int, default=5)
    p.add_argument("--smoothing", type=int, default=10)
    p.set_defaults(func=cmd_stabilize)

    p = sub.add_parser("slowmo", help=COMMANDS["slowmo"])
    p.add_argument("input"); p.add_argument("output")
    p.add_argument("--factor", type=float, default=2.0, help=">1 = slower")
    p.add_argument("--keep-audio", action="store_true")
    p.set_defaults(func=cmd_slowmo)

    p = sub.add_parser("speedup", help=COMMANDS["speedup"])
    p.add_argument("input"); p.add_argument("output")
    p.add_argument("--factor", type=float, default=2.0, help=">1 = faster")
    p.set_defaults(func=cmd_speedup)

    p = sub.add_parser("reverse", help=COMMANDS["reverse"])
    p.add_argument("input"); p.add_argument("output")
    p.set_defaults(func=cmd_reverse)

    p = sub.add_parser("loop", help=COMMANDS["loop"])
    p.add_argument("input"); p.add_argument("output")
    p.add_argument("--count", type=int, required=True)
    p.set_defaults(func=cmd_loop)

    p = sub.add_parser("crop-auto", help=COMMANDS["crop-auto"])
    p.add_argument("input"); p.add_argument("output")
    p.add_argument("--frames", type=int, default=120)
    p.set_defaults(func=cmd_crop_auto)

    p = sub.add_parser("framerate", help=COMMANDS["framerate"])
    p.add_argument("input"); p.add_argument("output")
    p.add_argument("--fps", type=float, required=True)
    p.set_defaults(func=cmd_framerate)

    p = sub.add_parser("mux", help=COMMANDS["mux"])
    p.add_argument("video"); p.add_argument("audio"); p.add_argument("output")
    p.set_defaults(func=cmd_mux)

    p = sub.add_parser("frames", help=COMMANDS["frames"])
    p.add_argument("input"); p.add_argument("-o", "--output", default="frames_out")
    p.add_argument("--count", type=int, default=10)
    p.set_defaults(func=cmd_frames)

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
