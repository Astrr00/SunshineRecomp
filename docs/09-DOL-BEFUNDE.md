# Befunde an der echten main.dol

Stand: 2026-09-14. Erstmals wurden die in dieser Sitzung gebauten Werkzeuge
gegen die **echte** Spielkopie gefahren, nicht nur gegen synthetische Abbilder.
Der Auftraggeber hat dafuer sein eigenes RVZ bereitgestellt.

**Keine Spieldaten im Repository.** Abbild, `main.dol` und alle daraus
erzeugten Dateien blieben in der Arbeitssitzung. Hier stehen ausschliesslich
Messwerte.

## Herkunft und Nachweis der Entpackung

| | |
|---|---|
| Vorlage | RVZ des Auftraggebers, 1.050.830.424 Bytes |
| Groesse laut RVZ-Kopf | ISO 1.459.978.240 Bytes, Disc-Kennung `GMSE01`, Name "Super Mario Sunshine" |
| Verfahren | ZSTD, Stufe 19, Blockgroesse 131.072, ein Rohdatenbereich mit 11.139 Gruppen |
| Entpackt mit | eigenem Leser nach RecompCore `c6a600eb` (`WIABlob`, `WIACompression`, `LaggedFibonacciGenerator`) |

Der Leser liegt als `tools/import/rvz.py` vor, ist aber auf Wunsch des
Auftraggebers **nicht Bestandteil des Repositorys** (Eintrag in `.gitignore`).
Verfolgter Code haengt nicht an ihm: Fehlt er, lehnt `tools/import`
komprimierte Container wie bisher mit Hinweis ab, und die Wandlung laeuft ueber
DolphinTool wie in [HANDOFF.md](HANDOFF.md), Abschnitt 5.

Die Groesse des RVZ deckt sich mit der Angabe in
[02-STATUS.md](02-STATUS.md); es ist dieselbe Datei wie bei den frueheren
Sitzungen.

**Beleg, dass die Entpackung stimmt:** Die gewonnene `main.dol` ist
4.128.928 Bytes gross und hat SHA-256
`13934c863d649b1ddca1ca4d7748f49d28a571685cbee5fb1542545c32869955`. Genau
dieser Wert steht seit dem 2026-09-10 in
[../scripts/build.ps1](../scripts/build.ps1) als
`MODERNGEKKO_REQUIRED_DOL_SHA256`, dort an einer Extraktion durch Dolphin
gewonnen. Zwei unabhaengige Wege, dasselbe Ergebnis. Der Eintrittspunkt
`0x8000522C` stimmt ebenfalls mit `moderngekko-port inspect` ueberein.

## Aufbau der main.dol

10 Sektionen, davon 2 ausfuehrbar. **Fuenf Textsektions-Plaetze im Kopf sind
frei** (2 bis 6).

| Bereich | Groesse | Sektion |
|---|---|---|
| `0x80003100-0x80005540` | 9.280 | text0 |
| `0x80005540-0x800055A0` | 96 | data7 |
| `0x800055A0-0x80005600` | 96 | data8 |
| `0x80005600-0x803730C0` | 3.594.944 | text1 |
| `0x803730C0-0x80373480` | 960 | data9 |
| `0x80373480-0x803734A0` | 32 | data10 |
| `0x803734A0-0x803AB660` | 229.824 | data11 |
| `0x803AB660-0x803E9700` | 254.112 | data12 |
| `0x803E9700-0x8040EB98` | 152.728 | bss |
| `0x8040C1C0-0x8040CF00` | 3.392 | data13 |
| `0x8040EBA0-0x80417800` | 35.936 | data14 |

**data13 liegt innerhalb des BSS-Bereichs.** Das ist beim GameCube normal --
der Kopf nennt eine Spanne von `.bss` bis `.sbss`, dazwischenliegende
Datensektionen eingeschlossen. Es hat aber einen eigenen Fehler aufgedeckt:
`gaps()` verglich nur aufeinanderfolgende Eintraege und meldete deshalb eine
Luecke von 7.328 Bytes zwischen `data13` und `data14`, die in Wirklichkeit BSS
ist. Wer dort einen Codebereich angelegt haette, haette ihn mitten in BSS
gelegt. Die Funktion verschmilzt ueberlappende Bereiche jetzt zuerst; die
einzige echte Luecke im geladenen Abbild ist **8 Bytes** gross
(`0x8040EB98-0x8040EBA0`). Ein Test haelt das fest.

## Anforderung: Adressbasis (WP7)

`python tools/symbols verify --dol <main.dol>`

