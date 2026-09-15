"""Tests fuer das Einbacken spielseitiger Gecko-Codes in ein DOL.

Die Codes hier sind erfunden; das DOL ist synthetisch. Geprueft wird der
Mechanismus, nicht der echte Widescreen-Code und nicht das Verhalten im Spiel.

Ein zusaetzlicher Test greift auf die echte ``GMSE01.ini`` zu, sofern der
Bootstrap sie nach ``ref/`` geholt hat. Ohne sie wird er uebersprungen statt
zu scheitern -- die Datei gehoert nicht in dieses Repository.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

_ROOT = Path(__file__).resolve().parent.parent
_TOOLS = _ROOT / "tools"
sys.path.insert(0, str(_TOOLS / "widescreen"))
sys.path.insert(0, str(_TOOLS / "common"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import bake as baker  # noqa: E402
import dol as dolfile  # noqa: E402
import gecko  # noqa: E402
from test_dol import (BLR, DATA_ADDRESS, MFLR, NOP, TEXT_ADDRESS,  # noqa: E402
                      build_dol, write_dol)

GAME_INI = (_ROOT / "ref" / "ModernGekko" / "vendor" / "dolphin" / "Data" /
            "Sys" / "GameSettings" / "GMSE01.ini")

SIMPLE = """\
[Gecko]
$Beispiel [autor]
04003104 60000000
C2003108 00000002
3B20FFA9 93380004
931F0140 00000000
$Anderer [autor]
04003100 11111111
"""


def ini_with(lines: str) -> str:
    return "[Gecko]\n$Test [autor]\n" + lines


class ParseTests(unittest.TestCase):
    def test_lists_the_codes_of_a_section(self):
        self.assertEqual(gecko.list_codes(SIMPLE),
                         ["Beispiel [autor]", "Anderer [autor]"])

    def test_matches_the_name_without_the_author(self):
        code = gecko.parse(SIMPLE, "Beispiel")
        self.assertEqual(len(code.writes), 1)

    def test_matches_the_full_name_with_the_author(self):
        self.assertEqual(len(gecko.parse(SIMPLE, "Beispiel [autor]").writes), 1)

    def test_reads_a_direct_write(self):
        code = gecko.parse(ini_with("04412408 3FE38E39\n"), "Test")
        self.assertEqual(code.writes[0].address, 0x80412408)
        self.assertEqual(code.writes[0].value, 0x3FE38E39)

    def test_body_excludes_the_word_the_handler_replaces(self):
        code = gecko.parse(ini_with(
            "C2003108 00000002\n3B20FFA9 93380004\n931F0140 00000000\n"), "Test")
        injection = code.injections[0]
        self.assertEqual(injection.body, (0x3B20FFA9, 0x93380004, 0x931F0140))
        self.assertEqual(injection.placeholder, 0)
        self.assertEqual(injection.returns_to, 0x8000310C)

    def test_reads_several_codes_in_sequence(self):
        code = gecko.parse(ini_with(
            "04003100 11111111\nC2003108 00000001\n60000000 00000000\n"
            "04003200 22222222\n"), "Test")
        self.assertEqual(len(code.writes), 2)
        self.assertEqual(len(code.injections), 1)

    def test_records_an_unsupported_code_type_instead_of_failing(self):
        code = gecko.parse(ini_with("28003100 00001234\n"), "Test")
        self.assertEqual(len(code.unsupported), 1)
        self.assertIn("0x28", code.unsupported[0])

    def test_rejects_an_injection_that_runs_past_the_end(self):
        with self.assertRaises(gecko.GeckoError) as caught:
            gecko.parse(ini_with("C2003108 00000009\n60000000 00000000\n"), "Test")
        self.assertIn("endet aber vorher", str(caught.exception))

    def test_rejects_an_injection_of_zero_lines(self):
        with self.assertRaises(gecko.GeckoError):
            gecko.parse(ini_with("C2003108 00000000\n"), "Test")

    def test_rejects_a_malformed_line(self):
        with self.assertRaises(gecko.GeckoError) as caught:
            gecko.parse(ini_with("nur Text\n"), "Test")
        self.assertIn("XXXXXXXX", str(caught.exception))

    def test_names_the_available_codes_when_one_is_missing(self):
        with self.assertRaises(gecko.GeckoError) as caught:
            gecko.parse(SIMPLE, "GibtEsNicht")
        self.assertIn("Beispiel", str(caught.exception))

    def test_ignores_other_sections(self):
        text = ("[ActionReplay]\n$Test [autor]\n04003100 11111111\n"
                "[Gecko]\n$Test [autor]\n04003200 22222222\n")
        code = gecko.parse(text, "Test")
        self.assertEqual([w.address for w in code.writes], [0x80003200])


class BakeTests(unittest.TestCase):
    def _dol(self, tmp: str, **kwargs) -> dolfile.Dol:
        return dolfile.read(write_dol(tmp, text_words=[NOP] * 64,
                                      data_words=64, **kwargs))

    def test_applies_writes_to_text_and_data(self):
        code = gecko.parse(ini_with(
            f"04{TEXT_ADDRESS & 0xFFFFFF:06X} AABBCCDD\n"
            f"04{DATA_ADDRESS & 0xFFFFFF:06X} 11223344\n"), "Test")
        with TemporaryDirectory() as tmp:
            binary = self._dol(tmp)
            data, report = baker.bake(binary, code)
            path = Path(tmp) / "out.dol"
            path.write_bytes(data)
            result = dolfile.read(path)
        self.assertTrue(report.ok)
        self.assertEqual(len(report.writes_applied), 2)
        self.assertEqual(result.word_at(TEXT_ADDRESS), 0xAABBCCDD)
        self.assertEqual(result.word_at(DATA_ADDRESS), 0x11223344)

    def test_reports_a_write_into_bss_instead_of_dropping_it(self):
        code = gecko.parse(ini_with("04500000 AABBCCDD\n"), "Test")
        with TemporaryDirectory() as tmp:
            _, report = baker.bake(self._dol(tmp), code)
        self.assertFalse(report.ok)
        self.assertEqual(len(report.writes_rejected), 1)
        self.assertIn("BSS", report.writes_rejected[0][1])

    def test_injection_branches_into_the_cave_and_back(self):
        target = TEXT_ADDRESS + 0x40
        code = gecko.parse(ini_with(
            f"C2{target & 0xFFFFFF:06X} 00000002\n"
            "3B20FFA9 93380004\n931F0140 00000000\n"), "Test")
        with TemporaryDirectory() as tmp:
            binary = self._dol(tmp)
            data, report = baker.bake(binary, code)
            path = Path(tmp) / "out.dol"
            path.write_bytes(data)
            result = dolfile.read(path)
        self.assertTrue(report.ok, report.problems)
        cave = report.placements[0].address
        self.assertEqual(result.word_at(target), dolfile.branch(target, cave))
        self.assertEqual(result.word_at(cave), 0x3B20FFA9)
        self.assertEqual(result.word_at(cave + 4), 0x93380004)
        self.assertEqual(result.word_at(cave + 8), 0x931F0140)
        # Das letzte Wort ist der Ruecksprung hinter die Einfuegestelle.
        self.assertEqual(result.word_at(cave + 12),
                         dolfile.branch(cave + 12, target + 4))

    def test_records_the_instruction_the_branch_displaces(self):
        target = TEXT_ADDRESS + 0x40
        code = gecko.parse(ini_with(
            f"C2{target & 0xFFFFFF:06X} 00000001\n60000000 00000000\n"), "Test")
        with TemporaryDirectory() as tmp:
            _, report = baker.bake(self._dol(tmp), code)
        self.assertEqual(report.replaced_instructions[target], NOP)

    def test_places_several_injections_one_after_another(self):
        first, second = TEXT_ADDRESS + 0x40, TEXT_ADDRESS + 0x80
        code = gecko.parse(ini_with(
            f"C2{first & 0xFFFFFF:06X} 00000001\n60000000 00000000\n"
            f"C2{second & 0xFFFFFF:06X} 00000002\n"
            "3B20FFA9 93380004\n931F0140 00000000\n"), "Test")
        with TemporaryDirectory() as tmp:
            _, report = baker.bake(self._dol(tmp), code)
        one, two = report.placements
        self.assertEqual(one.end, two.address)
        self.assertEqual(len(one.words), 2)   # ein Rumpfwort plus Ruecksprung
        self.assertEqual(len(two.words), 4)   # drei Rumpfworte plus Ruecksprung

    def test_refuses_an_injection_into_a_data_section(self):
        code = gecko.parse(ini_with(
            f"C2{DATA_ADDRESS & 0xFFFFFF:06X} 00000001\n60000000 00000000\n"),
            "Test")
        with TemporaryDirectory() as tmp:
            _, report = baker.bake(self._dol(tmp), code)
        self.assertFalse(report.ok)
        self.assertTrue(any("Datensektion" in problem
                            for problem in report.problems))

    def test_refuses_a_cave_that_overlaps_bss(self):
        target = TEXT_ADDRESS + 0x40
        code = gecko.parse(ini_with(
            f"C2{target & 0xFFFFFF:06X} 00000001\n60000000 00000000\n"), "Test")
        with TemporaryDirectory() as tmp:
            _, report = baker.bake(self._dol(tmp), code, cave_address=0x80500000)
        self.assertFalse(report.ok)
        self.assertTrue(any("bss" in problem for problem in report.problems))

    def test_notices_a_write_that_collides_with_an_injection(self):
        target = TEXT_ADDRESS + 0x40
        code = gecko.parse(ini_with(
            f"04{target & 0xFFFFFF:06X} AABBCCDD\n"
            f"C2{target & 0xFFFFFF:06X} 00000001\n60000000 00000000\n"), "Test")
        with TemporaryDirectory() as tmp:
            _, report = baker.bake(self._dol(tmp), code)
        self.assertFalse(report.ok)
        self.assertTrue(any("zugleich" in problem for problem in report.problems))

    def test_notices_two_different_values_for_one_address(self):
        code = gecko.parse(ini_with(
            f"04{TEXT_ADDRESS & 0xFFFFFF:06X} AABBCCDD\n"
            f"04{TEXT_ADDRESS & 0xFFFFFF:06X} 11223344\n"), "Test")
        with TemporaryDirectory() as tmp:
            _, report = baker.bake(self._dol(tmp), code)
        self.assertFalse(report.ok)
        self.assertTrue(any("zweimal" in problem for problem in report.problems))

    def test_counts_every_word_it_read_back(self):
        target = TEXT_ADDRESS + 0x40
        code = gecko.parse(ini_with(
            f"04{DATA_ADDRESS & 0xFFFFFF:06X} 11223344\n"
            f"C2{target & 0xFFFFFF:06X} 00000002\n"
            "3B20FFA9 93380004\n931F0140 00000000\n"), "Test")
        with TemporaryDirectory() as tmp:
            _, report = baker.bake(self._dol(tmp), code)
        # ein Schreiben, ein Sprung an der Einfuegestelle, vier Worte im Bereich
        self.assertEqual(report.verified_words, 6)

    def test_default_cave_sits_behind_everything_the_dol_occupies(self):
        with TemporaryDirectory() as tmp:
            binary = self._dol(tmp)
            address = baker.default_cave_address(binary)
        highest = max(region.end for region in dolfile.memory_map(binary))
        self.assertGreaterEqual(address, highest)
        self.assertEqual(address % dolfile.SECTION_ALIGNMENT, 0)

    def test_onframe_section_uses_the_form_moderngekko_port_reads(self):
        code = gecko.parse(ini_with(
            f"04{DATA_ADDRESS & 0xFFFFFF:06X} 11223344\n"), "Test")
        with TemporaryDirectory() as tmp:
            _, report = baker.bake(self._dol(tmp), code)
        text = baker.onframe_section(report.writes_applied, "Test")
        self.assertIn("[OnFrame]", text)
        self.assertIn("[OnFrame_Enabled]", text)
        self.assertIn(f"0x{DATA_ADDRESS:08X}:dword:0x11223344", text)


@unittest.skipUnless(GAME_INI.is_file(),
                     "GMSE01.ini fehlt; bitte scripts/bootstrap.ps1 ausfuehren")
class RealCodeTests(unittest.TestCase):
    """Gegen die echte Spiel-INI, sobald der Bootstrap sie geholt hat."""

    @classmethod
    def setUpClass(cls):
        cls.text = GAME_INI.read_text(encoding="utf-8", errors="replace")

    def test_widescreen_has_the_documented_shape(self):
        # docs/03-WIDESCREEN.md: 13 direkte Schreibungen, 12 Einfuegungen.
        code = gecko.parse(self.text, "Widescreen")
        self.assertEqual(len(code.writes), 13)
        self.assertEqual(len(code.injections), 12)
        self.assertEqual(code.unsupported, [])

    def test_every_placeholder_is_zero(self):
        code = gecko.parse(self.text, "Widescreen")
        self.assertEqual({i.placeholder for i in code.injections}, {0})


if __name__ == "__main__":
    unittest.main()


class AspectTests(unittest.TestCase):
    """Das Seitenverhaeltnis als einstellbares Wort (docs/19-ULTRAWIDE.md)."""

    def _code(self, aspect_value=gecko.ASPECT_16_9):
        return gecko.GeckoCode(
            name="Widescreen",
            writes=[gecko.Write(0x80416758, 0x44480000),
                    gecko.Write(gecko.ASPECT_ADDRESS, aspect_value)],
            injections=[])

    def test_parses_ratios_and_numbers(self):
        self.assertAlmostEqual(gecko.parse_aspect("16:9"), 16 / 9)
        self.assertAlmostEqual(gecko.parse_aspect("64:27"), 64 / 27)
        self.assertAlmostEqual(gecko.parse_aspect("2.37"), 2.37)
        self.assertAlmostEqual(gecko.parse_aspect(" 32 : 9 "), 32 / 9)

    def test_sixteen_nine_reproduces_the_shipped_word(self):
        # Die Gegenprobe: Wer 16:9 verlangt, muss genau das Wort bekommen,
        # das der Code ohnehin schreibt. Sonst stimmt die Umrechnung nicht.
        self.assertEqual(gecko.aspect_bits(gecko.parse_aspect("16:9")),
                         gecko.ASPECT_16_9)

    def test_rejects_nonsense(self):
        for text in ("", "breit", "16:0", "0:9", "0.5", "99:1"):
            with self.assertRaises(gecko.GeckoError):
                gecko.parse_aspect(text)

    def test_retarget_changes_only_the_aspect_word(self):
        code = self._code()
        wide = gecko.retarget_aspect(code, 64 / 27)
        self.assertEqual(len(wide.writes), len(code.writes))
        geaendert = {w.address: w.value for w in wide.writes}
        self.assertEqual(geaendert[0x80416758], 0x44480000)
        self.assertEqual(geaendert[gecko.ASPECT_ADDRESS], 0x4017B426)

    def test_retarget_refuses_an_unexpected_code(self):
        # Ein Code, der dort nicht 16/9 traegt, ist ein anderer Code.
        with self.assertRaises(gecko.GeckoError):
            gecko.retarget_aspect(self._code(0x3FAAAAAB), 64 / 27)
        leer = gecko.GeckoCode(name="ohne", writes=[], injections=[])
        with self.assertRaises(gecko.GeckoError):
            gecko.retarget_aspect(leer, 64 / 27)
