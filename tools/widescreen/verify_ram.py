"""Widescreen-Code im RAM eines laufenden Spiels nachpruefen.

    python tools/widescreen/verify_ram.py reads --ini <GMSE01.ini> [--cave 0x80417800]
    python tools/widescreen/verify_ram.py check --ini <GMSE01.ini> --manifest <manifest.json> \
        [--cave 0x80417800]

``reads`` gibt die ``--read``-Argumente fuer ``tools/diagnostics/headless_probe.py``
aus, ``check`` bewertet dessen Manifest. Zwei Varianten:

* **Gecko** (ohne ``--cave``): Die 13 Schreibungen muessen im RAM stehen, an
  jeder Einfuegestelle muss ein Sprung stehen, und der angesprungene Rumpf muss
  bytegenau der INI entsprechen -- so wie in docs/03-WIDESCREEN.md.
* **Eingebacken** (mit ``--cave``): dasselbe, nur dass der Sprung in den
  eigenen Codebereich fuehren und dort Rumpf plus Ruecksprung stehen muss.

Es wird nur gelesen; nichts wird in das Spiel geschrieben.
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "common"))

import bake as baker  # noqa: E402
import dol as dolfile  # noqa: E402
import gecko  # noqa: E402


def _decode_branch(word: int, at: int) -> int | None:
    if (word >> 26) != 18 or (word & 3) != 0:
        return None
    offset = word & 0x03FFFFFC
    if offset & 0x02000000:
        offset -= 0x04000000
    return at + offset


# Dolphins Codehandler legt die Ruempfe der Einfuegungen in seinem eigenen
# Bereich ab; ein Fenster darueber genuegt, um sie ueber die Sprungziele zu finden.
HANDLER_WINDOW = (0x80001800, 0x1800)


def reads(code: gecko.GeckoCode, cave: int | None) -> list[str]:
    out = [f"0x{w.address:08X}:4:write-{i}" for i, w in enumerate(code.writes)]
    out += [f"0x{inj.address:08X}:4:site-{i}" for i, inj in enumerate(code.injections)]
    if cave is None:
        out.append(f"0x{HANDLER_WINDOW[0]:08X}:{HANDLER_WINDOW[1]}:handler")
    if cave is not None:
        placements = baker.layout(code, cave)
        total = sum(len(p.words) for p in placements) * 4
        out.append(f"0x{cave:08X}:{total}:cave")
    return out


def check(code: gecko.GeckoCode, manifest: dict, cave: int | None,
          extra_reads: dict) -> list[str]:
    got = manifest["reads"]
    problems: list[str] = []

    for i, w in enumerate(code.writes):
        actual = int(got[f"write-{i}"]["u32"], 16)
        if actual != w.value:
            problems.append(f"0x{w.address:08X}: 0x{actual:08X} statt 0x{w.value:08X}")

    placements = baker.layout(code, cave) if cave is not None else None
    cave_bytes = bytes.fromhex(got["cave"]["hex"]) if cave is not None else b""

    for i, inj in enumerate(code.injections):
        word = int(got[f"site-{i}"]["u32"], 16)
        target = _decode_branch(word, inj.address)
        if target is None:
            problems.append(f"Einfuegestelle 0x{inj.address:08X}: kein Sprung (0x{word:08X})")
            continue
        if cave is None:
            # Gecko: Rumpf liegt beim Codehandler; wird ueber extra_reads geliefert.
            body = extra_reads.get(f"body-{i}")
            if body is None and "handler" in got:
                window = bytes.fromhex(got["handler"]["hex"])
                start = target - HANDLER_WINDOW[0]
                if 0 <= start < len(window):
                    body = window[start:]
            if body is None:
                problems.append(f"Einfuegestelle 0x{inj.address:08X}: Rumpf bei "
                                f"0x{target:08X} nicht gelesen")
                continue
            expected = b"".join(struct.pack(">I", w) for w in inj.body)
            if body[:len(expected)] != expected:
                problems.append(f"Rumpf von 0x{inj.address:08X} weicht ab")
        else:
            placement = placements[i]
            if target != placement.address:
                problems.append(f"Einfuegestelle 0x{inj.address:08X} springt nach "
                                f"0x{target:08X}, erwartet 0x{placement.address:08X}")
                continue
            start = placement.address - cave
            expected = b"".join(struct.pack(">I", w) for w in placement.words)
            if cave_bytes[start:start + len(expected)] != expected:
                problems.append(f"Codebereich fuer 0x{inj.address:08X} weicht ab")
    return problems


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("action", choices=["reads", "check"])
    p.add_argument("--ini", type=Path, required=True)
    p.add_argument("--code", default="Widescreen")
    p.add_argument("--cave", type=lambda x: int(x, 0))
    p.add_argument("--manifest", type=Path)
    p.add_argument("--bodies", type=Path,
                   help="Gecko-Variante: Verzeichnis mit body-<i>.bin der "
                        "angesprungenen Ruempfe")
    args = p.parse_args()
    code = gecko.parse(args.ini.read_text(errors="replace"), args.code)

    if args.action == "reads":
        print(" ".join(f"--read {r}" for r in reads(code, args.cave)))
        return 0

    manifest = json.loads(args.manifest.read_text())
    extra = {}
    if args.bodies:
        for f in args.bodies.glob("body-*.bin"):
            extra[f.stem] = f.read_bytes()
    problems = check(code, manifest, args.cave, extra)
    variant = "eingebacken" if args.cave is not None else "Gecko"
    n = len(code.writes) + len(code.injections)
    if problems:
        print(f"{variant}: {len(problems)} Abweichung(en) von {n} Stellen")
        for q in problems:
            print("  " + q)
        return 1
    print(f"{variant}: alle {n} Stellen stimmen "
          f"({len(code.writes)} Schreibungen, {len(code.injections)} Einfuegungen)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
