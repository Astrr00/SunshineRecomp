"""Abnahmelauf (WP6, PLAN 2.5): Szenario starten und gegen seine Zusagen pruefen.

    python tools/acceptance run <szenario.json> --runtime <moderngekko-run> \
        --game <extrahiertes-spiel> --module <modul> --output <neues-verzeichnis>
    python tools/acceptance check <szenario.json> --run <laufverzeichnis>
    python tools/acceptance list

``run`` startet den Lauf ueber tools/diagnostics/headless_probe.py und prueft
anschliessend. ``check`` prueft ein bereits vorhandenes Laufverzeichnis, etwa
nach einer Aenderung der Zusagen. Beide geben einen Bericht aus und enden mit
Exitcode 1, wenn eine Zusage nicht gehalten wurde.

Kein Szenario enthaelt Spieldaten: Es nennt Eingabefolgen, Adressen und
Schranken. Der Lauf selbst bleibt lokal.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "audio"))

import check as checker  # noqa: E402


def audio_summary(manifest: dict) -> dict | None:
    entries = [a for a in manifest.get("audio", []) if "_dspdump" in Path(a["path"]).name]
    if not entries:
        return None
    try:
        import measure
        import wav
    except ImportError:
        return None
    path = Path(entries[0]["path"])
    if not path.is_file():
        return None
    sound = wav.read(path)
    levels = measure.envelope(sound, 100.0)
    silent = sum(n for _, n in measure.silence_runs(levels))
    return {"seconds": sound.seconds,
            "silent_share": silent / len(levels) if levels else 1.0,
            "sample_rate": sound.sample_rate}


def load(path: Path) -> dict:
    scenario = json.loads(path.read_text())
    for required in ("name", "frames", "expect"):
        if required not in scenario:
            raise SystemExit(f"{path}: Feld '{required}' fehlt")
    return scenario


def execute(scenario: dict, base: Path, args) -> int:
    probe = Path(__file__).resolve().parents[1] / "diagnostics" / "headless_probe.py"
    cmd = [sys.executable, str(probe), "--runtime", str(args.runtime),
           "--game", str(args.game), "--output", str(args.output),
           "--frames", str(scenario["frames"]),
           "--timeout", str(scenario.get("timeout", 900))]
    if args.module:
        cmd += ["--module", str(args.module)]
    if args.jit:
        cmd += ["--jit"]
    if scenario.get("sequence"):
        cmd += ["--sequence", str((base / scenario["sequence"]).resolve())]
    for spec in scenario.get("reads", []):
        cmd += ["--read", spec]
    if any(k.startswith("audio_") for k in scenario["expect"]):
        cmd += ["--audio-dump"]
    print(f"  Lauf: {' '.join(Path(c).name if '/' in c else c for c in cmd[1:])}")
    return subprocess.call(cmd, stdout=subprocess.DEVNULL)


def report(result: checker.Result, path: Path | None) -> int:
    print(f"\n  Szenario {result.name}: "
          f"{'BESTANDEN' if result.passed else 'NICHT BESTANDEN'}")
    for what, ok, detail in result.checks:
        print(f"    [{'ok ' if ok else 'FEHL'}] {what}" + (f"  ({detail})" if detail else ""))
    if path:
        path.write_text(json.dumps(result.as_dict(), indent=2))
        print(f"  Bericht: {path}")
    return 0 if result.passed else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python tools/acceptance",
                                     description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    r = sub.add_parser("run")
    r.add_argument("scenario", type=Path)
    r.add_argument("--runtime", type=Path, required=True)
    r.add_argument("--game", type=Path, required=True)
    r.add_argument("--module", type=Path)
    r.add_argument("--jit", action="store_true")
    r.add_argument("--output", type=Path, required=True)
    r.add_argument("--report", type=Path)
    c = sub.add_parser("check")
    c.add_argument("scenario", type=Path)
    c.add_argument("--run", type=Path, required=True, dest="run_dir")
    c.add_argument("--report", type=Path)
    sub.add_parser("list")
    args = parser.parse_args(argv)

    if args.command == "list":
        for path in sorted(HERE.glob("*.json")):
            scenario = json.loads(path.read_text())
            print(f"  {path.name:24} {scenario.get('name','')}: "
                  f"{len(scenario.get('expect', {}))} Zusagen, {scenario['frames']} Bilder")
        return 0

    scenario = load(args.scenario)
    run_dir = args.output if args.command == "run" else args.run_dir
    if args.command == "run":
        code = execute(scenario, args.scenario.resolve().parent, args)
        if code != 0:
            print(f"  Hinweis: die Sonde endete mit {code}; es wird trotzdem geprueft")
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.is_file():
        print(f"Fehler: {manifest_path} fehlt", file=sys.stderr)
        return 2
    manifest = json.loads(manifest_path.read_text())
    stderr_path = run_dir / "stderr.log"
    stderr = stderr_path.read_text(errors="replace") if stderr_path.is_file() else ""
    result = checker.check(scenario, manifest, stderr, audio_summary(manifest))
    return report(result, args.report)


if __name__ == "__main__":
    raise SystemExit(main())
