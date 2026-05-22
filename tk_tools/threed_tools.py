"""3D / mesh tools: OBJ, STL, PLY, G-code, bbox, decimate, voxelize."""
from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path

from _common import human_size, lazy_import, tool_main

# ---- OBJ parser ----

def _parse_obj(path: Path):
    verts = []; faces = []; objects = set(); materials = set()
    normals = 0; uvs = 0
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if not parts:
                continue
            tag = parts[0]
            if tag == "v":
                verts.append(tuple(float(x) for x in parts[1:4]))
            elif tag == "vn":
                normals += 1
            elif tag == "vt":
                uvs += 1
            elif tag == "f":
                # face indices may include /vt/vn
                idx = []
                for p in parts[1:]:
                    v = p.split("/")[0]
                    idx.append(int(v))
                faces.append(idx)
            elif tag == "o" and len(parts) > 1:
                objects.add(parts[1])
            elif tag == "usemtl" and len(parts) > 1:
                materials.add(parts[1])
    return verts, faces, objects, materials, normals, uvs


def cmd_obj_info(args):
    verts, faces, objects, materials, normals, uvs = _parse_obj(Path(args.input))
    print(f"Vertices:  {len(verts)}")
    print(f"Faces:     {len(faces)}")
    print(f"Normals:   {normals}")
    print(f"UVs:       {uvs}")
    print(f"Objects:   {len(objects)}  {sorted(objects)}")
    print(f"Materials: {len(materials)}  {sorted(materials)}")
    if verts:
        xs, ys, zs = zip(*verts, strict=False)
        print(f"BBox X:    [{min(xs):.4f}, {max(xs):.4f}]")
        print(f"BBox Y:    [{min(ys):.4f}, {max(ys):.4f}]")
        print(f"BBox Z:    [{min(zs):.4f}, {max(zs):.4f}]")


# ---- STL parser ----

def _is_binary_stl(path: Path) -> bool:
    data = path.read_bytes()
    if len(data) < 84:
        return False
    if data[:5].lower() == b"solid":
        # could still be binary; check size
        try:
            ntri = struct.unpack_from("<I", data, 80)[0]
            expected = 84 + ntri * 50
            return expected == len(data)
        except Exception:
            return False
    return True


def _parse_stl(path: Path):
    """Yield (n, v0, v1, v2)."""
    if _is_binary_stl(path):
        with open(path, "rb") as f:
            f.seek(80)
            ntri = struct.unpack("<I", f.read(4))[0]
            for _ in range(ntri):
                rec = f.read(50)
                if len(rec) < 50:
                    break
                vals = struct.unpack("<12fH", rec)
                n = vals[0:3]; v0 = vals[3:6]; v1 = vals[6:9]; v2 = vals[9:12]
                yield n, v0, v1, v2
    else:
        text = path.read_text(encoding="utf-8", errors="replace")
        n_cur = (0, 0, 0); cur_v = []
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("facet normal"):
                parts = line.split()
                n_cur = tuple(float(x) for x in parts[2:5])
                cur_v = []
            elif line.startswith("vertex"):
                parts = line.split()
                cur_v.append(tuple(float(x) for x in parts[1:4]))
                if len(cur_v) == 3:
                    yield n_cur, cur_v[0], cur_v[1], cur_v[2]


def cmd_stl_info(args):
    path = Path(args.input)
    fmt = "binary" if _is_binary_stl(path) else "ascii"
    ntri = 0
    minx = miny = minz = float("inf")
    maxx = maxy = maxz = float("-inf")
    vol6 = 0.0
    for _, v0, v1, v2 in _parse_stl(path):
        ntri += 1
        for v in (v0, v1, v2):
            if v[0] < minx: minx = v[0]
            if v[1] < miny: miny = v[1]
            if v[2] < minz: minz = v[2]
            if v[0] > maxx: maxx = v[0]
            if v[1] > maxy: maxy = v[1]
            if v[2] > maxz: maxz = v[2]
        # signed tetra volume
        vol6 += (v0[0]*(v1[1]*v2[2] - v1[2]*v2[1])
               - v0[1]*(v1[0]*v2[2] - v1[2]*v2[0])
               + v0[2]*(v1[0]*v2[1] - v1[1]*v2[0]))
    print(f"Format:    {fmt}")
    print(f"Triangles: {ntri}")
    if ntri:
        print(f"BBox X:    [{minx:.4f}, {maxx:.4f}]")
        print(f"BBox Y:    [{miny:.4f}, {maxy:.4f}]")
        print(f"BBox Z:    [{minz:.4f}, {maxz:.4f}]")
        print(f"Size:      {maxx-minx:.4f} x {maxy-miny:.4f} x {maxz-minz:.4f}")
        print(f"Volume:    {abs(vol6) / 6.0:.4f} (signed)")


