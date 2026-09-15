# Plan: Weiterführung des Sunshine-Ports

Stand: 2026-09-14. Dieses Dokument ist ein **Plan**, kein Statusbericht. Für
diesen Plan wurde am Port nichts weitergeführt, gebaut oder getestet. Grundlage
sind die Dokumente 01 bis 08, HANDOFF.md, die Skripte und Patches im
Repository sowie eine Nachprüfung der Upstream-Quellen und der Symbollage, die
in Abschnitt 9 mit Quelle festgehalten ist. Aussagen, die nicht geprüft
wurden, sind als Annahme oder „zu prüfen" markiert.

Leseanleitung:

| Abschnitt | Inhalt |
|---|---|
| 0 | Zielbild: was „nativer Windows-Port" hier bedeutet, Produktform |
| 1 | Stand je Anforderung in einer Tabelle |
| 2 | Leitentscheidungen, die der Plan vorschlägt |
| 3 | Reihenfolge, Releases, Abhängigkeiten |
| 4 | Arbeitspakete mit Ziel, Schritten, Beleg und Aufwandsklasse |
| 5 | Anforderung 1 (Framerate) gesondert |
| 6 | Entscheidungen, die der Auftraggeber treffen muss |
| 7 | Risiken und Gegenmaßnahmen |
| 8 | Erster konkreter Schritt der nächsten Sitzung |
| 9 | Für diesen Plan neu geprüfte Fakten |

Unverändert bleiben die getroffenen Architekturentscheidungen aus
`01-MACHBARKEIT.md`: statische Recompilation mit DolRecomp und ModernGekko,
keine Decompilation, kein Aurora, Zielrevision GMSE01 Rev 0, keine Spieldaten
im Repository, GPL-3.0-or-later.

---

## 0. Zielbild: nativer Windows-Port

Ziel des Auftrags ist ein **nativer Port von Super Mario Sunshine für Windows
x86-64**, keine Emulatorinstallation mit Spielabbild. Jede Phase dieses Plans
wird an diesem Ziel gemessen. Was „nativ" in der gewählten Architektur
bedeutet und wo ihre Grenze liegt, steht hier ausdrücklich, damit es nicht
stillschweigend unterschiedlich verstanden wird.

### 0.1 Was heute nativ ist und was nicht

| Schicht | Stand | Folge für den Plan |
|---|---|---|
| Spiellogik (CPU) | nativ: statisch nach x86-64 rekompiliert (224 C-Dateien, `gGMSE01_recomp.dll`) | Ausnahmen laufen im Interpreter: 139 SMC-Stellen und die vom Gecko-Code veränderten Chunks. WP8 holt die Widescreen-Chunks in den nativen Code, WP5 misst den Rest |
| Grafik | der GX-Befehlsstrom des Spiels wird von Dolphins VideoCommon auf Vulkan/OpenGL abgebildet | die Flipper-GPU als Laufzeitbibliothek. Ein Renderer auf Quellcodeebene (Aurora) setzt dekompilierten Spielcode voraus, den es für GMSE01 nicht gibt (01-MACHBARKEIT, 1.1 und 1.2). Diese Grenze gilt für jeden Recomp-Port, auch Zelda64Recomp und SunPad |
| Ton | DSP-HLE und Audiobackend der Laufzeit | native Nachbildung des DSP; Abnahme in WP1 |
| System (VI, DVD, Speicherkarte, Timer, Eingabe) | Laufzeitbibliothek mit Dolphin-Abstammung | für den Nutzer unsichtbar, solange die Produktform stimmt (0.2) |
| Fenster und Launcher | `DolphinNoGUI`-Plattform Win32 (gepatcht), ImGui-Launcher | tragen noch Laufzeitnamen: Fensterklasse `DolphinNoGUI` (in `windows_display_probe.py` belegt), Dolphin-INIs im Profil |

Das ist dieselbe Bedeutung von „nativ", die Zelda64Recomp und SunPad
verwenden: nativer Spielcode plus eine Laufzeitbibliothek für die
Hardware-Schichten. Wer auch GPU und DSP ohne Nachbildung will, braucht eine
Decompilation; die liegt für die US-Fassung nicht vor. Diese Entscheidung wird
nicht neu aufgerollt.

### 0.2 Produktform

Aus „Windows-Anwendung" folgen Kriterien, die bisher nur verstreut standen. Sie
gehören zur Abnahme von v0.2 und werden in WP4 umgesetzt:

1. **Eine Anwendung mit eigenem Namen.** `SunshineRecomp.exe` startet, wählt
   die Spielkopie, richtet ein und spielt. Runner und Werkzeuge sind interne
   Bestandteile. Fenstertitel, Fensterklasse, Protokoll- und
   Absturzmeldungen ohne „ModernGekko" oder „Dolphin". Die CMake-Optionen
   dafür existieren (`MODERNGEKKO_FRONTEND_NAME`,
   `MODERNGEKKO_DEFAULT_WINDOW_TITLE`, `MODERNGEKKO_RUNNER_OUTPUT_NAME`); die
   Fensterklasse ist noch fest codiert.
2. **Eigene Einstellungen.** Der Nutzer sieht keine Dolphin-INIs. Anzeige,
   Controller und Ton werden in der Anwendung gesetzt und intern übersetzt;
   das ist die in WP3 gewählte Technik.
3. **Keine Emulatorbedienung.** Kein Netplay, keine Cheat-Verwaltung, keine
   Spieleliste. Schnellspeichern (Savestates) bleibt als Komfortfunktion mit
   eigenem Namen.
4. **Verhalten wie eine Windows-Anwendung.** Installer, Startmenüeintrag,
   DPI-Bewusstsein, randloses Vollbild, Alt+Tab ohne Absturz, Verhalten bei
   Fokusverlust wählbar, Absturzbericht.
5. **Start ohne Ruckler.** Shader werden beim ersten Start mit
   Fortschrittsanzeige vorkompiliert (die Laufzeit wartet bereits auf Shader
   vor dem Start; Kompilierungsmodus in WP12 zu prüfen), das Modul liegt im
   Cache; der zweite Start ist sofort.
6. **Alles lokal.** Spielkopie, extrahierte Daten und Modul bleiben auf dem
   Rechner. Ob das Modul mitgeliefert werden darf, ist eine Entscheidung des
   Auftraggebers (Abschnitt 6, Nummer 10) und verändert WP2 grundlegend.

### 0.3 Was dem Ziel nicht dient

Aurora als Renderer, Android, andere Regionen, Netplay und die
RetroAchievements-Elemente der Laufzeit bleiben außerhalb des Umfangs.

---

## 1. Stand je Anforderung

Zusammengezogen aus 02 bis 08. „Belegt" heißt: tatsächlich ausgeführt und
dokumentiert. Alles andere ist offen.

