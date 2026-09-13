# Widescreen-Prüfung GMSE01 Rev 0

Stand: 2026-09-09. Experimenteller Zwischenstand, keine vollständige Abnahme
von Anforderung 3 oder 4. Alle Spieldaten, Savestates und Bilder bleiben lokal
unter `build/widescreen/` und sind nicht Bestandteil des Repositorys.

## Aktivierung aus dem Quellcode abgeleitet

In `ref/ModernGekko/vendor/dolphin/Data/Sys/GameSettings/GMSE01.ini` steht
**ein** ausführbarer Widescreen-Code, `$Widescreen [gamemasterplc]`.
Der zweite Name unter `[Gecko_RetroAchievements_Verified]` ist eine
Freigabemarkierung, kein zweiter Code. Die frühere Übergabe war hier falsch.

Der Code enthält 13 direkte 32-Bit-Schreiboperationen (Typ 04) und zwölf
Code-Injektionen (Typ C2). Er verändert sowohl Daten als auch Instruktionen.

Quellpfade relativ zu `ref/ModernGekko/`:

- `src/runtime/dolphin_runtime.cpp`: `Runtime::Create` setzt das Benutzerverzeichnis
  und initialisiert UICommon. Die Laufzeit verwendet damit Dolphins INI-System.
- `vendor/dolphin/Source/Core/Core/Cheats/GeckoCodeConfig.cpp`: `LoadCodes`
  liest `[Gecko]` aus globaler und lokaler INI sowie die Aktivierung über
  `ReadEnabledAndDisabled(..., "Gecko", ...)`.
- `vendor/dolphin/Source/Core/Core/Cheats/PatchEngine.cpp`: lädt die Codes und
  ruft pro Frame `Gecko::RunCodeHandler` auf.
- `vendor/dolphin/Source/Core/Core/Config/CheatSettings.cpp` und
  `Cheats/GeckoCode.cpp`: `Core/EnableCheats` muss wahr sein.
- `vendor/dolphin/Source/Core/VideoCommon/Present.cpp`: `ForceWide` berücksichtigt
  das VI-Seitenverhältnis und ergibt nur ungefähr 16:9. `CustomStretch` (5)
  verwendet das explizite Zielverhältnis. Dies betrifft die Ausgabe der bereits
  spielseitig angepassten Projektion; `wideScreenHack` bleibt **False**.

Minimal für den bereits mitgelieferten System-Code:

```ini
; <user-dir>/Config/Dolphin.ini
[Core]
EnableCheats=True

; <user-dir>/GameSettings/GMSE01.ini
[Gecko_Enabled]
$Widescreen

; <user-dir>/Config/GFX.ini
[Settings]
AspectRatio=5
CustomAspectRatioWidth=16
CustomAspectRatioHeight=9
wideScreenHack=False
```

`scripts/widescreen-profile.py <neues-user-dir> --copy-saves-from build/userdir`
erzeugt ein isoliertes Testprofil. Es übernimmt den Code aus der gepinnten
lokalen Quell-INI unter eigenem Namen, hält deren SHA-256 fest und kopiert
optional vorhandene GC-Spielstände. Es überschreibt kein bestehendes Profil,
lädt nichts herunter und aktiviert keinen 60-FPS-Code. Start anschließend mit
dem vorhandenen `moderngekko-run.exe`, Modul, `--user-dir` und `--automation-dir`
wie in HANDOFF Abschnitt 5 beschrieben.

## Gemessene Aktivierung und Ausführung

- `automation/aspect.bin`: vor der ersten Anwendung `3FAAAAAB` an `0x80412408`.
- `automation/aspect-title.bin`: danach `3FE38E39`, also etwa 1,7777778.
- `automation/patch-verification.json`: alle 13 direkten Schreibwerte stimmen;
  bei allen zwölf C2-Stellen ist der Branch vorhanden und der angesprungene
  Nutzcode stimmt bytegenau mit der INI überein (ohne das vom Handler ersetzte
  letzte Rücksprungwort). Grundlage: lokaler 5-MiB-RAM-Abzug.
