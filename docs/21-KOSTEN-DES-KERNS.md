# Warum der native Kern langsam ist

Stand: 2026-09-16, am selben Tag um den Nachtrag ergänzt. Der Auftraggeber
hat das Ziel präzisiert: „dass das Spiel nativ mit so viel Fps läuft".
[16-RUECKWEG.md](16-RUECKWEG.md) hat den nativen Kern hergestellt und dabei
gemessen, dass er **langsamer** ist als der Ersatz-JIT. Dieses Dokument sagt,
woran das liegt — gemessen, nicht erschlossen.

> **Nachtrag vom 2026-09-16** am Ende des Dokuments: Zwei der drei Vorschläge
> aus „Zwei Hebel" sind gemessen und wirkungslos, einer ist berichtigt, die
> Leerlaufprüfung hat **9 % Bildrate** hergegeben — und der grösste Posten ist
> gefunden: **zwei Drittel aller Dispatches sind ein einziges `dcbf`** in
> `DCFlushRange`, weil der Erzeuger danach unbedingt zurückkehrt.

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

## Nachtrag vom 2026-09-16: gemessen, drei Berichtigungen, ein Gewinn

Die drei Vorschläge aus „Zwei Hebel" sind gebaut und gemessen worden. Zwei
Aussagen von oben sind dadurch widerlegt, eine ist zu berichtigen, und dabei
ist ein Posten gefunden worden, der **9 % Bildrate** bringt.

### Berichtigung 1: Profiler gibt es hier

Oben steht „ohne einen Profiler (in dieser Umgebung nicht vorhanden)". Das war
falsch: `gdb`, `valgrind` mit `callgrind`, `gprof` und `gprofng` sind
installiert. Brauchbar war davon keiner: Ein `callgrind`-Lauf mit
Cache-Simulation über das 90 MiB große Modul hatte nach neun Minuten noch kein
einziges Bild erzeugt und wurde abgebrochen. Weitergemessen wurde deshalb mit
A/B-Läufen und Zählern — aus Kostengründen, nicht aus Mangel an Werkzeug.

### Berichtigung 2: Die Abrechnung zu bündeln bringt nichts

Der erste Hebel oben lautet, vieles an der Abrechnung „würde je Burst genügen
statt je Dispatch". Gebaut: ein Bündel von bis zu n Blöcken je Abrechnung.
Kachelzustand, Ausnahmen und Host-Call-Adressen werden weiter je Block
geprüft; gebündelt sind nur Taktverbuchung, Zeitbasis, Taktbudget und
Leerlaufprüfung. Ungedrosselt, 300 Bilder, Bilder je Sekunde:

| Bündel | Runde 1 | Runde 2 |
|---|---|---|
| 1 | 23,56 | 23,56 |
| 16 | 23,77 | 23,69 |
| 64 | 23,51 | 22,66 |
| 64, zusätzlich ohne Kachel- und Host-Call-Prüfung | 23,59 | 23,96 |

Nichts. Die Gegenprobe ohne die beiden Prüfungen ändert ebenfalls nichts —
auch sie sind kein Posten. Ein zweiter Anlauf, bei dem `ctx->downcount` je
Block geleert wird (sonst verbraucht das Bündel das modulinterne
Schleifenbudget und jede Schleife verlässt das Modul sofort), ergab 25,30 /
25,83 gegen 25,73 / 25,47 bei Bündel 8 und 26,05 / 26,66 bei Bündel 32 —
höchstens 3 %, innerhalb der Streuung zweier Läufe derselben Einstellung. Der
Code ist deshalb wieder entfernt; er kostete Wahlfreiheit bei der
Leerlauferkennung und brachte nichts.

### Der Gewinn: die Leerlaufprüfung fragte über einen Hash

Beim Zählen, **warum** ein Bündel endet, fiel der eigentliche Posten auf. Bei
Bündel 64, 300 Bilder:

| Abbruchgrund | Anzahl | Anteil |
|---|---|---|
| Gastzeiger steht wieder auf dem Einsprung | 137.589.470 | **98,4 %** |
| `ppc.Exceptions` | 954.101 | 0,7 % |
| Bündellänge erreicht | 1.141.288 | 0,8 % |
| Taktbudget | 104.622 | 0,07 % |
| `ctx->exception` | 6.478 | 0,005 % |
| Adresse nicht gedeckt | 178 | 0,0001 % |
| Host-Call | 0 | 0 |

Das Modul kehrt also bei **98 %** aller Dispatches mit dem Gastzeiger auf
genau der Adresse zurück, an der es betreten wurde. Genau dann fragt die
Schleife `IsBusyWaitLoop(address)` — und diese Funktion begann mit

```cpp
const auto cached = m_busy_wait_cache.find(address);
```

einem Hash-Zugriff auf eine `std::unordered_map`, die nicht in den L1 passt,
rund 197 Millionen Mal je 300 Bilder. Davor sitzt jetzt ein direkt
abgebildeter Zwischenspeicher aus 1.024 Einträgen (8 KiB): Schlüssel und Wert,
zwei Ladungen. Die Hash-Tabelle bleibt maßgeblich und wird an denselben
Stellen geleert wie zuvor.

Gegenprobe, **dieselbe Binärdatei**, nur `STATICRECOMP_NO_BWCACHE=1`
unterscheidet sich:

| Runde | mit Zwischenspeicher | ohne |
|---|---|---|
| 1 | 26,46 | 23,86 |
| 2 | 26,00 | 24,08 |
| 3 | 26,35 | 24,33 |
| Mittel | **26,27** | 24,09 |

**+9,0 %**, in allen drei Paaren ohne Überschneidung.
`patches/recompcore-leerlauf-zwischenspeicher.patch`.

Die Antwort selbst ändert sich nicht: Der Schlüssel ist die volle Adresse, und
geleert wird an denselben drei Stellen wie die Hash-Tabelle. Alle drei
Abnahmeszenarien bestehen damit unverändert — `nativ` 8 von 8 (35,71 % nativ),
`boot` 10 von 10, `spielstart` 11 von 11 mit `gpMarioAddress` = `0x80E9AD44`,
2.399 Bildern und 82,58 s Ton.

### Berichtigung 3: Wo der zweite Hebel wirklich sitzt

Oben steht, das Modul gebe „bei fast jedem Sprung ab" und die Lösung liege
darin, dass es solche Sprünge selbst auflöst. Der Blick in den erzeugten Code
schärft das:

- **Direkte Aufrufe über Kachelgrenzen geben bereits nicht ab.**
  `emit_cross_chunk_call` (`DolRecomp/src/backend/emitter.c`) erzeugt
  `func_XXXX(ctx);` und springt danach zur Fortsetzung zurück.
- **Kachelinterne Schleifen laufen bis `DOLRECOMP_C_LOOP_CYCLE_BUDGET`**,
  voreingestellt 256 verbuchte Takte. Die Konstante steht in einem
  `#ifndef`-Block und ist über `-D` beim Modulbau überschreibbar.
- **Abgegeben wird bei Sprüngen, deren Ziel erst zur Laufzeit feststeht**:
  `emit_dynamic_branch` schreibt `ctx->pc = target; return;`. Das trifft
  `blr`, `bctr` und `bctrl`, also jeden Funktionsrücksprung über eine
  Funktionsgrenze und jeden Aufruf über einen Zeiger.

**Was ein Wiedereintritt kostet, steht im Maschinencode.** Jede Kachelfunktion
beginnt mit einem `switch (ctx->pc)` über 4.096 Fälle — einen je Befehlswort.
`clang` macht daraus eine Sprungtabelle (Auszug aus `func_80009600`):

```
mov    $0x7fff6a00,%eax
add    0x280(%rdi),%eax        ; ctx->pc
rol    $0x1e,%eax              ; (pc - Basis) / 4
cmp    $0xfff,%eax
ja     <Vorgabezweig>
lea    <Tabelle>(%rip),%rcx
movslq (%rcx,%rax,4),%r8       ; Ladung aus 3,5 MiB .rodata
add    %rcx,%r8
jmp    *%r8                    ; indirekter Sprung
```