| # | Anforderung | Belegt | Offen | Einordnung |
|---|---|---|---|---|
| 1 | Unbegrenzte Framerate | nichts | alles; Architektur unentschieden; Bildabschluss hängt am VI-Interrupt | größtes technisches Risiko, reine Neuentwicklung |
| 2 | Hohe Auflösung, getrennte Ausgabe | `internal_scale` 1–12 und `output_resolution` getrennt gemessen (796x448 bzw. 2389x1344 intern bei 1280x720 Fenster); randloses Vollbild 1920x1080 und 3440x1440; Rückkehr zur Fenstergröße | HiDPI, Mehrmonitor, Launcher-Bedienung, Kantenglättung/Filterung als Option | weitgehend erledigt |
| 3 | Echtes Widescreen | 16:9 über den spielseitigen Gecko-Code, 25/25 Patchstellen im RAM nachgewiesen; zusätzliche Sicht ohne Streckung gemessen (Marker 8,54 % vs. 8,63 % Breite) | Filme (Balken/Streckung), vollständige HUD-, Effekt- und Culling-Abnahme, 21:9 und 32:9; geänderte Chunks laufen im SMC-Fallback | Grundlage steht, Abnahme fehlt |
| 4 | HUD-Anker, Menüs, Sequenzen | nur mittelbar über die 2D-Konstanten des Gecko-Codes | systematisch nichts; Adressbasis fehlte bislang | nicht begonnen |
| 5 | Windows-Anwendung | Win32-Fenster, randloses Vollbild, Alt+Enter, DPI-Kontext; Launcher gebaut; RVZ-Import im Launcher 179/179 Dateien byteidentisch | Launcher nie visuell bedient; kein Modulbau im Launcher; kein Paket/Installer; Netplay-Elemente ohne Auftrag | halb |
| 7 | Analoge Schultertaste, Belegung | Halb- und Voll-R per Automation unterschieden (0 gegen 542,793 Einheiten Weg) | reale Controller, Belegungsoberfläche, Totzonen, Empfindlichkeit, Invertierung, Tastatur/Maus, Hotplug | Produktseite nicht begonnen |
| 8 | Originalgetreu, Speichern/Laden | erster Shine, reguläres Save/Load, Neustart mit 1 Shine, Delfino Plaza steuerbar | **Ton nie geprüft**; Spielverlauf jenseits des Anfangs; R-Dauerplateau ungeklärt (identisch unter JIT64, also kein Recomp-Fehler belegt) | Kern trägt, Abdeckung klein |
| 9 | Import eigener Kopie | Python-Importer und Launcher-Import byteidentisch zu DolphinTool | automatischer Modulbau nach der Auswahl, Fortschrittsanzeige, verständliche Fehlermeldungen für andere Fassungen | Importteil erledigt |

Querschnittsbefunde, die den Plan prägen:

1. **Adressbasis.** Die US-Disc hat keine Symbol-Map. Neu geprüft: das
   GPL-3.0-Projekt BetterSunshineEngine liefert eine Symbolliste für GMSE01
   (`maps/us.map`, rund 3.500 Einträge, Funktionen und Daten; Details in
   Abschnitt 9). Damit fällt die größte Hürde für die Anforderungen 1, 3 und 4
   deutlich kleiner aus als in 01-MACHBARKEIT angenommen.
2. **Belege liegen nur lokal.** Eingabesequenzen für Dateiauswahl, FLUDD,
   Bosskampf und Speichern sowie die gepaarten Checkpoints liegen unter
   `build/` auf dem Rechner des Auftraggebers, nicht im Repository. Ein
   Plattenfehler löscht die Reproduzierbarkeit.
3. **Patchstapel wächst.** Sechs Patches mit 1.027 Zeilen gegen drei
   Upstream-Bäume; jedes weitere Arbeitspaket an Launcher, Anzeige oder
   Laufzeit vergrößert ihn.
4. **Dokumentation.** Acht Dokumente plus HANDOFF und STATUS mit
   überlappenden „Neuester Stand"-Absätzen. Für Außenstehende ist der aktuelle
   Stand nur mühsam auffindbar.

---

## 2. Leitentscheidungen (Vorschlag)

### 2.1 Erst ein spielbares Produkt, dann Modernisierung, mit einer Ausnahme

Die Präzisierung des Auftraggebers vom 2026-09-10 (native Windows-Anwendung,
alle Controller, spielbar nach Auswahl einer eigenen ROM) ist die
Produktdefinition. Dafür fehlen vor allem Ton (ungeprüft), der automatische
Modulbau samt Toolchain beim Endnutzer und die Controller-Oberfläche. Diese
Punkte kommen vor Ultrawide, HUD und Framerate.

Ausnahme: Der **Framerate-Spike** (WP13) wird früh und zeitlich begrenzt
eingeschoben. Sein Ergebnis entscheidet über die Architektur der
Präsentationsschicht und kann Anzeige (WP12) und Widescreen (WP8, WP9)
beeinflussen. Ohne diese Entscheidung würde später doppelt gebaut.

### 2.2 Forks statt Patchdateien

Die drei Upstream-Bäume werden als Forks unter dem GitHub-Konto des
Auftraggebers geführt (ModernGekko, RecompCore auf Branch
`moderngekko-runtime`, DolRecomp), jeweils mit einem Branch `sunshine`, auf
dem die bisherigen Patches als Commits liegen. `bootstrap.ps1` klont die Forks
auf feste Commits statt Upstream plus Patches. Vorteile: nachvollziehbare
Historie je Änderung, Upstream-PRs per `git format-patch` weiterhin möglich,
kein Patch-Reihenfolge-Problem mehr. Upstream hat sich seit den Pins nicht
bewegt (Abschnitt 9); ein Rebase ist erst nötig, wenn Upstream etwas liefert,
das der Port braucht.

Lizenzfolge: Die Forks müssen spätestens mit dem ersten verteilten Binary
öffentlich sein (GPL-3.0). Bis dahin dürfen sie privat bleiben.

### 2.3 Widescreen wird Teil des Rekompilats, nicht Laufzeit-Gecko

Der Gecko-Code läuft heute über Dolphins Codehandler, und die von ihm
veränderten Chunks (`802C9600–802CD600`, `80361600–80365600`) laufen im
SMC-Fallback, also im Interpreter. Ziel: die 13 direkten Schreibungen und die
zwölf Code-Injektionen werden **vor** der Recompilation in den DOL
eingebracht, sodass der native Code bereits die Widescreen-Fassung ist.

`moderngekko-port` unterstützt bereits DOL-Patches aus `[OnFrame]` /
`[OnFrame_Enabled]` der Spiel-INI, aber nur einfache `adresse:dword:wert`-
Zeilen innerhalb bestehender Textsektionen (Abschnitt 9). Die Injektionen
brauchen zusätzlich einen Codebereich (neue oder verlängerte Textsektion) und
einen Sprung an der Einfügestelle; das ist eine kleine Erweiterung, kein
Umbau. Nachweis wie in Dokument 03: RAM-Vergleich gegen die Gecko-Variante und
Verschwinden des SMC-Fallbacks im Log.

