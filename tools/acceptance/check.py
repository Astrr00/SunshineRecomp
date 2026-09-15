"""Prueft das Manifest eines Laufs gegen die Zusagen eines Szenarios (WP6).

Die Pruefung ist von der Ausfuehrung getrennt: ``run.py`` startet den Lauf und
schreibt ein Manifest, dieses Modul entscheidet ueber bestanden oder nicht.
Dadurch laesst sich die Entscheidungslogik ohne Spielkopie testen, und ein
alter Lauf laesst sich nachtraeglich gegen geaenderte Zusagen pruefen.

Ein Szenario ist JSON:

    {
      "name": "boot",
      "frames": 600,
      "sequence": "fixtures/game-start.json",   // optional
      "reads": ["0x8040CE48:4:arena-lo"],       // optional
      "expect": {
        "exit_code": 0,
        "min_frames": 500,
        "no_error": true,
        "smc_failed": 0,
        "reads": {"arena-lo": "0x817feec0",
                  "mario": ["0x80000000", "0x81800000"]},   // Bereich statt Wert
        "audio_seconds_per_present": [0.0110, 0.0113],
        "audio_min_seconds": 5.0,
        "audio_max_silence_share": 0.95
      }
    }

Jede Zusage unter ``expect`` ist freiwillig; fehlt sie, wird sie nicht
geprueft. Das haelt Szenarien ehrlich: Es steht genau das drin, was wirklich
zugesagt wird.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

SHUTDOWN = re.compile(
    r"shutdown: native=(?P<native>\d+) fallback=(?P<fallback>\d+) "
    r"native_exc=(?P<native_exc>\d+) hook_fb=(?P<hook_fb>\d+) "
    r"smc_failed=(?P<smc_failed>\d+) verifications=(?P<verifications>\d+) "
    r"reverify_events=(?P<reverify>\d+) bursts=(?P<bursts>\d+) cycles=(?P<cycles>\d+)")


@dataclass
class Result:
    name: str
    checks: list[tuple[str, bool, str]] = field(default_factory=list)

    def add(self, what: str, ok: bool, detail: str = "") -> None:
        self.checks.append((what, ok, detail))

    @property
    def passed(self) -> bool:
        return all(ok for _, ok, _ in self.checks)

    def as_dict(self) -> dict:
        return {"name": self.name, "passed": self.passed,
                "checks": [{"check": w, "ok": ok, "detail": d} for w, ok, d in self.checks]}


def counters(stderr: str) -> dict | None:
    """Die Zaehlerzeile des statischen Kerns, falls vorhanden."""
    match = None
    for match in SHUTDOWN.finditer(stderr):
        pass
    return {k: int(v) for k, v in match.groupdict().items()} if match else None


def _in_range(value: float, bounds: list) -> bool:
    return bounds[0] <= value <= bounds[1]


def check(scenario: dict, manifest: dict, stderr: str = "",
          audio: dict | None = None) -> Result:
    """``audio``: optional {"seconds": float, "silent_share": float}."""
    expect = scenario.get("expect", {})
    result = Result(scenario.get("name", "unbenannt"))

    if "exit_code" in expect:
        got = manifest.get("exit_code")
        result.add(f"Exitcode {expect['exit_code']}", got == expect["exit_code"], f"war {got}")
    if expect.get("no_error"):
        error = manifest.get("error")
        result.add("kein Fehler im Manifest", not error, str(error or ""))
    if "min_frames" in expect:
        start = manifest.get("status_at_start", {})
        end = manifest.get("status_at_end", {})
        try:
            frames = int(end["frame_count"]) - int(start["frame_count"])
        except (KeyError, TypeError, ValueError):
            result.add(f"mindestens {expect['min_frames']} Bilder", False, "Zaehler fehlen")
        else:
            result.add(f"mindestens {expect['min_frames']} Bilder",
                       frames >= expect["min_frames"], f"waren {frames}")
    if "reads" in expect:
        got = manifest.get("reads", {})
        for name, want in expect["reads"].items():
            entry = got.get(name)
            if entry is None:
                result.add(f"Lesung {name}", False, "fehlt im Manifest")
            elif isinstance(want, list):
                # Zwei Werte heissen Bereich. Fuer Zeiger ist das ehrlicher als
                # ein fester Wert: Belegt werden soll, dass das Objekt im
                # Arbeitsspeicher liegt, nicht wo genau.
                have = entry.get("u32")
                low, high = (int(str(b), 0) for b in want)
                try:
                    value = int(str(have), 0)
                except (TypeError, ValueError):
                    result.add(f"Lesung {name} in [{want[0]}, {want[1]}]", False,
                               f"kein Wort: {have}")
                else:
                    result.add(f"Lesung {name} in [{want[0]}, {want[1]}]",
                               low <= value <= high, f"war {have}")
            else:
                have = entry.get("u32", entry.get("hex"))
                result.add(f"Lesung {name} = {want}", str(have) == str(want), f"war {have}")

    found = counters(stderr)
    if "smc_failed" in expect:
        if found is None:
            result.add(f"smc_failed = {expect['smc_failed']}", False, "keine Zaehlerzeile")
        else:
            result.add(f"smc_failed = {expect['smc_failed']}",
                       found["smc_failed"] == expect["smc_failed"],
                       f"war {found['smc_failed']}")
    if "max_fallback" in expect:
        if found is None:
            result.add("Interpreter-Rueckfaelle", False, "keine Zaehlerzeile")
        else:
            result.add(f"hoechstens {expect['max_fallback']} Interpreter-Rueckfaelle",
                       found["fallback"] <= expect["max_fallback"], f"waren {found['fallback']}")

    if audio is not None:
        if "audio_min_seconds" in expect:
            result.add(f"mindestens {expect['audio_min_seconds']} s Ton",
                       audio["seconds"] >= expect["audio_min_seconds"],
                       f"waren {audio['seconds']:.2f} s")
        if "audio_max_silence_share" in expect:
            result.add(f"hoechstens {expect['audio_max_silence_share']:.0%} Stille",
                       audio["silent_share"] <= expect["audio_max_silence_share"],
                       f"waren {audio['silent_share']:.1%}")
        if "audio_seconds_per_present" in expect:
            start = manifest.get("status_at_start", {})
            end = manifest.get("status_at_end", {})
            try:
                presents = int(end["present_count"]) - int(start["present_count"])
            except (KeyError, TypeError, ValueError):
                presents = 0
            bounds = expect["audio_seconds_per_present"]
            if presents <= 0:
                result.add("Ton je Bildausgabe", False, "keine Bildausgaben gezaehlt")
            else:
                # Der Mitschnitt beginnt vor dem ersten gezaehlten Bild; der
                # Startversatz macht den Wert hier groesser als die reine
                # Steigung aus zwei Laeufen (tools/audio rate). Die Schranken
                # eines Szenarios muessen das beruecksichtigen.
                value = audio["seconds"] / presents
                result.add(f"Ton je Bildausgabe in [{bounds[0]}, {bounds[1]}] s",
                           _in_range(value, bounds), f"war {value:.6f} s")
    elif any(k.startswith("audio_") for k in expect):
        result.add("Tonmitschnitt vorhanden", False, "kein Mitschnitt im Lauf")

    if not result.checks:
        result.add("Szenario sagt etwas zu", False, "expect ist leer")
    return result
