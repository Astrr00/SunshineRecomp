"""DOL-Sektionen lesen und eine Symbolliste dagegen pruefen.

Die Pruefung braucht die ``sys/main.dol`` aus der Spielkopie des Nutzers und
laeuft deshalb nur auf dessen Rechner. Sie liest die Datei ausschliesslich und
gibt keinen Spielcode aus; im Bericht stehen nur Zaehlwerte.

Warum ueberhaupt statistisch geprueft wird: Dass eine fremde Symbolliste zur
eigenen Spielkopie passt, laesst sich ohne Originalquelle nicht beweisen. Statt
das zu behaupten, misst diese Datei zwei Groessen und stellt ihnen eine
Kontrollgruppe aus zufaelligen, gleich verteilten Adressen gegenueber. Liegen
die Symbolwerte deutlich darueber, treffen die Adressen tatsaechlich
Funktionsgrenzen. Das ist ein Indiz, kein Beweis, und wird auch so berichtet.
"""

from __future__ import annotations

import random
import struct
from dataclasses import dataclass
from pathlib import Path

DOL_HEADER_SIZE = 0x100
TEXT_SECTIONS = 7
DATA_SECTIONS = 11
OFF_SECTION_OFFSETS = 0x00
OFF_SECTION_ADDRESSES = 0x48
OFF_SECTION_SIZES = 0x90
OFF_BSS_ADDRESS = 0xD8
OFF_BSS_SIZE = 0xDC
OFF_ENTRY = 0xE0

# PowerPC-Wortmuster, mit denen eine Funktion typischerweise endet oder nach
# denen Fuellbytes folgen. Vor einem echten Funktionsanfang steht fast immer
# eines davon.
_BLR = 0x4E800020
_BCTR = 0x4E800420
_NOP = 0x60000000
_PADDING = 0x00000000


class DolError(Exception):
    """Die DOL-Datei kann nicht gelesen werden. Die Meldung ist fuer Nutzer."""


@dataclass(frozen=True)
class Section:
    index: int
    executable: bool
    offset: int
    address: int
    size: int

    @property
    def end(self) -> int:
        return self.address + self.size

    def contains(self, address: int) -> bool:
        return self.address <= address < self.end


@dataclass
class Dol:
    path: Path
    data: bytes
    sections: list[Section]
    entry: int
    bss_address: int
    bss_size: int

    @property
    def text_sections(self) -> list[Section]:
        return [s for s in self.sections if s.executable]

    def section_of(self, address: int) -> Section | None:
        for section in self.sections:
            if section.contains(address):
                return section
        return None

    def word_at(self, address: int) -> int | None:
        """Liest ein Big-Endian-Wort an einer virtuellen Adresse."""
        section = self.section_of(address)
        if section is None or address + 4 > section.end:
            return None
        offset = section.offset + (address - section.address)
        if offset + 4 > len(self.data):
            return None
        return struct.unpack_from(">I", self.data, offset)[0]


def read(path: Path) -> Dol:
    try:
        data = path.read_bytes()
    except OSError as error:
        raise DolError(f"Die Datei \"{path}\" ist nicht lesbar.") from error
    if len(data) < DOL_HEADER_SIZE:
        raise DolError(
            f"Die Datei \"{path}\" ist mit {len(data)} Bytes zu klein fuer ein "
            f"DOL (mindestens {DOL_HEADER_SIZE} noetig)."
        )

    sections: list[Section] = []
    for index in range(TEXT_SECTIONS + DATA_SECTIONS):
        offset = struct.unpack_from(">I", data, OFF_SECTION_OFFSETS + index * 4)[0]
        address = struct.unpack_from(">I", data, OFF_SECTION_ADDRESSES + index * 4)[0]
        size = struct.unpack_from(">I", data, OFF_SECTION_SIZES + index * 4)[0]
        if offset == 0 or size == 0:
            continue
        if offset + size > len(data):
            raise DolError(
                f"Sektion {index} liegt ausserhalb der Datei "
                f"(Offset {offset}, Groesse {size}, Datei {len(data)} Bytes). "
                f"Das DOL ist beschaedigt."
            )
        sections.append(Section(index=index, executable=index < TEXT_SECTIONS,
                                offset=offset, address=address, size=size))

    if not sections:
        raise DolError(f"Das DOL \"{path}\" enthaelt keine Sektionen.")
    if not any(section.executable for section in sections):
        raise DolError(f"Das DOL \"{path}\" enthaelt keine ausfuehrbare Sektion.")

    return Dol(
        path=path,
        data=data,
        sections=sections,
        entry=struct.unpack_from(">I", data, OFF_ENTRY)[0],
        bss_address=struct.unpack_from(">I", data, OFF_BSS_ADDRESS)[0],
        bss_size=struct.unpack_from(">I", data, OFF_BSS_SIZE)[0],
    )