Für Ultrawide werden die aspektabhängigen Konstanten des Codes nicht fest
eingebrannt, sondern beim Start von einem nativen Mod (Mod-ABI) aus der
Konfiguration gesetzt. Ein Codepfad für 16:9, 21:9 und 32:9.

### 2.4 Adressbasis aus `us.map`, Lücken durch JP-Übertragung

`us.map` wird mit Herkunft, Commit und Prüfsumme nach `tools/symbols/`
übernommen, in DolRecomps MAP-Format gewandelt und dem Recompiler per `--map`
übergeben. Mods binden dann an `DOLRECOMP_SYMBOL_<Name>` statt an Zahlen.
Fehlt ein benötigtes Symbol, wird es aus der CC0-Liste der japanischen
Fassung übertragen (Abschnitt 4, WP7).

### 2.5 Verifikation gehört zu jedem Arbeitspaket

- Ein reproduzierbarer **Abnahmelauf** (WP6) im Repository; jedes
  Arbeitspaket, das Laufzeit, Modul oder Mods berührt, muss ihn bestehen.
- Der in RecompCore vorhandene **Lockstep-Verifizierer** (nativer Block gegen
  Interpreter, Aktivierung per Umgebungsvariable, Abschnitt 9) wird auf der
  Abnahmestrecke eingesetzt, um Recompilationsfehler von Spielverhalten zu
  trennen.
- Belegkonvention wie bisher: JSON-Manifeste, PNG-Maße und SHA-256, lokale
  Pfade; nichts gilt als fertig ohne Beleg.

### 2.6 Dokumentation konsolidieren

`02-STATUS.md` wird zur einzigen Anforderungsmatrix (Tabelle wie in
Abschnitt 1, je Arbeitspaket fortgeschrieben). Die nummerierten Dokumente
bleiben als Belegprotokolle bestehen; neue Sitzungen ergänzen neue Nummern
statt „Neuester Stand"-Absätze in alten Dokumenten. HANDOFF verweist auf
PLAN und STATUS.

---

## 3. Reihenfolge, Releases, Abhängigkeiten

### 3.1 Phasen

```
Phase 0  Absicherung            WP0
Phase 1  Spielbar (v0.1, v0.2)  WP1 Ton, WP2 Toolchain/Modulbau, WP3 Controller,
                                WP4 Launcher/Windows, WP5 Stabilität, WP6 Abnahmelauf
         eingeschoben           WP13 Framerate-Spike (zeitlich begrenzt)
Phase 2  Anzeige (v0.3)         WP7 Adressbasis, WP8 16:9 im Rekompilat, WP9 Ultrawide,
                                WP10 HUD/Menüs/Sequenzen, WP11 Filme, WP12 Feinschliff
Phase 3  Framerate (v0.4)       WP14 Umsetzung nach Spike-Ergebnis, WP15 optional
Phase 4  Abschluss (v1.0)       WP16
```

Abhängigkeiten:

```
WP0 ──> WP6 ──> alle WPs an Laufzeit, Modul, Mods
WP2 ──> v0.2
WP7 ──> WP9, WP10, WP14 (Variante B)
WP8 ──> WP9 ──> WP10
WP13 ──> WP14; WP13 kann WP12 beeinflussen
WP1, WP3, WP4, WP5 sind untereinander unabhängig
```

### 3.2 Releases und Abnahmekriterien

| Release | Inhalt | Fertig, wenn |
|---|---|---|
| v0.1 Entwicklervorschau | Launcher-Ablauf ROM → Import → Modulbau → Spiel; Build Tools dürfen vorausgesetzt werden; 4:3 und 16:9; ein Controller | Abnahmelauf grün; Ton belegt; Ablauf am Rechner des Auftraggebers von Hand durchlaufen |
| v0.2 Spielbar | Toolchain-Paket im Lieferumfang, Controller-Oberfläche, Stabilität, Installer | frische Windows-11-VM ohne Entwicklungswerkzeuge: ROM → Spiel; drei Controllerarten belegt; 60-Minuten-Dauerlauf; wirkt als eigenständige Anwendung nach 0.2 |
| v0.3 Anzeige | 16:9 abgenommen, 21:9/32:9, HUD-Anker, Filme, HiDPI/Mehrmonitor | Bildmatrix je Seitenverhältnis; Culling-Test; Filme unverzerrt |
| v0.4 Framerate | Ergebnis aus WP13/WP14 | Messung Bildrate, Interpolationsqualität, Kameraschnitte ohne Artefakte |
| v1.0 | alle Anforderungen abgenommen, Endnutzerdokumentation, Lizenzpaket | Anforderungsmatrix vollständig „belegt" |

Aufwandsklassen in Abschnitt 4: S bis ein Tag, M zwei bis fünf Tage, L ein bis
drei Wochen, XL darüber oder offen. Das sind Größenordnungen für die
Reihenfolge, keine Zusagen.

---

## 4. Arbeitspakete

### WP0 Absicherung (S–M)

Ziel: Nichts Reproduzierbares hängt mehr an `build/`.

1. Eingabesequenzen aus den bisherigen Sitzungen (Dateiauswahl, Airstrip,
   FLUDD-Aufnahme, Bosskampf, Speichern, Neustart) als JSON-Fixtures nach
   `tools/acceptance/fixtures/` übernehmen, nach dem Muster von
   `tests/fixtures/airstrip-camera.json`. Savestates, GCI-Karten und Bilder
   bleiben lokal; ihre SHA-256 kommen in ein Manifest im Repository.
2. Alle Diagnose-Skripte, die nur unter `build/` liegen (Bosskampf-Steuerung,
   `parse_fifo.py`, Messskripte), nach `tools/diagnostics/` übernehmen.
3. GitHub Actions: `python -m unittest` und `git apply --check` aller Patches
   gegen die gepinnten Upstream-Commits (Ubuntu genügt; erkennt Drift). Der
   vollständige Windows-Build bleibt manuell auslösbar, weil LLVM rund 940 MB
   lädt.
4. Dokumentation gemäß 2.6 konsolidieren.

Beleg: CI grün; Fixtures und Manifest im Repository; STATUS als Matrix.

### WP1 Ton (S–M)

> Stand 2026-09-15: gemessen ([12-TON.md](12-TON.md)). Kein Zeitbasisfehler;
> das Rekompilat liefert 108,8 s lang abtastwertgleichen Ton wie der
> JIT-Referenzlauf, Tempo innerhalb 0,3 % zur Filmrate auf der Disc. Offen
> bleiben die Hörprobe, der echte Ausgabeweg (cubeb/WASAPI) und DSP-LLE.

Ziel: Audio belegen oder als Fehler eingrenzen. Ohne Ton kein spielbarer Port.

1. Log auf `audio backend:` prüfen. Die Laufzeit bevorzugt cubeb und fällt
   sonst still auf Null zurück (Abschnitt 9); ein stummer Lauf ist kein
   Beleg für einen Fehler.
