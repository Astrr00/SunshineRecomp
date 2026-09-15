# Übergabe: Nativer Super-Mario-Sunshine-Port für Windows

Stand: 2026-09-09, Kopf fortgeschrieben am 2026-09-15. Dieses Dokument ist die
Übergabe der Windows-Sitzungen. Es setzt kein Vorwissen voraus.

**Wo der aktuelle Stand steht:** [PLAN.md](PLAN.md) legt Leitentscheidungen,
Reihenfolge, Arbeitspakete und die offenen Entscheidungen des Auftraggebers
fest. [02-STATUS.md](02-STATUS.md) ist die Anforderungsmatrix: Stand je
Anforderung und je Arbeitspaket, jeweils mit Verweis auf das Belegprotokoll.
Beide sind neuer als der Rest dieses Dokuments.

**Seit dem 2026-09-14 in entfernten Sitzungen entstanden** (Linux, mit einer
vom Auftraggeber bereitgestellten Spielkopie, die im Repository nicht
auftaucht):

| Dokument | Ergebnis |
|---|---|
| [09-DOL-BEFUNDE.md](09-DOL-BEFUNDE.md) | DOL-Aufbau vermessen, Symbolkarte übernommen und gegengeprüft, Widescreen in das DOL gebacken |
| [10-KOPFLOSER-PRUEFSTAND.md](10-KOPFLOSER-PRUEFSTAND.md) | kopfloser Prüfstand; Arena- und Stapelfrage beantwortet; Gecko-Weg gegen eingebacken |
| [11-FRAMERATE-SPIKE.md](11-FRAMERATE-SPIKE.md) | WP13 abgeschlossen: Zuordnung 96–100 %, Zwischenbild gerendert, Schnitterkennung kalibriert |
| [12-TON.md](12-TON.md) | WP1: Ton gemessen, keine Zeitbasisabweichung |
| [13-STATISCHER-KERN.md](13-STATISCHER-KERN.md) | das Rekompilat führt höchstens 0,18 % der Gasttakte aus; Ursache gemessen (am 15.09. in zwei Punkten berichtigt) |

**Am 2026-09-15 abends, in derselben entfernten Sitzung, dazugekommen** — das
ist der aktuelle Stand und der beste Einstieg:

| Dokument | Ergebnis |
|---|---|
| [16-RUECKWEG.md](16-RUECKWEG.md) | **Der Kern läuft jetzt nativ.** Der Ersatz-JIT hatte den Dispatcher nie verlassen; ein Rückweg an den Ausnahme-Ausgängen senkt seinen Anteil an den Gasttakten von 99,99 % auf 0,015 %. Beide Abnahmeszenarien bestehen weiter. Preis: 1,27-mal langsamer als der Ersatz-JIT, nach einer ersten Verbesserung um 52 % |
| [17-LOCKSTEP.md](17-LOCKSTEP.md) | **Der Verifizierer läuft erstmals.** Von 116 gemeldeten Abweichungen kamen 112 aus seiner eigenen Halteregel, die übrigen 4 aus einem Verbuchungsunterschied. In keiner steht ein Rechenfehler des Rekompilats |
| [18-SKALIERER.md](18-SKALIERER.md) | Ausgabe-Skalierer als Produktfunktion: neun Kerne, zwei davon erstmals erreichbar. Interner Faktor 6 rendert 3840×2688, also mehr als 4K. Die Bildwirkung des Skalierers braucht ein echtes Fenster und steht aus |
| [19-ULTRAWIDE.md](19-ULTRAWIDE.md) | Das Seitenverhältnis steht in genau einem Wort des Widescreen-Codes (`0x80412408`). `tools/widescreen bake --aspect` macht es einstellbar; 4:3, 16:9, 64:27 und 32:9 sind erzeugt |

**Wichtig für die nächste Sitzung:** Der Rückweg ist ausdrücklich zu schalten
(`STATICRECOMP_YIELD=1`) und **nicht** Voreinstellung — erst wenn die vier
verbliebenen Lockstep-Meldungen geklärt sind, darf er das werden. Die
Bedingung steht in [16](16-RUECKWEG.md).