def free_text_slots(dol: Dol) -> list[int]:
    """Unbenutzte Textsektions-Plaetze des DOL-Kopfes.

    Fuer WP8 (Widescreen im Rekompilat) wird ein Platz fuer eingefuegten Code
    gebraucht. Ob einer frei ist, entscheidet ueber den Weg dorthin.
    """
    used = {section.index for section in dol.sections}
    return [index for index in range(TEXT_SECTIONS) if index not in used]


def _is_terminator(word: int | None) -> bool:
    if word is None:
        return False
    if word in (_BLR, _BCTR, _NOP, _PADDING):
        return True
    # Unbedingter Sprung (Opcode 18): das Ende eines Tail-Calls.
    return (word >> 26) == 18


def _is_prologue(word: int | None) -> bool:
    if word is None:
        return False
    if (word & 0xFFFF0000) == 0x94210000:  # stwu r1, -N(r1)
        return True
    if word == 0x7C0802A6:  # mflr r0
        return True
    return False


@dataclass
class Measurement:
    sampled: int = 0
    prologue: int = 0
    preceded_by_terminator: int = 0

    def share(self, value: int) -> float:
        return value / self.sampled if self.sampled else 0.0


def measure(dol: Dol, addresses: list[int]) -> Measurement:
    """Zaehlt Prologe an und Terminatoren vor den angegebenen Adressen."""
    result = Measurement()
    for address in addresses:
        section = dol.section_of(address)
        if section is None or not section.executable:
            continue
        result.sampled += 1
        if _is_prologue(dol.word_at(address)):
            result.prologue += 1
        if address - 4 >= section.address and _is_terminator(dol.word_at(address - 4)):
            result.preceded_by_terminator += 1
    return result


def control_sample(dol: Dol, count: int, seed: int = 20260914) -> list[int]:
    """Zufaellige, 4-Byte-ausgerichtete Adressen aus den Textsektionen.

    Fester Startwert, damit der Vergleich wiederholbar bleibt.
    """
    generator = random.Random(seed)
    sections = dol.text_sections
    weights = [section.size for section in sections]
    addresses: list[int] = []
    for _ in range(count):
        section = generator.choices(sections, weights=weights, k=1)[0]
        words = section.size // 4
        if words == 0:
            continue
        addresses.append(section.address + generator.randrange(words) * 4)
    return addresses


# ---------------------------------------------------------------------------
# Schreibender Teil: Worte aendern und Codebereiche anlegen
# ---------------------------------------------------------------------------

# DOL-Sektionen liegen ueblicherweise auf 32 Byte ausgerichtet in der Datei.
SECTION_ALIGNMENT = 0x20


@dataclass(frozen=True)
class Region:
    """Ein belegter Adressbereich des geladenen Programms."""
    start: int
    end: int
    label: str


def memory_map(dol: Dol) -> list[Region]:
    """Alle belegten Bereiche, nach Adresse sortiert -- einschliesslich BSS.

    BSS steht nicht in der Datei, belegt zur Laufzeit aber Speicher. Wer einen
    Codebereich sucht, muss ihn mitrechnen.
    """
    regions = [
        Region(section.address, section.end,
               f"{'text' if section.executable else 'data'}{section.index}")
        for section in dol.sections
    ]
    if dol.bss_size:
        regions.append(Region(dol.bss_address, dol.bss_address + dol.bss_size,
                              "bss"))
    return sorted(regions, key=lambda region: region.start)


def gaps(dol: Dol) -> list[Region]:
    """Luecken zwischen den belegten Bereichen.

    Bereiche koennen einander ueberlappen und tun das bei Sunshine auch: Der
    im Kopf genannte BSS-Bereich spannt von .bss bis .sbss und schliesst
    dazwischenliegende Datensektionen ein. Wer nur aufeinanderfolgende
    Eintraege vergleicht, meldet deshalb Luecken, die in Wirklichkeit BSS sind.
    Deshalb werden die Bereiche erst verschmolzen.

    Nur ein Hinweis, keine Freigabe: Der Spielheap und zur Laufzeit angelegte
    Puffer stehen in keinem DOL-Kopf. Ob eine Luecke wirklich frei bleibt, zeigt
    erst das laufende Spiel.
    """
    regions = memory_map(dol)
    if not regions:
        return []

    merged: list[list] = []
    for region in regions:
        if merged and region.start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], region.end)
            merged[-1][2].append(region.label)
        else:
            merged.append([region.start, region.end, [region.label]])

    result: list[Region] = []
    for previous, following in zip(merged, merged[1:]):
        if following[0] > previous[1]:
            result.append(Region(previous[1], following[0],
                                 f"zwischen {previous[2][-1]} und {following[2][0]}"))
    return result


