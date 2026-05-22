"""File forensics: magic, entropy, strings, hexdump, carve, hash-bulk, dup-bytes, pe-info, metadata-strip, timeline."""
from __future__ import annotations

import argparse
import csv
import hashlib
import math
import re
import struct
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from _common import ensure_dir, human_size, lazy_import, tool_main

# ---- Magic table ----

MAGICS = [
    (b"\x89PNG\r\n\x1a\n", "PNG image", "png"),
    (b"\xff\xd8\xff",      "JPEG image", "jpg"),
    (b"GIF87a",            "GIF image", "gif"),
    (b"GIF89a",            "GIF image", "gif"),
    (b"BM",                "BMP image", "bmp"),
    (b"RIFF",              "RIFF (WAV/AVI/WebP)", "riff"),
    (b"OggS",              "Ogg media", "ogg"),
    (b"fLaC",              "FLAC audio", "flac"),
    (b"ID3",               "MP3/ID3 audio", "mp3"),
    (b"\xff\xfb",          "MP3 audio", "mp3"),
    (b"\xff\xf3",          "MP3 audio", "mp3"),
    (b"\x1aE\xdf\xa3",     "Matroska/WebM", "mkv"),
    (b"\x00\x00\x00 ftyp", "MP4 container (offset 4)", "mp4"),
    (b"\x00\x00\x00\x18ftyp", "MP4/MOV (offset 4)", "mp4"),
    (b"PK\x03\x04",        "ZIP / Office (xlsx/docx/jar)", "zip"),
    (b"PK\x05\x06",        "ZIP (empty)", "zip"),
    (b"PK\x07\x08",        "ZIP (spanned)", "zip"),
    (b"Rar!\x1a\x07\x00",  "RAR v1.5+", "rar"),
    (b"Rar!\x1a\x07\x01\x00", "RAR v5", "rar"),
    (b"7z\xbc\xaf\x27\x1c", "7-Zip", "7z"),
    (b"\x1f\x8b",          "gzip", "gz"),
    (b"BZh",               "bzip2", "bz2"),
    (b"\xfd7zXZ\x00",      "xz", "xz"),
    (b"\x28\xb5\x2f\xfd",  "zstandard", "zst"),
    (b"%PDF-",             "PDF document", "pdf"),
    (b"\x7fELF",           "ELF executable", "elf"),
    (b"MZ",                "DOS/PE executable", "exe"),
    (b"\xca\xfe\xba\xbe",  "Mach-O fat / Java class", "bin"),
    (b"\xcf\xfa\xed\xfe",  "Mach-O 64", "bin"),
    (b"\xfe\xed\xfa\xce",  "Mach-O 32 BE", "bin"),
    (b"SQLite format 3\x00", "SQLite db", "sqlite"),
    (b"{\\rtf",            "RTF document", "rtf"),
    (b"<?xml",             "XML document", "xml"),
    (b"<!DOCTYPE",         "HTML/SGML document", "html"),
    (b"<html",             "HTML document", "html"),
    (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", "MS Compound (xls/doc/msi)", "cfb"),
    (b"-----BEGIN ",       "PEM-armored data", "pem"),
]


def _detect_magic(data: bytes):
    hits = []
    for magic, desc, ext in MAGICS:
        idx = data.find(magic, 0, max(64, len(magic) + 8))
        if idx != -1 and idx <= 32:
            hits.append((idx, magic, desc, ext))
    return hits


def cmd_magic(args):
    data = Path(args.input).read_bytes()[:4096]
    hits = _detect_magic(data)
    if not hits:
        print("(no known magic at offset 0..32)")
        return 1
    for off, magic, desc, ext in hits:
        print(f"offset {off:>4}: .{ext:<6}  {desc}    magic={magic[:16].hex()}")


# ---- entropy ----

def cmd_entropy(args):
    path = Path(args.input)
    counts = [0] * 256
    total = 0
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            for b in chunk:
                counts[b] += 1
            total += len(chunk)
    if total == 0:
        print("Empty file."); return 1
    H = 0.0
    for c in counts:
        if c:
            p = c / total
            H -= p * math.log2(p)
    print(f"File:    {path}")
    print(f"Size:    {human_size(total)}")
    print(f"Entropy: {H:.4f} bits/byte (max 8.0)")
    print(f"Hint:    {'compressed/encrypted' if H > 7.5 else 'mixed' if H > 5.0 else 'low/structured'}")


# ---- strings ----

def cmd_strings(args):
    data = Path(args.input).read_bytes()
    minlen = args.min
    ascii_pat = re.compile(rb"[\x20-\x7e]{%d,}" % minlen)
    out = []
    for m in ascii_pat.finditer(data):
        out.append(f"{m.start():>10x}  ascii   {m.group().decode('ascii')}")
    if not args.ascii_only:
        # utf-16 LE
        u16 = re.compile(rb"(?:[\x20-\x7e]\x00){%d,}" % minlen)
        for m in u16.finditer(data):
            try:
                s = m.group().decode("utf-16-le")
                out.append(f"{m.start():>10x}  utf16   {s}")
            except Exception:
                pass
    out.sort()
    if args.output:
        Path(args.output).write_text("\n".join(out), encoding="utf-8")
        print(f"Wrote {len(out)} strings -> {args.output}")
    else:
        print("\n".join(out))


# ---- hexdump ----

def _hexdump_bytes(data: bytes, base: int = 0):
    lines = []
    for off in range(0, len(data), 16):
        chunk = data[off:off + 16]
        hexs = " ".join(f"{b:02x}" for b in chunk)
        hexs = hexs.ljust(48)
        ascii_ = "".join(chr(b) if 0x20 <= b < 0x7f else "." for b in chunk)
        lines.append(f"{base + off:08x}  {hexs}  |{ascii_}|")
    return "\n".join(lines)


def cmd_hexdump(args):
    data = Path(args.input).read_bytes()
    if args.length:
        data = data[args.offset:args.offset + args.length]
    elif args.offset:
        data = data[args.offset:]
    out = _hexdump_bytes(data, base=args.offset)
    if args.output:
        Path(args.output).write_text(out, encoding="utf-8")
    else:
        print(out)


# ---- carve ----

def cmd_carve(args):
    data = Path(args.input).read_bytes()
    outdir = ensure_dir(Path(args.outdir))
    # find all magic offsets
    hits = []
    for magic, desc, ext in MAGICS:
        start = 0
        while True:
            idx = data.find(magic, start)
            if idx == -1:
                break
            hits.append((idx, ext, desc))
            start = idx + 1
    hits.sort()
    if not hits:
        print("No magic bytes found.")
        return 1
    print(f"Found {len(hits)} candidate(s).")
    count = 0
    for i, (off, ext, desc) in enumerate(hits):
        end = hits[i + 1][0] if i + 1 < len(hits) else len(data)
        if end - off < args.min_size:
            continue
        outp = outdir / f"carved_{i:04d}_{off:08x}.{ext}"
        outp.write_bytes(data[off:end])
        print(f"  {off:>10x}  .{ext:<6}  {human_size(end-off):>10}  {desc}")
        count += 1
    print(f"\nWrote {count} files -> {outdir}")


# ---- hash-bulk ----

def cmd_hash_bulk(args):
    root = Path(args.input)
    out = Path(args.output)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["path", "size", "sha256"])
        n = 0
        for p in root.rglob("*"):
            if not p.is_file():
                continue
            h = hashlib.sha256()
            with open(p, "rb") as fp:
                for chunk in iter(lambda: fp.read(65536), b""):
                    h.update(chunk)
            w.writerow([str(p), p.stat().st_size, h.hexdigest()])
            n += 1
    print(f"Hashed {n} files -> {out}")


