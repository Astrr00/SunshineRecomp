# Widescreen: gemessen statt begutachtet

Stand: 2026-09-15. WP8, Schritt 4 aus [PLAN.md](PLAN.md). Dokument 10 hatte
diesen Schritt an den Windows-Rechner verwiesen, weil er ein Bild braucht.
Mit FIFO-Aufzeichnung und Wiedergabe ([11](11-FRAMERATE-SPIKE.md)) geht er
kopflos — und liefert dabei mehr als ein Bild: die Projektionsmatrizen selbst.

**Keine Spieldaten im Repository.** Aufzeichnungen und Bilder blieben lokal.

## Aufbau

Zwei Läufe, gleiche Eingabefolge (`tools/acceptance/fixtures/game-start.json`
plus 1.800 Bilder Vorspann), gleiche Framezahl, nur der Bau unterscheidet
sich:

| | 4:3 | 16:9 |
|---|---|---|
| Spielwurzel | `imported` | `imported-wide` (gebackenes DOL, [09](09-DOL-BEFUNDE.md)) |
| Modul | `13934c86…` | `3a655b2e…` |
| Seitenverhältnis-Konstante `0x80412408` | `0x3FAAAAAB` = 1,33333 | `0x3FE38E39` = 1,77778 |
| erreichte Bilder | 5.328 | 5.333 |

Szene: die Flugplatz-Zwischensequenz, Mario und Peach vor dem Flugzeug, mit
Münzanzeige und Dialogfeldern im Bild. Aufgezeichnet als DFF, ausgewertet mit
`python tools/framerate projections` und wiedergegeben mit
`python tools/framerate replay`.

## Was die Projektionen sagen

Fünf verschiedene Projektionen im selben Frame, in **beiden** Bauten mit
**denselben Zeichenbefehlzahlen**: 8.053, 653, 51, 15 und 1.

### Die 3D-Welt

| | 4:3 | 16:9 |
|---|---|---|
| waagerechter Maßstab (XF 0x1020) | `0x3FCBFA1F` = 1,593571 | `0x3F9A678D` = 1,206285 |
| senkrechter Maßstab (XF 0x1022) | `0x40093F9A` = 2,144507 | `0x40093F9A` = 2,144507 |
| Sichtverhältnis (senkrecht / waagerecht) | 1,345724 | **1,777778** |

Der senkrechte Maßstab ist **bitgleich**; von den sieben Wörtern der
Projektion unterscheidet sich genau eines. Der waagerechte Maßstab wird mit
**0,75697** multipliziert. Bei der zweiten perspektivischen Projektion (653
Zeichenbefehle, andere Nahebene) derselbe Faktor auf sechs Stellen.

Das ist die Definition von echtem Widescreen: mehr Sicht zur Seite, senkrecht
unverändert, keine Streckung. Das Sichtverhältnis landet exakt auf 16/9,
während es im 4:3-Bau 1,3457 beträgt und nicht 1,3333 — der eingebackene Code
setzt also nicht nur die Konstante, sondern ersetzt auch die Rechnung, was zu
den zwölf Einfügestellen aus [03](03-WIDESCREEN.md) passt.

### Das HUD

| | 4:3 | 16:9 |
|---|---|---|
| waagerechter Maßstab | `0x3B5A740E` = 1/300 | `0x3B23D70A` = 1/400 |
| waagerechter Versatz | `0xBF800000` = −1,0 | `0xBF400000` = −0,75 |
| senkrecht | `0xBB924925`, `0x3F892493` | bitgleich |

Der 2D-Raum wird also von 600 auf 800 Einheiten verbreitert, und der bisherige
Bereich 0 bis 600 bleibt mittig: Links und rechts kommen je 100 Einheiten
hinzu. Senkrecht ändert sich nichts.

### Die Filme