221 Kacheln mal 16 KiB ergeben die 3,5 MiB `.rodata` des Moduls. Jeder
Dispatch zahlt eine Ladung daraus an praktisch zufälliger Stelle und einen
indirekten Sprung, den kein Sprungvorhersager trifft. Das ist der Preis der
Eigenschaft „jede Befehlsadresse ist ein Einsprungpunkt".

### Aufgelöst: zwei Drittel aller Dispatches sind ein einziges `dcbf`

Der Widerspruch — 98 % der Rückkehren auf der Einsprungadresse, aber nur
**9,2 verbuchte Takte** je Dispatch, während ein Ausstieg über das
Schleifenbudget 256 verbuchen müsste — ist mit `STATICRECOMP_DISPATCH_SAMPLES=1`
aufgelöst. Die Stichprobe (jeder 4.096. Dispatch, 300 Bilder):

| Gastadresse | Stichproben | liegt in |
|---|---|---|
| **`0x803436B0`** | **32.384** | `DCFlushRange` (`0x8034368C`) |
| `0x803487E0` | 1.421 | `__DVDInterruptHandler`-Umfeld |
| `0x80343680` | 817 | `DCInvalidateRange` (`0x8034365C`) |

Die erste Adresse ist **23-mal häufiger als die zweite**. Hochgerechnet sind
das rund **132 Millionen von 197 Millionen Dispatches — zwei Drittel**, und
sie stimmen mit den 132.653.100 gezählten `dcbf`-Hooks überein.

Der erzeugte Code sagt, warum:

```c
label_803436AC:
    ctx->pc = 0x803436ACu;
    // 803436AC: dcbf    0, r3
    ppc_fallback_instruction(ctx, 0x7C0018ACu, 0x803436ACu);
    return;                                   // <-- hier endet der Dispatch

label_803436B0:
    ctx->downcount -= 2;
    // 803436B0: addi    r3, r3, 32
    ctx->gpr[3] = ctx->gpr[3] + (u32)(s32)(32);

label_803436B4:
    // 803436B4: bc    16, 0, 0x803436AC
    ...
            goto label_803436AC;              // <-- wird nie erreicht
```

`DCFlushRange` ist eine Schleife aus drei Befehlen: `dcbf`, `addi`, `bdnz`.
Der Erzeuger behandelt `dcbf` im `default`-Zweig von
`emit_instruction_with_range` (`DolRecomp/src/backend/emitter.c:1610`) — genauer
in einem eigenen Fall für `DCBST`, `DCBF`, `DCBI` und `ICBI`, der
`ppc_fallback_instruction` aufruft **und danach unbedingt zurückkehrt**. Der
Rücksprung der Schleife wird deshalb nie im Modul genommen: Die Wirtsschleife
tritt bei `0x803436B0` wieder ein, führt zwei Befehle aus, springt zurück auf
`0x803436AC`, und das nächste `dcbf` steigt wieder aus.

**Eine Runde dieser Schleife kostet damit einen vollen Wiedereintritt** —
Sprungtabelle über 4.096 Fälle, indirekter Sprung, Wirtsschleife: gemessene
173,5 Wirtszyklen für vier verbuchte Gasttakte.

### Der nächste Schritt, beziffert

`ppc_cache_control(CPUState*, u8 operation, u32 ea, u32 cia)` gibt es in
DolRecomps Laufzeit bereits (`src/cpu/cpu.c:598`), und RecompCore bedient den
Haken (`StaticRecompCore_Hooks.cpp`, `PPC_CACHE_DCBF`). Es fehlt allein der
Zweig im C-Erzeuger, der ihn **ohne `return`** aufruft.

Abschätzung, nicht gemessen: Zwei Drittel von 197 Millionen Dispatches mal
173,5 Wirtszyklen sind rund 22,8 von 34,1 Milliarden Wirtszyklen. Blieben die
`dcbf`-Runden im Modul, wäre der Lauf grob **zweimal bis zweieinhalbmal so
schnell**.

Was dabei zu klären ist, und warum es keine Fingerübung ist:

1. Der Haken ruft bei abgeschaltetem Daten-Cache `InvalidateICacheLine(ea)`
   auf. Eine Invalidierung kann die gerade laufende Kachel treffen. Genau
   dagegen schützt heute das `return`. Wer es entfernt, muss dem Modul einen
   Weg geben, das zu erfahren — sonst fällt die SMC-Wache aus, auf der die
   Richtigkeitsaussage dieses Ports steht.
2. `icbi` sollte weiterhin zurückkehren; nur `dcbf`, `dcbst` und `dcbi` sind
   Kandidaten.
3. Es ist eine Änderung an **DolRecomp**, dem dritten fremden Baum, und zieht
   einen vollständigen Modulbau von rund 65 Minuten nach sich. Ein
   Zwischenbau nur des Modul-Klebers genügt nicht: Der Zweig sitzt im
   erzeugten Code jeder Kachel.

Der Auftraggeber hat am 2026-09-16 entschieden: erst messen, dann bauen.

### Gemessen: `dcbf` invalidiert im Wirt gar nichts

Die Sorge aus Punkt 1 war, der Cache-Haken könne die laufende Kachel
invalidieren. Ein Zähler in `OnICacheInvalidate` (Instrumentierung in
`tools/diagnostics/staticrecomp-invalidierung.patch`, nicht Teil des Baus)
unterscheidet, woher eine Invalidierung kommt und ob sie die Kachel des
gerade laufenden Dispatches trifft:

| Lauf | Invalidierungen | aus `dcbf`/`dcbst`/`dcbi` | treffen die laufende Kachel |
|---|---|---|---|
| Boot, 600 Bilder | 134.299 | **0** | 2 |
| ganze Eingabefolge, 2.400 Bilder | 134.323 | **0** | 9 |

