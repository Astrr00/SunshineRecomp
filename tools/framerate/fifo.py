"""DFF-Aufzeichnungen (Dolphin FIFO Player, Version 6) lesen und zerlegen.

Nachgebaut nach RecompCore ``c6a600eb``: ``Core/FifoPlayer/FifoDataFile.cpp``
(Dateilayout), ``VideoCommon/OpcodeDecoding.h`` (Befehlslaengen),
``VideoCommon/CPMemory.h`` (Vertexbeschreibung) und den Groessentabellen in
``VideoCommon/VertexLoader_*.h``.

Zweck ist der Framerate-Spike (docs/PLAN.md, WP13): Aus zwei aufeinander
folgenden Frames soll hervorgehen, wie das Spiel Matrizen laedt und ob sich
Zeichenbefehle zwischen Frames zuordnen lassen. Die Datei enthaelt Spieldaten
und bleibt lokal; hier werden nur Zaehlwerte gewonnen.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path

FILE_ID = 0x0D01F1F0
HEADER = "<IIIQIQIQIQIQIIQIII8s"   # FifoDataFile.cpp: FileHeader, 128 Bytes

# Matrixspeicher, den ein Zwischenbild interpolieren muss: Positions-,
# Normalen- und Post-Transform-Matrizen (Woerter 0x000-0x0FF, 0x400-0x45F,
# 0x500-0x5FF). Als Momentaufnahme je Zeichenbefehl 608 Woerter.
SNAPSHOT_REGIONS = ((0x000, 0x100), (0x400, 0x460), (0x500, 0x600))
SNAPSHOT_WORDS = sum(end - start for start, end in SNAPSHOT_REGIONS)

# CP-Register
CP_MATINDEX_A, CP_MATINDEX_B = 0x30, 0x40
CP_VCD_LO, CP_VCD_HI = 0x50, 0x60
CP_VAT_A, CP_VAT_B, CP_VAT_C = 0x70, 0x80, 0x90
CP_ARRAY_BASE, CP_ARRAY_STRIDE = 0xA0, 0xB0

# XF-Speicher und -Register
XF_POSMATRICES, XF_POSMATRICES_END = 0x000, 0x100
XF_NORMALMATRICES, XF_NORMALMATRICES_END = 0x400, 0x460
XF_POSTMATRICES, XF_POSTMATRICES_END = 0x500, 0x600
XF_SETMATRIXINDA = 0x1018
XF_PROJECTION = 0x1020  # sechs Gleitkommawerte, dann 0x1026 der Typ (0 perspektivisch, 1 orthografisch)
XF_PROJECTION_WORDS = 7

# Groessen je Attribut: (Art, Format, Elemente) -> Bytes.
# Art: 1 direkt, 2 Index8, 3 Index16. Format: 0..7 wie ComponentFormat.
_POS = {1: {f: (2, 3) if f < 2 else (4, 6) if f < 4 else (8, 12) for f in range(8)},
        2: {f: (1, 1) for f in range(8)}, 3: {f: (2, 2) for f in range(8)}}
_TEX = {1: {f: (1, 2) if f < 2 else (2, 4) if f < 4 else (4, 8) for f in range(8)},
        2: {f: (1, 1) for f in range(8)}, 3: {f: (2, 2) for f in range(8)}}
_COLOR = {1: (2, 3, 4, 2, 3, 4), 2: (1,) * 6, 3: (2,) * 6}


def _normal_size(kind: int, fmt: int, ntb: bool, index3: bool) -> int:
    if kind == 1:
        base = 1 if fmt < 2 else 2 if fmt < 4 else 4
        return base * (9 if ntb else 3)
    unit = 1 if kind == 2 else 2
    return unit * (3 if (ntb and index3) else 1)


class FifoError(Exception):
    pass


@dataclass
class MemoryUpdate:
    fifo_position: int
    address: int
    kind: int
    data: bytes


@dataclass
class Frame:
    index: int
    fifo_start: int
    fifo_end: int
    data: bytes
    updates: list[MemoryUpdate]


@dataclass
class Dff:
    path: Path
    version: int
    game_id: str
    bp_mem: list[int]
    cp_mem: list[int]
    xf_mem: list[int]
    xf_regs: list[int]
    frames: list[Frame]
    # Fuer write(): unveraendert uebernommene Kopffelder und der Texturspeicher
    min_loader: int = 1
    flags: int = 0
    tex_mem: bytes = b""
    mem1_size: int = 0x1800000
    mem2_size: int = 0


def read(path: Path) -> Dff:
    data = path.read_bytes()
    if len(data) < 128:
        raise FifoError("Datei zu klein fuer einen DFF-Kopf.")
    (file_id, version, min_loader, bp_off, bp_size, cp_off, cp_size, xf_off, xf_size,
     xfr_off, xfr_size, frame_list, frame_count, flags, tex_off, tex_size,
     mem1, mem2, game_id) = struct.unpack_from(HEADER, data, 0)
    if file_id != FILE_ID:
        raise FifoError(f"Keine DFF-Datei (Kennung 0x{file_id:08X}).")

    def words(offset: int, count: int) -> list[int]:
        # Die Groessenfelder zaehlen u32-Elemente (FifoDataFile::Load: ReadArray
        # mit header.bpMemSize usw.), nur texMemSize zaehlt Bytes (u8-Feld).
        return list(struct.unpack_from(f"<{count}I", data, offset))

    frames: list[Frame] = []
    for i in range(frame_count):
        (fifo_off, fifo_size, fifo_start, fifo_end, upd_off,
         upd_count) = struct.unpack_from("<QIIIQI", data, frame_list + i * 64)
        updates: list[MemoryUpdate] = []
        for j in range(upd_count):
            pos, address, d_off, d_size, kind = struct.unpack_from(
                "<IIQIB", data, upd_off + j * 24)
            updates.append(MemoryUpdate(pos, address, kind, data[d_off:d_off + d_size]))
        frames.append(Frame(i, fifo_start, fifo_end,
                            data[fifo_off:fifo_off + fifo_size], updates))
    return Dff(path, version, game_id.split(b"\0")[0].decode("ascii", "replace"),
               words(bp_off, bp_size), words(cp_off, cp_size), words(xf_off, xf_size),
               words(xfr_off, xfr_size), frames, min_loader, flags,
               data[tex_off:tex_off + tex_size], mem1, mem2)


def write(dff: Dff, path: Path) -> None:
    """Schreibt eine DFF in Dolphins Dateilayout (FifoDataFile::Save).

    Reihenfolge wie im Original: Kopf, Frameliste, BP/CP/XF-Speicher,
    XF-Register, Texturspeicher, dann je Frame Befehlsstrom und
    Speicheraktualisierungen (erst deren Daten, dann die Eintraege).
    """
    out = bytearray(128 + 64 * len(dff.frames))
    offsets = {}
    for name, words_ in (("bp", dff.bp_mem), ("cp", dff.cp_mem),
                         ("xf", dff.xf_mem), ("xfr", dff.xf_regs)):
        offsets[name] = (len(out), len(words_))     # Anzahl u32, nicht Bytes
        out += struct.pack(f"<{len(words_)}I", *words_)
    offsets["tex"] = (len(out), len(dff.tex_mem))
    out += dff.tex_mem
    for i, frame in enumerate(dff.frames):
        data_off = len(out)
        out += frame.data
        entries = []
        for u in frame.updates:
            d_off = len(out)
            out += u.data
            entries.append(struct.pack("<IIQIB3x", u.fifo_position, u.address,
                                       d_off, len(u.data), u.kind))
        upd_off = len(out)
        out += b"".join(entries)
        struct.pack_into("<QIIIQI32x", out, 128 + 64 * i, data_off, len(frame.data),
                         frame.fifo_start, frame.fifo_end, upd_off, len(frame.updates))
    struct.pack_into(HEADER, out, 0, FILE_ID, dff.version, dff.min_loader,
                     *offsets["bp"], *offsets["cp"], *offsets["xf"], *offsets["xfr"],
                     128, len(dff.frames), dff.flags, *offsets["tex"],
                     dff.mem1_size, dff.mem2_size,
                     dff.game_id.encode("ascii", "replace")[:8].ljust(8, b"\0"))
    path.write_bytes(bytes(out))


# ---------------------------------------------------------------------------
# Befehlsstrom
# ---------------------------------------------------------------------------

@dataclass
class Draw:
    position: int
    primitive: int
    vat: int
    vertices: int
    vertex_size: int
    pos_kind: int             # 0 fehlt, 1 direkt, 2 Index8, 3 Index16
    per_vertex_matrix: bool
    matrix_index: int         # aus MATINDEX_A, Bits 0..5
    matrix: tuple[float, ...]  # aktueller Inhalt der Positionsmatrix (12 Werte)
    matrices_hash: int         # alle Positionsmatrizen 0x000-0x0FF, fuer Matrix je Vertex
    projection: tuple[int, ...]   # XF 0x1020-0x1026: sechs Parameter und der Typ
    texture_key: tuple[int, ...]
    depth: int = 0                  # 0 im Frame selbst, sonst in einer Display-Liste
    xf_snapshot: bytes | None = None  # SNAPSHOT_REGIONS als "<608I", falls angefordert


@dataclass
class FrameSummary:
    draws: list[Draw] = field(default_factory=list)
    xf_matrix_loads: int = 0        # Matrizen per XF-Register, unmittelbar
    xf_indexed_loads: int = 0       # Matrizen per Index aus RAM (INDX A/B/C)
    xf_other_loads: int = 0
    xf_indexed_unresolved: int = 0  # Feld lag nicht in den Speicheraktualisierungen
    projection_loads: int = 0
    bp_loads: int = 0
    cp_loads: int = 0
    display_lists: int = 0
    display_lists_unresolved: int = 0
    bytes_decoded: int = 0
    unknown_opcodes: int = 0
    stopped_early: bool = False


class Decoder:
    """Verfolgt CP-, XF- und BP-Zustand und sammelt Zeichenbefehle."""

    def __init__(self, dff: Dff, snapshots: bool = False):
        self.snapshots = snapshots
        self.cp = list(dff.cp_mem) + [0] * (256 - len(dff.cp_mem))
        self.xf = list(dff.xf_mem) + [0] * (0x1000 - len(dff.xf_mem))
        self.xfr = list(dff.xf_regs) + [0] * (0x58 - len(dff.xf_regs))
        self.bp = list(dff.bp_mem) + [0] * (256 - len(dff.bp_mem))
        self.ram: dict[int, bytes] = {}
        self.last_efb_copy: int | None = None   # Position des letzten BP 0x52 (Frameebene)

    # -- Vertexgroesse aus VCD und VAT -------------------------------------
    def vertex_size(self, vat: int) -> tuple[int, int, bool]:
        lo, hi = self.cp[CP_VCD_LO], self.cp[CP_VCD_HI]
        a, b, c = self.cp[CP_VAT_A + vat], self.cp[CP_VAT_B + vat], self.cp[CP_VAT_C + vat]
        size = bin(lo & 0x1FF).count("1")
        pos_kind = (lo >> 9) & 3
        if pos_kind:
            size += _POS[pos_kind][(a >> 1) & 7][a & 1]
        nrm = (lo >> 11) & 3
        if nrm:
            size += _normal_size(nrm, (a >> 10) & 7, bool((a >> 9) & 1), bool(a >> 31))
        for i in range(2):
            kind = (lo >> (13 + 2 * i)) & 3
            if kind:
                fmt = (a >> (14 + 4 * i)) & 7
                size += _COLOR[kind][min(fmt, 5)]
        tex_fmt = [((a >> 22) & 7, (a >> 21) & 1),
                   ((b >> 1) & 7, b & 1), ((b >> 10) & 7, (b >> 9) & 1),
                   ((b >> 19) & 7, (b >> 18) & 1), ((b >> 28) & 7, (b >> 27) & 1),
                   ((c >> 6) & 7, (c >> 5) & 1), ((c >> 15) & 7, (c >> 14) & 1),
                   ((c >> 24) & 7, (c >> 23) & 1)]
        for i in range(8):
            kind = (hi >> (2 * i)) & 3
            if kind:
                fmt, elements = tex_fmt[i]
                size += _TEX[kind][fmt][elements]
        return size, pos_kind, bool(lo & 1)

    def snapshot(self) -> bytes:
        words: list[int] = []
        for start, end in SNAPSHOT_REGIONS:
            words += self.xf[start:end]
        return struct.pack(f"<{SNAPSHOT_WORDS}I", *words)

    def matrix(self, index: int) -> tuple[float, ...]:
        base = XF_POSMATRICES + index * 4
        raw = self.xf[base:base + 12]
        return tuple(struct.unpack("<f", struct.pack("<I", w))[0] for w in raw)

    def texture_key(self) -> tuple[int, ...]:
        # BP 0x94..0x97, 0xB4..0xB7: Texturadressen der acht Stufen;
        # 0x88..0x8B, 0xA8..0xAB: deren Groessen.
        return tuple(self.bp[r] for r in (0x94, 0x95, 0x96, 0x97, 0xB4, 0xB5, 0xB6, 0xB7,
                                          0x88, 0x89, 0x8A, 0x8B, 0xA8, 0xA9, 0xAA, 0xAB))

    def read_ram(self, address: int, size: int) -> bytes | None:
        """Liest aus den bisher angewandten Speicheraktualisierungen."""
        for start, chunk in self.ram.items():
            if start <= address and address + size <= start + len(chunk):
                offset = address - start
                return chunk[offset:offset + size]
        return None

    def apply_updates(self, updates: list[MemoryUpdate], upto: int) -> None:
        for update in updates:
            if update.fifo_position <= upto and id(update) not in self._applied:
                self.ram[update.address & 0x01FFFFFF] = update.data
                self._applied.add(id(update))

    def run(self, frame: Frame, summary: FrameSummary, data: bytes | None = None,
            base_position: int = 0, depth: int = 0) -> None:
        if depth == 0:
            self._applied = set()
            self.last_efb_copy = None
        stream = frame.data if data is None else data
        pos = 0
        while pos < len(stream):
            op = stream[pos]
            absolute = base_position + pos
            if depth == 0:
                self.apply_updates(frame.updates, absolute)
            if op == 0x00 or op == 0x44 or op == 0x48:
                pos += 1
                continue
            if op == 0x08:                       # CP
                if pos + 6 > len(stream):
                    break
                self.cp[stream[pos + 1]] = struct.unpack_from(">I", stream, pos + 2)[0]
                summary.cp_loads += 1
                pos += 6
                continue
            if op == 0x10:                       # XF
                if pos + 5 > len(stream):
                    break
                cmd = struct.unpack_from(">I", stream, pos + 1)[0]
                address, count = cmd & 0xFFFF, ((cmd >> 16) & 0xF) + 1
                if pos + 5 + count * 4 > len(stream):
                    break
                values = struct.unpack_from(f">{count}I", stream, pos + 5)
                for k, value in enumerate(values):
                    target = address + k
                    if target < 0x1000:
                        self.xf[target] = value
                    elif target - 0x1000 < len(self.xfr):
                        self.xfr[target - 0x1000] = value
                if address < XF_POSTMATRICES_END:
                    summary.xf_matrix_loads += 1
                elif XF_PROJECTION <= address < XF_PROJECTION + XF_PROJECTION_WORDS:
                    summary.projection_loads += 1
                else:
                    summary.xf_other_loads += 1
                pos += 5 + count * 4
                continue
            if op in (0x20, 0x28, 0x30, 0x38):   # INDX A/B/C/D
                if pos + 5 > len(stream):
                    break
                value = struct.unpack_from(">I", stream, pos + 1)[0]
                index, count, address = value >> 16, ((value >> 12) & 0xF) + 1, value & 0xFFF
                array = (op // 8) + 8              # CPArray: 12..15 = Pos/Nrm/Post/Light
                base = self.cp[CP_ARRAY_BASE + array] & 0x01FFFFFF
                stride = self.cp[CP_ARRAY_STRIDE + array] & 0xFF
                words = self.read_ram(base + index * stride, count * 4)
                if words is None:
                    summary.xf_indexed_unresolved += 1
                else:
                    for k in range(count):
                        if address + k < 0x1000:
                            self.xf[address + k] = struct.unpack_from(">I", words, k * 4)[0]
                summary.xf_indexed_loads += 1
                pos += 5
                continue
            if op == 0x40:                       # CALL_DL
                if pos + 9 > len(stream):
                    break
                address, size = struct.unpack_from(">II", stream, pos + 1)
                summary.display_lists += 1
                body = self.ram.get(address & 0x01FFFFFF)
                if body is not None and depth < 4:
                    self.run(frame, summary, body[:size], absolute, depth + 1)
                else:
                    summary.display_lists_unresolved += 1
                pos += 9
                continue
            if op == 0x61:                       # BP
                if pos + 5 > len(stream):
                    break
                self.bp[stream[pos + 1]] = struct.unpack_from(">I", stream, pos + 1)[0] & 0xFFFFFF
                if stream[pos + 1] == 0x52 and depth == 0:   # BPMEM_TRIGGER_EFB_COPY
                    self.last_efb_copy = absolute
                summary.bp_loads += 1
                pos += 5
                continue
            if 0x80 <= op <= 0xBF:               # Primitive
                if pos + 3 > len(stream):
                    break
                vat = op & 7
                count = struct.unpack_from(">H", stream, pos + 1)[0]
                size, pos_kind, per_vertex = self.vertex_size(vat)
                total = 3 + count * size
                if pos + total > len(stream):
                    summary.stopped_early = True
                    break
                index = self.cp[CP_MATINDEX_A] & 0x3F
                summary.draws.append(Draw(
                    absolute, (op & 0x78) >> 3, vat, count, size, pos_kind, per_vertex,
                    index, self.matrix(index), hash(tuple(self.xf[0:0x100])),
                    tuple(self.xfr[0x20:0x27]), self.texture_key(), depth,
                    self.snapshot() if self.snapshots else None))
                pos += total
                continue
            summary.unknown_opcodes += 1
            summary.stopped_early = True
            break
        if depth == 0:
            summary.bytes_decoded = pos


def summarize(dff: Dff, snapshots: bool = False,
              upto: int | None = None, keep: set[int] | None = None) -> list[FrameSummary]:
    """Zerlegt die Frames 0..upto (alle, wenn None). Mit ``keep`` werden nur
    fuer die genannten Frames Zeichenbefehle (und Momentaufnahmen) behalten;
    der Zustand wird trotzdem ueber alle vorherigen Frames gefuehrt."""
    decoder = Decoder(dff, snapshots)
    result = []
    last = len(dff.frames) - 1 if upto is None else upto
    for position, frame in enumerate(dff.frames[:last + 1]):
        summary = FrameSummary()
        decoder.snapshots = snapshots and (keep is None or position in keep)
        decoder.run(frame, summary)
        if keep is not None and position not in keep:
            summary.draws = []
        result.append(summary)
    return result
