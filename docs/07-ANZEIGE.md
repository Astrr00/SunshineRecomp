# Anzeige: interne Skalierung, Fenster und Vollbild

Stand: 2026-09-09. Experimentelle Fortsetzung; Anforderungen 2 und 5 sind noch
nicht vollständig abgenommen.

## Implementierung

- `config.ini`: `internal_scale=1..12` und separat
  `output_resolution=auto|BreitexHoehe` (320x240 bis 8192x8192).
  `auto` verwendet gespeicherte Fenstergeometrie. Bestehende `resolution=`-
  Angaben bleiben lesbar; explizites `internal_scale` hat Vorrang.
- Launcher zeigt `Nx native`, separate Fenstergrößen und randloses Vollbild.
  Die Oberfläche wurde gebaut, aber noch nicht visuell bedient/geprüft.
- Win32: physische Client-Pixel, DPI-Kontext, randloses Monitor-Vollbild,
  Alt+Enter, Rückkehr zur vorherigen Fensterposition/-größe; Escape verlässt
  zunächst Vollbild. Fenstergrößen oberhalb der Desktopgröße werden nicht
  still auf die maximale Desktop-Fensterhöhe beschnitten.
- Fenstertitel werden auf dem Fensterthread aktualisiert, damit der Titelthread
  beim Beenden nicht synchron auf die Fensternachrichtenverarbeitung wartet.
- Fensterkonfiguration wird erst nach Core-Shutdown gespeichert; die
  Vollbildumschaltung selbst ändert keine globale Dolphin-Konfiguration mehr.

## Build und Tests

`moderngekko-run` und `moderngekko-launcher` wurden gebaut. Vier ausgeführte
Testprogramme lieferten Exit 0: `moderngekko_frontend_config_test`,
`moderngekko_frontend_config_gamecube_test`,
`moderngekko_automation_protocol_test`, `moderngekko_launcher_savestates_test`.
`ctest` fand in diesem Build keine registrierten Tests; deshalb wurden die
Programme direkt ausgeführt. Die neuen Konfigurationstests prüfen Priorität,
Legacy-Migration, Erhalt der Ausgabegröße und ungültige Eingaben.

Der Launcher erwartete `Core/SavestateLayout.h`, der im ABI-4-Vendor-Pin fehlt.
Der Header wurde unverändert aus dem lokal vorhandenen Original-Vendor-Commit
`55c7b023fa0f4eba1cf3fdbbb25b1c5ec468d5ac` übernommen. Es wurden keine
Spieldaten geladen oder verändert.

## Messungen und Fehlerdiagnose

Lokale JSON-Protokolle und PNGs unter `build/display-verification-v2/` bis
`build/display-verification-v6/`. Der erste Versuch ohne Suffix verlor sein
Ergebnis wegen einer nicht abgefangenen Shutdown-Ausnahme und ist keine
vollständige Testaufzeichnung.

| Lauf | Vorgabe | Win32-Client | Ausgabe-PNG |
|---|---|---|---|
| v2/scale1 | Faktor 1, 1280x720 | 1280x720 | 1280x720 |
| v2/scale3 | Faktor 3, 1280x720 | 1280x720 | 1280x720 |
| v2/output1080 | Faktor 1, 1920x1080 | 1920x1057 | 1879x1057 |
| v3/output1080 | Faktor 1, 1920x1080 | 1920x1080 | 1920x1080 |
| v4/output1080 | Faktor 1, 1920x1080 | 1920x1080 | 1920x1080 |

v2/output1080 belegt die inzwischen korrigierte Windows-Größenbegrenzung.
Die Bildausgabe verwendet `FrameDumpsResolutionType=0`; sie misst hier die
Ausgabe, nicht die interne EFB-Größe. Der separate Vergleich unter
`build/display-internal-verification/` mit `FrameDumpsResolutionType=1`
bestätigt bei gleicher 1280x720-Fenstergröße: Faktor 1 ergibt **796x448**,
Faktor 3 **2389x1344** (XFB mit Seitenverhältniskorrektur). Beide Profile
führten nach den Vollbildwechseln weitere 30 Frames aus und endeten mit
Exit 0. Damit ist die Trennung in dieser Szene direkt gemessen.

