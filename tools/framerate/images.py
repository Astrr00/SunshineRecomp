"""PNG-Bilder lesen und vergleichen, ohne Fremdbibliotheken.

Fuer die Bildpruefung des Zwischenbilds (WP13): Dolphins Frame-Dump schreibt
8-Bit-RGB- oder RGBA-PNGs (Common/Image.cpp). Gelesen werden Farbtyp 2 und 6
mit 8 Bit je Kanal, alle fuenf Filter, ohne Interlacing. Verglichen wird die
mittlere absolute Differenz je Kanal sowie der Anteil abweichender Pixel.
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass
from pathlib import Path


class ImageError(Exception):
    pass


@dataclass
class Image:
    width: int
    height: int
    channels: int
    pixels: bytes        # zeilenweise, channels Bytes je Pixel

    def rgb(self) -> bytes:
        if self.channels == 3:
            return self.pixels
        out = bytearray(self.width * self.height * 3)
        out[0::3] = self.pixels[0::4]
        out[1::3] = self.pixels[1::4]
        out[2::3] = self.pixels[2::4]
        return bytes(out)


def read_png(path: Path) -> Image:
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ImageError(f"{path}: keine PNG-Datei")
    pos, width = 8, None
    idat = bytearray()
    while pos + 8 <= len(data):
        length, kind = struct.unpack_from(">I4s", data, pos)
        body = data[pos + 8:pos + 8 + length]
        if kind == b"IHDR":
            width, height, depth, color, _c, _f, interlace = struct.unpack(">IIBBBBB", body)
            if depth != 8 or color not in (2, 6) or interlace:
                raise ImageError(f"{path}: nur 8-Bit-RGB/RGBA ohne Interlacing "
                                 f"(Tiefe {depth}, Farbtyp {color}, Interlace {interlace})")
            channels = 3 if color == 2 else 4
        elif kind == b"IDAT":
            idat += body
        elif kind == b"IEND":
            break
        pos += 12 + length
    if width is None:
        raise ImageError(f"{path}: IHDR fehlt")
    raw = zlib.decompress(bytes(idat))
    stride = width * channels
    if len(raw) != height * (stride + 1):
        raise ImageError(f"{path}: Bilddaten haben die falsche Laenge")
    out = bytearray(height * stride)
    previous = bytearray(stride)
    bpp = channels
    for y in range(height):
        f = raw[y * (stride + 1)]
        line = bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        if f == 1:
            for x in range(bpp, stride):
                line[x] = (line[x] + line[x - bpp]) & 0xFF
        elif f == 2:
            for x in range(stride):
                line[x] = (line[x] + previous[x]) & 0xFF
        elif f == 3:
            for x in range(stride):
                left = line[x - bpp] if x >= bpp else 0
                line[x] = (line[x] + ((left + previous[x]) >> 1)) & 0xFF
        elif f == 4:
            for x in range(stride):
                a_ = line[x - bpp] if x >= bpp else 0
                b_ = previous[x]
                c_ = previous[x - bpp] if x >= bpp else 0
                p = a_ + b_ - c_
                pa, pb, pc = abs(p - a_), abs(p - b_), abs(p - c_)
                pred = a_ if (pa <= pb and pa <= pc) else (b_ if pb <= pc else c_)
                line[x] = (line[x] + pred) & 0xFF
        elif f != 0:
            raise ImageError(f"{path}: unbekannter Filter {f} in Zeile {y}")
        out[y * stride:(y + 1) * stride] = line
        previous = line
    return Image(width, height, channels, bytes(out))


@dataclass
class Difference:
    mean_abs: float          # mittlere absolute Differenz je Kanal (0..255)
    max_abs: int
    pixels_changed: int      # Pixel mit Differenz > threshold in irgendeinem Kanal
    pixels: int

    def as_dict(self) -> dict:
        return {"mean_abs": round(self.mean_abs, 4), "max_abs": self.max_abs,
                "pixels_changed": self.pixels_changed, "pixels": self.pixels,
                "changed_share": round(self.pixels_changed / self.pixels, 4) if self.pixels else None}


def difference(a: Image, b: Image, threshold: int = 8) -> Difference:
    if (a.width, a.height) != (b.width, b.height):
        raise ImageError(f"Bildgroessen verschieden: {a.width}x{a.height} und {b.width}x{b.height}")
    pa, pb = a.rgb(), b.rgb()
    total = max_abs = changed = 0
    n = a.width * a.height
    for i in range(n):
        d0 = abs(pa[3 * i] - pb[3 * i])
        d1 = abs(pa[3 * i + 1] - pb[3 * i + 1])
        d2 = abs(pa[3 * i + 2] - pb[3 * i + 2])
        total += d0 + d1 + d2
        m = max(d0, d1, d2)
        if m > max_abs:
            max_abs = m
        if m > threshold:
            changed += 1
    return Difference(total / (3 * n) if n else 0.0, max_abs, changed, n)


def write_png(path: Path, image: Image) -> None:
    """Schreibt ein RGB-Bild ungefiltert (fuer Tests und Differenzbilder)."""
    rgb = image.rgb()
    stride = image.width * 3
    raw = b"".join(b"\0" + rgb[y * stride:(y + 1) * stride] for y in range(image.height))

    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + kind + body + \
            struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)
    path.write_bytes(b"\x89PNG\r\n\x1a\n"
                     + chunk(b"IHDR", struct.pack(">IIBBBBB", image.width, image.height, 8, 2, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def difference_image(a: Image, b: Image, gain: int = 4) -> Image:
    pa, pb = a.rgb(), b.rgb()
    out = bytes(min(255, abs(x - y) * gain) for x, y in zip(pa, pb))
    return Image(a.width, a.height, 3, out)


@dataclass
class Betweenness:
    """Liegt das Zwischenbild je Pixel zwischen A und B?

    Fuer Pixel, an denen sich A und B unterscheiden, zaehlt ``in_range`` die
    Pixel, deren Zwischenwert je Kanal im Intervall [min(A,B), max(A,B)] liegt
    (Toleranz ``tolerance``), ``out_of_range`` die uebrigen. ``mid_only`` sind
    Pixel, an denen A und B gleich sind, das Zwischenbild aber abweicht: Das
    ist der Anteil, den die Interpolation neu ins Bild bringt (Subpixelkanten
    oder Fehler).
    """
    ab_changed: int
    in_range: int
    out_of_range: int
    mid_only: int
    pixels: int

    def as_dict(self) -> dict:
        return {"ab_changed": self.ab_changed, "in_range": self.in_range,
                "out_of_range": self.out_of_range, "mid_only": self.mid_only,
                "pixels": self.pixels,
                "in_range_share": round(self.in_range / self.ab_changed, 4) if self.ab_changed else None}


def betweenness(a: Image, mid: Image, b: Image, threshold: int = 8, tolerance: int = 8) -> Betweenness:
    if not (a.width, a.height) == (mid.width, mid.height) == (b.width, b.height):
        raise ImageError("Bildgroessen verschieden")
    pa, pm, pb = a.rgb(), mid.rgb(), b.rgb()
    changed = in_range = out_of_range = mid_only = 0
    n = a.width * a.height
    for i in range(n):
        o = 3 * i
        ab = max(abs(pa[o] - pb[o]), abs(pa[o + 1] - pb[o + 1]), abs(pa[o + 2] - pb[o + 2]))
        if ab > threshold:
            changed += 1
            ok = True
            for c in range(3):
                lo, hi = min(pa[o + c], pb[o + c]), max(pa[o + c], pb[o + c])
                if pm[o + c] < lo - tolerance or pm[o + c] > hi + tolerance:
                    ok = False
                    break
            if ok:
                in_range += 1
            else:
                out_of_range += 1
        else:
            am = max(abs(pa[o] - pm[o]), abs(pa[o + 1] - pm[o + 1]), abs(pa[o + 2] - pm[o + 2]))
            if am > threshold:
                mid_only += 1
    return Betweenness(changed, in_range, out_of_range, mid_only, n)
