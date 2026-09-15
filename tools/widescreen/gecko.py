"""Gecko-Codes aus einer Dolphin-Spiel-INI lesen und einordnen.

Hintergrund: Der spielseitige 16:9-Code fuer GMSE01 laeuft heute ueber Dolphins
Codehandler, also zur Laufzeit. Die davon geaenderten Codebereiche fallen damit
in den SMC-Rueckfall und werden interpretiert statt nativ ausgefuehrt (belegt in
docs/03-WIDESCREEN.md). Wer den Port nativ haben will, muss die Aenderungen vor
der Recompilation in das DOL bringen. Dieses Modul liest sie dafuer ein.

Unterstuetzt werden genau die beiden Codearten, die der Widescreen-Code
verwendet:

``04XXXXXX YYYYYYYY``
    Schreibt das Wort ``YYYYYYYY`` nach ``0x80000000 + 0xXXXXXX``.

``C2XXXXXX NNNNNNNN`` plus ``N`` Folgezeilen
    Fuegt Code bei ``0x80000000 + 0xXXXXXX`` ein. Der Codehandler ersetzt die
    Anweisung an der Zieladresse durch einen Sprung in den eingefuegten Code und
    **ersetzt dessen letztes Wort** durch den Ruecksprung nach Ziel+4. Genau so
    wurde es in docs/03-WIDESCREEN.md am laufenden Spiel im RAM nachgewiesen;
    deshalb ist hier der Rumpf alles bis auf das letzte Wort.

Alles andere wird nicht geraten, sondern als nicht unterstuetzt gemeldet.
"""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass, field

# Basisadresse, auf die sich die 24-Bit-Offsets der Codes beziehen.
GECKO_BASE = 0x80000000
CODE_WRITE32 = 0x04
CODE_INSERT_ASM = 0xC2

_LINE = re.compile(r"^([0-9A-Fa-f]{8})\s+([0-9A-Fa-f]{8})$")
_SECTION = re.compile(r"^\[([^\]]+)\]$")


class GeckoError(Exception):
    """Der Code kann nicht gelesen werden. Die Meldung ist fuer Nutzer."""


@dataclass(frozen=True)
class Write:
    """Ein direktes 32-Bit-Schreiben (Codeart 04)."""
    address: int
    value: int


@dataclass(frozen=True)
class Injection:
    """Eingefuegter Code (Codeart C2).

    ``body`` ist der Nutzcode ohne das vom Handler ersetzte letzte Wort.
    ``placeholder`` ist eben dieses Wort, damit die Annahme pruefbar bleibt.
    """
    address: int
    body: tuple[int, ...]
    placeholder: int

    @property
    def returns_to(self) -> int:
        return self.address + 4


@dataclass
class GeckoCode:
    name: str
    writes: list[Write] = field(default_factory=list)
    injections: list[Injection] = field(default_factory=list)
    unsupported: list[str] = field(default_factory=list)

    @property
    def addresses(self) -> list[int]:
        return ([write.address for write in self.writes] +
                [injection.address for injection in self.injections])


# Das Seitenverhaeltnis im Widescreen-Code.
#
# Der Code von gamemasterplc schreibt an genau einer Stelle das
# Seitenverhaeltnis: 0x80412408 traegt im unveraenderten Spiel 0x3FAAAAAB
# (4/3) und wird auf 0x3FE38E39 (16/9) gesetzt. Beides ist an der Spielkopie
# des Auftraggebers nachgelesen und in docs/19-ULTRAWIDE.md festgehalten.
#
# Fuer 21:9 und 32:9 ist genau dieses eine Wort zu aendern. Die uebrigen zwoelf
# Schreibungen sind Sichtweiten und Befehlsoperanden; sie bleiben unberuehrt,
# weil aus dem Code nicht hervorgeht, wie sie vom Seitenverhaeltnis abhaengen
# -- 600 wird einmal zu 800 (Faktor 4/3) und zweimal zu 700 (Faktor 7/6).
ASPECT_ADDRESS = 0x80412408
ASPECT_16_9 = 0x3FE38E39


def parse_aspect(text: str) -> float:
    """``16:9``, ``64:27`` oder eine Zahl wie ``2.37``."""
    cleaned = text.strip().replace(",", ".")
    if ":" in cleaned:
        left, _, right = cleaned.partition(":")
        try:
            width, height = float(left), float(right)
        except ValueError as error:
            raise GeckoError(f"Seitenverhaeltnis nicht lesbar: {text}") from error
        if height <= 0 or width <= 0:
            raise GeckoError(f"Seitenverhaeltnis muss positiv sein: {text}")
        value = width / height
    else:
        try:
            value = float(cleaned)
        except ValueError as error:
            raise GeckoError(f"Seitenverhaeltnis nicht lesbar: {text}") from error
    if not 1.0 <= value <= 8.0:
        raise GeckoError(f"Seitenverhaeltnis ausserhalb 1.0 bis 8.0: {value}")
    return value


def aspect_bits(aspect: float) -> int:
    """Die 32 Bit der Gleitkommazahl, wie das Spiel sie liest (big endian)."""
    return struct.unpack(">I", struct.pack(">f", aspect))[0]


