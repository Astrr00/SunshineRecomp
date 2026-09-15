# Ausgabe-Skalierer und hohe Auflösung

Stand: 2026-09-15. Der Auftraggeber hat am selben Tag als Ziel genannt:
„Widescreen-Auflösungen und bis zu 4K möglich. Integrierter Grafikskalierer
damit es hochauflösender wird." Der Skalierer stand in keinem Arbeitspaket;
dieses Dokument legt ihn an und hält fest, was daran belegt ist und was nicht.

## Der Befund: zwei Kerne waren eingebaut, aber unerreichbar

Die Laufzeit hat bereits einen gammakorrekten Ausgabe-Skalierer. Er sitzt in
`VideoCommon/PostProcessing.cpp` und rechnet in
`Data/Sys/Shaders/default_pre_post_process.glsl`. Der Shader kennt **neun**
Kerne:

| `resampling_method` | Kern |
|---|---|
| 0 | Voreinstellung — Hardware-Abtastung, **nicht** gammakorrekt |
| 1 | Bilinear |
| 2 | Bikubisch: B-Spline |
| 3 | Bikubisch: Mitchell-Netravali |
| 4 | Bikubisch: Catmull-Rom |
| 5 | Sharp Bilinear |
| 6 | Area Sampling |
| 7 | **Nearest Neighbor** |
| 8 | **Bikubisch: Hermite** |

Die C++-Aufzählung `OutputResamplingMode` (`VideoConfig.h:68-77`) endete
dagegen bei 6. Die beiden letzten Kerne waren also seit jeher umgesetzt, aber
über keine Einstellung erreichbar. Für ganzzahlige Vielfache ist Nearest
Neighbor der schärfste Weg und genau das, was man für „hochauflösender ohne
Weichzeichnen" will.

## Was gebaut wurde

Drei Patches:

| Patch | Inhalt |
|---|---|
| `recompcore-scaler-kernels.patch` | `NearestNeighbor` und `BicubicHermite` in die Aufzählung, damit die beiden vorhandenen Kerne erreichbar werden |
| `moderngekko-scaler.patch` | der Kern als Produkteinstellung: `GraphicsSettings::output_resampling`, Prüfung 0..8, `scaler=` in `config.ini`, `--scaler <name>` auf der Befehlszeile, Namen statt Zahlen |
| `moderngekko-host-call-active.patch` | gehört nicht hierher, siehe [16](16-RUECKWEG.md) |

Bedient wird mit Namen, nicht mit Zahlen — niemand soll wissen müssen, dass 5
„Sharp Bilinear" heißt:

```
scaler=auto | bilinear | bspline | mitchell | catmull-rom
     | sharp-bilinear | area | nearest | hermite
```

## Was belegt ist

**Die Einstellung kommt an.** Zwei Läufe am echten Spiel, sonst gleich:

| Lauf | erzeugte `GFX.ini` |
|---|---|
| `scaler=nearest` | `[Enhancements]`, `OutputResampling = 7` |
| ohne `scaler` | kein `[Enhancements]`-Abschnitt |

Der Wert 7 ist genau der Kern, der vor diesem Patch nicht erreichbar war.

**Ein unbekannter Name wird abgewiesen**, nicht stillschweigend ignoriert:

```
invalid config.ini: unknown scaler: lanczos     (Rückgabewert 1)
```

**Die Tests laufen ohne Spielkopie.** `moderngekko_frontend_config_test`
prüft die Namensabbildung, den Rundlauf durch `config.ini` und die Abweisung
eines unbekannten Namens.

## Was ausdrücklich nicht belegt ist

**Die Bildwirkung.** Der Ausgabe-Skalierer läuft nur im Präsentationspfad, und
der braucht eine echte Ausgabefläche. In dieser Umgebung gibt es keine:
`PlatformHeadless::GetWindowSystemInfo` (`PlatformHeadless.cpp:36-44`) liefert
`render_surface = nullptr`, und ohne Swapchain gibt es keinen Backbuffer, an
dem skaliert werden könnte.

Das ist gemessen, nicht vermutet: Dieselbe FIFO-Aufzeichnung, einmal mit Kern 1
(Bilinear) und einmal mit Kern 7 (Nearest Neighbor), Fenstergröße 1920x1080
gesetzt, Bildausgabe auf Fensterauflösung umgestellt:

| Gegenstand | Ergebnis |
|---|---|
| Bildgröße beider Läufe | 640 x 480 — **nicht** 1920x1080 |
| Unterschied der Bilder | `mean_abs=0.0, pixels_changed=0 von 307.200` |

Bitgleich. Der Skalierer hat nicht gearbeitet, weil er nicht arbeiten konnte.
**Die Abnahme der Bildwirkung gehört auf die Windows-Maschine mit echtem
Fenster** und steht aus.

## Hohe Auflösung: was hier belegt ist

Die interne Auflösung ist unabhängig von der Ausgabefläche und deshalb auch
kopflos messbar. Dieselbe Aufzeichnung, zwei Faktoren:

| interner Faktor | Bildgröße | Pixel |
|---|---|---|
| 1 | 640 x 448 | 0,29 MPixel |
| 6 | **3840 x 2688** | 10,32 MPixel |

Bei Faktor 6 rendert das Spiel exakt 3840 Pixel breit — die Breite von 4K —
und wegen des 4:3-Bildes 2.688 statt 2.160 Zeilen hoch, also **mehr** als 4K
in beiden Richtungen. Gerendert auf Mesas Lavapipe, einem
Software-Rasterisierer; das belegt den Bildweg, nicht die Geschwindigkeit auf
einer echten Grafikkarte.

Die getrennte Ausgabeauflösung ist in [07-ANZEIGE.md](07-ANZEIGE.md) an einem
echten Fenster bis 3440x1440 belegt. **3840x2160 wurde nie gefahren** und
bleibt offen.

## Werkzeug

`tools/framerate replay` kann jetzt drei Dinge mehr, alle für diese Abnahme:

| Schalter | Wirkung |
|---|---|
| `--internal N` | interner Auflösungsfaktor |
| `--window BREITExHOEHE` | Bildausgabe auf Fensterauflösung statt roher XFB-Auflösung |
| `--resampling K` | Kern des Ausgabe-Skalierers; ohne `--window` abgewiesen, weil wirkungslos |

Die Voreinstellung bleibt unverändert: rohe XFB-Auflösung, kein Skalieren —
so, wie es der Framerate-Spike ([11](11-FRAMERATE-SPIKE.md)) für die
Bildzuordnung braucht.

## Offen

1. Bildwirkung der neun Kerne am echten Fenster vergleichen (Windows).
2. 3840x2160 als Ausgabeauflösung fahren.
3. Eine Schärfungsstufe prüfen. Im Baum gibt es **kein** FSR/RCAS; wer sie
   will, muss sie als Nachbearbeitungsshader hinzufügen.
4. Bedienung ohne Dolphin-INIs (PLAN 0.2): Der Launcher zeigt den Skalierer
   noch nicht an.
