# Grafikdiagnose: Schleimflächen und NPCs am Delfino Airstrip

Stand: 2026-09-09. **Fehler eingegrenzt, nicht behoben.** Keine der hier
getesteten Genauigkeitseinstellungen wurde in das normale Widescreen-Profil
übernommen. Die ursprünglichen Anforderungen bleiben vollständig bestehen.

## Was getestet wurde

Der ungepatchte Gameplay-Savestate
`build/widescreen/cold-auto/cold-front.sav` wurde in separaten Profilen geladen.
Danach: 45 Frames rückwärts laufen, 25 Frames C-Stick rechts, 60 Frames neutral,
Screenshot. Eingaben stehen auch in `tests/fixtures/airstrip-camera.json`.
Alle Abzüge, Profile und Logs sind lokal unter `build/graphics-investigation/`.

**Wichtige Korrektur der Terminologie:** `--allow-interpreter` ist keine Wahl
des Interpreters. `SelectCPUCore()` in
`ref/ModernGekko/src/runtime/dolphin_runtime.cpp` wählt bei
`MODERNGEKKO_STATICRECOMP=0` unter Windows x86-64 **JIT64**.
Die Vergleichsläufe laden kein statisches Modul. `Config/Dolphin.ini` bestätigt
`CPUCore=1`; statische Läufe verwenden `CPUCore=6` und melden das geladene Modul.
Das Architekturziel bleibt statische Recompilation; JIT dient nur der Diagnose.

| Lokaler Versuch | Änderung gegenüber Standard | Bildbefund |
|---|---|---|
| `jit-auto/jit-turn.png` | JIT64, Vulkan, 3× | Fragmentierter NPC und überlagerte Schleimflächen wie im statischen Lauf |
| `vulkan1/auto/turn.png` | JIT64, Vulkan, 1× | Auffälligkeit bleibt |
| `opengl1/auto/turn.png` | JIT64, OpenGL, 1× | Auffälligkeit bleibt |
| `vulkan-explicit/auto/turn.png` | GMS.ini-Werte explizit in lokaler GMSE01.ini | Auffälligkeit bleibt |
| `accurate/auto/turn.png` | Mehrere Genauigkeitsschalter gemeinsam | NPC geschlossen, großflächiger Schleimeffekt fehlt |
| `format/auto/turn.png` | Nur EFBEmulateFormatChanges=True | Auffälligkeit bleibt |
| `truecolor/auto/turn.png` | Nur ForceTrueColor=False | Auffälligkeit bleibt |
| `depth/auto/turn.png` | Nur FastDepthCalc=False | Auffälligkeit bleibt |
| `shader/auto/turn.png` | Nur ShaderCompilationMode=0 | Auffälligkeit bleibt |
| `sampling/auto/turn.png` | Nur FastTextureSampling=False, JIT64, 1× | NPC geschlossen, großflächiger Schleimeffekt fehlt |
| `static-sampling1/auto/turn.png` | Dasselbe mit statischem Modul, 1× | Gleicher scheinbar sauberer Befund |
| `jit-sampling3/auto/turn.png` | Sampling aus, JIT64, 3× | Auffälligkeit wieder vorhanden |
| `static-sampling3/auto/turn.png` | Sampling aus, statisches Modul, 3× | Auffälligkeit wieder vorhanden |
| `static-nativecopy3/auto/turn.png` | Sampling aus + EFBScaledCopy=False, statisch, 3× | NPC geschlossen, großflächiger Schleimeffekt fehlt; kopierte Bildteile sichtbar niedrig aufgelöst |
| `native-newgame/auto/newgame-paint.png` | Letzte Kombination, 16:9; Spielszene neu aus Dateiauswahl aufgebaut | **Auffälligkeit wieder vorhanden** |
| `jit-newgame/auto/newgame-paint.png` | Gleiche Dateiauswahl, gleiche Grafikeinstellungen; Szenenaufbau unter JIT64 ohne Modul | **Gleiche Auffälligkeit** |

Ein D3D-Versuch startete gar nicht: ModernGekkos Frontend akzeptiert in
`config.ini` nur Vulkan und OpenGL. Es gibt dazu keinen Bildvergleich.

## Was diese Ergebnisse bedeuten – und was nicht

Die erste Schlussfolgerung „FastTextureSampling=False beseitigt den Fehler“
war zu stark und wurde durch den Szenenneuaufbau widerlegt. Das Verschwinden
eines Spieleffekts nach Savestate-Laden darf nicht als korrektes Rendering
gewertet werden. Auch „Sampling aus + native EFB-Kopien“ ist **keine Lösung**.

Die CPU-Vergleiche zeigen das gleiche Verhalten **aus dem übernommenen Zustand**.
Sie schließen einen Fehler in persistenten Daten, die zuvor beim statischen
Spielstart erzeugt wurden, nicht aus. Ein ausschließlich im laufenden nativen
CPU-Pfad entstehender Fehler ist damit weniger wahrscheinlich, aber kein
vollständiger CPU-Ausschluss bewiesen.

Der separate JIT64-Kaltstart (`jit-cold/`) erreichte den Titelbildschirm, aber
in dieser Sitzung nicht die Dateiauswahl. Eingaben kamen nachweislich im
Spiel-RAM an: `0x80404454` enthielt vor der Eingabe `0000`, bei gehaltenem
A+Start `1100`. Trotz mehrerer bestätigter Befehle blieb der Titelbildschirm.
Das ist weder eine gültige Gameplay-Referenz noch ein Anlass, blind denselben
Start immer wieder zu wiederholen. Das Verhalten bleibt zu untersuchen.

