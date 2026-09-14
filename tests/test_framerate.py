"""Tests fuer den DFF-Zerleger und die Zuordnung (synthetische Aufzeichnung)."""

from __future__ import annotations

import struct
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

_TOOLS = Path(__file__).resolve().parent.parent / "tools"
sys.path.insert(0, str(_TOOLS / "framerate"))

import fifo  # noqa: E402
from spike import analyze, match  # noqa: E402


def cp_reg(reg: int, value: int) -> bytes:
    return bytes([0x08, reg]) + struct.pack(">I", value)


def xf_load(address: int, words: list[int]) -> bytes:
    return bytes([0x10]) + struct.pack(">I", ((len(words) - 1) << 16) | address) + \
        b"".join(struct.pack(">I", w) for w in words)


def bp_reg(reg: int, value: int) -> bytes:
    return bytes([0x61]) + struct.pack(">I", (reg << 24) | (value & 0xFFFFFF))


def primitive(opcode: int, count: int, vertex_size: int) -> bytes:
    return bytes([opcode]) + struct.pack(">H", count) + bytes(count * vertex_size)


def indx_a(index: int, count: int, address: int) -> bytes:
    return bytes([0x20]) + struct.pack(">I", (index << 16) | ((count - 1) << 12) | address)


def build_dff(frames: list[bytes], updates: list[list[tuple[int, int, int, bytes]]],
              cp: dict[int, int]) -> bytes:
    """Baut eine DFF v6 mit Anfangszustand und beliebig vielen Frames."""
    out = bytearray(128)
    cp_mem = [0] * 256
    for reg, value in cp.items():
        cp_mem[reg] = value
    bp_off = len(out); out += struct.pack("<256I", *([0] * 256))
    cp_off = len(out); out += struct.pack("<256I", *cp_mem)
    xf_off = len(out); out += struct.pack("<4096I", *([0] * 4096))
    xfr_off = len(out); out += struct.pack("<88I", *([0] * 88))
    tex_off = len(out)
    frame_infos = []
    for data, ups in zip(frames, updates):
        data_off = len(out); out += data
        up_entries = []
        for pos, address, kind, payload in ups:
            d_off = len(out); out += payload
            up_entries.append(struct.pack("<IIQIB3x", pos, address, d_off, len(payload), kind))
        up_off = len(out); out += b"".join(up_entries)
        frame_infos.append(struct.pack("<QIIIQI32x", data_off, len(data), 0, len(data),
                                       up_off, len(ups)))
    list_off = len(out); out += b"".join(frame_infos)
    # Groessen wie FifoDataFile::Save: Anzahl u32 (256, 256, 4096, 88), Texturspeicher in Bytes
    struct.pack_into("<IIIQIQIQIQIQIIQIII8s", out, 0, fifo.FILE_ID, 6, 1,
                     bp_off, 256, cp_off, 256, xf_off, 4096, xfr_off, 88,
                     list_off, len(frames), 0, tex_off, 0, 0x1800000, 0, b"GMSE01\0\0")
    return bytes(out)


# VCD: Position direkt (Bits 9-10 = 1), VAT 0: XYZ (1) und Float (4): 12 Bytes je Vertex.
CP_STATE = {fifo.CP_VCD_LO: 1 << 9, fifo.CP_VAT_A: (1 << 0) | (4 << 1)}


