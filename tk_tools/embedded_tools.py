"""Embedded/MCU helpers: hex/srec, bin/C conversion, font->bmp, serial, CRCs."""
from __future__ import annotations

import argparse
import re
import sys
import zlib
from pathlib import Path

from _common import lazy_import, human_size, tool_main


# ---- hexview ----

def _hexdump_bytes(data: bytes, base: int = 0) -> str:
    lines = []
    for off in range(0, len(data), 16):
        chunk = data[off:off + 16]
        hexs = " ".join(f"{b:02x}" for b in chunk).ljust(48)
        ascii_ = "".join(chr(b) if 0x20 <= b < 0x7f else "." for b in chunk)
        lines.append(f"{base + off:08x}  {hexs}  |{ascii_}|")
    return "\n".join(lines)


def cmd_hexview(args):
    data = Path(args.input).read_bytes()
    if args.length:
        data = data[args.offset:args.offset + args.length]
    elif args.offset:
        data = data[args.offset:]
    print(_hexdump_bytes(data, base=args.offset))


# ---- intel-hex-info ----

def cmd_intel_hex_info(args):
    """Parse Intel HEX. Records: :LLAAAATT[DD]CC"""
    text = Path(args.input).read_text(encoding="utf-8", errors="replace")
    upper = 0  # extended linear
    segments = []  # list of (addr, length)
    cur_start = None; cur_end = None
    total = 0; records = 0
    for ln in text.splitlines():
        ln = ln.strip()
        if not ln.startswith(":"):
            continue
        records += 1
        ll = int(ln[1:3], 16)
        aa = int(ln[3:7], 16)
        tt = int(ln[7:9], 16)
        data_hex = ln[9:9 + ll * 2]
        if tt == 0x00:
            addr = (upper << 16) | aa
            if cur_end is not None and addr == cur_end:
                cur_end += ll
            else:
                if cur_start is not None:
                    segments.append((cur_start, cur_end - cur_start))
                cur_start = addr; cur_end = addr + ll
            total += ll
        elif tt == 0x04:  # extended linear
            upper = int(data_hex, 16)
        elif tt == 0x02:  # extended segment
            upper = int(data_hex, 16) >> 12
        elif tt == 0x01:  # EOF
            break
    if cur_start is not None:
        segments.append((cur_start, cur_end - cur_start))
    print(f"Records:   {records}")
    print(f"Data:      {total} bytes")
    print(f"Segments:  {len(segments)}")
    for addr, sz in segments:
        print(f"  {addr:#010x}  +{sz}  ({human_size(sz)})")
    if segments:
        lo = min(a for a, _ in segments)
        hi = max(a + s for a, s in segments)
        print(f"Range:     {lo:#010x} .. {hi:#010x}")


# ---- srec-info ----

def cmd_srec_info(args):
    text = Path(args.input).read_text(encoding="utf-8", errors="replace")
    records = 0
    data_recs = 0
    total = 0
    addrs = []
    addr_widths = {"1": 2, "2": 3, "3": 4}
    for ln in text.splitlines():
        ln = ln.strip()
        if not ln.startswith("S"):
            continue
        records += 1
        kind = ln[1]
        count = int(ln[2:4], 16)
        if kind in addr_widths:
            w = addr_widths[kind]
            addr = int(ln[4:4 + w * 2], 16)
            data_len = count - w - 1
            addrs.append((addr, data_len))
            data_recs += 1
            total += data_len
    print(f"Records:       {records}")
    print(f"Data records:  {data_recs}")
    print(f"Data bytes:    {total}")
    if addrs:
        lo = min(a for a, _ in addrs)
        hi = max(a + s for a, s in addrs)
        print(f"Range:         {lo:#010x} .. {hi:#010x}")


# ---- bin2c ----

def cmd_bin2c(args):
    data = Path(args.input).read_bytes()
    var = args.varname
    width = args.width
    lines = [f"const unsigned char {var}[{len(data)}] = {{"]
    for i in range(0, len(data), width):
        chunk = data[i:i + width]
        hexes = ", ".join(f"0x{b:02x}" for b in chunk)
        lines.append(f"    {hexes},")
    lines.append("};")
    lines.append(f"const unsigned int {var}_len = {len(data)};")
    out = "\n".join(lines) + "\n"
    if args.output:
        Path(args.output).write_text(out, encoding="utf-8")
        print(f"Wrote {args.output}")
    else:
        print(out)


# ---- c2bin ----

