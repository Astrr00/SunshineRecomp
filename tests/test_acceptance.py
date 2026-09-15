"""Tests fuer die Pruefung des Abnahmelaufs (ohne Spielkopie)."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

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
