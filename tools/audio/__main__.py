"""Tonmitschnitte vermessen (WP1, docs/PLAN.md Abschnitt 4).

    python tools/audio inspect <mitschnitt.wav> [...]
    python tools/audio compare <a.wav> <b.wav> [--report <json>]
    python tools/audio rate --run <manifest.json> --run <manifest.json> [--stream dsp|dtk]

``inspect`` nennt Format, Laenge, Pegel, Stille und spektralen Schwerpunkt.
``compare`` stellt zwei Mitschnitte gegenueber: Laengenverhaeltnis,
Tonhoehenverhaeltnis und Aehnlichkeit der Spektren.
``rate`` bestimmt aus zwei verschieden langen Laeufen desselben Aufbaus, wie
viel Ton je emuliertem Bild entsteht. Bezugsgroesse ist ``present_count``
(Bildausgaben, also VI-Felder), nicht ``frame_count``: letzteres zaehlt nur
eindeutige Bilder und haengt am Spielinhalt (VideoEvents.h).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import measure  # noqa: E402
import wav  # noqa: E402

SIZE = 2048


def load_run(manifest: Path, stream: str) -> dict:
    data = json.loads(manifest.read_text())
    dumps = [d for d in data.get("audio", []) if f"_{stream}dump" in Path(d["path"]).name]
    if not dumps:
        raise SystemExit(f"{manifest}: kein {stream}-Mitschnitt im Manifest")
    start, end = data["status_at_start"], data["status_at_end"]
    sound = wav.read(Path(dumps[0]["path"]))
    return {"manifest": manifest, "cpu": data.get("cpu"), "wave": sound,
            "presents": int(end["present_count"]) - int(start["present_count"]),
            "presents_total": int(end["present_count"]),
            "frames": int(end["frame_count"]) - int(start["frame_count"]),
            "seconds": sound.seconds, "sha256": dumps[0]["sha256"]}


def describe(sound: wav.Wave) -> dict:
    levels = measure.envelope(sound)
    runs = measure.silence_runs(levels)
    block_ms = 20.0
    longest = max((n for _, n in runs), default=0)
    spec = None
    try:
        spec = measure.spectrum(sound, SIZE)
    except ValueError:
        pass
    return {"path": str(sound.path), "sample_rate": sound.sample_rate,
            "channels": sound.channels, "frames": sound.frames,
            "seconds": round(sound.seconds, 4),
            "truncated_header": sound.truncated_header,
            "peak": max((abs(v) for v in sound.samples), default=0) / 32768.0,
            "rms": round(sum(levels) / len(levels), 6) if levels else 0.0,
            "silent_share": round(sum(n for _, n in runs) / len(levels), 4) if levels else None,
            "longest_silence_ms": round(longest * block_ms, 1),
            "clipped_share": round(measure.clipped_share(sound), 6),
            "centroid_hz": round(measure.centroid(spec, sound.sample_rate, SIZE), 1)
            if spec else None}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python tools/audio",
                                     description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    i = sub.add_parser("inspect")
    i.add_argument("wavs", nargs="+", type=Path)
    i.add_argument("--report", type=Path)
    c = sub.add_parser("compare")
    c.add_argument("a", type=Path)
    c.add_argument("b", type=Path)
    c.add_argument("--report", type=Path)
    r = sub.add_parser("rate")
    r.add_argument("--run", action="append", type=Path, required=True,
                   metavar="MANIFEST", help="zweimal angeben: kurzer und langer Lauf")
    r.add_argument("--stream", default="dsp", choices=("dsp", "dtk"))
    r.add_argument("--report", type=Path)
    args = parser.parse_args(argv)

    if args.command == "inspect":
        out = []
        for path in args.wavs:
            d = describe(wav.read(path))
            out.append(d)
            print(f"{path.name}: {d['sample_rate']} Hz, {d['channels']} Kanaele, "
                  f"{d['frames']:,} Abtastwerte, {d['seconds']:.3f} s"
                  + (", KOPF UNVOLLSTAENDIG" if d["truncated_header"] else ""))
            print(f"  Spitze {d['peak']:.3f}, Effektivwert {d['rms']:.5f}, Stille "
                  f"{d['silent_share']:.1%} (laengste {d['longest_silence_ms']:.0f} ms), "
                  f"uebersteuert {d['clipped_share']:.4%}, Schwerpunkt "
                  + (f"{d['centroid_hz']:.0f} Hz" if d["centroid_hz"] else "-"))
        result = out
    elif args.command == "compare":
        a, b = wav.read(args.a), wav.read(args.b)
        # Erst zeitlich ausrichten: Zwei Laeufe starten nicht auf denselben
        # Abtastwert, und ein Spektrenvergleich an verschobenen Stellen misst
        # den Inhaltsunterschied, nicht die Tonhoehe.
        block_ms = 50.0
        ea, eb = measure.envelope(a, block_ms), measure.envelope(b, block_ms)
        lag, lag_score = measure.best_lag(ea, eb)
        skip_a = max(0.0, -lag) * block_ms / 1000.0
        skip_b = max(0.0, lag) * block_ms / 1000.0
        overlap = min(a.seconds - skip_a, b.seconds - skip_b)
        prefix, same_share = measure.identical_prefix(a, b)
        prefix_seconds = prefix / a.sample_rate if a.sample_rate else 0.0
        windows = 64
        sa = measure.spectrum(a, SIZE, windows, skip_seconds=skip_a, span_seconds=overlap)
        sb = measure.spectrum(b, SIZE, windows, skip_seconds=skip_b, span_seconds=overlap)
        ratio, score = measure.pitch_ratio(sa, sb, a.sample_rate, b.sample_rate, SIZE)
        result = {"a": describe(a), "b": describe(b),
                  "alignment": {"lag_blocks": lag, "block_ms": block_ms,
                                "envelope_correlation": round(lag_score, 5),
                                "overlap_seconds": round(overlap, 3)},
                  "identical_prefix_seconds": round(prefix_seconds, 4),
                  "identical_sample_share": round(same_share, 5),
                  "length_ratio": round(b.seconds / a.seconds, 6) if a.seconds else None,
                  "pitch_ratio": round(ratio, 5), "spectral_similarity": round(score, 5),
                  "centroid_hz": [round(measure.centroid(sa, a.sample_rate, SIZE), 1),
                                  round(measure.centroid(sb, b.sample_rate, SIZE), 1)],
                  "centroid_ratio": round(
                      measure.centroid(sb, b.sample_rate, SIZE)
                      / measure.centroid(sa, a.sample_rate, SIZE), 5)}
        print(f"  Laengen: {a.seconds:.3f} s gegen {b.seconds:.3f} s "
              f"(Verhaeltnis {result['length_ratio']:.4f})")
        print(f"  Ausrichtung: Versatz {lag * block_ms:+.0f} ms, Huellkurven-Korrelation "
              f"{lag_score:.4f}, gemeinsamer Bereich {overlap:.1f} s")
        print(f"  Abtastwertgleich: die ersten {prefix_seconds:.3f} s "
              f"({prefix_seconds / min(a.seconds, b.seconds):.1%} der kuerzeren Aufnahme), "
              f"insgesamt {same_share:.2%} gleiche Abtastwerte")
        print(f"  Tonhoehe: Verhaeltnis {ratio:.4f} ({1200 * __import__('math').log2(ratio):+.0f} Cent), "
              f"Aehnlichkeit der Spektren {score:.3f}")
        print(f"  Schwerpunkt im gemeinsamen Bereich: "
              f"{measure.centroid(sa, a.sample_rate, SIZE):.0f} Hz gegen "
              f"{measure.centroid(sb, b.sample_rate, SIZE):.0f} Hz "
              f"(Verhaeltnis {result['centroid_ratio']:.4f})")
    else:
        if len(args.run) != 2:
            parser.error("rate braucht genau zwei --run")
        runs = sorted((load_run(p, args.stream) for p in args.run),
                      key=lambda r: r["presents"])
        short, long = runs
        s = measure.slope(short["presents"], short["seconds"],
                          long["presents"], long["seconds"])
        result = {"stream": args.stream, "cpu": short["cpu"],
                  "runs": [{"manifest": str(r["manifest"]), "presents": r["presents"],
                            "frames": r["frames"], "seconds": round(r["seconds"], 4),
                            "sample_rate": r["wave"].sample_rate,
                            "sha256": r["sha256"]} for r in runs],
                  "slope": s.as_dict()}
        print(f"  {args.stream}-Strom, {short['cpu']}: "
              f"{short['presents']} Bildausgaben / {short['seconds']:.3f} s gegen "
              f"{long['presents']} / {long['seconds']:.3f} s")
        print(f"  Ton je Bildausgabe: {s.seconds_per_frame * 1000:.4f} ms "
              f"= {s.frames_per_second:.4f} Bildausgaben je Sekunde Ton "
              f"(Startversatz {s.offset_seconds:.3f} s)")
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2, default=str))
        print(f"  Bericht: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
