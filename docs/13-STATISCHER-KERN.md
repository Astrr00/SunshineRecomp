# Wie viel vom Spiel läuft wirklich aus dem Rekompilat?

Stand: 2026-09-15. Entstanden als Nebenbefund der Tonmessung
([12-TON.md](12-TON.md)) und hier getrennt aufgeschrieben, weil die Frage den
Kern des Vorhabens betrifft.

**Kurz:** In keinem der 37 aufgezeichneten Läufe hat das rekompilierte Modul
mehr als **0,18 %** der Gasttakte ausgeführt. Der Rest lief in Dolphins
JIT64, der im statischen Kern als Ersatz mitläuft. Die Zeile
`native=… fallback=0` belegt das Gegenteil nicht: `fallback` zählt nur
Interpreter-Einzelschritte, nicht den Ersatz-JIT.

**Die Ursache ist gefunden** (Messung unten): Die Ausnahmevektoren des
GameCube-Betriebssystems liegen bei `0x80000100` bis `0x80001700`. Sie stehen
nicht in der `main.dol`, sondern schreibt das Betriebssystem beim Start selbst
in den Speicher — sie sind also in keinem Modul enthalten. Beim ersten
Systemaufruf springt das Spiel dorthin, der statische Kern übergibt an JIT64,
und JIT64 gibt die Kontrolle praktisch nicht zurück. Das passiert vor dem
ersten ausgegebenen Bild.

## Was die Zähler bedeuten

`StaticRecompCore.cpp:233` gibt beim Herunterfahren aus:

```
[staticrecomp] shutdown: native=… fallback=… native_exc=… hook_fb=…
               smc_failed=… verifications=… reverify_events=… bursts=… cycles=…
```

| Zähler | Bedeutung | Quelle |
|---|---|---|
| `native` | Aufrufe von `m_module->dispatch()`, also Blöcke aus dem Modul | `StaticRecompCore_Run.cpp:123,126` |
| `fallback` | **nur** Interpreter-Einzelschritte (`SingleStepInner`) | `Run.cpp:213,224` |
| `hook_fb` | einzelne Befehle, die nativer Code an den Interpreter abgibt | `Hooks.cpp:376` |
| `bursts` | Läufe zwischen `SyncIn` und `SyncOut` | `Run.cpp:107` |
| `cycles` | im Modul verbuchte Gasttakte | `Run.cpp:144` |

Der entscheidende Zweig erhöht **keinen** Zähler:

```cpp
if (m_module_active && IsForcedFallbackAddress(ppc.pc))
{ ppc.downcount -= interpreter.SingleStepInner(); ++m_fallback_steps; }
else if (m_fallback_jit)
{ m_fallback_jit->Run(); }                    // Run.cpp:216-218, zählt nichts
```

`m_fallback_jit` wird in `Init()` bedingungslos angelegt
(`StaticRecompCore.cpp:215-225`; auf x86-64 ein vollständiger `Jit64`) und ist
nicht abschaltbar. Wenn also kein Zähler wächst, heißt das nicht „nichts
passiert", sondern: **JIT64 arbeitet**.

## Die Messung

Der Gast-Takt ist 486 MHz (`SystemTimers.cpp:233`). Im Vorspann entspricht ein
eindeutiges Bild einem Filmbild, und die Filme deklarieren 29,97 fps
([12-TON.md](12-TON.md)); daraus ergibt sich die emulierte Zeit und damit die
Gesamtzahl der Gasttakte.

| Lauf | Bilder | `native` | `bursts` | Takte im Modul | Anteil |
|---|---|---|---|---|---|
| `run-baked` (14.09., gebackenes DOL) | 1.827 | 300.540 | 4.619 | 53.716.081 | **0,1813 %** |
| `run-gecko` (14.09., Gecko-Codes) | 1.827 | 255.829 | 3.826 | 48.539.908 | 0,1638 % |
| `run-stack-long` (14.09.) | 30.002 | 62.291 | 937 | 11.335.889 | 0,0023 % |
| `run-arena` (14.09.) | 604 | 32.122 | 511 | 5.549.382 | 0,0567 % |
| `ton-static-3600` (15.09.) | 3.601 | 682 | 17 | 59.591 | 0,0002 % |
| `ton-szene-static` (15.09., Spielszene) | 4.202 | 682 | 17 | 59.594 | 0,0002 % |

37 Läufe insgesamt, keiner über 0,18 %.

Der Spitzenwert stammt ausgerechnet aus dem Lauf, auf den sich Befund 3 in
[10-KOPFLOSER-PRUEFSTAND.md](10-KOPFLOSER-PRUEFSTAND.md) stützt.

## Zwei Dinge, die nicht die Ursache sind