`native-newgame/` wurde aus dem früheren Widescreen-**Dateiauswahl**-Savestate
gestartet, dann Block A gewählt und die Einleitung bis zur neuen Spielszene
durchlaufen. Es wurde ausdrücklich **kein Gameplay-Savestate** geladen.
Es ist trotzdem kein vollständiger Kaltstart. Die angelegten Bildschirmabzüge
belegen Dateiauswahl, Dialog und die neu aufgebaute Szene.

**Nachfolgend ausgeführter stärkerer Vergleich:** `jit-newgame/` lädt dieselbe
Dateiauswahl und baut den Flugplatz mit JIT64 neu auf. Auswahl, Einleitung,
Dialog und Kameradrehung wurden per Eingabe durchlaufen. Kein statisches Modul
wurde übergeben; nach regulärem Beenden bestätigt die gespeicherte Konfiguration
`CPUCore=1`. Das resultierende Bild zeigt denselben fragmentierten NPC und
dieselben auffälligen Schleimflächen wie `native-newgame/`. Der Fehler wurde
also nicht bloß in einem bereits aufgebauten Gameplay-Savestate übernommen.
Frühere globale Zustände aus dem Dateiauswahl-Savestate bleiben als gemeinsame
Vorgeschichte; der Grafik-/Texturpfad ist nun die vorrangige Untersuchungsspur.

Beide neu erzeugten Zustände sind gesichert als
`native-newgame/auto/newgame-paint.sav` und
`jit-newgame/auto/newgame-paint.sav`. Nicht mit ungepatchten 4:3-Profilen mischen:
hier war jeweils derselbe spielseitige 16:9-Code aktiv.

## Relevante Quellstellen

Unter `ref/ModernGekko/vendor/dolphin/Source/Core/VideoCommon/`:

- `ShaderGenCommon.cpp`, `ShaderHostConfig::GetCurrent`: manuelles Sampling
  wird über `!bFastTextureSampling` gewählt.
- `VideoConfig.h`, `ManualTextureSamplingWithCustomTextureSizes`: bei
  EFB-Skalierung ungleich 1 und `bCopyEFBScaled` wird ein anderer Pfad gewählt.
- `PixelShaderGen.cpp`, `sampleTexture`: schneller Pfad nutzt Hardware-Sampling;
  manueller Pfad verwendet Texel-Zugriff, Wrapping und eigene LOD-Berechnung.
  Der Pfad für angepasste Texturgrößen skaliert UVs und benutzt Modulo;
  der native Pfad benutzt für Repeat/Mirror bitweise Operationen.
- `Core/Config/GraphicsSettings.cpp` (relativ zu `Source/Core/`): Standardwerte
  `FastTextureSampling=True`, `EFBScaledCopy=True`.
- `Data/Sys/GameSettings/GMS.ini`: Sunshine-spezifische EFB-/Mipmap-Vorgaben
  sind im gebauten Sys-Verzeichnis vorhanden. Explizite Wiederholung dieser
  Werte beseitigte den Fehler nicht.

Diese Unterschiede begründen weitere Untersuchungen, sind noch kein Beweis
für einen bestimmten fehlerhaften Ausdruck im Shader.

## Reproduzierbare Testhilfe

`scripts/render-probe.py` startet einen isolierten Vergleichslauf, wartet auf
einen angegebenen Savestate-Frame-Schwellwert, spielt eine Eingabesequenz ab,
wartet auf die tatsächliche PNG-Ausgabe und beendet seinen Prozess regulär.
Es speichert Aufruf, PID, Zustand, Savestate-/PNG-SHA-256, PNG-Maße und Exitcode
in `manifest.json`. Ein bestehendes Ausgabeverzeichnis wird nicht überschrieben.
Bei einem nicht beendeten Prozess bleibt dessen PID protokolliert; kein
automatisches Töten und Neustarten aufgrund eines Timeouts.

Beispiel, mit dem verfügbaren Python-Interpreter ausführen:

```powershell
python scripts/render-probe.py `
  --output build/graphics-investigation/neuer-vergleich `
  --state build/widescreen/cold-auto/cold-front.sav `
  --cpu jit64 --minimum-frame 7000 `
  --sequence tests/fixtures/airstrip-camera.json
```

Für statische Ausführung `--cpu static --module <lokale-DLL>` verwenden.
Optional: `--resolution 1920x1080`, `--backend OpenGL`,
`--game-settings <lokale-GMSE01-INI>`.

Der neue Runner wurde tatsächlich als `harness-check/` ausgeführt und lieferte
ein PNG plus Manifest und Exitcode 0. Er ist **kein automatischer Beweis für
grafische Korrektheit**. Zeitlich identische Frames sind ebenfalls nicht
garantiert; CPU-/GPU-Thread und Screenshot-Auftrag laufen asynchron.

## Nächster Schritt

Die beim Szenenaufbau erzeugten Textur-/EFB-Daten und deren Savestate-Verhalten
prüfen; die CPU-Referenz ab Szenenaufbau liegt inzwischen vor, als Nächstes
die entsprechenden RAM- und GPU-Texturen direkt vergleichen. Kein weiterer
„Fix“ nur durch Verschwinden der sichtbaren Fragmente. Die zweite offene Spur
ist die tatsächliche Ausführung sämtlicher Gecko-C2-Stellen.

Ton, FLUDD, reguläres Fortschrittsladen, Framerate-Entkopplung und die übrigen
Port-Anforderungen sind durch diese Versuche nicht erledigt.

## Stand zum Fortsetzen

Die Testprozesse mit JIT64 wurden regulär beendet. Der statische Lauf
`native-newgame/auto` ist pausiert; der frühere Widescreen-Lauf
`build/widescreen/generated-auto` ist ebenfalls noch pausiert.
`build/graphics-investigation/image-manifest.json` enthält Maße und SHA-256
von 30 PNGs einschließlich der letzten JIT-Neuaufbau-Bilder.
