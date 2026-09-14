"""Symbolliste fuer GMSE01 pruefen und nach DolRecomps MAP-Format wandeln.

    python tools/symbols check
    python tools/symbols convert --to build/GMSE01.map
    python tools/symbols verify --dol build/game/sys/main.dol

``check`` und ``convert`` brauchen keine Spieldaten. ``verify`` liest die
``main.dol`` der eigenen Spielkopie und gibt nur Zaehlwerte aus.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "common"))

import dol as dolfile  # noqa: E402
import symbolmap  # noqa: E402

HERE = Path(__file__).resolve().parent
DEFAULT_MAP = HERE / "gmse01-bettersunshineengine.map"

# Angeheftete Herkunft; Einzelheiten in tools/symbols/README.md.
EXPECTED_SHA256 = "62eec2cb40ac19ccf2cddabffd37cca2e34761684c6bca250c7dc3f7d83a2c40"

# Adressen, die in diesem Projekt unabhaengig von der Symbolliste am laufenden
# Spiel gemessen wurden. Stimmen die Namen dazu, passt die Liste zu genau
# dieser Revision -- und die eigene Messung wird zugleich bestaetigt.
PROBES = [
    (0x8000522C, "__start", "Eintrittspunkt laut moderngekko-port inspect (Dok. 02)"),
    (0x8040E108, "gpMarioAddress", "Mario-Objektzeiger (Dok. 06)"),
    (0x8040E10C, "gpMarioPos", "Mario-Positionszeiger (Dok. 06)"),
    (0x803DD660, "__vt__6TMario", "Mario-Vtable (Dok. 06)"),
    (0x803BB71C, "__vt__17TBiancoGateKeeper", "Boss-Vtable (Dok. 06)"),
    (0x80404454, "mPadStatus__10JUTGamePad", "Pad-Status (Dok. 04)"),
]


def _load(path: Path) -> symbolmap.ConversionReport:
    report = symbolmap.read(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if path == DEFAULT_MAP and digest != EXPECTED_SHA256:
        print(f"  Warnung      : Pruefsumme weicht ab.\n"
              f"                 erwartet  {EXPECTED_SHA256}\n"
              f"                 vorhanden {digest}", file=sys.stderr)
    return report


def _print_report(report: symbolmap.ConversionReport) -> None:
    print(f"  Zeilen       : {report.total_lines} ({report.blank_lines} leer)")
    print(f"  Uebernommen  : {len(report.accepted)}")
    print(f"  Verworfen    : {report.skipped_count}")
    for reason, entries in sorted(report.skipped.items()):
        print(f"    {len(entries):>5}  {reason}")
        for entry in entries[:3]:
            print(f"           {entry}")
        if len(entries) > 3:
            print(f"           ... und {len(entries) - 3} weitere")


def _probe(report: symbolmap.ConversionReport) -> int:
    """Vergleicht die Liste mit den eigenen Messungen. Gibt die Treffer zurueck."""
    names_at: dict[int, set[str]] = {}
    for symbol in report.accepted:
        names_at.setdefault(symbol.address, set()).add(symbol.name)

    hits = 0
    print("\n  Abgleich mit eigenen Messungen am laufenden Spiel:")
    for address, expected, source in PROBES:
        found = names_at.get(address, set())
        if expected in found:
            hits += 1
            print(f"    0x{address:08X}  passt     {expected}")
        elif found:
            print(f"    0x{address:08X}  ABWEICHUNG erwartet {expected}, "
                  f"gefunden {', '.join(sorted(found))}")
        else:
            print(f"    0x{address:08X}  FEHLT     {expected}")
        print(f"                          {source}")
    print(f"    {hits} von {len(PROBES)} bestaetigt")
    return hits


def command_check(args: argparse.Namespace) -> int:
    print(f"Pruefe {args.map} ...")
    report = _load(args.map)
    _print_report(report)

    collisions = symbolmap.identifier_collisions(report.accepted)
    distinct = {k: v for k, v in collisions.items()
                if len({s.name for s in v}) > 1}
    print(f"\n  Bezeichner-Kollisionen: {len(collisions)}")
    print(f"    davon verschiedene Namen: {len(distinct)} "
          f"(Unterstriche zusammengezogen oder bei "
          f"{symbolmap.IDENTIFIER_BUFFER - 1} Zeichen abgeschnitten)")
    print("    DolRecomp haengt in diesen Faellen die Adresse an den Namen an.")
    for identifier, found in list(distinct.items())[:3]:
        print(f"      {identifier[:60]}: {', '.join(sorted({s.name for s in found}))[:90]}")

    hits = _probe(report)
    return 0 if hits == len(PROBES) else 1


def command_convert(args: argparse.Namespace) -> int:
    print(f"Wandle {args.map} ...")
    report = _load(args.map)
    _print_report(report)
    args.to.parent.mkdir(parents=True, exist_ok=True)
    args.to.write_text(symbolmap.to_dolrecomp(report.accepted), encoding="utf-8")
    print(f"\n  Geschrieben  : {args.to}")
    print(f"  Aufruf       : dolrecomp --map \"{args.to}\" ...")
    return 0


def command_verify(args: argparse.Namespace) -> int:
    print(f"Pruefe {args.map} gegen {args.dol} ...")
    report = _load(args.map)
    binary = dolfile.read(args.dol)

    print(f"\n  DOL          : {len(binary.data):,} Bytes, "
          f"{len(binary.sections)} Sektionen "
          f"({len(binary.text_sections)} ausfuehrbar)")
    print(f"  Eintritt     : 0x{binary.entry:08X}")
    print(f"  BSS          : 0x{binary.bss_address:08X}, {binary.bss_size:,} Bytes")
    slots = dolfile.free_text_slots(binary)
    print(f"  Freie Text-Plaetze im Kopf: {len(slots)} {slots if slots else ''}")

    findings: list[str] = []

    start = [s for s in report.accepted if s.name == "__start"]
    if not start:
        findings.append("Die Liste enthaelt kein __start.")
    elif start[0].address != binary.entry:
        findings.append(
            f"__start steht bei 0x{start[0].address:08X}, das DOL nennt als "
            f"Eintritt 0x{binary.entry:08X}. Die Liste gehoert zu einer anderen "
            f"Fassung.")
    else:
        print(f"\n  __start stimmt mit dem Eintrittspunkt ueberein "
              f"(0x{binary.entry:08X}).")

    in_text = [s.address for s in report.accepted
               if (section := binary.section_of(s.address)) is not None
               and section.executable]
    in_data = sum(1 for s in report.accepted
                  if (section := binary.section_of(s.address)) is not None
                  and not section.executable)
    outside = len(report.accepted) - len(in_text) - in_data
    print(f"  In Textsektionen : {len(in_text)}")
    print(f"  In Datensektionen: {in_data}")
    print(f"  Ausserhalb (BSS oder unbelegt): {outside}")
    if not in_text:
        findings.append("Kein Symbol faellt in eine Textsektion. DolRecomp "
                        "wuerde die Liste mit \"symbol map has no executable "
                        "entries\" abweisen.")

    symbols = dolfile.measure(binary, in_text)
    control = dolfile.measure(binary, dolfile.control_sample(binary, len(in_text)))
    print("\n  Stichprobe gegen Zufallskontrolle (gleiche Anzahl, gleiche Sektionen):")
    print(f"    {'':<26}{'Symbole':>10}{'Zufall':>10}")
    print(f"    {'gemessen':<26}{symbols.sampled:>10}{control.sampled:>10}")
    print(f"    {'Funktionsprolog':<26}"
          f"{symbols.share(symbols.prologue):>9.1%}"
          f"{control.share(control.prologue):>10.1%}")
    print(f"    {'Terminator davor':<26}"
          f"{symbols.share(symbols.preceded_by_terminator):>9.1%}"
          f"{control.share(control.preceded_by_terminator):>10.1%}")
    print("    Deutlich hoehere Symbolwerte sind ein Indiz fuer echte "
          "Funktionsgrenzen,")
    print("    kein Beweis der Uebereinstimmung mit dieser Spielkopie.")

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps({
            "dol": str(args.dol),
            "dol_sha256": hashlib.sha256(binary.data).hexdigest(),
            "map": str(args.map),
            "map_sha256": hashlib.sha256(args.map.read_bytes()).hexdigest(),
            "entry": f"0x{binary.entry:08X}",
            "free_text_slots": slots,
            "symbols_total": len(report.accepted),
            "symbols_in_text": len(in_text),
            "symbols_in_data": in_data,
            "symbols_outside": outside,
            "prologue_share": {"symbols": symbols.share(symbols.prologue),
                               "control": control.share(control.prologue)},
            "terminator_share": {
                "symbols": symbols.share(symbols.preceded_by_terminator),
                "control": control.share(control.preceded_by_terminator)},
            "findings": findings,
        }, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\n  Bericht      : {args.report}")

    if findings:
        print("\nBefunde:", file=sys.stderr)
        for finding in findings:
            print(f"  - {finding}", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python tools/symbols",
                                     description=__doc__.split("\n\n")[0])
    parser.add_argument("--map", type=Path, default=DEFAULT_MAP,
                        help="Symbolliste (Vorgabe: die angeheftete Fassung)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    check = subparsers.add_parser(
        "check", help="Liste pruefen und mit den eigenen Messungen abgleichen")
    check.set_defaults(handler=command_check)

    convert = subparsers.add_parser(
        "convert", help="nach DolRecomps MAP-Format schreiben")
    convert.add_argument("--to", type=Path, default=Path("build/GMSE01.map"))
    convert.set_defaults(handler=command_convert)

    verify = subparsers.add_parser(
        "verify", help="gegen die main.dol der eigenen Spielkopie pruefen")
    verify.add_argument("--dol", type=Path, required=True)
    verify.add_argument("--report", type=Path,
                        help="Befund zusaetzlich als JSON ablegen")
    verify.set_defaults(handler=command_verify)

    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except (symbolmap.SymbolMapError, dolfile.DolError) as error:
        print(f"\nFehler: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
