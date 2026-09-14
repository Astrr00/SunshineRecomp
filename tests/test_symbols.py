"""Tests fuer die Symbolliste und die DOL-Pruefung.

Alle Tests laufen ohne Spieldaten. Das DOL fuer die Pruefpfade wird
synthetisch erzeugt; ein echtes Abbild ist damit ausdruecklich nicht getestet.

Die Gegenprobe ``dolrecomp_parse_line`` bildet ``parse_line`` aus DolRecomps
``src/analysis/symbol_map.c`` (Commit 40637c46) nach. Damit wird die erzeugte
Ausgabe nicht gegen eine Annahme geprueft, sondern gegen den Leser, der sie
spaeter tatsaechlich verarbeitet -- einschliesslich der Frage, ob die
Kommentarzeilen folgenlos uebergangen werden.
"""

from __future__ import annotations

import hashlib
import string
import struct
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools" / "symbols"))

import dol as dolfile  # noqa: E402
import symbolmap  # noqa: E402

TEXT_ADDRESS = 0x80003100
DATA_ADDRESS = 0x80400000
BLR = 0x4E800020
STWU = 0x9421FFF0
MFLR = 0x7C0802A6
ORI_NOP = 0x60000000


# --------------------------------------------------------------------------
# Nachbildung des Lesers aus DolRecomp
# --------------------------------------------------------------------------

def _parse_hex(text: str) -> int | None:
    digits = text[2:] if text[:2].lower() == "0x" else text
    if not 1 <= len(digits) <= 8:
        return None
    if any(character not in string.hexdigits for character in digits):
        return None
    return int(digits, 16)


def _valid_name(name: str) -> bool:
    if not name or name[0] in ".*":
        return False
    return name not in ("UNUSED", "...UNUSED...")


def dolrecomp_parse_line(line: str) -> tuple[int, int, str] | None:
    """Liefert (Adresse, Groesse, Name) wie DolRecomps parse_line."""
    tokens = line.split()
    values = [_parse_hex(token) for token in tokens[:5]] + [None] * 5

    if len(tokens) >= 6 and all(v is not None for v in values[:5]):
        # Der C-Code bricht hier ab, statt die kuerzeren Formen zu versuchen.
        if _valid_name(tokens[5]):
            return values[2], values[1], tokens[5]
        return None
    if (len(tokens) >= 5 and all(v is not None for v in values[:4])
            and _valid_name(tokens[4])):
        return values[2], values[1], tokens[4]
    if (len(tokens) >= 3 and all(v is not None for v in values[:2])
            and _valid_name(tokens[2])):
        return values[0], values[1], tokens[2]
    if len(tokens) >= 2 and values[0] is not None and _valid_name(tokens[1]):
        return values[0], 0, tokens[1]
    return None


def dolrecomp_load(text: str) -> list[tuple[int, int, str]]:
    """Wie symbol_map_load: parst zeilenweise und verwirft schiefe Adressen."""
    loaded = []
    for line in text.splitlines():
        parsed = dolrecomp_parse_line(line)
        if parsed is None:
            continue
        if parsed[0] % 4 != 0:
            continue
        loaded.append(parsed)
    return loaded


def build_dol(text_words: list[int] | None = None, entry: int = TEXT_ADDRESS,
              data_words: int = 4, text_slots: int = 1) -> bytes:
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
    struct.pack_into(">I", header, dolfile.OFF_BSS_ADDRESS, 0x80500000)
    struct.pack_into(">I", header, dolfile.OFF_BSS_SIZE, 0x1000)
    return bytes(header) + text + data


class ParseTests(unittest.TestCase):
    def test_reads_name_and_address(self):
        report = symbolmap.parse("memset=0x80003100\n__start=0x8000522C\n")
        self.assertEqual([s.name for s in report.accepted], ["memset", "__start"])
        self.assertEqual(report.accepted[1].address, 0x8000522C)

    def test_counts_blank_lines_without_rejecting_them(self):
        report = symbolmap.parse("memset=0x80003100\n\n\n")
        self.assertEqual(report.blank_lines, 2)
        self.assertEqual(report.skipped_count, 0)

    def test_skips_unaligned_address_like_the_recompiler(self):
        report = symbolmap.parse("memset=0x80003100\ninit=0x8040D4A1\n")
        self.assertEqual(len(report.accepted), 1)
        self.assertIn("Adresse nicht durch 4 teilbar", report.skipped)

    def test_skips_address_outside_mem1(self):
        report = symbolmap.parse("memset=0x80003100\nwgPipe=0xCC008000\n")
        self.assertEqual(len(report.accepted), 1)
        self.assertIn("Adresse ausserhalb MEM1", report.skipped)

    def test_skips_names_the_recompiler_rejects(self):
        report = symbolmap.parse(
            "memset=0x80003100\n.hidden=0x80003200\n*star=0x80003300\n"
            "UNUSED=0x80003400\n")
        self.assertEqual(len(report.accepted), 1)
        self.assertEqual(report.skipped_count, 3)

    def test_skips_name_with_whitespace(self):
        # split_tokens wuerde hier trennen und die Zeile anders deuten.
        report = symbolmap.parse("memset=0x80003100\nzwei worte=0x80003200\n")
        self.assertEqual(len(report.accepted), 1)
        self.assertIn("Leerraum im Namen", report.skipped)

    def test_removes_exact_duplicates(self):
        report = symbolmap.parse(
            "gpMarioAddress=0x8040E108\ngpMarioAddress=0x8040E108\n")
        self.assertEqual(len(report.accepted), 1)
        self.assertIn("doppelter Eintrag", report.skipped)

    def test_keeps_two_names_at_one_address(self):
        report = symbolmap.parse("first=0x80003100\nsecond=0x80003100\n")
        self.assertEqual(len(report.accepted), 2)

    def test_rejects_a_list_without_usable_entries(self):
        with self.assertRaises(symbolmap.SymbolMapError):
            symbolmap.parse("nur Text ohne Adressen\n")

    def test_reports_unknown_line_shape(self):
        report = symbolmap.parse("memset=0x80003100\nkaputt\n")
        self.assertIn("unbekannte Zeilenform", report.skipped)


