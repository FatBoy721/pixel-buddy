"""Thumbnail previews for found files. Safe to call from a worker thread (QImage only).

Supported:
  images          loaded directly
  .3mf            embedded slicer thumbnail (Bambu, Orca, Prusa, Cura)
  .gcode          embedded "; thumbnail begin" PNG/JPG blocks (Prusa, Orca, Cura plugins)
  .bgcode         Prusa binary G-code thumbnail blocks
  .stl            rendered on the spot as a shaded 3D view
  everything else Quick Look on macOS (PDF, Word, HEIC, ...), otherwise None
"""

import base64
import math
import re
import struct
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPolygonF

SIZE = 256
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
GCODE_EXTS = {".gcode", ".gco", ".g"}
MAX_STL_TRIANGLES = 60_000


def make_preview(path, size=SIZE):
    path = Path(path)
    ext = path.suffix.lower()
    extractor = {
        ".3mf": from_3mf,
        ".bgcode": from_bgcode,
        ".stl": from_stl,
    }.get(ext, from_gcode if ext in GCODE_EXTS else from_image if ext in IMAGE_EXTS else None)
    image = None
    try:
        if extractor:
            image = extractor(path)
    except Exception:  # noqa: BLE001 - a broken file just means no preview
        image = None
    if (image is None or image.isNull()) and sys.platform == "darwin":
        image = from_quicklook(path, size)
    if image is None or image.isNull():
        return None
    return image.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)


def from_image(path):
    return QImage(str(path))


def from_bytes(data):
    image = QImage()
    image.loadFromData(data)
    return image if not image.isNull() else None


def from_3mf(path):
    with zipfile.ZipFile(path) as z:
        names = [n for n in z.namelist() if n.lower().endswith((".png", ".jpg", ".jpeg"))]
        # Prefer the lit plate render, then any thumbnail, then any image in Metadata.
        ranked = sorted(names, key=lambda n: (
            "no_light" in n,
            not re.search(r"plate_\d+\.png$|thumbnail", n, re.I),
            "small" in n.lower(),
            not n.lower().startswith("metadata/"),
        ))
        for name in ranked:
            image = from_bytes(z.read(name))
            if image:
                return image
    return None


def from_gcode(path):
    with open(path, "rb") as f:
        head = f.read(4_000_000).decode("ascii", "ignore")
    best = None
    pattern = r"; thumbnail(?:_(PNG|JPG))? begin (\d+)x(\d+) \d+\n(.*?); thumbnail(?:_\w+)? end"
    for fmt, w, h, body in re.findall(pattern, head, re.S):
        data = base64.b64decode("".join(line.lstrip("; ").strip() for line in body.splitlines()))
        image = from_bytes(data)
        if image and (best is None or image.width() > best.width()):
            best = image
    return best


def from_bgcode(path):
    """Walk Prusa's binary G-code blocks until the thumbnails (type 5) are found."""
    best = None
    with open(path, "rb") as f:
        if f.read(4) != b"GCDE":
            return None
        _version, checksum_type = struct.unpack("<IH", f.read(6))
        checksum_len = 4 if checksum_type == 1 else 0
        while True:
            header = f.read(8)
            if len(header) < 8:
                break
            block_type, compression, size = struct.unpack("<HHI", header)
            if compression:
                size = struct.unpack("<I", f.read(4))[0]
            if block_type == 5:
                img_format, _w, _h = struct.unpack("<HHH", f.read(6))
                data = f.read(size)
                image = from_bytes(data) if img_format in (0, 1) else None
                if image and (best is None or image.width() > best.width()):
                    best = image
            elif block_type == 1:
                break  # G-code starts; thumbnails always come before it
            else:
                f.seek(2 + size, 1)
            f.seek(checksum_len, 1)
    return best


def read_stl(path):
    with open(path, "rb") as f:
        head = f.read(84)
        count = struct.unpack("<I", head[80:84])[0] if len(head) == 84 else 0
        size = Path(path).stat().st_size
        if count and 84 + count * 50 == size:
            step = max(1, count // MAX_STL_TRIANGLES)
            tris = []
            for i, rec in enumerate(struct.iter_unpack("<12fH", f.read(count * 50))):
                if i % step == 0:
                    tris.append((rec[3:6], rec[6:9], rec[9:12]))
            return tris
    # ASCII STL
    verts = [tuple(map(float, m)) for m in re.findall(
        r"vertex\s+(\S+)\s+(\S+)\s+(\S+)", Path(path).read_text(errors="ignore"))]
    tris = [tuple(verts[i:i + 3]) for i in range(0, len(verts) - 2, 3)]
    step = max(1, len(tris) // MAX_STL_TRIANGLES)
    return tris[::step]


def from_stl(path, size=SIZE):
    """Flat-shaded isometric render, in the crab's orange."""
    tris = read_stl(path)
    if not tris:
        return None
    yaw, pitch = math.radians(35), math.radians(-55)
    cy, sy, cp, sp = math.cos(yaw), math.sin(yaw), math.cos(pitch), math.sin(pitch)

    def rotate(v):
        x, y, z = v
        x, y = x * cy - y * sy, x * sy + y * cy
        y, z = y * cp - z * sp, y * sp + z * cp
        return x, y, z

    faces = []
    for tri in tris:
        a, b, c = (rotate(v) for v in tri)
        ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
        vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
        nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
        length = math.sqrt(nx * nx + ny * ny + nz * nz) or 1
        light = abs(nx * 0.3 - ny * 0.5 + nz * 0.8) / length
        faces.append(((a[1] + b[1] + c[1]) / 3, light, (a, b, c)))

    xs = [p[0] for _d, _l, pts in faces for p in pts]
    zs = [p[2] for _d, _l, pts in faces for p in pts]
    span = max(max(xs) - min(xs), max(zs) - min(zs)) or 1
    scale = (size - 24) / span
    ox = (size - (max(xs) - min(xs)) * scale) / 2 - min(xs) * scale
    oz = (size - (max(zs) - min(zs)) * scale) / 2 + max(zs) * scale

    image = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    image.fill(Qt.transparent)
    p = QPainter(image)
    p.setRenderHint(QPainter.Antialiasing)
    for _depth, light, pts in sorted(faces, key=lambda f: -f[0]):  # far to near
        shade = 0.35 + 0.65 * light
        color = QColor(int(235 * shade), int(110 * shade), int(60 * shade))
        p.setPen(color)  # same-colour edge hides hairline seams between triangles
        p.setBrush(color)
        p.drawPolygon(QPolygonF([QPointF(ox + x * scale, oz - z * scale) for x, _y, z in pts]))
    p.end()
    return image


def from_quicklook(path, size):
    with tempfile.TemporaryDirectory() as tmp:
        try:
            subprocess.run(
                ["qlmanage", "-t", "-s", str(size), "-o", tmp, str(path)],
                capture_output=True, timeout=6, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        for thumb in Path(tmp).glob("*.png"):
            return QImage(str(thumb))
    return None