2. Hörprobe und Aufzeichnung per WASAPI-Loopback an drei Stellen (Titel,
   Airstrip-Dialog, Plaza), jeweils bei interner Skalierung 1 und 6.
3. Tempo und Tonhöhe gegen eine Aufnahme desselben Abschnitts aus
   Dolphin-Mainline vergleichen. SunPad hatte in seinem Recomp-Core einen
   zwölffach zu schnellen Timebase; ModernGekkos Core führt die Timebase
   selbst (`AdvanceGuestTimebase`). Messen, nicht annehmen.
4. Aussetzer und Unterläufe im Log; DSP-HLE ist Standard, LLE nur als
   Vergleich bei Fehlern.

Beleg: zwei Aufnahmen (Port, Mainline), Längen- und Spektrumvergleich,
Protokoll als `docs/09-TON.md`.

### WP2 Toolchain-Paket und Modulbau im Launcher (L)

> **Vorfrage seit 2026-09-15** ([13-STATISCHER-KERN.md](13-STATISCHER-KERN.md)):
> In 37 gemessenen Läufen führt das rekompilierte Modul höchstens 0,18 % der
> Gasttakte aus; den Rest übernimmt Dolphins JIT64, der im statischen Kern
> immer mitläuft. Der Modulbau ist dabei vollständig (100 % der Textbytes).
> Bevor der Modulbau in den Launcher wandert, muss geklärt sein, welchen
> Anteil nativer Ausführung dieser Stand überhaupt vorsieht.

Ziel: Der Endnutzer wählt eine ROM und bekommt ein Modul, ohne selbst
Werkzeuge zu installieren. Module dürfen nicht verteilt werden (abgeleitetes
Werk), also muss der Bau lokal laufen.

Ist-Zustand (Abschnitt 9): `moderngekko-port build` braucht einen zur
Compile-Zeit fest verdrahteten Quellbaum (`vendor/dolphin/module-template`,
`GXRuntime`, StaticRecomp-Header), `cmake`, `ninja`, einen Compiler auf PATH
(`cl`, `clang` oder `gcc`) und `dolrecomp` neben der EXE. Der Launcher baut
nicht; der Runner sucht das Modul neben der EXE, unter
`<user>/StaticRecompModules/` oder über `STATICRECOMP_MODULE`.

Vorbehalt: Entscheidung 10 in Abschnitt 6. Wird das Modul mitgeliefert,
entfallen die Schritte 1, 2 und 4; Schritt 3 reduziert sich auf Prüfung,
Extraktion und Fortschrittsanzeige.

1. **Spike (S):** Eine selbst enthaltene Toolchain ohne Visual Studio prüfen.
   Kandidaten: llvm-mingw und `zig cc` (beide bringen Header und
   C-Laufzeit für Windows mit). Frage: Lädt ein damit gebautes Modul in der
   MSVC-gebauten Laufzeit? Die Schnittstelle ist C (`CPUState*`, Funktions-
   zeiger); ob keine CRT-Objekte die Grenze überschreiten, ist **zu prüfen**.
   Abnahme: Abnahmelauf und Lockstep bestehen, Leistung vergleichbar mit dem
   clang-cl-Modul.
2. **Paketlayout (M):** `moderngekko-port` von Compile-Zeit-Pfaden auf ein
   Verzeichnis neben der EXE umstellen (`tools/` mit dolrecomp, cmake, ninja,
   Compiler, `module-template/`, `GXRuntime/`, Header). Modul-Cache kurz und
   absolut, `longPathAware`-Manifest für alle EXEs.
3. **Launcher-Ablauf (M):** ROM wählen → Prüfung (Disc-ID, DOL-SHA-256; bei
   JP, PAL oder verändertem DOL eine verständliche Meldung) → Extraktion mit
   Fortschritt → Modulbau mit Fortschritt (Chunks, Zeitschätzung, abbrechbar,
   Wiederaufnahme aus dem Cache) → Spielen. Cache je DOL-Hash bleibt.
4. **Rückfall:** Scheitert der Spike, erkennt der Launcher installierte Build
   Tools und führt zur Installation (winget). Das reicht für v0.1; für v0.2
   wird die Paketfrage dann neu bewertet.

Beleg: frische Windows-11-VM ohne Entwicklungswerkzeuge, ROM bis Spiel,
Zeiten gemessen.

### WP3 Controller (M–L)

Ziel: Alle gängigen Windows-Controller und Tastatur, frei belegbar, analoge
Schultertaste, Totzonen, Empfindlichkeit, Invertierung, Hotplug.

Ist-Zustand (Abschnitt 9): Der Launcher listet nur SDL-Gamepads mit
Mapping, schreibt eine feste Belegung nach `Config/GCPadNew.ini` und bietet
keine Belegungsoberfläche.

1. Geräte: SDL-Gamepads, SDL-Joysticks ohne Mapping (manuelle Belegung),
   Tastatur und Maus über Dolphins DInput-Gerät; GC-Adapter über Dolphins
   nativen libusb-Pfad nur, wenn der Auftraggeber ihn will (Abschnitt 6).
2. Oberfläche im Launcher: Gerät wählen, Belegung je Funktion durch
   Tastendruck (A, B, X, Y, Z, L, R, Start, Steuerkreuz, beide Sticks, L und
   R analog), je Achse Totzone, Radius, Empfindlichkeit, Invertierung;
   Trigger-Schwelle; Profile je Geräte-GUID; Hotplug-Meldung.
3. Umsetzung: Die Oberfläche erzeugt Dolphins Ausdruckssyntax in
   `GCPadNew.ini` (Totzone, Range, Invertierung). Der Eingabestapel der
   Laufzeit bleibt unverändert; das minimiert Regressionen.
4. Analoge Schultertaste: Sunshine unterscheidet Halb- und Volldruck. Mit
   realem Trigger prüfen, dass Spritzen im Laufen und im Stand wie in der
   Automation ausfallen.

Beleg: drei reale Geräte (XInput-Pad, DualSense oder DualShock über SDL,
Tastatur), Bilder für Halb- und Volldruck, Hotplug während des Spiels,
gespeicherte Profile nach Neustart aktiv.

### WP4 Launcher-Bedienung und Windows-Integration (M)

1. Produktform nach Abschnitt 0.2: eigener Name in EXE, Fenstertitel,
   Fensterklasse und Protokollen; keine Dolphin-INIs sichtbar; Verhalten bei
   Fokusverlust wählbar.
2. Netplay-Elemente ausblenden (kein Auftrag). Einstellungen: interne
   Skalierung, Ausgabeauflösung, Vollbildart, VSync, Seitenverhältnis,
   Savestates, Spielstandordner öffnen.
3. EXE-Manifest (DPI, `longPathAware`), Symbol, Versionsinfo, Einzelinstanz,
   Absturzprotokoll (Minidump plus Log) für Fehlerberichte.