# ---- dup-bytes ----

def cmd_dup_bytes(args):
    root = Path(args.input)
    by_size = defaultdict(list)
    for p in root.rglob("*"):
        if p.is_file():
            by_size[p.stat().st_size].append(p)
    groups = []
    for size, files in by_size.items():
        if len(files) < 2 or size == 0:
            continue
        by_hash = defaultdict(list)
        for p in files:
            h = hashlib.sha256()
            with open(p, "rb") as fp:
                for chunk in iter(lambda: fp.read(65536), b""):
                    h.update(chunk)
            by_hash[h.hexdigest()].append(p)
        for digest, ps in by_hash.items():
            if len(ps) > 1:
                groups.append((size, digest, ps))
    groups.sort(key=lambda x: -x[0])
    total_dup = 0
    for size, digest, ps in groups:
        print(f"\n{digest}  {human_size(size)}  ({len(ps)} copies)")
        for p in ps:
            print(f"  {p}")
        total_dup += size * (len(ps) - 1)
    print(f"\nGroups: {len(groups)}   Reclaimable: {human_size(total_dup)}")


# ---- pe-info ----

def cmd_pe_info(args):
    data = Path(args.input).read_bytes()
    if data[:2] != b"MZ":
        print("Not a PE/MZ file"); return 1
    pe_off = struct.unpack_from("<I", data, 0x3c)[0]
    if data[pe_off:pe_off+4] != b"PE\x00\x00":
        print("No PE signature"); return 1
    machine, nsec, ts, _, _, sizeopt, chars = struct.unpack_from("<HHIIIHH", data, pe_off + 4)
    machines = {0x14c: "i386", 0x8664: "x86_64", 0x1c0: "ARM", 0xaa64: "ARM64", 0x200: "IA64"}
    print(f"Machine:      {machines.get(machine, hex(machine))}")
    print(f"Sections:     {nsec}")
    print(f"Timestamp:    {datetime.utcfromtimestamp(ts).isoformat()} UTC")
    print(f"OptHdr size:  {sizeopt}")
    print(f"Characteristics: {chars:#06x}")
    # sections
    sec_off = pe_off + 4 + 20 + sizeopt
    print("\nSections:")
    for i in range(nsec):
        s = data[sec_off + i*40 : sec_off + (i+1)*40]
        name = s[:8].rstrip(b"\x00").decode("ascii", errors="replace")
        vsize, vaddr, rsize, raddr = struct.unpack_from("<IIII", s, 8)
        print(f"  {name:<10} vaddr={vaddr:#010x}  vsize={vsize:>8}  raw={rsize:>8}@{raddr:#010x}")
    # rough imports count via opt header data dir 1
    opt = data[pe_off + 24 : pe_off + 24 + sizeopt]
    if len(opt) >= 96:
        magic = struct.unpack_from("<H", opt, 0)[0]
        dd_off = 96 if magic == 0x10b else 112
        if len(opt) >= dd_off + 16:
            imp_rva, imp_size = struct.unpack_from("<II", opt, dd_off + 8)
            print(f"\nImport dir:   rva={imp_rva:#010x} size={imp_size}")