class DecodeTests(unittest.TestCase):
    def _read(self, frames, updates=None, cp=CP_STATE):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.dff"
            path.write_bytes(build_dff(frames, updates or [[] for _ in frames], cp))
            return fifo.read(path)

    def test_reads_header_and_frames(self):
        dff = self._read([b"\x00" * 4, b"\x00" * 8])
        self.assertEqual(dff.version, 6)
        self.assertEqual((len(dff.bp_mem), len(dff.cp_mem), len(dff.xf_mem), len(dff.xf_regs)),
                         (256, 256, 4096, 88))
        self.assertEqual(dff.game_id, "GMSE01")
        self.assertEqual([len(f.data) for f in dff.frames], [4, 8])

    def test_rejects_a_foreign_file(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.dff"
            path.write_bytes(b"\0" * 200)
            with self.assertRaises(fifo.FifoError):
                fifo.read(path)

    def test_vertex_size_follows_vcd_and_vat(self):
        dff = self._read([primitive(0x90, 3, 12)])  # Dreiecke, VAT 0
        s = fifo.summarize(dff)[0]
        self.assertEqual(len(s.draws), 1)
        self.assertEqual(s.draws[0].vertex_size, 12)
        self.assertEqual(s.draws[0].vertices, 3)
        self.assertEqual(s.draws[0].pos_kind, 1)
        self.assertFalse(s.stopped_early)

    def test_vertex_size_with_matrix_index_and_index16_texcoord(self):
        # PosMatIdx (Bit 0) + Position Index16 (3) + Tex0 Index8 in VCD_HI
        cp = {fifo.CP_VCD_LO: 1 | (3 << 9), fifo.CP_VCD_HI: 2, fifo.CP_VAT_A: 4 << 1}
        dff = self._read([primitive(0x80, 2, 1 + 2 + 1)], cp=cp)
        d = fifo.summarize(dff)[0].draws[0]
        self.assertEqual(d.vertex_size, 4)
        self.assertTrue(d.per_vertex_matrix)
        self.assertEqual(d.pos_kind, 3)

    def test_counts_loads_and_tracks_xf_matrix(self):
        words = [struct.unpack("<I", struct.pack("<f", float(i)))[0] for i in range(12)]
        stream = (cp_reg(fifo.CP_MATINDEX_A, 3) + xf_load(3 * 4, words)
                  + xf_load(fifo.XF_PROJECTION, [1, 2, 3, 4, 5, 6, 1])
                  + bp_reg(0x94, 0x1234) + primitive(0x90, 1, 12))
        s = fifo.summarize(self._read([stream]))[0]
        self.assertEqual((s.cp_loads, s.xf_matrix_loads, s.projection_loads, s.bp_loads),
                         (1, 1, 1, 1))
        d = s.draws[0]
        self.assertEqual(d.matrix_index, 3)
        self.assertEqual(d.matrix, tuple(float(i) for i in range(12)))
        self.assertEqual(d.projection[:6], (1, 2, 3, 4, 5, 6))
        self.assertEqual(d.texture_key[0], 0x1234)

    def test_resolves_indexed_matrix_from_memory_updates(self):
        base, stride = 0x00100000, 48
        payload = b"".join(struct.pack(">f", float(i)) for i in range(24))
        cp = dict(CP_STATE)
        cp[fifo.CP_ARRAY_BASE + 12] = base
        cp[fifo.CP_ARRAY_STRIDE + 12] = stride
        stream = indx_a(1, 12, 0) + primitive(0x90, 1, 12)   # zweiter Eintrag -> Matrix 0
        dff = self._read([stream], [[(0, base, 2, payload)]], cp=cp)
        s = fifo.summarize(dff)[0]
        self.assertEqual(s.xf_indexed_loads, 1)
        self.assertEqual(s.xf_indexed_unresolved, 0)
        self.assertEqual(s.draws[0].matrix, tuple(float(i) for i in range(12, 24)))

    def test_reports_an_unresolved_indexed_load(self):
        dff = self._read([indx_a(0, 12, 0)])
        self.assertEqual(fifo.summarize(dff)[0].xf_indexed_unresolved, 1)

    def test_stops_on_unknown_opcode(self):
        s = fifo.summarize(self._read([bytes([0x77])]))[0]
        self.assertTrue(s.stopped_early)
        self.assertEqual(s.unknown_opcodes, 1)

    def test_state_carries_over_between_frames(self):
        first = cp_reg(fifo.CP_MATINDEX_A, 5)
        second = primitive(0x90, 1, 12)
        summaries = fifo.summarize(self._read([first, second]))
        self.assertEqual(summaries[1].draws[0].matrix_index, 5)


class MatchTests(unittest.TestCase):
    def _draw(self, primitive_=2, vertices=3, texture=0):
        return fifo.Draw(0, primitive_, 0, vertices, 12, 1, False, 0, (0.0,) * 12, 0,
                         (0,) * 6, (texture,) + (0,) * 15)

    def test_matches_identical_sequences_completely(self):
        a = [self._draw(vertices=v) for v in (3, 4, 5)]
        self.assertEqual(match(a, list(a)), [(0, 0), (1, 1), (2, 2)])

    def test_tolerates_an_insertion(self):
        a = [self._draw(vertices=3), self._draw(vertices=5)]
        b = [self._draw(vertices=3), self._draw(vertices=4), self._draw(vertices=5)]
        self.assertEqual(match(a, b), [(0, 0), (1, 2)])

    def test_does_not_match_different_textures(self):
        self.assertEqual(match([self._draw(texture=1)], [self._draw(texture=2)]), [])

    def test_analyze_reports_matrix_changes(self):
        words_a = [struct.unpack("<I", struct.pack("<f", 1.0))[0]] * 12
        words_b = [struct.unpack("<I", struct.pack("<f", 2.0))[0]] * 12
        f1 = xf_load(0, words_a) + primitive(0x90, 1, 12)
        f2 = xf_load(0, words_b) + primitive(0x90, 1, 12)
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.dff"
            path.write_bytes(build_dff([f1, f2], [[], []], CP_STATE))
            report = analyze(fifo.read(path))
        pair = report["pairs"][0]
        self.assertEqual(pair["matched"], 1)
        self.assertEqual(pair["matched_matrix_changed"], 1)


if __name__ == "__main__":
    unittest.main()


# ---------------------------------------------------------------------------
# Zurueckschreiben, Zwischenbild, Bilder
# ---------------------------------------------------------------------------

import zlib  # noqa: E402

import images  # noqa: E402
import interpolate  # noqa: E402


def f32(value: float) -> int:
    return struct.unpack("<I", struct.pack("<f", value))[0]


class WriteTests(unittest.TestCase):
    def test_round_trip_keeps_header_frames_and_updates(self):
        frames = [primitive(0x90, 1, 12), xf_load(0, [1, 2]) + primitive(0x90, 2, 12)]
        updates = [[(0, 0x80100000, 2, b"\x01\x02\x03\x04")], []]
        with TemporaryDirectory() as tmp:
            src = Path(tmp) / "a.dff"
            src.write_bytes(build_dff(frames, updates, CP_STATE))
            dff = fifo.read(src)
            dff.tex_mem = bytes(range(16))
            dst = Path(tmp) / "b.dff"
            fifo.write(dff, dst)
            back = fifo.read(dst)
        self.assertEqual([f.data for f in back.frames], frames)
        self.assertEqual(back.cp_mem, dff.cp_mem)
        self.assertEqual(back.tex_mem, bytes(range(16)))
        self.assertEqual(back.game_id, "GMSE01")
        self.assertEqual(back.mem1_size, 0x1800000)
        u = back.frames[0].updates[0]
        self.assertEqual((u.fifo_position, u.address, u.kind, u.data), (0, 0x80100000, 2, b"\x01\x02\x03\x04"))


class InterpolateTests(unittest.TestCase):
    def _scene(self, tmp, a_words, b_words, extra_b=b""):
        # Frame 0: Anfang; Frame 1 (A) und 2 (B) laden Matrix 0 und zeichnen.
        base = cp_reg(fifo.CP_MATINDEX_A, 0)
        frames = [base + primitive(0x90, 1, 12),
                  xf_load(0, a_words) + primitive(0x90, 1, 12),
                  xf_load(0, b_words) + extra_b + primitive(0x90, 1, 12)]
        path = Path(tmp) / "s.dff"
        path.write_bytes(build_dff(frames, [[] for _ in frames], CP_STATE))
        return fifo.read(path)

    def test_middle_frame_holds_the_midpoint(self):
        with TemporaryDirectory() as tmp:
            dff = self._scene(tmp, [f32(0.0), f32(10.0)], [f32(4.0), f32(10.0)])
            result, report = interpolate.synthesize(dff, 1, 2, 0.5)
            out = Path(tmp) / "m.dff"
            fifo.write(result, out)
            back = fifo.read(out)
            check = interpolate.verify(dff, back, report)
        self.assertEqual(len(back.frames), 4)
        self.assertEqual(report.middle_index, 2)
        self.assertEqual(report.matched, 1)
        self.assertEqual(report.words_interpolated, 1)      # nur das erste Wort aendert sich
        self.assertEqual(report.xf_loads_inserted, 1)
        draws = fifo.summarize(back)[2].draws
        self.assertEqual(draws[0].matrix[0], 2.0)
        self.assertEqual(draws[0].matrix[1], 10.0)
        self.assertTrue(check["signatures_identical"])
        self.assertEqual(check["words_off_midpoint"], 0)
        self.assertEqual(check["words_at_midpoint"], 1)
        self.assertTrue(check["b_state_as_in_original"])

    def test_restores_state_after_a_for_frame_b(self):
        # B laedt Matrix 0 nicht neu (kein XF-Ladebefehl), nutzt also den Zustand nach A.
        with TemporaryDirectory() as tmp:
            base = cp_reg(fifo.CP_MATINDEX_A, 0)
            frames = [base + primitive(0x90, 1, 12),
                      xf_load(0, [f32(0.0)]) + primitive(0x90, 1, 12) + xf_load(4, [f32(8.0)]),
                      primitive(0x90, 1, 12)]
            path = Path(tmp) / "s.dff"
            path.write_bytes(build_dff(frames, [[] for _ in frames], CP_STATE))
            dff = fifo.read(path)
            result, report = interpolate.synthesize(dff, 1, 2, 0.5)
            check = interpolate.verify(dff, result, report)
        # Beim Zeichnen in A stand Wort 4 noch auf 0, in B auf 8.0 (nach A geladen):
        # das Zwischenframe zeichnet mit 4.0 und stellt danach 8.0 fuer B wieder her.
        self.assertEqual(report.words_interpolated, 1)
        self.assertEqual(report.words_restored, 1)
        self.assertTrue(check["b_state_as_in_original"])
        self.assertEqual(fifo.summarize(result)[2].draws[0].matrix[4], 4.0)
        self.assertEqual(fifo.summarize(result)[3].draws[0].matrix[4], 8.0)

    def test_memory_updates_shift_with_insertions(self):
        with TemporaryDirectory() as tmp:
            base = cp_reg(fifo.CP_MATINDEX_A, 0)
            frames = [base + primitive(0x90, 1, 12),
                      xf_load(0, [f32(0.0)]) + primitive(0x90, 1, 12),
                      xf_load(0, [f32(2.0)]) + primitive(0x90, 1, 12) + primitive(0x90, 1, 12)]
            # Aktualisierung vor dem zweiten Zeichenbefehl von B (Position 9 + 15 = 24)
            updates = [[], [], [(24, 0x80200000, 4, b"\0" * 8)]]
            path = Path(tmp) / "s.dff"
            path.write_bytes(build_dff(frames, updates, CP_STATE))
            dff = fifo.read(path)
            result, report = interpolate.synthesize(dff, 1, 2, 0.5)
        middle = result.frames[2]
        self.assertEqual(report.updates_shifted, 1)
        self.assertEqual(middle.updates[0].fifo_position, 24 + 9)   # ein XF-Ladebefehl mit 1 Wort
        self.assertEqual(len(middle.data), len(frames[2]) + 9 + report.bytes_restored)

    def test_rejects_bad_frame_order_and_t(self):
        with TemporaryDirectory() as tmp:
            dff = self._scene(tmp, [f32(0.0)], [f32(1.0)])
            with self.assertRaises(interpolate.InterpolationError):
                interpolate.synthesize(dff, 2, 1)
            with self.assertRaises(interpolate.InterpolationError):
                interpolate.synthesize(dff, 1, 2, 1.0)

    def test_loads_are_grouped_in_runs_of_at_most_16(self):
        changes = {i: i for i in range(20)} | {40: 1}
        piece = interpolate.loads_for(changes)
        self.assertEqual(interpolate._count_loads(piece), 3)
        self.assertEqual(len(piece), 3 * 5 + 21 * 4)

    def test_lerp_keeps_equal_words_exact(self):
        self.assertEqual(interpolate.lerp_words(f32(1.5), f32(1.5), 0.5), f32(1.5))
        self.assertEqual(interpolate.lerp_words(f32(1.0), f32(3.0), 0.25), f32(1.5))


def encode_png(width, height, rows, filters, color=2):
    """Schreibt ein PNG mit vorgegebenen Filtertypen je Zeile (Testhilfe)."""
    bpp = 3 if color == 2 else 4
    stride = width * bpp
    raw = bytearray()
    previous = bytes(stride)
    for line, f in zip(rows, filters):
        out = bytearray(stride)
        for x in range(stride):
            a = line[x - bpp] if x >= bpp else 0
            b = previous[x]
            c = previous[x - bpp] if x >= bpp else 0
            if f == 0:
                pred = 0
            elif f == 1:
                pred = a
            elif f == 2:
                pred = b
            elif f == 3:
                pred = (a + b) >> 1
            else:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pred = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
            out[x] = (line[x] - pred) & 0xFF
        raw += bytes([f]) + out
        previous = line

    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + \
            struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, color, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(raw))) + chunk(b"IEND", b""))


