# Framerate-Spike: Was zwischen zwei Frames wirklich passiert

Stand: 2026-09-14, zwei Teile. WP13 aus [PLAN.md](PLAN.md), Abschnitt 5.3,
gemessen an echten FIFO-Aufzeichnungen aus dem kopflosen Prüfstand
([10-KOPFLOSER-PRUEFSTAND.md](10-KOPFLOSER-PRUEFSTAND.md)). Teil 1 zählt, was
das Spiel zwischen zwei Frames an die GPU schickt. Teil 2 erzeugt daraus ein
synthetisches Zwischenbild, rendert es und prüft die Schnitterkennung an
Zahlen.

**Keine Spieldaten im Repository.** Aufzeichnungen, Zwischen-DFFs und Bilder
enthalten Spielinhalte und blieben in der Sitzung; hier stehen Zählwerte.

## Korrekturen gegenüber dem ersten Stand

Drei Aussagen aus Teil 1 waren falsch und sind unten berichtigt:

1. **Die „Flugplatz"-Szene war der Dateiauswahl-Bildschirm.** Die
   Eingabefolge kam nie über die Dateiauswahl hinaus; das Bild aus der
   Wiedergabe zeigt Mario am Strand vor den drei Kisten mit „Select data.".
   Die Beschriftung „Spielszene" beruhte auf einem gesetzten
   `gpMarioAddress`, das auch dort gesetzt ist. Die Zahlen bleiben gültig,
   nur die Szene heißt jetzt richtig.
2. **Der Projektionstyp steht in XF-Register 0x1026**, nicht in Bit 0 von
   0x1025 (`XFMemory.h`: `Projection { Raw rawProjection; ProjectionType
   type; }`). Damit gibt es 37 (Titel) bzw. 82 (Dateiauswahl)
   orthografische Zeichenbefehle je Frame statt „0".
3. **Die Größenfelder im DFF-Kopf zählen u32-Elemente, nicht Bytes**
   (`FifoDataFile::Load`: `ReadArray(m_BPMem, header.bpMemSize)`; nur
   `texMemSize` zählt Bytes). Der Leser lud vorher nur ein Viertel des
   Anfangszustands. Da das Spiel die betroffenen Register in jedem Frame neu
   setzt, änderte das keine Messzahl (nach der Korrektur nachgerechnet:
   identisch), wohl aber die zurückgeschriebenen Dateien: Der erste
   Wiedergabeversuch startete mit falschem Scissor-Versatz und zeigte die
   Szene im rechten unteren Viertel.

## Werkzeug

`tools/framerate` (Python, ohne Fremdbibliotheken, 26 Tests an synthetischen
Aufzeichnungen und Bildern):

| Modul | Zweck |
|---|---|
| `fifo.py` | DFF v6 lesen und schreiben; GX-Befehlsstrom zerlegen (CP/XF/BP-Zustand, indizierte Ladungen aus den Speicheraktualisierungen, Momentaufnahme der Matrizen je Zeichenbefehl) |
| `spike.py` | Zeichenbefehle zweier Frames zuordnen (gemeinsamer Anfang/Ende direkt, Rest per LCS), Bewegungsmaße je Paar, Schnitt-Heuristik |
| `interpolate.py` | synthetisches Zwischenframe zwischen zwei Frames als neue DFF |
| `replay.py` | DFF kopflos abspielen und je Frame ein PNG schreiben (DolphinNoGUI, Vulkan auf Lavapipe) |
| `images.py` | PNG lesen, Differenzen, „liegt das Zwischenbild zwischen A und B?" |

```
python tools/framerate analyze <aufzeichnung.dff> [--report <json>]
python tools/framerate interpolate <aufzeichnung.dff> --frames A B --to <zwischen.dff> [--t 0.5]
python tools/framerate replay <dff> --player <dolphin-emu-nogui> --output <verzeichnis> --images N
python tools/framerate compare A.png zwischen.png B.png [--diff-prefix <pfad>]
```