Neue Werkzeuge im Repository: `tools/symbols`, `tools/widescreen`,
`tools/framerate`, `tools/audio`, `tools/acceptance` (Abnahmelauf nach
PLAN 2.5), `tools/diagnostics/headless_probe.py`.

**Fortsetzung vom 2026-09-10:** [08-WINDOWS-ROM-CONTROLLER.md](08-WINDOWS-ROM-CONTROLLER.md).
Auftraggeber präzisiert: native Windows-Anwendung, alle Controller, spielbar
durch Auswahl einer eigenen ROM. Launcher ist auf GMSE01/DOL-Prüfsumme
konfiguriert, direkter RVZ-Import geprüft (179 Spieldateien identisch).
Frisch importiertes Spiel bootet mit dem vorhandenen statischen Modul ohne
Savestate (Bild, 29,96 FPS, Exit 0). Automatischer Modulbau nach ROM-Auswahl
und breite Controller-Belegung sind noch offen und als Nächstes zu integrieren.
Fehlende Startverzeichnisse behoben: frisches Profil schreibt 17 MB Shader-Cache,
Bild/Vollbild/Stop geprüft. Der frühere FST-Rename-Fehler bleibt ursächlich offen.

**Neueste Fortsetzung:** [07-ANZEIGE.md](07-ANZEIGE.md). Interner Faktor und
Fenstergröße sind separat konfigurierbar; Win32-Vollbildwechsel und Rückkehr
zur Fenstergröße wurden am Spiel vermessen. Vier Profile in
`build/display-verification-v6/` endeten regulär mit Exit 0. Ein beim Test
eingeführter Hänger wurde durch Verlegung der globalen Konfigurationsspeicherung
nach Core-Shutdown beseitigt; frühere v2–v5-Läufe sind keine erfolgreichen
Shutdown-Tests. Launcher gebaut, aber noch nicht visuell abgenommen. Neue
Patches sind im Bootstrap eingebunden und rekonstruieren den geänderten
Quellcode nachweislich. Die übrigen Anforderungen bleiben offen.

**Nachtrag zur Widescreen-Sitzung vom selben Tag:** Der spielseitige Gecko-Code
ist aktiviert und im RAM vollständig nachgewiesen. Dateiauswahl, Gameplay am
Delfino Airstrip, Kameradrehung, Echtzeitdialog und Pause wurden mit Bildern
geprüft. Ein Kaltstart-Vergleich bestätigt zusätzliche horizontale Sicht bei
weitgehend unveränderten Proportionen. Anforderung 3 ist trotzdem nicht fertig:
Filme behalten Balken/erscheinen gestreckt; die vollständige HUD-, Effekt- und
Culling-Prüfung sowie Ultrawide fehlen. Aktuelle Belege, Konfiguration,
Testprofile und Grenzen: [03-WIDESCREEN.md](03-WIDESCREEN.md).
Die nachstehenden älteren „nicht verifiziert“-Angaben zum Gameplay und zur
Dateiauswahl sind damit überholt; Ton und reguläres Fortschrittsladen bleiben offen.

