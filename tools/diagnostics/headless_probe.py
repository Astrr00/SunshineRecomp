"""Kopfloser Start der Laufzeit und Speicherabfrage ueber die Automation.

    python tools/diagnostics/headless_probe.py --runtime <moderngekko-run> \
        --game <extrahiertes-spiel> --module <modul> --output <neues-verzeichnis> \
        --read 0x8040CE48:4:arena-lo --read 0x8040E798:4:arena-hi --frames 600

Startet ``moderngekko-run --headless`` mit Null-Grafik, wartet die angegebene
Zahl Frames ab, liest die genannten Bereiche und beendet den Lauf regulaer.
Bilder gibt es kopflos nicht; der Zweck ist die Messung im RAM, etwa der
Arena-Grenzen (docs/09-DOL-BEFUNDE.md, offener Punkt).

Alles bleibt lokal. Das Verzeichnis darf noch nicht existieren, damit kein
frueherer Beleg ueberschrieben wird.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from automation import read_status, send  # noqa: E402


def wait_until(proc, predicate, timeout, what):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"Laufzeit endete ({proc.returncode}) waehrend: {what}")
        try:
            if predicate():
                return
        except (OSError, TimeoutError, KeyError, ValueError):
            pass
        time.sleep(0.1)
    raise TimeoutError(what)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--runtime", type=Path, required=True)
    p.add_argument("--game", type=Path, required=True)
    p.add_argument("--module", type=Path)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--frames", type=int, default=600,
                   help="Frames, die vor dem Lesen vergehen sollen")
    p.add_argument("--read", action="append", default=[],
                   metavar="ADRESSE:GROESSE:NAME")
    p.add_argument("--timeout", type=float, default=300)
    p.add_argument("--cheats-ini", type=Path,
                   help="lokale GameSettings/GMSE01.ini mit aktivierten Codes")
    p.add_argument("--sequence", type=Path,
                   help="JSON-Liste von pad_frames-Feldern, nach dem Warten "
                        "abgespielt (wie tests/fixtures/airstrip-camera.json)")
    p.add_argument("--audio-dump", action="store_true",
                   help="den emulierten Tonstrom als WAV nach user/Dump/Audio "
                        "schreiben ([DSP] DumpAudio; AudioCommon startet den "
                        "Mitschnitt beim Initialisieren des Tonstroms, also "
                        "auch beim Null-Backend)")
    p.add_argument("--uncapped", action="store_true",
                   help="Emulationsgeschwindigkeit aufheben ([Core] EmulationSpeed=0). "
                        "Nur so sagt die Wanduhr etwas ueber die Leistung eines Kerns; "
                        "gedrosselt laufen beide Kerne am selben Anschlag.")
    p.add_argument("--video-setting", action="append", default=[], metavar="SCHLUESSEL=WERT",
                   help="zusaetzliche Zeile im Abschnitt [Video] der config.ini "
                        "des Frontends, mehrfach moeglich (etwa scaler=nearest). "
                        "Anders als --core-setting geht das an ModernGekkos "
                        "eigene Einstellungen, nicht an Dolphins Dolphin.ini.")
    p.add_argument("--graphics", default="Null",
                   help="Grafik-Backend der Laufzeit; Null zeichnet nichts. Vulkan rendert "
                        "kopflos auf Lavapipe (docs/20, Schatten-EFB).")
    p.add_argument("--core-setting", action="append", default=[], metavar="SCHLUESSEL=WERT",
                   help="zusaetzliche Zeile im Abschnitt [Core] der Dolphin.ini, "
                        "mehrfach moeglich (etwa LargeEntryPointsMap=False). "
                        "Landet im Manifest, damit der Lauf nachvollziehbar bleibt.")
    p.add_argument("--jit", action="store_true",
                   help="ohne statisches Modul mit JIT64 laufen (Vergleichslauf); "
                        "--module wird dann nicht uebergeben")
    p.add_argument("--fifo", metavar="FRAMES",  type=int,
                   help="nach dem Warten so viele Frames als DFF aufzeichnen "
                        "(record_fifo aus dem FIFO-Patch; bis 120 erprobt)")
    args = p.parse_args()

    root = args.output.resolve()
    if root.exists():
        p.error("Ausgabeverzeichnis existiert; Belege werden nicht ueberschrieben")
    user, auto = root / "user", root / "auto"
    (user / "Config").mkdir(parents=True)
    # Das Frontend nimmt in config.ini nur Vulkan oder OpenGL an (Dok. 04);
    # kopflos setzt die Laufzeit den Null-Backend selbst (dolphin_runtime.cpp).
    for setting in args.video_setting:
        if "=" not in setting:
            p.error(f"--video-setting braucht SCHLUESSEL=WERT, nicht {setting!r}")
    (user / "config.ini").write_text(
        "[Video]\ninternal_scale=1\nbackend=Vulkan\nfullscreen=false\n"
        + "".join(f"{entry}\n" for entry in args.video_setting))
    # Dateilog, damit Codehandler, Boot und Core nachvollziehbar bleiben.
    (user / "Config/Logger.ini").write_text(
        "[Options]\nWriteToFile=True\nVerbosity=3\n"
        "[Logs]\nActionReplay=True\nBOOT=True\nCORE=True\nCOMMON=True\n"
        "Audio=True\nAudioInterface=True\nDSPHLE=True\n")
    for setting in args.core_setting:
        if "=" not in setting:
            p.error(f"--core-setting braucht SCHLUESSEL=WERT, nicht {setting!r}")
    (user / "Config/Dolphin.ini").write_text(
        f"[Core]\nEnableCheats={'True' if args.cheats_ini else 'False'}\n"
        + ("EmulationSpeed=0\n" if args.uncapped else "")
        + "".join(f"{s}\n" for s in args.core_setting)
        + ("[DSP]\nDumpAudio=True\n" if args.audio_dump else ""))
    # Bilder gibt es aus diesem Lauf nicht: Der Software-Renderer braucht eine
    # GL-Praesentation, die ModernGekko unter Linux abschaltet (ENABLE_EGL OFF),
    # und Vulkan kopflos bricht im Frontend mit einem ImGui-Assert ab (kein
    # Kontext). Bilder entstehen ueber die FIFO-Aufzeichnung und
    # tools/framerate/replay.py (dolphin-emu-nogui, Vulkan auf Lavapipe).
    if args.cheats_ini:
        (user / "GameSettings").mkdir()
        (user / "GameSettings/GMSE01.ini").write_bytes(args.cheats_ini.read_bytes())

    cmd = [str(args.runtime.resolve()), "--headless", "--game", str(args.game.resolve()),
           "--user-dir", str(user), "--automation-dir", str(auto),
           # Ein in config.ini gesetzter Backend gewinnt ueber den kopflosen
           # Null-Backend; deshalb ausdruecklich auf der Befehlszeile.
           "--graphics", args.graphics, "--audio", "Null"]
    static = bool(args.module) and not args.jit
    if static:
        cmd += ["--module", str(args.module.resolve())]
    else:
        # Ohne Modul weist die Laufzeit den Start ab ("no native module was
        # supplied"). Der Schalter waehlt nicht den Interpreter: SelectCPUCore
        # nimmt bei MODERNGEKKO_STATICRECOMP=0 unter x86-64 JIT64 (Dok. 04).
        cmd += ["--allow-interpreter"]
    env = dict(os.environ, MODERNGEKKO_STATICRECOMP="1" if static else "0")
    manifest = {"command": cmd, "reads": {}, "cpu": "static" if static else "jit64",
                "uncapped": bool(args.uncapped),
                "core_settings": list(args.core_setting),
                "video_settings": list(args.video_setting),
                "module_sha256": hashlib.sha256(args.module.read_bytes()).hexdigest()
                if static else None}

    with (root / "stdout.log").open("w") as out, (root / "stderr.log").open("w") as err:
        started = time.monotonic()
        proc = subprocess.Popen(cmd, env=env, stdout=out, stderr=err)
        manifest["pid"] = proc.pid
        try:
            wait_until(proc, lambda: read_status(auto).get("state") == "running",
                       args.timeout, "warten auf laufenden Core")
            manifest["status_at_start"] = read_status(auto)
            manifest["wall_at_start"] = round(time.monotonic() - started, 4)
            wait_until(proc, lambda: int(read_status(auto)["frame_count"]) >= args.frames,
                       args.timeout, f"warten auf Frame {args.frames}")
            if args.sequence:
                steps = json.loads(args.sequence.read_text())
                manifest["recordings"] = []
                for step in steps:
                    if "record" in step:
                        # {"record": FRAMES, "name": NAME}: FIFO-Aufzeichnung an
                        # dieser Stelle der Folge; das Spiel laeuft dabei weiter.
                        dff = auto / f"{step.get('name', len(manifest['recordings']))}.dff"
                        send(auto, "record_fifo",
                             [f"frames={step['record']}", f"path={dff}"], timeout=120)
                        wait_until(proc, lambda: dff.is_file() and dff.stat().st_size > 0,
                                   60, "warten auf die FIFO-Datei")
                        manifest["recordings"].append({
                            "path": str(dff), "frames": step["record"],
                            "bytes": dff.stat().st_size,
                            "sha256": hashlib.sha256(dff.read_bytes()).hexdigest()})
                        continue
                    send(auto, "pad_frames",
                         [f"{key}={value}" for key, value in step.items()], timeout=120)
                manifest["sequence"] = steps
            for spec in args.read:
                address, size, name = spec.split(":")
                address, size = int(address, 0), int(size, 0)
                path = auto / f"{name}.bin"
                send(auto, "read_memory", [f"address={address}", f"size={size}",
                                           f"path={path}"], timeout=30)
                data = path.read_bytes()
                entry = {"address": hex(address), "size": size, "hex": data.hex()}
                if size == 4:
                    entry["u32"] = hex(struct.unpack(">I", data)[0])
                manifest["reads"][name] = entry
            if args.fifo:
                dff = auto / "frames.dff"
                send(auto, "record_fifo", [f"frames={args.fifo}", f"path={dff}"],
                     timeout=120)
                wait_until(proc, lambda: dff.is_file() and dff.stat().st_size > 0,
                           60, "warten auf die FIFO-Datei")
                manifest["fifo"] = {"path": str(dff), "frames": args.fifo,
                                    "bytes": dff.stat().st_size,
                                    "sha256": hashlib.sha256(dff.read_bytes()).hexdigest()}
            manifest["status_at_end"] = read_status(auto)
            manifest["wall_at_end"] = round(time.monotonic() - started, 4)
            manifest["wall_seconds"] = round(manifest["wall_at_end"]
                                             - manifest["wall_at_start"], 4)
            manifest["frames_played"] = (int(manifest["status_at_end"]["frame_count"])
                                         - int(manifest["status_at_start"]["frame_count"]))
        except Exception as exc:  # noqa: BLE001 - alles landet im Manifest
            manifest["error"] = repr(exc)
        finally:
            if proc.poll() is None:
                try:
                    send(auto, "stop", [], timeout=15)
                    proc.wait(30)
                except Exception as exc:  # noqa: BLE001
                    manifest["shutdown_error"] = repr(exc)
                    proc.kill()
            manifest["exit_code"] = proc.poll()
            if args.audio_dump:
                # AudioCommon::StopAudioDump schreibt den WAV-Kopf erst beim
                # Herunterfahren des Tonstroms; darum erst nach proc.wait lesen.
                dumps = sorted((user / "Dump/Audio").glob("*.wav")) \
                    if (user / "Dump/Audio").is_dir() else []
                manifest["audio"] = [{"path": str(d), "bytes": d.stat().st_size,
                                      "sha256": hashlib.sha256(d.read_bytes()).hexdigest()}
                                     for d in dumps]
            (root / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps({k: manifest[k] for k in ("reads", "fifo", "recordings", "audio",
                                              "frames_played", "cpu", "exit_code")
                      if k in manifest} | {"error": manifest.get("error")}, indent=2))
    return 0 if "error" not in manifest else 1


if __name__ == "__main__":
    raise SystemExit(main())
