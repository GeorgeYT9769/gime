#!/usr/bin/env python3
"""Generate Gime's app icon (gime.png + gime.ico) with no dependencies.

The mark is a git branch — a vertical trunk with three nodes and a branch
line to a fourth node — on an indigo-to-cyan rounded square.

Run:  python make_icon.py
"""

from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent
N = 1024                      # supersampled render canvas
GRADIENT_A = (99, 102, 241)   # indigo-500, top-left
GRADIENT_B = (34, 211, 238)   # cyan-400, bottom-right
CORNER_RADIUS = 0.225         # fraction of the icon size
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)

# Glyph geometry, normalised to 0..1 — a git branch.
LINE_RADIUS = 0.050
NODE_RADIUS = 0.098
TRUNK_X = 0.34
NODE_YS = (0.22, 0.50, 0.78)
BRANCH_END_X = 0.68


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
def _primitives() -> list[tuple]:
    """Circles and capsules making up the branch, in canvas pixels."""
    prims: list[tuple] = []
    x, y = TRUNK_X * N, NODE_YS[0] * N
    y2 = NODE_YS[-1] * N
    prims.append(("seg", x, y, x, y2, LINE_RADIUS * N))          # trunk
    my = NODE_YS[1] * N
    prims.append(("seg", x, my, BRANCH_END_X * N, my, LINE_RADIUS * N))
    for ny in NODE_YS:                                            # nodes
        prims.append(("cir", x, ny * N, NODE_RADIUS * N))
    prims.append(("cir", BRANCH_END_X * N, my, NODE_RADIUS * N))
    return prims


def _segment_distance(px: float, py: float, x1: float, y1: float,
                      x2: float, y2: float) -> float:
    vx, vy = x2 - x1, y2 - y1
    length_sq = vx * vx + vy * vy
    if length_sq == 0:
        return math.hypot(px - x1, py - y1)
    t = ((px - x1) * vx + (py - y1) * vy) / length_sq
    if t < 0.0:
        t = 0.0
    elif t > 1.0:
        t = 1.0
    return math.hypot(px - (x1 + t * vx), py - (y1 + t * vy))


def _glyph_bounds(prims: list[tuple]) -> tuple[int, int, int, int]:
    xs0, ys0, xs1, ys1 = N, N, 0, 0
    for prim in prims:
        if prim[0] == "seg":
            _, x1, y1, x2, y2, rad = prim
            box = (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))
        else:
            _, cx, cy, rad = prim
            box = (cx, cy, cx, cy)
        xs0 = min(xs0, box[0] - rad)
        ys0 = min(ys0, box[1] - rad)
        xs1 = max(xs1, box[2] + rad)
        ys1 = max(ys1, box[3] + rad)
    pad = 4
    return (max(0, int(xs0) - pad), max(0, int(ys0) - pad),
            min(N, int(xs1) + pad + 1), min(N, int(ys1) + pad + 1))


def render() -> bytearray:
    """Draw the icon at N x N and return RGBA bytes."""
    px = bytearray(N * N * 4)

    radius = CORNER_RADIUS * N
    inset = 1.0
    cx = cy = N / 2.0
    half_x = N / 2.0 - inset
    half_y = N / 2.0 - inset
    inner_x = half_x - radius
    inner_y = half_y - radius

    prims = _primitives()
    gx0, gy0, gx1, gy1 = _glyph_bounds(prims)
    white = (255, 255, 255)

    for yy in range(N):
        y = yy + 0.5
        row = yy * N * 4
        dy = abs(y - cy) - inner_y
        dy_out_sq = max(dy, 0.0) ** 2

        in_glyph_rows = gy0 <= yy < gy1

        for xx in range(N):
            x = xx + 0.5
            dx = abs(x - cx) - inner_x
            outside = math.sqrt(max(dx, 0.0) ** 2 + dy_out_sq)
            inside = min(max(dx, dy), 0.0)
            d = outside + inside - radius
            coverage = 0.5 - d
            if coverage <= 0.0:
                continue
            if coverage > 1.0:
                coverage = 1.0

            # Indigo -> cyan diagonal gradient.
            t = ((x / N) + (y / N)) * 0.5
            r = GRADIENT_A[0] + (GRADIENT_B[0] - GRADIENT_A[0]) * t
            g = GRADIENT_A[1] + (GRADIENT_B[1] - GRADIENT_A[1]) * t
            b = GRADIENT_A[2] + (GRADIENT_B[2] - GRADIENT_A[2]) * t

            if in_glyph_rows and gx0 <= xx < gx1:
                best = float("inf")
                for prim in prims:
                    if prim[0] == "seg":
                        _, x1, y1, x2, y2, rad = prim
                        dist = _segment_distance(x, y, x1, y1, x2, y2) - rad
                    else:
                        _, sx, sy, rad = prim
                        dist = math.hypot(x - sx, y - sy) - rad
                    if dist < best:
                        best = dist
                        if best < -NODE_RADIUS * N:
                            break
                glyph = 0.5 - best
                if glyph > 0.0:
                    if glyph > 1.0:
                        glyph = 1.0
                    r += (white[0] - r) * glyph
                    g += (white[1] - g) * glyph
                    b += (white[2] - b) * glyph

            i = row + xx * 4
            px[i] = int(r + 0.5)
            px[i + 1] = int(g + 0.5)
            px[i + 2] = int(b + 0.5)
            px[i + 3] = int(coverage * 255 + 0.5)

    return px