Der dritte interne Test (output1080, PID 12480) erreichte die Automation
nicht: Eine native Warnung zeigte `IOS_FS: Failed to rename temporary FST
file`. Win32-Fenstertext tatsächlich ausgelesen; im neuen Profil lagen
`Wii/fst.bin` und `Wii/fst.bin.xxx` mit jeweils 384 Bytes. Der Prozess lebte
nach dem Timeout weiter und wurde nach dieser Diagnose beendet. Kein
erfolgreicher Start; die konkrete Ursache der Rename-Störung ist offen.
Der vierte interne Test wurde deshalb nicht begonnen. Die vier separaten
Ausgabetests in v6 waren zuvor vollständig erfolgreich.

Vollbildwechsel in v2/scale1, v2/scale3, v3/output1080 und v4/output1080:
Outer-Rect exakt `(0,0,1920,1080)`, Client 1920x1080, Stil `0x94000000`.
Rückwechsel stellt die ursprüngliche Client-Größe und Position wieder her.
Gemessene DPI: 96. Mehrmonitor- und HiDPI-Wechsel sind noch ungeprüft.

Die Bilder v3/output1080 und v2/scale3 wurden tatsächlich betrachtet:
Delfino Plaza, Mario/FLUDD, sichtbarer Schatten, Münzähler links oben,
Wassertank rechts unten. Das ist keine vollständige HUD-/Grafikabnahme.

**Hänger:** In v2 bis v4 blieb Stop nach den Wechseln hängen. Temporäre
Instrumentierung in v4 bestätigte: MainLoop beendet, Geometrie gespeichert,
Automation gestoppt, Core-State-Callback und Achievements beendet, FIFO
angehalten; `CPUManager::Stop()` kehrte nicht zurück. Die CPU-Zeit nahm weiter
zu. Auch v5 mit vorherigem Pause-Befehl hing. Die betroffenen Diagnoseprozesse
wurden nach bestätigtem Fortbestehen beendet. Der Titelthread-Fix beseitigte
diesen Fehler nicht; die ursprüngliche Zuordnung war unvollständig.
Die Instrumentierung wurde wieder entfernt. v6 prüft die Verlegung der
Konfigurationsspeicherung nach Core-Shutdown: **alle vier Profile erfolgreich**,
einschließlich Vollbildstart und regulärem Stop aus laufender Simulation,
Exit 0 ohne vorgeschaltetes Pause. v6 misst Fenster und Ausgabe exakt:
1280x720 bei Faktor 1 und 3; 1920x1080 bei Faktor 1; Vollbildstart 1920x1080,
Wechsel zurück zu 1280x720 und erneut 1920x1080. Damit ist der eingeführte
Hänger in dieser Testmatrix beseitigt. Die tieferliegende Reaktion der CPU
auf solche globalen Konfigurationsänderungen wurde nicht allgemein repariert.

## Reproduktion und offene Arbeit

`tools/diagnostics/windows_display_probe.py --output <neues-Verzeichnis>`
startet vier Profile mit dem lokalen gepaarten Plaza-Checkpoint. Optional
`--pause-before-stop`. Der Runner stoppt nach einem noch lebenden Testprozess,
statt weitere Prozesse aufzuhäufen. Er benutzt Win32-Messungen und den
lokalen Toggle-Message-Handler; die echte Alt+Enter-Tastenkombination ist damit
noch nicht separat getestet. Die UI wird nicht über Screenshots ferngesteuert.

Es werden keine Spiel-Save-Befehle gegeben. Savestates stellen ursprüngliche
Kartenpfade wieder her; die Test-GCI blieb nach v4 unverändert bei
`8e1ac668415c553f18702d6c887d1b631b81cc93cf0e1af53070620ee11cae14`.

Patches im Bootstrap: `moderngekko-display-settings.patch` (nach FIFO-Patch),
`recompcore-win32-display.patch`, `recompcore-savestate-layout.patch`.
Die vollständigen Patchketten wurden auf temporären Kopien der gepinnten
Originaldateien angewendet. Ergebnis textgleich mit den geänderten Quellen;
alle Reverse-Checks am Arbeitsbaum bestanden, einschließlich des älteren
FIFO-Patches (Bootstrap-Idempotenz). Kein Commit/Push.

Abschließende GCI-Prüfung nach allen Anzeigeversuchen: weiterhin
`8e1ac668415c553f18702d6c887d1b631b81cc93cf0e1af53070620ee11cae14`.
Kein `moderngekko-run`-Diagnoseprozess ist mehr aktiv. Der gepaarte
Plaza-Checkpoint bleibt unverändert für die Fortsetzung verfügbar.
