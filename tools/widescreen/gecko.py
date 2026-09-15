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
