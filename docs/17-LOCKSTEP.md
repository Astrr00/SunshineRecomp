# Der Lockstep-Verifizierer: freigeschaltet und erstmals gelaufen

Stand: 2026-09-15. Folgt auf [16-RUECKWEG.md](16-RUECKWEG.md). Dort wurde der
Rückweg in den statischen Kern gebaut; dieses Dokument beantwortet die Frage,
die damit sofort dringend wurde: **Rechnet der nativ ausgeführte Code richtig?**

**Kurz:** Der Verifizierer ist freigeschaltet, und sein Urteil ist lesbar
geworden. Er meldete zunächst Abweichungen in 3,4 % der geprüften Blöcke. Zwei
Ursachen sind gefunden und je am Einzelfall belegt, und **keine von beiden ist
ein Rechenfehler des Rekompilats**: seine eigene Halteregel, und ein
Verbuchungsunterschied zwischen Modul und Interpreter.

Stand nach beiden Korrekturen:

| Umfang | geprüft | Meldungen |
|---|---|---|
| 30 Bilder, ohne Rückweg | 151 | 0 |
| 30 Bilder, mit Rückweg | 3.410 | **0** |
| ganze Eingabefolge, mit Rückweg | 16.790 | **19** (0,11 %) |

Über 30 Bilder bleibt nichts übrig. Über die ganze Folge bleiben 19, und die
sind **nicht** aufgeklärt.

## Warum er abgeschaltet war

[13-STATISCHER-KERN.md](13-STATISCHER-KERN.md) hielt fest, dass der
Verifizierer sich mit dieser Zeile abmeldet:

```
[lockstep] module lacks ppc_set_mem_write_journal export;
           lockstep DISABLED (rebuild the module).
```

Die Ursache liegt nicht im Recompiler, sondern im Linker-Versionsskript
`module-template/module.exports`:

```
{ global: staticrecomp_get_module; local: *; };
```

Die Funktion trägt in `GXRuntime/src/core/cpu.c:27` bereits
`__attribute__((visibility("default")))`. Das `local: *` des Versionsskripts
überstimmt das. Und weil das Modul mit ThinLTO gebaut wird, ist die Folge
schwerer als ein fehlender Name: Wenn niemand `ppc_set_mem_write_journal`
aufrufen kann, ist `g_mem_write_journal` beweisbar immer NULL, und der
Optimierer entfernt **alle** Journal-Aufrufe aus den Schreibpfaden
(`cpu.h:223,247,271,295`). Ein nachträgliches Sichtbarmachen am fertigen
`.so` wäre also wirkungslos gewesen — es brauchte einen neuen Link.

## Was getan wurde

Eine Zeile im Versionsskript, dann ein reiner Neulink im vorhandenen
`module-build`. Die 221 Kacheln mussten nicht neu übersetzt werden:

| Gegenstand | Wert |
|---|---|
| Dauer des Neulinks | **29 min 47 s** (gegen rund 65 min für einen Vollbau) |
| exportierte Symbole vorher | `staticrecomp_get_module` |
| exportierte Symbole nachher | `staticrecomp_get_module`, `ppc_set_mem_write_journal` |
| Prüfsumme des Prüfmoduls | `48c3fda9f73c55b1…` |
| Prüfsumme des ausgelieferten Moduls | `63816d8db039e336…` — **unverändert** |

Das Versionsskript wurde danach zurückgesetzt. Das Prüfmodul liegt getrennt
und wird nicht ausgeliefert: Der Export kostet an jeder Gast-Speicherschreibung
einen geladenen Zeiger, einen Test und einen nicht genommenen Sprung, weil der
Optimierer die Aufrufe nun behalten muss.

**Falle für die nächste Sitzung:** Der Cache-Schlüssel von
`moderngekko-port build` kennt den Inhalt von `module.exports` nicht. Ein
erneuter Aufruf meldet „cache hit" und liefert je nach Reihenfolge das falsche
Modul. Prüf- und Auslieferungsmodul gehören in getrennte Verzeichnisse.

## Der erste Lauf

30 Bilder, mit Rückweg, Prüfmodul:

```
[lockstep] summary: checks=3408 reports=116 skipped_fallback=24 skipped_zero=9
           cap_hits=0 filtered=0 undercharges=0 max_deficit=0 distinct_pcs=3408
```

3.408 verschiedene Einsprungadressen geprüft, **116 Abweichungen** (3,4 %),
keine einzige Unterverbuchung von Takten (`undercharges=0`), keine
Begrenzungstreffer (`cap_hits=0`).

## Die Gegenprobe, die entscheidet

Derselbe Lauf **ohne** Rückweg — dann führt das Modul nur die 682 Blöcke des
Starts aus:

```
[lockstep] summary: checks=151 reports=5 skipped_fallback=18 skipped_zero=1
           cap_hits=0 filtered=0 undercharges=0 max_deficit=0 distinct_pcs=151
```

| | geprüft | gemeldet | Rate |
|---|---|---|---|
| ohne Rückweg | 151 | 5 | 3,31 % |
| mit Rückweg | 3.408 | 116 | 3,40 % |

Und die fünf Meldungen des Kontrolllaufs sind **dieselben** wie die ersten
fünf des anderen — gleiche Einsprungadresse, gleiche Endadresse, in gleicher
Reihenfolge:

```
#1 entry=0x80005458 end=0x80003194
#2 entry=0x80003194 end=0x80003194
#3 entry=0x80345954 end=0x80345CCC
#4 entry=0x803383E4 end=0x803384B8
#5 entry=0x803482A4 end=0x803482E8
```

**Damit ist belegt:** Der Rückweg erzeugt keine Abweichungen. Er führt nur
22-mal so viele Blöcke der Prüfung zu. Was der Verifizierer meldet, meldete er
vorher auch — es wurde nur an 151 statt an 3.408 Stellen gefragt.

## Die Ursache: die Halteregel des Verifizierers

Der Verifizierer schreibt die Speicherzugriffe des Moduls zurück, lädt die
Einsprungregister und lässt Dolphins Interpreter laufen — **bis `pc ==
end_pc`** (`StaticRecompLockstep_Check.cpp:178`). Bei einer Schleife, deren
Ende zugleich ihr Kopf ist, ist das nach der ersten Runde der Fall.

Am Einzelfall nachgewiesen. `STATICRECOMP_LOCKSTEP_TRACE=0x80003194`:

```
[ls-trace] ENTRY r3=0x803E985C r4=0x00000000 r5=0x00022AC0 charge=260
[ls-trace] step 1: pc=0x80003194 r3=0x803E985C …
[ls-trace] step 9: pc=0x800031B4 r3=0x803E987C …      <- eine Runde: +0x20
```

Die gemeldete Abweichung dazu:

```
DIVERGE #2 entry=0x80003194 end=0x80003194:
    r0:N=0x1131,I=0x114a   r3:N=0x803e9b9c,I=0x803e987c
```

`0x803e9b9c − 0x803e985c = 0x340 = 26 × 0x20`: Das Modul lief **26 Runden**,
die Nachbildung **eine**. Die Differenz in `r0` ist 25 — genau 26 − 1. Die
verbuchten 260 Takte passen zu 26 Runden eines Rumpfes von zehn Befehlen.
Beide Seiten rechnen dasselbe; sie laufen nur verschieden weit.

Von den 116 Meldungen enden **59** an oder vor ihrem Anfang, sind also
Schleifen; **41** enden genau an ihrem Anfang.

### Die Korrektur

`patches/recompcore-lockstep-halteregel.patch`, eine Zeile: Die Nachbildung
hält an der Endadresse erst an, wenn sie auch so viele Takte verbraucht hat,
wie das Modul verbucht hat.

```cpp
if (ppc.pc == end_pc && interp_cycles >= native_charge)
  break;
```

| | Meldungen vorher | nachher |
|---|---|---|
| mit Rückweg, 3.408 geprüfte Blöcke | 116 | **4** |
| ohne Rückweg, 151 geprüfte Blöcke | 5 | **0** |

**112 der 116 Meldungen waren die Halteregel.**

### Die Spätprüfung: den Verifizierer die Frage selbst beantworten lassen

Statt die übrigen Meldungen einzeln von Hand zu verfolgen, beantwortet der
Verifizierer die Frage jetzt selbst. Wenn er an der Endadresse nicht
übereinstimmt, läuft die Nachbildung weiter — bis zu acht weitere Ankünfte an
derselben Adresse — und vergleicht jedes Mal erneut. **Stimmt sie später
exakt überein** (alle Register, alle Gleitkommawerte, alle protokollierten
Speicherbytes), dann lag der Unterschied am Haltepunkt und nicht an der
Rechnung; das wird als `late` gezählt statt als Abweichung gemeldet.

Wirkung über 30 Bilder:

| | Meldungen | Spättreffer |
|---|---|---|
| vorher | 4 von 3.408 | — |
| nachher | **0 von 3.410** | 4, zusammen 13 weitere Runden |

**Über 30 Bilder bleibt keine einzige Abweichung.** Alle vier waren
Spättreffer: Die Nachbildung erreichte den Zustand des Moduls nach insgesamt
13 weiteren Schleifenrunden bitgenau.

