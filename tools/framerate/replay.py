"""DFF im FIFO-Player abspielen und Bilder ausgeben (kopflos, Vulkan auf Lavapipe).

    python tools/framerate replay <aufzeichnung.dff> --player <dolphin-emu-nogui> \
        --output <neues-verzeichnis> [--images N] [--timeout S]

Der Player ist DolphinNoGUI aus dem ModernGekko-Bau mit
``-DMODERNGEKKO_ENABLE_FIFO_REPLAY=ON`` (Dokument 05). Der Software-Renderer
ist unter Linux nicht nutzbar, weil ModernGekko EGL abschaltet und die
GL-Praesentation dann fehlt; Vulkan laeuft dagegen kopflos, hier mit Mesas
Lavapipe (mesa-vulkan-drivers). Der Player spielt die Datei in Schleife und
schreibt je Frame ein PNG nach user/Dump/Frames; nach N Bildern wird er
beendet. Ohne Schleife bricht der Player nach dem letzten Frame ab, bevor die
GPU alle Frames ausgegeben hat (gemessen: 1 von 3 Bildern), darum die Schleife.
"""

from __future__ import annotations

import os
import signal
import subprocess
import time
from pathlib import Path


class ReplayError(Exception):
    pass


def configure(user: Path) -> None:
    (user / "Config").mkdir(parents=True, exist_ok=True)
    (user / "Logs").mkdir(exist_ok=True)
    (user / "Config/Dolphin.ini").write_text(
        "[Core]\n[FifoPlayer]\nLoopReplay = True\n[Movie]\nDumpFrames = True\n"
        "[Interface]\nConfirmStop = False\n[Analytics]\nEnabled = False\nPermissionAsked = True\n")
    (user / "Config/GFX.ini").write_text(
        "[Settings]\nDumpFramesAsImages = True\nFrameDumpsResolutionType = 2\n"
        "[Hacks]\nImmediateXFBEnable = True\n")   # jede XFB-Kopie sofort ausgeben
    (user / "Config/Logger.ini").write_text(
        "[Options]\nWriteToFile = True\nWriteToConsole = False\nVerbosity = 3\n"
        "[Logs]\nVideo = True\nHost GPU = True\nFRAMEDUMP = True\nCORE = True\nBOOT = True\n")


def replay(dff: Path, player: Path, output: Path, images: int, timeout: float = 300,
           backend: str = "Vulkan") -> list[Path]:
    if output.exists():
        raise ReplayError(f"{output} existiert; Belege werden nicht ueberschrieben")
    user = output / "user"
    configure(user)
    frames = user / "Dump/Frames"
    frames.mkdir(parents=True)
    cmd = [str(player), "-p", "headless", "-u", str(user), "-v", backend, "-e", str(dff)]
    env = dict(os.environ)
    with (output / "stdout.log").open("w") as log:
        proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, env=env,
                                cwd=player.parent)
        deadline = time.monotonic() + timeout
        try:
            while time.monotonic() < deadline:
                if proc.poll() is not None:
                    break
                if len(list(frames.glob("framedump_*.png"))) >= images + 1:
                    break   # eins mehr: das letzte Bild koennte noch geschrieben werden
                time.sleep(0.2)
            else:
                raise ReplayError(f"Zeitueberschreitung nach {timeout} s "
                                  f"({len(list(frames.glob('framedump_*.png')))} Bilder)")
        finally:
            if proc.poll() is None:
                proc.send_signal(signal.SIGINT)
                try:
                    proc.wait(20)
                except subprocess.TimeoutExpired:
                    proc.kill()
    if proc.returncode not in (0, None) and len(list(frames.glob("framedump_*.png"))) < images:
        raise ReplayError(f"Player endete mit {proc.returncode}; siehe {output / 'stdout.log'}")
    found = sorted(frames.glob("framedump_*.png"), key=lambda p: int(p.stem.split("_")[1]))
    return found[:images]
