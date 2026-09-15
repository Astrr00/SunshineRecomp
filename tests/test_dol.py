"""Tests fuer das gemeinsame DOL-Modul (lesen, Speicherkarte, aendern).

Alle DOLs hier sind synthetisch. Ein echtes Hauptprogramm ist damit
ausdruecklich nicht getestet; es wird auch keines benoetigt.
"""

from __future__ import annotations

import struct
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools" / "common"))

import dol as dolfile  # noqa: E402

TEXT_ADDRESS = 0x80003100
DATA_ADDRESS = 0x80400000
BLR = 0x4E800020
STWU = 0x9421FFF0
MFLR = 0x7C0802A6
NOP = 0x60000000
BSS_ADDRESS = 0x80500000
BSS_SIZE = 0x1000


def build_dol(text_words: list[int] | None = None, entry: int = TEXT_ADDRESS,
              data_words: int = 4, text_slots: int = 1,
              bss_address: int = BSS_ADDRESS, bss_size: int = BSS_SIZE) -> bytes:
    """Baut ein minimales, formal gueltiges DOL."""
    words = text_words if text_words is not None else [MFLR, BLR, STWU, BLR]
    text = b"".join(struct.pack(">I", word) for word in words)
    data = b"\0" * (data_words * 4)

    header = bytearray(dolfile.DOL_HEADER_SIZE)
    offset = dolfile.DOL_HEADER_SIZE
    per_slot = len(text) // text_slots
    for slot in range(text_slots):
        start = slot * per_slot
        size = per_slot if slot < text_slots - 1 else len(text) - start
        struct.pack_into(">I", header, dolfile.OFF_SECTION_OFFSETS + slot * 4,
                         offset + start)
        struct.pack_into(">I", header, dolfile.OFF_SECTION_ADDRESSES + slot * 4,
                         TEXT_ADDRESS + start)
        struct.pack_into(">I", header, dolfile.OFF_SECTION_SIZES + slot * 4, size)

    data_slot = dolfile.TEXT_SECTIONS
    struct.pack_into(">I", header, dolfile.OFF_SECTION_OFFSETS + data_slot * 4,
                     offset + len(text))
    struct.pack_into(">I", header, dolfile.OFF_SECTION_ADDRESSES + data_slot * 4,
                     DATA_ADDRESS)
    struct.pack_into(">I", header, dolfile.OFF_SECTION_SIZES + data_slot * 4,
                     len(data))

    struct.pack_into(">I", header, dolfile.OFF_ENTRY, entry)
    struct.pack_into(">I", header, dolfile.OFF_BSS_ADDRESS, bss_address)
    struct.pack_into(">I", header, dolfile.OFF_BSS_SIZE, bss_size)
    return bytes(header) + text + data


def write_dol(directory: str, **kwargs) -> Path:
    path = Path(directory) / "main.dol"
    path.write_bytes(build_dol(**kwargs))
    return path