def branch(source: int, destination: int, link: bool = False) -> int:
    """Kodiert einen unbedingten PowerPC-Sprung (b beziehungsweise bl)."""
    offset = destination - source
    if offset % 4 != 0:
        raise DolError(
            f"Sprung von 0x{source:08X} nach 0x{destination:08X} ist nicht "
            f"durch 4 teilbar.")
    # Das Feld traegt 24 Bit plus zwei implizite Nullbits: +/-32 MiB.
    if not -(1 << 25) <= offset < (1 << 25):
        raise DolError(
            f"Sprung von 0x{source:08X} nach 0x{destination:08X} ist mit "
            f"{offset} Bytes zu weit; ein einzelnes b reicht nur 32 MiB weit.")
    return 0x48000000 | (offset & 0x03FFFFFC) | (1 if link else 0)


class DolBuilder:
    """Aendert ein DOL: einzelne Worte und neue Codesektionen."""

    def __init__(self, source: Dol):
        self.source = source
        self.data = bytearray(source.data)
        self.sections = list(source.sections)
        self._appended: list[Section] = []

    @property
    def appended(self) -> list[Section]:
        return list(self._appended)

    def section_of(self, address: int) -> Section | None:
        for section in self.sections:
            if section.contains(address):
                return section
        return None

    def in_bss(self, address: int) -> bool:
        return (self.source.bss_size != 0 and
                self.source.bss_address <= address
                < self.source.bss_address + self.source.bss_size)

    def write_word(self, address: int, value: int) -> Section:
        """Schreibt ein Wort und gibt die getroffene Sektion zurueck.

        Adressen ausserhalb der Datei -- vor allem in BSS -- sind ein Fehler
        und keine stille Auslassung: BSS steht nicht im DOL, ein Wert dort
        laesst sich nicht einbacken, sondern nur zur Laufzeit setzen.
        """
        if address % 4 != 0:
            raise DolError(f"Adresse 0x{address:08X} ist nicht durch 4 teilbar.")
        section = self.section_of(address)
        if section is None:
            where = "in BSS" if self.in_bss(address) else "ausserhalb aller Sektionen"
            raise DolError(
                f"Adresse 0x{address:08X} liegt {where} und steht damit nicht in "
                f"der Datei. Ein Wert dort kann nur zur Laufzeit gesetzt werden "
                f"(Mod), nicht im DOL.")
        if address + 4 > section.end:
            raise DolError(
                f"Wort bei 0x{address:08X} ragt ueber das Ende von Sektion "
                f"{section.index} hinaus.")
        offset = section.offset + (address - section.address)
        struct.pack_into(">I", self.data, offset, value)
        return section

    def read_word(self, address: int) -> int | None:
        section = self.section_of(address)
        if section is None or address + 4 > section.end:
            return None
        offset = section.offset + (address - section.address)
        return struct.unpack_from(">I", self.data, offset)[0]

    def append_text_section(self, address: int, words: list[int]) -> Section:
        """Legt eine neue Textsektion an und traegt sie in den Kopf ein."""
        if not words:
            raise DolError("Eine leere Sektion wird nicht angelegt.")
        if address % SECTION_ALIGNMENT != 0:
            raise DolError(
                f"Die Sektionsadresse 0x{address:08X} ist nicht auf "
                f"{SECTION_ALIGNMENT} Byte ausgerichtet.")
        used = {section.index for section in self.sections}
        free = [index for index in range(TEXT_SECTIONS) if index not in used]
        if not free:
            raise DolError(
                f"Alle {TEXT_SECTIONS} Textsektions-Plaetze des DOL-Kopfes sind "
                f"belegt. Fuer eingefuegten Code bleibt so kein Platz.")

        size = len(words) * 4
        end = address + size
        for region in memory_map(self.source):
            if address < region.end and region.start < end:
                raise DolError(
                    f"Der Bereich 0x{address:08X}-0x{end:08X} ueberschneidet "
                    f"{region.label} (0x{region.start:08X}-0x{region.end:08X}).")

        padding = (-len(self.data)) % SECTION_ALIGNMENT
        self.data.extend(b"\0" * padding)
        offset = len(self.data)
        for word in words:
            self.data.extend(struct.pack(">I", word))

        index = free[0]
        struct.pack_into(">I", self.data, OFF_SECTION_OFFSETS + index * 4, offset)
        struct.pack_into(">I", self.data, OFF_SECTION_ADDRESSES + index * 4, address)
        struct.pack_into(">I", self.data, OFF_SECTION_SIZES + index * 4, size)
        section = Section(index=index, executable=True, offset=offset,
                          address=address, size=size)
        self.sections.append(section)
        self._appended.append(section)
        return section

    def to_bytes(self) -> bytes:
        return bytes(self.data)
