"""Tests fuer die Pruefung des Abnahmelaufs (ohne Spielkopie)."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

_TOOLS = Path(__file__).resolve().parent.parent / "tools"
sys.path.insert(0, str(_TOOLS / "acceptance"))

import check as checker  # noqa: E402

SHUTDOWN = ("[staticrecomp] shutdown: native=682 fallback=0 native_exc=1 hook_fb=198 "
            "smc_failed=0 verifications=7 reverify_events=5 bursts=17 cycles=59591\n")


def manifest(frames=(0, 600), presents=(0, 1800), exit_code=0, error=None, reads=None,
             audio=True):
    m = {"exit_code": exit_code, "error": error,
         "status_at_start": {"frame_count": str(frames[0]), "present_count": str(presents[0])},
         "status_at_end": {"frame_count": str(frames[1]), "present_count": str(presents[1])},
         "reads": reads or {}}
    if audio:
        m["audio"] = [{"path": "/nirgends/GMSE01_dspdump.wav"}]
    return m


class CounterTests(unittest.TestCase):
    def test_reads_the_shutdown_line(self):
        found = checker.counters("Unsinn\n" + SHUTDOWN)
        self.assertEqual(found["native"], 682)
        self.assertEqual(found["fallback"], 0)
        self.assertEqual(found["smc_failed"], 0)
        self.assertEqual(found["cycles"], 59591)

    def test_takes_the_last_line_and_tolerates_none(self):
        second = SHUTDOWN.replace("native=682", "native=999")
        self.assertEqual(checker.counters(SHUTDOWN + second)["native"], 999)
        self.assertIsNone(checker.counters("kein Kern hier"))

    def test_unknown_counters_do_not_break_the_line(self):
        # Die Zeile ist im Vorhaben schon zweimal gewachsen. Eine feste
        # Reihenfolge haette jede Erweiterung in "keine Zaehlerzeile" verwandelt.
        erweitert = SHUTDOWN.rstrip("\n") + " ticks=1000 neuer_zaehler=7\n"
        found = checker.counters(erweitert)
        self.assertEqual(found["native"], 682)
        self.assertEqual(found["ticks"], 1000)
        self.assertEqual(found["neuer_zaehler"], 7)

    def test_a_line_without_native_is_not_a_counter_line(self):
        self.assertIsNone(checker.counters("shutdown: irgendwas=1 anderes=2\n"))


class NativeShareTests(unittest.TestCase):
    """Der Anteil nativ verbuchter Gasttakte -- die Zusage aus docs/16."""

    def _run(self, want, line):
        scenario = {"name": "t", "frames": 1, "expect": {"min_native_share": want}}
        return checker.check(scenario, manifest(), line)

    def test_share_is_measured_not_estimated(self):
        line = SHUTDOWN.rstrip("\n") + " ticks=100000\n"
        result = self._run(0.5, line.replace("cycles=59591", "cycles=60000"))
        self.assertTrue(result.passed)
        self.assertIn("60.00%", result.checks[0][2])

    def test_share_below_the_promise_fails(self):
        line = SHUTDOWN.rstrip("\n") + " ticks=100000\n"
        self.assertFalse(self._run(0.9, line.replace("cycles=59591", "cycles=60000")).passed)

    def test_without_ticks_the_promise_cannot_be_checked(self):
        # Lieber durchfallen als aus der Bildzahl schaetzen: genau diese
        # Schaetzung war in docs/13 eine Annahme und keine Messung.
        result = self._run(0.5, SHUTDOWN)
        self.assertFalse(result.passed)
        self.assertIn("ticks=", result.checks[0][2])

    def test_without_a_counter_line_the_promise_cannot_be_checked(self):
        result = self._run(0.5, "nichts")
        self.assertFalse(result.passed)


class CheckTests(unittest.TestCase):
    def test_all_promises_kept(self):
        scenario = {"name": "t", "frames": 600, "expect": {
            "exit_code": 0, "no_error": True, "min_frames": 550,
            "smc_failed": 0, "max_fallback": 0,
            "reads": {"arena-lo": "0x8040ce48"},
            "audio_min_seconds": 10.0, "audio_max_silence_share": 0.9,
            "audio_seconds_per_present": [0.011, 0.013]}}
        m = manifest(reads={"arena-lo": {"u32": "0x8040ce48"}})
        result = checker.check(scenario, m, SHUTDOWN,
                               {"seconds": 21.6, "silent_share": 0.65})
        self.assertTrue(result.passed, result.as_dict())
        self.assertEqual(len(result.checks), 9)

    def test_each_promise_can_fail(self):
        base = {"name": "t", "frames": 600}
        cases = [
            ({"exit_code": 0}, manifest(exit_code=1), SHUTDOWN, None),
            ({"no_error": True}, manifest(error="kaputt"), SHUTDOWN, None),
            ({"min_frames": 700}, manifest(), SHUTDOWN, None),
            ({"smc_failed": 0}, manifest(), SHUTDOWN.replace("smc_failed=0", "smc_failed=1"), None),
            ({"max_fallback": 0}, manifest(), SHUTDOWN.replace("fallback=0", "fallback=5"), None),
            ({"reads": {"x": "0x1"}}, manifest(reads={"x": {"u32": "0x2"}}), SHUTDOWN, None),
            ({"audio_min_seconds": 30.0}, manifest(), SHUTDOWN, {"seconds": 5.0, "silent_share": 0.1}),
            ({"audio_max_silence_share": 0.5}, manifest(), SHUTDOWN, {"seconds": 5.0, "silent_share": 0.9}),
            ({"audio_seconds_per_present": [0.011, 0.013]}, manifest(), SHUTDOWN,
             {"seconds": 100.0, "silent_share": 0.1}),
        ]
        for expect, m, err, audio in cases:
            with self.subTest(expect=expect):
                result = checker.check(base | {"expect": expect}, m, err, audio)
                self.assertFalse(result.passed, f"{expect} haette scheitern muessen")

    def test_missing_counter_line_fails_counter_promises(self):
        scenario = {"name": "t", "frames": 1, "expect": {"smc_failed": 0, "max_fallback": 0}}
        result = checker.check(scenario, manifest(), "")
        self.assertFalse(result.passed)
        self.assertTrue(all("Zaehlerzeile" in d for _, _, d in result.checks))

    def test_audio_promise_without_recording_fails(self):
        scenario = {"name": "t", "frames": 1, "expect": {"audio_min_seconds": 1.0}}
        result = checker.check(scenario, manifest(audio=False), SHUTDOWN, None)
        self.assertFalse(result.passed)
        self.assertIn("Tonmitschnitt", result.checks[0][0])

    def test_missing_read_is_reported(self):
        scenario = {"name": "t", "frames": 1, "expect": {"reads": {"fehlt": "0x1"}}}
        result = checker.check(scenario, manifest(), SHUTDOWN)
        self.assertFalse(result.passed)
        self.assertIn("fehlt im Manifest", result.checks[0][2])

    def test_empty_expect_is_itself_a_failure(self):
        result = checker.check({"name": "leer", "frames": 1, "expect": {}}, manifest(), SHUTDOWN)
        self.assertFalse(result.passed)

    def test_broken_counters_do_not_crash(self):
        scenario = {"name": "t", "frames": 1, "expect": {"min_frames": 1}}
        m = manifest()
        m["status_at_end"] = {}
        result = checker.check(scenario, m, SHUTDOWN)
        self.assertFalse(result.passed)
        self.assertIn("Zaehler fehlen", result.checks[0][2])


class ScenarioFileTests(unittest.TestCase):
    def test_shipped_scenarios_are_well_formed(self):
        folder = _TOOLS / "acceptance"
        found = sorted(folder.glob("*.json"))
        self.assertTrue(found, "keine Szenarien vorhanden")
        for path in found:
            with self.subTest(path.name):
                scenario = json.loads(path.read_text())
                for required in ("name", "frames", "expect"):
                    self.assertIn(required, scenario)
                self.assertTrue(scenario["expect"], "leere Zusagen")
                if "sequence" in scenario:
                    self.assertTrue((folder / scenario["sequence"]).is_file(),
                                    f"{scenario['sequence']} fehlt")
                for spec in scenario.get("reads", []):
                    address, size, name = spec.split(":")
                    int(address, 0), int(size, 0)
                    self.assertTrue(name)


class ReadRangeTests(unittest.TestCase):
    def test_range_accepts_a_pointer_inside_memory(self):
        scenario = {"name": "t", "frames": 1, "expect": {
            "reads": {"mario": ["0x80000000", "0x81800000"]}}}
        m = manifest(reads={"mario": {"u32": "0x80e9ad44"}})
        self.assertTrue(checker.check(scenario, m, SHUTDOWN).passed)

    def test_range_rejects_a_pointer_outside(self):
        scenario = {"name": "t", "frames": 1, "expect": {
            "reads": {"mario": ["0x80000000", "0x81800000"]}}}
        for value in ("0x0", "0x1000000", "0x81800004"):
            with self.subTest(value=value):
                m = manifest(reads={"mario": {"u32": value}})
                self.assertFalse(checker.check(scenario, m, SHUTDOWN).passed)

    def test_range_on_a_non_word_read_fails_clearly(self):
        scenario = {"name": "t", "frames": 1, "expect": {"reads": {"blob": ["0x0", "0x10"]}}}
        m = manifest(reads={"blob": {"hex": "00112233445566"}})
        result = checker.check(scenario, m, SHUTDOWN)
        self.assertFalse(result.passed)
        self.assertIn("kein Wort", result.checks[0][2])


class StackTests(unittest.TestCase):
    BASE = 0x80417800
    FLOOR = 0x80417918

    def test_finds_the_lowest_written_address_above_the_floor(self):
        blob = bytearray(0x10000)
        blob[0:0x118] = b"\xaa" * 0x118          # eingebackener Code, unter floor
        blob[0xD4B8] = 0x01                      # Stapel reicht bis hierher
        found = checker.low_water(bytes(blob), self.BASE, self.FLOOR)
        self.assertEqual(found, self.BASE + 0xD4B8)

    def test_untouched_region_reports_none(self):
        self.assertIsNone(checker.low_water(bytes(0x1000), self.BASE, self.FLOOR))

    def test_promise_holds_with_enough_margin(self):
        blob = bytearray(0x10000)
        blob[0xD4B8] = 0x01
        scenario = {"name": "t", "frames": 1, "expect": {"stack_low_water": {
            "read": "luecke", "base": hex(self.BASE), "floor": hex(self.FLOOR),
            "min_margin": 4096}}}
        m = manifest(reads={"luecke": {"hex": bytes(blob).hex()}})
        result = checker.check(scenario, m, SHUTDOWN)
        self.assertTrue(result.passed, result.as_dict())
        self.assertIn("0x80424cb8", result.checks[0][2])

    def test_promise_fails_when_the_stack_comes_too_close(self):
        blob = bytearray(0x10000)
        blob[0x200] = 0x01                        # kurz ueber dem Codebereich
        scenario = {"name": "t", "frames": 1, "expect": {"stack_low_water": {
            "read": "luecke", "base": hex(self.BASE), "floor": hex(self.FLOOR),
            "min_margin": 4096}}}
        m = manifest(reads={"luecke": {"hex": bytes(blob).hex()}})
        self.assertFalse(checker.check(scenario, m, SHUTDOWN).passed)

    def test_missing_read_is_reported(self):
        scenario = {"name": "t", "frames": 1, "expect": {"stack_low_water": {
            "read": "luecke", "base": "0x80417800", "floor": "0x80417918"}}}
        result = checker.check(scenario, manifest(), SHUTDOWN)
        self.assertFalse(result.passed)
        self.assertIn("fehlt", result.checks[0][2])


class ProjectionAspectTests(unittest.TestCase):
    """Die Zusage fuer das Sichtverhaeltnis (docs/19-ULTRAWIDE.md)."""

    @staticmethod
    def _dff(path, waagerecht: float, senkrecht: float, ortho: bool = False):
        """Eine synthetische Aufzeichnung mit genau einer Projektion."""
        import struct
        sys.path.insert(0, str(_TOOLS / "framerate"))
        import fifo  # noqa: PLC0415
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from test_framerate import CP_STATE, build_dff, primitive, xf_load  # noqa: PLC0415

        def bits(value):
            return struct.unpack(">I", struct.pack(">f", value))[0]

        stream = (xf_load(0x1020, [bits(waagerecht), 0, bits(senkrecht), 0, 0, 0])
                  + xf_load(0x1026, [1 if ortho else 0])
                  + primitive(0x90, 3, 12))
        path.write_bytes(build_dff([stream], [[]], CP_STATE))

    def _run(self, spec, **kwargs):
        with TemporaryDirectory() as tmp:
            dff = Path(tmp) / "szene.dff"
            self._dff(dff, **kwargs)
            m = manifest()
            m["recordings"] = [{"path": str(dff), "frames": 1}]
            scenario = {"name": "t", "frames": 1, "expect": {"projection_aspect": spec}}
            return checker.check(scenario, m, SHUTDOWN)

    def test_sixteen_nine_is_accepted(self):
        result = self._run({"recording": "szene", "frame": 0, "value": 16 / 9},
                           waagerecht=1.545456, senkrecht=2.747478)
        self.assertTrue(result.passed, result.checks)

    def test_a_wrong_aspect_fails(self):
        result = self._run({"recording": "szene", "frame": 0, "value": 64 / 27},
                           waagerecht=1.545456, senkrecht=2.747478)
        self.assertFalse(result.passed)
        self.assertIn("1.7777", result.checks[0][2])

    def test_ultrawide_is_accepted(self):
        result = self._run({"recording": "szene", "frame": 0, "value": 64 / 27},
                           waagerecht=1.159092, senkrecht=2.747478)
        self.assertTrue(result.passed, result.checks)

    def test_an_orthographic_frame_has_no_aspect(self):
        # Filme und HUD zeichnen orthografisch; daran laesst sich nichts messen.
        result = self._run({"recording": "szene", "frame": 0, "value": 16 / 9},
                           waagerecht=1.545456, senkrecht=2.747478, ortho=True)
        self.assertFalse(result.passed)
        self.assertIn("keine perspektivische", result.checks[0][2])

    def test_a_missing_recording_is_a_failure_not_a_pass(self):
        scenario = {"name": "t", "frames": 1,
                    "expect": {"projection_aspect": {"recording": "fehlt", "value": 1.0}}}
        result = checker.check(scenario, manifest(), SHUTDOWN)
        self.assertFalse(result.passed)
        self.assertIn("fehlt", result.checks[0][2])
