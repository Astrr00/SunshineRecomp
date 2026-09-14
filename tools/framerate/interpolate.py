"""Synthetisches Zwischenbild aus zwei Frames einer DFF-Aufzeichnung (WP13).

Modell der Variante A aus docs/PLAN.md 5.2 (Interpolation auf Rendererseite),
hier offline nachgestellt: Der Befehlsstrom des zweiten Frames (B) wird
unveraendert uebernommen; vor jedem Zeichenbefehl, der einem Zeichenbefehl des
ersten Frames (A) zugeordnet ist, werden die Matrizen, die sich zwischen A und
B geaendert haben, auf den Zwischenwert (t) gesetzt. Geometrie, Texturen und
alle uebrigen Befehle bleiben, wie B sie gesendet hat. Nicht zugeordnete
Zeichenbefehle bleiben unveraendert (Zustand von B).

Interpoliert werden die Positions-, Normalen- und Post-Transform-Matrizen
(fifo.SNAPSHOT_REGIONS) linear je Wort als float32 sowie die fuenf
Projektionsparameter, sofern der Projektionstyp gleich bleibt. Das ist die
einfachste Form; Rotationen werden affin gemischt, was bei kleinen Schritten
zwischen zwei Frames genuegt und hier gerade geprueft werden soll.

Das Ergebnis ist eine DFF mit dem Zwischenframe zwischen A und B, abspielbar
im FIFO-Player (tools/framerate/replay.py). Sie enthaelt Spieldaten und bleibt
lokal.
"""

from __future__ import annotations

import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fifo  # noqa: E402
from spike import match  # noqa: E402

XF_LOAD_MAX_WORDS = 16   # OpcodeDecoding: 4 Bit Zaehler im XF-Ladebefehl


class InterpolationError(Exception):
    pass


@dataclass
class Report:
    frames: tuple[int, int]
    t: float
    draws_a: int = 0
    draws_b: int = 0
    matched: int = 0
    matched_in_display_lists: int = 0     # nicht patchbar, bleiben wie in B
    draws_patched: int = 0
    words_interpolated: int = 0
    xf_loads_inserted: int = 0
    projection_patched: int = 0
    projection_type_changed: int = 0
    bytes_b: int = 0
    bytes_inserted: int = 0
    updates_shifted: int = 0
    middle_index: int = -1
    bytes_restored: int = 0       # Wiederherstellung des XF-Zustands nach A am Ende
    words_restored: int = 0
    inserted_at: list[int] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {k: (list(v) if isinstance(v, tuple) else v)
                for k, v in self.__dict__.items() if k != "inserted_at"} | {
                    "inserted_sites": len(self.inserted_at)}


def _f32(word: int) -> float:
    return struct.unpack("<f", struct.pack("<I", word))[0]


def _word(value: float) -> int:
    return struct.unpack("<I", struct.pack("<f", value))[0]


def lerp_words(a: int, b: int, t: float) -> int:
    """Zwischenwert zweier float32-Woerter; gleiche Woerter bleiben exakt."""
    if a == b:
        return b
    fa, fb = _f32(a), _f32(b)
    return _word(fa + (fb - fa) * t)


def xf_load(address: int, words: list[int]) -> bytes:
    assert 1 <= len(words) <= XF_LOAD_MAX_WORDS
    return bytes([0x10]) + struct.pack(">I", ((len(words) - 1) << 16) | address) + \
        b"".join(struct.pack(">I", w) for w in words)


def loads_for(changes: dict[int, int]) -> bytes:
    """Fasst geaenderte XF-Woerter (Adresse -> Wort) zu Ladebefehlen zusammen."""
    out = bytearray()
    run_start, run_words = None, []
    for address in sorted(changes) + [None]:
        contiguous = (address is not None and run_start is not None
                      and address == run_start + len(run_words)
                      and len(run_words) < XF_LOAD_MAX_WORDS)
        if not contiguous and run_words:
            out += xf_load(run_start, run_words)
            run_start, run_words = None, []
        if address is None:
            break
        if run_start is None:
            run_start = address
        run_words.append(changes[address])
    return bytes(out)


