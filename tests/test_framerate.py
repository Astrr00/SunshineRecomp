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
    struct.pack_into("<IIIQIQIQIQIQIIQIII8s", out, 0, fifo.FILE_ID, 6, 1,
                     bp_off, 1024, cp_off, 1024, xf_off, 16384, xfr_off, 352,
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
                  + xf_load(fifo.XF_PROJECTION, [1, 2, 3, 4, 5, 6])
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
