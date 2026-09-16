# Ultrawide: 21:9 und 32:9

Stand: 2026-09-15. WP9. Grundlage ist der 16:9-Befund aus
[03-WIDESCREEN.md](03-WIDESCREEN.md) und
[15-WIDESCREEN-ABNAHME.md](15-WIDESCREEN-ABNAHME.md).

## Zwei Irrtümer, durch Messung widerlegt

Zwei naheliegende Annahmen waren falsch. Sie stehen hier, weil die Messungen,
die sie widerlegen, zugleich die richtige Stelle gefunden haben — und weil
„naheliegend" in diesem Code offenbar kein guter Ratgeber ist.

**Erste Annahme:** Der Code schreibt an `0x80412408` bitgenau 16/9
(`0x3FE38E39`) über die 4/3 des Spiels (`0x3FAAAAAB`). Also müsse dort das
Seitenverhältnis stehen.

**Messung:** Vier DOLs gebacken (4:3, 16:9, 64:27, 32:9), mit jedem dieselbe
Eingabefolge bis zur Dateiauswahl gefahren, dort je 20 Bilder als FIFO
aufgezeichnet und die Projektion desselben Bildes verglichen:

| Fassung | Sichtverhältnis der Projektion | waagerechter Maßstab |
|---|---|---|
| 4:3 (unverändert) | 1,3457 | 2,041635 |
| 16:9 | 1,7778 | 1,545456 |
| 64:27 | **1,7778** | **1,545456** |
| 32:9 | **1,7778** | **1,545456** |

Bitgleich. Das Wort an `0x80412408` ändert an der Projektion **nichts**.

**Zweite Annahme:** In der größten der zwölf Einfügungen, bei `0x80363138`,
steht die Umrechnung als ganzzahliger Bruch:

```
80363160: 1C630003   mulli r3, r3, 3
80363164: 1CA50003   mulli r5, r5, 3
80363168: 7C631670   srawi r3, r3, 2
8036316C: 54A5F0BE   srwi  r5, r5, 2
```

Also mal **3/4** — und 3/4 ist genau (4/3) geteilt durch (16/9). Der Bruch
wurde auf 9/16 (64:27) und 3/8 (32:9) gesetzt; im gebackenen DOL steht danach
nachweislich `mulli r3, r3, 9`. **Die Projektion blieb wieder bei 1,7778.**
Auch diese Stelle ist es nicht; sie rechnet etwas anderes um.

## Wo das Seitenverhältnis wirklich steht

Bei `0x80416B74`. Der Code setzt dort 0,9134614 auf 1,2067341 — Verhältnis
**1,321056**. Und genau um diesen Faktor ändert sich das gemessene
Sichtverhältnis der Projektion, von 1,3457 auf 1,7778 (Verhältnis 1,321). Die
Konstante ist linear im Seitenverhältnis:

```
Konstante = Seitenverhältnis × 0,6787879
```

Die Gerade ist in beide Richtungen geprüft:

| Probe | Ergebnis |
|---|---|
| 16/9 × 0,6787879 | `0x3F9A7643` — **bitgenau der Wert, den der Code schreibt** |
| 0,9134614 ÷ 0,6787879 | 1,345724 — **das am unveränderten Spiel gemessene 1,3457** |

Zwei unabhängige Stützstellen, beide auf sechs Stellen getroffen.

## Wo das Seitenverhältnis steht

Der Widescreen-Code von gamemasterplc schreibt dreizehn Worte. Gegen die
unveränderte `main.dol` der Spielkopie gelesen, ergibt sich:

| Adresse | vorher | nachher | was es ist |
|---|---|---|---|
| **`0x80412408`** | `0x3FAAAAAB` = **1,333333** | `0x3FE38E39` = **1,777778** | **das Seitenverhältnis: 4/3 auf 16/9** |
| `0x80416758` | 600,0 | 800,0 | Sichtweite, Faktor 4/3 |
| `0x804123E8` | 600,0 | 700,0 | Sichtweite, Faktor 7/6 |
| `0x80416620` | 600,0 | 700,0 | Sichtweite, Faktor 7/6 |
| `0x80416B74` | 0,913461 | 1,206734 | Faktor 1,3210 |
| `0x80176AA4` u. a. (5×) | `0xC002B834`/`0xC002FA60` | `0xC002B83C` | Befehlsoperanden (`lfs`) |
| `0x8029610C`, `0x802960A0`, `0x8014E7D4` | Befehle | `li`-Befehle | ersetzte Anweisungen |