4. Installer (Inno Setup) oder ZIP mit Lizenztexten; Deinstallation lässt
   Spielstände unangetastet.

Beleg: visuelle Abnahme durch den Auftraggeber mit Bildern; Installation und
Deinstallation geprüft.

### WP5 Stabilität und Leistung (M)

1. `IOS_FS: Failed to rename temporary FST file` ursächlich klären
   (Verdacht: Wii-NAND-FST im Nutzerverzeichnis bei einem GC-Spiel oder
   zwei Prozesse auf demselben Profil). Reproduzieren, beheben oder
   ausschließen.
2. `CPUManager::Stop()`-Hänger bei Konfigurationsänderungen zur Laufzeit:
   Ursache verstehen statt nur umgehen; 50 automatisierte Vollbildwechsel
   unter Last.
3. Dauerlauf 60 Minuten mit Eingabeschleife; Speicher und Handles beobachten.
4. Leistung: SMC-Fallback messen (`STATICRECOMP_DISPATCH_SAMPLES`, 139
   SMC-Einträge), Frametime-Verteilung bei 1×, 3×, 6×, jeweils vor und nach
   WP8.
5. Lockstep-Verifikation auf der Abnahmestrecke, abschnittsweise
   (`STATICRECOMP_LOCKSTEP_START`/`_LIMIT`), weil sie sehr langsam ist.

Beleg: Protokolle; keine Hänger in der Matrix; Frametime-Tabelle.

### WP6 Abnahmelauf (M)

Ein Skript `tools/acceptance/run.py`: Kaltstart ohne Savestate → Titel →
Dateiauswahl (Slot A neu) → Airstrip → FLUDD → Boss 3 → 2 → 1 → 0 → Shine →
reguläres Speichern → Prozessende → Neustart → Slot A zeigt 1 Shine → Plaza
steuerbar. Eingaben aus den Fixtures von WP0, Ausrichtung über
`sunshine_state.py`, Bilder und JSON-Manifest je Prüfpunkt, GCI-Hash vor und
nach dem Speichern. Läuft mit statischem Modul; optional unter JIT64 als
Vergleich.

Beleg: ein Lauf mit Exit 0 und allen Prüfpunkten; Laufzeit dokumentiert.

### WP7 Adressbasis GMSE01 (S–M)

1. `maps/us.map` aus BetterSunshineEngine übernehmen (GPL-3.0; Quelle,
   Commit, SHA-256 in `tools/symbols/README.md`), von `Name=0xAdresse` in
   DolRecomps Zeilenformat `adresse name` wandeln.
2. Stichproben gegen den lokalen DOL: `__start` gleich Entry `0x8000522C`,
   Funktionsprologe an Funktionsadressen, die Gecko-Adressen (etwa
   `0x80412408`), der Mario-Zeiger `0x8040E108`. Mindestens 30 Treffer
   protokollieren.
3. Recompiler mit `--map` laufen lassen; `generated_symbols.h` entsteht,
   Mods nutzen Namen.
4. Lücken: fehlt ein benötigtes Symbol, Übertragung aus der japanischen
   Liste (38.262 Einträge mit Größen) über Reihenfolge- und
   Größen-Alignment gegen DolRecomps Funktionsanalyse des US-DOL. Das
   Verfahren lässt sich vorab an JP gegen PAL prüfen, weil dort beide Listen
   vorliegen; dafür ist kein JP- oder PAL-Abbild nötig.

Beleg: Stichprobenprotokoll, erzeugter Symbolheader.

### WP8 Widescreen 16:9 im Rekompilat und vollständige Abnahme (M)

> Stand 2026-09-14: Schritte 1 bis 3 erledigt und am laufenden Spiel belegt
> ([10-KOPFLOSER-PRUEFSTAND.md](10-KOPFLOSER-PRUEFSTAND.md)); offen ist die
> Bildabnahme (Schritt 4) und die Einbindung in den Launcher (WP2).

1. `tools/patches/gecko_to_dol.py`: die 13 Schreibungen als
   `[OnFrame]`-dword-Patches (bestehender Mechanismus, fließt in den
   Cache-Schlüssel ein); die zwölf Injektionen als Sprung plus Nutzcode in
   einer neuen Textsektion. Vorher prüfen, ob die Sektionstabelle des DOL
   einen freien Text-Slot hat (**zu prüfen**).
2. Nachweis: Disassembly-Diff, RAM-Vergleich mit der Gecko-Variante nach dem
   Verfahren aus `patch-verification.json`, Gecko-Code dabei ausgeschaltet.
3. Modul neu bauen (rund 20 Minuten). Der SMC-Fallback der beiden Chunks muss
   aus dem Log verschwinden.
4. Abnahme 16:9: HUD vollständig (FLUDD-Tank, Münzen, Leben, Shines,
   Sonnenmeter), Menüs, Pause, Karte, Echtzeit-Sequenzen, Wasser,
   Spiegelungen, Hitzeflimmer in mindestens drei Leveln (Airstrip, Plaza,
   Bianco), Schatten, Culling an den Rändern über feste Kamerapositionen im
   Vergleich 4:3 gegen 16:9.

Beleg: Bildmatrix mit Messprotokoll; Log ohne Fallback der Chunks.

### WP9 Ultrawide 21:9 und 32:9 (M–L)

1. Aspektabhängige Konstanten des Codes bestimmen: Seitenverhältnis
   (`0x80412408`), 2D-Breiten 800 und 700 (`0x80416758`, `0x804123E8`,
   `0x80416620`), Culling-Faktor 1,2067 (`0x80416B74`) sowie die festen
   Pixelversätze in den Injektionen (Lesart: rechtsbündige HUD-Elemente
   werden etwa von 415 nach 515 und von 397 nach 497 verschoben). Für
   Ultrawide müssen diese Werte eine Funktion des Seitenverhältnisses sein.
2. Umsetzung als nativer Mod (Mod-ABI): Hook auf eine frühe Funktion aus
   WP7, setzt die Werte einmal aus der Konfiguration; die Injektionen aus WP8
   lesen die Werte aus dem RAM statt aus Immediates.
3. Culling- und Pop-in-Test an den Rändern; Proportionsmessung mit dem
   Markerverfahren aus Dokument 03.

Beleg: Bilder 21:9 und 32:9 je Szene; Vergleichstabelle Proportionen.

### WP10 HUD-Anker, Menüs, Sequenzen (M–L)

1. Entscheidung des Auftraggebers zu HUD bei Ultrawide (Abschnitt 6).
2. J2D-Layout-Hooks über Symbolnamen aus WP7; Menüs zentriert; Echtzeit-
   Sequenzen mit den spieleigenen Balken prüfen (die Balken sind Spielinhalt
   und müssen bei allen Seitenverhältnissen korrekt liegen).

Beleg: Bildmatrix aller HUD-Elemente je Seitenverhältnis.

### WP11 Vorgerenderte Filme (S)

