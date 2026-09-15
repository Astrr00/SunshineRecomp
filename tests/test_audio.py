"""Tests fuer den WAV-Leser und die Tonmessung (synthetische Signale)."""

from __future__ import annotations

import array
import math
import struct
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

_TOOLS = Path(__file__).resolve().parent.parent / "tools"
sys.path.insert(0, str(_TOOLS / "audio"))

import measure  # noqa: E402
import wav  # noqa: E402


def sine(rate: int, seconds: float, hz: float, amplitude: float = 0.5,
         channels: int = 2) -> array.array:
    n = int(rate * seconds)
    out = array.array("h", bytes(2 * n * channels))
    for k in range(n):
        v = int(amplitude * 32767 * math.sin(2 * math.pi * hz * k / rate))
        for c in range(channels):
            out[k * channels + c] = v
    return out


class WavTests(unittest.TestCase):
    def test_round_trip(self):
        data = sine(8000, 0.25, 440.0)
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.wav"
            wav.write(path, 8000, 2, data)
            w = wav.read(path)
        self.assertEqual((w.sample_rate, w.channels, w.bits), (8000, 2, 16))
        self.assertEqual(w.frames, 2000)
        self.assertAlmostEqual(w.seconds, 0.25)
        self.assertFalse(w.truncated_header)
        self.assertEqual(list(w.samples), list(data))

    def test_accepts_a_header_with_wrong_sizes(self):
        # Dolphin schreibt die Groessen erst beim Herunterfahren; ein harter
        # Abbruch laesst sie auf dem Anfangswert stehen.
        data = sine(8000, 0.1, 200.0, channels=1)
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "b.wav"
            wav.write(path, 8000, 1, data)
            raw = bytearray(path.read_bytes())
            struct.pack_into("<I", raw, 4, 36)          # RIFF-Groesse ohne Daten
            struct.pack_into("<I", raw, 40, 0)          # data-Groesse 0
            path.write_bytes(bytes(raw))
            w = wav.read(path)
        self.assertTrue(w.truncated_header)
        self.assertEqual(w.frames, 800)                 # trotzdem alle Abtastwerte

    def test_rejects_foreign_and_unsupported_files(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "c.bin"
            path.write_bytes(b"\0" * 100)
            with self.assertRaises(wav.WavError):
                wav.read(path)
            # 8-Bit-PCM wird abgelehnt
            body = b"\x80" * 16
            head = struct.pack("<4sI4s4sIHHIIHH4sI", b"RIFF", 36 + len(body), b"WAVE",
                               b"fmt ", 16, 1, 1, 8000, 8000, 1, 8, b"data", len(body))
            path2 = Path(tmp) / "d.wav"
            path2.write_bytes(head + body)
            with self.assertRaises(wav.WavError):
                wav.read(path2)

    def test_mono_averages_channels(self):
        samples = array.array("h", [100, 300, -200, -100])   # zwei Rahmen, zwei Kanaele
        w = wav.Wave(Path("x"), 8000, 2, 16, samples, False)
        self.assertEqual(list(w.mono()), [200, -150])
        self.assertEqual(list(w.channel(0)), [100, -200])


class MeasureTests(unittest.TestCase):
    def test_envelope_and_silence(self):
        rate = 8000
        loud = sine(rate, 0.2, 300.0, amplitude=0.5, channels=1)
        quiet = array.array("h", bytes(2 * int(rate * 0.2)))
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "e.wav"
            wav.write(path, rate, 1, loud + quiet + loud)
            w = wav.read(path)
        levels = measure.envelope(w, block_ms=20.0)
        self.assertEqual(len(levels), 30)                 # 0,6 s in 20-ms-Bloecken
        runs = measure.silence_runs(levels)
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0], (10, 10))               # die mittleren 0,2 s
        self.assertAlmostEqual(levels[0], 0.5 / math.sqrt(2), places=2)

    def test_fft_finds_the_tone(self):
        rate, size, hz = 8192, 1024, 512.0
        data = sine(rate, 1.0, hz, channels=1)
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "f.wav"
            wav.write(path, rate, 1, data)
            w = wav.read(path)
        spec = measure.spectrum(w, size=size, windows=4)
        peak = max(range(len(spec)), key=lambda k: spec[k])
        self.assertEqual(peak, int(hz / (rate / size)))    # Fach 64
        self.assertAlmostEqual(measure.centroid(spec, rate, size), hz, delta=60)

    def test_fft_rejects_non_power_of_two(self):
        with self.assertRaises(ValueError):
            measure.fft([complex(0)] * 3)

    def test_pitch_ratio_detects_a_shifted_tone(self):
        rate, size = 8192, 1024
        with TemporaryDirectory() as tmp:
            waves = []
            for hz in (400.0, 800.0):
                path = Path(tmp) / f"{int(hz)}.wav"
                wav.write(path, rate, 1, sine(rate, 1.0, hz, channels=1))
                waves.append(wav.read(path))
            a, b = (measure.spectrum(w, size=size, windows=4) for w in waves)
        # b liegt eine Oktave ueber a; die Suche deckt +/- 0,25 Oktaven ab,
        # eine Oktave liegt ausserhalb und muss an den Rand laufen.
        ratio, _ = measure.pitch_ratio(a, b, rate, rate, size, span=1.5)
        self.assertAlmostEqual(ratio, 2.0, delta=0.05)
        same, score = measure.pitch_ratio(a, a, rate, rate, size)
        self.assertAlmostEqual(same, 1.0, delta=0.01)
        self.assertGreater(score, 0.99)

    def test_slope_removes_the_common_offset(self):
        # 16,683 ms je Bild, 3,4 s Startversatz in beiden Laeufen
        spf, offset = 0.016683, 3.4
        s = measure.slope(600, offset + 600 * spf, 3600, offset + 3600 * spf)
        self.assertAlmostEqual(s.seconds_per_frame, spf, places=9)
        self.assertAlmostEqual(s.offset_seconds, offset, places=6)
        self.assertAlmostEqual(s.frames_per_second, 1 / spf, places=4)
        with self.assertRaises(ValueError):
            measure.slope(600, 1.0, 600, 2.0)

    def test_clipped_share(self):
        w = wav.Wave(Path("x"), 8000, 1, 16, array.array("h", [0, 32767, -32768, 5]), False)
        self.assertEqual(measure.clipped_share(w), 0.5)


