# Status: Anforderungen, Arbeitspakete, Belege

Stand: 2026-09-15. Umfang: nativer Windows-x86-64-Port (Android entfallen).

Dieses Dokument ist die **Anforderungsmatrix** des Vorhabens
([PLAN.md](PLAN.md), Abschnitt 2.6). Hier steht nur, was tatsächlich
ausgeführt und beobachtet wurde. Was nicht überprüft ist, steht nicht unter
„belegt". Die nummerierten Dokumente bleiben die Belegprotokolle; neue
Sitzungen legen eine neue Nummer an, statt alte Dokumente mit
„Neuester Stand"-Absätzen zu ergänzen.

## Anforderungen

| # | Anforderung | Stand | Belegt | Offen |
|---|---|---|---|---|
| 1 | Unbegrenzte Framerate | Spike abgeschlossen | Zuordnung der Zeichenbefehle 96–100 %, Bewegung steckt in den Matrizen, synthetisches Zwischenbild gerendert und geprüft, Schnitterkennung kalibriert ([11](11-FRAMERATE-SPIKE.md)) | Umsetzung (WP14); Gegenschnitt in gleicher Szene; Kosten auf echter GPU; Entscheidung des Auftraggebers zu PLAN 5.4 |
| 2 | Hohe Auflösung, getrennte Ausgabe | weitgehend erledigt | `internal_scale` 1–12 und `output_resolution` getrennt gemessen; randloses Vollbild 1920x1080 und 3440x1440 ([07](07-ANZEIGE.md)) | HiDPI, Mehrmonitor, Launcher-Bedienung, Kantenglättung als Option |
| 3 | Echtes Widescreen | **Kern abgenommen** | 25/25 Patchstellen im RAM; in das DOL eingebacken, kein SMC-Rückfall; senkrechter Maßstab bitgleich, waagerechter mal 0,757, Sichtverhältnis exakt 16/9, HUD am Bildrand verankert und unverzerrt ([03](03-WIDESCREEN.md), [09](09-DOL-BEFUNDE.md), [10](10-KOPFLOSER-PRUEFSTAND.md), [15](15-WIDESCREEN-ABNAHME.md)) | Filme werden gestreckt (Projektion unverändert, [15](15-WIDESCREEN-ABNAHME.md)); Culling, Effekte und weitere HUD-Elemente; 21:9 und 32:9; ob der Code nativ oder im JIT läuft, ist offen ([13](13-STATISCHER-KERN.md)) |
| 4 | HUD-Anker, Menüs, Sequenzen | nicht begonnen | nur mittelbar über die 2D-Konstanten des Gecko-Codes | alles; Adressbasis steht jetzt zur Verfügung (WP7) |
| 5 | Windows-Anwendung | halb | Win32-Fenster, randloses Vollbild, Alt+Enter, DPI; Launcher gebaut; RVZ-Import 179/179 byteidentisch ([08](08-WINDOWS-ROM-CONTROLLER.md)) | Launcher nie visuell bedient; kein Modulbau im Launcher; kein Paket |
| 7 | Analoge Schultertaste, Belegung | Produktseite offen | Halb- und Voll-R unterschieden (0 gegen 542,793 Einheiten) ([05](05-FIFO-UND-FLUDD.md)) | reale Controller, Belegungsoberfläche, Totzonen, Tastatur/Maus, Hotplug |
| 8 | Originalgetreu, Speichern/Laden | Kern trägt, jetzt nativ | erster Shine, Save/Load, Neustart mit 1 Shine ([06](06-ERSTER-SHINE.md)); **Ton gemessen**: keine Zeitbasisabweichung, 108,8 s abtastwertgleich zum Referenzkern, Tempo innerhalb 0,3 % zur Filmrate auf der Disc ([12](12-TON.md)) | Hörprobe; echter Ausgabeweg (cubeb/WASAPI); Spielverlauf jenseits des Anfangs |
| 9 | Import eigener Kopie | Importteil erledigt | Python-Importer und Launcher-Import byteidentisch; RVZ-Leser an der echten Kopie belegt ([09](09-DOL-BEFUNDE.md)) | automatischer Modulbau nach der Auswahl, Fortschritt, Fehlermeldungen |

