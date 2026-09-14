# Framerate-Spike: Was zwischen zwei Frames wirklich passiert

Stand: 2026-09-14. Erster Teil von WP13 ([PLAN.md](PLAN.md), Abschnitt 5.3),
gemessen an echten FIFO-Aufzeichnungen aus dem kopflosen Prüfstand
([10-KOPFLOSER-PRUEFSTAND.md](10-KOPFLOSER-PRUEFSTAND.md)). Kein Bild, keine
Interpolation, keine Entscheidung -- nur die Zahlen, an denen die Entscheidung
zwischen renderer- und spielseitiger Interpolation hängt.

**Keine Spieldaten im Repository.** Die Aufzeichnungen enthalten Spielinhalte
und blieben in der Sitzung.

## Werkzeug

`tools/framerate` liest DFF-Aufzeichnungen (Version 6) und zerlegt den
GX-Befehlsstrom nach RecompCore `c6a600eb` (`FifoDataFile.cpp`,
`OpcodeDecoding.h`, `CPMemory.h`, Größentabellen der `VertexLoader_*.h`). Es
verfolgt CP-, XF- und BP-Zustand, löst indizierte Matrixladungen aus den
aufgezeichneten Speicheraktualisierungen auf und ordnet Zeichenbefehle
zweier Frames über eine längste gemeinsame Teilfolge ihrer Signaturen zu
(Primitivtyp, Vertexformat, Anzahl, Texturregister). 13 Tests an einer
synthetischen Aufzeichnung.

Aufgenommen wurde mit `headless_probe.py --fifo`, nach Eingabefolgen über das
Automationsprotokoll. Drei Szenen:

| Szene | Frames | Befund |
|---|---|---|
| Vorspannfilm (Frame 1500) | 3 | ein Zeichenbefehl, 430 KB Texturaktualisierung je Frame: THP-Video, für den Spike unbrauchbar |
| Titelbild (nach Start) | 3 | 3D-Szene mit Wasser |
| Flugplatz (Dateiauswahl, Slot A, Einleitung) | 4 | Spielszene, Mario-Objekt vorhanden (`gpMarioAddress` = `0x80E9AD44`) |

Alle Frames wurden vollständig dekodiert: null unbekannte Opcodes, kein
Abbruch, keine Display-Listen, keine unaufgelösten indizierten Ladungen.

## Messwerte

| | Titelbild | Flugplatz |
|---|---|---|
| Befehlsstrom je Frame | 279.950 B | 369.695 B |
| Zeichenbefehle je Frame | 1.285 | 3.097 |
| Vertices je Frame | 8.829 | 23.335 |
| Positionen direkt im Strom (CPU-erzeugt) | 73 (5,7 %) | 128 (4,1 %) |
| Positionen indiziert aus Vertexfeldern | 1.212 | 2.969 |
| Matrix je Vertex (Skinning) | 523 | 839 |
| XF-Matrizen unmittelbar geladen | 500 | 551 |
| XF-Matrizen indiziert aus RAM geladen | 400 | 664 |
| Projektionsladungen | 15 | 16 |
| **Zuordnung zum Vorframe** | **1.285 von 1.285 (100 %)** | **3.097 von 3.097 (100 %)** |
| davon mit geänderter Matrix | 935 | 2.440 bis 2.494 |
| davon mit geänderter Projektion | 0 | 0 |

Speicheraktualisierungen, die der Recorder je Frame mitschreibt (Frame 0 trägt
jeweils den Anfangszustand):

| | Titelbild Frames 1, 2 | Flugplatz Frames 1 bis 3 |
|---|---|---|
| Matrixfelder (`XFData`) | 13.776 / 11.724 B | 17.304 / 15.036 / 15.036 B |
| Vertexfelder (`VertexStream`) | 0 | 528 / 0 / 0 B |
| Texturen | 0 | 0 |

## Was das bedeutet

1. **Zeichenbefehle sind zwischen Frames stabil zuordenbar.** In beiden
   3D-Szenen 100 %, weit über der 90-%-Schwelle aus PLAN 5.3. Die Reihenfolge
   des Befehlsstroms ist von Frame zu Frame gleich; Einfügungen oder
   Auslassungen kamen in diesen Stichproben nicht vor.
2. **Die Bewegung steckt in den Matrizen, nicht in den Vertexdaten.** Am
   Flugplatz ändern sich je Frame 15 bis 17 KB Matrixdaten und praktisch keine
   Vertexdaten (528 Bytes einmalig, danach null). Rund 80 % der zugeordneten
   Zeichenbefehle tragen eine geänderte Matrix. Genau das ist die Voraussetzung
   für Interpolation auf Rendererseite: Man interpoliert Matrizen und lässt die
   Geometrie stehen.
3. **Beide Ladewege sind sichtbar.** Unmittelbare XF-Ladungen stehen im Strom,
   indizierte Ladungen lassen sich vollständig aus den aufgezeichneten
   Matrixfeldern auflösen. Ein Interpolator sieht also jede Matrix.
4. **CPU-erzeugte Geometrie bleibt bei 30 Hz.** Vier bis sechs Prozent der
   Zeichenbefehle bringen ihre Positionen direkt im Strom mit (Partikel,
   Wasser, Effekte). Sie lassen sich nicht über Matrizen glätten. Das
   entspricht dem Umfang, den Zelda64Recomp für sich beschreibt und der in
   PLAN 5.4 als realistisch benannt ist.
5. **Skinning ist Matrixarbeit.** 27 % der Zeichenbefehle nutzen Matrizen je
   Vertex aus der Matrixtabelle. Auch die sind interpolierbar, nur eben je
   Tabelleneintrag statt je Zeichenbefehl.

Für Variante A aus PLAN 5.2 (Interpolation in VideoCommon) ist das ein klares
Go auf der Ebene, die sich ohne Bild messen lässt.

## Was nicht belegt ist

- **Kameraschnitte.** In keiner Stichprobe wechselte die Projektion; ein
  Schnitt wurde nicht beobachtet und die Erkennung nicht geprüft. Dazu braucht
  es eine Aufzeichnung über einen Schnitt hinweg, etwa den Übergang von der
  Einleitung ins Spiel.
- **Das Zwischenbild.** Ob ein aus interpolierten Matrizen erzeugter Frame
  plausibel aussieht, ist nicht gezeigt. Der nächste Schritt ist ein
  synthetisches Zwischen-DFF (t = 0,5) und dessen Wiedergabe -- unter Windows
  mit dem FIFO-Replay-Bau aus Dokument 05, oder hier mit Dolphins
  Software-Renderer und Bildausgabe, falls der kopflos läuft.
- **Kosten.** Ein Zwischenbild bedeutet, den Befehlsstrom eines Frames erneut
  auszuführen. Bei 370 KB und 3.097 Zeichenbefehlen ist das auf einem PC
  unkritisch, gemessen ist es nicht.
- **Längere Spielabschnitte.** Vier Frames Flugplatz und drei Frames Titel
  sind Stichproben. Level mit Wasserflächen, Spiegelungen und Hitzeflimmer
  (EFB-Kopien, Dokument 05: vier je Frame) müssen gesondert aufgezeichnet
  werden.

## Nebenbefund: Stapeltiefe über 30.000 Frames

Ohne Eingabe (Vorspann und Titelschleife) lag die tiefste Stapelnutzung bei
`0x80424CB8`: 12 KB von 64 KB belegt, 54.176 Bytes über dem Ende des
Widescreen-Codebereichs. Das ergänzt Befund 1 aus Dokument 10, ersetzt aber
keine Messung im Spiel.
