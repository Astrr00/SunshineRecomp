# FIFO-Diagnose und FLUDD-Spielprüfung

Stand: 2026-09-09. Fortsetzung von `04-GRAFIKDIAGNOSE.md`. Kein vollständiger
Port-Abschluss; nachstehend nur tatsächlich ausgeführte Prüfungen.

## Neue, gebaute Diagnosefunktion

`patches/moderngekko-fifo-automation.patch` erweitert ModernGekko um:

```text
command=record_fifo
frames=1
path=airstrip.dff
```

Voraussetzungen: laufender Core, Pfad und 1–120 Frames. Der Befehl wartet auf
den Abschluss und das Speichern des Mitschnitts, maximal 30 Sekunden.
Bei Unterbrechung/Timeout kann noch eine partielle Datei folgen; nicht blind
einen zweiten Mitschnitt starten. Callback-Zustand wird gemeinsam besessen,
damit ein unterbrochener Wartevorgang keine lokale Referenz zurücklässt.

Der Patch enthält auch die standardmäßig ausgeschaltete CMake-Option
`MODERNGEKKO_ENABLE_FIFO_REPLAY`, die Dolphins vorhandenes `dolphin-nogui`-Ziel
für lokale Wiedergabetests zugänglich macht. Sie verändert die Port-Architektur
nicht. `scripts/bootstrap.ps1` wendet den Patch auf ModernGekko an.

Verifiziert:

- `moderngekko-run` und `moderngekko_automation_protocol_test` gebaut.
- `ctest --test-dir ref/ModernGekko/build -R automation_protocol --output-on-failure`:
  bestanden, einschließlich ungültiger Frame-Anzahl und fehlendem Pfad.
- Echtes Spiel: ein Frame sowie zwei Frames aufgezeichnet.
- Pausierter Core: gültig formulierter FIFO-Auftrag wird mit
  `record_fifo requires a running core` abgewiesen.
- Reverse-Check des exportierten Patches gegen den Arbeitsbaum erfolgreich.

## Messdaten

Lokale Artefakte unter `build/texture-investigation/`:

| Datei / Daten | Ergebnis |
|---|---|
| `fifo-auto/airstrip.dff` | 6.859.882 Bytes, DFF-Version 6, genau ein Frame |
| Grafikbefehle dieses Frames | 903.636 Bytes, bis zum exakten Ende dekodiert |
| Primitive-Zeichenbefehle | 13.006; keine Gleichsetzung mit Host-GPU-Drawcalls |
| Speicheraktualisierungen | 2.022 |
| EFB-Kopien | 4 |
| `dump/user/Dump/Textures/GMSE01/` | 206 Textur-PNGs einschließlich Mips |
| `dump/user/Dump/Textures/` | 33 EFB-Abzüge, zusammen 26.670.061 Bytes |

Die vier EFB-Ziele im Ein-Frame-Mitschnitt (physische GC-RAM-Adressen):

| Ziel | Quellgröße |
|---|---|
| `0x00CE3BC0` | 512×512 |
| `0x01049EC0` | 256×256 |
| `0x00F94FE0` | 640×448 |
| `0x004C8D80` | 640×448 |

`parse_fifo.py`, `fifo-analysis.json`, die Kontaktbögen `textures-*.png` und
`texture-index.json` liegen ebenfalls lokal im Diagnoseverzeichnis. Der
Parser folgt `FifoDataFile.cpp`, `CPMemory.h` und `OpcodeDecoding.h` aus dem
gepinnten Quellbaum; Headergrößen und Bereichsgrenzen wurden geprüft.

## Software-Renderer als Gegenprobe

Das vorhandene `DolphinNoGUI.exe` wurde mit der neuen optionalen CMake-Option
gebaut. Für den Test wurde die EXE nach `ref/ModernGekko/build/` kopiert,
damit sie dessen bereits vorhandenes `Sys/` findet.

Der erste Headless-Versuch erzeugte **kein** Referenzbild: Im Log steht
`Failed to create OpenGL window`. Auch ein Exitcode 0 kann beim NoGUI-Frontend
einen gescheiterten asynchronen Grafikstart begleiten; das wurde nicht als
Erfolg gezählt. Der Windows-Plattformpfad erzeugte danach einen GL-4.6-Kontext.

Die Bildausgabe gelang mit Windows-Plattform, `Software Renderer`, FIFO-Loop,
`Movie/DumpFrames=True`, `Settings/DumpFramesAsImages=True` und
`Settings/FrameDumpsResolutionType=2`. Nach zwei tatsächlich erzeugten PNGs
wurde ausschließlich der gestartete Diagnoseprozess beendet. Die Bilder
liegen unter `software/Dump/Frames/`, in roher XFB-Auflösung 640×448.

**Befund:** Die auffälligen Schleim-/Figurenanteile sind auch in dieser
Software-Wiedergabe vorhanden. Dabei läuft kein Spielcode, sondern derselbe
aufgezeichnete Befehlsstrom. Eine ausschließlich im Vulkan-/OpenGL-Renderer
entstehende Störung ist damit keine ausreichende Erklärung. Eine pixelgenaue
Bildgleichheit oder Übereinstimmung mit echter GameCube-Hardware ist nicht
bewiesen. Die frühere Bezeichnung als eindeutig fehlerhafte „fragmentierte
Geometrie“ war zu stark; vorgesehene Schleim-/Versinkeffekte und fehlerhafte
Zustände müssen weiter unterschieden werden. Keine Sampling-Umstellung wurde
als Lösung freigegeben.

