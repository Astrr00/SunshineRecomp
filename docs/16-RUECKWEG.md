# Der Rückweg in den statischen Kern

Stand: 2026-09-15, am 2026-09-16 um den Abschnitt
[„Zur Voreinstellung gemacht"](#am-2026-09-16-zur-voreinstellung-gemacht)
ergänzt. Fortsetzung von
[13-STATISCHER-KERN.md](13-STATISCHER-KERN.md). Dort wurde gemessen, dass das
Rekompilat höchstens 0,18 % der Gasttakte ausführt, und als Ausweg eine
billigere Rückfrage vorgeschlagen — mit dem Zusatz, das sei „ein Vorschlag an
ModernGekko, keine Aufgabe dieses Projekts". Dieser Zusatz war falsch: Das
Projekt pflegt sechs Patches gegen die drei fremden Bäume, ein siebter ist
verfahrenskonform, und die Frage lässt sich hier messen statt sie zu stellen.

**Kurz:** Der Rückweg ist gebaut und seit dem 2026-09-16 **Voreinstellung**
(`STATICRECOMP_NO_YIELD=1` schaltet ihn aus). Der Anteil des Ersatz-JIT an den
Gasttakten fällt von **99,99 % auf 0,01 %**. Beide Abnahmeszenarien bestehen
weiterhin. Der Preis ist Geschwindigkeit: Nativ läuft das Spiel derzeit
**halb so schnell** wie mit dem Ersatz-JIT.

## Zwei Irrtümer in Dokument 13, durch Messung berichtigt

**Erstens: Der Rückweg wurde nicht „kaum erreicht", sondern gar nicht.**
Dokument 13 schreibt, `JitBaseBlockCache::Dispatch()` enthalte die Rückfrage,
werde aber selten erreicht. Tatsächlich wird der Aufruf in der Voreinstellung
nicht einmal erzeugt:

```cpp
// JitAsm.cpp, Jit64AsmRoutineManager::Generate()
if (!assembly_dispatcher || !m_jit.GetBlockCache()->GetEntryPoints())
{
  // Ok, no block, let's call the slow dispatcher
  ABI_CallFunction(JitBase::Dispatch);
```

`assembly_dispatcher` ist fest `true`, und `GetEntryPoints()` ist ungleich
Null, sobald `MAIN_LARGE_ENTRY_POINTS_MAP` gilt — die Voreinstellung
(`MainSettings.cpp:49`). Der ganze Block entfällt also.

**Zweitens: Auch wenn er erzeugt wird, gibt er die Kontrolle nicht ab.**
Gegenprobe mit `LargeEntryPointsMap=False`, 60 Bilder:

| Lauf | `native` | `verifications` |
|---|---|---|
| Voreinstellung | 682 | 7 |
| `LargeEntryPointsMap=False` | 682 | **174** |

Die 174 statt 7 Verifikationen belegen, dass die Rückfrage jetzt gestellt
wird. `native` bleibt trotzdem bei 682. Der Grund steht im Quelltext:
`Dispatch()` liefert bei einer Moduladresse `nullptr`, und `nullptr` heißt im
Dispatcher nicht „aussteigen", sondern „kein Block vorhanden". Der JIT ruft
daraufhin `JitTrampoline`, übersetzt die Moduladresse selbst und springt
zurück nach `dispatcher_no_check` (`JitAsm.cpp:211-220`).

Es gab in diesem Stand also **keinen** Rückweg.

## Wo ein Rückweg hingehört: gemessen, nicht geraten

Drei Laufzeitzähler, in den erzeugten Code eingebaut (die Messfassung ist
nicht Teil des Patches):

| Messung | 60 Bilder | 600 Bilder |
|---|---|---|
| Dispatcher-Durchläufe | 31.131.945 | 35.840.826 |
| `rfi`-Ausgänge | 2.708.457 | 3.020.736 |
| Ausnahme-Ausgänge | 9.002 | 511.336 |

Und die Zahl, die entschied — wie viele dieser Sprungziele überhaupt im
Adressbereich des Moduls liegen:

| Ausgang | im Modulbereich | Anteil |
|---|---|---|
| `rfi` | 3.018.233 von 3.020.612 | **99,92 %** |
| Ausnahme | 496.798 von 510.424 | 97,3 % |

Die Gelegenheit zurückzukehren besteht also rund 3,5 Millionen Mal je Lauf.
Sie wurde nur nie wahrgenommen, weil niemand den Ausstieg erzeugt hat.

## Was gebaut wurde

`patches/recompcore-rueckweg.patch`, 177 Zeilen in vier Dateien:

1. **`StaticRecompCore.cpp`** veröffentlicht beim Laden des Moduls dessen
   Codebereich als `g_sr_yield_low` und `g_sr_yield_span`. Eine Spanne von 0
   heißt: abgeschaltet.
2. **`Jit64/Jit.cpp`** prüft an den Ausgängen von `rfi` und Ausnahme mit einem
   reinen Bereichsvergleich, ob das Sprungziel im Modul liegt, und verlässt
   den Dispatcher dann über den vorhandenen Ausgang `dispatcher_exit` —
   wortgleich zu der Ausleitung, die der Debugger schon heute benutzt.
3. **`StaticRecompCore_Run.cpp`** entscheidet weiterhin allein: Die
   Laufschleife prüft nach dem Ausstieg mit `DispatchableAt` und beginnt einen
   nativen Burst. Lehnt sie ab, vermerkt sie die Adresse in
   `g_sr_yield_block_pc`, und der nächste Rücksprung dorthin bleibt im JIT.
4. **Notbremse:** Bleiben Programmzähler und `downcount` über 16 Runden
   unverändert, wird der Rückweg abgeschaltet und eine Zeile nach stderr
   geschrieben. Der gescheiterte Versuch aus Dokument 13 lief 1.447 Sekunden
   und hinterließ nicht einmal eine Zählerzeile; das darf sich nicht
   wiederholen.

**Der Ausstieg ist stapelsicher, auch aus einem über `CALL` betretenen
Dispatcher.** `dispatcher_exit` ruft zuerst `ResetStack`, und das ist
`MOV(64, R(RSP), PPCSTATE(stored_stack_pointer))` (`JitAsm.cpp:252-255`) —
der beim Eintritt in `Jit64::Run()` gesicherte Stapelzeiger. Offene Rahmen der
BLR-Optimierung werden damit verworfen, bevor die aufrufererhaltenden Register
zurückgeholt werden. Dieselbe Ausleitung benutzt der Debugger schon heute.

Der Test sitzt **nicht** im gemeinsamen Dispatcher. Der Untersuchungslauf
empfahl das, weil `rfi` mit 88 Ereignissen je Bild zu selten schien. Die
Messung widerlegt es: Sobald der erste Rücksprung greift, führt das Modul
`rfi` selbst aus und behält die Kontrolle. Die Dispatcher-Durchläufe fielen
von 35.829.680 auf 29.882. Ein Test im heißen Pfad wäre Aufwand ohne Ertrag.

## Wirkung

Gleicher Lauf über 180 Bilder, exakt gemessen — der Nenner ist jetzt
`CoreTiming::GetTicks()` und keine Annahme über die Bildrate mehr:

| Wohin die Gasttakte gehen | ohne Rückweg | mit Rückweg |
|---|---|---|
| ins Rekompilat | 59.585 (0,0015 %) | 1.449.070.481 (35,11 %) |
| in den Ersatz-JIT | 4.077.555.153 (**99,99 %**) | 263.437 (**0,01 %**) |
| übersprungener Leerlauf | — | 2.001.994.418 (48,51 %) |
| nicht zugeordnet | — | 675.408.850 (16,37 %) |

Der belastbare Satz braucht keine Auslegung: **derselbe Zähler, davor und
danach, 99,99 % gegen 0,01 %.**

Über den langen Lauf (`spielstart`, 2.399 Bilder) wird das Bild schärfer; die
16,37 % nicht zugeordneter Takte waren fast ganz ein Anlaufeffekt:

| Wohin die Gasttakte gehen | Takte | Anteil |
|---|---|---|
| ins Rekompilat | 9.326.749.979 | 23,23 % |
| in den Ersatz-JIT | 6.150.917 | 0,015 % |
| übersprungener Leerlauf | 29.977.973.976 | 74,66 % |
| nicht zugeordnet | 841.956.643 | 2,10 % |

Drei Viertel der emulierten Zeit sind übersprungener Leerlauf — Takte, die
niemand ausführt. Von den Takten, die tatsächlich ausgeführt werden, entfallen
**99,93 %** auf das Rekompilat. Die verbleibenden 2,10 % sind nicht zugeordnet
und werden hier nicht als nativ verbucht.

## Richtigkeit

Beide Abnahmeszenarien bestehen mit aktivem Rückweg:

| Szenario | Zusagen | `gpMarioAddress` | Ton | `smc_failed` |
|---|---|---|---|---|
| `boot` | 10 von 10 | — | 22,29 s (Referenz 22,35 s) | 0 |
| `spielstart` | 11 von 11 | `0x80e9ad44` (**gleich der Referenz**) | 82,62 s (Referenz 82,60 s) | 0 |

In beiden Läufen steht `noprogress=0`: Die Notbremse hat nie ausgelöst.

Das Spiel spielt bis in die Flugplatz-Sequenz, die Arena- und Heapgrenzen
stimmen byteweise, der Stapel bleibt 54.216 Bytes über der Grenze.

**Das ist kein Richtigkeitsbeweis.** Der Lockstep-Verifizierer ist inzwischen
freigeschaltet ([17-LOCKSTEP.md](17-LOCKSTEP.md)) und zeigt: Die Abweichungen,
die er meldet, gibt es mit und ohne Rückweg in derselben Rate und an denselben
Blöcken — der Rückweg erzeugt also keine. Ob die Abweichungen selbst
Recompilationsfehler oder Artefakte des Verfahrens sind, ist offen. Solange das
so ist, sind die Abnahmeszenarien Stichproben und keine Prüfung.

## Am 2026-09-16 zur Voreinstellung gemacht

Bis dahin war der Rückweg ausdrücklich zu schalten (`STATICRECOMP_YIELD=1`),
mit der hier notierten Bedingung, das erst umzudrehen, wenn ein Lockstep-Lauf
ohne Meldung vorliegt. Beides hat sich geändert:

- Die Belege sind besser geworden. Nach den zwei Korrekturen am Verifizierer
  ([17-LOCKSTEP.md](17-LOCKSTEP.md)) meldet er über 30 Bilder **0 von 3.410**
  Prüfungen, statt vier wie zum Zeitpunkt der Bedingung. Über die ganze
  Eingabefolge bleiben 19 von 16.790 (0,11 %); die sind offen.
- Der Auftrag ist eindeutig: „Ziel wäre es dass das Spiel nativ mit so viel
  Fps läuft." Ein Schalter, der in der Voreinstellung *aus* ist, macht das
  Erzeugnis in der Voreinstellung zur Emulation — und jede Messung, die ihn
  vergisst, misst das Falsche. Genau dieser Fehler steht in Dokument 13.

Die Bedingung ist damit nicht erfüllt, sondern bewusst ersetzt. Der Schalter
ist umgekehrt worden, nicht entfernt:

```cpp
// StaticRecompCore.cpp, LoadModule()
const bool wanted = std::getenv("STATICRECOMP_NO_YIELD") == nullptr;
```

Gegenprobe über 180 Bilder, gleiche Spielkopie, gleiches Modul:

| Lauf | `native` | `cycles` | nativer Anteil |
|---|---|---|---|
| ohne Umgebungsvariable | 192.089.631 | 1.444.592.575 | 35,20 % |
| `STATICRECOMP_NO_YIELD=1` | 682 | 59.570 | 0,00 % |

Alle drei Abnahmeszenarien bestehen **ohne** gesetzte Umgebungsvariable:
`nativ` 8 von 8 (35,20 % nativ), `boot` 10 von 10, `spielstart` 11 von 11
(`gpMarioAddress` = `0x80E9AD44`, 2.397 Bilder, 82,56 s Ton).

Was offen bleibt, bleibt offen: die 19 Meldungen und die Geschwindigkeit
([21-KOSTEN-DES-KERNS.md](21-KOSTEN-DES-KERNS.md)). Wer sie untersucht,
schaltet mit `STATICRECOMP_NO_YIELD=1` zurück und vergleicht.

## Die Zusage

Damit der Befund nicht als Behauptung stehen bleibt, ist er eine prüfbare
Zusage geworden: `tools/acceptance/nativ.json` verlangt
`min_native_share: 0.25`. Die Zusage wird aus `cycles` und dem neuen `ticks`
der Zählerzeile gebildet — gemessen, nicht mehr aus Bildzahl und angenommener
Bildrate geschätzt, wie es Dokument 13 noch tun musste.

Gegenprobe, damit die Zusage nicht wertlos ist:

| Lauf | Ergebnis | gemessener Anteil |
|---|---|---|
| mit Rückweg | bestanden | 35,58 % |
| ohne Rückweg | **nicht bestanden** | 0,00 % |

## Der Preis: Geschwindigkeit

Ungedrosselt, gleicher Abschnitt, je zwei Läufe, Null-Grafik:

| Kern | Bilder je Sekunde |
|---|---|
| reiner JIT64 (`MODERNGEKKO_STATICRECOMP=0`) | 187,8 / 190,4 |
| statischer Kern, Rückweg aus | 31,3 / 30,9 |
| statischer Kern, Rückweg an | **16,3 / 16,2** |

Nativ war also halb so schnell wie der Ersatz-JIT im statischen Kern. Die
Ursache ist nicht das Rekompilat selbst, sondern der Aufwand je Dispatch:
192.215.336 Dispatches für 1.449.070.481 Takte sind **7,5 Takte je Dispatch**,
und die Burst-Schleife leistete je Dispatch Arbeit, die je Burst genügt hätte.

### Ein Teil davon ist behoben

Der auffälligste Posten war ein indirekter Aufruf in die Mod-Verwaltung bei
**jedem** Dispatch. Er entstand, weil `host_call_active` und
`host_call_generation` in ModernGekko nie verdrahtet waren
(`dolphin_runtime.cpp:749-753`), obwohl `ModManager` beide längst beantwortet.
Der statische Kern nahm deshalb an, es gebe immer Guest-Abfangstellen
(`RefreshHostCalls`, `StaticRecompCore_SMC.cpp:316-332`), hielt
`m_guest.host_call` ungleich null und fragte in der inneren Schleife bei jeder
Adresse nach. Zwei Zeilen, `patches/moderngekko-host-call-active.patch`:

| Kern | vorher | nachher |
|---|---|---|
| reiner JIT64 | 187,8 / 190,4 | 186,6 / 187,2 |
| statischer Kern, Rückweg aus | 31,3 / 30,9 | 31,8 / 31,2 |
| statischer Kern, Rückweg an | 16,3 / 16,2 | **24,7 / 24,9** |

**52 % mehr Leistung im nativen Pfad.** Der Abstand zum Ersatz-JIT schrumpft
von Faktor 2,0 auf 1,27. Die drei Abnahmeszenarien bestehen danach unverändert
(`boot` 10/10, `spielstart` 11/11, `nativ` 8/8).

Der Rest ist der nächste Angriffspunkt und keine Grenze des Verfahrens:
Leerlauferkennung, Zeitbasis und Kachelabfrage laufen weiterhin je Dispatch.

## Was das für das Vorhaben bedeutet

Die Grundsatzfrage aus Dokument 13 ist beantwortet, ohne dass eine fremde
Antwort abgewartet werden musste: Ein nativer Port ist mit diesem Unterbau
möglich, der Rückweg fehlte schlicht. Damit ist WP2 nicht länger blockiert.

Die Frage an ModernGekko ([14](14-FRAGE-AN-MODERNGEKKO.md)) bleibt sinnvoll,
hat aber einen anderen Inhalt: nicht mehr „ist das der vorgesehene Zustand",
sondern „hier ist ein Patch, der den Rückweg herstellt — ist das der
beabsichtigte Weg, und was fehlt ihm noch?"

## Grenzen

- Gemessen auf vier Kernen unter Linux mit Null-Grafik. Die
  Geschwindigkeitszahlen vergleichen CPU-Kerne miteinander und sagen nichts
  über eine echte GPU.
- Der Lockstep-Verifizierer fehlt. Ohne ihn ist die Richtigkeit nativ
  ausgeführten Codes nicht geprüft, sondern nur stichprobenhaft beobachtet.
- 2,10 % der Gasttakte sind nicht zugeordnet (über den langen Lauf; über 180
  Bilder waren es 16,37 %, weil der Anlauf durchschlägt).
- Nur `rfi` und Ausnahme-Ausgänge sind Rückwegpunkte. Kehrt das Spiel auf
  anderem Weg in Modulcode zurück, bleibt die Gelegenheit ungenutzt. Nach der
  Messung kommt das nicht vor, bewiesen ist es nicht.
- Nur Jit64 (x86-64). Der ARM64-JIT hat den Rückweg nicht.
- Windows ist ungeprüft: Der Patch ist plattformunabhängiger C++, aber gebaut
  und gemessen wurde unter Linux.