class AlignTests(unittest.TestCase):
    def test_best_lag_finds_the_shift(self):
        # Nicht periodisch, sonst waeren mehrere Versaetze gleich gut; ein
        # fester Pseudozufall statt Math.random, damit der Test reproduzierbar
        # bleibt.
        pattern, x = [], 12345
        for _ in range(60):
            x = (1103515245 * x + 12345) % (2 ** 31)
            pattern.append((x >> 16) / 32768.0)
        a = pattern
        b = [0.0] * 5 + pattern
        lag, score = measure.best_lag(a, b)
        self.assertEqual(lag, 5)
        self.assertGreater(score, 0.99)
        back, _ = measure.best_lag(b, a)
        self.assertEqual(back, -5)

    def test_best_lag_on_unrelated_signals_stays_low(self):
        a = [0.0, 1.0] * 40
        b = [0.3] * 80
        _, score = measure.best_lag(a, b)
        self.assertLess(score, 0.5)


class SpectrumWindowTests(unittest.TestCase):
    def test_span_makes_two_lengths_comparable(self):
        # Gleicher Anfang, verschiedene Laenge: mit span muessen die Spektren
        # uebereinstimmen, weil beide dieselben Zeitpunkte abtasten.
        rate, size = 8192, 512
        head = sine(rate, 1.0, 400.0, channels=1)
        tail = sine(rate, 1.0, 3000.0, channels=1)
        with TemporaryDirectory() as tmp:
            pa, pb = Path(tmp) / "a.wav", Path(tmp) / "b.wav"
            wav.write(pa, rate, 1, head + tail)
            wav.write(pb, rate, 1, head + tail + tail)
            a, b = wav.read(pa), wav.read(pb)
            without = [measure.centroid(measure.spectrum(w, size, 16), rate, size)
                       for w in (a, b)]
            withspan = [measure.centroid(
                measure.spectrum(w, size, 16, span_seconds=2.0), rate, size)
                for w in (a, b)]
        self.assertGreater(abs(without[0] - without[1]), 200)     # ohne span weit auseinander
        self.assertLess(abs(withspan[0] - withspan[1]), 30)       # mit span nahe beieinander


class IdenticalPrefixTests(unittest.TestCase):
    def test_reports_prefix_and_share(self):
        base = array.array("h", [10, 20, 30, 40, 50, 60, 70, 80])   # vier Rahmen stereo
        other = array.array("h", [10, 20, 30, 40, 99, 60, 70, 80])
        a = wav.Wave(Path("a"), 8000, 2, 16, base, False)
        b = wav.Wave(Path("b"), 8000, 2, 16, other, False)
        prefix, share = measure.identical_prefix(a, b)
        self.assertEqual(prefix, 2)                 # zwei volle Rahmen gleich
        self.assertAlmostEqual(share, 7 / 8)
        self.assertEqual(measure.identical_prefix(a, a), (4, 1.0))
