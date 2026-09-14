"""Framerate-Spike: Zeichenbefehle aufeinander folgender Frames einander zuordnen.

    python tools/framerate analyze <aufzeichnung.dff> [--report <json>]
    python tools/framerate interpolate <aufzeichnung.dff> --frames A B --to <neu.dff> [--t 0.5]
    python tools/framerate replay <aufzeichnung.dff> --player <dolphin-emu-nogui> \
        --output <verzeichnis> --images N
    python tools/framerate compare <A.png> <Zwischenbild.png> <B.png> [--report <json>]

Beantwortet fuer WP13 (docs/PLAN.md, Abschnitt 5.3) die messbaren Fragen:
Wie laedt das Spiel Matrizen (unmittelbar oder indiziert aus dem RAM)? Welcher
Anteil der Zeichenbefehle laesst sich zwischen zwei Frames zuordnen? Bei wie
vielen davon aendert sich die Matrix, bei wie vielen die Vertexdaten? Das ist
die Grundlage fuer die Entscheidung zwischen renderer- und spielseitiger
Interpolation -- nicht die Entscheidung selbst.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fifo  # noqa: E402
import images  # noqa: E402
import interpolate  # noqa: E402
import replay  # noqa: E402
from spike import analyze  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python tools/framerate",
                                     description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    a = sub.add_parser("analyze")
    a.add_argument("dff", type=Path)
    a.add_argument("--report", type=Path)
    i = sub.add_parser("interpolate", help="Zwischenframe zwischen zwei Frames erzeugen")
    i.add_argument("dff", type=Path)
    i.add_argument("--frames", type=int, nargs=2, required=True, metavar=("A", "B"))
    i.add_argument("--t", type=float, default=0.5)
    i.add_argument("--to", type=Path, required=True)
    i.add_argument("--report", type=Path)
    r = sub.add_parser("replay", help="DFF kopflos abspielen und Bilder ausgeben")
    r.add_argument("dff", type=Path)
    r.add_argument("--player", type=Path, required=True)
    r.add_argument("--output", type=Path, required=True)
    r.add_argument("--images", type=int, default=8)
    r.add_argument("--timeout", type=float, default=300)
    c = sub.add_parser("compare", help="Liegt das Zwischenbild zwischen A und B?")
    c.add_argument("a", type=Path)
    c.add_argument("mid", type=Path)
    c.add_argument("b", type=Path)
    c.add_argument("--report", type=Path)
    c.add_argument("--diff-prefix", type=Path, help="Differenzbilder <prefix>-A-B.png usw.")
    args = parser.parse_args(argv)
    if args.command == "compare":
        return compare(args)
    if args.command == "replay":
        try:
            found = replay.replay(args.dff, args.player, args.output, args.images, args.timeout)
        except replay.ReplayError as error:
            print(f"Fehler: {error}", file=sys.stderr)
            return 2
        print(f"{len(found)} Bilder unter {args.output / 'user/Dump/Frames'}")
        return 0
    try:
        dff = fifo.read(args.dff)
    except (fifo.FifoError, OSError) as error:
        print(f"Fehler: {error}", file=sys.stderr)
        return 2
    if args.command == "interpolate":
        try:
            result, report = interpolate.synthesize(dff, args.frames[0], args.frames[1], args.t)
        except interpolate.InterpolationError as error:
            print(f"Fehler: {error}", file=sys.stderr)
            return 2
        fifo.write(result, args.to)
        check = interpolate.verify(dff, fifo.read(args.to), report)
        print(f"{args.to}: Zwischenframe {report.middle_index} aus Frames {args.frames[0]} und "
              f"{args.frames[1]} (t={args.t}); {report.matched} von {report.draws_b} Zeichenbefehlen "
              f"zugeordnet, {report.draws_patched} gepatcht, {report.words_interpolated:,} Woerter "
              f"interpoliert in {report.xf_loads_inserted:,} XF-Ladungen (+{report.bytes_inserted:,} B), "
              f"{report.words_restored} Woerter fuer B wiederhergestellt")
        print(f"  Pruefung: Signaturen gleich {check['signatures_identical']}, "
              f"Woerter auf Zwischenwert {check['words_at_midpoint']:,}, daneben "
              f"{check['words_off_midpoint']}, B-Zustand wie im Original "
              f"{check['b_state_as_in_original']}")
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps({"report": report.as_dict(), "verify": check}, indent=2))
        return 0 if (check["signatures_identical"] and not check["words_off_midpoint"]
                     and check["b_state_as_in_original"]) else 1
    report = analyze(dff)
    print(f"{args.dff.name}: DFF v{report['version']} {report['game_id']}, "
          f"{len(report['frames'])} Frames")
    for i, f in enumerate(report["frames"]):
        print(f"  Frame {i}: {f['draws']} Draws, {f['vertices']:,} Vertices, "
              f"Positionen direkt {f['draws_direct_positions']} / indiziert "
              f"{f['draws_indexed_positions']}, Matrix je Vertex "
              f"{f['draws_per_vertex_matrix']}, orthografisch {f['draws_orthographic']}; "
              f"XF unmittelbar {f['xf_matrix_loads_immediate']}, indiziert "
              f"{f['xf_matrix_loads_indexed']} (unaufgeloest "
              f"{f['xf_matrix_loads_indexed_unresolved']}), Projektion {f['projection_loads']}"
              + (", ABGEBROCHEN" if f['stopped_early'] else ""))
    for p in report["pairs"]:
        print(f"  Frames {p['frames'][0]}->{p['frames'][1]}: zugeordnet {p['matched']} von "
              f"{p['draws_current']} ({p['matched_share_of_current']:.1%}); davon Matrix "
              f"geaendert {p['matched_matrix_changed']}, Matrixindex geaendert "
              f"{p['matched_matrix_index_changed']}, Projektion geaendert "
              f"{p['matched_projection_changed']}, direkte Positionen "
              f"{p['matched_direct_positions']}; Verschiebung Median "
              f"{(p['motion_translation_median'] or 0):.2f} / 90 % "
              f"{(p['motion_translation_p90'] or 0):.2f} / max "
              f"{(p['motion_translation_max'] or 0):.1f}"
              + (", SCHNITT" if p["cut"] else ""))
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2))
        print(f"  Bericht: {args.report}")
    return 0


def compare(args) -> int:
    try:
        a, mid, b = (images.read_png(p) for p in (args.a, args.mid, args.b))
        result = {"A_mid": images.difference(a, mid).as_dict(),
                  "mid_B": images.difference(mid, b).as_dict(),
                  "A_B": images.difference(a, b).as_dict(),
                  "betweenness": images.betweenness(a, mid, b).as_dict()}
        if args.diff_prefix:
            for tag, (x, y) in (("A-B", (a, b)), ("A-mid", (a, mid)), ("mid-B", (mid, b))):
                images.write_png(Path(f"{args.diff_prefix}-{tag}.png"), images.difference_image(x, y))
    except (images.ImageError, OSError) as error:
        print(f"Fehler: {error}", file=sys.stderr)
        return 2
    for key in ("A_mid", "mid_B", "A_B"):
        d = result[key]
        print(f"  {key:6}: mittlere Differenz {d['mean_abs']:.3f}, {d['pixels_changed']:,} von "
              f"{d['pixels']:,} Pixeln geaendert ({d['changed_share']:.2%})")
    bt = result["betweenness"]
    print(f"  Zwischen A und B: {bt['in_range']:,} von {bt['ab_changed']:,} geaenderten Pixeln "
          f"im Intervall ({bt['in_range_share']:.1%}), {bt['out_of_range']:,} ausserhalb, "
          f"{bt['mid_only']:,} nur im Zwischenbild geaendert")
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
