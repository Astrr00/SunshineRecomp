# Der Lockstep-Verifizierer: freigeschaltet und erstmals gelaufen

Stand: 2026-09-15. Folgt auf [16-RUECKWEG.md](16-RUECKWEG.md). Dort wurde der
Rückweg in den statischen Kern gebaut; dieses Dokument beantwortet die Frage,
die damit sofort dringend wurde: **Rechnet der nativ ausgeführte Code richtig?**

**Kurz:** Der Verifizierer ist freigeschaltet und läuft. Er meldet
Abweichungen — 3,4 % der geprüften Blöcke. Die Gegenprobe zeigt: **Sie kommen
nicht vom Rückweg.** Ohne ihn ist die Rate dieselbe, und es sind dieselben
Blöcke. Ob es Recompilationsfehler oder Artefakte des Verifizierers sind, ist
**offen** und der nächste Schritt.

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

## Was daraus noch nicht folgt

Ob die 3,4 % Recompilationsfehler sind, ist **nicht** entschieden. Es gibt
Anhaltspunkte in beide Richtungen, und beide sind Beobachtungen, keine Belege:

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

Eine einzelne Meldung bis zum Grund verfolgen, mit den Mitteln, die der
Verifizierer schon mitbringt: `STATICRECOMP_LOCKSTEP_TRACE=<pc>` gibt die
Einzelschritte aus, `STATICRECOMP_LOCKSTEP_FILTER` und `_WHITELIST` engen ein.
Erst wenn für eine Adresse feststeht, ob Modul oder Nachbildung recht hat,
lässt sich über die anderen 115 etwas sagen.

**Bis dahin bleibt der Rückweg ausdrücklich zu schalten und nicht
Voreinstellung.** Diese Bedingung aus Dokument 16 ist nicht erfüllt: Der
Verifizierer ist zwar verfügbar, aber sein Urteil ist noch nicht lesbar.

## Grenzen

- Ein Lauf über 30 Bilder. Später Spielverlauf ist nicht geprüft.
- Nur Linux, nur Jit64, nur dieses eine Modul.
- Das Prüfmodul ist nicht bitgleich mit dem ausgelieferten: Es trägt die
  Journal-Aufrufe, die der Optimierer sonst entfernt. Streng genommen prüft
  der Verifizierer damit ein anderes Binärbild als das, das ausgeliefert wird.
  Der übersetzte Spielcode ist derselbe; belegt ist das nicht.
