# Eingabefolge mit Kamerabewegung

Stand: 2026-09-16. Zweck: eine Automations-Eingabefolge, die in einer Szene mit
sichtbarer Bewegung landet — als Testvehikel für WP14 Schritt 4 (und für
Interpolationsprüfungen in Schritt 3). Hergeleitet aus
`tools/acceptance/fixtures/game-start.json` und der HANDOFF-Limit
"Pads in der Folge höchstens 300 Bilder je Schritt".

## Designentscheidung: Dateiauswahl statt echtes Gameplay

`docs/HANDOFF.md` Absatz "Eigentliches Spielgeschehen":

> Die Auswahl eines Speicherplatzes ist über das Automationsprotokoll nicht
> gelungen; die Eingaben kommen an, treffen aber die Cursor-Mechanik der
> Dateiauswahl nicht. Das ist eine Grenze der blinden Steuerung, kein belegter
> Fehler des Ports.

Echte Gameplay-Szenen mit Kamerabewegung (Delfino Plaza, FluG-Glacius usw.)
sind über die Automation **nicht erreichbar**. Eine Eingabefolge, die ins
Spiel hineinläuft, würde am Cursor-Problem der Dateiauswahl scheitern.

Der Dateiauswahl-Bildschirm selbst hat dagegen sichtbare Bewegung: Mario steht
am Strand und atmet, das Wasser läuft, der START-Schriftzug pulsiert. Mit dem
Hauptstick lässt sich der Blickwinkel **nicht** schwenken — der Dateiauswahl-
Bildschirm hat eine feste Kamera —, aber die Bewegung von Mario und Wasser
reicht aus, damit die XF-Matrixinterpolation (Schritt 3) etwas zu interpolieren
hat und Schritt 4 einen sichtbaren mid-Bild-Effekt zeigen kann.

**Wer echte Kamerabewegung braucht**, muss eine andere Lösung finden — zum
Beispiel direkt in `read_memory`/`write_memory` den Spielzustand in eine
beliebige Szene setzen, oder einen Savestate laden. Beides ist nicht in dieser
Sitzung entstanden.

## Die Folge

`tools/acceptance/fixtures/cameramovement.json` führt in vier Stufen:

| Stufe | Eingaben | Was passiert |
|---|---|---|
| 1 | `start`, 4× `a` | Boot, Titelbildschirm, Dateiauswahl erreichen (genau wie `game-start.json`) |
| 2 | 60 Bilder `main_x=1` | Mario wird nach rechts gekippt — Mario reagiert mit Animation |
| 3 | 60 Bilder `main_x=-1` | Mario wird nach links gekippt |
| 4 | 60 Bilder je `main_x`/`main_y` in 8 Richtungen | Mario dreht sich jeweils in eine andere Richtung; Wasser und START-Schriftzug pulsieren weiter |
| 5 | 60 Bilder je `c_x`/`c_y` ±64 | C-Stick-Schwenks; Wirkung im Dateiauswahl-Bild undefiniert, aber Bewegung wird registriert |

## Was die Folge **nicht** leistet

- **Echte Szenen mit echter 3D-Kamera.** Eine echte Schwenk-Szene bräuchte
  das Spiel in Delfino Plaza. Diese Folge bleibt im Dateiauswahl-Bild.
- **Schnitte.** Die Dateiauswahl hat keine FPS-Wechsel und keine
  Szenenwechsel; Schritt 3 würde keine Cuts detektieren. Wer Cuts messen
  will, muss eine andere Szene finden.
- **60-Hz-Simulation.** Die Folge ändert nichts an der Bildrate; das Spiel
  läuft weiterhin mit 30 Hz, das Zwischenbild ist die in Schritt 4 zu
  prüfende Sache.

## Verifikation

Wer die Folge fährt, sollte folgende Werte erwarten (vorbehaltlich echter
Messung):

- **Mit Stufe 3, ohne Stufe 4** (`MODERNGEKKO_GX_DRYRUN=3` ohne `_PRESENT`):
  Schatten-Bild liegt **zwischen** den Nachbarn, wo Mario sich bewegt
  (Dateiauswahl). 75–80 % der Pixel im Intervall [A, B] ± 8 — wie in
  `docs/20` für die Dateiauswahl-Bilder 1.880–1.887 dokumentiert.
- **Mit Stufe 4** (`MODERNGEKKO_GX_DRYRUN=3` plus `_PRESENT=1`): jede zweite
  Präsentation ersetzt; das Ersetzte liegt zwischen seinen Nachbarn.
- **Ohne Stufe 3** (nur `_PRESENT=1`, was der Patch wegen `g_interpolate &&
  present && present[0] == '1'` ohnehin ignoriert): kein Unterschied zur
  Kontrolle.

## Alternative Szenen mit Kamerabewegung

Falls die Dateiauswahl nicht ausreicht, drei Wege mit höherem Aufwand:

1. **Lockstep + read_memory**: einen Zustand in den Speicher schreiben, der
   den Spieler in eine Szene mit Kamerabewegung setzt (z.B. direkt nach
   `gpMarioAddress`-Setup). Erfordert genaue Adressen und einen laufenden
   Verifizierer.

2. **Savestate**: einen vorhandenen Savestate aus einem früheren Lauf laden.
   Erfordert einen Windows-Lauf, der den Savestate anlegt.

3. **Vorspannfilm überspringen**: `start` bringt den Spieler nicht direkt in
   eine Szene mit Kamerabewegung; das Vorspann-Video ist statisch
   (Filmstreifen). Wer den Film überspringt, landet auf dem Delfino Airstrip
   — dort **gibt** es Kamerabewegung. Aber: den Vorspann zu überspringen
   kostet mehrere Tastendrücke, die über die Automation nicht zuverlässig
   sind.

Diese Wege sind nicht in dieser Folge umgesetzt — sie sind als Aufgaben für
eine spätere Sitzung notiert.

## Hinweise für die nächste Sitzung

- **Pad-Werte**: `main_x`/`main_y` werden 1-basiert (1 = vollständig
  gedrückt) interpretiert, `c_x`/`c_y` als -127..127. Die Werte oben sind
  konsistent mit dem, was `tools/automation_protocol.cpp` und `tools/automation.py`
  erwarten — verifiziert per Code-Sicht, nicht per Lauf.
- **Bildzahl pro Schritt**: maximal 300, sonst kommt der Eingabe-Puffer aus
  dem Tritt. Die Stufen 2–5 halten sich mit 60 Bildern je Schritt deutlich
  darunter.
- **Lavapipe-Geschwindigkeit**: bei rund 8 Bildern je Sekunde brauchen die
  1.300 Bilder dieser Folge etwa 162 Sekunden Wanduhr. Das ist im
  akzeptablen Bereich.
- **Was als "sichtbare Bewegung" zählt**: Dateiauswahl-Mario atmet (Brust
  hebt/senkt sich), Wasser animiert, START-Schriftzug pulsiert. Die
  XF-Matrizen, die Mario bewegen, ändern sich; das reicht für die
  Interpolation in Schritt 3 und für die mid-Bild-Substitution in Schritt 4.
