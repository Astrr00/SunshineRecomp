"""Einrichtung: Import einer vom Nutzer bereitgestellten Spielkopie.

Das Projekt verteilt keine Spieldaten und laedt keine herunter. Dieser Schritt
liest ausschliesslich ein Abbild, das der Nutzer selbst angibt.

Ergebnis eines Imports:

    <ziel>/
        main.dol        Hauptprogramm, Eingabe fuer DolRecomp
        mario.MAP       Symbol-Map der Disc, Eingabe fuer benannte Hooks
        files/          uebriges Dateisystem (Spieldaten)
        import.json     Nachweis: Revision, Pruefsummen, Zeitpunkt
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import gcm
from gcm import DiscError, DiscHeader, dol_size, extract, read_fst, read_header

# Die Symbol-Map liegt auf der Retail-Disc. Sie traegt die benannten Adressen,
# auf denen die Framerate- und Widescreen-Hooks aufsetzen.
SYMBOL_MAP_NAME = "mario.MAP"


@dataclass(frozen=True)
class Revision:
    """Eine konkret unterstuetzte Spielrevision."""

    game_id: str
    version: int
    label: str
    size: int
    sha256: str
    verified: bool
    """True nur, wenn die Pruefsumme an einer echten Kopie bestaetigt wurde."""
    ships_symbol_map: bool = False
    """Ob diese Revision mario.MAP auf der Disc mitliefert.

    Nur die japanische Fassung tut das; die US-Disc enthaelt sie nicht.
    Siehe docs/01-MACHBARKEIT.md, Abschnitt 2.1.
    """


# Bislang genau eine unterstuetzte Revision, wie vom Auftrag gefordert.
# Die Pruefsumme wurde am 2026-09-09 an einer echten Kopie bestaetigt.
SUPPORTED_REVISIONS: dict[str, Revision] = {
    "GMSE01/0": Revision(
        game_id="GMSE01",
        version=0,
        label="Super Mario Sunshine (USA, Rev 0)",
        size=1_459_978_240,
        sha256="67cec1634e641227a4cd51e6a0b277730cb9a1adaa867530c9e66de45373e51d",
        verified=True,
        ships_symbol_map=False,
    ),
}


class ImportError_(Exception):
    """Der Import kann nicht fortgesetzt werden. Die Meldung ist fuer Nutzer."""


@dataclass
class ImportReport:
    revision: Revision | None = None
    header: DiscHeader | None = None
    sha256: str = ""
    size: int = 0
    checksum_matches: bool = False
    symbol_map_found: bool = False
    extracted_files: int = 0
    warnings: list[str] = field(default_factory=list)


def hash_file(path: Path, progress: Callable[[int, int], None] | None = None,
              chunk_size: int = 1 << 22) -> tuple[str, int]:
    """Berechnet SHA-256 und Groesse in einem Durchlauf."""
    digest = hashlib.sha256()
    total = path.stat().st_size
    read = 0
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
            read += len(chunk)
            if progress:
                progress(read, total)
    return digest.hexdigest(), read


def identify(header: DiscHeader) -> Revision | None:
    return SUPPORTED_REVISIONS.get(f"{header.game_id}/{header.version}")


def _describe_unsupported(header: DiscHeader) -> str:
    """Erklaert verstaendlich, warum eine Kopie nicht angenommen wird."""
    known = ", ".join(r.label for r in SUPPORTED_REVISIONS.values())
    if header.game_code.startswith("GMS"):
        region = {"E": "USA", "J": "Japan", "P": "PAL/Europa"}.get(
            header.game_code[3:4], "unbekannt"
        )
        return (
            f"Diese Kopie ist Super Mario Sunshine, aber die Fassung "
            f"{header.game_id} Rev {header.version} ({region}) wird noch nicht "
            f"unterstuetzt. Unterstuetzt wird derzeit: {known}."
        )
    return (
        f"Das Abbild enthaelt nicht Super Mario Sunshine, sondern "
        f"{header.game_id} \"{header.game_name}\". Unterstuetzt wird: {known}."
    )


def analyse(image: Path, progress: Callable[[int, int], None] | None = None
            ) -> ImportReport:
    """Prueft eine Spielkopie, ohne etwas zu schreiben."""
    if not image.is_file():
        raise ImportError_(f"Die Datei \"{image}\" wurde nicht gefunden.")

    report = ImportReport()
    try:
        with image.open("rb") as stream:
            report.header = read_header(stream)
            files = read_fst(stream, report.header)
    except DiscError as error:
        raise ImportError_(str(error)) from error

    report.revision = identify(report.header)
    if report.revision is None:
        raise ImportError_(_describe_unsupported(report.header))

    report.symbol_map_found = any(f.path == SYMBOL_MAP_NAME for f in files)
    if not report.symbol_map_found and report.revision.ships_symbol_map:
        # Nur melden, wenn diese Revision die Map eigentlich mitbringt --
        # sonst waere es ein Mangel der Kopie. Bei GMSE01 ist das Fehlen
        # normal; dort stammen Hook-Adressen aus anderen Quellen.
        report.warnings.append(
            f"Auf der Disc fehlt {SYMBOL_MAP_NAME}, obwohl diese Revision sie "
            f"normalerweise mitliefert. Die Kopie ist moeglicherweise "
            f"unvollstaendig."
        )

    report.sha256, report.size = hash_file(image, progress)
    report.checksum_matches = report.sha256 == report.revision.sha256

    if not report.checksum_matches:
        if report.size != report.revision.size:
            report.warnings.append(
                f"Die Dateigroesse weicht ab: erwartet "
                f"{report.revision.size:,} Bytes, vorhanden {report.size:,} Bytes. "
                f"Die Kopie ist vermutlich unvollstaendig oder veraendert."
            )
        else:
            report.warnings.append(
                "Die Pruefsumme weicht ab, obwohl die Groesse stimmt. Die Kopie "
                "wurde vermutlich veraendert (Patch, Modifikation)."
            )

    return report


def run(image: Path, destination: Path, allow_mismatch: bool = False,
        progress: Callable[[int, int], None] | None = None) -> ImportReport:
    """Prueft eine Spielkopie und entpackt sie nach ``destination``."""
    report = analyse(image, progress)

    if not report.checksum_matches and not allow_mismatch:
        raise ImportError_(
            "Die Integritaetspruefung ist fehlgeschlagen.\n"
            + "\n".join(f"  - {w}" for w in report.warnings)
            + "\nMit --allow-mismatch kann der Import trotzdem erzwungen werden; "
              "korrektes Verhalten ist dann nicht zugesichert."
        )

    assert report.header is not None
    header = report.header
    destination.mkdir(parents=True, exist_ok=True)
    system = destination / "sys"

    with image.open("rb") as stream:
        # Systembereiche in der von Dolphin erwarteten Anordnung. Die Laufzeit
        # verlangt genau dieses Layout ("invalid extracted game: missing
        # sys/main.dol"), deshalb wird es hier eins zu eins erzeugt.
        extract(stream, 0, gcm.BOOT_BIN_SIZE, system / "boot.bin")
        extract(stream, gcm.BI2_OFFSET, gcm.BI2_SIZE, system / "bi2.bin")
        extract(stream, gcm.APPLOADER_OFFSET, gcm.apploader_size(stream),
                system / "apploader.img")
        extract(stream, header.fst_offset, header.fst_size, system / "fst.bin")
        extract(stream, header.dol_offset, dol_size(stream, header.dol_offset),
                system / "main.dol")

        for entry in read_fst(stream, header):
            extract(stream, entry.offset, entry.size,
                    destination / "files" / entry.path)
            report.extracted_files += 1

    _write_receipt(destination, report)
    return report


def _write_receipt(destination: Path, report: ImportReport) -> None:
    assert report.revision is not None and report.header is not None
    receipt = {
        "imported_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "game_id": report.header.game_id,
        "version": report.header.version,
        "label": report.revision.label,
        "image_sha256": report.sha256,
        "image_size": report.size,
        "checksum_matches": report.checksum_matches,
        "symbol_map": report.symbol_map_found,
        "extracted_files": report.extracted_files,
        "warnings": report.warnings,
    }
    (destination / "import.json").write_text(
        json.dumps(receipt, indent=2, ensure_ascii=False), encoding="utf-8"
    )
