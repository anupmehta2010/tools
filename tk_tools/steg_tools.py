"""Steganography tools: hide/extract text or files in images and WAV via LSB; stash data in EXIF UserComment."""
from __future__ import annotations

import argparse
import struct
import wave
from pathlib import Path

from _common import lazy_import, tool_main

MAGIC = b"STG1"


def _pil():
    lazy_import("PIL", install_hint="pip install pillow")
    from PIL import Image
    return Image


def _bits_from_bytes(data: bytes):
    for byte in data:
        for i in range(7, -1, -1):
            yield (byte >> i) & 1


def _bytes_from_bits(bits):
    out = bytearray()
    b = 0; count = 0
    for bit in bits:
        b = (b << 1) | (bit & 1)
        count += 1
        if count == 8:
            out.append(b); b = 0; count = 0
    return bytes(out)


def _embed_bits_into_image(img, payload: bytes):
    cap = img.width * img.height * 3
    if len(payload) * 8 > cap:
        raise ValueError(f"Payload too large: need {len(payload) * 8} bits, capacity {cap}")
    pixels = list(img.getdata())
    new_pixels = []
    bit_iter = iter(_bits_from_bytes(payload))
    done = False
    for px in pixels:
        if done:
            new_pixels.append(px)
            continue
        r, g, b = px[0], px[1], px[2]
        rest = px[3:] if len(px) > 3 else ()
        new_chan = []
        for chan in (r, g, b):
            try:
                bit = next(bit_iter)
                new_chan.append((chan & 0xFE) | bit)
            except StopIteration:
                new_chan.append(chan)
                done = True
        new_pixels.append(tuple(new_chan) + rest)
    out = img.copy()
    out.putdata(new_pixels)
    return out


def _extract_bits_from_image(img, n_bits: int):
    bits = []
    for px in img.getdata():
        for chan in px[:3]:
            bits.append(chan & 1)
            if len(bits) >= n_bits:
                return bits
    return bits


def cmd_lsb_embed(args):
    Image = _pil()
    img = Image.open(args.input).convert("RGBA" if Path(args.input).suffix.lower() == ".png" else "RGB")
    msg = args.message.encode("utf-8") if args.message else Path(args.message_file).read_text(encoding="utf-8").encode("utf-8")
    header = MAGIC + struct.pack(">I", len(msg))
    payload = header + msg
    out = _embed_bits_into_image(img, payload)
    out.save(args.output, "PNG")
    print(f"Embedded {len(msg)} bytes -> {args.output}")


def cmd_lsb_extract(args):
    Image = _pil()
    img = Image.open(args.input)
    head_bits = _extract_bits_from_image(img, (len(MAGIC) + 4) * 8)
    head = _bytes_from_bits(head_bits)
    if head[: len(MAGIC)] != MAGIC:
        print("[!] no STG1 magic found")
        return 1
    n = struct.unpack(">I", head[len(MAGIC): len(MAGIC) + 4])[0]
    total_bits = (len(MAGIC) + 4 + n) * 8
    all_bits = _extract_bits_from_image(img, total_bits)
    data = _bytes_from_bits(all_bits)
    msg = data[len(MAGIC) + 4 :]
    text = msg.decode("utf-8", errors="replace")
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"Wrote {args.output}")
    else:
        print(text)


def cmd_lsb_embed_file(args):
    Image = _pil()
    img = Image.open(args.input).convert("RGBA" if Path(args.input).suffix.lower() == ".png" else "RGB")
    data = Path(args.file).read_bytes()
    name = Path(args.file).name.encode("utf-8")
    if len(name) > 255:
        name = name[:255]
    header = MAGIC + b"F" + bytes([len(name)]) + name + struct.pack(">Q", len(data))
    payload = header + data
    out = _embed_bits_into_image(img, payload)
    out.save(args.output, "PNG")
    print(f"Embedded file {args.file} ({len(data)} bytes) -> {args.output}")


def cmd_lsb_extract_file(args):
    Image = _pil()
    img = Image.open(args.input)
    head_bits = _extract_bits_from_image(img, (len(MAGIC) + 1 + 1) * 8)
    head = _bytes_from_bits(head_bits)
    if head[: len(MAGIC)] != MAGIC or head[len(MAGIC):len(MAGIC) + 1] != b"F":
        print("[!] no STG1 file magic")
        return 1
    name_len = head[-1]
    base_bits = (len(MAGIC) + 1 + 1) * 8
    name_bits = _extract_bits_from_image(img, base_bits + name_len * 8)
    name = _bytes_from_bits(name_bits)[-name_len:].decode("utf-8", errors="replace")
    size_bits = _extract_bits_from_image(img, base_bits + name_len * 8 + 8 * 8)
    size = struct.unpack(">Q", _bytes_from_bits(size_bits)[-8:])[0]
    total = base_bits + name_len * 8 + 8 * 8 + size * 8
    all_bits = _extract_bits_from_image(img, total)
    blob = _bytes_from_bits(all_bits)
    data = blob[-size:]
    out_path = Path(args.output) if args.output else Path(name)
    if out_path.is_dir():
        out_path = out_path / name
    out_path.write_bytes(data)
    print(f"Extracted {size} bytes -> {out_path}")


