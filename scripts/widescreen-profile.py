"""Create an isolated experimental GMSE01 16:9 profile from local Dolphin settings."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path, help="New, unused user directory")
    parser.add_argument("--copy-saves-from", type=Path)
    args = parser.parse_args()
    project = Path(__file__).resolve().parent.parent
    source = project / "ref/ModernGekko/vendor/dolphin/Data/Sys/GameSettings/GMSE01.ini"
    ini = source.read_text(encoding="utf-8")
    # Use the pinned local code, never download code or game data.
    code = ini.split("$Widescreen [gamemasterplc]\n", 1)[1].split("$60FPS", 1)[0].strip()
    root = args.destination.resolve()
    if root.exists():
        parser.error("Destination already exists; choose a new test profile")
    if args.copy_saves_from and not (args.copy_saves_from / "GC").is_dir():
        parser.error("Source profile has no GC save directory")
    (root / "Config").mkdir(parents=True)
    (root / "GameSettings").mkdir()
    (root / "config.ini").write_text(
        "[Video]\nresolution=1920x1080\nbackend=Vulkan\nfullscreen=false\n"
        "show_fps_in_title=true\n", encoding="utf-8")
    (root / "Config/Dolphin.ini").write_text("[Core]\nEnableCheats=True\n", encoding="utf-8")
    (root / "Config/GFX.ini").write_text(
        "[Settings]\nAspectRatio=5\nCustomAspectRatioWidth=16\n"
        "CustomAspectRatioHeight=9\nwideScreenHack=False\n", encoding="utf-8")
    (root / "GameSettings/GMSE01.ini").write_text(
        "[Gecko]\n$SunshineRecomp Experimental 16:9 [gamemasterplc]\n" + code +
        "\n\n[Gecko_Enabled]\n$SunshineRecomp Experimental 16:9\n", encoding="utf-8")
    if args.copy_saves_from:
        shutil.copytree(args.copy_saves_from / "GC", root / "GC")
    (root / "widescreen-source.json").write_text(json.dumps({
        "source": str(source.relative_to(project)),
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "revision": "GMSE01 Rev 0",
        "experimental": True,
        "limitations": "FMV, complete HUD coverage, culling and ultrawide not validated",
    }, indent=2), encoding="utf-8")
    print(root)


if __name__ == "__main__":
    main()
