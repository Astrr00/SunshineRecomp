# Kopfloser Prüfstand in der Cloud

Stand: 2026-09-14. Erstmals lief das statisch rekompilierte Spiel ausserhalb
des Windows-Rechners: unter Linux, ohne Fenster, mit Null-Grafik, gesteuert
über das Automationsprotokoll. Damit lassen sich Fragen am laufenden Spiel
beantworten, für die bisher eine Sitzung am Rechner des Auftraggebers nötig
war.

**Keine Spieldaten im Repository.** Spielkopie, Module und Laufverzeichnisse
blieben in der Sitzung. Hier stehen Messwerte.

## Aufbau

| Schritt | Ergebnis |
|---|---|
| Abhängigkeiten | Ubuntu 24.04, GCC 13, CMake 3.28, Ninja; Wayland-, X11- und USB-Entwicklungspakete |
| RecompCore `c6a600eb` | einzeln geholt, 33 Untermodule (Windows-Binärpakete ausgelassen), 688 MB |
| Sechs Patches | alle in Bootstrap-Reihenfolge angewandt, GXRuntime meldet CPU-ABI 4 |
| ModernGekko-Bau | `moderngekko-run`, `moderngekko-port`, `dolrecomp`, `moderngekko-module-info`; Vorgaben wie in `build.ps1` (Frontend-Name, Disc-ID, DOL-Prüfsumme) |
| Modulbau | `moderngekko-port build … --backend c --toolchain clang`: 221 C-Dateien, ThinLTO-Link, **64 min 46 s auf 4 Kernen**, `gGMSE01_recomp.so` mit 90.043.344 Bytes |
| Start | `moderngekko-run --headless --graphics Null --audio Null --automation-dir …`; Modul geladen, Eintritt `0x8000522C` |

Drei Stolpersteine, jeweils mit Ursache:

1. **clang 18 scheitert an `std::expected`.** Mit libstdc++ meldet clang vor
   Version 19 ein zu altes Concepts-Level; `<expected>` bleibt leer. GCC 13
   baut den Baum ohne Änderung.
2. **`config.ini` erzwingt Vulkan oder OpenGL**, und ein dort gesetzter Backend
   gewinnt über den kopflosen Null-Backend. `--graphics Null` auf der
   Befehlszeile löst das; `internal_scale` muss seit dem Anzeige-Patch gesetzt
   sein.
3. **`Sys/` wird neben der EXE gesucht.** Ein kopierter Runner findet weder
   Schriften noch `codehandler.bin`; Gecko-Codes laufen dann stumm nicht. Das
   erklärt auch, warum ein erster Vergleichslauf alle 25 Stellen unverändert
   zeigte. Ein Symlink neben dem Runner genügt.

Der Treiber ist `tools/diagnostics/headless_probe.py`: Er startet, wartet
eine Framezahl ab, liest benannte Bereiche und beendet den Lauf regulär.
Alles landet in einem Manifest.

## Befund 1: Der Codebereich liegt im Hauptstapel, nicht im Heap

Offen aus [09-DOL-BEFUNDE.md](09-DOL-BEFUNDE.md): Beginnt der Spielheap bei
`0x80417800`, wo der eingebackene Widescreen-Codebereich liegt?

`__OSArenaLo` und `__OSArenaHi` tragen bei Frame 600 beide `0x817FEEC0`:
Das Spiel hat die Arena beim Start vollständig in seine Heaps übernommen; der
ursprüngliche Wert ist damit nicht mehr lesbar. Entscheidend sind die
Statika von `JKRHeap` (Adressen aus der Symbolliste, `0x8040E290` ff.):

| Feld | Wert |
|---|---|
| `mCodeStart` | `0x80000000` |
| `mCodeEnd` | `0x80427820` |
| `mUserRamStart` = `sRootHeap` | **`0x80427820`** |
| `mUserRamEnd` | `0x817FEEC0` |
| `mMemorySize` | 25.165.824 Bytes |

Der Wurzel-Heap beginnt bei `0x80427820`, also 65.568 Bytes hinter dem
Abbildende `0x80417800`. Dieser Zwischenraum ist der **Hauptstapel**: Bei
Frame 1800 sind darin nur die Bytes `0x804267E8–0x80427803` beschrieben, er
wächst also von `0x80427800` abwärts und hat bis dahin rund 4 KB belegt.

Folge für WP8: Der Codebereich `0x80417800–0x80417918` liegt am untersten
Ende des Stapels, 61.136 Bytes unter der tiefsten beobachteten Nutzung, und
im Bereich, den das Spiel selbst als Code führt (`mCodeStart`…`mCodeEnd`). Vom
Heap wird er nicht berührt. Er wäre erst betroffen, wenn der Stapel um mehr
als 61 KB tiefer liefe; dann stünde ohnehin `data14` darunter als Nächstes.
Ob das im Spielverlauf vorkommt, ist mit einer Tiefstandsmessung über den
Abnahmelauf zu belegen, nicht hier.

