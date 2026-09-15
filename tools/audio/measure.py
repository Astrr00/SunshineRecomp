"""Tonmitschnitte vermessen und vergleichen (WP1).

Ohne Fremdbibliotheken. Drei Fragen stehen im Vordergrund:

* **Tempo.** Wie viele Sekunden Ton entstehen je emuliertem Bild? Das
  beantwortet, ob die Zeitbasis richtig laeuft. Weil der Mitschnitt schon
  waehrend des Startvorgangs beginnt, der Bildzaehler aber erst spaeter, wird
  die Rate aus zwei verschieden langen Laeufen als Steigung bestimmt; der
  gemeinsame Startversatz faellt dabei heraus.
* **Tonhoehe.** Verschiebt sich das Spektrum zwischen zwei Laeufen? Dafuer
  gibt es eine schnelle Fourier-Transformation (Cooley-Tukey, Basis 2) und
  einen Vergleich ueber logarithmisch gestauchte Spektren.
* **Aussetzer.** Lueckenlose Stille mitten im Strom deutet auf Unterlaeufe.
"""

from __future__ import annotations

import array
import cmath
import math
from dataclasses import dataclass

import wav


# ---------------------------------------------------------------------------
# Huellkurve und Stille
# ---------------------------------------------------------------------------

def envelope(sound: wav.Wave, block_ms: float = 20.0) -> list[float]:
    """Effektivwert je Block, auf 1.0 bezogen (Vollausschlag 32768)."""
    block = max(1, int(sound.sample_rate * block_ms / 1000.0))
    mono = sound.mono()
    out = []
    for start in range(0, len(mono) - block + 1, block):
        total = 0
        for k in range(start, start + block):
            v = mono[k]
            total += v * v
        out.append(math.sqrt(total / block) / 32768.0)
    return out


def silence_runs(levels: list[float], threshold: float = 0.0005) -> list[tuple[int, int]]:
    """Zusammenhaengende Bloecke unter der Schwelle als (Start, Laenge)."""
    runs, start = [], None
    for i, level in enumerate(levels):
        if level < threshold:
            if start is None:
                start = i
        elif start is not None:
            runs.append((start, i - start))
            start = None
    if start is not None:
        runs.append((start, len(levels) - start))
    return runs


def clipped_share(sound: wav.Wave, limit: int = 32700) -> float:
    s = sound.samples
    return sum(1 for v in s if v >= limit or v <= -limit) / len(s) if s else 0.0


# ---------------------------------------------------------------------------
# Spektrum
# ---------------------------------------------------------------------------

def fft(values: list[complex]) -> list[complex]:
    """Iteratives Cooley-Tukey, Laenge muss eine Zweierpotenz sein."""
    n = len(values)
    if n & (n - 1):
        raise ValueError("Laenge muss eine Zweierpotenz sein")
    out = list(values)
    j = 0
    for i in range(1, n):                      # Bitumkehr
        bit = n >> 1
        while j & bit:
            j ^= bit
            bit >>= 1
        j |= bit
        if i < j:
            out[i], out[j] = out[j], out[i]
    length = 2
    while length <= n:
        step = -2j * math.pi / length
        half = length // 2
        for start in range(0, n, length):
            for k in range(half):
                w = cmath.exp(step * k)
                u = out[start + k]
                v = out[start + half + k] * w
                out[start + k] = u + v
                out[start + half + k] = u - v
        length <<= 1
    return out


def _hann(n: int) -> list[float]:
    return [0.5 - 0.5 * math.cos(2 * math.pi * k / (n - 1)) for k in range(n)]