def retarget_aspect(code: GeckoCode, aspect: float) -> GeckoCode:
    """Denselben Code mit einem anderen Seitenverhaeltnis.

    Geprueft wird, dass die erwartete Stelle vorhanden ist und wirklich 16/9
    traegt. Sonst ist es ein anderer Code als der, gegen den hier gemessen
    wurde, und Raten waere das Falsche.
    """
    treffer = [w for w in code.writes if w.address == ASPECT_ADDRESS]
    if not treffer:
        raise GeckoError(
            f"Der Code '{code.name}' schreibt nichts nach {ASPECT_ADDRESS:#010x}; "
            "das Seitenverhaeltnis laesst sich so nicht aendern.")
    if len(treffer) > 1:
        raise GeckoError(f"Mehrfaches Schreiben nach {ASPECT_ADDRESS:#010x}.")
    if treffer[0].value != ASPECT_16_9:
        raise GeckoError(
            f"Erwartet wurde 16/9 ({ASPECT_16_9:#010x}) an {ASPECT_ADDRESS:#010x}, "
            f"gefunden {treffer[0].value:#010x}.")
    bits = aspect_bits(aspect)
    writes = [Write(w.address, bits) if w.address == ASPECT_ADDRESS else w
              for w in code.writes]
    return GeckoCode(name=f"{code.name} @ {aspect:.6f}", writes=writes,
                     injections=list(code.injections),
                     unsupported=list(code.unsupported))


def list_codes(text: str, section: str = "Gecko") -> list[str]:
    """Namen aller Codes eines INI-Abschnitts, in Reihenfolge."""
    names: list[str] = []
    current = ""
    for line in text.splitlines():
        stripped = line.strip()
        match = _SECTION.match(stripped)
        if match:
            current = match.group(1)
            continue
        if current == section and stripped.startswith("$"):
            names.append(stripped[1:].strip())
    return names


def _code_lines(text: str, name: str, section: str) -> list[str]:
    """Die Datenzeilen genau eines Codes.

    Der Name in der INI traegt haeufig den Autor (``$Widescreen [gamemasterplc]``).
    Gesucht wird deshalb nach dem Namen vor der Autorenklammer.
    """
    wanted = name.strip().lower()
    lines: list[str] = []
    current_section = ""
    collecting = False
    found = False

    for line in text.splitlines():
        stripped = line.strip()
        match = _SECTION.match(stripped)
        if match:
            current_section = match.group(1)
            collecting = False
            continue
        if current_section != section:
            continue
        if stripped.startswith("$"):
            title = stripped[1:].strip()
            bare = title.split("[")[0].strip().lower()
            collecting = bare == wanted or title.lower() == wanted
            found = found or collecting
            continue
        if collecting and stripped and not stripped.startswith(("#", ";", "*")):
            lines.append(stripped)

    if not found:
        available = ", ".join(list_codes(text, section)) or "keine"
        raise GeckoError(
            f"Im Abschnitt [{section}] gibt es keinen Code \"{name}\". "
            f"Vorhanden: {available}")
    return lines


def parse(text: str, name: str, section: str = "Gecko") -> GeckoCode:
    """Liest einen benannten Code und zerlegt ihn in Schreiben und Einfuegungen."""
    words: list[int] = []
    for number, line in enumerate(_code_lines(text, name, section), start=1):
        match = _LINE.match(line)
        if not match:
            raise GeckoError(
                f"Zeile {number} des Codes \"{name}\" hat nicht die Form "
                f"\"XXXXXXXX YYYYYYYY\": {line[:60]}")
        words.append(int(match.group(1), 16))
        words.append(int(match.group(2), 16))

    if not words:
        raise GeckoError(f"Der Code \"{name}\" enthaelt keine Daten.")

    code = GeckoCode(name=name)
    index = 0
    while index + 1 < len(words):
        first, second = words[index], words[index + 1]
        kind = first >> 24
        address = GECKO_BASE + (first & 0x00FFFFFF)

        if kind == CODE_WRITE32:
            code.writes.append(Write(address=address, value=second))
            index += 2
            continue

        if kind == CODE_INSERT_ASM:
            line_count = second
            if line_count == 0:
                raise GeckoError(
                    f"Einfuegung bei 0x{address:08X} nennt null Zeilen.")
            start = index + 2
            end = start + line_count * 2
            if end > len(words):
                raise GeckoError(
                    f"Einfuegung bei 0x{address:08X} nennt {line_count} Zeilen, "
                    f"der Code endet aber vorher.")
            payload = words[start:end]
            code.injections.append(Injection(address=address,
                                             body=tuple(payload[:-1]),
                                             placeholder=payload[-1]))
            index = end
            continue

        code.unsupported.append(
            f"Codeart 0x{kind:02X} bei 0x{address:08X} "
            f"(Wort {first:08X} {second:08X})")
        index += 2

    if index != len(words):
        raise GeckoError(
            f"Der Code \"{name}\" endet mitten in einer Anweisung.")
    return code