# ---- obj2stl ----

def cmd_obj2stl(args):
    verts, faces, *_ = _parse_obj(Path(args.input))
    # triangulate fan
    tris = []
    for face in faces:
        if len(face) < 3:
            continue
        for i in range(1, len(face) - 1):
            tris.append((face[0], face[i], face[i + 1]))
    out = Path(args.output)
    if args.ascii:
        lines = ["solid obj"]
        for a, b, c in tris:
            v0 = verts[a-1]; v1 = verts[b-1]; v2 = verts[c-1]
            lines.append("  facet normal 0 0 0")
            lines.append("    outer loop")
            for v in (v0, v1, v2):
                lines.append(f"      vertex {v[0]} {v[1]} {v[2]}")
            lines.append("    endloop")
            lines.append("  endfacet")
        lines.append("endsolid obj")
        out.write_text("\n".join(lines), encoding="utf-8")
    else:
        with open(out, "wb") as f:
            f.write(b"\x00" * 80)
            f.write(struct.pack("<I", len(tris)))
            for a, b, c in tris:
                v0 = verts[a-1]; v1 = verts[b-1]; v2 = verts[c-1]
                f.write(struct.pack("<12fH", 0, 0, 0, *v0, *v1, *v2, 0))
    print(f"Wrote {len(tris)} triangles -> {out}")


# ---- stl2obj ----

def cmd_stl2obj(args):
    verts = []; idx_of = {}; faces = []
    for _, v0, v1, v2 in _parse_stl(Path(args.input)):
        face = []
        for v in (v0, v1, v2):
            key = (round(v[0], 6), round(v[1], 6), round(v[2], 6))
            i = idx_of.get(key)
            if i is None:
                verts.append(key)
                i = len(verts)
                idx_of[key] = i
            face.append(i)
        faces.append(face)
    out = Path(args.output)
    with open(out, "w", encoding="utf-8") as f:
        f.write("# converted by threed_tools\n")
        for v in verts:
            f.write(f"v {v[0]} {v[1]} {v[2]}\n")
        for face in faces:
            f.write(f"f {' '.join(str(i) for i in face)}\n")
    print(f"Wrote {len(verts)} verts, {len(faces)} faces -> {out}")


# ---- ply-info ----

def cmd_ply_info(args):
    with open(args.input, "rb") as f:
        header = []
        while True:
            line = f.readline()
            if not line:
                break
            header.append(line.decode("ascii", errors="replace").rstrip())
            if header[-1] == "end_header":
                break
    if not header or header[0] != "ply":
        print("Not a PLY file"); return 1
    fmt = None; elements = []
    for ln in header:
        if ln.startswith("format "):
            fmt = ln.split()[1]
        elif ln.startswith("element "):
            parts = ln.split()
            elements.append((parts[1], int(parts[2])))
    print(f"Format:   {fmt}")
    print("Elements:")
    for name, count in elements:
        print(f"  {name:<16} {count}")


# ---- gcode-info ----