**Aktuellste Fortsetzung:** [06-ERSTER-SHINE.md](06-ERSTER-SHINE.md).
Boss besiegt, erster Shine eingesammelt, regulär gespeichert und nach
vollständigem Neustart in Slot A als 1 Shine wiedergefunden. Der erfolgreiche
Durchlauf enthielt keinen Savestate-Rücksprung. Ein vorheriger Save-Konflikt
entstand beim Mischen eines älteren Savestates mit einer neueren GCI und
wurde nicht durch einen Spieleingriff umgangen. Aktueller Lauf:
`build/one-shine-reload/auto/`, **pausiert in Delfino Plaza** nach regulärem
Laden; Bewegung und Zustandsleser dort geprüft. Ein gepaarter Diagnose-
Checkpoint liegt unter `build/one-shine-reload/checkpoint/`.
R-Dauerbetätigung zeigte ein noch ungeklärtes Verbrauchsplateau; siehe die
Messwerte in Dokument 06. Die Details der vorangegangenen Instrumentierung:
[05-FIFO-UND-FLUDD.md](05-FIFO-UND-FLUDD.md).
FIFO-Aufnahme ist implementiert, gebaut und getestet. Software-FIFO-Wiedergabe
zeigt dieselben auffälligen Schleimanteile; deren eindeutige Einordnung als
Grafikfehler war voreilig. FLUDD wurde im Spiel aufgenommen; Spritzen,
sichtbare Reinigung/Belohnung und der Unterschied zwischen halbem/vollem R
sind geprüft. Reguläres Save hat die Test-GCI geändert; der Slot wurde nach
Neustart ohne Savestate erkannt und gestartet. Story-Fortschritt über den
ersten Shine hinaus bleibt ungeprüft. Fortsetzung am pausierten Lauf unter
`build/gameplay-verification/auto/`. Die älteren Diagnoseversuche stehen in
[04-GRAFIKDIAGNOSE.md](04-GRAFIKDIAGNOSE.md).
Die Schleim-/NPC-Artefakte wurden über CPU, Backend, Auflösung und einzelne
Genauigkeitsschalter verglichen. Ein scheinbarer Sampling-Fix wurde beim
Neuaufbau der Spielszene widerlegt und **nicht übernommen**. Ein reproduzierbarer
Runner liegt unter `scripts/render-probe.py`. Grafikfehler weiter offen.

---

## 1. Auftrag

Nativer Port von Super Mario Sunshine für **Windows x86-64**. Vorbild ist
Dusklight für Twilight Princess: originalgetreuer Lauf plus moderne Grafik-,
Anzeige- und Steuerungsoptionen.

**Android wurde vom Auftraggeber am 2026-09-09 ausdrücklich gestrichen.** Damit
entfallen die ursprüngliche Anforderung 6, die Touch-Belegungen aus Anforderung 7
und die Smartphone-Seitenverhältnisse (19,5:9, 20:9) aus Anforderung 3.
Ultrawide (21:9, 32:9) bleibt.

Verbindliche Funktionen, Nummerierung wie im Auftrag:

1. Unbegrenzte Framerate (entkoppeltes Rendering, feste Simulationstakte,
   Interpolation, keine Artefakte bei Kameraschnitten)
2. Hohe Auflösungen, **Trennung von interner Render- und Ausgabeauflösung**
3. Echtes Widescreen ohne schwarze Balken, ohne Strecken, ohne pauschales Zoomen
4. HUD-Anker, Menüs, Zwischensequenzen; vorgerenderte Videos gesondert
5. Windows-Anwendung mit Fenster, randlosem Vollbild, Controller/Tastatur/Maus
6. *(entfallen)*
7. Analoge GC-Schultertaste (Spritzen im Laufen vs. im Stand), freie Belegung,
   Empfindlichkeit, Invertierung, Totzonen
8. Originalgetreues Spielverhalten, Speichern/Laden
9. Import einer eigenen Spielkopie, keine Mitlieferung von Spieldaten

Arbeitsprinzip des Auftraggebers: **Funktionen erst nach tatsächlicher
Überprüfung als fertig bezeichnen.** Ein Fenster mit Platzhaltergrafik ist kein
spielbarer Port.

---

## 2. Architekturentscheidung (getroffen, begründet, nicht neu aufrollen)

**Statische Recompilation** mit DolRecomp + ModernGekko. **Nicht** Decompilation,
**nicht** Aurora.

Begründung, jeweils am Quellcode geprüft:

- **doldecomp/sms** steht bei 38,82 % dekompiliert / 17,45 % gelinkt und
  unterstützt nur `GMSJ01` (JP) und `GMSP01` (PAL, im README selbst als defekt
  markiert), **nicht** die US-Fassung. Damit trägt der Dusklight-Weg nicht.
  Nutzbar bleibt die Decomp als **Referenz** (CC0): 38.262 Symbolnamen und
  Strukturwissen für `GMSJ01` — adressverschieden zu GMSE01.
