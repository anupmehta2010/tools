"""Local AI helpers: ollama summarize/chat, STT, TTS, rembg, embeddings."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path

from _common import lazy_import, tool_main


OLLAMA_URL = "http://localhost:11434/api/generate"


def _ollama_generate(prompt: str, model: str) -> str:
    payload = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode("utf-8")
    req = urllib.request.Request(OLLAMA_URL, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.URLError as e:
        print(f"[!] Could not reach ollama at {OLLAMA_URL}: {e}")
        print("    Make sure ollama is running: `ollama serve`")
        raise SystemExit(2)
    return data.get("response", "")


# ---- Command implementations ----

def cmd_summarize(args):
    """Summarize text via local ollama HTTP."""
    if args.input:
        text = Path(args.input).read_text(encoding="utf-8")
    else:
        text = sys.stdin.read()
    prompt = f"Summarize the following text in {args.sentences} sentences:\n\n{text}"
    out = _ollama_generate(prompt, args.model)
    if args.output:
        Path(args.output).write_text(out, encoding="utf-8")
        print(f"Wrote {args.output}")
    else:
        print(out)


def cmd_chat(args):
    """One-shot prompt via ollama."""
    prompt = args.prompt if args.prompt else sys.stdin.read()
    out = _ollama_generate(prompt, args.model)
    if args.output:
        Path(args.output).write_text(out, encoding="utf-8")
        print(f"Wrote {args.output}")
    else:
        print(out)


def cmd_stt(args):
    """Speech-to-text via faster-whisper."""
    fw = lazy_import("faster_whisper", "pip install faster-whisper")
    model = fw.WhisperModel(args.model, device="cpu", compute_type="int8")
    segments, info = model.transcribe(args.input, beam_size=5)
    parts = []
    for seg in segments:
        parts.append(seg.text.strip())
    text = " ".join(parts).strip()
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"Wrote {args.output} ({info.language}, {info.duration:.1f}s)")
    else:
        print(text)


def cmd_tts(args):
    """Text-to-speech via pyttsx3 (fallback) or piper if available."""
    text = args.text if args.text else (Path(args.input).read_text(encoding="utf-8") if args.input else sys.stdin.read())
    out_path = Path(args.output) if args.output else Path("tts.wav")
    if shutil.which("piper"):
        import subprocess
        proc = subprocess.run(
            ["piper", "--output_file", str(out_path)],
            input=text, text=True, capture_output=True, check=False,
        )
        if proc.returncode != 0:
            print(f"[!] piper failed: {proc.stderr}")
            return 1
        print(f"Wrote {out_path} (piper)")
        return 0
    pyttsx3 = lazy_import("pyttsx3", "pip install pyttsx3")
    engine = pyttsx3.init()
    if args.rate:
        engine.setProperty("rate", args.rate)
    engine.save_to_file(text, str(out_path))
    engine.runAndWait()
    print(f"Wrote {out_path} (pyttsx3)")


def cmd_rembg(args):
    """Remove background from image."""
    rembg = lazy_import("rembg", "pip install rembg")
    src = Path(args.input).read_bytes()
    out_bytes = rembg.remove(src)
    out_path = Path(args.output) if args.output else Path(args.input).with_suffix(".rembg.png")
    out_path.write_bytes(out_bytes)
    print(f"Wrote {out_path}")


def cmd_embed(args):
    """Text -> embedding vector (JSON) via sentence-transformers."""
    st = lazy_import("sentence_transformers", "pip install sentence-transformers")
    model = st.SentenceTransformer(args.model)
    if args.input:
        texts = Path(args.input).read_text(encoding="utf-8").splitlines()
        texts = [t for t in texts if t.strip()]
    elif args.text:
        texts = [args.text]
    else:
        texts = [sys.stdin.read()]
    vecs = model.encode(texts).tolist()
    out = vecs[0] if len(vecs) == 1 else vecs
    payload = json.dumps(out)
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
        print(f"Wrote {args.output}")
    else:
        print(payload)


# ---- COMMANDS dict ----
COMMANDS = {
    "summarize": "summarize text via local ollama",
    "chat":      "one-shot prompt via ollama",
    "stt":       "audio -> text via faster-whisper",
    "tts":       "text -> wav via piper or pyttsx3",
    "rembg":     "remove background from image",
    "embed":     "text -> embedding vector JSON",
}


def build_parser(parser=None):
    parser = parser or argparse.ArgumentParser(prog="ai_tools", description="Local AI helpers")
    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("summarize", help=COMMANDS["summarize"])
    p.add_argument("-i", "--input")
    p.add_argument("-o", "--output")
    p.add_argument("--model", default="llama3.2")
    p.add_argument("--sentences", type=int, default=5)
    p.set_defaults(func=cmd_summarize)

    p = sub.add_parser("chat", help=COMMANDS["chat"])
    p.add_argument("prompt", nargs="?")
    p.add_argument("-o", "--output")
    p.add_argument("--model", default="llama3.2")
    p.set_defaults(func=cmd_chat)

    p = sub.add_parser("stt", help=COMMANDS["stt"])
    p.add_argument("input")
    p.add_argument("-o", "--output")
    p.add_argument("--model", default="base")
    p.set_defaults(func=cmd_stt)

    p = sub.add_parser("tts", help=COMMANDS["tts"])
    p.add_argument("text", nargs="?")
    p.add_argument("-i", "--input")
    p.add_argument("-o", "--output")
    p.add_argument("--rate", type=int)
    p.set_defaults(func=cmd_tts)

    p = sub.add_parser("rembg", help=COMMANDS["rembg"])
    p.add_argument("input")
    p.add_argument("-o", "--output")
    p.set_defaults(func=cmd_rembg)

    p = sub.add_parser("embed", help=COMMANDS["embed"])
    p.add_argument("text", nargs="?")
    p.add_argument("-i", "--input")
    p.add_argument("-o", "--output")
    p.add_argument("--model", default="all-MiniLM-L6-v2")
    p.set_defaults(func=cmd_embed)

    return parser


@tool_main("ai")
def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 1
    return args.func(args) or 0


if __name__ == "__main__":
    raise SystemExit(main())