## Arbeitspakete

| WP | Gegenstand | Stand | Beleg |
|---|---|---|---|
| WP0 | Absicherung | teilweise | CI mit Tests und Patch-Prüfung (`checks.yml`, `scripts/check_patches.py`); Eingabefolgen als Fixtures unter `tools/acceptance/fixtures/`; dieses Dokument als Matrix. Offen: restliche Diagnoseskripte aus `build/` des Auftraggebers |
| WP1 | Ton | **gemessen** | [12-TON.md](12-TON.md); offen: Hörprobe, echter Ausgabeweg, DSP-LLE |
| WP2 | Toolchain-Paket, Modulbau im Launcher | nicht begonnen, **nicht mehr blockiert** | die Vorfrage aus [13](13-STATISCHER-KERN.md) ist mit [16](16-RUECKWEG.md) beantwortet |
| WP3 | Controller | nicht begonnen | — |
| WP4 | Launcher, Windows-Anwendung | teilweise | [07](07-ANZEIGE.md), [08](08-WINDOWS-ROM-CONTROLLER.md) |
| WP5 | Stabilität | teilweise | Stapeltiefe über 30.000 Frames gemessen ([11](11-FRAMERATE-SPIKE.md)); Dauerlauf offen |
| WP6 | Abnahmelauf | **Grundgeruest steht** | `tools/acceptance` mit drei Szenarien; `boot` (10/10), `spielstart` (11/11) und `nativ` (8/8) am echten Spiel bestanden, 19 Tests ohne Spielkopie ([README](../tools/acceptance/README.md)) |
| WP7 | Adressbasis | **erledigt** | `tools/symbols`, 12.573/12.573 Bezeichner gegengeprüft ([09](09-DOL-BEFUNDE.md)) |
| WP8 | 16:9 im Rekompilat | **Schritte 1–4 belegt** | `tools/widescreen`, gebackenes DOL ohne SMC-Rückfall, Bildabnahme an Projektion und Bild ([15](15-WIDESCREEN-ABNAHME.md)); offen: Culling, Effekte, Filme |
| WP9 | Ultrawide | nicht begonnen | — |
| WP10 | HUD, Menüs, Sequenzen | nicht begonnen | — |
| WP11 | Filme | Befund liegt vor | die Filmprojektion ist vom Widescreen-Code unberührt, bei 16:9 also gestreckt ([15](15-WIDESCREEN-ABNAHME.md)) |
| WP12 | Feinschliff | nicht begonnen | — |
| WP13 | Framerate-Spike | **abgeschlossen** | [11-FRAMERATE-SPIKE.md](11-FRAMERATE-SPIKE.md) |
| WP14 | Framerate-Umsetzung | wartet auf Entscheidung | PLAN 5.4 |
| WP15 | 60-FPS-Modus (optional) | zurückgestellt | Entscheidung 6 im Plan |
| WP16 | Abschluss | nicht begonnen | — |

## Die Grundsatzfrage ist beantwortet

[13-STATISCHER-KERN.md](13-STATISCHER-KERN.md) hatte gemessen, dass das
rekompilierte Modul höchstens 0,18 % der Gasttakte ausführt, und die Frage vor
WP2 gestellt. [16-RUECKWEG.md](16-RUECKWEG.md) beantwortet sie: Der Rückweg
fehlte schlicht — der Ersatz-JIT betrat seinen Dispatcher und kehrte nie
zurück. Mit `patches/recompcore-rueckweg.patch` fällt sein Anteil an den
Gasttakten von **99,99 % auf 0,015 %**, und beide Abnahmeszenarien bestehen
weiter. Ein nativer Port ist mit diesem Unterbau möglich.

Zwei Punkte bleiben offen und sind die nächsten Schritte:

1. **Richtigkeit.** Der Lockstep-Verifizierer schaltet ab, weil das Modul
   `ppc_set_mem_write_journal` nicht exportiert. Solange das so ist, ist der
   Rückweg ausdrücklich zu schalten (`STATICRECOMP_YIELD=1`) und nicht
   Voreinstellung.
