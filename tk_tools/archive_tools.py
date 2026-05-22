"""Archive tools: zip, unzip, tar (gz/bz2/xz), auto-extract, list."""
from __future__ import annotations

import argparse
import tarfile
import zipfile
from pathlib import Path

from _common import human_size, tool_main


def cmd_zip(args):
    out = Path(args.output)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=args.level) as zf:
        for src in args.inputs:
            sp = Path(src)
            if sp.is_dir():
                for p in sp.rglob("*"):
                    if p.is_file():
                        zf.write(p, p.relative_to(sp.parent))
            elif sp.is_file():
                zf.write(sp, sp.name)
            else:
                print(f"  skip (not found): {sp}")
    print(f"Wrote {out}  ({human_size(out.stat().st_size)})")


def cmd_unzip(args):
    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.input) as zf:
        zf.extractall(out)
    print(f"Extracted to {out}")


def cmd_zip_list(args):
    with zipfile.ZipFile(args.input) as zf:
        total = 0
        for info in zf.infolist():
            print(f"{info.file_size:>12,}  {info.filename}")
            total += info.file_size
        print(f"\n{len(zf.infolist())} files, {human_size(total)} total uncompressed")


def cmd_tar(args):
    mode_map = {"gz": "w:gz", "bz2": "w:bz2", "xz": "w:xz", "none": "w"}
    mode = mode_map[args.compression]
    with tarfile.open(args.output, mode) as tf:
        for src in args.inputs:
            sp = Path(src)
            tf.add(sp, arcname=sp.name)
    out = Path(args.output)
    print(f"Wrote {out}  ({human_size(out.stat().st_size)})")


def cmd_untar(args):
    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    with tarfile.open(args.input) as tf:
        tf.extractall(out)
    print(f"Extracted to {out}")


def cmd_extract_any(args):
    src = Path(args.input)
    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    if zipfile.is_zipfile(src):
        with zipfile.ZipFile(src) as zf:
            zf.extractall(out)
    elif tarfile.is_tarfile(src):
        with tarfile.open(src) as tf:
            tf.extractall(out)
    else:
        print(f"Unsupported archive: {src}")
        return 1
    print(f"Extracted to {out}")


COMMANDS = {
    "zip":      "create a ZIP archive",
    "unzip":    "extract a ZIP archive",
    "zip-list": "list contents of a ZIP",
    "tar":      "create a tar archive (gz/bz2/xz)",
    "untar":    "extract a tar archive",
    "extract":  "auto-detect and extract zip/tar",
}


def build_parser(parser=None):
    parser = parser or argparse.ArgumentParser(prog="archive_tools", description="Archive utilities")
    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("zip", help=COMMANDS["zip"])
    p.add_argument("inputs", nargs="+")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--level", type=int, default=6)
    p.set_defaults(func=cmd_zip)

    p = sub.add_parser("unzip", help=COMMANDS["unzip"])
    p.add_argument("input"); p.add_argument("-d", "--outdir", required=True)
    p.set_defaults(func=cmd_unzip)

    p = sub.add_parser("zip-list", help=COMMANDS["zip-list"])
    p.add_argument("input")
    p.set_defaults(func=cmd_zip_list)

    p = sub.add_parser("tar", help=COMMANDS["tar"])
    p.add_argument("inputs", nargs="+")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--compression", choices=["gz", "bz2", "xz", "none"], default="gz")
    p.set_defaults(func=cmd_tar)

    p = sub.add_parser("untar", help=COMMANDS["untar"])
    p.add_argument("input"); p.add_argument("-d", "--outdir", required=True)
    p.set_defaults(func=cmd_untar)

    p = sub.add_parser("extract", help=COMMANDS["extract"])
    p.add_argument("input"); p.add_argument("-d", "--outdir", required=True)
    p.set_defaults(func=cmd_extract_any)

    return parser


@tool_main("archive")
def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 1
    return args.func(args) or 0


if __name__ == "__main__":
    raise SystemExit(main())