def cmd_c2bin(args):
    text = Path(args.input).read_text(encoding="utf-8", errors="replace")
    # strip comments
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"//[^\n]*", "", text)
    nums = re.findall(r"0x[0-9a-fA-F]+|\b\d+\b", text)
    data = bytearray()
    for n in nums:
        v = int(n, 0)
        if 0 <= v <= 0xff:
            data.append(v)
    Path(args.output).write_bytes(bytes(data))
    print(f"Wrote {len(data)} bytes -> {args.output}")


# ---- font2bmp ----

ASCII_PRINT = "".join(chr(c) for c in range(0x20, 0x7f))
ASCII_PLUS = ASCII_PRINT + "".join(chr(c) for c in range(0xa1, 0xff))


def cmd_font2bmp(args):
    Image = lazy_import("PIL.Image", "pip install pillow")
    from PIL import Image, ImageDraw, ImageFont
    glyphs_map = {"ASCII": ASCII_PRINT, "ASCII+": ASCII_PLUS}
    glyphs = glyphs_map.get(args.glyphs, args.glyphs)
    font = ImageFont.truetype(args.font, args.size)
    w = args.width; h = args.height
    rows_per = (h + 7) // 8
    out_bytes = []
    for ch in glyphs:
        img = Image.new("1", (w, h), 0)
        d = ImageDraw.Draw(img)
        d.text((0, 0), ch, fill=1, font=font)
        # 1bpp column-major (each byte = 8 vertical pixels)
        for col in range(w):
            for page in range(rows_per):
                byte = 0
                for bit in range(8):
                    y = page * 8 + bit
                    if y < h and img.getpixel((col, y)):
                        byte |= 1 << bit
                out_bytes.append(byte)
    varname = args.varname
    lines = [
        f"// Font: {args.font} {args.size}px  glyphs={len(glyphs)}  cell={w}x{h}",
        f"const unsigned char {varname}[{len(out_bytes)}] = {{",
    ]
    for i in range(0, len(out_bytes), 16):
        lines.append("    " + ", ".join(f"0x{b:02x}" for b in out_bytes[i:i+16]) + ",")
    lines.append("};")
    lines.append(f"const unsigned int {varname}_glyphs = {len(glyphs)};")
    lines.append(f"const unsigned char {varname}_w = {w}, {varname}_h = {h};")
    out = "\n".join(lines) + "\n"
    if args.output:
        Path(args.output).write_text(out, encoding="utf-8")
        print(f"Wrote {args.output}  ({len(glyphs)} glyphs, {len(out_bytes)} bytes)")
    else:
        print(out)


# ---- serial ----

def cmd_serial_list(args):
    ser = lazy_import("serial.tools.list_ports", "pip install pyserial")
    for p in ser.comports():
        print(f"{p.device:<20} {p.description}")


def cmd_serial_monitor(args):
    lazy_import("serial", "pip install pyserial")
    import serial
    s = serial.Serial(args.port, args.baud, timeout=args.timeout)
    print(f"Opened {args.port} @ {args.baud}. Ctrl+C to exit.")
    try:
        while True:
            line = s.readline()
            if line:
                sys.stdout.write(line.decode("utf-8", errors="replace"))
                sys.stdout.flush()
    except KeyboardInterrupt:
        pass
    finally:
        s.close()


# ---- CRCs ----

def _read_bytes_arg(args) -> bytes:
    if args.hex:
        h = args.hex.replace(" ", "").replace(":", "")
        return bytes.fromhex(h)
    return Path(args.input).read_bytes()


def cmd_crc16(args):
    """CRC-16/CCITT-FALSE: poly=0x1021, init=0xFFFF, no reflect."""
    data = _read_bytes_arg(args)
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if (crc & 0x8000) else (crc << 1) & 0xFFFF
    print(f"CRC-16/CCITT-FALSE: 0x{crc:04x}")


def cmd_crc32(args):
    data = _read_bytes_arg(args)
    print(f"CRC-32: 0x{zlib.crc32(data) & 0xFFFFFFFF:08x}")


_CRC8_TABLE = None


def _crc8_table():
    global _CRC8_TABLE
    if _CRC8_TABLE is None:
        t = []
        for i in range(256):
            c = i
            for _ in range(8):
                c = ((c << 1) ^ 0x07) & 0xFF if (c & 0x80) else (c << 1) & 0xFF
            t.append(c)
        _CRC8_TABLE = t
    return _CRC8_TABLE