- Das Log des ersten Widescreen-Laufs meldet geladene statische Recompilation
  sowie SMC-Fallback für die geänderten Chunks `802C9600–802CD600` und
  `80361600–80365600`. RAM-Nachweise allein belegen ausdrücklich **nicht**, dass
  jede geänderte Instruktion in jeder nativen Aufrufkette ausgeführt wird.
- Mehrere Statusmessungen in Film, Dateiauswahl und Gameplay lagen bei rund
  29,95–29,97 FPS und Geschwindigkeit 1. Das sind Stichproben, kein Benchmark.

## Bilder und Prüfgrenzen

| Lokales Bild unter `build/widescreen/` | Beobachtung |
|---|---|
| `automation/select.png` | Dateiauswahl mit A/B/C, Options-Schild, Mario, Meer und Schatten |
| `automation/select-jump.png` | Block A tatsächlich ausgewählt; Start-Menü geöffnet |
| `automation/airstrip.png` | Echtzeitdialog mit Peach am Flugzeug; Münzanzeige sichtbar |
| `automation/gameplay-front.png` | Mario im steuerbaren Spiel, NPCs, Flugzeug und Bodenschatten |
| `automation/gameplay-turn.png` | Nach Bewegung und Kameradrehung: Schleim, NPCs, Meer und weitere Flugplatzgeometrie |
| `automation/pause-menu.png` | Pause, Continue/Save und Levelname sichtbar; Abdunklung über die Breite |
| `automation/cutscene2.png` | Einleitungsfilm: 2407×1344, oben und unten jeweils 192 schwarze Pixelzeilen |
| `exact-auto/wide-front.png` | Benutzerdefiniertes 16:9: 2389×1344 (Rundung auf ganze Pixel), keine vollständig schwarzen Randzeilen |
| `cold-auto/cold-select2.png` | Ungepatchte Dateiauswahl nach Kaltstart, 1920×1440 |
| `cold-auto/cold-front.png` | Gültige 4:3-Gameplay-Referenz, vollständig ohne Cheats/Savestate gestartet |
| `cold-auto/cold-turn.png` | 4:3-Kameradrehung: ebenfalls auffällige Schleim-/NPC-Darstellung |
| `generated-auto/wide-edge1.png`, `wide-edge2.png` | Weitere Kamerawinkel, Meer und Flugzeug; NPC am äußersten linken Rand sichtbar |

**Zusätzliche Sicht nachgewiesen:** In `cold-front.png` ist das rechte
Flugzeugrad angeschnitten; in `exact-auto/wide-front.png` vollständig im Bild.
Der rote B-Marker über Peach hat bei einer RGB-Schwellwertmessung folgende
Ausdehnungen (Bounding Box inklusive Endpixel):

| | 4:3 Kaltstart | 16:9 |
|---|---|---|
| PNG | 1920×1440 | 2389×1344 |
| roter Markerbereich | 123×120 | 116×111 |
| Breite / Bildhöhe | 8,5417 % | 8,6310 % |
| Höhe / Bildhöhe | 8,3333 % | 8,2589 % |

Das stützt zusammen mit dem zusätzlichen sichtbaren Szenenbereich echtes
Widescreen statt einer Streckung um 33 %. Die Bilder sind keine zeitgleichen
Frames; Animation, Antialiasing und Schwellwertmessung begrenzen die Genauigkeit.
Messprotokoll: `build/widescreen/marker-measurements.json`.

**Keine pauschale Aussage „Rendering korrekt“:** Die Bilder am Schleimhaufen
zeigen auffällige überlagerte beziehungsweise fragmentierte Geometrie/NPCs.
Das ist auch in der ungepatchten Kaltstart-Referenz `cold-turn.png` sichtbar.
Es ist daher kein isoliert belegter Widescreen-Fehler; die Ursache wurde in
dieser Sitzung nicht geklärt. Ebenso ist ein einzelner sichtbarer NPC am
Bildrand keine vollständige Culling-Abnahme.

Das erzeugte Profil `generated-profile/` wurde zusätzlich tatsächlich gestartet:
Modul geladen, etwa 30 FPS, vor jedem Savestate-Laden `3FE38E39` an
`0x80412408` ausgelesen. Damit ist auch die Aktivierung unter dem eigenen
Code-Namen des Profilskripts geprüft.