THP-Wiedergabe: Pillarbox 4:3 als Voreinstellung, Zoom als Option
(Entscheidung in Abschnitt 6). Umsetzung über die Projektion der Filmszene.

Beleg: Filmbilder ohne Verzerrung bei 16:9, 21:9, 32:9.

### WP12 Anzeige-Feinschliff (S–M)

HiDPI und Mehrmonitor (Monitorwahl, Vollbild auf Zweitmonitor), exklusiv
gegen randlos, VSync- und Limiter-Verhalten, Kantenglättung und anisotrope
Filterung als Optionen. Hinweis für den Auftraggeber: Dolphins interne
Skalierung ist ganzzahlig (Faktor 1 bis 12); freie Faktoren sind mit dieser
Laufzeit nicht möglich.

Beleg: Messprotokoll wie Dokument 07 auf zwei Monitoren mit unterschiedlicher
DPI.

### WP13 Framerate-Spike (M, zeitlich begrenzt)

> Stand 2026-09-14: alle fünf Schritte gemessen ([11-FRAMERATE-SPIKE.md](11-FRAMERATE-SPIKE.md)):
> 96 bis 100 % Zuordnung auch bei bewegter Kamera, Bewegung in den Matrizen,
> beide Ladewege sichtbar; synthetische Zwischenbilder gerendert (Dateiauswahl
> 92,9 %, Kameraschwenk 86,8 % der geänderten Pixel zwischen den
> Nachbarframes, kein sichtbares Artefakt); Filmübergang und harter
> Szenenwechsel erkannt, Schwenks nicht fälschlich. Go für Variante A auf
> Messebene; offen: Gegenschnitt in gleicher Szene, gesteuerte Spielszene.

Siehe Abschnitt 5.3. Ergebnis: `docs/11-FRAMERATE-SPIKE.md` mit Go/No-Go und
gewählter Variante.

### WP14 Framerate-Umsetzung (XL)

Siehe Abschnitt 5. Beginnt erst nach Entscheidung des Auftraggebers zu 5.4.

### WP15 Optional: experimenteller 60-FPS-Modus (S)

Dolphins `GMSE01.ini` enthält einen `$60FPS`-Code (drei Schreibungen, eine
Injektion). Er verdoppelt die Logikrate und verändert damit Physik und Timer;
SunPad führt ihn nur als Testoption. **Er erfüllt Anforderung 1 nicht.** Nur
als klar gekennzeichnete Experimentaloption, wenn der Auftraggeber sie will.

### WP16 Abschluss v1.0 (M)

Endnutzerdokumentation (Installation, ROM, Controller, Optionen),
Anforderungsmatrix vollständig belegt, Lizenzpaket (Quellen der Forks,
Drittlizenzen), Release-Notes, reproduzierbarer Build aus dem Fork-Stand.

---

## 5. Anforderung 1: Entkoppeltes Rendering

### 5.1 Warum es der härteste Posten bleibt

Das Spiel rendert über seinen eigenen rekompilierten GX-Code. Ein
aufgezeichneter Airstrip-Frame enthält 13.006 Zeichenbefehle, vier
EFB-Kopien und 2.022 Speicheraktualisierungen (Dokument 05). Es gibt keine
Engine-Schnittstelle „zeichne noch einmal mit interpoliertem Zustand". Der
Bildabschluss hängt am emulierten VI-Interrupt. Kein untersuchtes Projekt
(SunPad, ModernGekko, Dusklight) liefert entkoppeltes Rendering; die
Präsentationsschicht der gepinnten Dolphin-Quellen kennt keine Interpolation
(Abschnitt 9). Zelda64Recomp hat es mit RT64 gelöst, indem Display-Listen
aufeinanderfolgender Frames einander zugeordnet und Transformationen
interpoliert werden.

### 5.2 Zwei Kandidaten

**A. Renderer-seitig (VideoCommon).** Das Spiel läuft weiter mit 30 Hz. Der
Befehlsstrom und die von ihm gelesenen Speicherbereiche werden je Frame
mitgeschnitten (die FifoRecorder-Mechanik ist in der Laufzeit bereits
vorhanden, `record_fifo`). Zwischenbilder entstehen, indem der letzte Frame
mit interpolierten XF-Matrizen (Positions- und Normalenmatrizen, Projektion
und Sicht) erneut ausgeführt wird; die Zuordnung erfolgt über
Zeichenreihenfolge, Vertexformat, Textur und Matrixindex. Kameraschnitte
werden über Sprünge der Sichtmatrix erkannt und nicht interpoliert. Nicht
zuordenbare Teile (Partikel, CPU-berechnete Vertexdaten, Wasserflächen,
EFB-Kopien) bleiben auf dem letzten Stand, also bei 30 Hz.
Vorteile: keine Spieladressen, generisch, baut auf vorhandener FIFO-
Infrastruktur auf. Nachteile: tiefer Eingriff in Dolphins VideoCommon
(FIFO, OpcodeDecoder und VertexManager sind nicht für erneute Ausführung
gebaut; asynchroner GPU-Thread; EFB-Kopien und Texturcache), Qualität der
Zuordnung, Kosten der erneuten Ausführung je Ausgabeframe.

**B. Spielseitig (Mod-ABI).** Hooks in die Spielschleife: `update` bleibt bei
30 Hz, `draw` läuft je Ausgabeframe mit interpolierten Modell- und
Kameratransformationen (J3D-Basistransformationen, Kameraklasse). Erfordert
tiefes Engine-Wissen und viele Adressen (WP7 hilft), die Trennung von
Berechnung und Zeichnen ist in JSystem nicht sauber, hohes Regressionsrisiko;
dafür ist die Interpolation für alles Gehookte konstruktionsbedingt
korrekt. BetterSunshineEngine (GPL-3.0) zeigt Engine-Hooks auf der
US-Fassung und kann als Referenz dienen.

Empfehlung: A zuerst prüfen, B als Rückfall oder Ergänzung (etwa nur Kamera
und Mario).

### 5.3 Spike (WP13), Vorschlag fünf Arbeitstage

Offline, ohne Laufzeitumbau:

1. Zwei aufeinanderfolgende Frames aufzeichnen (`record_fifo frames=2`).
2. Werkzeug auf Basis von `parse_fifo.py`: Matrixladungen und Zeichenbefehle
   extrahieren, Zeichenbefehle zwischen Frame N−1 und N zuordnen, Trefferquote
   und Fehlerklassen ausweisen.
3. Klären, ob Sunshines J3D Matrizen unmittelbar in den FIFO schreibt oder
   indiziert aus RAM-Feldern lädt. Das entscheidet, ob am FIFO oder am
   RAM-Abbild interpoliert werden muss (**zu prüfen**).
4. Synthetischen Zwischen-Frame (t = 0,5) als DFF erzeugen und mit dem
   vorhandenen FIFO-Replay-Build (`MODERNGEKKO_ENABLE_FIFO_REPLAY`) rendern.