# --------------------------------------------------------------------------- #
# Resizing (area average, premultiplied so edges stay clean)
# --------------------------------------------------------------------------- #
def resize(src: bytearray, size: int) -> bytearray:
    scale = N / size
    out = bytearray(size * size * 4)
    for oy in range(size):
        y0 = int(oy * scale)
        y1 = max(y0 + 1, int((oy + 1) * scale))
        for ox in range(size):
            x0 = int(ox * scale)
            x1 = max(x0 + 1, int((ox + 1) * scale))
            count = (y1 - y0) * (x1 - x0)
            a_sum = r_sum = g_sum = b_sum = 0
            for y in range(y0, y1):
                base = y * N * 4
                for x in range(x0, x1):
                    i = base + x * 4
                    a = src[i + 3]
                    a_sum += a
                    r_sum += src[i] * a
                    g_sum += src[i + 1] * a
                    b_sum += src[i + 2] * a
            o = (oy * size + ox) * 4
            if a_sum:
                out[o] = min(255, round(r_sum / a_sum))
                out[o + 1] = min(255, round(g_sum / a_sum))
                out[o + 2] = min(255, round(b_sum / a_sum))
                out[o + 3] = min(255, round(a_sum / count))
    return out


# --------------------------------------------------------------------------- #
# File formats
# --------------------------------------------------------------------------- #
def write_png(path: Path, rgba: bytearray, size: int,
              height: int | None = None) -> None:
    height = size if height is None else height

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data +
                struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    raw = bytearray()
    stride = size * 4
    for y in range(height):
        raw.append(0)                       # filter type: None
        raw.extend(rgba[y * stride:(y + 1) * stride])

    png = bytearray(b"\x89PNG\r\n\x1a\n")
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", size, height, 8, 6, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    png += chunk(b"IEND", b"")
    path.write_bytes(bytes(png))


def write_ico(path: Path, images: dict[int, bytearray]) -> None:
    """ICO container with PNG-compressed entries (supported since Vista)."""
    entries = []
    blob = bytearray()
    offset = 6 + 16 * len(images)
    for size in sorted(images):
        data = bytearray()
        # Re-encode each size as its own PNG.
        tmp = path.with_suffix(f".{size}.png")
        write_png(tmp, images[size], size)
        data = tmp.read_bytes()
        tmp.unlink()
        entries.append((size, len(data), offset))
        offset += len(data)
        blob += data

    out = bytearray(struct.pack("<HHH", 0, 1, len(images)))
    for size, length, at in entries:
        dim = 0 if size >= 256 else size
        out += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, length, at)
    out += blob
    path.write_bytes(bytes(out))


# --------------------------------------------------------------------------- #
def main() -> None:
    print(f"rendering {N}x{N} …")
    canvas = render()

    images: dict[int, bytearray] = {}
    for size in ICO_SIZES:
        images[size] = resize(canvas, size)
        print(f"  {size}x{size} done")

    png_path = OUT_DIR / "gime.png"
    write_png(png_path, images[256], 256)
    ico_path = OUT_DIR / "gime.ico"
    write_ico(ico_path, images)

    print(f"wrote {png_path.name} ({png_path.stat().st_size} bytes)")
    print(f"wrote {ico_path.name} ({ico_path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
