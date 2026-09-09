"""Kommandozeilen-Einrichtung fuer den Import einer eigenen Spielkopie.

    python tools/import --check  "D:/Sunshine.iso"
    python tools/import --import "D:/Sunshine.iso" --to build/game
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from importer import (  # noqa: E402
    SUPPORTED_REVISIONS,
    ImportError_,
    ImportReport,
    analyse,
    run,
)


def _progress(read: int, total: int) -> None:
    percent = 100.0 * read / total if total else 0.0
    print(f"\r  Pruefsumme: {percent:5.1f} %", end="", file=sys.stderr, flush=True)


def _report(report: ImportReport) -> None:
    assert report.revision is not None and report.header is not None
    print(f"  Erkannt      : {report.revision.label}")
    print(f"  Disc-Kennung : {report.header.revision}")
    print(f"  Groesse      : {report.size:,} Bytes")
    print(f"  SHA-256      : {report.sha256}")
    print(f"  Integritaet  : {'bestaetigt' if report.checksum_matches else 'ABWEICHUNG'}")
    print(f"  Symbol-Map   : {'gefunden' if report.symbol_map_found else 'FEHLT'}")
    for warning in report.warnings:
        print(f"  Hinweis      : {warning}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python tools/import",
        description="Prueft und importiert eine vom Nutzer bereitgestellte "
                    "Spielkopie. Es werden keine Spieldaten mitgeliefert oder "
                    "heruntergeladen.",
    )
    parser.add_argument("image", type=Path, nargs="?",
                        help="Pfad zum unkomprimierten ISO/GCM-Abbild")
    parser.add_argument("--to", type=Path, default=Path("build/game"),
                        help="Zielverzeichnis des Imports (Vorgabe: build/game)")
    parser.add_argument("--check", action="store_true",
                        help="nur pruefen, nichts entpacken")
    parser.add_argument("--allow-mismatch", action="store_true",
                        help="Import trotz abweichender Pruefsumme erzwingen")
    parser.add_argument("--list-revisions", action="store_true",
                        help="unterstuetzte Spielrevisionen anzeigen")
    args = parser.parse_args(argv)

    if args.list_revisions:
        print("Unterstuetzte Revisionen:")
        for revision in SUPPORTED_REVISIONS.values():
            state = "geprueft" if revision.verified else "ungeprueft"
            print(f"  {revision.game_id} Rev {revision.version}  {revision.label}")
            print(f"    SHA-256 {revision.sha256}  [{state}]")
        return 0

    if args.image is None:
        parser.error("Es wurde kein Abbild angegeben.")

    try:
        if args.check:
            print(f"Pruefe {args.image} ...")
            report = analyse(args.image, _progress)
            print(file=sys.stderr)
            _report(report)
            return 0 if report.checksum_matches else 1

        print(f"Importiere {args.image} nach {args.to} ...")
        report = run(args.image, args.to, args.allow_mismatch, _progress)
        print(file=sys.stderr)
        _report(report)
        print(f"  Entpackt     : {report.extracted_files} Dateien nach {args.to}")
        return 0
    except ImportError_ as error:
        print(file=sys.stderr)
        print(f"Fehler: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
