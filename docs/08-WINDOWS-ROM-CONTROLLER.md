# Windows-App, ROM-Einrichtung und Controller

Stand: 2026-09-10. Verbindliche Präzisierung des Auftraggebers:
Der Port soll nativ unter Windows laufen, alle Controller unterstützen und
nach Laden einer eigenen ROM/Disc-Spielkopie spielbar sein. Die älteren
Grafik-, Framerate-, Eingabe- und Save-Anforderungen bleiben bestehen.

## Ziel der Bedienung

Windows-Anwendung starten, eigene Sunshine-Spielkopie auswählen, automatische
Einrichtung mit Fortschrittsanzeige, spielen. Der Anwender soll weder manuell
extrahieren noch Build-Befehle eingeben oder Modulpfade zusammensuchen müssen.
Spieldaten und daraus erzeugte Module bleiben lokal; keine Downloads oder
Mitlieferung von Spieldaten. Aktuell verifiziert: GMSE01 USA Rev. 0.
Andere Regionen/Revisionen nicht stillschweigend als unterstützt ausgeben.

Controller: Windows-Geräte erkennen, Hotplug, frei belegbare Knöpfe und
Achsen, analoge Schultertasten, Totzonen/Empfindlichkeit/Invertierung. Die
bestehende SDL-Konfiguration aktiviert dinput, gameinput, hidapi, rawinput,
virtual, wgi und xinput. Das belegt verfügbare Backends, nicht getestete
Funktion jedes Geräts. Der Launcher überspringt derzeit SDL-Joysticks ohne
Gamepad-Mapping; breite Unterstützung und deren Belegungsoberfläche fehlen.

## Bereits ausgeführt

- Launcher kann nun mit `--user-dir <Pfad>` isoliert betrieben werden;
  GCM ist zusätzlich im Disc-Dateifilter enthalten.
- `scripts/build.ps1` setzt Frontendname/Benutzerverzeichnis SunshineRecomp,
  RequiredDiscID GMSE01 und den gemessenen SHA-256 von main.dol:
  `13934c863d649b1ddca1ca4d7748f49d28a571685cbee5fb1542545c32869955`.
  Derselbe CMake-Stand ist gebaut.
- Vorheriger Importversuch scheiterte an `this disc is not the pinned patched
  release`: Ohne RequiredDiscID akzeptierte `PrepareDisc` keine normale Disc.
  Das war fehlende Anwendungskonfiguration, kein defektes RVZ-Abbild.
- Erfolgreicher Aufruf des gebauten Launchers mit `--extract` auf die vorhandene
  `Super Mario Sunshine (USA).rvz`, ohne vorherige ISO-Konvertierung:
  Exit 0. Ausgabe: `build/launcher-rom-import/user/games/GMSE01`.
- SHA-256-Vergleich aller Dateien gegen `build/game`: 179 Spieldateien identisch,
  keine zusätzlichen/geänderten Spieldateien. Nur `import.json`, der Bericht
  des separaten Importers, fehlt. `build/launcher-rom-import/comparison.json`.
  Dies prüft die Extraktionsfunktion des Launchers, noch nicht die Bedienung
  des Dateidialogs oder den vollständigen Ablauf bis zum Spielstart.
- Anschließend genau diesen neuen Import ohne Savestate mit dem vorhandenen
  statischen Modul gestartet: `build/launcher-rom-import/cold-result.json`,
  29,9574 FPS, Exit 0. Bildschirmabzug tatsächlich betrachtet: frühe Wolken-
  und Logo-Animation, **noch kein vollständiger Titelbildschirm** trotz des
  Dateinamens `cold-title.png`. Modul-Ladezeile im stderr bestätigt.
  Manuelle Modulübergabe in diesem Test; keine Behauptung eines bereits
  automatischen ROM-bis-Spiel-Ablaufs.

## Noch zu integrieren

`moderngekko_launcher.cpp` startet nach dem Import nur `moderngekko-run --game`.
Die Laufzeit sucht ein Modul neben der EXE oder unter
`<user>/StaticRecompModules/gGMSE01_recomp.dll`; sie baut es nicht selbst.
Das gebaute `moderngekko-port build` kann den Modulbau ausführen, verwendet
aber derzeit im Binary festgelegte Quellpfade und einen Compiler auf PATH.
Ein übertragbares Paket braucht deshalb einen vollständigen lokalen
Einrichtungspfad einschließlich Werkzeugen/Quellen und Prüfung seiner
Voraussetzungen. Keine vorbereitete Moduldatei als Ersatz für diesen
noch fehlenden Anwenderablauf ausgeben.

## Startverzeichnisse korrigiert

Die Laufzeit ließ `UICommon::CreateDirectories()` aus. Der Aufruf steht jetzt
nach SetUserDirectory und vor Init. Frischer Test:
`build/startup-directory-verification/scale3/`: Start, Spielbild,
Vollbildwechsel, 30 weitere Frames und regulärer Exit 0. Cache umfasst sieben
Dateien mit zusammen 17.077.226 Bytes; Log ohne `failed`/`Failed`-Treffer.
Vollbild war auf der aktuellen Anzeige **3440x1440**, Fenster 1280x720.
Das belegt Monitorfüllung; der feste 16:9-Spielcode wird dadurch nicht Ultrawide.

Der frühere FST-Rename-Fehler ist damit nicht ursächlich erklärt oder als
behoben nachgewiesen. Der Wiederholungsstart unter dem damaligen Profil
lief später bis Frame 36835 (28,8 FPS); nach der Sitzungsunterbrechung war
sein Prozess nicht mehr vorhanden. Ein regulärer Exit ist für diesen
unterbrochenen Wiederholungslauf nicht belegt.