- **Aurora** exportiert `include/dolphin/gx/*.h`, `ai.h`, `card.h`, `dvd.h`; es
  ist eine quellcodeseitige Neuimplementierung des GameCube-SDK auf WebGPU. Ein
  rekompiliertes Binary ruft kein `GXBegin()` als linkbares Symbol auf, sondern
  schreibt in GX-FIFO-Register. Es gibt keine Bindungsstelle. Als späterer
  optionaler nativer Renderer notiert, in v1 nicht auf dem kritischen Pfad.

Ausführlich in `docs/01-MACHBARKEIT.md`.

**Lizenzfolge:** ModernGekko und DolRecomp sind GPL-3.0 (Dolphin-Abstammung
GPL-2.0-or-later). Der Port **muss** GPL-3.0-or-later sein. `LICENSE` liegt bei.

---

## 3. Repository und Umgebung

| | |
|---|---|
| Arbeitsverzeichnis | `C:\Users\niemc\Documents\Projekte\SunshineRecomp` |
| GitHub | `Astrr00/SunshineRecomp` (**privat**), Branch `main` |
| Letzter Commit | `2ccf8cc` "Aufloesungsverhalten vermessen (Anforderung 2)" |
| Spielkopie des Nutzers | `C:\Users\niemc\Documents\Projekte\Super Mario Sunshine (USA).rvz` |

Werkzeugkette, verifiziert:

| Werkzeug | Version | Ort |
|---|---|---|
| MSVC `cl.exe` | 19.44.35228 | `C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools` |
| Windows SDK | 10.0.26100.0 | Standard |
| CMake | 4.4.3 | winget, user scope |
| LLVM / clang-cl | 20.1.8 | `ref/llvm` (per Bootstrap geladen) |
| Ninja | 1.13.2 | auf PATH |
| Python | 3.14.7 | auf PATH |

`vcvars64.bat` muss vor jedem CMake/Ninja-Aufruf im selben `cmd`-Prozess laufen.
`scripts/build.ps1` findet MSVC über `vswhere` und erledigt das.

---

## 4. Was im Repository liegt

```
docs/01-MACHBARKEIT.md   Architekturentscheidung, geprüfte Commits, Lizenzlage
docs/02-STATUS.md        Anforderungsmatrix: Stand je Anforderung und Arbeitspaket
docs/HANDOFF.md          dieses Dokument
patches/                 zwei Patches gegen Upstream-Lücken (siehe Abschnitt 7)
scripts/bootstrap.ps1    klont Abhängigkeiten auf feste Commits, lädt LLVM, patcht
scripts/build.ps1        baut DolRecomp (clang-cl) und ModernGekko (MSVC)
tools/import/            Disc-Import: gcm.py, importer.py, __main__.py
tests/test_import.py     14 Tests gegen ein synthetisches GameCube-Abbild
```

Nicht im Repository und per `.gitignore` ausgeschlossen: `build/`, `ref/`,
Abbilder, `main.dol`, generierter Code, Module. **Es werden keine Spieldaten
verteilt oder heruntergeladen.**

---

## 5. Vollständiger Ablauf von null auf lauffähig

```powershell
./scripts/bootstrap.ps1                 # Abhängigkeiten + LLVM + Patches
./scripts/build.ps1 -Target all -Test   # DolRecomp und ModernGekko
```

RVZ nach ISO wandeln (der Importer lehnt komprimierte Container bewusst ab):

```powershell
./ref/ModernGekko/Binary/x64/DolphinTool.exe convert `
  -i "C:\Users\niemc\Documents\Projekte\Super Mario Sunshine (USA).rvz" `
  -o "build\Super Mario Sunshine (USA).iso" -f iso
```

Importieren:

```powershell
python tools/import "build\Super Mario Sunshine (USA).iso" --to build\game
```

Modul bauen (rund 20 Minuten):

```powershell
./ref/ModernGekko/build/moderngekko-port.exe build build\game `
  --backend c --toolchain clang --output build\mod
```

Starten:

```powershell
./ref/ModernGekko/build/moderngekko-run.exe --game build\game `
  --module build\mod\GMSE01\<hash>\gGMSE01_recomp.dll --user-dir build\userdir
```

