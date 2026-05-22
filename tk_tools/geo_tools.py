"""Geo / location tools: gpx/kml convert, gpx info/simplify/merge, distance, geocode, reverse-geocode, exif-gps, bbox."""
from __future__ import annotations

import argparse
import json
import math
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

from _common import lazy_import, human_size, ensure_dir, confirm, tool_main


GPX_NS = "http://www.topografix.com/GPX/1/1"
KML_NS = "http://www.opengis.net/kml/2.2"
USER_AGENT = "tools-geo/1.0 (contact: sophosai007@gmail.com)"


def _haversine(lat1, lon1, lat2, lon2) -> float:
    R = 6371000.0
    p1 = math.radians(lat1); p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1); dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _parse_gpx_points(path: Path):
    """Return list of (lat, lon, ele, time) tuples and list of (track_name, segments)."""
    tree = ET.parse(path)
    root = tree.getroot()
    ns = {"g": GPX_NS}
    # Detect actual namespace
    tag = root.tag
    if tag.startswith("{"):
        uri = tag[1:].split("}")[0]
        ns = {"g": uri}
    tracks = []
    for trk in root.findall("g:trk", ns):
        name_el = trk.find("g:name", ns)
        name = name_el.text if name_el is not None else ""
        segs = []
        for seg in trk.findall("g:trkseg", ns):
            pts = []
            for p in seg.findall("g:trkpt", ns):
                lat = float(p.attrib["lat"]); lon = float(p.attrib["lon"])
                ele_el = p.find("g:ele", ns)
                t_el = p.find("g:time", ns)
                ele = float(ele_el.text) if ele_el is not None and ele_el.text else None
                t = t_el.text if t_el is not None else None
                pts.append((lat, lon, ele, t))
            segs.append(pts)
        tracks.append((name, segs))
    return tracks


def _write_gpx(tracks, out: Path):
    ET.register_namespace("", GPX_NS)
    gpx = ET.Element(f"{{{GPX_NS}}}gpx", attrib={"version": "1.1", "creator": "geo_tools"})
    for name, segs in tracks:
        trk = ET.SubElement(gpx, f"{{{GPX_NS}}}trk")
        if name:
            ET.SubElement(trk, f"{{{GPX_NS}}}name").text = name
        for pts in segs:
            seg = ET.SubElement(trk, f"{{{GPX_NS}}}trkseg")
            for lat, lon, ele, t in pts:
                pt = ET.SubElement(seg, f"{{{GPX_NS}}}trkpt",
                                   attrib={"lat": f"{lat}", "lon": f"{lon}"})
                if ele is not None:
                    ET.SubElement(pt, f"{{{GPX_NS}}}ele").text = f"{ele}"
                if t:
                    ET.SubElement(pt, f"{{{GPX_NS}}}time").text = t
    tree = ET.ElementTree(gpx)
    tree.write(out, encoding="utf-8", xml_declaration=True)


def cmd_gpx2kml(args):
    tracks = _parse_gpx_points(Path(args.input))
    ET.register_namespace("", KML_NS)
    kml = ET.Element(f"{{{KML_NS}}}kml")
    doc = ET.SubElement(kml, f"{{{KML_NS}}}Document")
    for name, segs in tracks:
        for i, pts in enumerate(segs):
            pm = ET.SubElement(doc, f"{{{KML_NS}}}Placemark")
            ET.SubElement(pm, f"{{{KML_NS}}}name").text = f"{name or 'track'}-{i}"
            ls = ET.SubElement(pm, f"{{{KML_NS}}}LineString")
            ET.SubElement(ls, f"{{{KML_NS}}}tessellate").text = "1"
            coords = " ".join(f"{lon},{lat},{ele or 0}" for lat, lon, ele, _ in pts)
            ET.SubElement(ls, f"{{{KML_NS}}}coordinates").text = coords
    ET.ElementTree(kml).write(args.output, encoding="utf-8", xml_declaration=True)
    print(f"GPX -> KML: {args.output}")


def cmd_kml2gpx(args):
    tree = ET.parse(args.input)
    root = tree.getroot()
    ns = {"k": KML_NS}
    if root.tag.startswith("{"):
        uri = root.tag[1:].split("}")[0]
        ns = {"k": uri}
    tracks = []
    for pm in root.iter(f"{{{ns['k']}}}Placemark"):
        name_el = pm.find("k:name", ns)
        name = name_el.text if name_el is not None else ""
        for ls in pm.iter(f"{{{ns['k']}}}LineString"):
            coords_el = ls.find("k:coordinates", ns)
            if coords_el is None or not coords_el.text:
                continue
            pts = []
            for tok in coords_el.text.split():
                bits = tok.split(",")
                if len(bits) < 2:
                    continue
                lon = float(bits[0]); lat = float(bits[1])
                ele = float(bits[2]) if len(bits) > 2 else None
                pts.append((lat, lon, ele, None))
            tracks.append((name, [pts]))
    _write_gpx(tracks, Path(args.output))
    print(f"KML -> GPX: {args.output}")


