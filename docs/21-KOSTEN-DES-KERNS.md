# Warum der native Kern langsam ist

Stand: 2026-09-16. Der Auftraggeber hat das Ziel präzisiert: „dass das Spiel
nativ mit so viel Fps läuft". [16-RUECKWEG.md](16-RUECKWEG.md) hat den nativen
Kern hergestellt und dabei gemessen, dass er **langsamer** ist als der
Ersatz-JIT. Dieses Dokument sagt, woran das liegt — gemessen, nicht erschlossen.

**Kurz:** Ein Dispatch kostet **173,5 Wirtszyklen** und führt dabei **9,2
Gasttakte** aus. Das Modul gibt die Kontrolle also alle neun Gastbefehle an die
C++-Schleife zurück. Dolphins JIT läuft rund elfmal länger am Stück. Nicht die
Rückfälle sind das Problem, sondern die Häufigkeit der Rückgaben.

## Ausgangslage

Ungedrosselt, gleicher Abschnitt, Null-Grafik, vier Kerne:

| Kern | Bilder je Sekunde |
|---|---|
| reine Emulation (JIT64) | 186,9 |
| statischer Kern, Rückweg aus | 31,5 |
| statischer Kern, Rückweg an | 24,8 |

## Was es nicht ist

**Die Rückfälle aus nativem Code sind fast alle billig.** `hook_fb` zählte
134,9 Millionen je 180 Bilder, was zunächst nach dem Hauptposten aussah. Nach
Art aufgeschlüsselt:

| Art | Anzahl | Weg |
|---|---|---|
| `dcbf` (xo 86) | 132.653.100 | schnell |
| `dcbi` (xo 470) | 2.149.049 | schnell |
| `dcbst` (xo 54) | 124.440 | schnell |
| `icbi` (xo 982) | **85** | schnell, mit Blockinvalidierung |
| `mtspr`, `mfspr` | 1.318 | **langsam** (SyncOut, Interpreterschritt, SyncIn) |

Nur 1.318 von 134,9 Millionen nehmen den teuren Weg. Und `icbi` — der einzige,
der die Blockinvalidierung des JIT auslöst — kommt 85-mal vor. Eine
Invalidierungslawine gibt es also nicht.

**Die Vorarbeit im Hook kostet nichts.** Gegenprobe: Der schnelle Weg wurde vor
die gesamte übrige Vorarbeit gezogen (vor `TranslateRelAddress`, vor die
Lockstep-Abfrage, vor die Zeigerauflösungen) und ungedrosselt gemessen:

| Fassung | Bilder je Sekunde |
|---|---|
| Vorarbeit wie bisher | 23,9 / 23,3 |
| Vorarbeit übersprungen | 23,9 / 23,1 |

Kein Unterschied. Diese naheliegende Optimierung ist damit ausgeschlossen —
gemessen, nicht vermutet.

## Was es ist

Ein `__rdtsc` je Burst (nicht je Dispatch; bei 513 Dispatches je Burst im
Rauschen), 300 Bilder ungedrosselt:

| Messung | Wert |
|---|---|
| Wirtszyklen in der Burst-Schleife | 34.125.955.332 |
| Dispatches | 196.700.326 |
| **Wirtszyklen je Dispatch** | **173,5** |
| verbuchte Gasttakte je Dispatch | **9,2** |
| Wanduhr des Laufs | 12,46 s |

Die 34,1 Milliarden Wirtszyklen bei 12,46 s entsprechen 2,74 GHz — also steckt
praktisch die **gesamte** Laufzeit in der Burst-Schleife. Das Verhältnis ist
rund **19 Wirtszyklen je Gasttakt**; ein guter JIT liegt bei eins bis drei.

### Die Aufteilung

Ein zweites `__rdtsc`-Paar direkt um `m_module->dispatch()`. Die Sonde
verfälscht mit: Der Gesamtwert steigt von 173,5 auf 222,6, die Sonde kostet
also 49,1 Zyklen. Um die herausgerechnet:

| Anteil | Wirtszyklen je Dispatch |
|---|---|
| im Modul | ≈ 94 |
| in der C++-Schleife drumherum | ≈ 80 |
| zusammen | 173,5 |

**Beide Hälften sind gleich groß.** Es gibt also nicht einen Schuldigen,
sondern zwei Hebel.

### Wie oft zurückgegeben wird

| Kern | Rückgaben an die Wirtsschleife je Bild |
|---|---|
| Dolphins JIT (Dispatcher-Durchläufe, ohne Rückweg) | rund 60.000 |
| das Modul (Dispatches) | rund 653.000 |

Elfmal häufiger. Der JIT verkettet seine Blöcke direkt und läuft lange
Strecken, ohne in C++ zurückzukehren; das Modul kehrt alle neun Gastbefehle
zurück.

## Zwei weitere Verdächtige in der Schleife, einer davon klein