---

## 6. Was verifiziert ist — und was nicht

### Verifiziert

| Gegenstand | Beleg |
|---|---|
| DolRecomp gebaut | ctest 19/19 |
| ModernGekko gebaut | alle eigenen Tests grün |
| Import korrekt | **byte-identisch** zu DolphinTool über 179 Dateien |
| Revision bestätigt | `GMSE01` Rev 0, 1.459.978.240 Bytes, SHA-256 `67cec163…3e51d` |
| Recompilation | 16.618 LLVM-Chunks bzw. 224 C-Dateien, Exit 0 |
| Modul geladen | `[staticrecomp] module loaded … entry=0x8000522C` |
| Bild | Eröffnungssequenz, Titelbildschirm, Dateiauswahl gerendert |
| Bildrate | stabil 29,9–30,0 FPS (Sunshines native Rate) |
| Eingabe | `start` → Titel, `a` → Dateiauswahl, jeweils belegt |
| Speichern | Memory-Card-Datei mit 57.408 Bytes angelegt |
| Auflösung | 1× = 640×477, 3× = 1920×1430, 6× = 3840×2859, je 30 FPS |

### Nicht verifiziert

- **Ton.** Weder Höreindruck noch Logeintrag. In beide Richtungen offen.
- **Eigentliches Spielgeschehen.** Die Auswahl eines Speicherplatzes gelingt über
  das Automationsprotokoll nicht — Eingaben kommen an (Mario reagiert), treffen
  aber die Cursor-Mechanik der Dateiauswahl nicht. **Das ist eine Grenze der
  blinden Fernsteuerung, kein belegter Fehler.** Am schnellsten von Hand mit
  Controller oder Tastatur zu prüfen.
- **Laden** eines gespeicherten Fortschritts.
- Anforderungen **1, 3, 4, 7** sind unbearbeitet.

---

## 7. Upstream-Defekte und die beiden Patches

**Wurzel:** GXRuntimes `include/core/cpu.h` ist eine veraltete Dublette von
`DolRecomp/src/cpu/cpu.h`. Beide tragen denselben Include-Guard
`DOLRECOMP_CPU_H`, sodass je Übersetzungseinheit nur einer wirkt. DolRecomps
Fassung ist die vollständige (enthält `cycle_budget`, `external_pointer` und alle
drei Inline-Helfer).

**Folge:** ModernGekkos Laufzeit verlangt CPU-ABI 4 (`sizeof(CPUState)` = 3536),
das gepinnte GXRuntime liefert ABI 3 (3528). Ein damit gebautes Modul wird beim
Start abgewiesen: `native module was rejected: CPU ABI mismatch`. Das trifft auch
das offizielle `ModernGekko-Template`, weil es dieselbe Pipeline fährt.

**Lösung, in `scripts/bootstrap.ps1` verankert:**

1. Vendor-Submodul `ref/ModernGekko/vendor/dolphin` auf RecompCores Branch
   `moderngekko-runtime`, Commit `c6a600eb434056873566ef951d11974619a7ed31`
   (dort ABI 4 mit `cycle_budget`).
2. `patches/recompcore-abi-gaps.patch` schließt zwei Lücken dieses Branches:
   - `StaticRecompCore::GetExceptionCheckTarget` ist als `override` deklariert,
     obwohl `JitBase` die Methode nicht kennt (MSVC C3668). Sie kommt im ganzen
     `Source/`-Baum einmal vor und hat keinen Aufrufer → `override` entfällt.
   - GXRuntime fehlen die Inline-Wrapper `ppc_fp_available_inline`,
     `ppc_psq_load_inline`, `ppc_psq_store_inline`, die DolRecomps Emitter stets
     erzeugt. Ergänzt als Weiterleitungen — laut Kommentar in
     `DolRecomp/src/cpu/cpu.h` ist genau das der Vertrag (die hostende Laufzeit
     stellt sie bereit, ein Schnellpfad ist optional).