5. Kameraschnitt-Erkennung an einer Szene mit Schnitt prüfen.

Go für A, wenn in Gameplay-Szenen mindestens 90 % der Zeichenbefehle
zugeordnet werden, das Zwischenbild plausibel ist und der Schnitt erkannt
wird. Sonst B bewerten oder dem Auftraggeber die Optionen aus 5.4 vorlegen.

### 5.4 Was „unbegrenzt" realistisch bedeutet

Die Simulation bleibt originalgetreu bei 30 Hz. Gerendert wird mit
Bildschirmrate oder ohne Begrenzung. Interpoliert wird nur zuordenbare
Geometrie; Partikel, Wasseranimation und HUD-Animationen laufen in
30-Hz-Schritten. Die Eingabeabtastung bleibt bei 30 Hz, solange das Polling
des Spiels nicht gehookt wird (außerhalb des Auftrags). Dieser Umfang muss
vor WP14 mit dem Auftraggeber vereinbart sein. Zur Einordnung: Zelda64Recomp
beschreibt seinen Umfang genau so („Game objects and terrain, texture
scrolling, screen effects, and most HUD elements are all rendered at high
framerates"; „Changing framerate has no effect on gameplay").

---

## 6. Entscheidungen des Auftraggebers

| # | Frage | Empfehlung |
|---|---|---|
| 1 | Toolchain mitliefern (grob 150–300 MB) oder Build Tools voraussetzen? | mitliefern; Build Tools nur als Rückfall in v0.1 |
| 2 | Forks der drei Upstream-Bäume unter eigenem Konto, zunächst privat? | ja |
| 3 | Framerate-Umfang nach 5.4 akzeptabel? Obergrenze Bildschirmrate statt „unbegrenzt"? | Umfang nach 5.4; Obergrenze wählbar |
| 4 | Filme: Pillarbox 4:3 oder Zoom? | Pillarbox, Zoom als Option |
| 5 | HUD bei Ultrawide im inneren 16:9-Bereich oder an den Bildrändern? | innerer Bereich, Ränder optional |
| 6 | Experimenteller 60-FPS-Modus (WP15) gewünscht? | weglassen, bis Anforderung 1 steht |
| 7 | Ganzzahlige interne Skalierung (1 bis 12) akzeptabel? | ja; freie Faktoren nicht möglich |
| 8 | GC-Adapter-Unterstützung (Zadig-Treiber) im Umfang? | nicht in v0.2 |
| 9 | Mindestanforderungen: Windows 10 22H2 oder nur 11? GPU mit Vulkan 1.1? | Windows 10 22H2 und 11, Vulkan mit OpenGL-Rückfall |
| 10 | Verteilungsmodell: Modul beim Nutzer bauen (bisherige Festlegung in 02 und 08; WP2 bleibt L) oder das rekompilierte Modul mitliefern wie Zelda64Recomp („prebuilt binaries (which do not contain game assets)"; die Spielkopie dient nur den Assets; WP2 schrumpft auf Prüfung und Extraktion)? Das Modul ist aus dem Spielcode abgeleitet; das Risiko dieser Verteilung trägt der Herausgeber. | bisherige Festlegung beibehalten, bis der Auftraggeber das Risiko bewertet hat; ein späterer Wechsel bleibt möglich, weil Cache-Layout und Laufzeitprüfung (Disc-ID, DOL-SHA-256) in beiden Modellen gleich sind |

---

## 7. Risiken und Gegenmaßnahmen

| Risiko | Wirkung | Gegenmaßnahme | Frühindikator |
|---|---|---|---|
| Framerate-Architektur nicht machbar | Anforderung 1 fällt oder schrumpft | Spike zuerst, Umfang 5.4 früh vereinbaren | Zuordnungsquote im Spike |
| Toolchain-Paket lädt nicht in MSVC-Laufzeit | kein Modulbau ohne Build Tools | Spike WP2.1 vor dem Launcher-Umbau, Rückfall Build Tools | Modul-Ladefehler, Lockstep-Abweichung |
| Ton defekt (Timebase, Unterläufe) | nicht spielbar | WP1 zuerst, Vergleich Mainline | Tempoabweichung in der Aufnahme |
| DOL-Konversion des Widescreen-Codes ändert Verhalten | Regression | RAM-Vergleich gegen Gecko-Variante, Lockstep, Abnahmelauf | Abweichung an einer der 25 Stellen |
| Belege nur lokal | Reproduzierbarkeit verloren | WP0 | fehlende Fixtures im Repository |
| Upstream-Pins veralten | Aufwand beim Rebase | Forks, Rebase nur bei Bedarf | neue Upstream-Commits mit relevanten Themen |
| Pfadlängen, Windows-Eigenheiten | Abbrüche beim Modulbau | Manifest, kurze Cache-Pfade | Fehler „Pfad zu lang" |
| Rechtliches | Verteilung unzulässig | keine Spieldaten/Module verteilen, GPL-Quellen bereitstellen, Repository bis Release privat | — |
| Leistung 4K plus Interpolation | Ruckeln trotz Entkopplung | Kosten je Ausgabeframe im Spike messen | Frametime bei 6× |

---

## 8. Erster Schritt der nächsten Sitzung

Reihenfolge, damit der Auftraggeber die Entscheidungen aus Abschnitt 6 mit
Messwerten treffen kann:

1. **WP0:** Fixtures und Skripte aus `build/` ins Repository, CI mit Tests und
   Patch-Check, STATUS als Matrix.
2. **WP1:** Ton messen. Ergebnis als `docs/09-TON.md`.
3. **WP2 Schritt 1:** Toolchain-Spike (llvm-mingw oder `zig cc`), Modul bauen,
   laden, Abnahmelauf und Lockstep.
4. **WP7:** `us.map` übernehmen, Stichproben, `--map`-Lauf.
5. Danach **WP13**, der Framerate-Spike.

Erwartung: zwei bis drei Sitzungen bis einschließlich WP7. Erst auf
ausdrückliche Aufforderung committen und pushen; deutsch; nichts als fertig
bezeichnen, was nicht überprüft wurde.

Wo die Arbeit stattfinden muss: Alles, was Spielkopie, Windows-Werkzeugkette
oder die Belege unter `build/` braucht (WP0 Sicherung, WP1, WP2 Schritt 1,
WP5, WP6, WP8 Nachweis, WP13), läuft in einer Sitzung auf dem Windows-Rechner
des Auftraggebers wie bisher. Aus einer entfernten Sitzung ohne Spieldaten
sind nur reine Repository-Arbeiten möglich: CI-Workflow, Konsolidierung der
Dokumentation, der `us.map`-Konverter mit Tests an synthetischen Daten,
`gecko_to_dol.py` an einem synthetischen DOL, das Zuordnungswerkzeug für den
Framerate-Spike ohne echte Aufzeichnungen.

---

## 9. Für diesen Plan geprüfte Fakten (2026-09-14)

Alle Angaben an den genannten Quellen nachgesehen, nicht aus READMEs oder
Erinnerung übernommen.

| Gegenstand | Befund | Quelle |
|---|---|---|
| Upstream ModernGekko | HEAD von `master` ist `5417826` (2026-08-23/24), identisch mit dem Pin; keine neueren Commits; keine Commits zu Framerate, Widescreen oder Controller-Oberfläche | Commit-Liste, flacher Klon |
| Upstream DolRecomp | HEAD von `main` ist `40637c4` (2026-09-05), identisch mit dem Pin | Commit-Liste, flacher Klon |
| RecompCore `moderngekko-runtime` | `c6a600e` (2026-08-23), identisch mit dem Pin | flacher Klon |
| doldecomp/sms | weiterhin nur `config/GMSJ01` (38.262 Symbole, davon 12.879 Funktionen mit Größe) und `config/GMSP01` (37.936); kein GMSE01; HEAD 2026-09-14 | Sparse-Klon `config/` |
| BetterSunshineEngine | DotKuribo/BetterSunshineEngine, GPL-3.0, Ziel NTSC-U; `maps/us.map` (Branch `main`) mit rund 3.500 Zeilen `Name=0xAdresse`, Funktionen und Daten, `__start=0x8000522C`; dazu `jp.map`, `eu.map`, `kr.map` | Repository-Seite, Rohdatei |
| Sunshine-Recomp aus ModernGekkos Hall of Fame (binsento) | kein öffentliches Repository gefunden; SunPad bleibt der einzige öffentliche Referenzport | Websuche |
| DolRecomp `--map` | akzeptiert unter anderem Zeilen `adresse größe name` und `adresse name` (Hex, Adresse 4-Byte-ausgerichtet); erzeugt `DOLRECOMP_SYMBOL_<Name>` und `DOLRECOMP_SYMBOL_SIZE_<Name>`; unbrauchbare Maps werden abgewiesen | `src/analysis/symbol_map.c`, README |
| Mod-ABI | `RECOMP_PATCH`, `RECOMP_FORCE_PATCH`, `RECOMP_HOOK`, `RECOMP_HOOK_RETURN`, Exporte, Importe, Events, Callbacks, `on_load`; Hooks binden an 32-Bit-Adressen; Speicherzugriff über `external_read`/`external_write` am `CPUState`; Mods als `<id>.mgm` neben der EXE oder unter `<user-dir>/Mods`, `--mods`, `--no-mods` | `include/moderngekko/mod_abi.h`, `mod-template/`, README |
| `moderngekko-port build` | Quellpfad `MODERNGEKKO_SOURCE_DIR` zur Compile-Zeit; nutzt `vendor/dolphin/module-template` (CMake, Ninja), `GXRuntime`, StaticRecomp-Header; Compiler `cl`/`clang`/`gcc` auf PATH; `dolrecomp` neben der EXE; Cache `<output>/<disc>/<dol-sha256>-<schlüssel>/`, Schlüssel enthält Compiler-Identität, Revisionen, ABI-Versionen, Backend, Patch-Fingerabdruck; DOL-Patches nur aus `[OnFrame]`/`[OnFrame_Enabled]` mit `adresse:dword:wert` innerhalb bestehender Textsektionen | `tools/moderngekko_port.cpp`, `tools/dol_patch.cpp` |
| Launcher | ImGui/SDL3; „Extract and Play" startet `moderngekko-run --game … --user-dir …`, baut kein Modul; nur SDL-Gamepads mit Mapping, feste Belegung in `GCPadNew.ini`, keine Belegungsoberfläche; Netplay-UI vorhanden | `tools/moderngekko_launcher.cpp`, `tools/frontend_config.cpp` |
| Runner | Modulsuche: neben der EXE, `<user>/StaticRecompModules/`, `STATICRECOMP_MODULE`; `--audio <backend>`, `--mods`, `--allow-interpreter`, `--automation-dir`; Audio bevorzugt cubeb, sonst Null | `tools/moderngekko_run.cpp`, `src/runtime/dolphin_runtime.cpp` |
| Lockstep-Verifizierer | vorhanden in RecompCore; Aktivierung über `STATICRECOMP_LOCKSTEP`, dazu `_START`, `_LIMIT`, `_FILTER`, `_NODEDUP`, `_MAXREPORT`, `_STEPCAP`, `_TRACE`, `_REPEAT`, `_WHITELIST`; weitere Schalter `STATICRECOMP_DISPATCH_SAMPLES`, `STATICRECOMP_FALLBACK_RANGES` | `Source/Core/Core/PowerPC/StaticRecomp/` |
| Gecko-Codes GMSE01 | `$Widescreen [gamemasterplc]`: 13 Schreibungen, 12 Injektionen (eine mit neun Zeilen); `$60FPS [gamemasterplc]`: 3 Schreibungen, 1 Injektion | `Data/Sys/GameSettings/GMSE01.ini` |
| Sunshine-Voreinstellungen | `GMS.ini`: `EFBToTextureEnable=False`, `EFBAccessEnable=True`, `ArbitraryMipmapDetection=True`, `PerfQueriesEnable=True` | `Data/Sys/GameSettings/GMS.ini` |
| Präsentation | keine Interpolation in `Present.cpp`; `VertexShaderManager::LoadProjectionMatrix` ist die Stelle des generischen Seitenverhältnis-Hacks; FifoPlayer bietet `WriteFrame`, `LoadXFReg`, Objekt- und Frame-Bereiche | `Source/Core/VideoCommon/`, `Source/Core/Core/FifoPlayer/` |
| ModernGekko-Template | Entwicklerwerkzeug (`make run ISO=…`), Controller per Hand in INI; kein Endnutzer-Launcher, keine Verteilungsregel für Module | Template-README |
| Zelda64Recomp | Releases enthalten den rekompilierten Spielcode („prebuilt binaries (which do not contain game assets)"); die Spielkopie wird im Hauptmenü angegeben und nur für Assets gelesen; Framerate-Umfang: „Game objects and terrain, texture scrolling, screen effects, and most HUD elements are all rendered at high framerates" | README (Branch `dev`) |
| SunPad bekannte Probleme (2026-09-04) | Timebase im eigenen Recomp-Core zwölffach zu schnell (behoben, Abnahme offen); Modul braucht Mac-Toolchain; 60 FPS nur Test; Widescreen experimentell mit abgetrennten Schatten; Controller-Belegung eng | `docs/KNOWN_ISSUES.md` |

Nicht geprüft und im Plan als Annahme oder „zu prüfen" markiert: das Laden
eines mit llvm-mingw oder `zig cc` gebauten Moduls in der MSVC-Laufzeit; freie
Text-Slots in der DOL-Sektionstabelle für die Injektionen; ob J3D Matrizen
unmittelbar oder indiziert lädt; die genaue Wirkung des `$60FPS`-Codes; ob
die Lockstep-Verifikation mit den aktuellen Pins unter Windows läuft.