`0x3FAAAAAB` und `0x3FE38E39` sind bitgenau 4/3 und 16/9. **Genau dieses eine
Wort bestimmt das Seitenverhältnis.**

Die übrigen zwölf Schreibungen sind nicht einheitlich skaliert: 600 wird
einmal zu 800 (Faktor 4/3) und zweimal zu 700 (Faktor 7/6), und 0,913461 wird
zu 1,206734 (Faktor 1,3210, nicht 4/3). Aus dem Code geht nicht hervor, wie
sie vom Seitenverhältnis abhängen. **Sie bleiben deshalb unberührt**, und was
das für Culling und Sichtweiten bedeutet, ist unten unter den Grenzen
festgehalten.

## Das Werkzeug

`tools/widescreen bake --aspect` ändert den Bruch in der Einfügung und das
dazugehörige Datenwort:

```bash
python tools/widescreen --ini <GMSE01.ini> bake \
    --dol <spiel>/sys/main.dol --to <ziel>/sys/main.dol --aspect 64:27
```

Angenommen werden Verhältnisse (`16:9`, `64:27`, `32:9`) und Zahlen (`2.37`).
Geprüft wird vor der Änderung, dass beide Stellen genau so aussehen wie
erwartet — ein Code, der dort etwas anderes schreibt, ist ein anderer Code,
und Raten wäre das Falsche.

**Die schärfste Gegenprobe:** `--aspect 16:9` muss bitgenau das Wort erzeugen,
das im Code von gamemasterplc steht. Das tut es; ein Test prüft es ohne
Spielkopie, und das damit gebackene DOL ist bytegleich mit dem ohne die
Option.

**Zur Bezeichnung:** „21:9" ist ein Marketingname. Wörtlich genommen sind es
2,3333; die üblichen Ultrawide-Bildschirme haben 64:27 = 2,3704 (3440×1440
sogar 43:18 = 2,3889). Das Werkzeug rechnet, was dasteht, und verschweigt den
Unterschied nicht.

Vier DOLs wurden erzeugt und das geänderte Wort in jedem nachgelesen:

| Fassung | Wort an `0x80416B74` | ergibt Seitenverhältnis |
|---|---|---|
| unverändert (4:3) | `0x3F69D89C` = 0,913461 | 1,345724 |
| 16:9 | `0x3F9A7643` = 1,206734 | 1,777778 |
| 64:27 | `0x3FCDF304` = 1,608979 | 2,370370 |
| 32:9 | `0x401A7643` = 2,413468 | 3,555556 |

Das Wort an `0x80412408` bleibt dabei auf 16/9. Es zu ändern hatte in der
Messung keine Wirkung, und was es sonst tut, ist offen — wer es mitändern
will, braucht dafür erst einen Beleg.

## Abnahme an der Projektion

Dieselbe Eingabefolge bis zur Dateiauswahl, dort je 20 Bilder als FIFO
aufgezeichnet, Projektion desselben Bildes verglichen:

| Fassung | waagerechter Maßstab | senkrechter Maßstab | Sichtverhältnis | Ziel |
|---|---|---|---|---|
| 4:3 (unverändert) | 2,041635 | 2,747478 | 1,3457 | — |
| 16:9 | 1,545456 | 2,747478 | 1,7778 | 1,777778 |
| 64:27 | 1,159092 | 2,747478 | **2,3704** | 2,370370 |
| 32:9 | 0,772728 | 2,747478 | **3,5556** | 3,555556 |

Beide Ultrawide-Verhältnisse werden auf vier Stellen getroffen. Der senkrechte
Maßstab ist in allen vier Fassungen **bitgleich**: Es wird nicht gezoomt und
nicht gestreckt, sondern seitlich mehr Sicht freigegeben. Das ist dieselbe
Eigenschaft, die [15-WIDESCREEN-ABNAHME.md](15-WIDESCREEN-ABNAHME.md) für 16:9
belegt hat — jetzt auch für 21:9 und 32:9.

Die zweite Projektion derselben Szene (653 Zeichenbefehle, vermutlich eine
zweite Kamera) folgt demselben Verhältnis: 2,050304 senkrecht in allen
Fassungen, waagerecht 1,523569 / 1,153296 / 0,864972 / 0,576648.

**Nicht auswertbar ist die Zahl der Zeichenbefehle.** Sie steigt von 2.276 auf
2.444, aber sie stieg in einer früheren Messreihe genauso, in der sich die
Projektion gar nicht änderte. Ob bei 32:9 wirklich mehr Geometrie gezeichnet
wird — also ob das Culling mitgeht — ist damit **nicht** gezeigt.