**Null.** Der Grund steht in `StaticRecompCore_Hooks.cpp:390-414`: Der
Rückfall-Haken hat für `dcbf`, `dcbst` und `dcbi` einen schnellen Weg, der
zwei Register liest, fünf Takte verbucht und den Gastzeiger weitersetzt —
und **nur für `icbi`** `InvalidateICacheLine` ruft. Der Kommentar dort
(„every one funnels into InvalidateICacheLine") beschreibt den Code nicht;
der Code ist strenger als sein Kommentar. Das `return` nach `dcbf` schützte
also nichts.

Die 2 beziehungsweise 9 Treffer auf die laufende Kachel kommen alle aus
`icbi` (Herkunft 255 im Zähler), fast alle im Boot, etwa

```
ea=8035f6d0 len=4 dispatch=8035f6d0 kachel=[8035d600,80361600) state=1
```

— ein `icbi` auf genau den Befehl, der gerade ausgeführt wird, bei
verifizierter Kachel. Das ist der Fall, für den die SMC-Wache gebaut ist, und
sie greift heute, weil das Modul nach `icbi` zurückkehrt. **`icbi` kehrt
deshalb weiterhin zurück.** `dcbi` ebenfalls: Es kann im Nutzermodus einen
Privilegfehler auslösen, den der langsame Weg über den Interpreter meldet,
und diese Meldung darf nicht bis zum nächsten Ausstieg liegen bleiben.

### Der Eingriff

`patches/dolrecomp-dcbf-bleibt-im-modul.patch`, 22 Zeilen in
`src/backend/emitter.c`. Für `dcbst` und `dcbf` erzeugt der Emitter jetzt

```c
ppc_fallback_instruction(ctx, 0x7C0018ACu, 0x803436ACu);
if (ctx->exception || ctx->pc != 0x803436B0u) return;
```

statt eines unbedingten `return`: Hat der Haken eine Ausnahme ausgelöst oder
den Gastzeiger woanders hingesetzt, geht die Kontrolle wie bisher an den Wirt;
sonst läuft die Kachel weiter, und der Rücksprung der `DCFlushRange`-Schleife
wird erstmals im Modul genommen. Im Erzeugnis ist das nachgesehen: drei
`dcbf`-Stellen mit der neuen Bedingung, sieben `icbi`/`dcbi`-Stellen mit dem
alten `return`.

### Gemessen: +37 %, nicht Faktor zwei

Modulbau 62 Minuten. Dieselbe Laufzeit, dieselbe Spielkopie, nur das Modul
unterscheidet sich; ungedrosselt, 300 Bilder, drei Paare:

| Runde | altes Modul | neues Modul |
|---|---|---|
| 1 | 25,39 | 34,71 |
| 2 | 25,55 | 34,94 |
| 3 | 25,45 | 34,81 |
| Mittel | 25,46 | **34,82** |

**+36,8 %**, ohne Überschneidung. Die Zähler bestätigen den Mechanismus
genau: `native` fällt von 196,8 auf **64,9 Millionen** Dispatches — die
vorhergesagten zwei Drittel weniger —, während `hook_fb` (136,2 Millionen),
`cycles` und `bursts` unverändert bleiben. Dieselbe Gastarbeit, dieselben
Haken, ein Drittel der Wiedereintritte. `smc_failed` = 0.

**Die Abschätzung „Faktor zwei bis zweieinhalb" war zu hoch.** Sie hatte
unterstellt, mit dem Wiedereintritt fielen alle 173,5 Wirtszyklen je Dispatch
weg. Weg fällt aber nur der Wiedereintritt selbst; der `dcbf`-Haken läuft
weiter — als Aufruf über `ctx->instruction_fallback` in den Wirt, mit
Lockstep-Flag, MSR-Abgleich und Taktverbuchung —, und der ist offenbar der
größere Teil des Postens. Zwei Drittel weniger Dispatches ergeben 37 % mehr
Bildrate, also kostete ein `dcbf`-Dispatch nur etwa ein Drittel dessen, was
ein durchschnittlicher Dispatch kostet. Das ist plausibel: Er führte vier
Gasttakte aus und nichts Schweres.

Der nächste Posten liegt damit im Haken selbst, nicht mehr im Erzeuger.

**Abnahme mit dem neuen Modul:** `nativ` 8 von 8 (35,45 % nativ), `boot`
10 von 10 (606 Bilder, 22,32 s Ton), `spielstart` 11 von 11
(`gpMarioAddress` = `0x80E9AD44`, 2.396 Bilder, 82,53 s Ton, Stapel
54.216 Bytes über der Grenze). Und der Tonvergleich des Boot-Mitschnitts,
altes gegen neues Modul, das schärfste Maß:

```
Ausrichtung: Versatz +0 ms, Huellkurven-Korrelation 1.0000
Abtastwertgleich: die ersten 22.291 s (100.0% der kuerzeren Aufnahme),
                  insgesamt 100.00% gleiche Abtastwerte
```

Der Tonstrom ist über die gesamte gemeinsame Länge **abtastwertgleich**. Das
neue Modul rechnet, soweit dieses Maß reicht, dasselbe wie das alte — nur
schneller. Der Lockstep-Lauf mit einem eigens gelinkten Prüfmodul folgt.

Mit **34,8 Bildern je Sekunde ungedrosselt** hält der native Kern in dieser
Umgebung erstmals die 30 Hz der Simulation — die Voraussetzung, die
[20-VARIABLE-BILDRATE.md](20-VARIABLE-BILDRATE.md) für die variable Bildrate
braucht.

## Was das für das Ziel bedeutet

„Nativ mit so vielen Bildern je Sekunde" ist mit dem heutigen Modulaufbau
nicht zu haben: Nativ ist derzeit siebenmal langsamer als Emulation. Die
Ursache ist aber weder das Verfahren noch das Rekompilat an sich, sondern eine
Struktureigenschaft — wie oft das Modul abgibt. Das ist behebbar.

Der Nachtrag vom selben Tag beziffert das: **Zwei Drittel aller Abgaben sind
ein einziger Befehl**, `dcbf` in `DCFlushRange`. Ein Zweig im C-Erzeuger, der
ihn ohne `return` behandelt, wäre grob ein Faktor zwei bis zweieinhalb — und
ist die einzige Änderung, die noch in dieser Grössenordnung liegt.

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