## Befund 2: Der Gecko-Weg ist reproduziert, samt SMC-Rückfall

Lauf mit dem unveränderten Modul, aktiviertem Code aus
`scripts/widescreen-profile.py`, 1800 Frames:

| Gegenstand | Ergebnis |
|---|---|
| 13 Schreibungen | alle Werte im RAM wie in der INI |
| 12 Einfügestellen | überall ein Sprung; angesprungener Rumpf bytegenau wie die INI |
| Codehandler | `GeckoCodes: Using 480 of 3256 bytes` |
| Laufzeit | `native=255829 fallback=0 smc_failed=1` |
| SMC | `chunk [0x802C9600,0x802CD600) hash mismatch; interpreter until the original code is restored` |

Das ist genau der in [03-WIDESCREEN.md](03-WIDESCREEN.md) beschriebene
Befund: Der Widescreen-Code wirkt, und der davon geänderte Chunk läuft im
Interpreter. Der zweite dort genannte Chunk (`80361600`) wurde in 1800 Frames
noch nicht angesprungen. Prüfer: `tools/widescreen/verify_ram.py`.

## Befund 3: Das gebackene DOL läuft nativ, ohne SMC-Rückfall

Zweites Modul aus dem in [09](09-DOL-BEFUNDE.md) gebackenen DOL
(`3a655b2e…`, 69 min 50 s), Runner ohne DOL-Prüfsummenzwang, Spielwurzel mit
dem gebackenen `sys/main.dol`, **keine Cheats**, 1800 Frames:

| Gegenstand | Gecko-Weg | eingebacken |
|---|---|---|
| 13 Schreibungen im RAM | stimmen | stimmen |
| 12 Einfügestellen | Sprung zum Codehandler, Rumpf wie INI | Sprung nach `0x80417800`, Rumpf und Rücksprung wie berechnet |
| Seitenverhältnis `0x80412408` | `3FE38E39` | `3FE38E39` |
| native Aufrufe / Rückfälle | 255.829 / 0 | 300.540 / 0 |
| Chunk-Prüfungen | 18 | 40 |
| `smc_failed` | **1** (`802C9600` im Interpreter) | **0** |
| Heap-Nutzer-RAM | `0x80427820–0x817FEEC0` | `0x80427820–0x817FEEC0` |

Derselbe Spielabschnitt, dieselbe Framezahl: Auf dem Gecko-Weg meldet die
Laufzeit den Hash-Fehler und interpretiert den geänderten Chunk; mit dem
gebackenen DOL gibt es keine einzige SMC-Zeile im Log, und die Chunk-Prüfungen
(40, mehr als beim Gecko-Lauf) bestehen alle. Der Widescreen-Code läuft damit
**nativ** -- das ist das Ziel von WP8, am laufenden Spiel belegt. Prüfer:
`tools/widescreen/verify_ram.py --cave 0x80417800`.

## Was für das Produkt daraus folgt

1. **Der Runner erzwingt die DOL-Prüfsumme** (`MODERNGEKKO_REQUIRED_DOL_SHA256`,
   `moderngekko_run.cpp`) und bootet `sys/main.dol` unmittelbar. Das gebackene
   DOL muss also die geladene Datei sein, und die Prüfsumme muss auf das
   gebackene DOL lauten -- oder die Prüfung erfolgt, wie beim Launcher schon
   heute, vor dem Patchen an der Originaldatei. Für diesen Versuch wurde ein
   zweiter Runner ohne die Vorgabe gebaut.
2. **Der Patchmechanismus des Launchers kennt keine neuen Sektionen.**
   `dol_patch.cpp` ersetzt Worte innerhalb bestehender Textsektionen. Für den
   Produktweg muss entweder der Launcher das gebackene DOL aus
   `tools/widescreen` übernehmen, oder der Manifest-Mechanismus um eine
   Sektion erweitert werden. Das gehört in WP2, Schritt 3.
3. **Der Codebereich liegt im Stapel.** Sicher gegen den Heap, 61 KB unter
   der beobachteten Stapelnutzung. Eine Tiefstandsmessung über den
   Abnahmelauf (WP6) macht daraus einen belegten Wert.

Nicht belegt bleibt, was nur ein Bild zeigen kann: HUD, Effekte, Culling. Das
bleibt die Bildabnahme aus WP8, Punkt 4, am Windows-Rechner.

## Was der Prüfstand nicht kann

Kein Bild, kein Ton, keine Eingabe von Hand. Er misst Speicher, Log und
Zähler. Bildabnahme, HUD, Culling und Hörproben bleiben Aufgaben am
Windows-Rechner. Eingaben per `pad_frames` sind grundsätzlich möglich, wurden
hier aber nicht genutzt.