3. `patches/dolrecomp-msvc-popcount.patch`: `__builtin_popcountll` kennt MSVC
   nicht; ersetzt durch `std::bitset<64>::count()` (keine Annahme über den
   Befehlssatz, anders als `__popcnt64`).

---

## 8. Fallstricke, die Zeit gekostet haben

1. **`--backend c`, nicht `llvm`.** `moderngekko-port` ruft sein eigenes
   gepinntes DolRecomp **ohne** `--runtime moderngekko` auf und verarbeitet die
   Ausgabe über RecompCores Modulvorlage plus GXRuntime. Mit `--backend llvm`
   emittiert der Emitter `ppc_native_region_available` und `func_..._budget`, die
   dort fehlen. Die 224 erzeugten C-Dateien decken sich mit der Angabe des
   Apple-Referenzports SunPad ("221 C chunks, ~220 MiB") — das ist der richtige
   Pfad. Die Meldung *"the ModernGekko runtime requires the LLVM backend"* stammt
   vom **eigenständigen** DolRecomp und gilt für diesen Pfad nicht.
2. **Windows-Pfadlänge.** `moderngekko-port` legt seinen Cache relativ zum
   Arbeitsverzeichnis an, mit 81 Zeichen langem Hash-Ordner. Immer einen kurzen
   absoluten `--output` setzen. `LongPathsEnabled` steht zwar auf 1, die
   Programme tragen aber kein passendes Manifest.
3. **`-DCMAKE_CXX_FLAGS` ersetzt die Vorgabe**, statt sie zu ergänzen. MSVCs
   `/DWIN32 /D_WINDOWS /EHsc` muss mitgeführt werden, sonst scheitert `<chrono>`
   an C4530. Der Baum baut mit `/WX`, und `RelocationAliases.cpp` braucht
   zusätzlich `/D_SILENCE_CXX20_OLD_SHARED_PTR_ATOMIC_SUPPORT_DEPRECATION_WARNING`.
4. **`test_rpx.exe` scheitert** an einem zlib-ng/MSVC-Linkerfehler
   (`__imp__aligned_malloc`). Das ist ein Testziel des eingebetteten DolRecomp;
   die benötigten Programme baut man gezielt mit
   `--target moderngekko-port dolrecomp moderngekko-run moderngekko-module-info`.
5. **`moderngekko-module-info` meldet fälschlich "CPU ABI mismatch"**, weil es
   gegen ModernGekkos eigenen Header prüft. Maßgeblich ist der tatsächliche
   Start.
6. **Compilerwechsel im bestehenden CMake-Build-Verzeichnis** setzt Cache-Werte
   zurück (`DOLRECOMP_ENABLE_LLVM` fiel dabei still auf `OFF`). Bei
   Toolchain-Wechsel das Verzeichnis löschen.

---

## 9. Automationsprotokoll — das wichtigste Werkzeug zum Prüfen

Mit `--automation-dir <pfad>` legt die Laufzeit `<pfad>/commands/` an und
verarbeitet dort abgelegte Textdateien. Damit lassen sich Eingaben einspeisen und
Bilder aufnehmen, ohne am Rechner zu sitzen.

```
command=pad_frames
port=0
frames=12
start=1
```

```
command=screenshot
path=C:\...\bild.png
```

Weitere Befehle: `pad`, `clear_pad`, `pause`, `resume`, `save_state`,
`load_state`, `read_memory`, `write_memory`, `stop`. Pad-Felder unter anderem
`a b x y z start l r l_analog r_analog main_x main_y c_x c_y dpad_*`.

Ergänzt und am Spiel geprüft: `record_fifo` mit `frames=1..120` und
`path=<lokale.dff>`; benötigt einen laufenden Core. Siehe Abschnitt zur
FIFO-Diagnose in `05-FIFO-UND-FLUDD.md`.

`l_analog`/`r_analog` sind für **Anforderung 7** zentral: Sunshine unterscheidet
die halb und ganz gedrückte Schultertaste.

Die Bildgröße lässt sich aus dem PNG-Kopf lesen (Bytes 16–23, Big-Endian) — so
wurde die Auflösungsmessung gemacht.