**Der Modulbau ist vollständig.** DolRecomp übersetzt im C-Backend nicht
erkannte Funktionen, sondern jedes Befehlswort jeder Textsektion, in festen
Kacheln zu 4.096 Befehlen (`pipeline.c:35,1524,1664-1681`). Nachgezählt am
gebauten Modul:

| Gegenstand | Wert |
|---|---|
| Codebereiche | 2 (`0x80003100–0x80005540`, `0x80005600–0x803730C0`) |
| Kacheln | 221 |
| abgedeckte Textbytes | 3.604.224 von 3.604.224 = **100,000 %** |
| Befehlswörter nativ | 899.042 von 901.056 = 99,78 % |
| eingebettete Daten (nur kommentiert) | 1.718 = 0,19 % |
| `ppc_fallback_instruction` | 296 = 0,03 %, ausschließlich Supervisor-Befehle (`mtsprg`, `mtibat`, `mfpvr`, `dcbi` …) |
| unbekannte Opcodes | 0 |
| gültige Einsprungpunkte | 901.056, also jede Befehlsadresse |

**Die Zeitbasis stimmt.** Ton und Bild laufen innerhalb von 0,3 % zur
deklarierten Filmrate ([12-TON.md](12-TON.md)).

## Der Mechanismus

`DispatchableAt` (`StaticRecompCore_SMC.cpp:246`) liefert nur dann wahr, wenn
alle vier Bedingungen gelten: keine erzwungene Rückfallzone, die Adresse liegt
in einer Kachel, die Kachel enthält **keine Host-Call-Adresse**, und die Kachel
ist verifiziert (FNV-1a-64 über den Gast-RAM gegen den im Modul gebackenen
Hash).

Der Modulbau deckt die `main.dol` vollständig ab — aber das Spiel führt auch
Code aus, der nie in der `main.dol` stand: Das GameCube-Betriebssystem
installiert seine Ausnahmebehandlung beim Start als Speicherinhalt
(`OSExceptionInit`), unterhalb der ersten Textsektion des DOL
(`0x80003100`). Jede Ausnahme — Systemaufruf, Dekrementierer, externer
Interrupt — springt dorthin und damit aus dem Modul heraus.

`Jit64::Run()` betritt anschließend den Dispatcher, der erst bei
`CPU::State != Running` zurückkehrt (`Jit.cpp:514`, `JitAsm.cpp:231`).

In den Läufen vom 15.09. stehen die Zähler schon nach **fünf Bildern** auf
682/17/59.600 und wachsen danach nicht mehr — auch nicht über 4.202 Bilder
bis in eine Spielszene hinein. Die native Ausführung findet also vollständig
vor dem ersten ausgegebenen Bild statt.

## Die Messung, die es entscheidet

`DispatchableAt` wurde lokal instrumentiert: Es zählt jeden Aufruf und den
Grund einer Ablehnung (`tools/diagnostics/staticrecomp-dispatch-probe.patch`,
rund 40 Zeilen, nur für die Messung). Ergebnis, dreimal identisch — über
5 und 3.000 Bilder, mit dem gewöhnlichen und mit dem Widescreen-Modul:

```
[sr-probe] dispatchable_at: total=18 ok=17 forced=0 nochunk=1
           hostcall=0 unverified=0 last_bad_pc=00000c00
```

Das ist der ganze Vorgang:

1. **18-mal** wird überhaupt gefragt, ob eine Adresse im Modul liegt.
2. **17-mal** lautet die Antwort ja; das sind die 17 Bursts mit 682 Blöcken.
3. **Einmal** lautet sie nein, und zwar bei `pc = 0x00000C00` — dem Vektor für
   `System Call`. Bei einer Ausnahme schaltet der Prozessor die
   Adressübersetzung ab, deshalb die reale statt der effektiven Adresse.
4. Danach wird **nie wieder gefragt**.

Weder Host-Calls (`hostcall=0`) noch fehlgeschlagene Kachelprüfungen
(`unverified=0`) spielen eine Rolle. Die Vermutung zu `host_call_active` aus
der ersten Fassung dieses Dokuments ist damit widerlegt.

Der Rückweg in den statischen Kern existiert:
`JitBaseBlockCache::Dispatch()` (`JitCache.cpp:232-240`) fragt vor jeder
Blocksuche `g_static_recomp_core->DispatchableAt(pc)` und kehrt dann mit
`nullptr` zurück. Erreicht wird er aber kaum: Der JIT verkettet seine Blöcke
direkt und ruft `Dispatch()` nur bei einem Fehlschlag der schnellen Suche.
Über 3.000 Bilder geschah das genau einmal.

## Der Lockstep-Verifizierer steht nicht zur Verfügung

