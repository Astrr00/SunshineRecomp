# SunshineRecomp

Nativer Port von Super Mario Sunshine für **Windows x86-64** auf Basis statischer
Recompilation.

**Status: früh.** Das Spiel startet, läuft und speichert; eine fertige
Anwendung ist es nicht. Der aktuelle Stand je Anforderung und Arbeitspaket
steht in [docs/02-STATUS.md](docs/02-STATUS.md), das weitere Vorgehen in
[docs/PLAN.md](docs/PLAN.md), die Architekturentscheidung in
[docs/01-MACHBARKEIT.md](docs/01-MACHBARKEIT.md).

Offene Grundsatzfrage seit dem 2026-09-15: Das rekompilierte Modul führt
gemessen höchstens 0,18 % der Gasttakte aus, den Rest übernimmt der
mitlaufende JIT ([docs/13-STATISCHER-KERN.md](docs/13-STATISCHER-KERN.md)).

## Bauen

Voraussetzungen, verifiziert am 2026-09-09: Visual Studio 2022 Build Tools mit der
C++-Arbeitslast (MSVC 19.44), Windows SDK 10.0.26100, CMake ab 3.20, Ninja, Git,
Python 3.10 oder neuer.

Externe Abhängigkeiten werden nach `ref/` geholt und sind nicht vendoriert. Das
Bootstrap-Skript klont Recompiler und Laufzeit auf feste Commits und lädt zusätzlich
LLVM (rund 940 MB):

```powershell
./scripts/bootstrap.ps1
```

```powershell
./scripts/build.ps1 -Target all -Test
```

Zwei Eigenheiten, die das Build-Skript automatisch behandelt:

- **LLVM ist Pflicht, nicht optional.** DolRecomp bricht mit
  `the ModernGekko runtime requires the LLVM backend` ab, wenn es ohne
  `-DDOLRECOMP_ENABLE_LLVM=ON` gebaut wurde. Akzeptiert wird nur LLVM 19.x oder 20.x,
  und beim Aufruf muss `--backend llvm` gesetzt sein.
- **DolRecomp wird mit `clang-cl` gebaut, ModernGekko mit MSVC.** Der
  LLVM-Backend-Code nutzt `__builtin_popcountll`, das MSVC nicht kennt.
- Die offiziellen LLVM-Windows-Pakete verdrahten den Pfad zum DIA SDK von
  Visual Studio 2019. Das Skript biegt ihn auf die lokale Installation um.

## Spieldaten

Dieses Projekt enthält **keine** Spieldaten, liefert keine aus und lädt keine
herunter. Für die Nutzung ist eine eigene Kopie des Spiels erforderlich.

## Import einer eigenen Spielkopie

Benötigt Python 3.10 oder neuer. Unterstützt werden unkomprimierte ISO- und
GCM-Abbilder; komprimierte Container (RVZ, WIA, CISO, GCZ, WBFS) werden erkannt und
mit einem Hinweis abgelehnt.

Kopie prüfen, ohne etwas zu schreiben:

```bash
python tools/import --check "D:/Super Mario Sunshine.iso"
```

Kopie importieren:

```bash
python tools/import "D:/Super Mario Sunshine.iso" --to build/game
```

Unterstützte Revisionen anzeigen:

```bash
python tools/import --list-revisions
```

Der Import erzeugt `main.dol` (Eingabe für den Recompiler), `mario.MAP`
(Symbol-Map der Disc), `files/` (übriges Dateisystem) und `import.json`
(Nachweis über Revision und Prüfsummen). Alles davon bleibt lokal und ist von der
Versionskontrolle ausgeschlossen.

## Tests

```bash
python -m unittest discover -s tests -v
```

Die Tests erzeugen ein synthetisches Abbild im GameCube-Format. Sie prüfen die
Formatlogik ohne Spieldaten; ein echtes Abbild ist damit **nicht** getestet.

## Lizenz

GPL-3.0-or-later, siehe [LICENSE](LICENSE). Die Laufzeit (ModernGekko, mit
Dolphin-Abstammung unter GPL-2.0-or-later) und der Recompiler (DolRecomp) stehen unter
GPL-3.0; ein Port, der sie einbindet, muss es ebenfalls sein. Das gilt auch für die
Dateien unter `patches/`, die Ausschnitte aus diesen Quellen enthalten. Einzelheiten in
[docs/01-MACHBARKEIT.md](docs/01-MACHBARKEIT.md), Abschnitt 4.
