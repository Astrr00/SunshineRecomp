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