## Die 2D-Ebene folgt nicht — und warum sie unberührt bleibt

Dieselben Aufzeichnungen zeigen die zweite Hälfte des Bildes, und dort ist
Ultrawide **nicht** fertig. Die orthografische Projektion der 32 2D-Draws:

| Fassung | Maßstab | Versatz | daraus der Bereich |
|---|---|---|---|
| 4:3 | 0,003333 = 2/600 | −1,000000 | 0 … 600 |
| 16:9 | 0,002500 = 2/800 | −0,750000 | −100 … 700 |
| 64:27, nur Kamera geändert | 0,002500 | −0,750000 | −100 … 700 — **stehengeblieben** |

Bei 16:9 ist der Bereich symmetrisch um den Spielraum 0 … 600: je 100 Einheiten
links und rechts. Bei Ultrawide bleibt er auf den 16:9-Werten.

Die rechte Kante ist gefunden: die beiden Schreibungen `0x804123E8` und
`0x80416620` gehen von 600 auf 700, und 700 ist genau die rechte Kante. Als
Gerade: Kante = 300 + 225 × Seitenverhältnis, was 600 bei 4:3 und 700 bei 16:9
trifft. Mit `--hud-2d` gebacken und gemessen:

| Fassung | Maßstab | Versatz | Bereich |
|---|---|---|---|
| 16:9 | 0,002500 | −0,750000 | −100 … 700 (unverändert, richtig) |
| 64:27 | **0,002143** | **−0,785714** | **−100 … 833,33** |

Die rechte Kante wandert also mit. **Die linke nicht.** Damit wäre das Bild
bei 64:27 unsymmetrisch — 100 Einheiten links gegen 233 rechts —, und das ist
schlechter als der 16:9-Zustand, nicht besser.

**Deshalb ist die 2D-Skalierung nicht Vorgabe.** `--aspect` ändert nur die
Kamera; `--hud-2d` schaltet die unfertige 2D-Skalierung zum Weitersuchen dazu.
Die offene Frage ist eng: Woher kommt die linke Kante −100? Sie ist keine der
dreizehn direkten Schreibungen; in Frage kommen die eingefügten
Ganzzahlkonstanten (−87, 593, 600, 515, 497, −5000) und die drei ersetzten
Befehle (`li` mit 746, −106, 572).

## Die Zusage

Damit der Befund nicht eine einmalige Messung bleibt, ist er eine Zusage des
Abnahmelaufs geworden: `tools/acceptance/widescreen.json` fährt die
Eingabefolge bis zur 3D-Szene, zeichnet dort 20 Bilder als FIFO auf und sagt
das Sichtverhältnis **1,777778 ± 0,0005** zu. Gemessen wird die perspektivische
Projektion mit den meisten Zeichenbefehlen — die Hauptkamera.

Gegenprobe, damit die Zusage nicht wertlos ist:

| Spielkopie | Ergebnis | gemessen |
|---|---|---|
| mit 16:9 gebacken | bestanden | 1,777778 |
| mit 64:27 gebacken | **nicht bestanden** | 2,370371 |

Das Szenario läuft mit `--jit`: Das vorhandene Modul ist für das ungebackene
DOL gebaut, ein gebackenes bräuchte ein eigenes (rund 65 Minuten). Gegenstand
ist die Projektion, nicht der Kern.

## Grenzen

- Geändert wird eine einzige Konstante. Sichtweiten, Culling-Grenzen und die
  zwölf Einfügungen bleiben auf den 16:9-Werten. Bei 32:9 ist zu erwarten, dass
  am linken und rechten Rand Dinge fehlen, die dort stehen müssten. Die
  Zeichenbefehlzahl taugt dafür nicht als Beleg (siehe oben); das braucht einen
  Bildvergleich am echten Fenster.
- Belegt ist die **Projektion der Kamera**, nicht das **Bild**. Dass die Kamera
  weiter sieht, heißt noch nicht, dass HUD, Effekte und Filme dabei richtig
  sitzen — die 2D-Ebene folgt nachweislich nicht (siehe oben).
- HUD-Verankerung ist für 16:9 in [15](15-WIDESCREEN-ABNAHME.md) am Bild
  abgenommen; für 21:9 und 32:9 steht das aus.
- Filme bleiben unberührt und werden gestreckt ([15](15-WIDESCREEN-ABNAHME.md),
  WP11).