Über die ganze Eingabefolge fällt die Zahl von 52 auf **19 von 16.790**
(0,11 %), bei 10 Spättreffern. Eine hundertfach höhere Schrittobergrenze
ändert daran nichts (19 gegen 23 — Streuung zwischen Läufen).

**Diese 19 sind nicht alle vom selben Muster.** Einige zeigen Unterschiede
anderer Art: bei einem weicht der Stapelzeiger `r1` ab, bei einem anderen ein
Gleitkommaregister. Sie sind **nicht** aufgeklärt, und sie als „vermutlich
dasselbe" abzutun wäre genau der Fehler, den dieses Dokument zweimal
berichtigt hat.

### Die verbliebenen vier (vor der Spätprüfung)

```
#1 entry=0x802F5754 end=0x802F58C4: r7:N=0x13,I=0xf
#2 entry=0x802F58C4 end=0x802F58C4: r7:N=0x2d,I=0x27
#3 entry=0x80314CBC end=0x80314D50: r28,r29,r30,r31 um 0x28 / 0x28 / 2 / 0x300
#4 entry=0x802FE0E4 end=0x802FE0E4: r3,r5 um 8, r28 um 0x10
```

Alle vier zeigen dasselbe Muster wie zuvor — Zähler und Zeiger um **genau eine
Schrittweite** auseinander, das Modul jeweils eine Runde weiter. Eine
hundertfach höhere Schrittobergrenze (`STEPCAP=2000000`) ändert nichts.

Auch das ist am Einzelfall belegt. `STATICRECOMP_LOCKSTEP_TRACE=0x802FE0E4`:

| Gegenstand | Wert |
|---|---|
| Länge einer Schleifenrunde | **29 Befehle** (Kopfbesuche bei Schritt 1, 30, 59, 88, …) |
| Schritte der Nachbildung | 261 = 9 × 29, also 9 Runden |
| Runden des Moduls | 10 (`r3` von 0x50 auf 0xa0, Schrittweite 8) |
| verbuchte Takte des Moduls | **260** |

Das Modul verbucht also rund **26 Takte je Runde, wo der Interpreter 29
Befehle zählt** — etwa 10 % zu wenig. Die neue Halteregel greift deshalb eine
Runde zu früh, und der Vergleich sieht genau eine Runde Unterschied.

**Es ist kein Rechenunterschied, sondern ein Verbuchungsunterschied.** Beide
Seiten durchlaufen dieselbe Befehlsfolge mit denselben Werten; sie hören nur
an verschiedenen Stellen auf. Damit sind alle 116 ursprünglichen Meldungen
erklärt, und in keiner einzigen steht eine Abweichung im Rechenergebnis.

Das löst die vier nicht auf — dafür müsste das Modul melden, wie viele
Befehle es ausgeführt hat, nicht nur wie viele Takte es verbucht hat. Das ist
eine Änderung an DolRecomp beziehungsweise an der Modul-Schnittstelle und
gehört in die Frage an ModernGekko ([14](14-FRAGE-AN-MODERNGEKKO.md)).

## Über die ganze Eingabefolge

Der bisherige Lauf ging über 30 Bilder. Mit der Eingabefolge bis in die
Flugplatz-Sequenz — 2.396 Bilder, 90,7 s Wanduhr — wird fünfmal mehr geprüft:

```
[lockstep] summary: checks=16781 reports=52 skipped_fallback=32 skipped_zero=99
           cap_hits=13 filtered=0 undercharges=0 max_deficit=0 distinct_pcs=16781
[staticrecomp] yield: yields=327117 rejects=102177 noprogress=0 ...
[staticrecomp] shutdown: native=421635378 fallback=0 smc_failed=0
               bursts=5380514 cycles=9302847122 ticks=40046993267
```

| Gegenstand | Wert |
|---|---|
| geprüfte Einsprungadressen | **16.781** (vorher 3.408) |
| Meldungen | **52** = 0,31 % (vorher 3,4 %) |
| nativ verbuchte Takte | 9.302.847.122 |
| `smc_failed`, `fallback`, `noprogress` | 0, 0, 0 |
| `gpMarioAddress` | `0x80e9ad44` — **derselbe Wert wie in der Referenz** |

Die 52 aufgeteilt: 5 enden an ihrem Anfang, 14 vor ihrem Anfang, 33 dahinter;
genau eine nennt MMIO. Sie zeigen dasselbe Muster wie die vier analysierten —
Zähler und Zeiger um ein kleines Vielfaches einer Schrittweite auseinander,
das Modul jeweils weiter. **Einzeln verfolgt wurden sie nicht**, also ist
„dieselbe Ursache" hier eine Lesart und kein Beleg. Dass 33 vorwärts enden,
schließt eine Schleife im Block nicht aus.

