"""Capture a local savestate with an explicit CPU/backend/configuration for visual comparison.

This is a diagnostic, not a graphics correctness test. Captures contain game
data and must remain local. Savestates can restore their original memory-card
paths, so a new output directory alone does not isolate card writes.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import time

from automation import send, read_status as read_automation_status


def read_status(root):
    path = root / "status.txt"
    if not path.exists():
        return {}
    return read_automation_status(root)


def wait_until(proc, predicate, timeout, description):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"Runtime exited ({proc.returncode}) while {description}")
        if predicate():
            return
        time.sleep(0.05)
    raise TimeoutError(description)


def main():
    project = Path(__file__).resolve().parent.parent
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True, help="New, unused directory")
    p.add_argument("--game", type=Path, default=project / "build/game")
    p.add_argument("--runtime", type=Path, default=project / "ref/ModernGekko/build/moderngekko-run.exe")
    p.add_argument("--state", type=Path, required=True)
    p.add_argument("--module", type=Path)
    p.add_argument("--cpu", choices=["static", "jit64"], default="static")
    p.add_argument("--backend", choices=["Vulkan", "OpenGL"], default="Vulkan")
    p.add_argument("--resolution", choices=["640x528", "1920x1080", "3840x2160"], default="640x528")
    p.add_argument("--game-settings", type=Path, help="Local GMSE01 INI overrides")
    p.add_argument("--sequence", type=Path, help="JSON list of pad_frames field dictionaries")
    p.add_argument("--minimum-frame", type=int, required=True,
                   help="Frame threshold confirming the expected savestate has loaded")
    args = p.parse_args()
    root = args.output.resolve()
    if root.exists():
        p.error("Output already exists; existing evidence must not be overwritten")
    if args.cpu == "static" and args.module is None:
        p.error("--cpu static requires --module")
    if args.cpu == "jit64" and args.module is not None:
        p.error("JIT64 comparison must not load a static module")
    for f in [args.runtime, args.state, args.module, args.game_settings, args.sequence]:
        if f is not None and not f.is_file():
            p.error(f"Missing file: {f}")
    sequence = json.loads(args.sequence.read_text()) if args.sequence else [{"frames": 60}]
    if not isinstance(sequence, list) or not all(isinstance(step, dict) for step in sequence):
        p.error("Sequence must be a JSON list of pad_frames field dictionaries")
    user, auto = root / "user", root / "auto"
    (user / "Config").mkdir(parents=True)
    (user / "config.ini").write_text(
        f"[Video]\nresolution={args.resolution}\nbackend={args.backend}\nfullscreen=false\n")
    (user / "Config/Dolphin.ini").write_text("[Core]\nEnableCheats=False\n")
    (user / "Config/GFX.ini").write_text(
        "[Settings]\nAspectRatio=5\nCustomAspectRatioWidth=4\n"
        "CustomAspectRatioHeight=3\nwideScreenHack=False\n")
    if args.game_settings:
        (user / "GameSettings").mkdir()
        (user / "GameSettings/GMSE01.ini").write_bytes(args.game_settings.read_bytes())
    command = [str(args.runtime.resolve()), "--game", str(args.game.resolve()),
               "--user-dir", str(user), "--automation-dir", str(auto),
               "--load-state", str(args.state.resolve())]
    if args.module:
        command += ["--module", str(args.module.resolve())]
    else:
        command += ["--allow-interpreter"]
    env = dict(os.environ, MODERNGEKKO_STATICRECOMP="1" if args.cpu == "static" else "0")
    manifest = {"command": command, "cpu_requested": args.cpu, "sequence": sequence,
                "state_sha256": hashlib.sha256(args.state.read_bytes()).hexdigest(),
                "warning": "Savestate-derived comparison; not an independent cold-boot reference"}
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2))
    with (root / "stdout.log").open("w") as stdout, (root / "stderr.log").open("w") as stderr:
        proc = subprocess.Popen(command, env=env, stdout=stdout, stderr=stderr,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        manifest["pid"] = proc.pid
        (root / "manifest.json").write_text(json.dumps(manifest, indent=2))
        try:
            def ready():
                s = read_status(auto)
                return s.get("state") == "running" and int(s.get("frame_count", "0")) >= args.minimum_frame
            wait_until(proc, ready, 90, "waiting for savestate readiness")
            for step in sequence:
                send(auto, "pad_frames", [f"{key}={value}" for key, value in step.items()], timeout=60)
            send(auto, "screenshot", ["path=frame.png"])
            # Screenshot acknowledgement is only a queued request. Let the frame dumper finish.
            send(auto, "pad_frames", ["frames=5"])
            shot = auto / "frame.png"
            wait_until(proc, lambda: shot.is_file(), 20, "waiting for PNG output")
            png = shot.read_bytes()
            if png[:8] != b"\x89PNG\r\n\x1a\n":
                raise RuntimeError("Invalid PNG signature")
            manifest.update(png_dimensions=struct.unpack(">II", png[16:24]),
                            png_sha256=hashlib.sha256(png).hexdigest(), status=read_status(auto))
        finally:
            if proc.poll() is None:
                try:
                    send(auto, "stop", [], timeout=10)
                    proc.wait(15)
                except (RuntimeError, TimeoutError, subprocess.TimeoutExpired) as exc:
                    # Keep a live handle recorded instead of silently killing/restarting work.
                    manifest["shutdown_error"] = str(exc)
            manifest["exit_code"] = proc.poll()
            (root / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(root / "auto/frame.png")


if __name__ == "__main__":
    main()