def cmd_crc8(args):
    """CRC-8 with polynomial 0x07."""
    data = _read_bytes_arg(args)
    tab = _crc8_table()
    crc = 0
    for b in data:
        crc = tab[crc ^ b]
    print(f"CRC-8 (poly 0x07): 0x{crc:02x}")


def cmd_checksum_fletcher(args):
    data = _read_bytes_arg(args)
    if args.bits == 16:
        s1 = s2 = 0
        for b in data:
            s1 = (s1 + b) % 255
            s2 = (s2 + s1) % 255
        print(f"Fletcher-16: 0x{(s2 << 8) | s1:04x}")
    else:
        s1 = s2 = 0
        # pad to multiple of 2
        if len(data) % 2:
            data = data + b"\x00"
        for i in range(0, len(data), 2):
            word = data[i] | (data[i + 1] << 8)
            s1 = (s1 + word) % 65535
            s2 = (s2 + s1) % 65535
        print(f"Fletcher-32: 0x{(s2 << 16) | s1:08x}")


COMMANDS = {
    "hexview":           "hexdump a binary file",
    "intel-hex-info":    "parse Intel HEX file",
    "srec-info":         "parse Motorola S-record file",
    "bin2c":             "convert binary to C array",
    "c2bin":             "convert C array back to binary",
    "font2bmp":          "render TTF/OTF glyphs to 1bpp C array",
    "serial-list":       "list available serial ports",
    "serial-monitor":    "open serial port and stream input",
    "crc16":             "CRC-16/CCITT-FALSE",
    "crc32":             "CRC-32 (zlib)",
    "crc8":              "CRC-8 (poly 0x07)",
    "checksum-fletcher": "Fletcher-16 or Fletcher-32 checksum",
}


def build_parser(parser=None):
    parser = parser or argparse.ArgumentParser(prog="embedded_tools", description="Embedded/MCU helpers")
    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("hexview", help=COMMANDS["hexview"])
    p.add_argument("input")
    p.add_argument("--offset", type=int, default=0)
    p.add_argument("--length", type=int, default=0)
    p.set_defaults(func=cmd_hexview)

    p = sub.add_parser("intel-hex-info", help=COMMANDS["intel-hex-info"]); p.add_argument("input")
    p.set_defaults(func=cmd_intel_hex_info)

    p = sub.add_parser("srec-info", help=COMMANDS["srec-info"]); p.add_argument("input")
    p.set_defaults(func=cmd_srec_info)

    p = sub.add_parser("bin2c", help=COMMANDS["bin2c"])
    p.add_argument("input"); p.add_argument("-o", "--output")
    p.add_argument("--varname", default="data")
    p.add_argument("--width", type=int, default=16)
    p.set_defaults(func=cmd_bin2c)

    p = sub.add_parser("c2bin", help=COMMANDS["c2bin"])
    p.add_argument("input"); p.add_argument("output")
    p.set_defaults(func=cmd_c2bin)

    p = sub.add_parser("font2bmp", help=COMMANDS["font2bmp"])
    p.add_argument("font", help="path to .ttf/.otf")
    p.add_argument("-o", "--output")
    p.add_argument("--size", type=int, default=8)
    p.add_argument("--width", type=int, default=6)
    p.add_argument("--height", type=int, default=8)
    p.add_argument("--glyphs", default="ASCII")
    p.add_argument("--varname", default="font_data")
    p.set_defaults(func=cmd_font2bmp)

    p = sub.add_parser("serial-list", help=COMMANDS["serial-list"])
    p.set_defaults(func=cmd_serial_list)

    p = sub.add_parser("serial-monitor", help=COMMANDS["serial-monitor"])
    p.add_argument("--port", required=True)
    p.add_argument("--baud", type=int, default=115200)
    p.add_argument("--timeout", type=float, default=1.0)
    p.set_defaults(func=cmd_serial_monitor)

    for name, fn in [("crc16", cmd_crc16), ("crc32", cmd_crc32), ("crc8", cmd_crc8)]:
        p = sub.add_parser(name, help=COMMANDS[name])
        p.add_argument("input", nargs="?")
        p.add_argument("--hex", help="hex bytes instead of file")
        p.set_defaults(func=fn)

    p = sub.add_parser("checksum-fletcher", help=COMMANDS["checksum-fletcher"])
    p.add_argument("input", nargs="?")
    p.add_argument("--hex")
    p.add_argument("--bits", type=int, choices=[16, 32], default=16)
    p.set_defaults(func=cmd_checksum_fletcher)

    return parser


@tool_main("embedded")
def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 1
    return args.func(args) or 0


if __name__ == "__main__":
    raise SystemExit(main())