class OutputFormatTests(unittest.TestCase):
    """Die Ausgabe wird gegen die Nachbildung von DolRecomps Leser geprueft."""

    def test_recompiler_reads_back_every_symbol(self):
        source = ("memset=0x80003100\n__start=0x8000522C\n"
                  "__vt__6TMario=0x803DD660\n")
        accepted = symbolmap.parse(source).accepted
        loaded = dolrecomp_load(symbolmap.to_dolrecomp(accepted))
        self.assertEqual([(a, n) for a, _, n in loaded],
                         [(0x80003100, "memset"), (0x8000522C, "__start"),
                          (0x803DD660, "__vt__6TMario")])

    def test_comment_lines_are_ignored_by_the_recompiler(self):
        accepted = symbolmap.parse("memset=0x80003100\n").accepted
        output = symbolmap.to_dolrecomp(accepted)
        self.assertTrue(any(line.startswith("#") for line in output.splitlines()))
        self.assertEqual(len(dolrecomp_load(output)), 1)

    def test_size_is_zero_so_the_recompiler_infers_it(self):
        accepted = symbolmap.parse("memset=0x80003100\n").accepted
        self.assertEqual(dolrecomp_load(symbolmap.to_dolrecomp(accepted))[0][1], 0)

    def test_output_is_sorted_and_deterministic(self):
        source = "later=0x80003200\nb=0x80003100\na=0x80003100\n"
        accepted = symbolmap.parse(source).accepted
        first = symbolmap.to_dolrecomp(accepted)
        self.assertEqual(first, symbolmap.to_dolrecomp(list(reversed(accepted))))
        rows = [line.split() for line in first.splitlines()
                if not line.startswith("#")]
        self.assertEqual(rows, [["80003100", "a"], ["80003100", "b"],
                                ["80003200", "later"]])

    def test_mangled_names_survive_the_round_trip(self):
        name = "@12@JSGFindObject__Q26JDrama9TDirectorCFPCcQ26JStage8TEObject"
        accepted = symbolmap.parse(f"{name}=0x80177974\n").accepted
        self.assertEqual(dolrecomp_load(symbolmap.to_dolrecomp(accepted))[0][2],
                         name)


class IdentifierTests(unittest.TestCase):
    def test_replaces_forbidden_characters(self):
        self.assertEqual(symbolmap.to_identifier("MsWrap<f>__Ffff"),
                         "MsWrap_f_Ffff")

    def test_collapses_repeated_underscores(self):
        self.assertEqual(symbolmap.to_identifier("a__b"), "a_b")
        self.assertEqual(symbolmap.to_identifier("a___b"), "a_b")

    def test_strips_trailing_underscores(self):
        self.assertEqual(symbolmap.to_identifier("name__"), "name")

    def test_prefixes_a_leading_digit(self):
        self.assertEqual(symbolmap.to_identifier("12name"), "_12name")

    def test_truncates_at_the_recompiler_buffer(self):
        self.assertEqual(len(symbolmap.to_identifier("a" * 400)), 255)

    def test_finds_collisions_from_collapsed_underscores(self):
        report = symbolmap.parse(
            "writeBlock__12TCardManagerFUl=0x80003100\n"
            "writeBlock___12TCardManagerFUl=0x80003200\n")
        collisions = symbolmap.identifier_collisions(report.accepted)
        self.assertIn("writeBlock_12TCardManagerFUl", collisions)

    def test_same_address_twice_is_no_collision(self):
        report = symbolmap.parse("alias=0x80003100\nalias2=0x80003200\n")
        self.assertEqual(symbolmap.identifier_collisions(report.accepted), {})


