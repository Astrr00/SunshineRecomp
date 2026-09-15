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
| Einleitungsfilm nach Spielstart | rund 1.900 Frames | THP-Video (ein Zeichenbefehl je Frame, 3.625 B), kein 3D |
| Flugplatz-Zwischensequenz (Mario, Peach, Toadsworth am Flugzeug) | 11 mal 120 | 3D-Szene mit 8.800 bis 9.700 Zeichenbefehlen und 650 bis 670 KB je Frame; Kamera bewegt sich nach jedem Dialogschritt |

Der Spielstart über die Automation brauchte drei Anläufe, weil die
Dateiauswahl keinen Cursor zeigt: Start am Titel; A überspringt den Titel;
A öffnet „create a file … in Slot A?", A wählt YES, A bestätigt „File
created."; danach wählt der Stick (rechts, dann links) eine Kiste, A öffnet
„START / COPY / ERASE / SCORE", A startet. Die verwendete Folge steht in
`tests/fixtures/game-start.json`; sie ist nicht minimiert. Danach läuft der
Einleitungsfilm rund 1.900 Frames; die Zwischensequenz dahinter wartet nach
jedem Satz auf A. Ein Zeichenbefehl-Zähler auf dem ersten Frame jeder
Aufzeichnung (1 = Film, 0 = Überblendung, 8.800 = Szene) zeigt, wo man ist.

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

### Bewegte Kamera: Flugplatz-Zwischensequenz

Der entscheidende Fall. Nach dem ersten Dialogschritt schwenkt die Kamera
über den Flugplatz (Median der Verschiebung aller Positionsmatrizen 126,
dann 93 Einheiten je Frame, abklingend). Zwischenbild für die Frames 1→2
dieses Fensters:

| | Wert |
|---|---|
| zugeordnet | 8.813 von 8.817 Zeichenbefehlen (99,95 %) |
| interpolierte Wörter / XF-Ladungen | 1.861.611 / 147.875 (+8,2 MB) |
| Prüfung | Signaturen gleich, 0 Wörter neben dem Zwischenwert, B wie im Original |
| A gegen B | 153.718 Pixel (53,6 %), mittlere Differenz 16,6 |
| A gegen Zwischenbild | 114.716 Pixel (40,0 %), 10,85 |
| Zwischenbild gegen B | 116.108 Pixel (40,5 %), 10,99 |
| geänderte Pixel mit Zwischenbild im Intervall [A, B] | 133.448 von 153.718 (86,8 %) |
| nur im Zwischenbild geändert | 15.218 (5,3 % des Bildes) |

Die Differenzen zu A und zu B sind gleich groß: Das Zwischenbild liegt in
der Mitte. Im Bild selbst ist es ein sauberes Zwischenbild des Schwenks:
Peach, Mario, der hereinlaufende Toadsworth, Flugzeug und Palme stehen
konsistent zueinander, keine Doppelkonturen. Die Nur-Zwischenbild-Pixel
verteilen sich über Kanten und die Wolkenschicht am Himmel; bei 53 %
bewegten Pixeln ist ein Anteil außerhalb des Intervalls durch verdeckte und
freigelegte Flächen zu erwarten und kein Fehlerbeleg.

## Teil 2b: Schnitte

Was die Aufzeichnungen an Bewegung zeigen (Median der Verschiebung der
zugeordneten Positionsmatrizen je Frame-Paar, in Spieleinheiten):

| Situation | Zuordnung | Verschiebung je Frame |
|---|---|---|
| Dateiauswahl, 119 Paare in Folge (Stillstand) | 99,1 bis 100 % | 0,04 bis 0,42 (90 %-Wert höchstens 1,4) |
| Zwischensequenz, Kamera steht (w15, w16) | 99,5 bis 100 % | höchstens 0,11 |
| Szenenbeginn nach dem Film: Irisblende und Kameraschwenk (w14, d01) | 94 bis 99 % | 41, 118, 205, 263, 229, 186, 151, 115, 85, 65, 42, 31, 21, 13, 9 |
| Kameraschwenk nach Dialogschritt (d02) | 100 % | 126, 93, 70, 54, 42, 35, 26, 20, 17, 14, 11, 8 (abrupt aus dem Stand) |
| Kamerafahrt nach jedem weiteren Dialogschritt (d03 bis d11, identisch) | 96 bis 100 % | 11, 15, 20, 22, 23, 12, 2 |
| Filmübergang: 0, dann 255, dann 8.561 Zeichenbefehle | 0 %, 2,9 % | nicht bestimmbar |
| Titel gegen Dateiauswahl (harter Szenenwechsel, zwei Dateien) | 37,6 % der Dateiauswahl-Befehle | 1.638 |

Daraus die Heuristik in `spike.py` (`cut_verdict`), drei Regeln:

1. **Weniger als 60 % zuordenbar**: anderer Inhalt. Trifft Filmframes (ein
   Zeichenbefehl), den Filmübergang und den harten Szenenwechsel.
2. **Verschiebung über 1.000**: gleiche Inhalte, andere Kamera. Trifft den
   harten Szenenwechsel (1.638); Schwenks erreichen 263.
3. **Sprung gegenüber dem Vorpaar**: Verschiebung über 50 und mehr als
   achtmal so groß wie im Vorpaar. Ein Schwenk wächst stetig (41, 118, 205,
   263: Faktor höchstens 2,9), ein Schnitt kommt aus dem Stand.

Ergebnis über alle 17 aufgezeichneten Fenster der Zwischensequenz (2.040
Paare): angeschlagen nur bei Filmframes und am Filmübergang; kein
Kameraschwenk und keine Kamerafahrt wurde als Schnitt gewertet. Die erste
Fassung mit einer festen Schwelle von 200 hatte drei Schwenkframes falsch
markiert; die Irisblende am Szenenbeginn (das Bild wächst aus einem
schwarzen Kreis, während die Kamera schwenkt) zeigt, warum eine reine
Schwelle nicht reicht.

Zwei Grenzen, beide belegt oder aus den Zahlen ableitbar:

- **Ein abrupt beginnender Schwenk** (d02: 126 aus dem Stand) wird nach Regel
  3 einmal als Schnitt gewertet, sobald Vorgeschichte vorliegt. Folge: ein
  ausgelassenes Zwischenbild, ein 30-Hz-Schritt an dieser Stelle, kein
  Geisterbild. Die umgekehrte Fehlentscheidung (Schnitt nicht erkannt) wäre
  ein Geisterbild aus zwei Kameras; die Regeln sind bewusst so gewählt.
- **Ein Kameraschnitt bei gleichem Inhalt und kleiner Distanz** (etwa 300
  Einheiten, aus einem Schwenk heraus) ist nicht in den Aufzeichnungen und
  von einem Schwenk mit derselben Verschiebung nicht zu unterscheiden. Der
  Dialogteil der Flugplatz-Sequenz enthielt keinen solchen Schnitt: Nach
  jedem A fährt die Kamera, sie springt nicht. Die Aufzeichnung einer
  Sequenz mit Gegenschnitt (Sprecherwechsel) steht aus.

## Stand der Spike-Kriterien aus PLAN 5.3

| Kriterium | Stand |
|---|---|
| mindestens 90 % Zuordnung in Spielszenen | erfüllt: Titel und Dateiauswahl 100 %, Zwischensequenz mit Kamera in Bewegung 96 bis 100 % |
| Zwischenbild plausibel | ja: Dateiauswahl 92,9 % und Kameraschwenk 86,8 % der geänderten Pixel zwischen A und B, Differenzen zu A und B gleich groß, kein sichtbares Artefakt; Titel neutral (Stillstand, Effekt-Restdifferenz) |
| Schnitt erkannt | Filmübergang und harter Szenenwechsel ja, Schwenks nicht fälschlich; Gegenschnitt in gleicher Szene nicht beobachtet |

Auf der Ebene, die sich hier messen lässt, ist das ein **Go für Variante A**
(Interpolation im Renderer) mit zwei benannten Restrisiken: Gegenschnitte
mit kleiner Distanz und Effektmatrizen. Die Entscheidung nach PLAN 5.4 (was
„unbegrenzt" umfasst) bleibt beim Auftraggeber.

## Was nicht belegt ist

- **Gegenschnitt in gleicher Szene**, siehe oben.
- **Spielszene mit Steuerung.** Alle bewegten Szenen sind Zwischensequenzen
  mit Kamerafahrt; eine gesteuerte Szene (Mario läuft, Kamera folgt) wurde
  nicht aufgezeichnet, weil die Sequenz nach dem Film auf Eingaben wartet.
- **Kosten auf der GPU.** Lavapipe rendert die Flugplatz-Szene in rund einer
  Sekunde je Frame; das sagt nichts über eine echte GPU. Die Kosten der
  Variante A sind ein zweiter Durchlauf des Befehlsstroms je Zwischenbild
  (8.800 Zeichenbefehle, 670 KB) plus die Matrixinterpolation.
- **Rotation.** Matrizen werden affin gemischt; bei den gemessenen Schritten
  ist das unsichtbar, bei schnellen Drehungen schrumpft die Matrix zwischen
  den Stützstellen.
- **Länge.** Stichproben von drei bis 120 Frames, 17 Fenster.

## Nebenbefund: Stapeltiefe über 30.000 Frames

Ohne Eingabe (Vorspann und Titelschleife) lag die tiefste Stapelnutzung bei
`0x80424CB8`: 12 KB von 64 KB belegt, 54.176 Bytes über dem Ende des
Widescreen-Codebereichs. Das ergänzt Befund 1 aus Dokument 10, ersetzt aber
keine Messung im Spiel.
