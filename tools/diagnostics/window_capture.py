#!/usr/bin/env python3
"""Greift das praesentierte Fenster der Laufzeit unter Xvfb ab (docs/18).

Der Bildmitschnitt der Laufzeit (FrameDumper) geht am Nachbearbeiter vorbei,
der Ausgabe-Skalierer ist dort unsichtbar. Dieses Werkzeug startet einen
eigenen Xvfb, laesst die Laufzeit ueber headless_probe mit nativer interner
Aufloesung in ein grosses Fenster zeichnen und liest bei den gewuenschten
Bildnummern den Bildschirm mit xwd -- das ist das Bild nach dem Skalierer.
Je Kern entsteht ein PNG je Bildnummer; gemessen wird der Anteil gleicher
horizontaler Nachbarpixel (Nearest Neighbor hinterlaesst Bloecke, jeder
andere Kern Verlaeufe) und der Anteil nicht-schwarzer Pixel.

Beispiel:
    python tools/diagnostics/window_capture.py --runtime <moderngekko-run> \
        --game <extracted> --module <recomp.so> --output <dir> \
        --sequence tools/acceptance/fixtures/game-start.json \
        --kernels nearest,bilinear --frames 720,900
Braucht Xvfb und xwd (Debian: xvfb, x11-apps).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import struct
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from automation import read_status  # noqa: E402
from tools.framerate.images import Image, write_png  # noqa: E402

KERNELS = ("auto", "bilinear", "bspline", "mitchell", "catmull-rom", "sharp-bilinear", "area",
           "nearest", "hermite")


def xwd_to_image(path: Path) -> Image:
    data = path.read_bytes()
    header = struct.unpack(">25I", data[:100])
    header_size, _, _, _, width, height, _, byte_order, _, _, _, bpp, bpl = header[:13]
    rmask, gmask, bmask, _, _, ncolors = header[14:20]
    offset = header_size + ncolors * 12
    bytes_per_pixel = bpp // 8
    order = "little" if byte_order == 0 else "big"

    def shift(mask: int) -> int:
        return (mask & -mask).bit_length() - 1 if mask else 0

    rs, gs, bs = shift(rmask), shift(gmask), shift(bmask)
    out = bytearray(width * height * 3)
    for y in range(height):
        row = data[offset + y * bpl: offset + y * bpl + width * bytes_per_pixel]
        for x in range(width):
            value = int.from_bytes(row[x * bytes_per_pixel:(x + 1) * bytes_per_pixel], order)
            o = (y * width + x) * 3
            out[o] = (value & rmask) >> rs
            out[o + 1] = (value & gmask) >> gs
            out[o + 2] = (value & bmask) >> bs
    return Image(width, height, 3, bytes(out))


def metrics(image: Image, rows: range) -> dict:
    p = image.rgb()
    w = image.width
    same = nonblack = n = 0
    for y in rows:
        for x in range(1, w):
            o = (y * w + x) * 3
            n += 1
            if p[o:o + 3] == p[o - 3:o]:
                same += 1
            if p[o] or p[o + 1] or p[o + 2]:
                nonblack += 1
    return {"same_neighbour_share": round(same / n, 4), "non_black_share": round(nonblack / n, 4)}


def capture(args, kernel: str, display: str) -> dict:
    out = args.output / kernel
    shutil.rmtree(out, ignore_errors=True)
    cmd = [sys.executable, str(ROOT / "tools/diagnostics/headless_probe.py"),
           "--runtime", str(args.runtime), "--game", str(args.game), "--output", str(out),
           "--frames", "1", "--timeout", str(args.timeout), "--graphics", "Vulkan", "--x11",
           "--video-setting", f"internal_scale={args.internal}",
           "--video-setting", f"output_resolution={args.output_resolution}",
           "--video-setting", f"scaler={kernel}",
           "--core-setting", "WindowCapture=1\n[Interface]\nUsePanicHandlers=False"]
    if args.module:
        cmd += ["--module", str(args.module)]
    if args.sequence:
        cmd += ["--sequence", str(args.sequence)]
    env = dict(os.environ, DISPLAY=display)
    proc = subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    auto = out / "auto"
    result = {"kernel": kernel, "captures": []}
    deadline = time.monotonic() + args.timeout
    try:
        for target in args.frames:
            while time.monotonic() < deadline and proc.poll() is None:
                try:
                    count = int(read_status(auto)["frame_count"])
                except (OSError, KeyError, ValueError, json.JSONDecodeError):
                    count = -1
                if count >= target:
                    xwd = args.output / f"{kernel}-{target}.xwd"
                    subprocess.run(["xwd", "-root", "-display", display, "-silent", "-out", str(xwd)],
                                   check=True, timeout=60)
                    image = xwd_to_image(xwd)
                    png = args.output / f"{kernel}-{target}.png"
                    write_png(png, image)
                    xwd.unlink()
                    rows = range(image.height // 5, image.height * 4 // 5, 4)
                    result["captures"].append({"target": target, "frame": count, "png": str(png),
                                               "width": image.width, "height": image.height,
                                               **metrics(image, rows)})
                    break
                time.sleep(0.2)
            else:
                result["captures"].append({"target": target, "error": "nicht erreicht"})
    finally:
        proc.terminate()
        try:
            proc.wait(20)
        except subprocess.TimeoutExpired:
            proc.kill()
    return result


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--runtime", type=Path, required=True)
    p.add_argument("--game", type=Path, required=True)
    p.add_argument("--module", type=Path)
    p.add_argument("--sequence", type=Path)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--kernels", default="nearest,bilinear",
                   help="Kommaliste aus " + ",".join(KERNELS) + " oder 'alle'")
    p.add_argument("--frames", default="720", help="Kommaliste von Bildnummern")
    p.add_argument("--internal", type=int, default=1, help="interne Aufloesung (1 = nativ)")
    p.add_argument("--output-resolution", default="1920x1080")
    p.add_argument("--screen", default="1920x1080x24", help="Xvfb-Bildschirm")
    p.add_argument("--display", default=":77")
    p.add_argument("--timeout", type=int, default=600)
    args = p.parse_args()
    kernels = list(KERNELS) if args.kernels == "alle" else args.kernels.split(",")
    unknown = [k for k in kernels if k not in KERNELS]
    if unknown:
        p.error(f"unbekannte Kerne: {unknown}")
    args.frames = [int(f) for f in args.frames.split(",")]
    args.output.mkdir(parents=True, exist_ok=True)
    xvfb = subprocess.Popen(["Xvfb", args.display, "-screen", "0", args.screen],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2)
    results = []
    try:
        for kernel in kernels:
            results.append(capture(args, kernel, args.display))
            for c in results[-1]["captures"]:
                if "error" in c:
                    print(f"{kernel:14s} Bild {c['target']}: {c['error']}")
                else:
                    print(f"{kernel:14s} Bild {c['frame']:5d}: gleiche Nachbarn "
                          f"{c['same_neighbour_share'] * 100:5.1f} %, nicht schwarz "
                          f"{c['non_black_share'] * 100:5.1f} %")
    finally:
        xvfb.terminate()
    (args.output / "capture.json").write_text(json.dumps(
        {"internal": args.internal, "output_resolution": args.output_resolution, "results": results},
        indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