2. **Geschwindigkeit.** Nativ läuft das Spiel derzeit halb so schnell wie mit
   dem Ersatz-JIT — 7,5 Gasttakte je Dispatch, die Burst-Schleife leistet je
   Dispatch Arbeit, die je Burst genügen würde.

Die Frage an ModernGekko ([14](14-FRAGE-AN-MODERNGEKKO.md)) bleibt sinnvoll,
hat aber einen anderen Inhalt: nicht mehr „ist das der vorgesehene Zustand",
sondern „hier ist ein Patch — ist das der beabsichtigte Weg?".

## Belegprotokolle

| Dokument | Gegenstand |
|---|---|
| [01](01-MACHBARKEIT.md) | Architekturentscheidung: statische Recompilation, keine Decompilation |
| [03](03-WIDESCREEN.md) | Widescreen über den spielseitigen Gecko-Code, 25 Stellen im RAM |
| [04](04-GRAFIKDIAGNOSE.md) | CPU-, Renderer- und Sampling-Vergleiche; kein Grafikfix freigegeben |
| [05](05-FIFO-UND-FLUDD.md) | FLUDD, analoge Schultertaste, FIFO-Diagnose |
| [06](06-ERSTER-SHINE.md) | erster Boss, erster Shine, Save/Load über einen Neustart |
| [07](07-ANZEIGE.md) | interne Skalierung und Ausgabeauflösung getrennt |
| [08](08-WINDOWS-ROM-CONTROLLER.md) | RVZ-Import im Launcher, Controller-Ist-Zustand |
| [09](09-DOL-BEFUNDE.md) | DOL-Aufbau, Symbolkarte, Widescreen ins DOL gebacken |
| [10](10-KOPFLOSER-PRUEFSTAND.md) | kopfloser Prüfstand, Arena und Stapel, Gecko gegen eingebacken |
| [11](11-FRAMERATE-SPIKE.md) | Framerate-Spike: Zuordnung, Zwischenbild, Schnitte |
| [12](12-TON.md) | Ton gemessen |
| [13](13-STATISCHER-KERN.md) | wie viel wirklich aus dem Rekompilat läuft |
| [14](14-FRAGE-AN-MODERNGEKKO.md) | die daraus folgende Frage an ModernGekko, vorbereitet |
| [15](15-WIDESCREEN-ABNAHME.md) | Widescreen an Projektion und Bild abgenommen |
| [16](16-RUECKWEG.md) | der Rückweg in den statischen Kern: gebaut, gemessen, abgenommen |

Die frühere Chronik dieses Dokuments ist in die Matrizen oben aufgegangen. Was
darunter folgt, sind die Messwerte der Windows-Sitzungen; sie bleiben als
Beleg stehen.

## Umgebung

Alles auf einem Rechner verifiziert (Windows 11 Pro 26200, 16 logische Kerne):

| Werkzeug | Version | Herkunft |
|---|---|---|
| MSVC `cl.exe` | 19.44.35228 (Toolset 14.44.35207) | bereits installiert |
| Windows SDK | 10.0.26100.0 | bereits installiert |
| CMake | 4.4.3 | nachinstalliert (winget, user scope) |
| LLVM / clang-cl | 20.1.8 | nachinstalliert (offizielles Release nach `ref/llvm`) |
| Ninja | 1.13.2 | bereits installiert |
| Python | 3.14.7 | bereits installiert |

## Verifizierte Ergebnisse

### Werkzeugkette (Meilenstein 2)

| Gegenstand | Ergebnis |
|---|---|
| DolRecomp, C-Backend, MSVC | gebaut; **ctest 19/19 bestanden** |
| DolRecomp, LLVM-Backend, clang-cl | gebaut (`dolrecomp.exe`, 42.674.176 Bytes); Testsuite **noch nicht** gelaufen |
| ModernGekko, MSVC | gebaut, 1888 Ziele; `ModernGekko.exe`, `moderngekko-run.exe`, `moderngekko-port.exe` |
| ModernGekko, ctest | **49/52 bestanden.** Die 3 Ausfälle (`fullbench`, `fuzzer`, `zstreamtest`) sind Testziele der vendorierten zstd-Bibliothek mit Status "Not Run" — sie werden von diesem Build gar nicht erzeugt. Alle ModernGekko-eigenen Tests sind grün. |
| `dolphin-tool` (Disc-Werkzeug) | gebaut; hängt nicht am Standardziel und wird separat gebaut |