**Die Kachelsuche.** Sie geht über eine Tabelle mit einem `int` je
Gast-Befehlswort — 24 MiB, zufällig angesprungen. Ein Dispatch deckt aber nur
neun Befehle ab und bleibt fast immer in derselben Kachel. Ein
Ein-Eintrag-Zwischenspeicher (Bereich und Index der zuletzt getroffenen Kachel;
der **Zustand** wird weiterhin frisch aus `m_chunk_state` gelesen, deshalb
braucht er bei Zustandsänderungen keine Leerung) im selben Binärcode
gegeneinander gemessen:

| | Bilder je Sekunde |
|---|---|
| mit Zwischenspeicher | 24,52 / 25,31 / 25,04 |
| ohne | 24,04 / 24,35 / 24,23 |

**+3,1 %**, konsistent über alle drei Paare. Real, aber klein. Er bleibt drin —
15 Zeilen für 3 % —, er erklärt aber die 80 Zyklen nicht.

**Die Zeitbasis.** `AdvanceGuestTimebase` teilt und modulo-t durch
`TIMER_RATIO`, eine Konstante; der Übersetzer macht daraus eine Multiplikation.
Kein Posten.

Damit sind drei naheliegende Erklärungen für die 80 Zyklen der Schleife
geprüft und zwei davon ausgeschlossen. Wo der Rest sitzt, ist **offen**.

## Zwei Hebel

**1. Die Schleife billiger machen (≈ 80 Zyklen, in der Laufzeit, patchbar).**
Bisher gefunden: 3 % durch den Kachel-Zwischenspeicher. Der Rest ist nicht
lokalisiert; ohne einen Profiler (in dieser Umgebung nicht vorhanden) bleibt
nur weiteres Ausschlussverfahren.
Je Dispatch laufen heute: Ladungsprüfung des Kachelzustands, Taktverbuchung,
`AdvanceGuestTimebase`, Neuberechnung des Taktbudgets, zwei Leerlaufprüfungen
und zwei Ausnahmeabfragen. Vieles davon würde je Burst genügen statt je
Dispatch. Ein Teil ist in dieser Sitzung schon abgeräumt worden: Die
Verdrahtung von `host_call_active` hat einen indirekten Aufruf je Dispatch
entfernt und **52 % gebracht** ([16-RUECKWEG.md](16-RUECKWEG.md)).

**2. Seltener zurückgeben (≈ 94 Zyklen mal seltener, im Recompiler).** Neun
Gastbefehle je Dispatch heißt: Das Modul gibt bei fast jedem Sprung ab.
Innerhalb einer Kachel springt es per `goto`; die Kacheln fassen 4.096 Befehle,
also kann die Ursache nicht das Überschreiten von Kachelgrenzen allein sein —
es sind die Sprünge, deren Ziel erst zur Laufzeit feststeht, allen voran
Funktionsaufrufe und -rücksprünge.

Die Form der Lösung ist dieselbe, die der JIT benutzt: Das Modul löst solche
Sprünge selbst auf, statt abzugeben. Es kennt sein Taktbudget bereits
(`ctx->cycle_budget`, von der Schleife je Dispatch gesetzt) und könnte
weiterlaufen, bis das Budget erschöpft ist oder die Adresse seine Deckung
verlässt. Die Schwierigkeit liegt nicht im Ablauf, sondern in der Sicherheit:
Vor jedem Kacheleintritt prüft heute die Wirtsschleife den Kachelzustand gegen
selbstmodifizierenden Code. Wer diese Prüfung ins Modul verlegt, muss sie
genauso streng halten.

Das ist eine Änderung an DolRecomp — einem dritten fremden Baum — und zieht
einen Modulbau von rund 65 Minuten nach sich. **In dieser Sitzung nicht mehr
begonnen.**

Der zweite Hebel ist der größere: Er verkleinert nicht einen Posten, sondern
die Anzahl, mit der beide Posten multipliziert werden.

## Was das für das Ziel bedeutet

„Nativ mit so vielen Bildern je Sekunde" ist mit dem heutigen Modulaufbau
nicht zu haben: Nativ ist derzeit siebenmal langsamer als Emulation. Die
Ursache ist aber weder das Verfahren noch das Rekompilat an sich, sondern eine
Struktureigenschaft — wie oft das Modul abgibt. Das ist behebbar.

**Nicht gemessen und hier nicht messbar:** wie sich das auf einer echten
Grafikkarte und einem schnelleren Kern verhält. Alle Zahlen stammen von vier
Kernen mit Null-Grafik. Der Faktor zwischen den Kernen dürfte bleiben, die
absoluten Bildraten nicht.

## Grenzen

- Ein Abschnitt (Start bis Dateiauswahl), ein Modul, ein Rechner.
- `__rdtsc` zählt Wirtszyklen ohne Rücksicht auf Taktänderungen; die
  Umrechnung auf 2,74 GHz ist eine Plausibilitätsprobe, keine Kalibrierung.
- Die Aufteilung 94 zu 80 stützt sich auf die Annahme, dass die Sonde in
  beiden Messungen gleich viel kostet. Die 49,1 Zyklen sind aus der Differenz
  der beiden Läufe bestimmt, nicht unabhängig gemessen.
