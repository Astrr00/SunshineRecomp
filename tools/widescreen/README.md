# Widescreen in das Rekompilat statt in die Laufzeit

## Warum

Der spielseitige 16:9-Code fuer GMSE01 laeuft heute ueber Dolphins Codehandler.
Das funktioniert -- in [../../docs/03-WIDESCREEN.md](../../docs/03-WIDESCREEN.md)
sind alle 25 Patchstellen im RAM nachgewiesen -- hat aber einen Preis: Die
geaenderten Codebereiche `802C9600-802CD600` und `80361600-80365600` gelten der
Laufzeit als selbstmodifizierend und laufen im **Interpreter** statt nativ.

In einem nativen Port ist das die falsche Stelle. Steht die Aenderung schon im
DOL, bevor DolRecomp laeuft, rekompiliert der Recompiler sie mit, und der
SMC-Rueckfall entfaellt. Dieses Werkzeug bringt sie dorthin.

Siehe [../../docs/PLAN.md](../../docs/PLAN.md), Abschnitte 2.3 und WP8.

## Was der Code enthaelt

Gelesen aus `ref/ModernGekko/vendor/dolphin/Data/Sys/GameSettings/GMSE01.ini`,
Abschnitt `[Gecko]`, Code `$Widescreen [gamemasterplc]`:

| Art | Anzahl | Bedeutung |
|---|---|---|
| `04XXXXXX YYYYYYYY` | 13 | schreibt ein Wort nach `0x80000000 + 0xXXXXXX` |
| `C2XXXXXX NNNNNNNN` | 12 | fuegt Code bei `0x80000000 + 0xXXXXXX` ein |

Die Zahlen stimmen mit der Zaehlung in Dokument 03 ueberein und werden von
[../../tests/test_widescreen.py](../../tests/test_widescreen.py) gegen die
echte INI geprueft, sobald der Bootstrap sie geholt hat.

Zum Verhalten der Einfuegung: Der Codehandler ersetzt die Anweisung an der
Zieladresse durch einen Sprung in den eingefuegten Code und **ueberschreibt
dessen letztes Wort** mit dem Ruecksprung nach Ziel+4. Das ist keine Annahme --
Dokument 03 haelt fest, dass der angesprungene Nutzcode bytegenau mit der INI
uebereinstimmt, "ohne das vom Handler ersetzte letzte Rücksprungwort". Bei allen
zwoelf Einfuegungen ist dieses letzte Wort `0x00000000`; das Werkzeug prueft es
und warnt, falls nicht.

## Benutzung

Ohne Spieldaten:

```bash
python tools/widescreen --ini <GMSE01.ini> inspect --list
python tools/widescreen --ini <GMSE01.ini> inspect
```

Mit der eigenen Spielkopie, ohne etwas zu schreiben:

```bash
python tools/widescreen --ini <GMSE01.ini> plan --dol build/game/sys/main.dol
```

`plan` zeigt, in welcher Sektion jedes Schreibziel landet, die Speicherkarte des
DOL samt Luecken, die freien Textsektions-Plaetze und einen Vorschlag fuer den
Codebereich.

Erzeugen:

```bash
python tools/widescreen --ini <GMSE01.ini> bake \
    --dol build/game/sys/main.dol --to build/patched-main.dol \
    --report build/widescreen-bake.json
```

Die Spielkopie bleibt unveraendert; `bake` schreibt eine neue Datei. Mit
`--cave-address` laesst sich die Adresse des Codebereichs vorgeben, mit
`--onframe` zusaetzlich die 13 Schreibungen in der `[OnFrame]`-Form ablegen, die
`moderngekko-port` von sich aus versteht.

## Am echten Recompiler gegengeprueft

Der echte `dolrecomp` (Commit `40637c46`, unter Linux mit dem C-Backend gebaut,
eigene Testsuite 19 von 19) wurde auf ein gebackenes DOL angesetzt. Quelle war
ein synthetisches DOL mit Sunshine-aehnlicher Sektionsaufteilung und der
**echte** Widescreen-Code aus `GMSE01.ini`:

```
dolrecomp --gamecube --map <symbole.map> <gebacken.dol> <ausgabe>
  loaded 12574 executable symbols
  decoding text[0]: 950272 instructions at 0x80003100
    950272 decoded, 950272 known, 0 unknown
  decoding text[1]: 70 instructions at 0x804A3100
    70 decoded, 70 known, 0 unknown
    chunks (233 files)
```

Daran haengt die eigentliche Aussage von WP8:

| Gegenstand | Befund |
|---|---|
| DOL nach dem Backen lesbar | ja, drei statt zwei Sektionen |
| Codebereich als Textsektion erkannt | ja, Index 1, `0x804A3100`, 280 Bytes, ausfuehrbar |
| Eingefuegte Anweisungen gueltig | **70 von 70 dekodiert, 0 unbekannt** |
| Im Rekompilat vorhanden | ja, `chunk_0232_text1_804A3100.c` fuer den Bereich und `chunk_0082_text0_8014B100.c` fuer die Spruenge hinein |
| Nachgepruefte Worte beim Backen | 95 (13 Schreibungen, 12 Spruenge, 70 Worte im Bereich) |

Der Codebereich wird also **mitrekompiliert**, statt zur Laufzeit vom
Codehandler erzeugt zu werden. Genau das ist der Unterschied zwischen
interpretiertem und nativem Widescreen.

Das synthetische DOL ist kein Ersatz fuer die eigene Spielkopie: Sektionsgrenzen
und die Frage BSS oder Daten entscheidet erst das echte Hauptprogramm.

## Zwei Stellen, die im Voraus nicht entscheidbar sind

**Schreibziele in BSS.** Drei der 13 Schreibungen zielen auf `0x80416620`,
`0x80416758` und `0x80416B74`. Ob diese Adressen in einer Datensektion liegen
oder in BSS, haengt vom echten DOL ab und ist hier nicht geprueft. BSS steht
nicht in der Datei: Was dort liegt, laesst sich nicht einbacken, sondern nur zur
Laufzeit setzen. `plan` und `bake` ordnen jede Adresse ein und lehnen ab, statt
stillschweigend etwas auszulassen. Fuer die abgelehnten Werte ist der Mod aus
WP9 der Weg.

Ein Anhaltspunkt: `0x80412408` trug vor dem Patch `3FAAAAAB`, also 1,3333
(Dokument 03). Ein von Null verschiedener Anfangswert spricht fuer eine
Datensektion. Fuer die drei anderen liegt nichts Vergleichbares vor.

**Adresse des Codebereichs.** Der DOL-Kopf kennt die geladenen Sektionen und
BSS, aber nicht den Heap des Spiels. Das Werkzeug prueft gegen alles Bekannte
und schlaegt die erste ausgerichtete Adresse dahinter vor. Ob sie im Lauf frei
bleibt, entscheidet das Spiel, nicht der Kopf. Deshalb ist der Vorschlag ein
Vorschlag und `--cave-address` vorhanden.

## Was gepruefte Datei heisst und was nicht

`bake` liest das Ergebnis vollstaendig neu ein und vergleicht jedes geaenderte
Wort: jede Schreibung, jeden Sprung an einer Einfuegestelle und jedes Wort des
Codebereichs einschliesslich des Ruecksprungs. Ist etwas davon nicht so, wie es
sein soll, wird **keine Datei geschrieben**.

Das prueft die Datei. Es prueft nicht das Spiel. Die Abnahme von WP8 verlangt
weiterhin:

1. den RAM-Vergleich gegen die Gecko-Fassung nach dem Verfahren aus
   `patch-verification.json` (Dokument 03), bei ausgeschaltetem Gecko-Code,
2. den Nachweis, dass der SMC-Rueckfall der beiden Bereiche aus dem Log
   verschwindet,
3. die Bildabnahme ueber HUD, Menues, Effekte und Culling in mehreren Leveln.

Solange das nicht vorliegt, ist Anforderung 3 nicht abgenommen.