def cmd_gpx_info(args):
    tracks = _parse_gpx_points(Path(args.input))
    n_pts = 0; dist = 0.0; ascent = 0.0; descent = 0.0
    t_first = t_last = None
    for _, segs in tracks:
        for pts in segs:
            prev = None
            for lat, lon, ele, t in pts:
                n_pts += 1
                if prev is not None:
                    dist += _haversine(prev[0], prev[1], lat, lon)
                    if ele is not None and prev[2] is not None:
                        d = ele - prev[2]
                        if d > 0: ascent += d
                        else: descent += -d
                prev = (lat, lon, ele, t)
                if t:
                    if t_first is None: t_first = t
                    t_last = t
    print(f"Tracks:    {len(tracks)}")
    print(f"Points:    {n_pts}")
    print(f"Distance:  {dist / 1000:.3f} km ({dist:.1f} m)")
    print(f"Ascent:    {ascent:.1f} m")
    print(f"Descent:   {descent:.1f} m")
    print(f"Start:     {t_first}")
    print(f"End:       {t_last}")


def _perp_distance(p, a, b):
    if a == b:
        return _haversine(p[0], p[1], a[0], a[1])
    # use planar approximation in meters via equirectangular near the segment
    lat0 = math.radians((a[0] + b[0]) / 2)
    def proj(pt):
        return (math.radians(pt[1]) * math.cos(lat0) * 6371000,
                math.radians(pt[0]) * 6371000)
    px, py = proj(p); ax, ay = proj(a); bx, by = proj(b)
    dx, dy = bx - ax, by - ay
    seg2 = dx * dx + dy * dy
    if seg2 == 0:
        ex, ey = px - ax, py - ay
        return math.hypot(ex, ey)
    t = ((px - ax) * dx + (py - ay) * dy) / seg2
    t = max(0.0, min(1.0, t))
    cx, cy = ax + t * dx, ay + t * dy
    return math.hypot(px - cx, py - cy)


def _douglas_peucker(points, epsilon):
    if len(points) < 3:
        return points
    dmax = 0.0
    index = 0
    for i in range(1, len(points) - 1):
        d = _perp_distance(points[i], points[0], points[-1])
        if d > dmax:
            dmax = d; index = i
    if dmax > epsilon:
        left = _douglas_peucker(points[: index + 1], epsilon)
        right = _douglas_peucker(points[index:], epsilon)
        return left[:-1] + right
    else:
        return [points[0], points[-1]]


def cmd_gpx_simplify(args):
    tracks = _parse_gpx_points(Path(args.input))
    new_tracks = []
    total_before = 0; total_after = 0
    for name, segs in tracks:
        new_segs = []
        for pts in segs:
            total_before += len(pts)
            keep = _douglas_peucker(pts, args.epsilon)
            total_after += len(keep)
            new_segs.append(keep)
        new_tracks.append((name, new_segs))
    _write_gpx(new_tracks, Path(args.output))
    print(f"Simplified {total_before} -> {total_after} points (eps={args.epsilon} m) -> {args.output}")


def cmd_distance(args):
    lat1, lon1 = [float(x) for x in args.a.split(",")]
    lat2, lon2 = [float(x) for x in args.b.split(",")]
    d = _haversine(lat1, lon1, lat2, lon2)
    print(f"{d:.2f} m  ({d / 1000:.4f} km)")


def _http_get(url: str, timeout: float = 15.0):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8")


def cmd_geocode(args):
    q = urllib.parse.urlencode({"q": args.address, "format": "json", "limit": args.limit})
    url = f"https://nominatim.openstreetmap.org/search?{q}"
    data = json.loads(_http_get(url))
    if not data:
        print("(no results)")
        return 1
    if args.json:
        print(json.dumps(data, indent=2))
        return
    for r in data:
        print(f"  {r.get('lat')},{r.get('lon')}  {r.get('display_name')}")


def cmd_reverse_geocode(args):
    lat, lon = [float(x) for x in args.point.split(",")]
    q = urllib.parse.urlencode({"lat": lat, "lon": lon, "format": "json"})
    url = f"https://nominatim.openstreetmap.org/reverse?{q}"
    data = json.loads(_http_get(url))
    if args.json:
        print(json.dumps(data, indent=2))
        return
    print(data.get("display_name", "(no result)"))