---

## 10. Nächster Schritt: Anforderung 3, echtes Widescreen

**Hier wurde die Arbeit unterbrochen.**

Ausgangslage: Alle Messungen liegen bei rund 1,34 (4:3). Der generische
Widescreen-Hack von Dolphin ist **kein** gangbarer Weg — SunPads
`docs/KNOWN_ISSUES.md` (Punkt 9) dokumentiert für Sunshine abgetrennte Schatten,
harte Projektionsnähte und duplizierte Geometrie, dazu einen Hitzeflimmer-Effekt,
der eine Geisterkopie der Szene erzeugt.

**Der vielversprechende Hebel:** Dolphin liefert
`ref/ModernGekko/vendor/dolphin/Data/Sys/GameSettings/GMSE01.ini` mit
spielseitigem Code für genau diese Revision. Unter `[Gecko]` steht ein
`$Widescreen [gamemasterplc]` (Zeile 118). Der zweite Name in Zeile 188 unter
`[Gecko_RetroAchievements_Verified]` ist nur eine Freigabemarkierung. Der Code
enthält 13 direkte Schreibpatches und zwölf Code-Injektionen, verändert also
Daten und Instruktionen im Spiel selbst.

Aufgaben:

1. Klären, wie ModernGekko Gecko-Codes aktiviert (Dolphin nutzt üblicherweise
   einen `[Gecko_Enabled]`-Abschnitt in einer nutzerseitigen Spiel-INI unter
   `<user-dir>/GameSettings/GMSE01.ini`). `MODERNGEKKO_GAME_SETTINGS_OVERRIDE`
   in ModernGekkos CMake ist ein weiterer möglicher Weg.
2. Aktivieren und an echten Spielszenen prüfen: Gameplay, HUD, Menüs,
   Zwischensequenzen, jeweils mit Bildern.
3. Gezielt auf die dokumentierten Fehlerbilder achten: Schatten, Nähte,
   duplizierte Geometrie, Himmel, Wasser, Spiegelungen, Bildschirmeffekte.
4. Sichtbarkeitsprüfungen (Culling) am erweiterten Bildrand kontrollieren.
5. Erst danach 21:9 und 32:9 angehen.

**Wichtige Einschränkung für die Anforderungen 1, 3 und 4:** Die US-Disc enthält
**keine** `mario.MAP`. Nachgeprüft: 174 Dateien, nur `opening.bnr`, `data/` und
`AudioRes/`, keine Symboldatei. Die Symbol-Map gehört zur japanischen Fassung,
weshalb die Decompilation auf `GMSJ01` zielt. ModernGekkos Mod-ABI
(`include/moderngekko/mod_abi.h`, `RECOMP_PATCH` / `RECOMP_HOOK` /
`RECOMP_HOOK_RETURN` auf `CPUState*`) bindet zwar an **rohe 32-Bit-Adressen**,
sodass Hooks grundsätzlich möglich sind — aber jede Hook-Stelle muss erst
gefunden werden. Quellen dafür: die adressbasierten Codes in `GMSE01.ini`, die
CC0-Symbole der Decompilation für `GMSJ01` (namensgleich, adressverschieden) und
DolRecomps eigene Analyse.

**Anforderung 1 bleibt der härteste Posten.** Kein untersuchtes Projekt liefert
entkoppeltes Rendering. Der Bildabschluss hängt am emulierten VI-Interrupt; ob
sich das sauber lösen lässt, ist ungeprüft und das größte offene Risiko.

---

## 11. Arbeitsweise, die der Auftraggeber erwartet

- Deutsch schreiben.
- Am **tatsächlichen Quellcode** entscheiden, nicht an READMEs.
- Befunde messen statt vermuten (Strukturgrößen, Bildgrößen, Prüfsummen).
- Eigene Irrtümer klar benennen und korrigieren.
- Nichts als fertig bezeichnen, was nicht überprüft wurde.
- Erst auf ausdrückliche Aufforderung committen und pushen.
- Keine Spieldaten verteilen, nichts automatisch herunterladen.