def cmd_exif_hide(args):
    Image = _pil()
    img = Image.open(args.input)
    msg = args.message.encode("utf-8")
    try:
        piexif = __import__("piexif")
        exif_dict = piexif.load(img.info.get("exif", b""))
        # UserComment with ASCII prefix
        exif_dict["Exif"][piexif.ExifIFD.UserComment] = b"ASCII\x00\x00\x00" + msg
        exif_bytes = piexif.dump(exif_dict)
        img.save(args.output, exif=exif_bytes)
        print(f"Hid {len(msg)} bytes in EXIF.UserComment (piexif) -> {args.output}")
    except ImportError:
        # Fallback: use PNG text chunks (or JPEG comment via Pillow info)
        from PIL import PngImagePlugin
        if Path(args.output).suffix.lower() == ".png":
            meta = PngImagePlugin.PngInfo()
            for k, v in (img.info or {}).items():
                if isinstance(v, str):
                    meta.add_text(k, v)
            meta.add_text("UserComment", args.message)
            img.save(args.output, "PNG", pnginfo=meta)
        else:
            img.save(args.output, comment=msg)
        print(f"Hid {len(msg)} bytes via Pillow image info -> {args.output}  (install piexif for true EXIF)")


def cmd_audio_lsb_embed(args):
    with wave.open(args.input, "rb") as w:
        params = w.getparams()
        frames = bytearray(w.readframes(w.getnframes()))
    if params.sampwidth != 2 and params.sampwidth != 1:
        print(f"[!] unsupported sample width: {params.sampwidth}")
        return 1
    msg = args.message.encode("utf-8")
    payload = MAGIC + struct.pack(">I", len(msg)) + msg
    cap = len(frames)
    if len(payload) * 8 > cap:
        print(f"[!] payload too large for cover ({len(payload) * 8} > {cap} bits)")
        return 1
    bi = iter(_bits_from_bytes(payload))
    for i in range(len(frames)):
        try:
            bit = next(bi)
        except StopIteration:
            break
        frames[i] = (frames[i] & 0xFE) | bit
    with wave.open(args.output, "wb") as w:
        w.setparams(params)
        w.writeframes(bytes(frames))
    print(f"Embedded {len(msg)} bytes -> {args.output}")


def cmd_audio_lsb_extract(args):
    with wave.open(args.input, "rb") as w:
        frames = w.readframes(w.getnframes())
    # read magic + length
    head_bits = [frames[i] & 1 for i in range((len(MAGIC) + 4) * 8)]
    head = _bytes_from_bits(head_bits)
    if head[: len(MAGIC)] != MAGIC:
        print("[!] no STG1 magic")
        return 1
    n = struct.unpack(">I", head[len(MAGIC):])[0]
    total = (len(MAGIC) + 4 + n) * 8
    bits = [frames[i] & 1 for i in range(total)]
    data = _bytes_from_bits(bits)
    text = data[len(MAGIC) + 4 :].decode("utf-8", errors="replace")
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"Wrote {args.output}")
    else:
        print(text)


COMMANDS = {
    "lsb-embed":         "Hide text in image LSB",
    "lsb-extract":       "Extract hidden text from image LSB",
    "lsb-embed-file":    "Hide a file inside an image (LSB, with header)",
    "lsb-extract-file":  "Extract hidden file from image",
    "exif-hide":         "Stuff text into EXIF UserComment (piexif fallback to Pillow info)",
    "audio-lsb-embed":   "Hide text in WAV via LSB",
    "audio-lsb-extract": "Extract hidden text from WAV",
}


def build_parser(parser=None):
    parser = parser or argparse.ArgumentParser(prog="steg_tools", description="Steganography utilities")
    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("lsb-embed", help=COMMANDS["lsb-embed"])
    p.add_argument("input"); p.add_argument("output")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--message")
    g.add_argument("--message-file")
    p.set_defaults(func=cmd_lsb_embed)

    p = sub.add_parser("lsb-extract", help=COMMANDS["lsb-extract"])
    p.add_argument("input")
    p.add_argument("-o", "--output")
    p.set_defaults(func=cmd_lsb_extract)

    p = sub.add_parser("lsb-embed-file", help=COMMANDS["lsb-embed-file"])
    p.add_argument("input"); p.add_argument("output")
    p.add_argument("--file", required=True)
    p.set_defaults(func=cmd_lsb_embed_file)

    p = sub.add_parser("lsb-extract-file", help=COMMANDS["lsb-extract-file"])
    p.add_argument("input")
    p.add_argument("-o", "--output")
    p.set_defaults(func=cmd_lsb_extract_file)

    p = sub.add_parser("exif-hide", help=COMMANDS["exif-hide"])
    p.add_argument("input"); p.add_argument("output")
    p.add_argument("--message", required=True)
    p.set_defaults(func=cmd_exif_hide)

    p = sub.add_parser("audio-lsb-embed", help=COMMANDS["audio-lsb-embed"])
    p.add_argument("input"); p.add_argument("output")
    p.add_argument("--message", required=True)
    p.set_defaults(func=cmd_audio_lsb_embed)

    p = sub.add_parser("audio-lsb-extract", help=COMMANDS["audio-lsb-extract"])
    p.add_argument("input")
    p.add_argument("-o", "--output")
    p.set_defaults(func=cmd_audio_lsb_extract)

    return parser


@tool_main("steg")
def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 1
    return args.func(args) or 0


if __name__ == "__main__":
    raise SystemExit(main())
