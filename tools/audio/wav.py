"""WAV-Dateien lesen, ohne Fremdbibliotheken.

Fuer WP1 (Ton): Der Emulator schreibt den Mitschnitt mit
``AudioCommon::WaveFileWriter`` als RIFF/WAVE mit 16-Bit-PCM. Der Kopf wird
erst beim Herunterfahren mit den richtigen Laengen ueberschrieben
(``WaveFile.cpp``); wird der Prozess hart beendet, bleiben die Groessenfelder
zu klein. Dieser Leser nimmt deshalb die tatsaechliche Dateilaenge, wenn die
angegebene nicht passt, und meldet das als ``truncated_header``.

Die Datei enthaelt Spielton und bleibt lokal; hier entstehen nur Messzahlen.
"""

from __future__ import annotations

import array
import struct
import sys
from dataclasses import dataclass
from pathlib import Path


class WavError(Exception):
    pass


@dataclass
class Wave:
    path: Path
    sample_rate: int
    channels: int
    bits: int
    samples: array.array      # verschraenkt, int16
    truncated_header: bool

    @property
    def frames(self) -> int:
        """Abtastwerte je Kanal."""
        return len(self.samples) // self.channels

    @property
    def seconds(self) -> float:
        return self.frames / self.sample_rate if self.sample_rate else 0.0

    def channel(self, index: int) -> array.array:
        return self.samples[index::self.channels]

    def mono(self) -> array.array:
        """Mittelwert aller Kanaele als int32-Feld (kein Uebersteuern)."""
        if self.channels == 1:
            return array.array("i", self.samples)
        out = array.array("i", bytes(4 * self.frames))
        n, c = self.frames, self.channels
        s = self.samples
        for k in range(n):
            base = k * c
            out[k] = sum(s[base:base + c]) // c
        return out


def read(path: Path) -> Wave:
    data = Path(path).read_bytes()
    if len(data) < 44 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise WavError(f"{path}: keine RIFF/WAVE-Datei")
    declared_riff = struct.unpack_from("<I", data, 4)[0]
    truncated = declared_riff + 8 != len(data)

    pos, fmt, payload = 12, None, None
    while pos + 8 <= len(data):
        kind, size = struct.unpack_from("<4sI", data, pos)
        body_at = pos + 8
        if kind == b"fmt ":
            fmt = struct.unpack_from("<HHIIHH", data, body_at)
        elif kind == b"data":
            end = body_at + size
            if size == 0 or end > len(data):
                end = len(data)          # Kopf nicht abgeschlossen
                truncated = True
            payload = data[body_at:end]
            break                        # data ist bei Dolphin der letzte Abschnitt
        pos = body_at + size + (size & 1)
    if fmt is None:
        raise WavError(f"{path}: fmt-Abschnitt fehlt")
    if payload is None:
        raise WavError(f"{path}: data-Abschnitt fehlt")
    audio_format, channels, rate, _byte_rate, _align, bits = fmt
    if audio_format != 1 or bits != 16:
        raise WavError(f"{path}: nur 16-Bit-PCM (Format {audio_format}, {bits} Bit)")
    if channels < 1:
        raise WavError(f"{path}: {channels} Kanaele")
    usable = len(payload) - (len(payload) % (2 * channels))
    samples = array.array("h")
    samples.frombytes(payload[:usable])
    if sys.byteorder == "big":
        samples.byteswap()
    return Wave(Path(path), rate, channels, bits, samples, truncated)


def write(path: Path, rate: int, channels: int, samples: array.array) -> None:
    """Schreibt eine 16-Bit-PCM-Datei (fuer Tests und Ausschnitte)."""
    body = samples.tobytes() if sys.byteorder == "little" else (
        lambda a: (a.byteswap(), a.tobytes())[1])(array.array("h", samples))
    header = struct.pack("<4sI4s4sIHHIIHH4sI", b"RIFF", 36 + len(body), b"WAVE",
                         b"fmt ", 16, 1, channels, rate, rate * channels * 2,
                         channels * 2, 16, b"data", len(body))
    Path(path).write_bytes(header + body)