Zwei weitere orthografische Projektionen sind in **allen sieben Wörtern**
bitgleich, darunter die des bildschirmfüllenden Vierecks, über das der
THP-Film ausgegeben wird (`0x3B4CCCCD` = 1/320, also ein 640 Einheiten
breiter Raum über die volle Breite). Der Widescreen-Code fasst Filme **nicht**
an. Auf einem 16:9-Bildschirm wird der Film damit waagerecht gestreckt. Das
ist der Befund für WP11; Pillarbox oder Zoom bleiben zu bauen
(Entscheidung 4 im Plan).

## Was das Bild sagt

Beide Aufzeichnungen wurden mit dem FIFO-Player wiedergegeben (640x448, das
EFB-Format; die Anzeige-Streckung auf 16:9 macht erst das Frontend). Im
16:9-Bild ist rechts das ganze Rad des Flugzeugs zu sehen, das im 4:3-Bild
angeschnitten ist, und links mehr Himmel. Peach und Mario stehen gleich hoch
und schmaler — genau das, was ein 16:9-Bild in einem 4:3-Puffer tut.

Die Münzanzeige oben links, in Pixeln gemessen:

| | 4:3 | 16:9 |
|---|---|---|
| Höhe | 44 px | **44 px** |
| Breite | 123 px | 91 px (Faktor 0,74) |
| linke Kante | x = 23 | x = 18 |

Die Höhe stimmt exakt, die Breite folgt dem vorhergesagten Faktor 0,75 auf
einen Pixel genau. Auf einem 16:9-Bildschirm, der dieselben 640 Pixel um den
Faktor 4/3 breiter zeigt, erscheint die Anzeige damit wieder in ihrer
ursprünglichen Form: 91 · 1,333 = 121 gegen 123 Pixel.

Rechnet man die Pixelpositionen in Spieleinheiten zurück
(4:3: Pixel = 1,0667 · x; 16:9: Pixel = 0,8 · x + 80), liegt die linke Kante
der Anzeige bei x = 21,6 beziehungsweise x = −77,5. Die neue linke Bildkante
liegt bei x = −100. Der Abstand zur Bildkante beträgt also **21,6 gegen 22,5
Einheiten** — derselbe Rand. Das HUD ist an der Bildkante verankert und
wandert mit ihr nach außen; es klebt nicht am alten 4:3-Rahmen.

## Stand der WP8-Kriterien

| Kriterium | Stand |
|---|---|
| mehr waagerechte Sicht, keine Streckung | **belegt**, exakt an der Projektion und im Bild |
| HUD unverzerrt und richtig verankert | **belegt** für die Münzanzeige, in Pixeln gemessen |
| nichts geht verloren | Zeichenbefehlzahlen je Projektion in beiden Bauten gleich |
| Filme | **nicht gelöst**: Projektion unverändert, also Streckung bei 16:9 |
| Culling | nicht systematisch geprüft (siehe unten) |

## Was nicht belegt ist

- **Culling.** Im gemessenen Frame sind die Zeichenbefehlzahlen gleich, und
  das zusätzlich Sichtbare wird gezeichnet — es fehlt also nichts am Rand.
  Das ist ein Frame einer Zwischensequenz. Ob das Spiel in offenen Szenen
  Objekte am neuen Rand wegschneidet, weil seine Sichtbarkeitsprüfung den
  alten Rahmen benutzt, ist damit nicht beantwortet. Dafür braucht es Szenen
  mit Objekten knapp außerhalb des 4:3-Rahmens.
- **21:9 und 32:9.** Nur 16/9 gemessen. Der Weg ist derselbe: Konstante und
  2D-Raum; dass die Rechnung auch für 2,37 trägt, ist offen (WP9).
- **Effekte.** Wasser, Spiegelungen, Hitzeflimmern und alles, was den
  Bildschirmrand als Bezug nimmt, wurde nicht betrachtet.
- **Weitere HUD-Elemente.** Gemessen ist die Münzanzeige. Dialogfelder,
  Pausenmenü und Anzeigen am rechten Rand stehen aus.
- **Der ganze Rest des Spiels.** Eine Szene, ein Frame.
