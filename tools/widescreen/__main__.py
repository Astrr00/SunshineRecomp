"""Spielseitigen Gecko-Code vor der Recompilation in das DOL bringen.

    python tools/widescreen inspect --ini <GMSE01.ini>
    python tools/widescreen plan    --ini <GMSE01.ini> --dol build/game/sys/main.dol
    python tools/widescreen bake    --ini <GMSE01.ini> --dol build/game/sys/main.dol \
                                    --to build/patched-main.dol

``inspect`` braucht keine Spieldaten. ``plan`` und ``bake`` lesen die
``main.dol`` der eigenen Spielkopie. Es wird nichts an der Spielkopie
veraendert; ``bake`` schreibt eine neue Datei.

Das Ergebnis ist Eingabe fuer DolRecomp, kein Ersatz fuer die Abnahme am
laufenden Spiel. Siehe docs/PLAN.md, WP8.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "common"))

import bake as baker  # noqa: E402
import dol as dolfile  # noqa: E402
import gecko  # noqa: E402

DEFAULT_CODE = "Widescreen"


def _load_code(args: argparse.Namespace) -> gecko.GeckoCode:
    text = args.ini.read_text(encoding="utf-8", errors="replace")
    return gecko.parse(text, args.code, args.section)


def _describe(code: gecko.GeckoCode) -> None:
    print(f"  Code         : {code.name}")
    print(f"  Schreiben    : {len(code.writes)}")
    print(f"  Einfuegungen : {len(code.injections)}")
    if code.unsupported:
        print(f"  Nicht unterstuetzt: {len(code.unsupported)}")
        for entry in code.unsupported:
            print(f"    {entry}")


def command_inspect(args: argparse.Namespace) -> int:
    text = args.ini.read_text(encoding="utf-8", errors="replace")
    if args.list:
        print(f"Codes im Abschnitt [{args.section}] von {args.ini}:")
        for name in gecko.list_codes(text, args.section):
            print(f"  {name}")
        return 0

    code = gecko.parse(text, args.code, args.section)
    print(f"{args.ini}\n")
    _describe(code)

    placeholders = {injection.placeholder for injection in code.injections}
    if code.injections:
        print(f"\n  Letztes Wort jeder Einfuegung: "
              f"{', '.join(f'0x{value:08X}' for value in sorted(placeholders))}")
        print("  Dieses Wort ersetzt der Codehandler durch den Ruecksprung;")
        print("  es gehoert nicht zum Nutzcode (belegt in docs/03-WIDESCREEN.md).")
        if placeholders - {0}:
            print("  Warnung: Nicht alle Platzhalter sind 0. Bitte pruefen, ob "
                  "hier Nutzcode verworfen wuerde.")

    print("\n  Direktes Schreiben:")
    for write in code.writes:
        print(f"    0x{write.address:08X} = 0x{write.value:08X}")
    print("\n  Einfuegungen:")
    for injection in code.injections:
        print(f"    0x{injection.address:08X}  {len(injection.body):>3} Worte "
              f"Rumpf, zurueck nach 0x{injection.returns_to:08X}")
    return 0


def _print_map(binary: dolfile.Dol) -> None:
    print("\n  Speicherbelegung laut DOL-Kopf:")
    for region in dolfile.memory_map(binary):
        print(f"    0x{region.start:08X}-0x{region.end:08X}  "
              f"{region.end - region.start:>9,} Bytes  {region.label}")
    holes = dolfile.gaps(binary)
    if holes:
        print("\n  Luecken dazwischen:")
        for hole in holes:
            print(f"    0x{hole.start:08X}-0x{hole.end:08X}  "
                  f"{hole.end - hole.start:>9,} Bytes  {hole.label}")
    else:
        print("\n  Keine Luecken zwischen den geladenen Bereichen.")


def command_plan(args: argparse.Namespace) -> int:
    code = _load_code(args)
    binary = dolfile.read(args.dol)
    print(f"{args.ini}\n{args.dol}\n")
    _describe(code)

    print(f"\n  DOL          : {len(binary.data):,} Bytes, "
          f"{len(binary.sections)} Sektionen, Eintritt 0x{binary.entry:08X}")
    slots = dolfile.free_text_slots(binary)
    print(f"  Freie Textsektions-Plaetze: {len(slots)} {slots if slots else ''}")
    if not slots:
        print("    Ohne freien Platz kann kein Codebereich angelegt werden.")

    usable, unusable = baker.classify_writes(binary, code)
    print(f"\n  Schreibziele in der Datei : {len(usable)}")
    for write, where in usable:
        print(f"    0x{write.address:08X} = 0x{write.value:08X}   {where}")
    if unusable:
        print(f"\n  Schreibziele ausserhalb der Datei: {len(unusable)}")
        for write, why in unusable:
            print(f"    0x{write.address:08X} = 0x{write.value:08X}   {why}")
        print("    Diese Werte lassen sich nicht einbacken. Sie gehoeren in "
              "einen Mod,")
        print("    der sie beim Start setzt (docs/PLAN.md, WP9).")

    _print_map(binary)

    if code.injections:
        needed = sum(len(injection.body) + 1 for injection in code.injections) * 4
        proposal = baker.default_cave_address(binary)
        print(f"\n  Codebereich  : {needed:,} Bytes noetig")
        print(f"  Vorschlag    : 0x{proposal:08X} (hinter allem, was das DOL belegt)")
        print("    Der DOL-Kopf kennt den Heap des Spiels nicht. Ob diese "
              "Adresse")
        print("    dauerhaft frei bleibt, zeigt erst der Lauf. Mit "
              "--cave-address")
        print("    laesst sich stattdessen eine Luecke von oben waehlen.")
    return 0


def command_bake(args: argparse.Namespace) -> int:
    code = _load_code(args)
    binary = dolfile.read(args.dol)
    original = hashlib.sha256(binary.data).hexdigest()
    print(f"Backe \"{code.name}\" in {args.dol} ...")
    print(f"  Quelle SHA-256: {original}")

    data, report = baker.bake(binary, code, args.cave_address)

    print(f"\n  Geschrieben  : {len(report.writes_applied)} von "
          f"{len(code.writes)}")
    if report.writes_rejected:
        print(f"  Abgelehnt    : {len(report.writes_rejected)}")
        for write, why in report.writes_rejected:
            print(f"    0x{write.address:08X} = 0x{write.value:08X}   {why}")
    if report.placements:
        print(f"  Codebereich  : 0x{report.cave_address:08X}, "
              f"{report.cave_words} Worte für {len(report.placements)} "
              f"Einfuegungen")
        for placement in report.placements:
            target = placement.injection.address
            print(f"    0x{target:08X} -> 0x{placement.address:08X}"
                  f"-0x{placement.end:08X}   verdraengt "
                  f"0x{report.replaced_instructions.get(target, 0):08X}")
    print(f"  Nachgeprueft : {report.verified_words} Worte neu eingelesen "
          f"und verglichen")

    if report.problems:
        print(f"\n  Befunde ({len(report.problems)}):", file=sys.stderr)
        for problem in report.problems:
            print(f"    {problem}", file=sys.stderr)

    if not report.ok:
        print("\nNichts geschrieben: Das Ergebnis waere unvollstaendig.",
              file=sys.stderr)
        return 1

    args.to.parent.mkdir(parents=True, exist_ok=True)
    args.to.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    print(f"\n  Geschrieben  : {args.to}")
    print(f"  Ergebnis SHA-256: {digest}")

    if args.onframe:
        args.onframe.parent.mkdir(parents=True, exist_ok=True)
        args.onframe.write_text(
            baker.onframe_section(report.writes_applied, code.name),
            encoding="utf-8")
        print(f"  [OnFrame]-Form der {len(report.writes_applied)} Schreibungen: "
              f"{args.onframe}")

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps({
            "ini": str(args.ini),
            "code": code.name,
            "source_dol": str(args.dol),
            "source_sha256": original,
            "output_dol": str(args.to),
            "output_sha256": digest,
            "cave_address": f"0x{report.cave_address:08X}",
            "cave_words": report.cave_words,
            "writes_applied": [
                {"address": f"0x{w.address:08X}", "value": f"0x{w.value:08X}",
                 "section": where} for w, where in report.writes_applied],
            "writes_rejected": [
                {"address": f"0x{w.address:08X}", "value": f"0x{w.value:08X}",
                 "reason": why} for w, why in report.writes_rejected],
            "injections": [
                {"target": f"0x{p.injection.address:08X}",
                 "cave": f"0x{p.address:08X}",
                 "words": len(p.words),
                 "replaced": f"0x{report.replaced_instructions.get(p.injection.address, 0):08X}",
                 "returns_to": f"0x{p.injection.returns_to:08X}"}
                for p in report.placements],
            "verified_words": report.verified_words,
            "limits": [
                "Nachgeprueft ist nur die Datei, nicht das Verhalten im Spiel.",
                "Die Adresse des Codebereichs ist gegen den DOL-Kopf geprueft, "
                "nicht gegen den Heap des Spiels.",
            ],
        }, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"  Bericht      : {args.report}")

    print("\n  Geprueft ist damit die Datei, nicht das Spiel. Die Abnahme "
          "verlangt")
    print("  weiterhin den RAM-Vergleich gegen die Gecko-Fassung und den "
          "Nachweis,")
    print("  dass der SMC-Rueckfall der betroffenen Bereiche im Log "
          "verschwindet.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python tools/widescreen",
                                     description=__doc__.split("\n\n")[0])
    parser.add_argument("--ini", type=Path, required=True,
                        help="Dolphin-Spiel-INI mit dem Code, etwa GMSE01.ini")
    parser.add_argument("--code", default=DEFAULT_CODE,
                        help=f"Name des Codes (Vorgabe: {DEFAULT_CODE})")
    parser.add_argument("--section", default="Gecko",
                        help="INI-Abschnitt (Vorgabe: Gecko)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect = subparsers.add_parser("inspect", help="Code lesen und auflisten")
    inspect.add_argument("--list", action="store_true",
                         help="nur die Namen aller Codes zeigen")
    inspect.set_defaults(handler=command_inspect)

    plan = subparsers.add_parser(
        "plan", help="gegen die eigene main.dol einordnen, nichts schreiben")
    plan.add_argument("--dol", type=Path, required=True)
    plan.set_defaults(handler=command_plan)

    bake_command = subparsers.add_parser(
        "bake", help="geaendertes DOL erzeugen und nachpruefen")
    bake_command.add_argument("--dol", type=Path, required=True)
    bake_command.add_argument("--to", type=Path, required=True)
    bake_command.add_argument("--cave-address", type=lambda x: int(x, 0),
                              help="Adresse des Codebereichs (Vorgabe: hinter "
                                   "allem, was das DOL belegt)")
    bake_command.add_argument("--onframe", type=Path,
                              help="die direkten Schreibungen zusaetzlich in "
                                   "moderngekko-ports [OnFrame]-Form ablegen")
    bake_command.add_argument("--report", type=Path,
                              help="Befund zusaetzlich als JSON ablegen")
    bake_command.set_defaults(handler=command_bake)

    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except (gecko.GeckoError, dolfile.DolError) as error:
        print(f"\nFehler: {error}", file=sys.stderr)
        return 2
    except OSError as error:
        print(f"\nFehler: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
