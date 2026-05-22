"""Advanced image tools: rembg, exif, palette, smart-crop, upscale, panorama, hdr, denoise, blur-face, compare."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

from _common import lazy_import, tool_main


def _pil():
    lazy_import("PIL", install_hint="pip install pillow")
    from PIL import Image
    return Image


def _cv2():
    return lazy_import("cv2", install_hint="pip install opencv-python")


def cmd_rembg(args):
    rembg = lazy_import("rembg", install_hint="pip install rembg")
    _pil()
    inp = Path(args.input)
    out = Path(args.output)
    data = inp.read_bytes()
    result = rembg.remove(data)
    out.write_bytes(result)
    print(f"Background removed -> {out}")


def cmd_exif_strip(args):
    Image = _pil()
    img = Image.open(args.input)
    data = list(img.getdata())
    clean = Image.new(img.mode, img.size)
    clean.putdata(data)
    clean.save(args.output)
    print(f"Stripped EXIF -> {args.output}")


def cmd_exif_show(args):
    Image = _pil()
    from PIL.ExifTags import GPSTAGS, TAGS
    img = Image.open(args.input)
    exif = getattr(img, "_getexif", lambda: None)()
    out_dict = {}
    if not exif:
        print("{}")
        return
    for tag_id, val in exif.items():
        name = TAGS.get(tag_id, str(tag_id))
        if name == "GPSInfo" and isinstance(val, dict):
            gps = {}
            for gid, gv in val.items():
                gname = GPSTAGS.get(gid, str(gid))
                gps[gname] = _jsonify(gv)
            out_dict[name] = gps
        else:
            out_dict[name] = _jsonify(val)
    text = json.dumps(out_dict, indent=2, default=str)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"Wrote {args.output}")
    else:
        print(text)


def _jsonify(v):
    if isinstance(v, bytes):
        try:
            return v.decode("utf-8", errors="replace")
        except Exception:
            return v.hex()
    if isinstance(v, (tuple, list)):
        return [_jsonify(x) for x in v]
    if isinstance(v, dict):
        return {str(k): _jsonify(val) for k, val in v.items()}
    try:
        json.dumps(v)
        return v
    except TypeError:
        return str(v)


def cmd_palette(args):
    Image = _pil()
    img = Image.open(args.input).convert("RGB")
    if args.width and img.width > args.width:
        ratio = args.width / img.width
        img = img.resize((args.width, max(1, int(img.height * ratio))))
    bucket = max(1, 256 // args.bucket_div)
    counts = {}
    for r, g, b in img.getdata():
        key = (r // bucket * bucket, g // bucket * bucket, b // bucket * bucket)
        counts[key] = counts.get(key, 0) + 1
    top = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[: args.colors]
    total = img.width * img.height
    rows = []
    for (r, g, b), cnt in top:
        pct = 100 * cnt / total
        rows.append(f"  #{r:02X}{g:02X}{b:02X}  rgb({r:>3},{g:>3},{b:>3})  {pct:5.1f}%")
    print(f"Top {len(top)} colors:")
    print("\n".join(rows))
    if args.output:
        sw = 64
        canvas = Image.new("RGB", (sw * len(top), sw))
        for i, ((r, g, b), _) in enumerate(top):
            for x in range(i * sw, (i + 1) * sw):
                for y in range(sw):
                    canvas.putpixel((x, y), (r, g, b))
        canvas.save(args.output)
        print(f"Wrote swatch -> {args.output}")


def cmd_smart_crop(args):
    cv2 = _cv2()
    _pil()
    img = cv2.imread(args.input)
    if img is None:
        print(f"[!] Could not read {args.input}")
        return 1
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    cascade_path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
    cascade = cv2.CascadeClassifier(str(cascade_path))
    faces = cascade.detectMultiScale(gray, 1.1, 4)
    target_w = args.width
    target_h = args.height
    if len(faces) == 0:
        print("(no face detected; center crop)")
        cx, cy = w // 2, h // 2
    else:
        # average face centers, weighted
        xs = []; ys = []
        for (fx, fy, fw, fh) in faces:
            xs.append(fx + fw // 2); ys.append(fy + fh // 2)
        cx = sum(xs) // len(xs); cy = sum(ys) // len(ys)
    x0 = max(0, min(w - target_w, cx - target_w // 2))
    y0 = max(0, min(h - target_h, cy - target_h // 2))
    crop = img[y0:y0 + target_h, x0:x0 + target_w]
    cv2.imwrite(args.output, crop)
    print(f"Smart-cropped ({len(faces)} faces) -> {args.output}")


def cmd_upscale(args):
    Image = _pil()
    if args.engine == "realesrgan" and shutil.which("realesrgan-ncnn-vulkan"):
        cmd = ["realesrgan-ncnn-vulkan", "-i", args.input, "-o", args.output, "-s", str(args.factor)]
        r = subprocess.run(cmd, check=False, capture_output=True, text=True)
        if r.returncode == 0:
            print(f"Upscaled via realesrgan -> {args.output}")
            return 0
        print(r.stderr or r.stdout)
        print("[!] realesrgan failed; falling back to LANCZOS")
    img = Image.open(args.input)
    new = (img.width * args.factor, img.height * args.factor)
    out = img.resize(new, Image.LANCZOS)
    out.save(args.output)
    print(f"Upscaled {img.size} -> {out.size} (LANCZOS) -> {args.output}")


def cmd_panorama(args):
    cv2 = _cv2()
    images = []
    for p in args.inputs:
        im = cv2.imread(p)
        if im is None:
            print(f"[!] Could not read {p}")
            return 1
        images.append(im)
    stitcher = cv2.Stitcher_create() if hasattr(cv2, "Stitcher_create") else cv2.createStitcher()
    status, pano = stitcher.stitch(images)
    if status != 0:
        print(f"[!] Stitching failed (status={status})")
        return 1
    cv2.imwrite(args.output, pano)
    print(f"Panorama from {len(images)} images -> {args.output}")


def cmd_hdr(args):
    cv2 = _cv2()
    np = lazy_import("numpy", install_hint="pip install numpy")
    images = [cv2.imread(p) for p in args.inputs]
    if any(im is None for im in images):
        print("[!] Could not read all inputs")
        return 1
    np.array(args.times, dtype=np.float32) if args.times else np.array(
        [1.0 / (2 ** i) for i in range(len(images))], dtype=np.float32)
    align = cv2.createAlignMTB()
    align.process(images, images)
    merge = cv2.createMergeMertens()
    fusion = merge.process(images)
    out = np.clip(fusion * 255, 0, 255).astype("uint8")
    cv2.imwrite(args.output, out)
    print(f"HDR merge of {len(images)} exposures -> {args.output}")


def cmd_denoise(args):
    if args.engine == "opencv":
        cv2 = _cv2()
        img = cv2.imread(args.input)
        if img is None:
            print(f"[!] Could not read {args.input}")
            return 1
        out = cv2.fastNlMeansDenoisingColored(img, None, args.strength, args.strength, 7, 21)
        cv2.imwrite(args.output, out)
        print(f"Denoised (opencv) -> {args.output}")
    else:
        Image = _pil()
        from PIL import ImageFilter
        img = Image.open(args.input)
        out = img.filter(ImageFilter.MedianFilter(size=args.size))
        out.save(args.output)
        print(f"Denoised (median {args.size}) -> {args.output}")


def cmd_blur_face(args):
    cv2 = _cv2()
    img = cv2.imread(args.input)
    if img is None:
        print(f"[!] Could not read {args.input}")
        return 1
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    cascade_path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
    cascade = cv2.CascadeClassifier(str(cascade_path))
    faces = cascade.detectMultiScale(gray, 1.1, 4)
    for (x, y, w, h) in faces:
        roi = img[y:y + h, x:x + w]
        k = max(15, (args.strength // 2) * 2 + 1)
        img[y:y + h, x:x + w] = cv2.GaussianBlur(roi, (k, k), 0)
    cv2.imwrite(args.output, img)
    print(f"Blurred {len(faces)} faces -> {args.output}")


def cmd_compare(args):
    Image = _pil()
    a = Image.open(args.a).convert("RGB")
    b = Image.open(args.b).convert("RGB")
    h = max(a.height, b.height)
    if a.height != h:
        a = a.resize((int(a.width * h / a.height), h), Image.LANCZOS)
    if b.height != h:
        b = b.resize((int(b.width * h / b.height), h), Image.LANCZOS)
    gap = args.gap
    canvas = Image.new("RGB", (a.width + b.width + gap, h), (255, 255, 255))
    canvas.paste(a, (0, 0))
    canvas.paste(b, (a.width + gap, 0))
    canvas.save(args.output)
    print(f"Side-by-side comparison -> {args.output}")


COMMANDS = {
    "rembg":       "Remove image background (lazy: rembg)",
    "exif-strip":  "Remove all EXIF metadata",
    "exif-show":   "Dump EXIF as JSON",
    "palette":     "Extract N dominant colors (bucket counting)",
    "smart-crop":  "Face-aware crop via OpenCV haar cascade",
    "upscale":     "2x/4x upscale via LANCZOS (or realesrgan-ncnn-vulkan if on PATH)",
    "panorama":    "Stitch images into a panorama (OpenCV)",
    "hdr":         "HDR merge of bracketed exposures (OpenCV Mertens)",
    "denoise":     "Denoise via Pillow median filter or OpenCV NL-means",
    "blur-face":   "Detect and blur faces (OpenCV)",
    "compare":     "Side-by-side composite of two images",
}


def build_parser(parser=None):
    parser = parser or argparse.ArgumentParser(prog="imagepro_tools", description="Advanced image tools")
    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("rembg", help=COMMANDS["rembg"])
    p.add_argument("input"); p.add_argument("output")
    p.set_defaults(func=cmd_rembg)

    p = sub.add_parser("exif-strip", help=COMMANDS["exif-strip"])
    p.add_argument("input"); p.add_argument("output")
    p.set_defaults(func=cmd_exif_strip)

    p = sub.add_parser("exif-show", help=COMMANDS["exif-show"])
    p.add_argument("input"); p.add_argument("-o", "--output")
    p.set_defaults(func=cmd_exif_show)

    p = sub.add_parser("palette", help=COMMANDS["palette"])
    p.add_argument("input"); p.add_argument("-o", "--output")
    p.add_argument("--colors", type=int, default=8)
    p.add_argument("--bucket-div", type=int, default=8, help="larger = coarser buckets")
    p.add_argument("--width", type=int, default=200, help="downscale before counting")
    p.set_defaults(func=cmd_palette)

    p = sub.add_parser("smart-crop", help=COMMANDS["smart-crop"])
    p.add_argument("input"); p.add_argument("output")
    p.add_argument("--width", type=int, required=True)
    p.add_argument("--height", type=int, required=True)
    p.set_defaults(func=cmd_smart_crop)

    p = sub.add_parser("upscale", help=COMMANDS["upscale"])
    p.add_argument("input"); p.add_argument("output")
    p.add_argument("--factor", type=int, default=2, choices=[2, 3, 4])
    p.add_argument("--engine", default="lanczos", choices=["lanczos", "realesrgan"])
    p.set_defaults(func=cmd_upscale)

    p = sub.add_parser("panorama", help=COMMANDS["panorama"])
    p.add_argument("inputs", nargs="+")
    p.add_argument("-o", "--output", required=True)
    p.set_defaults(func=cmd_panorama)

    p = sub.add_parser("hdr", help=COMMANDS["hdr"])
    p.add_argument("inputs", nargs="+")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--times", type=float, nargs="*", help="exposure times in seconds")
    p.set_defaults(func=cmd_hdr)

    p = sub.add_parser("denoise", help=COMMANDS["denoise"])
    p.add_argument("input"); p.add_argument("output")
    p.add_argument("--engine", default="pillow", choices=["pillow", "opencv"])
    p.add_argument("--size", type=int, default=3, help="median filter size")
    p.add_argument("--strength", type=int, default=10, help="opencv NL-means strength")
    p.set_defaults(func=cmd_denoise)

    p = sub.add_parser("blur-face", help=COMMANDS["blur-face"])
    p.add_argument("input"); p.add_argument("output")
    p.add_argument("--strength", type=int, default=51)
    p.set_defaults(func=cmd_blur_face)

    p = sub.add_parser("compare", help=COMMANDS["compare"])
    p.add_argument("a"); p.add_argument("b")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--gap", type=int, default=10)
    p.set_defaults(func=cmd_compare)

    return parser


@tool_main("image-pro")
def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 1
    return args.func(args) or 0


if __name__ == "__main__":
    raise SystemExit(main())
