# Ultrawide: 21:9 und 32:9

Stand: 2026-09-15. WP9. Grundlage ist der 16:9-Befund aus
[03-WIDESCREEN.md](03-WIDESCREEN.md) und
[15-WIDESCREEN-ABNAHME.md](15-WIDESCREEN-ABNAHME.md).

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

`tools/widescreen bake --aspect` ändert genau dieses Wort:

```bash
python tools/widescreen --ini <GMSE01.ini> bake \
    --dol <spiel>/sys/main.dol --to <ziel>/sys/main.dol --aspect 64:27
```

Angenommen werden Verhältnisse (`16:9`, `64:27`, `32:9`) und Zahlen (`2.37`).
Geprüft wird vor der Änderung, dass an `0x80412408` wirklich 16/9 steht — ein
Code, der dort etwas anderes schreibt, ist ein anderer Code, und Raten wäre
das Falsche.

**Zur Bezeichnung:** „21:9" ist ein Marketingname. Wörtlich genommen sind es
2,3333; die üblichen Ultrawide-Bildschirme haben 64:27 = 2,3704 (3440×1440
sogar 43:18 = 2,3889). Das Werkzeug rechnet, was dasteht, und verschweigt den
Unterschied nicht.

Vier DOLs wurden erzeugt und das geänderte Wort in jedem nachgelesen:

| Fassung | Wort an `0x80412408` | Wert |
|---|---|---|
| unverändert (4:3) | `0x3FAAAAAB` | 1,333333 |
| 16:9 | `0x3FE38E39` | 1,777778 |
| 64:27 | `0x4017B426` | 2,370370 |
| 32:9 | `0x40638E39` | 3,555556 |

Die 16:9-Fassung ist die Gegenprobe: Wer `--aspect 16:9` verlangt, muss genau
das Wort bekommen, das der Code ohnehin schreibt. Das tut sie, bitgenau — und
ein Test prüft es ohne Spielkopie.

## Abnahme an der Projektion

*(Messung läuft; die Zahlen folgen, sobald die vier Läufe abgeschlossen sind.)*

## Grenzen

- Geändert wird eine einzige Konstante. Sichtweiten und Culling-Grenzen
  bleiben auf den 16:9-Werten. Bei 32:9 ist zu erwarten, dass am linken und
  rechten Rand Dinge fehlen, die dort stehen müssten — das ist zu messen, nicht
  zu vermuten.
- HUD-Verankerung ist für 16:9 in [15](15-WIDESCREEN-ABNAHME.md) am Bild
  abgenommen; für 21:9 und 32:9 steht das aus.
- Filme bleiben unberührt und werden gestreckt ([15](15-WIDESCREEN-ABNAHME.md),
  WP11).