def spectrum(sound: wav.Wave, size: int = 2048, windows: int = 24,
             skip_seconds: float = 0.0, span_seconds: float | None = None) -> list[float]:
    """Mittleres Betragsspektrum ueber gleichmaessig verteilte Fenster.

    Es werden nur Fenster mit Signal beruecksichtigt; reine Stille wuerde den
    Mittelwert verwaessern. Rueckgabe: ``size // 2`` Werte, auf die Summe 1
    normiert (dadurch vom Pegel unabhaengig).
    """
    mono = sound.mono()
    usable = len(mono) - size
    if usable <= 0:
        raise ValueError("Aufnahme kuerzer als ein Fenster")
    first = int(skip_seconds * sound.sample_rate)
    # Mit span_seconds liegen die Fenster an festen Zeitpunkten. Nur so lassen
    # sich zwei Aufnahmen vergleichen: sonst waeren die Fenster nach Anteil der
    # jeweiligen Laenge verteilt und traefen verschiedene Stellen der Musik.
    last = min(usable, first + int(span_seconds * sound.sample_rate)) \
        if span_seconds is not None else usable
    starts = [first + (last - first) * k // max(1, windows - 1)
              for k in range(windows)] if last > first else [0]
    window = _hann(size)
    total = [0.0] * (size // 2)
    used = 0
    for start in starts:
        chunk = mono[start:start + size]
        if len(chunk) < size:
            continue
        energy = sum(abs(v) for v in chunk)
        if energy < size * 8:                  # praktisch stumm
            continue
        spec = fft([complex(chunk[k] * window[k], 0.0) for k in range(size)])
        for k in range(size // 2):
            total[k] += abs(spec[k])
        used += 1
    if not used:
        raise ValueError("kein Fenster mit Signal gefunden")
    scale = sum(total)
    return [v / scale for v in total] if scale else total


def centroid(spec: list[float], rate: int, size: int) -> float:
    """Spektraler Schwerpunkt in Hertz."""
    bin_hz = rate / size
    weight = sum(spec)
    return sum(v * k * bin_hz for k, v in enumerate(spec)) / weight if weight else 0.0


def pitch_ratio(a: list[float], b: list[float], rate_a: int, rate_b: int, size: int,
                span: float = 0.25, steps: int = 101) -> tuple[float, float]:
    """Frequenzverhaeltnis zwischen zwei Spektren durch Verschiebung.

    Rueckgabe: um welchen Faktor ``b`` hoeher klingt als ``a``, samt
    Aehnlichkeit (0 bis 1) beim besten Faktor. 1.0 bedeutet gleiche Tonhoehe,
    2.0 eine Oktave hoeher. Die Suche laeuft logarithmisch ueber plus/minus
    ``span`` Oktaven; ein Verhaeltnis am Rand des Suchbereichs heisst, dass der
    wahre Wert ausserhalb liegen kann.
    """
    def value(spec, rate, hz):
        pos = hz / (rate / size)
        i = int(pos)
        if i < 0 or i + 1 >= len(spec):
            return 0.0
        frac = pos - i
        return spec[i] * (1 - frac) + spec[i + 1] * frac

    probes = [80.0 * (2 ** (k / 24.0)) for k in range(24 * 7)]   # 80 Hz bis ~10 kHz
    best, best_score = 1.0, -1.0
    for step in range(steps):
        r = 2 ** (span * (2 * step / (steps - 1) - 1))
        va = [value(a, rate_a, hz * r) for hz in probes]
        vb = [value(b, rate_b, hz) for hz in probes]
        na, nb = math.sqrt(sum(v * v for v in va)), math.sqrt(sum(v * v for v in vb))
        if na <= 0 or nb <= 0:
            continue
        score = sum(x * y for x, y in zip(va, vb)) / (na * nb)
        if score > best_score:
            best, best_score = r, score
    # Gesucht wurde a(hz * r) gegen b(hz): ein hoeher klingendes b findet sich
    # bei kleinem r. Nach aussen gilt die natuerliche Leserichtung b zu a.
    return 1.0 / best, best_score


def identical_prefix(a: wav.Wave, b: wav.Wave) -> tuple[int, float]:
    """Wie weit sind zwei Aufnahmen abtastwertgleich, und wie hoch ist der
    Anteil gleicher Abtastwerte insgesamt?

    Rueckgabe (Abtastwerte je Kanal bis zur ersten Abweichung, Anteil 0 bis 1).
    Zwei Laeufe desselben Spiels mit verschiedenen CPU-Kernen muessen hier
    uebereinstimmen, wenn die Emulation deterministisch ist; das ist der
    schaerfste Vergleich, den es ohne Hoerprobe gibt.
    """
    sa, sb = a.samples, b.samples
    n = min(len(sa), len(sb))
    first = n
    for i in range(n):
        if sa[i] != sb[i]:
            first = i
            break
    same = sum(1 for i in range(n) if sa[i] == sb[i])
    channels = max(1, a.channels)
    return first // channels, (same / n if n else 0.0)


def best_lag(a: list[float], b: list[float], max_lag: int = 50) -> tuple[int, float]:
    """Versatz in Bloecken, bei dem zwei Huellkurven am besten uebereinstimmen.

    Rueckgabe (Versatz, Korrelation). Positiver Versatz heisst: ``b`` beginnt
    um so viele Bloecke spaeter als ``a``.
    """
    def correlate(shift: int) -> float:
        x = a[max(0, -shift):]
        y = b[max(0, shift):]
        n = min(len(x), len(y))
        if n < 8:
            return -1.0
        mx, my = sum(x[:n]) / n, sum(y[:n]) / n
        cov = sum((x[i] - mx) * (y[i] - my) for i in range(n))
        vx = math.sqrt(sum((x[i] - mx) ** 2 for i in range(n)))
        vy = math.sqrt(sum((y[i] - my) ** 2 for i in range(n)))
        return cov / (vx * vy) if vx > 0 and vy > 0 else -1.0

    best, score = 0, -2.0
    for shift in range(-max_lag, max_lag + 1):
        value = correlate(shift)
        if value > score:
            best, score = shift, value
    return best, score


# ---------------------------------------------------------------------------
# Tempo aus zwei Laeufen
# ---------------------------------------------------------------------------

@dataclass
class Slope:
    seconds_per_frame: float
    frames_per_second: float
    offset_seconds: float        # Ton vor dem ersten gezaehlten Bild
    short: tuple[int, float]
    long: tuple[int, float]

    def as_dict(self) -> dict:
        return {"seconds_per_frame": round(self.seconds_per_frame, 8),
                "frames_per_second": round(self.frames_per_second, 4),
                "offset_seconds": round(self.offset_seconds, 4),
                "short": [self.short[0], round(self.short[1], 4)],
                "long": [self.long[0], round(self.long[1], 4)]}


def slope(short_frames: int, short_seconds: float,
          long_frames: int, long_seconds: float) -> Slope:
    """Sekunden Ton je Bild als Steigung zweier Laeufe.

    Der Mitschnitt beginnt in beiden Laeufen beim gleichen Startvorgang, also
    mit demselben konstanten Versatz; die Differenz beseitigt ihn.
    """
    if long_frames == short_frames:
        raise ValueError("Die beiden Laeufe brauchen verschiedene Bildzahlen")
    spf = (long_seconds - short_seconds) / (long_frames - short_frames)
    return Slope(spf, 1.0 / spf if spf else float("inf"),
                 short_seconds - spf * short_frames,
                 (short_frames, short_seconds), (long_frames, long_seconds))