[PLAN.md](PLAN.md), Abschnitt 2.5, benennt den in RecompCore vorhandenen
Lockstep-Verifizierer als das Mittel, um Recompilationsfehler von
Spielverhalten zu trennen. Mit dem gebauten Modul geht das nicht:

```
[lockstep] module lacks ppc_set_mem_write_journal export;
           lockstep DISABLED (rebuild the module).
```

`ppc_set_mem_write_journal` gibt es in DolRecomps Laufzeit (`src/cpu/cpu.c:14`,
`src/cpu/cpu.h:130`), aber das fertige Modul exportiert es nicht: `nm -D`
findet genau eine exportierte Funktion, und diese ist nicht dabei.
`StaticRecompLockstep.cpp:60` sucht sie über `GetSymbolAddress` und schaltet
sonst ab. Ein Modulbau dauert rund 70 Minuten
([09-DOL-BEFUNDE.md](09-DOL-BEFUNDE.md)); ein Lauf mit passend gebautem Modul
steht noch aus.

Solange das so bleibt, gibt es kein Mittel, die Richtigkeit nativ
ausgeführten Codes zu prüfen — auch nicht für die 682 Blöcke, die tatsächlich
laufen.

## Versuch: dem Modul die Gelegenheit zurückgeben

Wenn der Rückweg nur deshalb ungenutzt bleibt, weil der JIT seine Blocksuche
in Assembler erledigt, dann müsste das Modul wieder zum Zug kommen, sobald
jede Blocksuche über `JitBaseBlockCache::Dispatch()` läuft. Zwei Schalter,
lokal eingebaut (`tools/diagnostics/staticrecomp-cdispatch.patch`):

| Schalter | Wirkung |
|---|---|
| `STATICRECOMP_CDISPATCH=1` | `assembly_dispatcher = false`, jede Blocksuche über die C++-Fassung mit der Rückfrage |
| `STATICRECOMP_NO_BLOCKLINK=1` | der Ersatz-JIT verkettet seine Blöcke nicht |

Das Ergebnis ist nicht das erhoffte:

| Lauf | Zeit bis Bild 30 |
|---|---|
| gewöhnlich | 22 s |
| `STATICRECOMP_CDISPATCH=1` | **nach 1.447 s kein einziges Bild ausgegeben** |

Der Lauf musste hart beendet werden und hinterließ deshalb nicht einmal eine
Zählerzeile. Mindestens 65-mal langsamer, vermutlich weit mehr.

Naheliegende Erklärung, nicht isoliert nachgewiesen: `DispatchableAt` ist
nicht billig. Es ruft `RefreshHostCalls()` (Funktionszeiger in die
Mod-Verwaltung), schlägt den Kachelindex nach und prüft den Kachelzustand —
bei jeder einzelnen Blocksuche. Genau deshalb dürfte der Assembler-Weg
existieren.

Damit ist der Rückweg nicht bloß ungenutzt, sondern in dieser Form
**unbrauchbar**: An jeder Blockgrenze zu fragen kostet mehr, als die native
Ausführung einbringen könnte. Eine Lösung müsste die Frage billiger machen
(etwa eine Bitmaske je Kachel, im Assembler-Dispatcher geprüft) oder sie
seltener stellen (etwa nur beim Rücksprung aus einer Ausnahme).

## Warum der statische Kern langsamer ist

`SetStaticRecompFallback(true)` (`JitBase.h:207-217`) schaltet im Ersatz-JIT
**fastmem ab**:

```cpp
m_fastmem_enabled = false;
m_page_table_fastmem_enabled = false;
jo.fastmem = false;
jo.fastmem_arena = false;
```

Jeder Speicherzugriff des Gasts läuft damit über den langsamen Pfad. Das ist
dieselbe JIT-Maschine wie im Vergleichslauf, nur ohne ihre wichtigste
Optimierung — und erklärt den unten gemessenen Faktor 6,7, ohne dass er damit
vollständig aufgeklärt wäre (die Prüfungen je Block kommen hinzu).

## Was ungeklärt bleibt

Die Läufe vom 14.09. (`run-baked`, `run-gecko`) erreichen 300.540 bzw. 255.829
Dispatches, die vom 15.09. reproduzierbar 682 — bei **byte-gleichem Modul,
byte-gleichem DOL, unverändertem Runner, identischer Konfiguration und
demselben Spielstand**. Geprüft und ausgeschlossen: Modul-Prüfsumme,
DOL-Prüfsumme, Zeitstempel der Binärdateien, `Sys`-Verzeichnis,
`Dolphin.ini`, Mods, CPU-Merkmale. Sechs Wiederholungen derselben
Konfiguration ergaben sechsmal 682. Die Ursache des Unterschieds ist **nicht
gefunden**.