def cmd_gcode_info(args):
    z_max = float("-inf"); z_min = float("inf"); z_layers = set()
    e_total = 0.0
    cur_e = 0.0; cur_xy = (0.0, 0.0)
    total_xy = 0.0
    time_estimate = 0.0
    feed = 1500.0  # default mm/min
    lines = 0
    with open(args.input, encoding="utf-8", errors="replace") as f:
        for line in f:
            lines += 1
            # strip comment
            line = line.split(";", 1)[0].strip()
            if not line:
                continue
            tokens = line.split()
            cmd = tokens[0].upper()
            if cmd in ("G0", "G1"):
                x = y = z = e = None
                for t in tokens[1:]:
                    try:
                        if t[0].upper() == "X": x = float(t[1:])
                        elif t[0].upper() == "Y": y = float(t[1:])
                        elif t[0].upper() == "Z": z = float(t[1:])
                        elif t[0].upper() == "E": e = float(t[1:])
                        elif t[0].upper() == "F": feed = float(t[1:])
                    except ValueError:
                        pass
                if z is not None:
                    z_layers.add(round(z, 4))
                    if z > z_max: z_max = z
                    if z < z_min: z_min = z
                nx = cur_xy[0] if x is None else x
                ny = cur_xy[1] if y is None else y
                dx = nx - cur_xy[0]; dy = ny - cur_xy[1]
                dist = (dx*dx + dy*dy) ** 0.5
                total_xy += dist
                if feed > 0:
                    time_estimate += dist / (feed / 60.0)
                cur_xy = (nx, ny)
                if e is not None:
                    # relative or absolute? assume absolute (most slicers)
                    de = e - cur_e
                    if de > 0:
                        e_total += de
                    cur_e = e
    print(f"Lines:        {lines}")
    print(f"Z layers:     {len(z_layers)}")
    if z_layers:
        print(f"Z range:      [{z_min:.3f}, {z_max:.3f}]")
    print(f"XY distance:  {total_xy:.1f} mm")
    print(f"Filament:     {e_total:.2f} mm")
    print(f"Est. time:    {time_estimate/60:.1f} min ({time_estimate:.0f} s)")


# ---- mesh-bbox ----

def cmd_mesh_bbox(args):
    path = Path(args.input)
    ext = path.suffix.lower()
    if ext == ".obj":
        verts, *_ = _parse_obj(path)
        if not verts:
            print("Empty"); return 1
        xs, ys, zs = zip(*verts, strict=False)
        print(f"X: [{min(xs):.4f}, {max(xs):.4f}]")
        print(f"Y: [{min(ys):.4f}, {max(ys):.4f}]")
        print(f"Z: [{min(zs):.4f}, {max(zs):.4f}]")
    elif ext == ".stl":
        minv = [float("inf")] * 3; maxv = [float("-inf")] * 3
        for _, v0, v1, v2 in _parse_stl(path):
            for v in (v0, v1, v2):
                for i in range(3):
                    if v[i] < minv[i]: minv[i] = v[i]
                    if v[i] > maxv[i]: maxv[i] = v[i]
        print(f"X: [{minv[0]:.4f}, {maxv[0]:.4f}]")
        print(f"Y: [{minv[1]:.4f}, {maxv[1]:.4f}]")
        print(f"Z: [{minv[2]:.4f}, {maxv[2]:.4f}]")
    else:
        print(f"Unsupported: {ext}"); return 1


# ---- decimate (grid-snap) ----

def cmd_decimate(args):
    path = Path(args.input)
    grid = args.grid
    tris_in = 0; tris_out = []
    seen_tris = set()
    for _, v0, v1, v2 in _parse_stl(path):
        tris_in += 1
        snap = []
        for v in (v0, v1, v2):
            snap.append((round(v[0] / grid) * grid,
                         round(v[1] / grid) * grid,
                         round(v[2] / grid) * grid))
        # drop degenerate
        if len({snap[0], snap[1], snap[2]}) < 3:
            continue
        key = tuple(sorted(snap))
        if key in seen_tris:
            continue
        seen_tris.add(key)
        tris_out.append(snap)
    out = Path(args.output)
    with open(out, "wb") as f:
        f.write(b"\x00" * 80)
        f.write(struct.pack("<I", len(tris_out)))
        for s0, s1, s2 in tris_out:
            f.write(struct.pack("<12fH", 0, 0, 0, *s0, *s1, *s2, 0))
    print(f"In:  {tris_in} triangles")
    print(f"Out: {len(tris_out)} triangles  ({100*len(tris_out)/max(tris_in,1):.1f}%)")
    print(f"Wrote {out}")


# ---- voxelize ----

