"""Framerate-Spike: Zeichenbefehle aufeinander folgender Frames einander zuordnen.

    python tools/framerate analyze <aufzeichnung.dff> [--report <json>]

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
from spike import analyze  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python tools/framerate",
                                     description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    a = sub.add_parser("analyze")
    a.add_argument("dff", type=Path)
    a.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    try:
        dff = fifo.read(args.dff)
    except (fifo.FifoError, OSError) as error:
        print(f"Fehler: {error}", file=sys.stderr)
        return 2
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
              f"{p['matched_direct_positions']}")
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2))
        print(f"  Bericht: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