Für die Bewertung ändert das nichts: Auch der beste Lauf bleibt bei 0,18 %.
Der Mechanismus erklärt allerdings, wie beide Werte zustande kommen können:
Wie oft der statische Kern wieder zum Zug kommt, hängt daran, wie oft die
schnelle Blocksuche des JIT fehlschlägt. Alles, was den Blockspeicher des JIT
leert — Code nachladen, Speicherbereiche ungültig machen — schafft
Gelegenheiten. 4.619 Bursts gegen 17 sind derselbe Mechanismus bei
unterschiedlich häufigen Fehlschlägen.

## Nebenmessung: Geschwindigkeit

Ohne Drosselung (`[Core] EmulationSpeed=0`), gleicher Abschnitt, je zwei Läufe:

| Kern | Bildausgaben je Sekunde Wanduhr |
|---|---|
| JIT64 (`MODERNGEKKO_STATICRECOMP=0`) | 483,7 und 478,7 |
| statischer Kern mit Modul | 72,6 und 72,1 |

Der statische Kern ist **6,7-mal langsamer** als der reine JIT — obwohl in
beiden Fällen im Wesentlichen derselbe JIT die Arbeit macht. Der Unterschied
muss aus dem statischen Kern selbst kommen (`SetStaticRecompFallback(true)`,
Prüfungen je Block, SMC-Verifikation). Gemessen, nicht erklärt.

Gedrosselt (Voreinstellung 100 %) fällt das nicht auf: Beide Kerne erreichen
Echtzeit (0,97 gegen 1,00). Auf schwächerer Hardware oder bei höherer
Auflösung wäre der Abstand dagegen unmittelbar spürbar.

## Was daraus folgt

1. **Die Zeile `fallback=0` taugt nicht als Beleg für native Ausführung.**
   Wo sie bisher so gelesen wurde, muss die Aussage eingeschränkt werden;
   [10-KOPFLOSER-PRUEFSTAND.md](10-KOPFLOSER-PRUEFSTAND.md) ist entsprechend
   korrigiert. Ein belastbarer Beleg braucht `cycles` im Verhältnis zur
   emulierten Zeit.
2. **Der Widescreen-Befund aus WP8 bleibt gültig, aber enger.** Dass der
   eingebackene Code ohne SMC-Meldung läuft und die 25 Stellen im RAM
   stimmen, ist unabhängig davon belegt. Ob dieser Code im Modul oder im JIT
   ausgeführt wurde, ist damit **nicht** gezeigt.
3. **Für das Produkt ist das die zentrale offene Frage.** Ein „nativer
   Windows-Port" ist heute in der Ausführung ganz überwiegend Dolphins JIT.
   Ob das der beabsichtigte Zwischenstand von ModernGekko ist, ob eine
   Konfiguration fehlt oder ob ein Fehler vorliegt, muss vor WP2 geklärt
   werden — es entscheidet, was das Produkt überhaupt ist.

## Nächste Schritte

1. **Die Frage an ModernGekko richten.** Ausformuliert in
   [14-FRAGE-AN-MODERNGEKKO.md](14-FRAGE-AN-MODERNGEKKO.md), nicht
   abgeschickt — das entscheidet der Auftraggeber. Sie ist jetzt scharf: Der statische
   Kern verlässt das Modul beim ersten Systemaufruf und kommt nur zurück, wenn
   die schnelle Blocksuche des JIT fehlschlägt. Ist das der beabsichtigte
   Zwischenstand, oder fehlt ein Rückweg? `StaticRecompShouldYieldAt`
   (`StaticRecompCore.cpp:32`) ist definiert, wird aber in keinem der beiden
   Bäume aufgerufen — das sieht nach einer unfertigen Stelle aus.
2. **Prüfen, ob die Ausnahmevektoren mitrekompiliert werden können.** Sie
   entstehen erst zur Laufzeit; ein Modul kann sie nur abdecken, wenn der
   Recompiler die Vorlagen aus dem DOL erkennt und die installierten Kopien
   als dieselben Chunks führt.
3. **Fastmem im Ersatz-JIT bewerten.** Solange das Spiel ohnehin dort läuft,
   kostet die Abschaltung unmittelbar Leistung. Ob sie für die SMC-Prüfung
   nötig ist, steht nicht im Quelltext.
4. **Den Rückweg billig machen.** Der vorhandene Weg über
   `JitBaseBlockCache::Dispatch()` ist gemessen unbrauchbar (siehe oben). Eine
   Bitmaske je Kachel, die der Assembler-Dispatcher mit zwei Befehlen prüft,
   wäre der naheliegende Ansatz — das ist ein Vorschlag an ModernGekko, keine
   Aufgabe dieses Projekts.