## Tatsächliches Gameplay: FLUDD erreicht

Die eigene `airport0.szs` wurde lokal entpackt: Yaz0-Ausgabe 4.920.064 Bytes,
RARC mit 34 Knoten und 557 Dateien. `map/scene.bin` hat 12.232 Bytes.
Der Eintrag `watergun_item` liegt bei ungefähr `(-6634, 500, 1591)`.
Es wurden keine Spieldaten beschafft oder veröffentlicht.

Für die Navigation wurden nur Controllerbefehle verwendet. Positionen wurden
zusätzlich aus dem RAM gelesen: `0x8040E108` zeigt in dieser GMSE01-Revision
auf das Mario-Objekt; `0x8040E10C` auf dessen drei Positionsfloats. Der erste
Versuch, den Objektzeiger als Positionszeiger zu deuten, lieferte unplausible
Floats und wurde korrigiert. Die Positionszuordnung wurde durch tatsächliche
Bewegung und passende Höhenwerte (Plattform 500, Wasser ungefähr −80) geprüft.
Dies ist keine vollständige Strukturrekonstruktion oder allgemeine Hook-Map.

FLUDD wurde tatsächlich berührt, die Aufnahmesequenz lief, die Nachfrage zur
Tutorial-Wiederholung wurde mit „No“ bestätigt. Bilder unter `fifo-auto/`:

- `fludd-pickup.png`, `fludd-equipped.png`: Aufnahme und ausgerüstetes Gerät.
- `first-spray.png`, `spraying.png`: Wasserpartikel und Wasseranzeige.
- `wash-mark.png`: sichtbar teilweise entferntes M.
- `wash-centered.png`: M vollständig verschwunden, Münze erschienen,
  Tutorialhinweis in diesem Bild verschwunden.

**Grenze:** Das M und der Hinweis erscheinen in späteren Bildern erneut;
eine dauerhaft abgeschlossene Tutorial-/Fortschrittsflagge ist damit nicht
bewiesen. Die Münze wurde nicht nachweislich eingesammelt (Anzeige weiterhin
0). Die vollständige Reinigung der großen Schleimfläche und der erste Boss
bleiben offen. Der sichtbare Reinigungs- und Belohnungseffekt selbst ist belegt.

## Analoge Schultertaste: gemessener Unterschied

Aus demselben lokalen Savestate, jeweils 30 Frames mit `main_y=-0.7`:

| R-Zustand | Vorher (X,Y,Z) | Nachher (X,Y,Z) | XZ-Weg |
|---|---|---|---|
| `r=1`, `r_analog=1` | −6320, 500, 1650 | −6320, 500, 1650 | 0 |
| `r=0`, `r_analog=0.5` | −6320, 500, 1650 | −6175, 500, 1127 | 542,793 |

Das bestätigt die Unterscheidung zwischen stationärem Zielen und Bewegung in
der Automation. Belege: `trigger-full.png`, `trigger-half.png`,
`trigger-results.json`. Reale Controller, freie Belegung und Einstellungs-UI
sind damit **nicht** abgenommen.

## Regulärer Speicherversuch

Save im Pause-Menü und anschließend „Yes“ im Mario-A-Dialog wurden bestätigt.
Die GCI-Prüfsumme änderte sich von
`887de755eb976093783ace7df22470cf285066e62ef2a484680e8ba51566a755` nach
`6f827b57065929abdf966d7a8ab03eab008efa2d3a20fd6458267b4c808ae0cd`.
Das betrifft nur das separate Testprofil unter
`build/graphics-investigation/native-newgame/user/`.

Der anschließende reguläre Neustart ohne Savestate verwendet
`build/gameplay-verification/auto/`. Vor dem Neustart wurden die beiden
Diagnoseoptionen FastTextureSampling/EFBScaledCopy im Testprofil wieder auf
True gesetzt. Die vorherigen FLUDD-Aufnahmen wurden noch mit den als
Diagnose verwendeten False-Werten aufgenommen; sie sind kein vollständiger
Grafikvergleich des Standardprofils. Ergebnis der normalen Wiederaufnahme
ist gesondert zu prüfen und darf nicht aus dem erfolgreichen Savestate-Laden
abgeleitet werden.

**Ergebnis dieses Neustarts:** `load-selection.png` zeigt Slot A mit 0 Shines
statt „New“. Der Slot wurde über die normale Dateiauswahl gestartet;
`loaded-progress.png` zeigt den Peach-Dialog und `normal-load-playable.png`
den anschließenden Spielzustand. Der grundlegende Datei-Save-/Load-Weg ist
damit belegt. Der Start erfolgte erneut am Anfang des Flugplatzes; die
Erhaltung abgeschlossenen Story-Fortschritts ist vor dem ersten Shine noch
nicht abgenommen. Keine Behauptung, dass FLUDD-Aufnahme oder temporäre
Reinigung über diesen Save hinweg erhalten bleiben müssten oder erhalten
geblieben seien.

Aktuell läuft ausschließlich der Prozess für `build/gameplay-verification/auto/`,
am regulär geladenen Flugplatz **pausiert**. `normal-load.sav` sichert diesen
Zustand. Für weitere Mechaniktests ist zusätzlich
`build/texture-investigation/fifo-auto/fludd-tested.sav` vorhanden; dessen
Laden ist ausdrücklich ein Savestate-Test, kein Ersatz für reguläres Laden.
`build/texture-investigation/evidence-manifest.json` enthält die aktuellen
DFF-/PNG-Prüfsummen und Abmessungen. Nichts committed oder gepusht.
