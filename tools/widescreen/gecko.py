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
# ZWEI ANNAHMEN, BEIDE DURCH MESSUNG WIDERLEGT (docs/19-ULTRAWIDE.md):
#   1. Das Wort an 0x80412408 geht von bitgenau 4/3 auf bitgenau 16/9. Es auf
#      64:27 zu setzen aendert an der Projektion nichts -- gemessen an vier
#      gebackenen DOLs und vier FIFO-Aufzeichnungen derselben Szene.
#   2. Die Einfuegung bei 0x80363138 rechnet mit "mal 3/4", also genau
#      (4/3)/(16/9). Den Bruch auf 9/16 zu setzen aendert an der Projektion
#      ebenfalls nichts.
#
# DIE WIRKSAME STELLE IST 0x80416B74. Sie geht von 0,9134614 auf 1,2067341,
# Verhaeltnis 1,321056 -- und genau um diesen Faktor aendert sich das gemessene
# Sichtverhaeltnis der Projektion, von 1,3457 auf 1,7778. Die Konstante ist
# linear im Seitenverhaeltnis:
#
#     Konstante = Seitenverhaeltnis * 0,6787879
#
# Gegenprobe in beide Richtungen: 16/9 mal 0,6787879 ergibt bitgenau
# 0x3F9A7643, den Wert, den der Code schreibt; und 0,9134614 geteilt durch
# 0,6787879 ergibt 1,345724 -- das am unveraenderten Spiel gemessene
# Sichtverhaeltnis 1,3457.
ASPECT_ADDRESS = 0x80412408
ASPECT_16_9 = 0x3FE38E39
SCALE_ADDRESS = 0x80416B74
SCALE_16_9 = 0x3F9A7643

# Die 2D-Ebene haengt an einer eigenen Stelle. Gemessen an denselben vier
# Aufzeichnungen: Der orthografische Maszstab geht von 0,003333 (also 1/300)
# auf 0,0025 (1/400), und das Wort an 0x80416758 geht dabei von 600 auf 800 --
# die halbe Breite ist 300 beziehungsweise 400. Beide Stuetzstellen liegen
# exakt auf Breite = 450 mal Seitenverhaeltnis (450*4/3 = 600, 450*16/9 = 800).
HUD_WIDTH_ADDRESS = 0x80416758
HUD_WIDTH_16_9 = 0x44480000      # 800.0
HUD_WIDTH_PER_ASPECT = 450.0

# Die rechte Kante der 2D-Ebene. Aus Maszstab und Versatz der gemessenen
# orthografischen Projektion laesst sich der Bereich ausrechnen:
#   4:3   Maszstab 0,003333 = 2/600, Versatz -1,00  ->  Bereich   0 .. 600
#   16:9  Maszstab 0,002500 = 2/800, Versatz -0,75  ->  Bereich -100 .. 700
# Die 700 sind genau die beiden Schreibungen unten (600 auf 700). Die rechte
# Kante ist 300 plus halbe Breite, also 300 + 225 mal Seitenverhaeltnis; das
# trifft 600 bei 4:3 und 700 bei 16:9.
EDGE_ADDRESSES = (0x804123E8, 0x80416620)
EDGE_16_9 = 0x442F0000           # 700.0
EDGE_BASE = 300.0
EDGE_PER_ASPECT = 225.0


def _f32(bits: int) -> float:
    return struct.unpack(">f", struct.pack(">I", bits))[0]


# Aus der gemessenen Geraden: Konstante geteilt durch Seitenverhaeltnis.
SCALE_PER_ASPECT = _f32(SCALE_16_9) / (16.0 / 9.0)


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


def scale_bits(aspect: float) -> int:
    """Die Konstante an 0x80416B74 fuer ein Seitenverhaeltnis."""
    return aspect_bits(aspect * SCALE_PER_ASPECT)


def aspect_of_scale(bits: int) -> float:
    """Umgekehrt: welches Seitenverhaeltnis diese Konstante ergibt."""
    return _f32(bits) / SCALE_PER_ASPECT


def hud_width_bits(aspect: float) -> int:
    """Die Breite der 2D-Ebene an 0x80416758 fuer ein Seitenverhaeltnis."""
    return aspect_bits(aspect * HUD_WIDTH_PER_ASPECT)


def edge_bits(aspect: float) -> int:
    """Die rechte Kante der 2D-Ebene fuer ein Seitenverhaeltnis."""
    return aspect_bits(EDGE_BASE + aspect * EDGE_PER_ASPECT)


def retarget_aspect(code: GeckoCode, aspect: float, hud: bool = False) -> GeckoCode:
    """Denselben Code mit einem anderen Seitenverhaeltnis.

    Geaendert wird in der Vorgabe nur 0x80416B74, die Projektion der Kamera.
    Sie ist vollstaendig belegt: 64:27 misst 2,3704, 32:9 misst 3,5556.

    ``hud=True`` skaliert zusaetzlich die 2D-Ebene (0x80416758 und die beiden
    Kanten). Das ist **unfertig** und deshalb nicht Vorgabe: Gemessen wandert
    damit die rechte Kante mit, die linke bleibt bei -100 stehen. Bei 16:9 ist
    der Bereich -100 bis 700, also symmetrisch um den Spielraum 0 bis 600; bei
    64:27 wird er -100 bis 833,33 und damit unsymmetrisch. Solange die Stelle
    der linken Kante nicht gefunden ist, waere das eine Verschlechterung.
    Siehe docs/19-ULTRAWIDE.md.

    Das Wort an 0x80412408 bleibt auf 16/9: Es zu aendern hatte in der Messung
    keine Wirkung, und was es sonst tut, ist offen. Wer es mitaendern will,
    braucht dafuer erst einen Beleg.

    Geprueft wird vorher, dass alle Stellen so aussehen wie erwartet.
    """
    def genau_eins(addresse, erwartet, was):
        treffer = [w for w in code.writes if w.address == addresse]
        if len(treffer) != 1:
            raise GeckoError(f"Erwartet wurde genau ein Schreiben nach "
                             f"{addresse:#010x} ({was}), gefunden {len(treffer)}.")
        if treffer[0].value != erwartet:
            raise GeckoError(f"Erwartet wurde {erwartet:#010x} an {addresse:#010x} "
                             f"({was}), gefunden {treffer[0].value:#010x}.")

    genau_eins(ASPECT_ADDRESS, ASPECT_16_9, "Datenkonstante 16/9")
    genau_eins(SCALE_ADDRESS, SCALE_16_9, "Projektion der Kamera")
    if hud:
        genau_eins(HUD_WIDTH_ADDRESS, HUD_WIDTH_16_9, "Breite der 2D-Ebene")
        for adresse in EDGE_ADDRESSES:
            genau_eins(adresse, EDGE_16_9, "rechte Kante der 2D-Ebene")

    ersatz = {SCALE_ADDRESS: scale_bits(aspect)}
    if hud:
        ersatz[HUD_WIDTH_ADDRESS] = hud_width_bits(aspect)
        for adresse in EDGE_ADDRESSES:
            ersatz[adresse] = edge_bits(aspect)
    writes = [Write(w.address, ersatz[w.address]) if w.address in ersatz else w
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