def cmd_exif_gps(args):
    lazy_import("PIL", install_hint="pip install pillow")
    from PIL import Image
    from PIL.ExifTags import TAGS, GPSTAGS
    img = Image.open(args.input)
    exif = getattr(img, "_getexif", lambda: None)()
    if not exif:
        print("(no EXIF)")
        return 1
    gps_info = None
    for tid, val in exif.items():
        if TAGS.get(tid) == "GPSInfo":
            gps_info = {GPSTAGS.get(k, k): v for k, v in val.items()}
            break
    if not gps_info:
        print("(no GPS in EXIF)")
        return 1
    def conv(triple, ref):
        d, m, s = [float(x) for x in triple]
        v = d + m / 60 + s / 3600
        if ref in ("S", "W"):
            v = -v
        return v
    try:
        lat = conv(gps_info["GPSLatitude"], gps_info.get("GPSLatitudeRef", "N"))
        lon = conv(gps_info["GPSLongitude"], gps_info.get("GPSLongitudeRef", "E"))
    except KeyError:
        print("(GPS fields missing)")
        return 1
    print(f"{lat:.6f},{lon:.6f}")
    if args.altitude and "GPSAltitude" in gps_info:
        print(f"alt: {float(gps_info['GPSAltitude'])} m")


def cmd_bbox(args):
    tracks = _parse_gpx_points(Path(args.input))
    lats = []; lons = []
    for _, segs in tracks:
        for pts in segs:
            for lat, lon, *_ in pts:
                lats.append(lat); lons.append(lon)
    if not lats:
        print("(no points)")
        return 1
    print(f"min_lat: {min(lats):.6f}")
    print(f"min_lon: {min(lons):.6f}")
    print(f"max_lat: {max(lats):.6f}")
    print(f"max_lon: {max(lons):.6f}")


def cmd_gpx_merge(args):
    all_tracks = []
    for p in args.inputs:
        all_tracks.extend(_parse_gpx_points(Path(p)))
    _write_gpx(all_tracks, Path(args.output))
    print(f"Merged {len(args.inputs)} GPX files -> {args.output}")


COMMANDS = {
    "gpx2kml":         "Convert GPX to KML",
    "kml2gpx":         "Convert KML to GPX",
    "gpx-info":        "Summary of a GPX (points, distance, ascent/descent)",
    "gpx-simplify":    "Douglas-Peucker simplification (epsilon meters)",
    "distance":        "Great-circle (haversine) between two lat,lon",
    "geocode":         "Address -> lat,lon via Nominatim",
    "reverse-geocode": "lat,lon -> address via Nominatim",
    "exif-gps":        "Extract GPS coords from image EXIF",
    "bbox":            "Bounding box of GPX track points",
    "gpx-merge":       "Concatenate multiple GPX files",
}


def build_parser(parser=None):
    parser = parser or argparse.ArgumentParser(prog="geo_tools", description="Geo / location utilities")
    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("gpx2kml", help=COMMANDS["gpx2kml"])
    p.add_argument("input"); p.add_argument("output")
    p.set_defaults(func=cmd_gpx2kml)

    p = sub.add_parser("kml2gpx", help=COMMANDS["kml2gpx"])
    p.add_argument("input"); p.add_argument("output")
    p.set_defaults(func=cmd_kml2gpx)

    p = sub.add_parser("gpx-info", help=COMMANDS["gpx-info"])
    p.add_argument("input")
    p.set_defaults(func=cmd_gpx_info)

    p = sub.add_parser("gpx-simplify", help=COMMANDS["gpx-simplify"])
    p.add_argument("input"); p.add_argument("output")
    p.add_argument("--epsilon", type=float, default=10.0, help="meters")
    p.set_defaults(func=cmd_gpx_simplify)

    p = sub.add_parser("distance", help=COMMANDS["distance"])
    p.add_argument("a", help="lat,lon")
    p.add_argument("b", help="lat,lon")
    p.set_defaults(func=cmd_distance)

    p = sub.add_parser("geocode", help=COMMANDS["geocode"])
    p.add_argument("address")
    p.add_argument("--limit", type=int, default=5)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_geocode)

    p = sub.add_parser("reverse-geocode", help=COMMANDS["reverse-geocode"])
    p.add_argument("point", help="lat,lon")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_reverse_geocode)

    p = sub.add_parser("exif-gps", help=COMMANDS["exif-gps"])
    p.add_argument("input")
    p.add_argument("--altitude", action="store_true")
    p.set_defaults(func=cmd_exif_gps)

    p = sub.add_parser("bbox", help=COMMANDS["bbox"])
    p.add_argument("input")
    p.set_defaults(func=cmd_bbox)

    p = sub.add_parser("gpx-merge", help=COMMANDS["gpx-merge"])
    p.add_argument("inputs", nargs="+")
    p.add_argument("-o", "--output", required=True)
    p.set_defaults(func=cmd_gpx_merge)

    return parser


@tool_main("geo")
def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 1
    return args.func(args) or 0


if __name__ == "__main__":
    raise SystemExit(main())
