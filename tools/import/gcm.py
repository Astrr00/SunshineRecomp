"""Lesen von GameCube-Disc-Abbildern (GCM/ISO).

Nur unkomprimierte 1:1-Abbilder. Formate wie RVZ, WIA, CISO oder GCZ werden
erkannt und mit einer verstaendlichen Meldung abgelehnt, statt als defekt zu
gelten.

Alle Offsets im Disc-Format sind Big-Endian.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Iterator

DISC_MAGIC = 0xC2339F3D
DISC_MAGIC_OFFSET = 0x1C
HEADER_SIZE = 0x440

# Offsets im Disc-Header
OFF_GAME_CODE = 0x00
OFF_MAKER_CODE = 0x04
OFF_DISC_ID = 0x06
OFF_VERSION = 0x07
OFF_GAME_NAME = 0x20
OFF_DOL = 0x420
OFF_FST = 0x424
OFF_FST_SIZE = 0x428

FST_ENTRY_SIZE = 12

# Feste Lage der Systembereiche einer GameCube-Disc.
BOOT_BIN_SIZE = 0x440       # sys/boot.bin, ab Offset 0
BI2_OFFSET = 0x440
BI2_SIZE = 0x2000           # sys/bi2.bin
APPLOADER_OFFSET = 0x2440   # sys/apploader.img

# Signaturen von Containerformaten, die wir nicht selbst auspacken.
_CONTAINER_SIGNATURES = {
    b"RVZ\x01": "RVZ",
    b"WIA\x01": "WIA",
    b"WBFS": "WBFS",
    b"CISO": "CISO",
    b"\x01\xc0\x0b\xb1": "GCZ",
}


class DiscError(Exception):
    """Das Abbild kann nicht als unkomprimiertes GameCube-Abbild gelesen werden."""


@dataclass(frozen=True)
class DiscHeader:
    game_code: str
    maker_code: str
    disc_id: int
    version: int
    game_name: str
    dol_offset: int
    fst_offset: int
    fst_size: int

    @property
    def game_id(self) -> str:
        """Sechsstellige Disc-Kennung, z. B. ``GMSE01``."""
        return f"{self.game_code}{self.maker_code}"

    @property
    def revision(self) -> str:
        return f"{self.game_id} Rev {self.version}"


@dataclass(frozen=True)
class FstEntry:
    path: str
    offset: int
    size: int


def _u32(data: bytes, offset: int) -> int:
    return struct.unpack_from(">I", data, offset)[0]


def _ascii(data: bytes) -> str:
    """Dekodiert einen Feststring und verwirft Fuellbytes."""
    return data.split(b"\0", 1)[0].decode("ascii", errors="replace").strip()


def detect_container(head: bytes) -> str | None:
    """Erkennt bekannte Containerformate. Gibt den Namen oder ``None`` zurueck."""
    for signature, name in _CONTAINER_SIGNATURES.items():
        if head.startswith(signature):
            return name
    return None


def read_header(stream: BinaryIO) -> DiscHeader:
    """Liest und validiert den Disc-Header."""
    stream.seek(0)
    data = stream.read(HEADER_SIZE)
    if len(data) < HEADER_SIZE:
        container = detect_container(data)
        if container:
            raise DiscError(
                f"Das Abbild liegt im {container}-Format vor. Es wird ein "
                f"unkomprimiertes ISO/GCM benoetigt."
            )
        raise DiscError(
            "Die Datei ist zu klein fuer ein GameCube-Abbild "
            f"({len(data)} Bytes gelesen, mindestens {HEADER_SIZE} noetig)."
        )

    if _u32(data, DISC_MAGIC_OFFSET) != DISC_MAGIC:
        container = detect_container(data)
        if container:
            raise DiscError(
                f"Das Abbild liegt im {container}-Format vor. Es wird ein "
                f"unkomprimiertes ISO/GCM benoetigt."
            )
        raise DiscError(
            "Kein GameCube-Abbild: Die Magic-Signatur an Offset 0x1C fehlt. "
            "Wii-Abbilder und beschaedigte Dateien werden hier ebenfalls abgewiesen."
        )

    return DiscHeader(
        game_code=_ascii(data[OFF_GAME_CODE:OFF_GAME_CODE + 4]),
        maker_code=_ascii(data[OFF_MAKER_CODE:OFF_MAKER_CODE + 2]),
        disc_id=data[OFF_DISC_ID],
        version=data[OFF_VERSION],
        game_name=_ascii(data[OFF_GAME_NAME:OFF_GAME_NAME + 0x60]),
        dol_offset=_u32(data, OFF_DOL),
        fst_offset=_u32(data, OFF_FST),
        fst_size=_u32(data, OFF_FST_SIZE),
    )


def read_fst(stream: BinaryIO, header: DiscHeader) -> list[FstEntry]:
    """Liest die Dateitabelle und liefert alle Dateien mit vollem Pfad."""
    if header.fst_size < FST_ENTRY_SIZE:
        raise DiscError("Die Dateitabelle des Abbilds ist leer oder unbrauchbar.")

    stream.seek(header.fst_offset)
    fst = stream.read(header.fst_size)
    if len(fst) < FST_ENTRY_SIZE:
        raise DiscError("Die Dateitabelle konnte nicht gelesen werden.")

    entry_count = _u32(fst, 8)
    strings_start = entry_count * FST_ENTRY_SIZE
    if entry_count == 0 or strings_start > len(fst):
        raise DiscError(
            f"Die Dateitabelle nennt {entry_count} Eintraege, die nicht in "
            f"{len(fst)} Bytes passen. Das Abbild ist vermutlich beschaedigt."
        )

    def name_at(offset: int) -> str:
        absolute = strings_start + offset
        if absolute >= len(fst):
            return ""
        end = fst.index(b"\0", absolute) if b"\0" in fst[absolute:] else len(fst)
        return fst[absolute:end].decode("ascii", errors="replace")

    files: list[FstEntry] = []
    # Verzeichnisse gelten bis zu ihrem "next"-Index. Der Stapel haelt
    # (Endindex, Pfadpraefix) und wird beim Ueberschreiten abgeraeumt.
    directory_stack: list[tuple[int, str]] = []

    for index in range(1, entry_count):
        base = index * FST_ENTRY_SIZE
        raw = _u32(fst, base)
        is_directory = (raw >> 24) != 0
        name = name_at(raw & 0x00FFFFFF)
        arg1 = _u32(fst, base + 4)
        arg2 = _u32(fst, base + 8)

        while directory_stack and index >= directory_stack[-1][0]:
            directory_stack.pop()

        prefix = directory_stack[-1][1] if directory_stack else ""

        if is_directory:
            directory_stack.append((arg2, f"{prefix}{name}/"))
        else:
            files.append(FstEntry(path=f"{prefix}{name}", offset=arg1, size=arg2))

    return files


def dol_size(stream: BinaryIO, dol_offset: int) -> int:
    """Ermittelt die Laenge des Hauptprogramms aus seinem eigenen Kopf.

    Der DOL-Header nennt keine Gesamtlaenge; sie ergibt sich als groesstes
    Ende ueber alle 7 Text- und 11 Datensegmente.
    """
    stream.seek(dol_offset)
    head = stream.read(0x100)
    if len(head) < 0x100:
        raise DiscError("Das Hauptprogramm (main.dol) konnte nicht gelesen werden.")

    total = 0
    for i in range(18):
        offset = _u32(head, i * 4)
        size = _u32(head, 0x90 + i * 4)
        if offset and size:
            total = max(total, offset + size)
    if total == 0:
        raise DiscError("Das Hauptprogramm (main.dol) enthaelt keine Segmente.")
    return total


def apploader_size(stream: BinaryIO) -> int:
    """Ermittelt die Laenge des Apploaders aus seinem Kopf.

    Der Kopf liegt bei 0x2440 und nennt Nutzlast- und Anhangslaenge getrennt;
    die Datei ist beides plus die 0x20 Bytes des Kopfes selbst.
    """
    stream.seek(APPLOADER_OFFSET)
    head = stream.read(0x20)
    if len(head) < 0x20:
        raise DiscError("Der Apploader konnte nicht gelesen werden.")
    payload = _u32(head, 0x14)
    trailer = _u32(head, 0x18)
    return 0x20 + payload + trailer


def extract(stream: BinaryIO, offset: int, size: int, destination: Path,
            chunk_size: int = 1 << 20) -> None:
    """Schreibt einen Bereich des Abbilds stueckweise auf die Festplatte."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    stream.seek(offset)
    remaining = size
    with destination.open("wb") as out:
        while remaining > 0:
            chunk = stream.read(min(chunk_size, remaining))
            if not chunk:
                raise DiscError(
                    f"Das Abbild endet vorzeitig beim Lesen von {destination.name}."
                )
            out.write(chunk)
            remaining -= len(chunk)


def iter_files(path: Path) -> Iterator[FstEntry]:
    """Bequemer Zugriff: liefert alle Dateien eines Abbilds."""
    with path.open("rb") as stream:
        header = read_header(stream)
        yield from read_fst(stream, header)