`build/widescreen/image-measurements.json` enthält Bildgrößen, schwarze
Randzeilen und SHA-256 der aufgenommenen Bilder. Die anfangs aufgenommenen
Dateien `opening.png`, `title.png`, `title2.png`, `files.png` und
`after-start.png` haben irreführende Namen: Sie entstanden vor den korrigierten
Eingaben und sind keine Belege für die im Namen genannten Bildschirme.

**Offen:** vollständige HUD-Abdeckung einschließlich FLUDD, systematische
Rand-Culling-Prüfung, Wasser-/Spiegelungs- und Hitzeflimmer-Prüfung über mehrere
Level, weitere Echtzeit-Zwischensequenzen sowie unverzerrte Filmwiedergabe.
21:9 und 32:9 wurden nicht aktiviert. Eine bloße Vergrößerung der
Ausgabebreite würde den festen 16:9-Spielcode nicht korrekt anpassen.

## Reproduzierbare Eingabe und eigene Fehlversuche

Die Dateiauswahl benötigt Mario unter einem Block, dann A. Im ersten
Widescreen-Lauf: aus der Ausgangsposition `main_x=-1` für zwölf Frames,
30 Frames neutral, A für zwei Frames, 90 Frames neutral. Damit öffnete sich
das Start-Menü von A; ein weiterer A-Druck startete die Flugplatz-Einleitung.
Die Bilder müssen jeden Übergang bestätigen; Eingaben während einer
Bildschirmtransition können wirkungslos bleiben.

Die ersten acht Pad-Befehle dieser Sitzung enthielten versehentlich kein
`port=0` und wurden verworfen. `status.txt/last_error` kann durch einen später
erfolgreichen Screenshot geleert werden: immer auch `failed/` prüfen.
`scripts/automation.py` ergänzt Port 0 bei Pad-Befehlen, veröffentlicht die
Befehlsdatei atomar und wartet auf `processed/` oder `failed/`.
Eine Screenshot-Bestätigung bedeutet nur, dass der Auftrag angenommen wurde;
vor Pause/Stop muss noch ein Frame für die Bildausgabe stattfinden.

Der Versuch, einen Widescreen-Savestate bei ausgeschalteten Cheats zu laden
und die 25 Patchstellen aus der lokalen DOL zurückzuschreiben, lieferte
verzerrte Vergleichsbilder. Auch die geladene Dateiauswahl enthielt noch
angepasste Layoutdaten. Diese Versuche (`baseline-auto/`, `baseline-fresh/`)
sind **keine gültige ungepatchte Referenz**. Dafür wird `cold-auto/` verwendet:
vollständiger Start ohne Cheats, ohne Savestate und ohne RAM-Schreiboperationen.

In dieser Sitzung war weder `python` auf PATH noch ein Interpreter über `py`
registriert. Verwendet wurde der gebündelte Interpreter unter
`C:/Users/niemc/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe`.

Es wurde weder committed noch gepusht. Die ursprüngliche Speicherkarte unter
`build/userdir/` blieb unverändert; Spielversuche verwenden separate Profile.

## Fortsetzung

Zum Sitzungsende ist die Laufzeit mit `generated-profile/` und
`generated-auto/` am Flugplatz **pausiert**. `resume` über das
Automationsprotokoll setzt sie fort. Der lokale Checkpoint
`generated-auto/wide-turn-settled.sav` erlaubt dieselbe Szene nach einem
Neustart; nur zusammen mit demselben aktivierten Widescreen-Code verwenden.
Die beiden neuen Python-Skripte wurden syntaktisch geprüft; das Profil wurde
erzeugt und in der Laufzeit aktiviert, die Automationshilfe wurde laufend für
Eingabe, Bilder, RAM-Abzüge und Savestates benutzt. Abschließend stimmt der
ausgegebene Code textgenau mit der lokalen Quell-INI überein.

Nächste fachliche Arbeit: zunächst die bereits in 4:3 sichtbaren
Schleim-/NPC-Artefakte isolieren und die Ausführung aller C2-Hooks prüfen;
danach FLUDD-HUD, Film-Seitenverhältnis und reproduzierbare Rand-Culling-Tests.
Ultrawide bleibt bis zur belastbaren 16:9-Abnahme zurückgestellt.