Reproduzierbar über [../scripts/bootstrap.ps1](../scripts/bootstrap.ps1) und
[../scripts/build.ps1](../scripts/build.ps1).

### Datenimport (Anforderung 9)

| Gegenstand | Ergebnis |
|---|---|
| Eigene Tests | **12/12 bestanden** gegen ein synthetisches GameCube-Abbild |
| Echte Kopie, Erkennung | `GMSE01`, Revision 0, NTSC-U, "Super Mario Sunshine" |
| Echte Kopie, Größe | 1.459.978.240 Bytes — wie erwartet |
| Echte Kopie, SHA-256 | `67cec163…3e51d` — **stimmt überein** |
| Extraktion | 174 Dateien plus `main.dol` (4.128.928 Bytes) |

Die Prüfsumme war zuvor aus dem SunPad-Projekt übernommen und als ungeprüft
markiert. Sie ist jetzt an einer echten Kopie bestätigt.

Die Vorlage lag als **RVZ** vor (1.050.830.424 Bytes) und wurde mit dem
mitgebauten `DolphinTool` nach ISO gewandelt. Der Importer lehnt komprimierte
Container bewusst mit Hinweis ab, statt sie als defekt zu melden.

### Statische Recompilation (Meilenstein 3, Teil 1)

| Gegenstand | Ergebnis |
|---|---|
| Aufruf | `--gamecube --cpu gekko --backend llvm --runtime moderngekko --game-id GMSE01 -j16` |
| Ergebnis | Exit 0 |
| Dauer | 1.637,7 s (rund 27 Minuten) |
| Erzeugt | 16.618 LLVM-Objekt-Chunks, dazu ThinLTO-Zusammenfassungen |
| Umfang | 4,1 GB |
| SMC-Warnung | 139 Einträge in `generated_smc.txt`, überwiegend Einzelinstruktionen |

Die SMC-Stellen sind selbstmodifizierender Code, den die Laufzeit über den
Interpreter abwickelt. 139 Einträge sind wenig; die Leistungswirkung ist noch
nicht gemessen.

### Modulbau (Meilenstein 3, Teil 2)

Über das dafür vorgesehene Werkzeug `moderngekko-port build`, wie es auch das
offizielle `ModernGekko-Template` aufruft:

| Gegenstand | Ergebnis |
|---|---|
| Aufruf | `build <game-root> --backend c --toolchain clang --output <pfad>` |
| Ergebnis | Exit 0, 231 Ziele |
| Dauer | 1.231,6 s (rund 20 Minuten) |
| Erzeugt | `gGMSE01_recomp.dll`, 98.255.360 Bytes |
| Zwischenschritt | 224 C-Dateien, 230 MB |

Die 224 C-Dateien decken sich mit der Angabe des Referenzports SunPad für
GMSE01 ("221 C chunks and about 220 MiB before compilation"). Das bestätigt,
dass das **C-Backend** der passende Pfad ist.

### Datenimport gegen eine Referenz geprüft

Das Ergebnis des eigenen Importers wurde Byte für Byte mit einer Extraktion
durch Dolphins `DolphinTool` verglichen: **179 von 179 Dateien identisch**,
einschließlich `sys/boot.bin`, `bi2.bin`, `apploader.img`, `fst.bin` und
`main.dol`.

`moderngekko-port inspect` erkennt die importierte Kopie:
Super Mario Sunshine, `GMSE01`, GameCube (Gekko), Entry `0x8000522c`.

## Offen

### Unmittelbar als Nächstes

- **Eingabe.** Controller- und Tastaturbelegung sind ungeprüft; ohne sie kommt
  man nicht über die Eröffnungssequenz hinaus.
- **Ton.** Ob Audio ausgegeben wird, ist nicht überprüft.
- **Spielstand.** Speichern und Laden sind ungeprüft.

### Noch nicht begonnen

