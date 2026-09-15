# Wie viel vom Spiel läuft wirklich aus dem Rekompilat?

Stand: 2026-09-15. Entstanden als Nebenbefund der Tonmessung
([12-TON.md](12-TON.md)) und hier getrennt aufgeschrieben, weil die Frage den
Kern des Vorhabens betrifft.

**Kurz:** In keinem der 37 aufgezeichneten Läufe hat das rekompilierte Modul
mehr als **0,18 %** der Gasttakte ausgeführt. Der Rest lief in Dolphins
JIT64, der im statischen Kern als Ersatz mitläuft. Die Zeile
`native=… fallback=0` belegt das Gegenteil nicht: `fallback` zählt nur
Interpreter-Einzelschritte, nicht den Ersatz-JIT.

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

Zwei Eigenheiten fallen dabei auf:

1. **Host-Calls gelten immer als aktiv.** `dolphin_runtime.cpp:749` setzt
   `recomp_source.host_call = &ModManager::HostCall` bedingungslos, und
   `host_call_active` wird nirgends zugewiesen; `RefreshHostCalls`
   (`SMC.cpp:327-330`) nimmt dann den Vorgabewert `true`. Eine einzige gehookte
   Adresse sperrt damit eine ganze Kachel von 16 KB.
2. **Der Weg zurück ist schmal.** `Jit64::Run()` betritt den Dispatcher, der
   erst bei `CPU::State != Running` zurückkehrt (`Jit.cpp:514`,
   `JitAsm.cpp:231`). Es gibt eine Rückgabeprüfung in
   `JitBaseBlockCache::Dispatch()` (`JitCache.cpp:232-240`), aber
   `StaticRecompShouldYieldAt` (`StaticRecompCore.cpp:32`) wird in beiden
   Bäumen nirgends aufgerufen.

In den Läufen vom 15.09. stehen die Zähler schon nach **fünf Bildern** auf
682/17/59.600 und wachsen danach nicht mehr — auch nicht über 4.202 Bilder
bis in eine Spielszene hinein. Die native Ausführung findet also vollständig
vor dem ersten ausgegebenen Bild statt.

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

1. Den Verdacht zu den Host-Calls prüfen: Ein Lauf mit einer Fassung, in der
   `host_call_active` einen Wert bekommt, der ohne Mods `false` ergibt, zeigt
   unmittelbar, ob die Kachelsperre die Ursache ist.
2. Den Lockstep-Verifizierer (`STATICRECOMP_LOCKSTEP`) auf einem kurzen
   Abschnitt laufen lassen; er meldet, welche Adressen nativ ausgeführt
   werden.
3. Die Frage an ModernGekko selbst richten, sobald sie sauber formuliert ist:
   Welcher Anteil nativer Ausführung ist bei diesem Stand zu erwarten?