class ReadTests(unittest.TestCase):
    def test_reads_sections_and_entry(self):
        with TemporaryDirectory() as tmp:
            binary = dolfile.read(write_dol(tmp))
        self.assertEqual(binary.entry, TEXT_ADDRESS)
        self.assertEqual(len(binary.text_sections), 1)
        self.assertEqual(len(binary.sections), 2)

    def test_classifies_addresses_by_section(self):
        with TemporaryDirectory() as tmp:
            binary = dolfile.read(write_dol(tmp))
        self.assertTrue(binary.section_of(TEXT_ADDRESS).executable)
        self.assertFalse(binary.section_of(DATA_ADDRESS).executable)
        self.assertIsNone(binary.section_of(BSS_ADDRESS))

    def test_reads_words_big_endian_and_stops_at_the_edge(self):
        with TemporaryDirectory() as tmp:
            binary = dolfile.read(write_dol(tmp, text_words=[MFLR, BLR]))
        self.assertEqual(binary.word_at(TEXT_ADDRESS), MFLR)
        self.assertEqual(binary.word_at(TEXT_ADDRESS + 4), BLR)
        self.assertIsNone(binary.word_at(TEXT_ADDRESS + 8))

    def test_rejects_a_file_that_is_too_small(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "short.dol"
            path.write_bytes(b"\0" * 16)
            with self.assertRaises(dolfile.DolError) as caught:
                dolfile.read(path)
        self.assertIn("zu klein", str(caught.exception))

    def test_rejects_a_section_outside_the_file(self):
        with TemporaryDirectory() as tmp:
            raw = bytearray(build_dol())
            struct.pack_into(">I", raw, dolfile.OFF_SECTION_SIZES, 0x1000000)
            path = Path(tmp) / "broken.dol"
            path.write_bytes(bytes(raw))
            with self.assertRaises(dolfile.DolError) as caught:
                dolfile.read(path)
        self.assertIn("beschaedigt", str(caught.exception))

    def test_rejects_a_dol_without_executable_section(self):
        with TemporaryDirectory() as tmp:
            raw = bytearray(build_dol())
            struct.pack_into(">I", raw, dolfile.OFF_SECTION_SIZES, 0)
            path = Path(tmp) / "nocode.dol"
            path.write_bytes(bytes(raw))
            with self.assertRaises(dolfile.DolError):
                dolfile.read(path)

    def test_counts_free_text_slots(self):
        with TemporaryDirectory() as tmp:
            one = dolfile.read(write_dol(tmp, text_slots=1))
        self.assertEqual(len(dolfile.free_text_slots(one)),
                         dolfile.TEXT_SECTIONS - 1)
        with TemporaryDirectory() as tmp:
            two = dolfile.read(write_dol(tmp, text_slots=2))
        self.assertEqual(len(dolfile.free_text_slots(two)),
                         dolfile.TEXT_SECTIONS - 2)


class MemoryMapTests(unittest.TestCase):
    def test_includes_bss_and_sorts_by_address(self):
        with TemporaryDirectory() as tmp:
            binary = dolfile.read(write_dol(tmp))
        regions = dolfile.memory_map(binary)
        self.assertEqual([region.label for region in regions],
                         ["text0", "data7", "bss"])
        self.assertEqual(regions, sorted(regions, key=lambda r: r.start))

    def test_omits_bss_when_it_is_empty(self):
        with TemporaryDirectory() as tmp:
            binary = dolfile.read(write_dol(tmp, bss_size=0))
        self.assertNotIn("bss", [r.label for r in dolfile.memory_map(binary)])

    def test_finds_the_gaps_between_regions(self):
        with TemporaryDirectory() as tmp:
            binary = dolfile.read(write_dol(tmp))
        holes = dolfile.gaps(binary)
        self.assertTrue(holes)
        self.assertTrue(all(hole.start < hole.end for hole in holes))
        for hole in holes:
            for region in dolfile.memory_map(binary):
                self.assertFalse(hole.start < region.end and region.start < hole.end)


    def test_a_region_inside_another_is_no_gap(self):
        # Wie bei Sunshine: BSS spannt ueber eine dazwischenliegende
        # Datensektion. Ohne Verschmelzen entstuende hier eine Schein-Luecke,
        # und ein Codebereich landete mitten in BSS.
        with TemporaryDirectory() as tmp:
            binary = dolfile.read(write_dol(
                tmp, bss_address=DATA_ADDRESS - 0x1000,
                bss_size=0x2000))
        for hole in dolfile.gaps(binary):
            for region in dolfile.memory_map(binary):
                self.assertFalse(hole.start < region.end and region.start < hole.end,
                                 f"Luecke {hole} liegt in {region}")


class BranchTests(unittest.TestCase):
    def test_encodes_forward_and_backward(self):
        self.assertEqual(dolfile.branch(0x80000000, 0x80000100), 0x48000100)
        self.assertEqual(dolfile.branch(0x80000100, 0x80000000), 0x4BFFFF00)

    def test_encodes_a_link_branch(self):
        self.assertEqual(dolfile.branch(0x80000000, 0x80000100, link=True),
                         0x48000101)

    def test_zero_distance_is_a_branch_to_itself(self):
        self.assertEqual(dolfile.branch(0x80000000, 0x80000000), 0x48000000)

    def test_rejects_an_unaligned_target(self):
        with self.assertRaises(dolfile.DolError):
            dolfile.branch(0x80000000, 0x80000002)

    def test_rejects_a_distance_beyond_reach(self):
        with self.assertRaises(dolfile.DolError) as caught:
            dolfile.branch(0x80000000, 0x84000000)
        self.assertIn("32 MiB", str(caught.exception))

    def test_accepts_the_edge_of_the_range(self):
        self.assertIsInstance(dolfile.branch(0x82000000, 0x80000000), int)


class BuilderTests(unittest.TestCase):
    def _builder(self, tmp: str, **kwargs) -> dolfile.DolBuilder:
        return dolfile.DolBuilder(dolfile.read(write_dol(tmp, **kwargs)))

    def test_writes_a_word_into_text_and_data(self):
        with TemporaryDirectory() as tmp:
            builder = self._builder(tmp)
            self.assertTrue(builder.write_word(TEXT_ADDRESS, 0x12345678).executable)
            self.assertFalse(builder.write_word(DATA_ADDRESS, 0xCAFEBABE).executable)
            self.assertEqual(builder.read_word(TEXT_ADDRESS), 0x12345678)
            self.assertEqual(builder.read_word(DATA_ADDRESS), 0xCAFEBABE)

    def test_refuses_to_write_into_bss(self):
        with TemporaryDirectory() as tmp:
            builder = self._builder(tmp)
            with self.assertRaises(dolfile.DolError) as caught:
                builder.write_word(BSS_ADDRESS, 1)
        self.assertIn("BSS", str(caught.exception))
        self.assertIn("Laufzeit", str(caught.exception))

    def test_refuses_an_unaligned_write(self):
        with TemporaryDirectory() as tmp:
            builder = self._builder(tmp)
            with self.assertRaises(dolfile.DolError):
                builder.write_word(TEXT_ADDRESS + 1, 0)

    def test_refuses_a_write_past_the_section_end(self):
        with TemporaryDirectory() as tmp:
            builder = self._builder(tmp, text_words=[MFLR, BLR])
            with self.assertRaises(dolfile.DolError):
                builder.write_word(TEXT_ADDRESS + 8, 0)

    def test_appends_a_text_section_that_reads_back(self):
        with TemporaryDirectory() as tmp:
            builder = self._builder(tmp)
            address = 0x80600000
            section = builder.append_text_section(address, [MFLR, BLR])
            self.assertTrue(section.executable)
            path = Path(tmp) / "out.dol"
            path.write_bytes(builder.to_bytes())
            again = dolfile.read(path)
        self.assertEqual(again.word_at(address), MFLR)
        self.assertEqual(again.word_at(address + 4), BLR)
        self.assertTrue(again.section_of(address).executable)

    def test_refuses_a_section_that_overlaps_bss(self):
        with TemporaryDirectory() as tmp:
            builder = self._builder(tmp)
            with self.assertRaises(dolfile.DolError) as caught:
                builder.append_text_section(BSS_ADDRESS, [MFLR])
        self.assertIn("bss", str(caught.exception))

    def test_refuses_an_unaligned_section_address(self):
        with TemporaryDirectory() as tmp:
            builder = self._builder(tmp)
            with self.assertRaises(dolfile.DolError):
                builder.append_text_section(0x80600004, [MFLR])

    def test_refuses_when_every_text_slot_is_taken(self):
        with TemporaryDirectory() as tmp:
            builder = self._builder(tmp, text_words=[NOP] * dolfile.TEXT_SECTIONS,
                                    text_slots=dolfile.TEXT_SECTIONS)
            with self.assertRaises(dolfile.DolError) as caught:
                builder.append_text_section(0x80600000, [MFLR])
        self.assertIn("belegt", str(caught.exception))

    def test_leaves_the_source_untouched(self):
        with TemporaryDirectory() as tmp:
            binary = dolfile.read(write_dol(tmp))
            before = binary.data
            builder = dolfile.DolBuilder(binary)
            builder.write_word(TEXT_ADDRESS, 0xDEADBEEF)
            self.assertEqual(binary.data, before)
            self.assertNotEqual(builder.to_bytes(), before)


class MeasurementTests(unittest.TestCase):
    def test_recognises_prologue_and_terminator(self):
        with TemporaryDirectory() as tmp:
            binary = dolfile.read(write_dol(tmp, text_words=[MFLR, BLR, STWU, BLR]))
        result = dolfile.measure(binary, [TEXT_ADDRESS, TEXT_ADDRESS + 8])
        self.assertEqual(result.sampled, 2)
        self.assertEqual(result.prologue, 2)
        self.assertEqual(result.preceded_by_terminator, 1)

    def test_ignores_addresses_outside_text(self):
        with TemporaryDirectory() as tmp:
            binary = dolfile.read(write_dol(tmp))
        self.assertEqual(dolfile.measure(binary, [DATA_ADDRESS, BSS_ADDRESS]).sampled, 0)

    def test_nop_counts_as_terminator(self):
        with TemporaryDirectory() as tmp:
            binary = dolfile.read(write_dol(tmp, text_words=[NOP, MFLR]))
        result = dolfile.measure(binary, [TEXT_ADDRESS + 4])
        self.assertEqual(result.preceded_by_terminator, 1)
        self.assertEqual(result.prologue, 1)

    def test_control_sample_is_aligned_inside_text_and_repeatable(self):
        with TemporaryDirectory() as tmp:
            binary = dolfile.read(write_dol(tmp))
        sample = dolfile.control_sample(binary, 50)
        self.assertEqual(len(sample), 50)
        self.assertTrue(all(address % 4 == 0 for address in sample))
        self.assertTrue(all(binary.section_of(a).executable for a in sample))
        self.assertEqual(sample, dolfile.control_sample(binary, 50))


if __name__ == "__main__":
    unittest.main()