def snapshot_addresses() -> list[int]:
    addresses = []
    for start, end in fifo.SNAPSHOT_REGIONS:
        addresses += range(start, end)
    return addresses


def synthesize(dff: fifo.Dff, a: int, b: int, t: float = 0.5) -> tuple[fifo.Dff, Report]:
    """Erzeugt die DFF mit dem Zwischenframe zwischen den Frames a und b."""
    if not 0 <= a < b < len(dff.frames):
        raise InterpolationError(f"Es muss 0 <= a < b < Frameanzahl gelten "
                                 f"(a={a}, b={b}, {len(dff.frames)} Frames).")
    if not 0.0 < t < 1.0:
        raise InterpolationError("t muss zwischen 0 und 1 liegen (ausschliesslich).")
    summaries = fifo.summarize(dff, snapshots=True)
    draws_a, draws_b = summaries[a].draws, summaries[b].draws
    if summaries[b].stopped_early or summaries[a].stopped_early:
        raise InterpolationError("Ein Frame wurde nicht vollstaendig dekodiert.")
    report = Report((a, b), t, len(draws_a), len(draws_b), bytes_b=len(dff.frames[b].data))
    addresses = snapshot_addresses()
    unpack = struct.Struct(f"<{fifo.SNAPSHOT_WORDS}I").unpack

    inserts: dict[int, bytes] = {}       # Position im Strom von B -> einzufuegende Bytes
    for i, j in match(draws_a, draws_b):
        report.matched += 1
        da, db = draws_a[i], draws_b[j]
        if db.depth:
            report.matched_in_display_lists += 1
            continue
        changes: dict[int, int] = {}
        if da.xf_snapshot != db.xf_snapshot:
            wa, wb = unpack(da.xf_snapshot), unpack(db.xf_snapshot)
            for address, x, y in zip(addresses, wa, wb):
                if x != y:
                    changes[address] = lerp_words(x, y, t)
        piece = loads_for(changes)
        if da.projection != db.projection:
            if da.projection[6] != db.projection[6]:
                report.projection_type_changed += 1
            else:
                piece += xf_load(fifo.XF_PROJECTION,
                                 [lerp_words(x, y, t) for x, y in zip(da.projection[:6], db.projection[:6])]
                                 + [db.projection[6]])
                report.projection_patched += 1
        if piece:
            inserts[db.position] = inserts.get(db.position, b"") + piece
            report.draws_patched += 1
            report.words_interpolated += len(changes)
            report.xf_loads_inserted += _count_loads(piece)

    source = dff.frames[b].data
    out = bytearray()
    shift_at: list[tuple[int, int]] = []   # (Position in B, kumulierte Verschiebung)
    cursor, shifted = 0, 0
    for position in sorted(inserts):
        out += source[cursor:position]
        out += inserts[position]
        shifted += len(inserts[position])
        shift_at.append((position, shifted))
        report.inserted_at.append(position)
        cursor = position
    out += source[cursor:]
    report.bytes_inserted = shifted

    def shifted_position(q: int) -> int:
        k = 0
        for position, total in shift_at:
            if position < q:
                k = total
            else:
                break
        return q + k

    updates = []
    for u in dff.frames[b].updates:
        new_position = shifted_position(u.fifo_position)
        report.updates_shifted += new_position != u.fifo_position
        updates.append(fifo.MemoryUpdate(new_position, u.address, u.kind, u.data))
    middle = fifo.Frame(-1, dff.frames[b].fifo_start, dff.frames[b].fifo_end, bytes(out), updates)

    # Der Player spielt A, Zwischenframe, B nacheinander. Matrizen, die B nicht
    # selbst neu laedt, muessen fuer B so dastehen wie nach A. Darum stellt ein
    # Block am Ende des Zwischenframes den XF-Zustand nach A wieder her -- vor
    # der abschliessenden EFB-Kopie, weil Dolphins FifoPlaybackAnalyzer verlangt,
    # dass ein Frame mit ihr endet (ASSERT part_start == fifoData.size()).
    decoder = fifo.Decoder(dff)
    for frame in dff.frames[:b]:
        decoder.run(frame, fifo.FrameSummary())
    after_a = decoder.snapshot()
    after_a_projection = tuple(decoder.xfr[0x20:0x27])
    decoder.run(middle, fifo.FrameSummary())
    after_middle = decoder.snapshot()
    restore = {address: x for address, x, y in zip(addresses, unpack(after_a), unpack(after_middle))
               if x != y}
    tail = loads_for(restore)
    if tuple(decoder.xfr[0x20:0x27]) != after_a_projection:
        tail += xf_load(fifo.XF_PROJECTION, list(after_a_projection))
    if tail:
        at = decoder.last_efb_copy if decoder.last_efb_copy is not None else len(middle.data)
        middle.data = middle.data[:at] + tail + middle.data[at:]
        middle.updates = [fifo.MemoryUpdate(u.fifo_position + (len(tail) if u.fifo_position > at else 0),
                                            u.address, u.kind, u.data) for u in middle.updates]
    report.bytes_restored = len(tail)
    report.words_restored = len(restore)

    frames = list(dff.frames)
    frames.insert(b, middle)          # zwischen a und b; bei a + 1 == b direkt dazwischen
    for k, frame in enumerate(frames):
        frame.index = k
    report.middle_index = b
    result = fifo.Dff(dff.path, dff.version, dff.game_id, dff.bp_mem, dff.cp_mem, dff.xf_mem,
                      dff.xf_regs, frames, dff.min_loader, dff.flags, dff.tex_mem,
                      dff.mem1_size, dff.mem2_size)
    return result, report


