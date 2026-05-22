"""Advanced audio tools: normalize, denoise, bpm, spectrogram, waveform, pitch, tempo, stems, silence-trim, loudness."""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

from _common import lazy_import, human_size, ensure_dir, confirm, tool_main


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


def cmd_normalize(args):
    _check_ffmpeg()
    cmd = [
        "ffmpeg", "-y", "-i", args.input,
        "-af", "loudnorm=I=-16:LRA=11:TP=-1.5",
        args.output,
    ]
    r = _run(cmd)
    return r.returncode


def cmd_denoise(args):
    _check_ffmpeg()
    cmd = ["ffmpeg", "-y", "-i", args.input, "-af", f"afftdn=nf={args.nf}", args.output]
    r = _run(cmd)
    return r.returncode


def cmd_bpm(args):
    librosa = lazy_import("librosa", install_hint="pip install librosa")
    y, sr = librosa.load(args.input, sr=None, mono=True)
    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    bpm = float(tempo) if hasattr(tempo, "__float__") else float(tempo[0])
    print(f"BPM: {bpm:.2f}")


def cmd_spectrogram(args):
    _check_ffmpeg()
    cmd = [
        "ffmpeg", "-y", "-i", args.input,
        "-lavfi", f"showspectrumpic=s={args.width}x{args.height}:legend=1",
        args.output,
    ]
    r = _run(cmd)
    return r.returncode


def cmd_waveform(args):
    _check_ffmpeg()
    cmd = [
        "ffmpeg", "-y", "-i", args.input,
        "-filter_complex", f"showwavespic=s={args.width}x{args.height}:colors={args.color}",
        "-frames:v", "1",
        args.output,
    ]
    r = _run(cmd)
    return r.returncode


def cmd_pitch(args):
    _check_ffmpeg()
    semitones = args.semitones
    if args.engine == "rubberband":
        af = f"rubberband=pitch={2 ** (semitones / 12)}"
    else:
        # asetrate / aresample preserves duration only if combined with atempo
        factor = 2 ** (semitones / 12)
        # change sample rate then resample back, then correct tempo
        # build atempo chain to undo
        s = 1.0 / factor
        atempos = []
        while s > 2.0:
            atempos.append(2.0); s /= 2.0
        while s < 0.5:
            atempos.append(0.5); s /= 0.5
        atempos.append(s)
        chain = ",".join(f"atempo={x}" for x in atempos)
        af = f"asetrate=44100*{factor},aresample=44100,{chain}"
    cmd = ["ffmpeg", "-y", "-i", args.input, "-af", af, args.output]
    r = _run(cmd)
    return r.returncode


def cmd_tempo(args):
    _check_ffmpeg()
    s = args.factor
    chain = []
    while s > 2.0:
        chain.append(2.0); s /= 2.0
    while s < 0.5:
        chain.append(0.5); s /= 0.5
    chain.append(s)
    af = ",".join(f"atempo={x}" for x in chain)
    cmd = ["ffmpeg", "-y", "-i", args.input, "-af", af, args.output]
    r = _run(cmd)
    return r.returncode


def cmd_stems(args):
    if shutil.which("demucs") is None:
        # try as python module
        lazy_import("demucs", install_hint="pip install demucs")
    out_dir = ensure_dir(Path(args.output))
    cmd = ["demucs", "-n", args.model, "-o", str(out_dir), args.input]
    r = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if r.returncode != 0:
        print("[!] demucs failed.")
        print(r.stderr or r.stdout)
        print("    Install: pip install demucs")
        return r.returncode
    print(r.stdout)
    print(f"Stems -> {out_dir}")


def cmd_silence_trim(args):
    _check_ffmpeg()
    af = (
        f"silenceremove=start_periods=1:start_silence={args.start}:start_threshold={args.threshold}dB:"
        f"stop_periods=-1:stop_silence={args.start}:stop_threshold={args.threshold}dB"
    )
    cmd = ["ffmpeg", "-y", "-i", args.input, "-af", af, args.output]
    r = _run(cmd)
    return r.returncode