## Was daraus noch nicht folgt

Dass 3.404 von 3.408 Blöcken sauber durchlaufen, ist ein starkes Ergebnis,
aber kein Freispruch. Die folgenden Beobachtungen zur ersten Fassung bleiben
als Beleg stehen, weil sie zeigen, womit man bei diesem Verfahren rechnen muss:

**Für Artefakte des Verfahrens.** Der Verifizierer führt einen Block noch
einmal auf Dolphins Interpreter aus und vergleicht. Meldung #3 zeigt, dass das
für Hardwarezugriffe nicht wiederholbar ist:

```
mmio#:N=8,I=1   N@0xcc003004/4 … I@0x0c003004/4
```

Die native Seite hat acht Registerzugriffe gemacht, die Nachbildung einen —
und unter einer anderen Adressform. Ein zweites Lesen eines Statusregisters
liefert eben nicht denselben Wert. Von 116 Meldungen nennen allerdings nur
zwei überhaupt MMIO.

Meldung #5 (`entry=0x803482A4`) zeigt ein anderes Muster: `lr` der Nachbildung
ist die Einsprungadresse selbst, `cr` unterscheidet sich, und `r3` zeigt auf
ganz andere Speicherstellen. Die beiden Seiten sind also verschiedene Wege
gegangen — das passt eher zu einem unvollständig wiederhergestellten
Ausgangszustand als zu einem falsch übersetzten Befehl.

**Gegen Artefakte.** 114 von 116 Meldungen nennen kein MMIO. `skipped_fallback`
fängt nur 24 Blöcke ab.

**Was dagegen spricht, dass die Sache dramatisch ist:** Der Abnahmelauf
besteht. `boot` 10 von 10, `spielstart` 11 von 11, `gpMarioAddress` mit
demselben Wert wie die Referenz, Ton innerhalb von 0,1 % — bei 9,3 Milliarden
nativ ausgeführten Takten. Ein Recompilationsfehler in 3,4 % der Blöcke, der
sich auf den Spielzustand auswirkt, wäre dabei kaum unbemerkt geblieben.

## Nächster Schritt

Die 19 verbliebenen Meldungen der langen Folge sind der nächste Gegenstand —
einzeln, mit `STATICRECOMP_LOCKSTEP_TRACE`, so wie die beiden aufgeklärten
Fälle. Wer sie ungeprüft als „vermutlich dasselbe" abhakt, wiederholt den
Fehler, den dieses Dokument zweimal berichtigen musste.

Daneben bleibt der Verbuchungsunterschied, und er reicht über den
Verifizierer hinaus: Wenn das Modul je Schleifenrunde rund 10 % zu wenig
verbucht, läuft die emulierte Uhr gegenüber der geleisteten Arbeit zu schnell.
[12-TON.md](12-TON.md) hat Ton und Bild innerhalb von 0,3 % zur Filmrate
gemessen — das schließt einen kleinen systematischen Fehler nicht aus, es
begrenzt ihn. Zu klären ist, ob 26 gegen 29 für diesen Block richtig ist (der
Gekko braucht nicht für jeden Befehl einen Takt) oder ob das Modul zu wenig
verbucht.

**Der Rückweg bleibt bis dahin ausdrücklich zu schalten und nicht
Voreinstellung.** Dass keine der Meldungen ein Rechenfehler ist, ist ein
starkes Ergebnis — aber die Bedingung aus Dokument 16 lautet: ein
Lockstep-Lauf ohne ungeklärte Meldungen, und vier stehen noch.

## Grenzen

- Der längste Lauf geht über 2.396 Bilder bis in die Flugplatz-Sequenz.
  Späterer Spielverlauf ist nicht geprüft. 16.781 Einsprungadressen sind viel
  gegenüber 151, aber wenig gegenüber den 901.056, die das Modul kennt.
- Die korrigierte Halteregel ist an einem Fall belegt und an 112 Meldungen
  wirksam. Dass sie in jedem denkbaren Fall richtig hält, ist damit nicht
  gezeigt; sie könnte eine echte Abweichung verdecken, die zufällig erst nach
  dem Takterreichen auftritt.
- Nur Linux, nur Jit64, nur dieses eine Modul.
- Das Prüfmodul ist nicht bitgleich mit dem ausgelieferten: Es trägt die
  Journal-Aufrufe, die der Optimierer sonst entfernt. Streng genommen prüft
  der Verifizierer damit ein anderes Binärbild als das, das ausgeliefert wird.
  Der übersetzte Spielcode ist derselbe; belegt ist das nicht.
