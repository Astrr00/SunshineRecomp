"""Gecko-Code vor der Recompilation in das DOL bringen.

Der Weg ueber Dolphins Codehandler funktioniert (docs/03-WIDESCREEN.md), hat
aber einen Preis: Die geaenderten Codebereiche gelten der Laufzeit als
selbstmodifizierend und laufen im Interpreter statt nativ. Steht die Aenderung
dagegen schon im DOL, rekompiliert DolRecomp sie mit.

Was hier passiert:

* **Direktes Schreiben (04).** Das Wort wird an seine Stelle in der Datei
  geschrieben. Adressen in BSS gehen nicht -- BSS steht nicht im DOL. Solche
  Werte bleiben Sache eines Mods zur Laufzeit; sie werden gemeldet, nicht
  stillschweigend uebergangen.
* **Einfuegung (C2).** Der Rumpf kommt in einen neuen Codebereich, an der
  Zieladresse steht danach ein Sprung dorthin, und am Ende des Rumpfes ein
  Ruecksprung nach Ziel+4. Das ist dasselbe Ergebnis, das der Codehandler zur
  Laufzeit herstellt.

Die Wahl der Adresse fuer den Codebereich ist die heikle Stelle: Der DOL-Kopf
kennt nur die geladenen Sektionen und BSS, nicht den Heap des Spiels. Dass eine
Luecke dauerhaft frei bleibt, kann dieses Werkzeug nicht wissen. Es prueft
deshalb nur gegen das Bekannte und sagt das auch.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import dol as dolfile
from gecko import GeckoCode, Injection, Write


@dataclass
class Placement:
    """Wo die Einfuegung eines Codes im neuen Codebereich liegt."""
    injection: Injection
    address: int
    words: tuple[int, ...]

    @property
    def end(self) -> int:
        return self.address + len(self.words) * 4


@dataclass
class BakeReport:
    cave_address: int = 0
    cave_words: int = 0
    writes_applied: list[tuple[Write, str]] = field(default_factory=list)
    writes_rejected: list[tuple[Write, str]] = field(default_factory=list)
    placements: list[Placement] = field(default_factory=list)
    replaced_instructions: dict[int, int] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)
    verified_words: int = 0

    @property
    def ok(self) -> bool:
        return not self.problems and not self.writes_rejected


def classify_writes(binary: dolfile.Dol, code: GeckoCode
                    ) -> tuple[list[tuple[Write, str]], list[tuple[Write, str]]]:
    """Teilt die Schreibziele in "steht in der Datei" und "steht nicht darin"."""
    usable: list[tuple[Write, str]] = []
    unusable: list[tuple[Write, str]] = []
    for write in code.writes:
        section = binary.section_of(write.address)
        if section is not None and write.address + 4 <= section.end:
            usable.append((write, f"{'text' if section.executable else 'data'}"
                                  f"{section.index}"))
        elif (binary.bss_size and binary.bss_address <= write.address
              < binary.bss_address + binary.bss_size):
            unusable.append((write, "BSS -- steht nicht in der Datei"))
        else:
            unusable.append((write, "ausserhalb aller Sektionen"))
    return usable, unusable


def default_cave_address(binary: dolfile.Dol) -> int:
    """Erster ausgerichteter Platz hinter allem, was das DOL belegt.

    Bewusst konservativ und bewusst nicht als sicher ausgegeben: Hinter BSS
    beginnt ueblicherweise der Heap des Spiels.
    """
    regions = dolfile.memory_map(binary)
    highest = max(region.end for region in regions)
    alignment = dolfile.SECTION_ALIGNMENT
    return (highest + alignment - 1) // alignment * alignment


def layout(code: GeckoCode, cave_address: int) -> list[Placement]:
    """Verteilt die Einfuegungen hintereinander in den Codebereich."""
    placements: list[Placement] = []
    cursor = cave_address
    for injection in code.injections:
        # Der Ruecksprung steht an der Stelle, die der Codehandler zur Laufzeit
        # ueberschreibt: hinter dem Rumpf.
        return_at = cursor + len(injection.body) * 4
        words = tuple(injection.body) + (
            dolfile.branch(return_at, injection.returns_to),)
        placements.append(Placement(injection=injection, address=cursor,
                                    words=words))
        cursor += len(words) * 4
    return placements


def bake(binary: dolfile.Dol, code: GeckoCode,
         cave_address: int | None = None) -> tuple[bytes, BakeReport]:
    """Erzeugt das geaenderte DOL und prueft anschliessend jedes Wort nach."""
    report = BakeReport()
    builder = dolfile.DolBuilder(binary)

    usable, unusable = classify_writes(binary, code)
    report.writes_rejected = unusable

    targets = {injection.address for injection in code.injections}
    for write, _ in usable:
        if write.address in targets:
            report.problems.append(
                f"0x{write.address:08X} ist zugleich Schreibziel und "
                f"Einfuegestelle. Das laesst sich nicht beides einbacken.")

    seen: dict[int, int] = {}
    for write, where in usable:
        if write.address in seen and seen[write.address] != write.value:
            report.problems.append(
                f"0x{write.address:08X} wird zweimal mit verschiedenen Werten "
                f"geschrieben (0x{seen[write.address]:08X}, 0x{write.value:08X}).")
        seen[write.address] = write.value
        try:
            builder.write_word(write.address, write.value)
            report.writes_applied.append((write, where))
        except dolfile.DolError as error:
            report.problems.append(str(error))

    if code.injections:
        report.cave_address = (default_cave_address(binary)
                               if cave_address is None else cave_address)
        report.placements = layout(code, report.cave_address)
        words: list[int] = []
        for placement in report.placements:
            words.extend(placement.words)
        report.cave_words = len(words)
        try:
            builder.append_text_section(report.cave_address, words)
        except dolfile.DolError as error:
            report.problems.append(str(error))
            return builder.to_bytes(), report

        for placement in report.placements:
            target = placement.injection.address
            original = builder.read_word(target)
            if original is None:
                report.problems.append(
                    f"Die Einfuegestelle 0x{target:08X} liegt in keiner "
                    f"Sektion der Datei.")
                continue
            section = builder.section_of(target)
            if section is not None and not section.executable:
                # Ein Sprung in einer Datensektion waere kein eingefuegter Code,
                # sondern ein veraenderter Wert. Dann stimmt etwas anderes nicht.
                report.problems.append(
                    f"Die Einfuegestelle 0x{target:08X} liegt in Datensektion "
                    f"{section.index}, nicht in ausfuehrbarem Code. Passen INI "
                    f"und DOL zusammen?")
                continue
            report.replaced_instructions[target] = original
            try:
                builder.write_word(target,
                                   dolfile.branch(target, placement.address))
            except dolfile.DolError as error:
                report.problems.append(str(error))

    data = builder.to_bytes()
    _verify(data, code, report)
    return data, report


def _verify(data: bytes, code: GeckoCode, report: BakeReport) -> None:
    """Liest das Ergebnis neu ein und vergleicht jedes geaenderte Wort.

    Absichtlich ueber den frischen Leser statt ueber den Zwischenstand: So
    prueft der Vergleich auch, dass der Sektionskopf stimmt.
    """
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "patched.dol"
        path.write_bytes(data)
        try:
            result = dolfile.read(path)
        except dolfile.DolError as error:
            report.problems.append(f"Das erzeugte DOL ist unlesbar: {error}")
            return

    checked = 0
    for write, _ in report.writes_applied:
        actual = result.word_at(write.address)
        if actual != write.value:
            report.problems.append(
                f"Nachpruefung: 0x{write.address:08X} traegt "
                f"0x{actual if actual is not None else 0:08X} statt "
                f"0x{write.value:08X}.")
        checked += 1

    for placement in report.placements:
        target = placement.injection.address
        expected = dolfile.branch(target, placement.address)
        actual = result.word_at(target)
        if actual != expected:
            report.problems.append(
                f"Nachpruefung: Die Einfuegestelle 0x{target:08X} traegt "
                f"0x{actual if actual is not None else 0:08X} statt des "
                f"Sprungs 0x{expected:08X}.")
        checked += 1
        for index, word in enumerate(placement.words):
            address = placement.address + index * 4
            actual = result.word_at(address)
            if actual != word:
                report.problems.append(
                    f"Nachpruefung: 0x{address:08X} im Codebereich traegt "
                    f"0x{actual if actual is not None else 0:08X} statt "
                    f"0x{word:08X}.")
            checked += 1
    report.verified_words = checked


def onframe_section(writes: list[tuple[Write, str]], name: str) -> str:
    """Die direkten Schreibungen in der Form, die moderngekko-port versteht.

    ``LoadDefaultDolPatches`` in ``tools/moderngekko_port.cpp`` liest
    ``[OnFrame]`` und nimmt ausschliesslich Zeilen ``adresse:dword:wert`` an,
    freigeschaltet ueber ``[OnFrame_Enabled]``. Einfuegungen lassen sich so
    nicht ausdruecken; dafuer gibt es den Codebereich.
    """
    lines = ["[OnFrame]", f"${name}"]
    for write, _ in writes:
        lines.append(f"0x{write.address:08X}:dword:0x{write.value:08X}")
    lines += ["", "[OnFrame_Enabled]", f"${name}", ""]
    return "\n".join(lines)