class DolTests(unittest.TestCase):
    def _write(self, directory: str, **kwargs) -> Path:
        path = Path(directory) / "main.dol"
        path.write_bytes(build_dol(**kwargs))
        return path

    def test_reads_sections_and_entry(self):
        with TemporaryDirectory() as tmp:
            binary = dolfile.read(self._write(tmp))
        self.assertEqual(binary.entry, TEXT_ADDRESS)
        self.assertEqual(len(binary.text_sections), 1)
        self.assertEqual(len(binary.sections), 2)

    def test_classifies_addresses_by_section(self):
        with TemporaryDirectory() as tmp:
            binary = dolfile.read(self._write(tmp))
        self.assertTrue(binary.section_of(TEXT_ADDRESS).executable)
        self.assertFalse(binary.section_of(DATA_ADDRESS).executable)
        self.assertIsNone(binary.section_of(0x80500000))

    def test_reads_words_big_endian_and_stops_at_the_edge(self):
        with TemporaryDirectory() as tmp:
            binary = dolfile.read(self._write(tmp, text_words=[MFLR, BLR]))
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
            one = dolfile.read(self._write(tmp, text_slots=1))
        self.assertEqual(len(dolfile.free_text_slots(one)),
                         dolfile.TEXT_SECTIONS - 1)
        with TemporaryDirectory() as tmp:
            two = dolfile.read(self._write(tmp, text_slots=2))
        self.assertEqual(len(dolfile.free_text_slots(two)),
                         dolfile.TEXT_SECTIONS - 2)


class MeasurementTests(unittest.TestCase):
    def test_recognises_prologue_and_terminator(self):
        # blr, dann stwu: die zweite Adresse ist ein glaubhafter Funktionsanfang.
        words = [MFLR, BLR, STWU, BLR]
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "main.dol"
            path.write_bytes(build_dol(text_words=words))
            binary = dolfile.read(path)
        result = dolfile.measure(binary, [TEXT_ADDRESS, TEXT_ADDRESS + 8])
        self.assertEqual(result.sampled, 2)
        self.assertEqual(result.prologue, 2)          # mflr und stwu
        self.assertEqual(result.preceded_by_terminator, 1)  # nur vor stwu ein blr

    def test_ignores_addresses_outside_text(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "main.dol"
            path.write_bytes(build_dol())
            binary = dolfile.read(path)
        self.assertEqual(dolfile.measure(binary, [DATA_ADDRESS, 0x80500000]).sampled, 0)

    def test_nop_counts_as_terminator_but_not_prologue(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "main.dol"
            path.write_bytes(build_dol(text_words=[ORI_NOP, MFLR]))
            binary = dolfile.read(path)
        result = dolfile.measure(binary, [TEXT_ADDRESS + 4])
        self.assertEqual(result.preceded_by_terminator, 1)
        self.assertEqual(result.prologue, 1)

    def test_control_sample_is_aligned_inside_text_and_repeatable(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "main.dol"
            path.write_bytes(build_dol())
            binary = dolfile.read(path)
        sample = dolfile.control_sample(binary, 50)
        self.assertEqual(len(sample), 50)
        self.assertTrue(all(address % 4 == 0 for address in sample))
        self.assertTrue(all(binary.section_of(a).executable for a in sample))
        self.assertEqual(sample, dolfile.control_sample(binary, 50))


class VendoredMapTests(unittest.TestCase):
    """Die beiliegende Liste selbst -- ohne Spieldaten pruefbar."""

    @classmethod
    def setUpClass(cls):
        cls.path = (Path(__file__).resolve().parent.parent / "tools" / "symbols"
                    / "gmse01-bettersunshineengine.map")
        cls.report = symbolmap.read(cls.path)

    def test_checksum_matches_the_pinned_source(self):
        digest = hashlib.sha256(self.path.read_bytes()).hexdigest()
        self.assertEqual(
            digest,
            "62eec2cb40ac19ccf2cddabffd37cca2e34761684c6bca250c7dc3f7d83a2c40",
            "Die angeheftete Symbolliste wurde veraendert; "
            "tools/symbols/README.md nachziehen.")

    def test_matches_addresses_measured_in_this_project(self):
        # Unabhaengig am laufenden Spiel gemessen, siehe docs/04 und docs/06.
        names_at = {}
        for symbol in self.report.accepted:
            names_at.setdefault(symbol.address, set()).add(symbol.name)
        for address, expected in [
            (0x8000522C, "__start"),
            (0x8040E108, "gpMarioAddress"),
            (0x8040E10C, "gpMarioPos"),
            (0x803DD660, "__vt__6TMario"),
            (0x803BB71C, "__vt__17TBiancoGateKeeper"),
            (0x80404454, "mPadStatus__10JUTGamePad"),
        ]:
            self.assertIn(expected, names_at.get(address, set()),
                          f"0x{address:08X} traegt nicht den erwarteten Namen")

    def test_every_accepted_symbol_survives_the_recompiler(self):
        loaded = dolrecomp_load(symbolmap.to_dolrecomp(self.report.accepted))
        self.assertEqual(len(loaded), len(self.report.accepted))


if __name__ == "__main__":
    unittest.main()
