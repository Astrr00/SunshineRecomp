"""Read measured GMSE01 Rev 0 state through ModernGekko automation.

No game memory is modified. Boss addresses are explicit: a matching vtable
alone does not establish that an allocation is still part of the active scene.
"""
import argparse
import json
from pathlib import Path
import struct
import sys
import uuid

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT))
from scripts.automation import send, read_status


def snapshot(automation, game, boss_address=None):
    automation = Path(automation).resolve()
    boot = (Path(game) / "sys/boot.bin").read_bytes()
    if boot[:6] != b"GMSE01" or boot[7] != 0:
        raise ValueError("Only GMSE01 Rev 0 has been measured")
    status = read_status(automation)
    if status.get("game_id") != "GMSE01" or status.get("state") not in ("running", "paused"):
        raise ValueError("No running or paused GMSE01 core")
    output = automation / "telemetry" / uuid.uuid4().hex
    output.mkdir(parents=True)

    def read(address, size, name):
        if not 0x80000000 <= address < address + size <= 0x81800000:
            raise ValueError(f"Not a MEM1 range: {address:#x}+{size}")
        path = output / (name + ".bin")
        send(automation, "read_memory", [f"address={address}", f"size={size}", f"path={path}"])
        data = path.read_bytes()
        if len(data) != size:
            raise ValueError("Incomplete memory read")
        return data

    u32 = lambda data, offset=0: struct.unpack_from(">I", data, offset)[0]
    vec = lambda data, offset: struct.unpack_from(">3f", data, offset)
    mario = u32(read(0x8040E108, 4, "mario-pointer"))
    data = read(mario, 0x3E8, "mario")
    # Vtable measured in the supported revision, including independent cold boots.
    if u32(data) != 0x803DD660:
        raise ValueError("Mario allocation does not match the measured layout")
    result = {"frame_at_start": int(status["frame_count"]), "mario_address": hex(mario),
              "position": vec(data, 0x10), "yaw_degrees": struct.unpack_from(">f", data, 0x34)[0],
              "evidence": str(output), "core_state_at_start": status["state"]}
    gun = u32(data, 0x3E4)
    if gun:
        owner = u32(read(gun + 8, 4, "gun-owner"))
        if owner != mario:
            raise ValueError("Water gun owner does not point back to Mario")
        water = read(gun + 0x1C80, 8, "water")
        result["fludd"] = {"address": hex(gun), "water": struct.unpack_from(">i", water)[0],
                           "nozzle": water[4]}
    if boss_address is not None:
        boss = read(boss_address, 0x178, "boss")
        if u32(boss) != 0x803BB71C or u32(boss, 0x4C) != 0x10000022:
            raise ValueError("Boss type does not match the measured layout")
        head_address = u32(boss, 0x174)
        head = read(head_address, 0x74, "head")
        if u32(head, 0x68) != boss_address:
            raise ValueError("Boss head owner does not match")
        result["boss_candidate"] = {"address": hex(boss_address), "hp": boss[0x13C],
                                    "position": vec(boss, 0x10),
                                    "head_position": vec(head, 0x10),
                                    "head_vulnerable": bool(u32(head, 0x70))}
    (output / "snapshot.json").write_text(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--automation", required=True, type=Path)
    parser.add_argument("--game", type=Path, default=PROJECT / "build/game")
    parser.add_argument("--boss-address", type=lambda x: int(x, 0))
    args = parser.parse_args()
    print(json.dumps(snapshot(args.automation, args.game, args.boss_address), indent=2))