| Gegenstand | Ergebnis |
|---|---|
| `__start` gegen Eintrittspunkt im Kopf | stimmt ueberein, `0x8000522C` |
| Symbole in Textsektionen | 12.335 |
| Symbole in Datensektionen | 2.210 |
| ausserhalb (BSS oder unbelegt) | 538 |

Stichprobe gegen eine Zufallskontrolle aus gleich vielen ausgerichteten
Adressen derselben Sektionen:

| Merkmal | Symbole | Zufall |
|---|---|---|
| Funktionsprolog an der Adresse | 77,2 % | 2,2 % |
| Funktionsende unmittelbar davor | **99,9 %** | 10,9 % |

Fast jede Symboladresse folgt auf ein `blr`, einen unbedingten Sprung oder
Fuellbytes, der Zufall nur in jedem zehnten Fall. Die Liste trifft also echte
Funktionsgrenzen dieser Spielkopie. Ein Beweis der Herkunft ist das nicht, aber
zusammen mit den sechs bereits in [04](04-GRAFIKDIAGNOSE.md) und
[06](06-ERSTER-SHINE.md) unabhaengig gemessenen Adressen ist die Grundlage
belastbar.

Nebenbefund: `gpMarioAddress` (`0x8040E108`) und `gpMarioPos` (`0x8040E10C`)
liegen in BSS. Das passt zu ihrer Rolle als zur Laufzeit gesetzte Zeiger und
bestaetigt die Messung aus Dokument 06 ein weiteres Mal.

## Anforderung 3: Widescreen im Rekompilat (WP8)

### Die offene Frage ist beantwortet

Der Plan hielt fest, dass drei der 13 Schreibziele moeglicherweise in BSS
liegen und sich dann nicht einbacken liessen. **Sie tun es nicht.** Alle 13
liegen in der Datei:

| Ziel | Sektion |
|---|---|
| `0x80416758`, `0x80416620`, `0x80412408`, `0x80416B74`, `0x804123E8` | data14 |
| `0x80176AA4`, `0x80176C40`, `0x80176FF4`, `0x80177198`, `0x8029B974`, `0x8029610C`, `0x802960A0`, `0x8014E7D4` | text1 |

Damit braucht Anforderung 3 keinen Laufzeit-Mod fuer die Schreibungen. Der
entsprechende Vorbehalt in [PLAN.md](PLAN.md) entfaellt.

### Der eingefuegte Code ist in sich schluessig

Jede der zwoelf C2-Einfuegungen verdraengt eine echte Anweisung an ihrer
Zieladresse. Geprueft wurde, ob der eingefuegte Rumpf sie bewahrt:

| Befund | Anzahl |
|---|---|
| verdraengte Anweisung im Rumpf enthalten | **12 von 12** |
| davon als letztes Rumpfwort | 10 |
| davon an anderer Stelle (`0x80156004` Position 6 von 7, `0x80363138` Position 1 von 17) | 2 |

Eine erste, zu eng gefasste Pruefung hatte nur das letzte Rumpfwort
betrachtet und zwei Einfuegungen faelschlich als Abweichung gemeldet. Der
Fehler lag in der Pruefung, nicht in den Daten.

### Ergebnis des Einbackens

`python tools/widescreen --ini <GMSE01.ini> bake --dol <main.dol> --to <ziel>`

| Gegenstand | Ergebnis |
|---|---|
| Schreibungen angewandt | 13 von 13 |
| Einfuegungen | 12, Codebereich bei `0x80417800`, 70 Worte |
| Nachgeprueft | 95 Worte neu eingelesen und verglichen |
| Ergebnis SHA-256 | `3a655b2e4b330eafe4917ebe6a01a3ee280bd5205c526e8d3bb22e1bb9da01af` |

### Das Rekompilat

Beide DOLs wurden mit DolRecomp `40637c46` (unter Linux gebaut, C-Backend,
ctest 19/19) und der erzeugten Symbolliste uebersetzt:

| | Original | mit Widescreen |
|---|---|---|
| geladene ausfuehrbare Symbole | 12.335 | 12.335 |
| text0 | 2.320 Anweisungen, 0 unbekannt | unveraendert |
| text1 | 898.736 Anweisungen, 0 unbekannt | unveraendert |
| text2 (Codebereich) | — | **70 Anweisungen, 70 bekannt, 0 unbekannt** |
| erzeugte Chunks | 221 | 222 |