# ---- metadata-strip ----

def cmd_metadata_strip(args):
    inp = Path(args.input); outp = Path(args.output)
    ext = inp.suffix.lower()
    if ext in (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".webp"):
        lazy_import("PIL.Image", "pip install pillow")
        from PIL import Image as I
        img = I.open(inp)
        data = list(img.getdata())
        clean = I.new(img.mode, img.size)
        clean.putdata(data)
        clean.save(outp)
        print(f"Stripped image metadata -> {outp}")
    else:
        mut = lazy_import("mutagen", "pip install mutagen")
        f = mut.File(inp, easy=False)
        if f is None:
            print(f"Unsupported file type: {ext}"); return 1
        outp.write_bytes(inp.read_bytes())
        f2 = mut.File(outp, easy=False)
        f2.delete()
        f2.save()
        print(f"Stripped audio metadata -> {outp}")


# ---- timeline ----

def cmd_timeline(args):
    root = Path(args.input); out = Path(args.output)
    rows = []
    for p in root.rglob("*"):
        try:
            st = p.stat()
        except OSError:
            continue
        rows.append((datetime.utcfromtimestamp(st.st_mtime).isoformat(), "M", st.st_size, str(p)))
        rows.append((datetime.utcfromtimestamp(st.st_ctime).isoformat(), "C", st.st_size, str(p)))
        rows.append((datetime.utcfromtimestamp(st.st_atime).isoformat(), "A", st.st_size, str(p)))
    rows.sort()
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", "type", "size", "path"])
        for r in rows:
            w.writerow(r)
    print(f"Wrote {len(rows)} timeline entries -> {out}")


COMMANDS = {
    "magic":          "detect file type from magic bytes",
    "entropy":        "Shannon entropy of file bytes",
    "strings":        "extract printable strings (ascii + utf-16)",
    "hexdump":        "hexdump bytes (offset hex ascii)",
    "carve":          "scan blob for embedded files by magic bytes",
    "hash-bulk":      "sha256 every file in tree -> CSV",
    "dup-bytes":      "find duplicate files by content",
    "pe-info":        "parse minimal PE/MZ header",
    "metadata-strip": "strip image (Pillow) / audio (mutagen) metadata",
    "timeline":       "build CSV timeline from file m/c/a times",
}


def build_parser(parser=None):
    parser = parser or argparse.ArgumentParser(prog="forensic_tools", description="File forensics utilities")
    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("magic", help=COMMANDS["magic"]); p.add_argument("input")
    p.set_defaults(func=cmd_magic)

    p = sub.add_parser("entropy", help=COMMANDS["entropy"]); p.add_argument("input")
    p.set_defaults(func=cmd_entropy)

    p = sub.add_parser("strings", help=COMMANDS["strings"])
    p.add_argument("input"); p.add_argument("-o", "--output")
    p.add_argument("--min", type=int, default=4)
    p.add_argument("--ascii-only", action="store_true")
    p.set_defaults(func=cmd_strings)

    p = sub.add_parser("hexdump", help=COMMANDS["hexdump"])
    p.add_argument("input"); p.add_argument("-o", "--output")
    p.add_argument("--offset", type=int, default=0)
    p.add_argument("--length", type=int, default=0)
    p.set_defaults(func=cmd_hexdump)

    p = sub.add_parser("carve", help=COMMANDS["carve"])
    p.add_argument("input"); p.add_argument("outdir")
    p.add_argument("--min-size", type=int, default=64)
    p.set_defaults(func=cmd_carve)

    p = sub.add_parser("hash-bulk", help=COMMANDS["hash-bulk"])
    p.add_argument("input"); p.add_argument("output")
    p.set_defaults(func=cmd_hash_bulk)

    p = sub.add_parser("dup-bytes", help=COMMANDS["dup-bytes"])
    p.add_argument("input")
    p.set_defaults(func=cmd_dup_bytes)

    p = sub.add_parser("pe-info", help=COMMANDS["pe-info"]); p.add_argument("input")
    p.set_defaults(func=cmd_pe_info)

    p = sub.add_parser("metadata-strip", help=COMMANDS["metadata-strip"])
    p.add_argument("input"); p.add_argument("output")
    p.set_defaults(func=cmd_metadata_strip)

    p = sub.add_parser("timeline", help=COMMANDS["timeline"])
    p.add_argument("input"); p.add_argument("output")
    p.set_defaults(func=cmd_timeline)

    return parser


@tool_main("forensic")
def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 1
    return args.func(args) or 0


if __name__ == "__main__":
    raise SystemExit(main())