def _count_loads(piece: bytes) -> int:
    count, pos = 0, 0
    while pos < len(piece):
        n = ((struct.unpack_from(">I", piece, pos + 1)[0] >> 16) & 0xF) + 1
        pos += 5 + 4 * n
        count += 1
    return count


def verify(original: fifo.Dff, result: fifo.Dff, report: Report) -> dict:
    """Prueft das Zwischenframe mit dem Zerleger: gleiche Zeichenbefehle wie B,
    Matrizen zugeordneter Befehle exakt auf dem Zwischenwert zwischen A und B
    (beide aus der Originalaufzeichnung), und B beginnt im Ergebnis mit
    demselben XF-Zustand wie im Original."""
    a, b, m, t = report.frames[0], report.frames[1], report.middle_index, report.t
    source = fifo.summarize(original, snapshots=True)
    summaries = fifo.summarize(result, snapshots=True)
    draws_a, draws_b = source[a].draws, source[b].draws
    draws_m = summaries[m].draws
    b_state_same = all(x.xf_snapshot == y.xf_snapshot and x.projection == y.projection
                       for x, y in zip(draws_b, summaries[b + 1].draws))
    pairs_mb = match(draws_m, draws_b)
    b_to_a = {j: i for i, j in match(draws_a, draws_b)}
    unpack = struct.Struct(f"<{fifo.SNAPSHOT_WORDS}I").unpack
    exact = off = 0
    for mi, j in pairs_mb:
        i = b_to_a.get(j)
        if i is None or draws_b[j].depth:
            continue
        wa, wm, wb = (unpack(draws_a[i].xf_snapshot), unpack(draws_m[mi].xf_snapshot),
                      unpack(draws_b[j].xf_snapshot))
        for x, y, z in zip(wa, wm, wb):
            if x != z:
                if y == lerp_words(x, z, t):
                    exact += 1
                else:
                    off += 1
    return {"middle_frame": m, "draws_middle": len(draws_m), "draws_b": len(draws_b),
            "matched_middle_to_b": len(pairs_mb),
            "signatures_identical": ([fifo_sig(d) for d in draws_m]
                                     == [fifo_sig(d) for d in draws_b]),
            "stopped_early": summaries[m].stopped_early,
            "unknown_opcodes": summaries[m].unknown_opcodes,
            "decoded_bytes": summaries[m].bytes_decoded, "stream_bytes": len(result.frames[m].data),
            "words_at_midpoint": exact, "words_off_midpoint": off,
            "b_state_as_in_original": b_state_same}


def fifo_sig(draw: fifo.Draw) -> tuple:
    from spike import signature
    return signature(draw)