def cmd_voxelize(args):
    np = lazy_import("numpy", "pip install numpy")
    path = Path(args.input)
    # Read all tris, compute bbox, rasterize triangle-AABBs into voxel grid (occupancy)
    tris = list(_parse_stl(path))
    if not tris:
        print("Empty mesh"); return 1
    minv = [float("inf")] * 3; maxv = [float("-inf")] * 3
    for _, v0, v1, v2 in tris:
        for v in (v0, v1, v2):
            for i in range(3):
                if v[i] < minv[i]: minv[i] = v[i]
                if v[i] > maxv[i]: maxv[i] = v[i]
    size = [maxv[i] - minv[i] for i in range(3)]
    res = args.resolution
    dx = size[0] / res
    dy = size[1] / res
    dz = size[2] / res
    grid = np.zeros((res, res, res), dtype=np.uint8)
    for _, v0, v1, v2 in tris:
        tri = [v0, v1, v2]
        tminx = min(v[0] for v in tri); tmaxx = max(v[0] for v in tri)
        tminy = min(v[1] for v in tri); tmaxy = max(v[1] for v in tri)
        tminz = min(v[2] for v in tri); tmaxz = max(v[2] for v in tri)
        ix0 = max(0, int((tminx - minv[0]) / dx))
        ix1 = min(res - 1, int((tmaxx - minv[0]) / dx))
        iy0 = max(0, int((tminy - minv[1]) / dy))
        iy1 = min(res - 1, int((tmaxy - minv[1]) / dy))
        iz0 = max(0, int((tminz - minv[2]) / dz))
        iz1 = min(res - 1, int((tmaxz - minv[2]) / dz))
        grid[ix0:ix1+1, iy0:iy1+1, iz0:iz1+1] = 1
    out = Path(args.output)
    grid.tofile(out)
    meta = {
        "resolution": res,
        "shape": list(grid.shape),
        "dtype": "uint8",
        "origin": minv,
        "voxel_size": [dx, dy, dz],
        "occupied": int(grid.sum()),
    }
    Path(str(out) + ".json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"Wrote {out} ({human_size(out.stat().st_size)})")
    print(f"Occupied voxels: {int(grid.sum())} / {res**3}")


COMMANDS = {
    "obj-info":   "parse Wavefront OBJ summary",
    "stl-info":   "parse STL (ASCII or binary) summary",
    "obj2stl":    "convert OBJ to STL",
    "stl2obj":    "convert STL to OBJ",
    "ply-info":   "parse PLY header",
    "gcode-info": "parse G-code summary (layers, filament, time)",
    "mesh-bbox":  "compute bbox of OBJ or STL",
    "decimate":   "grid-snap vertex clustering decimation (STL->STL)",
    "voxelize":   "voxelize STL into binary occupancy grid (+JSON meta)",
}


def build_parser(parser=None):
    parser = parser or argparse.ArgumentParser(prog="threed_tools", description="3D/mesh utilities")
    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("obj-info", help=COMMANDS["obj-info"]); p.add_argument("input")
    p.set_defaults(func=cmd_obj_info)

    p = sub.add_parser("stl-info", help=COMMANDS["stl-info"]); p.add_argument("input")
    p.set_defaults(func=cmd_stl_info)

    p = sub.add_parser("obj2stl", help=COMMANDS["obj2stl"])
    p.add_argument("input"); p.add_argument("output")
    p.add_argument("--ascii", action="store_true")
    p.set_defaults(func=cmd_obj2stl)

    p = sub.add_parser("stl2obj", help=COMMANDS["stl2obj"])
    p.add_argument("input"); p.add_argument("output")
    p.set_defaults(func=cmd_stl2obj)

    p = sub.add_parser("ply-info", help=COMMANDS["ply-info"]); p.add_argument("input")
    p.set_defaults(func=cmd_ply_info)

    p = sub.add_parser("gcode-info", help=COMMANDS["gcode-info"]); p.add_argument("input")
    p.set_defaults(func=cmd_gcode_info)

    p = sub.add_parser("mesh-bbox", help=COMMANDS["mesh-bbox"]); p.add_argument("input")
    p.set_defaults(func=cmd_mesh_bbox)

    p = sub.add_parser("decimate", help=COMMANDS["decimate"])
    p.add_argument("input"); p.add_argument("output")
    p.add_argument("--grid", type=float, default=0.5)
    p.set_defaults(func=cmd_decimate)

    p = sub.add_parser("voxelize", help=COMMANDS["voxelize"])
    p.add_argument("input"); p.add_argument("output")
    p.add_argument("--resolution", type=int, default=64)
    p.set_defaults(func=cmd_voxelize)

    return parser


@tool_main("3d")
def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 1
    return args.func(args) or 0


if __name__ == "__main__":
    raise SystemExit(main())