Sieben Chunks unterscheiden sich, dazu kommt der neue
`chunk_0221_text2_80417800.c`. Unter den sieben sind
**`chunk_0178_text1_802C9600.c`** und **`chunk_0216_text1_80361600.c`**.

Das sind genau die beiden Bereiche, fuer die das Log des Gecko-Laufs in
[03-WIDESCREEN.md](03-WIDESCREEN.md) einen SMC-Rueckfall meldet
(`802C9600–802CD600` und `80361600–80365600`). Sie werden jetzt mit den
Widescreen-Aenderungen **nativ rekompiliert**, statt zur Laufzeit vom
Codehandler veraendert und anschliessend interpretiert zu werden. Das ist der
Zweck von WP8, und er ist an der echten Spielkopie belegt.

## Was damit ausdruecklich nicht belegt ist

1. **Kein Lauf.** Nichts davon wurde gespielt. Ob das Bild stimmt, ob der
   SMC-Rueckfall im Log tatsaechlich verschwindet und ob HUD, Effekte und
   Culling taugen, muss am laufenden Spiel geprueft werden.
2. **Die Adresse des Codebereichs ist nicht abgesichert.** Siehe den naechsten
   Abschnitt; das ist der letzte offene Punkt von WP8.
3. **Kein Modulbau.** `moderngekko-port` wurde hier nicht gefahren; der Schritt
   vom erzeugten C zum ladbaren Modul steht aus.
4. **Nur diese Revision.** Alle Zahlen gelten fuer `GMSE01` Rev 0.

## Offener Punkt: Wo beginnt der Spielheap?

Der Codebereich liegt bei `0x80417800`, unmittelbar hinter dem letzten
geladenen Byte. Nimmt das Spiel seinen Speicher ab dieser Adresse, ueberschreibt
es den Bereich. Die Laufzeit merkt das -- ihr SMC-Waechter hasht jeden Chunk
beim ersten nativen Sprung hinein und stuft ihn bei Abweichung zurueck --, und
der Interpreter fuehrt dann aus, was gerade dort steht. Das waere kein stiller
Fehler, sondern ein Absturz.

### Was am DOL geklaert ist

Die Symbolliste nennt die beiden Zeiger, in denen die Arena-Grenzen stehen:

| Symbol | Adresse |
|---|---|
| `__OSArenaLo` | `0x8040CE48` |
| `__OSArenaHi` | `0x8040E798` |

Beide liegen im BSS-Bereich; ihre **Werte** setzt das Spiel beim Start.
`OSSetArenaLo` steht bei `0x803433AC`, `OSInit` bei `0x80341D94`.

Gesucht und **nicht gefunden**: Die Adresse `0x80417800` kommt im gesamten DOL
weder als Datenwort noch als `lis`/`ori`- oder `lis`/`addi`-Paar vor. Die
Untergrenze ist also keine eingebackene Konstante gleich dem Abbildende; sie
wird zur Laufzeit berechnet. Aus der Datei allein ist die Frage damit nicht zu
beantworten.

Ebenfalls geprueft und verworfen: ein Codebereich in ungenutztem Platz
innerhalb des Abbilds. Zusammenhaengende Nullbereiche ab 280 Bytes gibt es nur
in `text0` (drei, groesster 1.228 Bytes) und `data12` (sieben, groesster 780
Bytes). Wozu diese Bereiche dienen, ist nicht bekannt; sie ohne Kenntnis zu
belegen waere geraten, nicht gemessen.

### Wie es zu beantworten ist

Am laufenden Spiel, mit einem Befehl:

```bash
python tools/diagnostics/sunshine_state.py     --automation <automations-verzeichnis> --cave-address 0x80417800
```

Der Zustandsleser gibt jetzt zusaetzlich `arena.lo`, `arena.hi` und
`arena.cave_below_arena` aus. Ist `cave_below_arena` wahr, liegt der Bereich
unterhalb des Spielheaps und bleibt unberuehrt.

Faellt die Antwort ungünstig aus, stehen drei Wege offen:

1. **Arena anheben.** Die berechnete Untergrenze um die Groesse des Bereichs
   nach oben schieben. Kostet 280 Bytes Heap und ist der uebliche Weg.
2. **Bereich verschieben.** Etwa unter `__OSArenaHi`, wenn dort Luft ist.
3. **Auf Einfuegungen verzichten** und nur die 13 direkten Schreibungen
   einbacken. Die brauchen keinen Codebereich. Der Rest bliebe dann beim
   Gecko-Weg -- also ein Teilerfolg statt des vollen.

Vor dieser Messung sollte kein gebackenes DOL in einen echten Modulbau gehen.