Aufgenommen wurde mit `headless_probe.py`; Eingabefolgen können jetzt
mitten in der Folge aufzeichnen (`{"record": 120, "name": "w00"}`). Der
FIFO-Player ist DolphinNoGUI aus dem ModernGekko-Bau mit
`-DMODERNGEKKO_ENABLE_FIFO_REPLAY=ON` (Dokument 05); für Bilder ohne
Bildschirm braucht er einen Vulkan-Treiber ohne Bildschirm, hier Mesas
Lavapipe (`mesa-vulkan-drivers`).

Drei Dinge am Player, die Zeit gekostet haben und für Windows genauso gelten:

- Der Software-Renderer heißt in der Konfiguration `Software Renderer`;
  `Software` fällt still auf Vulkan zurück. Unter Linux läuft er ohnehin
  nicht, weil ModernGekko `ENABLE_EGL` erzwungen abschaltet und dem
  Renderer dann die GL-Präsentation fehlt („Failed to create OpenGL window").
- Bild k gehört nur mit `[Hacks] ImmediateXFBEnable = True` zu DFF-Frame k.
  Ohne den Schalter hinken die Bilder um einen Frame nach; ein Testlauf mit
  verdoppeltem Frame hat das belegt. Die erste Bildauswertung war deshalb
  falsch und ist verworfen.
- Ohne Schleife bricht der Player nach dem letzten Frame ab, bevor die GPU
  alle Bilder geschrieben hat (1 von 3). `replay.py` spielt in Schleife und
  beendet den Player nach N Bildern. Der Assert `part_start ==
  fifoData.size()` im `FifoPlaybackAnalyzer` verlangt, dass jeder Frame mit
  der EFB-Kopie endet; eingefügte Befehle müssen davor liegen.

## Szenen

| Szene | Frames | Befund |
|---|---|---|
| Vorspannfilm (Frame 1500) | 3 | ein Zeichenbefehl, 430 KB Texturaktualisierung je Frame: THP-Video |
| Titelbild (nach Start) | 3 | 3D-Szene mit Wasser, Logo orthografisch |
| Dateiauswahl (Strand, Mario vor den Kisten) | 4 und 120 | 3D-Szene, `gpMarioAddress` = `0x80E9AD44` |
| Einleitungsfilm nach Spielstart | 6 mal 120 | THP-Video (ein Zeichenbefehl je Frame, 3.625 B), kein 3D |

Der Spielstart über die Automation brauchte drei Anläufe, weil die
Dateiauswahl keinen Cursor zeigt: Start am Titel; A überspringt den Titel;
A öffnet „create a file … in Slot A?", A wählt YES, A bestätigt „File
created."; danach wählt der Stick (rechts, dann links) eine Kiste, A öffnet
„START / COPY / ERASE / SCORE", A startet. Die verwendete Folge steht in
`tests/fixtures/game-start.json`; sie ist nicht minimiert.

## Teil 1: Messwerte je Frame

| | Titelbild | Dateiauswahl |
|---|---|---|
| Befehlsstrom je Frame | 279.950 B | 369.695 B |
| Zeichenbefehle je Frame | 1.285 | 3.097 |
| Vertices je Frame | 8.829 | 23.335 |
| Positionen direkt im Strom (CPU-erzeugt) | 73 (5,7 %) | 128 (4,1 %) |
| Positionen indiziert aus Vertexfeldern | 1.212 | 2.969 |
| Matrix je Vertex (Skinning) | 523 | 839 |
| orthografische Projektion (2D) | 37 | 82 |
| XF-Matrizen unmittelbar geladen | 500 | 551 |
| XF-Matrizen indiziert aus RAM geladen | 400 | 664 |
| Projektionsladungen | 15 | 16 |
| **Zuordnung zum Vorframe** | **1.285 von 1.285 (100 %)** | **3.097 von 3.097 (100 %)** |
| davon mit geänderter Matrix | 935 | 2.440 bis 2.494 |
| davon mit geänderter Projektion | 0 | 0 |

Speicheraktualisierungen je Frame (Frame 0 trägt den Anfangszustand):

| | Titelbild Frames 1, 2 | Dateiauswahl Frames 1 bis 3 |
|---|---|---|
| Matrixfelder (`XFData`) | 13.776 / 11.724 B | 17.304 / 15.036 / 15.036 B |
| Vertexfelder (`VertexStream`) | 0 | 528 / 0 / 0 B |
| Texturen | 0 | 0 |

Über 120 Frames Dateiauswahl (Mario steht, setzt sich, schläft ein) lag die
Zuordnung nie unter 99,1 %; die Zeichenbefehle je Frame schwankten zwischen
2.985 und 3.042.

Was das bedeutet, unverändert aus Teil 1: Zeichenbefehle sind zwischen
Frames stabil zuordenbar; die Bewegung steckt in den Matrizen, nicht in den
Vertexdaten; beide Ladewege sind sichtbar; vier bis sechs Prozent der
Zeichenbefehle bringen CPU-erzeugte Positionen mit und bleiben bei 30 Hz;
Skinning ist Matrixarbeit.

## Teil 2a: Das Zwischenbild

`interpolate.py` stellt Variante A aus PLAN 5.2 offline nach: Der
Befehlsstrom von Frame B wird übernommen; vor jedem Zeichenbefehl, der einem
Befehl aus Frame A zugeordnet ist, setzen eingefügte XF-Ladungen alle
Matrixwörter, die sich zwischen A und B unterscheiden, auf den linearen
Zwischenwert (float32, t = 0,5). Positions-, Normalen- und
Post-Transform-Matrizen (0x000–0x0FF, 0x400–0x45F, 0x500–0x5FF) und die
Projektionsparameter (bei gleichem Typ) sind erfasst. Am Ende des
Zwischenframes stellt ein Block den Zustand nach A wieder her, damit B im
Player so beginnt wie im Original. Der Zerleger prüft das Ergebnis: gleiche
Zeichenbefehle wie B, jedes geänderte Wort exakt auf dem Zwischenwert, B mit
demselben Zustand wie im Original.

| | Titel 1→2 | Dateiauswahl 2→3 |
|---|---|---|
| zugeordnet und gepatcht | 1.285 von 1.285 | 3.097 von 3.097 |
| interpolierte Wörter | 261.201 | 599.994 |
| eingefügte XF-Ladungen | 18.412 (+1.136.864 B) | 44.880 (+2.624.376 B) |
| wiederhergestellte Wörter für B | 189 | 165 |
| Prüfung: Wörter neben dem Zwischenwert | 0 | 0 |
| größte Verschiebung je Frame | 20,4 Einheiten | 19,6 Einheiten |

Die Wortzahl ist absichtlich brutal: Es wird die ganze Matrixtabelle
interpoliert, weil das Werkzeug nicht weiß, welche Einträge ein Befehl
referenziert. Ein Interpolator im Renderer hätte den Zustand direkt und
liefe über die referenzierten Matrizen (zwölf Wörter je Befehl plus
Normalen- und Texturmatrizen); die Streamvergrößerung ist ein Artefakt des
Nachbaus, kein Kostenmaß.

### Bildprüfung

Gerendert mit `replay.py` (640 mal 448, Vulkan auf Lavapipe, jede Wiedergabe
bitidentisch mit der nächsten Schleife). „geändert" heißt: mindestens ein
Kanal weicht um mehr als 8 ab.

| | Dateiauswahl 2→3 | Titel 1→2 |
|---|---|---|
| A gegen B | 4.090 Pixel (1,43 %), mittlere Differenz 0,68 | 1.100 Pixel (0,38 %), 0,29 |
| A gegen Zwischenbild | 2.928 Pixel (1,02 %), 0,45 | 1.555 Pixel (0,54 %), 0,21 |
| Zwischenbild gegen B | 1.360 Pixel (0,47 %), 0,33 | 1.298 Pixel (0,45 %), 0,20 |
| geänderte Pixel, bei denen das Zwischenbild im Intervall [A, B] liegt | 3.799 von 4.090 (92,9 %) | 769 von 1.100 (69,9 %) |
| Pixel, die nur im Zwischenbild abweichen | 117 (0,04 % des Bildes) | 752 (0,26 %) |

Dateiauswahl: Die Möwe oben links und das „Z" über dem schlafenden Mario
stehen im Zwischenbild an Zwischenpositionen, die Differenzbilder zeigen sie
je einmal halb verschoben; das Wasser (direkte Positionen) kommt aus B und
liegt deshalb näher an B. Kein sichtbares Artefakt.

Titel: Zwischen A und B bewegt sich fast nichts (0,38 % der Pixel, zwei
Vögel). Die 752 Nur-Zwischenbild-Pixel sitzen fast alle im Sonnenglanz des
Logos (Spalten 448–576, Zeilen 64–128) und sind mit bloßem Auge kaum zu
sehen: ein Leuchteffekt, der bei A und B gleich aussieht und beim
Zwischenzustand der Matrizen anders. Welche Matrix das ist, ist nicht
bestimmt. Für die Bewertung heißt das: Bei stillstehender Szene bringt
Interpolation nichts und kann Effekte minimal verändern; ein Interpolator
sollte unbewegte Matrizen (Differenz null) unangetastet lassen, was hier
schon so ist, und Effekt-Matrizen erkennbar ausnehmen können.

## Teil 2b: Schnitte

Die Schnitt-Heuristik in `spike.py` schlägt an, wenn sich weniger als 60 %
der Zeichenbefehle zuordnen lassen oder wenn der Median der Verschiebung der
zugeordneten Positionsmatrizen 200 Einheiten übersteigt (Sicht mal Modell:
ein Kamerasprung bewegt alle Matrizen). Kalibriert an zwei Extremen:

| | Zuordnung | Median Verschiebung | Urteil |
|---|---|---|---|
| Dateiauswahl, 119 Paare in Folge | 99,1 bis 100 % | 0,04 bis 0,42 (90 %-Wert höchstens 1,39; Maximum 1,8) | kein Schnitt |
| Titel gegen Dateiauswahl (harter Szenenwechsel) | 37,6 % der Dateiauswahl-Befehle | 1.638 | Schnitt |

Der Abstand zwischen beiden ist drei Größenordnungen. Was fehlt, ist der
schwierige Fall: ein Kameraschnitt bei gleichem Inhalt (Zwischensequenz),
bei dem die Zuordnung hoch bleibt und nur die Verschiebung springt. Die
sechs Fenster nach dem Spielstart enthielten noch den Einleitungsfilm; die
Aufzeichnung dahinter läuft (siehe Ergänzung unten, falls vorhanden).

## Stand der Spike-Kriterien aus PLAN 5.3

| Kriterium | Stand |
|---|---|
| mindestens 90 % Zuordnung in Spielszenen | erfüllt in Titel und Dateiauswahl (100 %); Spielszene mit Kamera in Bewegung noch offen |
| Zwischenbild plausibel | Dateiauswahl: ja (92,9 % im Intervall, Bewegung halbiert, kein Artefakt). Titel: neutral, Effekt-Restdifferenz |
| Schnitt erkannt | harter Szenenwechsel ja; Kameraschnitt in gleicher Szene nicht gemessen |

## Was nicht belegt ist

- **Spielszenen mit bewegter Kamera.** Beide gerenderten Szenen haben eine
  stehende Kamera. Die Bildprüfung sagt deshalb nichts über Kameraschwenks.
- **Kameraschnitt in gleicher Szene**, siehe oben.
- **Kosten auf der GPU.** Lavapipe rendert die Dateiauswahl in rund 0,2 s je
  Frame; das sagt nichts über eine echte GPU. Die Kosten der Variante A sind
  ein zweiter Durchlauf des Befehlsstroms je Zwischenbild (3.097
  Zeichenbefehle, 23.335 Vertices) plus die Matrixinterpolation.
- **Rotation.** Matrizen werden affin gemischt; bei kleinen Schritten ist
  das unsichtbar (größte Verschiebung 20 Einheiten je Frame), bei schnellen
  Drehungen schrumpft die Matrix zwischen den Stützstellen.
- **Länge.** Alles Stichproben von drei bis 120 Frames.

## Nebenbefund: Stapeltiefe über 30.000 Frames

Ohne Eingabe (Vorspann und Titelschleife) lag die tiefste Stapelnutzung bei
`0x80424CB8`: 12 KB von 64 KB belegt, 54.176 Bytes über dem Ende des
Widescreen-Codebereichs. Das ergänzt Befund 1 aus Dokument 10, ersetzt aber
keine Messung im Spiel.