| Anforderung | Stand |
|---|---|
| 1 Unbegrenzte Framerate | nicht begonnen; größtes technisches Risiko |
| 2 Hohe Auflösungen | nicht begonnen |
| 3 Echtes Widescreen | nicht begonnen; Ausgangspunkt vorhanden (siehe unten) |
| 4 HUD, Menüs, Zwischensequenzen | nicht begonnen |
| 5 Windows-Shell | nicht begonnen; ModernGekko liefert `PlatformWin32` |
| 7 Analoge Schultertaste | nicht begonnen |
| 8 Originalgetreues Verhalten | nicht prüfbar, solange nichts läuft |

### Erster Start unter Windows (Meilenstein 3, Teil 3)

Nach Behebung des unten beschriebenen Upstream-Versatzes:

| Gegenstand | Ergebnis |
|---|---|
| Modul geladen | `[staticrecomp] module loaded: gGMSE01_recomp.dll entry=0x8000522C` |
| Modulgröße | 91.837.952 Bytes |
| Fenstertitel | `ModernGekko - Super Mario Sunshine [GMSE01] \| 30.0 FPS` |
| Bildrate | Anlauf 0 → 17 → **30,0 FPS**, danach über mehrere Messpunkte stabil |
| Bild | Bildschirmabzug über das Automationsprotokoll erzeugt (394.199 Bytes PNG) |

30,0 FPS ist Sunshines native Bildrate, das Spiel läuft also mit Volltempo. Der
Abzug zeigt die gerenderte Eröffnungssequenz mit Himmel, Wolken, Linsenreflexen
und Vordergrundgeometrie — kein Platzhalterbild.

### Eingabe und Speichern (Meilenstein 3, Teil 4)

Über das Automationsprotokoll (`pad_frames`) wurden Controllereingaben
eingespeist und der Fortschritt mit Bildschirmabzügen belegt:

| Schritt | Eingabe | Beobachtet |
|---|---|---|
| 1 | — | Eröffnungssequenz, Himmel mit Flugzeug |
| 2 | `start` | Titelbildschirm: Logo, Palme, Regenbogen, Startaufforderung |
| 3 | `a` | Dateiauswahl mit Mario am Strand, Blöcken A/B/C und Options-Schild |
| 4 | `a` | Memory-Card-Abfrage bestätigt |
| 5 | — | Datenauswahl mit drei freien Plätzen |

Damit ist belegt:

- **Eingabe wirkt** — jeder Tastendruck führte zum erwarteten Bildschirmwechsel.
- **Rendering ist korrekt** — Figurenmodell, Text, Wasser, Schatten, Transparenz
  und Menügrafik werden sauber gezeichnet.
- **Speichern arbeitet** — beim Bestätigen wurde eine Memory-Card-Datei von
  57.408 Bytes im Benutzerverzeichnis angelegt, und der anschließende Bildschirm
  zeigt die Datenauswahl.

Die Bildrate blieb während der gesamten Sequenz bei 29,9 bis 30,0 FPS.

Über längere Standzeit wechselt Mario in die Ruhe-Animation (schlafend) und bei
erneuter Eingabe zurück — die Animationszustände laufen also über die Zeit
korrekt weiter.

**Ausdrücklich noch nicht überprüft:**

- **Ton.** Es liegt weder eine hörbare Prüfung noch ein Logeintrag vor, der
  Audioausgabe belegen oder widerlegen würde.
- **Eigentliches Spielgeschehen.** Die Auswahl eines Speicherplatzes ist über
  das Automationsprotokoll nicht gelungen; die Eingaben kommen an, treffen aber
  die Cursor-Mechanik der Dateiauswahl nicht. Das ist eine Grenze der blinden
  Steuerung, kein belegter Fehler des Ports. Am schnellsten ist das mit
  Controller oder Tastatur von Hand zu prüfen.
- **Laden** eines zuvor gespeicherten Fortschritts.

### Auflösung: Ist-Zustand vermessen (Anforderung 2)

Die Skalierung wird über `<user-dir>/config.ini`, Schlüssel `resolution=`,
gesteuert und in Dolphins ganzzahligen EFB-Faktor (1 bis 12) übersetzt. Drei
Stufen wurden gefahren und die tatsächliche Bildgröße aus dem PNG-Kopf gemessen:

| `resolution=` | Faktor | tatsächlich gerendert | Bildrate |
|---|---|---|---|
| `640x528` | 1 | 640 × 477 | 30,0 FPS |
| `1920x1080` | 3 | 1920 × 1430 | 30,0 FPS |
| `3840x2160` | 6 | 3840 × 2859 | 30,0 FPS |

**Was funktioniert:** Die interne Renderauflösung skaliert exakt linear, und
4K intern läuft auf dieser Hardware ohne Einbruch bei vollen 30 FPS.

**Was fehlt.** Die Anforderung verlangt, interne Render- und Ausgabeauflösung zu
trennen. Der Ist-Zustand leistet das nicht:

1. **Die Bezeichnungen führen in die Irre.** `1920x1080` erzeugt kein
   1920 × 1080, sondern 1920 × 1430; `3840x2160` erzeugt 3840 × 2859. Es sind
   reine Faktor-Etiketten, keine Ausgabeauflösungen. Die Datei sagt das im
   Kommentar zwar selbst ("Dolphin's internal render target, not the window
   size"), die Werte behaupten aber etwas anderes.
2. **Es gibt keine Steuerung der Ausgabeauflösung.** Ausgabe ist schlicht die
   Fenstergröße; native Displayauflösung, 1080p, 1440p und 4K als *Ausgabe*
   sind nicht wählbar.
3. **Kein frei einstellbarer Skalierungsfaktor** jenseits der ganzzahligen
   EFB-Stufen.

Das Seitenverhältnis liegt durchgehend bei rund 1,34 (4:3). Das ist die
Ausgangslage, die Anforderung 3 zu ändern hat.

### Upstream-Defekt: CPU-ABI-Versatz in ModernGekko

Das gebaute Modul wurde von der Laufzeit zunächst abgewiesen:

```
initialization failed: native module was rejected: CPU ABI mismatch
```

Das ist kein Fehler dieses Projekts. Der vorgesehene Einstiegspunkt
`moderngekko-port run` scheitert identisch, weil er intern denselben Aufruf
absetzt, und das offizielle `ModernGekko-Template` fährt dieselbe Pipeline.

**Gemessene Ursache.** Ein kleines Testprogramm gegen beide Header:

| Header | CPU-ABI | `sizeof(CPUState)` |
|---|---|---|
| GXRuntime (das Modul baut damit) | 3 | 3528 Bytes |
| ModernGekko (die Laufzeit fordert das) | 4 | 3536 Bytes |

Der Unterschied ist genau ein Feld, `int64_t cycle_budget` — die 8 Bytes. Die
übrigen scheinbaren Abweichungen im Header sind nur Typ-Aliase (`u32` gegen
`uint32_t`). Dazu passt, dass der LLVM-Emitter `func_..._budget` und
`ppc_native_region_available` erzeugt: Beides gehört zu dieser neueren ABI.

**Lage im Upstream.** ModernGekkos Standardbranch ist `master`; dessen HEAD ist
`5417826c` — genau unser Pin, es gibt keinen neueren Stand. Sein
Vendor-Submodul zeigt auf RecompCores Branch `moderngekko-vendor` (ABI 3).
RecompCore pflegt daneben `moderngekko-runtime` (`c6a600eb`) mit ABI 4 und
`cycle_budget`.

Damit stehen zwei unvollständige Stände nebeneinander:

- `moderngekko-vendor` baut, erzeugt aber Module, die die Laufzeit ablehnt.
- `moderngekko-runtime` hat die passende ABI, **übersetzt aber selbst nicht**:
  `StaticRecompCore::GetExceptionCheckTarget` ist als `override` deklariert,
  obwohl `JitBase` die Methode nicht kennt (MSVC: C3668).

**Vorgehen hier.** Das Vendor-Submodul wird auf `c6a600eb` gesetzt, und das
gegenstandslose `override` wird entfernt — die Methode kommt im gesamten
`Source/`-Baum genau einmal vor und hat keinen Aufrufer. Beides ist in
[../scripts/bootstrap.ps1](../scripts/bootstrap.ps1) verankert; die Patches
liegen unter [../patches/](../patches/).

### Angewandte Patches

| Patch | Ziel | Grund |
|---|---|---|
| `dolrecomp-msvc-popcount.patch` | `ref/DolRecomp` | `__builtin_popcountll` kennt MSVC nicht; ersetzt durch `std::bitset::count` (keine Annahme über den Befehlssatz) |
| `recompcore-abi-gaps.patch` | `ref/ModernGekko/vendor/dolphin` | zwei Lücken im Branch `moderngekko-runtime` (siehe unten) |

Der zweite Patch schließt:

1. **Gegenstandsloses `override`.** `StaticRecompCore::GetExceptionCheckTarget`
   ist als `override` deklariert, obwohl `JitBase` die Methode nicht kennt.
   Sie kommt im gesamten `Source/`-Baum genau einmal vor und hat keinen
   Aufrufer, das `override` entfällt daher ersatzlos.
2. **Fehlende Inline-Helfer in GXRuntime.** DolRecomps Emitter erzeugt stets
   die `_inline`-Formen von `ppc_fp_available`, `ppc_psq_load` und
   `ppc_psq_store`. GXRuntimes Kopie der CPU-Laufzeit deklarierte nur die
   Nicht-Inline-Varianten. Die drei Wrapper werden ergänzt und leiten weiter —
   laut Kommentar in `DolRecomp/src/cpu/cpu.h` ist genau das der Vertrag: Die
   hostende Laufzeit stellt die `_inline`-Formen bereit, ein Schnellpfad ist
   optional.

**Gemeinsame Wurzel.** GXRuntimes `include/core/cpu.h` ist eine veraltete
Dublette von `DolRecomp/src/cpu/cpu.h`. Beide tragen denselben Include-Guard
`DOLRECOMP_CPU_H`, sodass je Übersetzungseinheit nur einer wirkt. DolRecomps
eigene Fassung ist die vollständige: Sie enthält `cycle_budget` (ABI 4),
GXRuntimes Erweiterung `external_pointer` und alle drei Inline-Helfer. Die
Pins belegen den Versatz unmittelbar — `moderngekko-runtime` pinnt DolRecomp
`1bec3554`, dessen Emitter die psq-Inlines erzeugt, während das mitgelieferte
GXRuntime sie nicht kennt.

Zusätzlich baut ModernGekko mit
`/D_SILENCE_CXX20_OLD_SHARED_PTR_ATOMIC_SUPPORT_DEPRECATION_WARNING`, weil der
Baum mit `/WX` übersetzt und `RelocationAliases.cpp` das unter C++20 veraltete
`std::atomic_store_explicit` für `shared_ptr` nutzt. Die MSVC-Vorgabe
`/DWIN32 /D_WINDOWS /EHsc` muss dabei mitgeführt werden, sonst scheitert
`<chrono>` an C4530.

### Bekannte Hindernisse

1. **Keine Symbol-Map für `GMSE01`.** Die US-Disc enthält keine `mario.MAP`
   (nachgeprüft: 174 Dateien, keine Symboldatei). Hooks binden ohnehin an rohe
   Adressen, aber jede Hook-Stelle muss erst ermittelt werden. Ausgangspunkte:
   Dolphins `GMSE01.ini` mit adressbasierten Codes einschließlich zweier
   `$Widescreen`-Einträge, und die CC0-Symbole der Decompilation für `GMSJ01`
   (namensgleich, adressverschieden). Siehe
   [01-MACHBARKEIT.md](01-MACHBARKEIT.md), Abschnitt 2.1.
2. **Widescreen-Fehlerbild.** Der Referenzport dokumentiert für Dolphins
   generischen Widescreen-Hack bei Sunshine abgetrennte Schatten,
   Projektionsnähte und duplizierte Geometrie. Der generische Hack ist damit
   kein gangbarer Weg.
3. **Framerate-Entkopplung ungeprüft.** Ob sich der Bildabschluss vom emulierten
   VI-Interrupt lösen lässt, ist offen.

## Was dieses Projekt nicht enthält

Keine Spieldaten, keine Symbole, keine rekompilierten Module. Disc-Abbild,
extrahiertes Dateisystem, generierter Code und gebaute Module bleiben lokal und
sind über `.gitignore` ausgeschlossen. Module aus rekompiliertem Spielcode sind
abgeleitete Werke und dürfen nicht weitergegeben werden.
