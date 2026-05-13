"""OLED & embedded display tools: image/video to C arrays, BMP, optimization, preview.

Designed for SSD1306, SSD1351, ILI9341, ST7789, ST7735, and other tiny embedded
displays driven from MCUs (ESP32, Arduino, Raspberry Pi Pico, etc).
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path

from _common import lazy_import


# Common display profiles. Add/extend freely.
DISPLAYS = {
    "ssd1306":      {"width": 128, "height": 64,  "format": "mono",   "name": 'SSD1306 0.96" OLED (mono)'},
    "ssd1306_72":   {"width": 72,  "height": 40,  "format": "mono",   "name": 'SSD1306 small (mono)'},
    "ssd1309":      {"width": 128, "height": 64,  "format": "mono",   "name": 'SSD1309 2.42" OLED (mono)'},
    "ssd1322":      {"width": 256, "height": 64,  "format": "gray4",  "name": 'SSD1322 grayscale OLED'},
    "ssd1327":      {"width": 128, "height": 128, "format": "gray4",  "name": 'SSD1327 grayscale OLED'},
    "ssd1351_96":   {"width": 96,  "height": 96,  "format": "rgb565", "name": 'SSD1351 0.95" RGB OLED'},
    "ssd1351_128":  {"width": 128, "height": 128, "format": "rgb565", "name": 'SSD1351 1.5" RGB OLED'},
    "ili9341":      {"width": 320, "height": 240, "format": "rgb565", "name": 'ILI9341 2.8" TFT'},
    "ili9488":      {"width": 480, "height": 320, "format": "rgb565", "name": 'ILI9488 3.5" TFT'},
    "st7789":       {"width": 240, "height": 240, "format": "rgb565", "name": 'ST7789 1.3" IPS'},
    "st7789_320":   {"width": 320, "height": 240, "format": "rgb565", "name": 'ST7789 2.0" IPS'},
    "st7735_160":   {"width": 160, "height": 128, "format": "rgb565", "name": 'ST7735 1.8" TFT'},
    "st7735_80":    {"width": 80,  "height": 160, "format": "rgb565", "name": 'ST7735S 0.96" TFT'},
    "epd_29":       {"width": 296, "height": 128, "format": "mono",   "name": 'Waveshare 2.9" e-paper'},
    "epd_42":       {"width": 400, "height": 300, "format": "mono",   "name": 'Waveshare 4.2" e-paper'},
    "matrix_64x32": {"width": 64,  "height": 32,  "format": "rgb888", "name": 'HUB75 LED matrix 64x32'},
    "matrix_64x64": {"width": 64,  "height": 64,  "format": "rgb888", "name": 'HUB75 LED matrix 64x64'},
}


def cmd_displays(args):
    print(f"{'Key':<14} {'W':>4} x {'H':>4}  {'Format':<8}  Name")
    print("-" * 72)
    for key, spec in DISPLAYS.items():
        print(f"{key:<14} {spec['width']:>4} x {spec['height']:>4}  {spec['format']:<8}  {spec['name']}")


def _resize_for(img, w, h, fit_mode):
    from PIL import Image
    if fit_mode == "stretch":
        return img.resize((w, h), Image.LANCZOS)
    if fit_mode == "fit":
        img2 = img.copy()
        img2.thumbnail((w, h), Image.LANCZOS)
        bg = (0, 0, 0) if img2.mode in ("RGB", "RGBA") else 0
        if img2.mode == "RGBA":
            bg = (0, 0, 0, 0)
        canvas = Image.new(img2.mode, (w, h), bg)
        ox = (w - img2.width) // 2
        oy = (h - img2.height) // 2
        canvas.paste(img2, (ox, oy))
        return canvas
    if fit_mode == "cover":
        sw, sh = img.size
        scale = max(w / sw, h / sh)
        new = (max(1, int(sw * scale)), max(1, int(sh * scale)))
        img = img.resize(new, Image.LANCZOS)
        cx = (img.width - w) // 2
        cy = (img.height - h) // 2
        return img.crop((cx, cy, cx + w, cy + h))
    return img


def _to_mono_bytes(img, threshold=128, dither=True):
    from PIL import Image
    if dither:
        bw = img.convert("1")
    else:
        bw = img.convert("L").point(lambda p: 255 if p >= threshold else 0).convert("1")
    w, h = bw.size
    pixels = bw.load()
    out = bytearray()
    for y in range(h):
        for xb in range((w + 7) // 8):
            byte = 0
            for bit in range(8):
                x = xb * 8 + bit
                if x < w and pixels[x, y]:
                    byte |= 1 << (7 - bit)
            out.append(byte)
    return bytes(out)


def _to_rgb565_bytes(img, big_endian=True):
    img = img.convert("RGB")
    out = bytearray()
    for r, g, b in img.getdata():
        v = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
        if big_endian:
            out.append((v >> 8) & 0xFF); out.append(v & 0xFF)
        else:
            out.append(v & 0xFF); out.append((v >> 8) & 0xFF)
    return bytes(out)


def _to_rgb888_bytes(img):
    img = img.convert("RGB")
    out = bytearray()
    for r, g, b in img.getdata():
        out += bytes([r, g, b])
    return bytes(out)


def _to_gray4_bytes(img):
    """Pack two 4-bit pixels per byte (high nibble = first pixel)."""
    img = img.convert("L")
    w, h = img.size
    pixels = list(img.getdata())
    out = bytearray()
    i = 0
    while i < len(pixels):
        a = pixels[i] >> 4
        b = pixels[i + 1] >> 4 if (i + 1) < len(pixels) else 0
        out.append((a << 4) | b)
        i += 2
    return bytes(out)


def _bytes_to_c_array(data, varname, width, height, fmt, header=None):
    lines = []
    if header:
        lines.append(f"// {header}")
    lines.append(f"// {varname}: {width}x{height}, format={fmt}, {len(data)} bytes")
    lines.append(f"const unsigned char {varname}[] = {{")
    BPL = 16
    for i in range(0, len(data), BPL):
        chunk = data[i:i + BPL]
        lines.append("  " + ", ".join(f"0x{b:02X}" for b in chunk) + ",")
    lines.append("};")
    lines.append(f"const unsigned int {varname}_len    = {len(data)};")
    lines.append(f"const unsigned int {varname}_width  = {width};")
    lines.append(f"const unsigned int {varname}_height = {height};")
    return "\n".join(lines)


def _resolve_target(args, default_w=128, default_h=64, default_fmt="rgb565"):
    if args.display:
        if args.display not in DISPLAYS:
            raise SystemExit(f"Unknown display: {args.display}. Use 'oled displays' to list profiles.")
        spec = DISPLAYS[args.display]
        w = args.width or spec["width"]
        h = args.height or spec["height"]
        fmt = args.format or spec["format"]
    else:
        w = args.width or default_w
        h = args.height or default_h
        fmt = args.format or default_fmt
    return w, h, fmt


def _encode_pixels(img, fmt, *, threshold, dither, little_endian):
    if fmt == "mono":
        return _to_mono_bytes(img, threshold=threshold, dither=dither)
    if fmt == "rgb565":
        return _to_rgb565_bytes(img, big_endian=not little_endian)
    if fmt == "rgb888":
        return _to_rgb888_bytes(img)
    if fmt == "gray4":
        return _to_gray4_bytes(img)
    raise SystemExit(f"Unsupported format: {fmt}")


def cmd_image_to_c(args):
    lazy_import("PIL", install_hint="pip install pillow")
    from PIL import Image, ImageOps
    img = Image.open(args.input)
    w, h, fmt = _resolve_target(args)
    img = _resize_for(img, w, h, args.fit)
    if args.invert:
        if img.mode in ("RGB", "RGBA"):
            r = img.convert("RGB")
            img = ImageOps.invert(r)
        else:
            img = ImageOps.invert(img.convert("L"))
    data = _encode_pixels(img, fmt,
                          threshold=args.threshold,
                          dither=args.dither,
                          little_endian=args.little_endian)
    code = _bytes_to_c_array(data, args.varname, w, h, fmt,
                             header=f"Generated from {Path(args.input).name}")
    if args.output:
        Path(args.output).write_text(code, encoding="utf-8")
        print(f"Wrote {args.output} ({len(data):,} bytes of pixel data)")
    else:
        print(code)


def cmd_preview(args):
    lazy_import("PIL", install_hint="pip install pillow")
    from PIL import Image
    if args.display:
        if args.display not in DISPLAYS:
            print(f"Unknown display: {args.display}")
            return 1
        spec = DISPLAYS[args.display]
        w, h = spec["width"], spec["height"]
        fmt = args.format or spec["format"]
    else:
        w = args.width or 128
        h = args.height or 64
        fmt = args.format or "mono"
    img = Image.open(args.input)
    img = _resize_for(img, w, h, args.fit)
    if fmt == "mono":
        if args.dither:
            preview = img.convert("1").convert("RGB")
        else:
            preview = img.convert("L").point(lambda p: 255 if p >= args.threshold else 0).convert("RGB")
    elif fmt == "gray4":
        preview = img.convert("L").quantize(colors=16).convert("RGB")
    elif fmt == "rgb565":
        rgb = img.convert("RGB")
        out = bytearray()
        for r, g, b in rgb.getdata():
            r2 = (r & 0xF8) | (r >> 5)
            g2 = (g & 0xFC) | (g >> 6)
            b2 = (b & 0xF8) | (b >> 5)
            out += bytes([r2, g2, b2])
        preview = Image.frombytes("RGB", (w, h), bytes(out))
    else:
        preview = img.convert("RGB")
    big = preview.resize((w * args.scale, h * args.scale), Image.NEAREST)
    big.save(args.output)
    print(f"Wrote preview ({w * args.scale} x {h * args.scale}) -> {args.output}")


def cmd_video_to_c(args):
    lazy_import("PIL", install_hint="pip install pillow")
    from PIL import Image
    if shutil.which("ffmpeg") is None:
        print("[!] ffmpeg required for video extraction.")
        return 2
    w, h, fmt = _resolve_target(args, default_w=128, default_h=64, default_fmt="mono")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        cmd = [
            "ffmpeg", "-y", "-i", args.input,
            "-vf", f"fps={args.fps},scale={w}:{h}:flags=lanczos",
        ]
        if args.frames:
            cmd += ["-frames:v", str(args.frames)]
        cmd.append(str(tmp_dir / "f%05d.png"))
        print("$", " ".join(cmd))
        rc = subprocess.call(cmd)
        if rc != 0:
            return rc
        frame_files = sorted(tmp_dir.glob("f*.png"))
        if not frame_files:
            print("No frames extracted.")
            return 1
        all_data = bytearray()
        frame_size = 0
        for f in frame_files:
            img = Image.open(f)
            data = _encode_pixels(img, fmt,
                                  threshold=args.threshold,
                                  dither=args.dither,
                                  little_endian=args.little_endian)
            all_data.extend(data)
            frame_size = len(data)
        var = args.varname
        lines = [
            f"// Animation from {Path(args.input).name}: {len(frame_files)} frames @ {args.fps} fps",
            f"// {w}x{h}, format={fmt}, {frame_size:,} bytes/frame, {len(all_data):,} bytes total",
            f"const unsigned char {var}[] = {{",
        ]
        BPL = 16
        for i in range(0, len(all_data), BPL):
            chunk = all_data[i:i + BPL]
            lines.append("  " + ", ".join(f"0x{b:02X}" for b in chunk) + ",")
        lines.append("};")
        lines.append(f"const unsigned int {var}_frames     = {len(frame_files)};")
        lines.append(f"const unsigned int {var}_frame_size = {frame_size};")
        lines.append(f"const unsigned int {var}_width      = {w};")
        lines.append(f"const unsigned int {var}_height     = {h};")
        lines.append(f"const unsigned int {var}_fps        = {args.fps};")
        code = "\n".join(lines)
        if args.output:
            Path(args.output).write_text(code, encoding="utf-8")
            print(f"Wrote {args.output} ({len(frame_files)} frames, {len(all_data):,} bytes)")
        else:
            print(code)


def cmd_optimize_video(args):
    if shutil.which("ffmpeg") is None:
        print("[!] ffmpeg required.")
        return 2
    if args.display:
        if args.display not in DISPLAYS:
            print(f"Unknown display: {args.display}")
            return 1
        spec = DISPLAYS[args.display]
        w, h = spec["width"], spec["height"]
    else:
        w = args.width
        h = args.height
    cmd = [
        "ffmpeg", "-y", "-i", args.input,
        "-vf", f"scale={w}:{h}:flags=lanczos,fps={args.fps}",
        "-c:v", args.codec,
    ]
    if args.codec == "mjpeg":
        cmd += ["-q:v", str(args.quality)]
    elif args.codec == "libx264":
        cmd += ["-crf", str(args.quality), "-preset", "veryfast"]
    if args.no_audio:
        cmd += ["-an"]
    cmd.append(args.output)
    print("$", " ".join(cmd))
    return subprocess.call(cmd)


def cmd_bitmap(args):
    lazy_import("PIL", install_hint="pip install pillow")
    from PIL import Image
    if args.display:
        if args.display not in DISPLAYS:
            print(f"Unknown display: {args.display}")
            return 1
        spec = DISPLAYS[args.display]
        w, h = spec["width"], spec["height"]
    else:
        w = args.width
        h = args.height
    img = Image.open(args.input).convert("RGB")
    img = _resize_for(img, w, h, args.fit)
    img.save(args.output, "BMP")
    print(f"Wrote {args.output} ({w}x{h})")


def cmd_gif_to_frames(args):
    """Extract animated GIF frames as a series of PNGs (and an index file)."""
    lazy_import("PIL", install_hint="pip install pillow")
    from PIL import Image
    out_dir = Path(args.outdir)
    out_dir.mkdir(parents=True, exist_ok=True)
    img = Image.open(args.input)
    n = 0
    durations = []
    while True:
        try:
            img.seek(n)
        except EOFError:
            break
        frame = img.convert("RGBA")
        frame.save(out_dir / f"frame_{n:04d}.png")
        durations.append(img.info.get("duration", 100))
        n += 1
    (out_dir / "frames.txt").write_text(
        "\n".join(f"frame_{i:04d}.png  {d}ms" for i, d in enumerate(durations)),
        encoding="utf-8",
    )
    print(f"Extracted {n} frame(s) -> {out_dir}/")


def cmd_u8g2_format(args):
    """Output XBM-style C array for U8g2's drawXBM(): rows of bytes, LSB-first per byte."""
    lazy_import("PIL", install_hint="pip install pillow")
    from PIL import Image
    img = Image.open(args.input)
    w, h, _ = _resolve_target(args, default_w=128, default_h=64, default_fmt="mono")
    img = _resize_for(img, w, h, args.fit)
    if args.invert:
        from PIL import ImageOps
        img = ImageOps.invert(img.convert("L"))
    bw = img.convert("1") if args.dither else img.convert("L").point(
        lambda p: 255 if p >= args.threshold else 0).convert("1")
    pixels = bw.load()
    out = bytearray()
    for y in range(h):
        for xb in range((w + 7) // 8):
            byte = 0
            for bit in range(8):
                x = xb * 8 + bit
                if x < w and pixels[x, y]:
                    byte |= 1 << bit
            out.append(byte)
    var = args.varname
    lines = [
        f"// U8g2-style XBM bitmap for {var}: {w}x{h}",
        f"#define {var}_width  {w}",
        f"#define {var}_height {h}",
        f"static const unsigned char {var}_bits[] U8X8_PROGMEM = {{",
    ]
    BPL = 12
    for i in range(0, len(out), BPL):
        chunk = out[i:i + BPL]
        lines.append("  " + ", ".join(f"0x{b:02X}" for b in chunk) + ",")
    lines.append("};")
    code = "\n".join(lines)
    if args.output:
        Path(args.output).write_text(code, encoding="utf-8")
        print(f"Wrote {args.output}  ({len(out)} bytes pixel data)")
    else:
        print(code)


def cmd_adafruit_format(args):
    """Output Adafruit_GFX-style C array for drawBitmap(): rows of bytes, MSB-first per byte."""
    lazy_import("PIL", install_hint="pip install pillow")
    from PIL import Image
    img = Image.open(args.input)
    w, h, _ = _resolve_target(args, default_w=128, default_h=64, default_fmt="mono")
    img = _resize_for(img, w, h, args.fit)
    if args.invert:
        from PIL import ImageOps
        img = ImageOps.invert(img.convert("L"))
    data = _to_mono_bytes(img, threshold=args.threshold, dither=args.dither)
    var = args.varname
    lines = [
        f"// Adafruit GFX-style bitmap for {var}: {w}x{h}",
        f"// Use with: display.drawBitmap(0, 0, {var}, {w}, {h}, WHITE);",
        f"const uint8_t {var}[] PROGMEM = {{",
    ]
    BPL = 12
    for i in range(0, len(data), BPL):
        chunk = data[i:i + BPL]
        lines.append("  " + ", ".join(f"0x{b:02X}" for b in chunk) + ",")
    lines.append("};")
    code = "\n".join(lines)
    if args.output:
        Path(args.output).write_text(code, encoding="utf-8")
        print(f"Wrote {args.output}  ({len(data)} bytes pixel data)")
    else:
        print(code)


def cmd_palette(args):
    """Quantize image to N-color palette (good for tiny RGB displays)."""
    lazy_import("PIL", install_hint="pip install pillow")
    from PIL import Image
    img = Image.open(args.input).convert("RGB")
    if args.display:
        if args.display in DISPLAYS:
            spec = DISPLAYS[args.display]
            img = _resize_for(img, spec["width"], spec["height"], args.fit)
    pal = img.quantize(colors=args.colors)
    pal.convert("RGB").save(args.output)
    print(f"Wrote {args.output} ({args.colors}-color palette)")


COMMANDS = {
    "displays":        "list built-in display profiles",
    "image-to-c":      "convert image to C/C++ array (mono/gray4/rgb565/rgb888)",
    "video-to-c":      "extract video frames and emit as C array animation",
    "preview":         "render preview at target display's resolution + color depth",
    "optimize-video":  "re-encode video for embedded playback (low-res, mjpeg)",
    "bitmap":          "save image as 24-bit BMP at target display's resolution",
    "gif-to-frames":   "split GIF into PNG frames (with timing index)",
    "palette":         "quantize image to N-color palette",
    "u8g2-format":     "image -> U8g2 XBM-style C array (LSB-first)",
    "adafruit-format": "image -> Adafruit_GFX C array (MSB-first)",
}


def _add_format_args(p):
    p.add_argument("--display", choices=list(DISPLAYS), help="display profile (presets W/H/format)")
    p.add_argument("--width", type=int)
    p.add_argument("--height", type=int)
    p.add_argument("--format", choices=["mono", "gray4", "rgb565", "rgb888"])
    p.add_argument("--fit", choices=["stretch", "fit", "cover"], default="fit")
    p.add_argument("--invert", action="store_true")
    p.add_argument("--threshold", type=int, default=128, help="for mono")
    p.add_argument("--dither", action="store_true", help="Floyd-Steinberg dither (mono)")
    p.add_argument("--little-endian", action="store_true", help="for rgb565 byte order")


def build_parser(parser=None):
    parser = parser or argparse.ArgumentParser(prog="oled_tools", description="OLED & embedded display utilities")
    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("displays", help=COMMANDS["displays"])
    p.set_defaults(func=cmd_displays)

    p = sub.add_parser("image-to-c", help=COMMANDS["image-to-c"])
    p.add_argument("input")
    p.add_argument("-o", "--output")
    _add_format_args(p)
    p.add_argument("--varname", default="image_data")
    p.set_defaults(func=cmd_image_to_c)

    p = sub.add_parser("video-to-c", help=COMMANDS["video-to-c"])
    p.add_argument("input")
    p.add_argument("-o", "--output")
    _add_format_args(p)
    p.add_argument("--fps", type=int, default=10)
    p.add_argument("--frames", type=int, default=60, help="max frames")
    p.add_argument("--varname", default="video_frames")
    p.set_defaults(func=cmd_video_to_c)

    p = sub.add_parser("preview", help=COMMANDS["preview"])
    p.add_argument("input")
    p.add_argument("output")
    p.add_argument("--display", choices=list(DISPLAYS))
    p.add_argument("--width", type=int)
    p.add_argument("--height", type=int)
    p.add_argument("--format", choices=["mono", "gray4", "rgb565", "rgb888"])
    p.add_argument("--fit", choices=["stretch", "fit", "cover"], default="fit")
    p.add_argument("--threshold", type=int, default=128)
    p.add_argument("--dither", action="store_true")
    p.add_argument("--scale", type=int, default=4, help="pixel scale-up for visual preview")
    p.set_defaults(func=cmd_preview)

    p = sub.add_parser("optimize-video", help=COMMANDS["optimize-video"])
    p.add_argument("input")
    p.add_argument("output")
    p.add_argument("--display", choices=list(DISPLAYS))
    p.add_argument("--width", type=int, default=320)
    p.add_argument("--height", type=int, default=240)
    p.add_argument("--fps", type=int, default=15)
    p.add_argument("--codec", default="mjpeg", choices=["mjpeg", "libx264"])
    p.add_argument("--quality", type=int, default=5)
    p.add_argument("--no-audio", action="store_true")
    p.set_defaults(func=cmd_optimize_video)

    p = sub.add_parser("bitmap", help=COMMANDS["bitmap"])
    p.add_argument("input")
    p.add_argument("output")
    p.add_argument("--display", choices=list(DISPLAYS))
    p.add_argument("--width", type=int)
    p.add_argument("--height", type=int)
    p.add_argument("--fit", choices=["stretch", "fit", "cover"], default="fit")
    p.set_defaults(func=cmd_bitmap)

    p = sub.add_parser("gif-to-frames", help=COMMANDS["gif-to-frames"])
    p.add_argument("input")
    p.add_argument("-d", "--outdir", required=True)
    p.set_defaults(func=cmd_gif_to_frames)

    p = sub.add_parser("palette", help=COMMANDS["palette"])
    p.add_argument("input"); p.add_argument("output")
    p.add_argument("--colors", type=int, default=16)
    p.add_argument("--display", choices=list(DISPLAYS))
    p.add_argument("--fit", choices=["stretch", "fit", "cover"], default="fit")
    p.set_defaults(func=cmd_palette)

    p = sub.add_parser("u8g2-format", help=COMMANDS["u8g2-format"])
    p.add_argument("input")
    p.add_argument("-o", "--output")
    _add_format_args(p)
    p.add_argument("--varname", default="bitmap")
    p.set_defaults(func=cmd_u8g2_format)

    p = sub.add_parser("adafruit-format", help=COMMANDS["adafruit-format"])
    p.add_argument("input")
    p.add_argument("-o", "--output")
    _add_format_args(p)
    p.add_argument("--varname", default="bitmap")
    p.set_defaults(func=cmd_adafruit_format)

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
