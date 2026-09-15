"""Tests fuer die Symbolliste und die DOL-Pruefung.

Alle Tests laufen ohne Spieldaten. Das DOL-Modul selbst wird in
tests/test_dol.py geprueft.

Die Gegenprobe ``dolrecomp_parse_line`` bildet ``parse_line`` aus DolRecomps
``src/analysis/symbol_map.c`` (Commit 40637c46) nach. Damit wird die erzeugte
Ausgabe nicht gegen eine Annahme geprueft, sondern gegen den Leser, der sie
spaeter tatsaechlich verarbeitet -- einschliesslich der Frage, ob die
Kommentarzeilen folgenlos uebergangen werden.
"""

from __future__ import annotations

import hashlib
import string
import sys
import unittest
from pathlib import Path

_TOOLS = Path(__file__).resolve().parent.parent / "tools"
sys.path.insert(0, str(_TOOLS / "symbols"))
sys.path.insert(0, str(_TOOLS / "common"))

import symbolmap  # noqa: E402


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
        # "char base[112]" in DolRecomps src/backend/symbols.c: 111 Zeichen.
        self.assertEqual(symbolmap.IDENTIFIER_BUFFER, 112)
        self.assertEqual(len(symbolmap.to_identifier("a" * 400)), 111)

    def test_finds_a_collision_caused_by_truncation(self):
        long_name = "x" * 130
        report = symbolmap.parse(
            f"{long_name}A=0x80003100\n{long_name}B=0x80003200\n")
        self.assertEqual(len(symbolmap.identifier_collisions(report.accepted)), 1)

    def test_finds_collisions_from_collapsed_underscores(self):
        report = symbolmap.parse(
            "writeBlock__12TCardManagerFUl=0x80003100\n"
            "writeBlock___12TCardManagerFUl=0x80003200\n")
        collisions = symbolmap.identifier_collisions(report.accepted)
        self.assertIn("writeBlock_12TCardManagerFUl", collisions)

    def test_same_address_twice_is_no_collision(self):
        report = symbolmap.parse("alias=0x80003100\nalias2=0x80003200\n")
        self.assertEqual(symbolmap.identifier_collisions(report.accepted), {})


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

    def test_identifier_collisions_are_the_measured_number(self):
        # Am erzeugten generated_symbols.h gegengeprueft: 12573 von 12573
        # Bezeichnern stimmen mit dieser Nachbildung ueberein.
        collisions = symbolmap.identifier_collisions(self.report.accepted)
        self.assertEqual(len(collisions), 22)
        distinct = {k: v for k, v in collisions.items()
                    if len({s.name for s in v}) > 1}
        self.assertEqual(len(distinct), 5)

    def test_every_accepted_symbol_survives_the_recompiler(self):
        loaded = dolrecomp_load(symbolmap.to_dolrecomp(self.report.accepted))
        self.assertEqual(len(loaded), len(self.report.accepted))


if __name__ == "__main__":
    unittest.main()
