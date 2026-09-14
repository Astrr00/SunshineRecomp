"""Symbolliste fuer GMSE01 lesen und nach DolRecomps MAP-Format schreiben.

Die US-Disc enthaelt keine ``mario.MAP`` (nachgeprueft, siehe
docs/01-MACHBARKEIT.md, Abschnitt 2.1). Die hier verarbeitete Liste stammt aus
einem fremden GPL-3.0-Projekt; Herkunft, Commit und Pruefsumme stehen in
tools/symbols/README.md.

Es sind **keine Spieldaten**: Die Liste enthaelt Namen und Adressen, keinen
Programmcode. Sie wird nicht heruntergeladen, sondern liegt angeheftet bei.

Die Regeln unten sind aus DolRecomps ``src/analysis/symbol_map.c`` (Commit
40637c46) abgelesen, nicht vermutet:

* ``symbol_map_load`` verwirft Adressen, die nicht durch 4 teilbar sind.
* ``split_tokens`` trennt an Leerraum; ein Name mit Leerzeichen zerfaellt und
  wuerde als andere Zeilenform gelesen.
* ``valid_name`` lehnt leere Namen, ``.``- und ``*``-Anfaenge sowie ``UNUSED``
  und ``...UNUSED...`` ab.
* ``parse_hex`` nimmt hoechstens acht Hexziffern an.
* Die zweispaltige Form ``adresse name`` setzt Groesse 0. Das ist Absicht:
  ``resolved_size`` in ``src/backend/symbols.c`` leitet die Groesse dann aus
  der naechsten Symboladresse innerhalb derselben Sektion ab. Eine geratene
  Groesse waere schlechter als die abgeleitete.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# MEM1 des GameCube. Alles darueber ist Hardware (etwa der Schreib-Sammel-Pipe
# wgPipe bei 0xCC008000) und gehoert in keine ladbare Sektion.
MEM1_START = 0x80000000
MEM1_END = 0x81800000

# So gross ist der Puffer in DolRecomps src/backend/symbols.c
# ("char identifier[256]"). Laengere Bezeichner werden dort abgeschnitten.
IDENTIFIER_BUFFER = 256

_LINE = re.compile(r"^([^=]+)=0x([0-9A-Fa-f]{1,8})$")
_REJECTED_NAMES = {"UNUSED", "...UNUSED..."}


class SymbolMapError(Exception):
    """Die Symbolliste kann nicht gelesen werden. Die Meldung ist fuer Nutzer."""


@dataclass(frozen=True)
class Symbol:
    name: str
    address: int


@dataclass
class ConversionReport:
    total_lines: int = 0
    blank_lines: int = 0
    accepted: list[Symbol] = field(default_factory=list)
    skipped: dict[str, list[str]] = field(default_factory=dict)

    def skip(self, reason: str, detail: str) -> None:
        self.skipped.setdefault(reason, []).append(detail)

    @property
    def skipped_count(self) -> int:
        return sum(len(v) for v in self.skipped.values())


def _name_is_usable(name: str) -> str | None:
    """Gibt den Ablehnungsgrund zurueck oder ``None``, wenn der Name taugt."""
    if not name:
        return "leerer Name"
    if any(character.isspace() for character in name):
        # split_tokens wuerde hier trennen und die Zeile anders deuten.
        return "Leerraum im Namen"
    if name[0] in ".*":
        return "Name beginnt mit . oder * (valid_name)"
    if name in _REJECTED_NAMES:
        return "Name ist UNUSED (valid_name)"
    return None


def parse(text: str) -> ConversionReport:
    """Liest das Format ``name=0xADRESSE`` und wendet DolRecomps Regeln an."""
    report = ConversionReport()
    seen: set[Symbol] = set()
    for number, line in enumerate(text.splitlines(), start=1):
        report.total_lines += 1
        stripped = line.strip()
        if not stripped:
            report.blank_lines += 1
            continue

        match = _LINE.match(stripped)
        if not match:
            report.skip("unbekannte Zeilenform", f"Zeile {number}: {stripped[:60]}")
            continue

        name, digits = match.group(1), match.group(2)
        reason = _name_is_usable(name)
        if reason is not None:
            report.skip(reason, f"Zeile {number}: {name[:60]}")
            continue

        address = int(digits, 16)
        if address % 4 != 0:
            # symbol_map_load verwirft das ohnehin; hier wird es sichtbar.
            report.skip("Adresse nicht durch 4 teilbar",
                        f"{name} = 0x{address:08X}")
            continue
        if not MEM1_START <= address < MEM1_END:
            report.skip("Adresse ausserhalb MEM1", f"{name} = 0x{address:08X}")
            continue

        symbol = Symbol(name=name, address=address)
        if symbol in seen:
            # Die Quelle fuehrt einige Symbole doppelt. DolRecomps
            # symbol_map_deduplicate wuerde sie zusammenlegen; hier fallen sie
            # schon vorher weg, damit die Ausgabe jede Zeile genau einmal hat.
            report.skip("doppelter Eintrag", f"{name} = 0x{address:08X}")
            continue
        seen.add(symbol)
        report.accepted.append(symbol)

    if not report.accepted:
        raise SymbolMapError(
            "Die Symbolliste enthaelt keine brauchbaren Eintraege. Erwartet "
            "wird je Zeile \"name=0xADRESSE\"."
        )
    return report


def read(path: Path) -> ConversionReport:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise SymbolMapError(f"Die Symbolliste \"{path}\" ist nicht lesbar.") from error
    return parse(text)


def to_dolrecomp(symbols: list[Symbol]) -> str:
    """Erzeugt DolRecomps zweispaltige MAP-Form, stabil sortiert.

    Die Sortierung nach (Adresse, Name) entspricht ``symbol_compare`` im
    Recompiler; damit ist die Ausgabe deterministisch und die dortige
    Deduplizierung greift wie vorgesehen.
    """
    lines = ["# Erzeugt von tools/symbols. Herkunft: tools/symbols/README.md.",
             "# Spalten: Adresse, Name. Keine Groesse -- DolRecomp leitet sie",
             "# aus der naechsten Symboladresse derselben Sektion ab.",
             "#"]
    for symbol in sorted(symbols, key=lambda s: (s.address, s.name)):
        lines.append(f"{symbol.address:08X} {symbol.name}")
    return "\n".join(lines) + "\n"


def to_identifier(name: str, buffer_size: int = IDENTIFIER_BUFFER) -> str:
    """Bildet ``symbol_name_to_identifier`` aus DolRecomp nach.

    Wird gebraucht, um vorab zu sehen, welchen Namen ein Mod spaeter als
    ``DOLRECOMP_SYMBOL_<Bezeichner>`` verwenden kann und wo zwei verschiedene
    Symbole auf denselben Bezeichner fallen.
    """
    out: list[str] = []
    previous_underscore = False
    for character in name:
        emitted = character if (character.isascii() and
                                (character.isalnum() or character == "_")) else "_"
        if not out and emitted.isdigit():
            if len(out) + 1 >= buffer_size:
                break
            out.append("_")
            previous_underscore = True
        if emitted == "_" and previous_underscore:
            continue
        if len(out) + 1 >= buffer_size:
            break
        out.append(emitted)
        previous_underscore = emitted == "_"
    while len(out) > 1 and out[-1] == "_":
        out.pop()
    return "".join(out)


def identifier_collisions(symbols: list[Symbol]) -> dict[str, list[Symbol]]:
    """Bezeichner, auf die mehr als eine Adresse faellt.

    Der Recompiler haengt in diesem Fall die Adresse an, der Name allein ist
    dann also nicht mehr benutzbar. Fuer Mods ist das der Unterschied zwischen
    einem lesbaren und einem geratenen Hook.
    """
    groups: dict[str, list[Symbol]] = {}
    for symbol in symbols:
        groups.setdefault(to_identifier(symbol.name), []).append(symbol)
    return {
        identifier: found
        for identifier, found in groups.items()
        if len({s.address for s in found}) > 1
    }