class ImageTests(unittest.TestCase):
    ROWS = [bytes([10, 20, 30, 40, 50, 60, 70, 80, 90]),
            bytes([15, 25, 35, 45, 55, 65, 75, 85, 95]),
            bytes([200, 0, 100, 3, 250, 7, 9, 11, 13]),
            bytes([1, 2, 3, 4, 5, 6, 7, 8, 9]),
            bytes([255, 254, 253, 0, 1, 2, 128, 127, 126])]

    def test_reads_all_five_filters(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "f.png"
            path.write_bytes(encode_png(3, 5, self.ROWS, [0, 1, 2, 3, 4]))
            img = images.read_png(path)
        self.assertEqual((img.width, img.height, img.channels), (3, 5, 3))
        self.assertEqual(img.pixels, b"".join(self.ROWS))

    def test_rgba_is_reduced_to_rgb(self):
        rows = [bytes([1, 2, 3, 255, 4, 5, 6, 0])]
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "f.png"
            path.write_bytes(encode_png(2, 1, rows, [4], color=6))
            img = images.read_png(path)
        self.assertEqual(img.rgb(), bytes([1, 2, 3, 4, 5, 6]))

    def test_difference_and_round_trip(self):
        a = images.Image(2, 1, 3, bytes([0, 0, 0, 100, 100, 100]))
        b = images.Image(2, 1, 3, bytes([0, 0, 0, 110, 90, 100]))
        d = images.difference(a, b)
        self.assertAlmostEqual(d.mean_abs, 20 / 6)
        self.assertEqual((d.max_abs, d.pixels_changed, d.pixels), (10, 1, 2))
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "w.png"
            images.write_png(path, b)
            self.assertEqual(images.read_png(path).pixels, b.pixels)
        with self.assertRaises(images.ImageError):
            images.difference(a, images.Image(1, 1, 3, bytes(3)))


class BetweennessTests(unittest.TestCase):
    def test_counts_in_range_out_of_range_and_mid_only(self):
        a = images.Image(4, 1, 3, bytes([0, 0, 0,  100, 100, 100,  50, 50, 50,  10, 10, 10]))
        b = images.Image(4, 1, 3, bytes([0, 0, 0,  200, 200, 200,  50, 50, 50,  90, 90, 90]))
        m = images.Image(4, 1, 3, bytes([0, 0, 0,  150, 150, 150,  90, 50, 50,  250, 90, 90]))
        bt = images.betweenness(a, m, b)
        # Pixel 1: zwischen; Pixel 3: ausserhalb (250 > 90 + Toleranz); Pixel 2: nur im Zwischenbild
        self.assertEqual((bt.ab_changed, bt.in_range, bt.out_of_range, bt.mid_only, bt.pixels),
                         (2, 1, 1, 1, 4))
        self.assertEqual(bt.as_dict()["in_range_share"], 0.5)


class MotionTests(unittest.TestCase):
    def _draw(self, matrix, per_vertex=False):
        return fifo.Draw(0, 2, 0, 3, 12, 1, per_vertex, 0, tuple(matrix), 0, (0,) * 7, ())

    def test_translation_and_rotation_parts(self):
        identity = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0]
        moved = [1, 0, 0, 3, 0, 1, 0, 4, 0, 0, 1, 0]      # Verschiebung (3, 4, 0)
        from spike import motion
        self.assertEqual(motion(self._draw(identity), self._draw(moved)), (5.0, 0.0))
        self.assertIsNone(motion(self._draw(identity), self._draw(moved, per_vertex=True)))

    def test_cut_verdict_thresholds(self):
        from spike import cut_verdict
        self.assertFalse(cut_verdict({"matched_share_of_current": 0.99, "motion_translation_median": 0.4}))
        self.assertTrue(cut_verdict({"matched_share_of_current": 0.376, "motion_translation_median": 0.4}))
        self.assertTrue(cut_verdict({"matched_share_of_current": 1.0, "motion_translation_median": 1638.0}))
        self.assertFalse(cut_verdict({"matched_share_of_current": None, "motion_translation_median": None}))
