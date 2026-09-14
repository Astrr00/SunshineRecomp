# Adressbasis fuer GMSE01

Die US-Disc enthaelt **keine** Symbol-Map. Nachgeprueft am 2026-09-09 an einer
echten Kopie: 174 Dateien, nur `opening.bnr`, `data/` und `AudioRes/`, keine
Symboldatei (siehe [../../docs/01-MACHBARKEIT.md](../../docs/01-MACHBARKEIT.md),
Abschnitt 2.1). Die Symbol-Map gehoert zur japanischen Fassung; deshalb zielt
auch die Decompilation auf `GMSJ01`.

Ohne benannte Adressen muesste jede Hook-Stelle fuer die Anforderungen 1, 3
und 4 einzeln gesucht werden. Diese Liste schliesst die Luecke.

## Herkunft

| | |
|---|---|
| Datei | `gmse01-bettersunshineengine.map` |
| Projekt | [DotKuribo/BetterSunshineEngine](https://github.com/DotKuribo/BetterSunshineEngine) |
| Pfad dort | `maps/us.map` |
| Commit | `fd6273014545ac0174fa54fada02edd9212f63d8` |
| SHA-256 | `62eec2cb40ac19ccf2cddabffd37cca2e34761684c6bca250c7dc3f7d83a2c40` |
| Lizenz | GPL-3.0 |
| Uebernommen am | 2026-09-14, unveraendert |

Die Datei liegt hier bei, statt beim Bootstrap geladen zu werden: Sie ist
Eingabe fuer den Recompiler, keine Bauabhaengigkeit, und eine feste Kopie haelt
den Bau reproduzierbar. Die Pruefsumme wird von
[../../tests/test_symbols.py](../../tests/test_symbols.py) mitgeprueft; eine
Aktualisierung muss diese Datei mitziehen.

Lizenzlage: BetterSunshineEngine steht unter GPL-3.0, dieses Projekt ebenfalls
(siehe [../../LICENSE](../../LICENSE)). Die Uebernahme ist damit zulaessig;
diese Seite ist die Quellenangabe.

**Keine Spieldaten.** Die Liste enthaelt Namen und Adressen, keinen
Programmcode und keine Spielinhalte. Sie ersetzt kein Spielabbild und macht
keines entbehrlich.

## Abgleich mit den eigenen Messungen

Dass eine fremde Liste zur eigenen Spielkopie passt, ist ohne Originalquelle
nicht beweisbar. Pruefbar ist aber, ob sie zu den Adressen passt, die in
diesem Projekt unabhaengig am laufenden Spiel gemessen wurden. Sechs solcher
Adressen liegen vor, alle sechs passen:

| Adresse | Name in der Liste | Eigene Messung |
|---|---|---|
| `0x8000522C` | `__start` | Eintrittspunkt laut `moderngekko-port inspect` (Dok. 02) |
| `0x8040E108` | `gpMarioAddress` | Mario-Objektzeiger (Dok. 06) |
| `0x8040E10C` | `gpMarioPos` | Mario-Positionszeiger (Dok. 06) |
| `0x803DD660` | `__vt__6TMario` | Mario-Vtable (Dok. 06) |
| `0x803BB71C` | `__vt__17TBiancoGateKeeper` | Boss-Vtable am Flugplatz (Dok. 06) |
| `0x80404454` | `mPadStatus__10JUTGamePad` | Pad-Status (Dok. 04) |

Die Namen sind nicht nur vorhanden, sondern benennen jeweils genau das, was
an der Stelle gemessen wurde. Das stuetzt beides: die Liste und die eigene
Zuordnung von damals.

Der Gegenbeleg fehlt bewusst nicht: `0x80412408`, das vom Widescreen-Code
geaenderte Seitenverhaeltnis (Dok. 03), traegt **keinen** Namen. Das naechste
Symbol davor liegt 4.048 Bytes entfernt. Namenlose Konstanten in Datensektionen
sind der Normalfall; die Liste deckt nicht alles ab.

## Inhalt

15.108 Zeilen, davon 7 leer. Nach den Regeln des Recompilers bleiben
**15.083 Symbole**:

| Verworfen | Anzahl | Grund |
|---|---|---|
| `wgPipe = 0xCC008000` | 1 | ausserhalb MEM1, Hardware-Register |
| `init$3268` und fuenf weitere | 6 | Adresse nicht durch 4 teilbar; `symbol_map_load` verwirft solche Zeilen |
| exakte Wiederholungen | 11 | dieselbe Adresse mit demselben Namen |

Adressbereich `0x80000000` bis `0x8041731C`. Funktionen und Daten, Namen als
CodeWarrior-Mangling (`__vt__6TMario`, `set__Q29JGeometry8TVec3<f>Fffff`).

`jp.map` desselben Projekts ist leer (0 Bytes) und daher nicht uebernommen.

## Bezeichner-Kollisionen

DolRecomp macht aus jedem Namen einen C-Bezeichner
(`DOLRECOMP_SYMBOL_<Name>`). Dabei werden Sonderzeichen zu `_`, mehrfache
Unterstriche zusammengezogen und bei 255 Zeichen abgeschnitten. **21
Bezeichner** stehen danach fuer mehr als eine Adresse:

* 17 sind eingebettete Vorlagenfunktionen, die der Compiler je
  Uebersetzungseinheit erneut ausgegeben hat (`MsWrap<f>__Ffff` steht an 29
  Adressen). Das ist keine Unstimmigkeit der Liste.
* 4 entstehen erst beim Zusammenziehen der Unterstriche, etwa
  `writeBlock__12TCardManagerFUl` und `writeBlock___12TCardManagerFUl`.

Der Recompiler haengt in diesen Faellen die Adresse an den Bezeichner. Fuer
Mods heisst das: Diese 21 Namen sind nicht allein benutzbar, die Adresse
gehoert dazu. Alle uebrigen sind eindeutig.

## Benutzung

Ohne Spieldaten, taeglich brauchbar:

```bash
python tools/symbols check
python tools/symbols convert --to build/GMSE01.map
```

`convert` schreibt DolRecomps zweispaltige Form `ADRESSE NAME`. Die Groesse
bleibt absichtlich weg: `resolved_size` in `src/backend/symbols.c` leitet sie
aus der naechsten Symboladresse derselben Sektion ab, und das ist genauer als
ein geratener Wert. Danach:

```bash
dolrecomp --map build/GMSE01.map --gamecube <main.dol> <ausgabe>
```

Der Recompiler erzeugt dann `generated_symbols.h` mit
`DOLRECOMP_SYMBOL_<Name>` und `DOLRECOMP_SYMBOL_SIZE_<Name>`. Mods binden an
Namen statt an Zahlen.

## Pruefung gegen die eigene Spielkopie

Braucht die `main.dol` des eigenen Imports und laeuft deshalb nur auf dem
Rechner mit der Spielkopie:

```bash
python tools/symbols verify --dol build/game/sys/main.dol --report build/symbols-verify.json
```

Geprueft wird:

1. **`__start` gegen den Eintrittspunkt im DOL-Kopf.** Weichen sie ab, gehoert
   die Liste zu einer anderen Fassung. Das ist der harte Teil der Pruefung.
2. **Verteilung** der Symbole auf Text-, Datensektionen und den Rest.
3. **Freie Textsektions-Plaetze** im DOL-Kopf. Diese Zahl entscheidet ueber den
   Weg in WP8 (Widescreen im Rekompilat, siehe
   [../../docs/PLAN.md](../../docs/PLAN.md)): Fuer eingefuegten Code wird ein
   Platz gebraucht.
4. **Funktionsgrenzen, statistisch.** Gezaehlt wird, wie oft an einer
   Symboladresse ein ueblicher Prolog steht (`stwu r1, -N(r1)` oder `mflr r0`)
   und wie oft davor ein Funktionsende steht (`blr`, `bctr`, unbedingter
   Sprung, `nop` oder Fuellbytes). Dagegen laeuft eine Kontrollgruppe aus
   gleich vielen zufaelligen, ausgerichteten Adressen derselben Sektionen.

Zu Punkt 4 ausdruecklich: Liegen die Symbolwerte deutlich ueber der
Kontrolle, treffen die Adressen echte Funktionsgrenzen. Das ist ein **Indiz,
kein Beweis** der Uebereinstimmung mit dieser Spielkopie, und wird auch so
ausgegeben. Der Zufallsstartwert ist fest, der Vergleich also wiederholbar.

Die Werte dieser Pruefung sind noch nicht erhoben; dafuer fehlt in der
Sitzung, in der dieses Werkzeug entstanden ist, die Spielkopie.