def cmd_loudness(args):
    _check_ffmpeg()
    cmd = ["ffmpeg", "-hide_banner", "-nostats", "-i", args.input, "-af", "ebur128=peak=true", "-f", "null", "-"]
    r = _run(cmd, capture=True)
    # ebur128 writes to stderr
    text = (r.stderr or "") + (r.stdout or "")
    # Find Summary block
    m = re.search(r"Summary:\s*(.*?)(?:\n\s*\n|$)", text, re.S)
    if m:
        print(m.group(0))
    else:
        # print last 30 lines
        for line in text.splitlines()[-30:]:
            print(line)
    return 0


COMMANDS = {
    "normalize":    "Loudness normalization (loudnorm I=-16)",
    "denoise":      "Spectral denoise (afftdn)",
    "bpm":          "Detect BPM (librosa)",
    "spectrogram":  "Render spectrogram as PNG (ffmpeg showspectrumpic)",
    "waveform":     "Render waveform as PNG (ffmpeg showwavespic)",
    "pitch":        "Pitch-shift by N semitones",
    "tempo":        "Change tempo without pitch (atempo chain)",
    "stems":        "Split into vocals/drums/bass/other (demucs)",
    "silence-trim": "Trim leading/trailing silence",
    "loudness":     "Measure integrated LUFS (ebur128)",
}


def build_parser(parser=None):
    parser = parser or argparse.ArgumentParser(prog="audiopro_tools", description="Advanced audio tools")
    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("normalize", help=COMMANDS["normalize"])
    p.add_argument("input"); p.add_argument("output")
    p.set_defaults(func=cmd_normalize)

    p = sub.add_parser("denoise", help=COMMANDS["denoise"])
    p.add_argument("input"); p.add_argument("output")
    p.add_argument("--nf", type=int, default=-25, help="noise floor in dB")
    p.set_defaults(func=cmd_denoise)

    p = sub.add_parser("bpm", help=COMMANDS["bpm"])
    p.add_argument("input")
    p.set_defaults(func=cmd_bpm)

    p = sub.add_parser("spectrogram", help=COMMANDS["spectrogram"])
    p.add_argument("input"); p.add_argument("output")
    p.add_argument("--width", type=int, default=1024)
    p.add_argument("--height", type=int, default=512)
    p.set_defaults(func=cmd_spectrogram)

    p = sub.add_parser("waveform", help=COMMANDS["waveform"])
    p.add_argument("input"); p.add_argument("output")
    p.add_argument("--width", type=int, default=1200)
    p.add_argument("--height", type=int, default=300)
    p.add_argument("--color", default="0x00aaff")
    p.set_defaults(func=cmd_waveform)

    p = sub.add_parser("pitch", help=COMMANDS["pitch"])
    p.add_argument("input"); p.add_argument("output")
    p.add_argument("--semitones", type=float, required=True)
    p.add_argument("--engine", default="asetrate", choices=["asetrate", "rubberband"])
    p.set_defaults(func=cmd_pitch)

    p = sub.add_parser("tempo", help=COMMANDS["tempo"])
    p.add_argument("input"); p.add_argument("output")
    p.add_argument("--factor", type=float, required=True, help="1.5 = 1.5x faster")
    p.set_defaults(func=cmd_tempo)

    p = sub.add_parser("stems", help=COMMANDS["stems"])
    p.add_argument("input")
    p.add_argument("-o", "--output", default="stems_out")
    p.add_argument("--model", default="htdemucs")
    p.set_defaults(func=cmd_stems)

    p = sub.add_parser("silence-trim", help=COMMANDS["silence-trim"])
    p.add_argument("input"); p.add_argument("output")
    p.add_argument("--threshold", type=float, default=-50.0, help="dB threshold")
    p.add_argument("--start", type=float, default=0.5, help="min silence seconds")
    p.set_defaults(func=cmd_silence_trim)

    p = sub.add_parser("loudness", help=COMMANDS["loudness"])
    p.add_argument("input")
    p.set_defaults(func=cmd_loudness)

    return parser


@tool_main("audio-pro")
def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 1
    return args.func(args) or 0


if __name__ == "__main__":
    raise SystemExit(main())
