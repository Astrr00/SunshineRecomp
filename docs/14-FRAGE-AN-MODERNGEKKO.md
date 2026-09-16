# Frage an ModernGekko: Welcher Anteil nativer Ausführung ist vorgesehen?

Stand: 2026-09-15. Vorbereitet, nicht abgeschickt. Die Messungen stehen in
[13-STATISCHER-KERN.md](13-STATISCHER-KERN.md).

> **Am selben Tag überholt.** Die Fragen 1 bis 3 und 5 sind inzwischen selbst
> beantwortet, drei davon mit einem Patch:
>
> | Frage | Antwort |
> |---|---|
> | 1–3, Rückweg | Er fehlte. `patches/recompcore-rueckweg.patch` stellt ihn an den Ausnahme-Ausgängen her; der Anteil des Ersatz-JIT fällt von 99,99 % auf 0,015 % ([16](16-RUECKWEG.md)) |
> | 5, `ppc_set_mem_write_journal` | Das Versionsskript `module.exports` setzt alles außer `staticrecomp_get_module` auf `local`; ThinLTO entfernt daraufhin die Journal-Aufrufe. Ein Neulink mit ergänztem Skript genügt ([17](17-LOCKSTEP.md)) |
> | 4, `StaticRecompShouldYieldAt` | weiterhin offen; wir haben sie bewusst **nicht** verwendet, weil sie zusätzlich für Host-Call-Adressen wahr liefert und einen Einmal-Zustand verbraucht — das Prädikat passt nicht zum Tor in `StaticRecompCore_Run.cpp` |
>
> Dafür sind zwei neue Fragen entstanden, die wir nicht selbst beantworten
> können:
>
> 6. **Ist der beschriebene Rückweg der beabsichtigte Weg?** Wir setzen den
>    Test an die Ausgänge von `rfi` und Ausnahme, nicht in den Dispatcher —
>    weil 99,92 % der Rücksprungziele im Modulbereich liegen und der Dispatcher
>    danach ohnehin fast nicht mehr durchlaufen wird.
> 7. **Verbucht das Modul zu wenig Takte?** Auf einem Block mit 29 Befehlen je
>    Schleifenrunde verbucht es rund 26. Der Lockstep-Verifizierer kann eine
>    Schleife deshalb nicht exakt anhalten. Sollte die Modul-Schnittstelle die
>    Zahl ausgeführter Befehle melden, nicht nur die verbuchten Takte?

Diese Frage entscheidet, was der Port ist, und blockiert WP2
([PLAN.md](PLAN.md)). Sie geht an das Projekt, dessen Laufzeit wir verwenden,
nicht an ein Forum: Sie ist eine sachliche Rückfrage zum Entwurf, keine
Fehlermeldung.

## Was wir wissen wollen

1. Ist es der vorgesehene Zustand, dass der statische Kern das Modul beim
   ersten Ausnahmesprung verlässt und praktisch nicht zurückkehrt?
2. Falls nein: Welche Konfiguration fehlt uns?
3. Falls ja: Ist ein billiger Rückweg geplant, und wäre eine Bitmaske je
   Kachel im Assembler-Dispatcher der richtige Ansatz?
4. `StaticRecompShouldYieldAt` ist definiert, wird aber nirgends aufgerufen.
   Ist das eine unfertige Stelle?
5. Soll das Modul `ppc_set_mem_write_journal` exportieren? Ohne diesen Export
   schaltet der Lockstep-Verifizierer ab.

## Was wir vorher geprüft haben

Damit die Frage nicht das Offensichtliche abfragt:

- Der Modulbau ist vollständig: 221 Kacheln, 3.604.224 von 3.604.224
  Textbytes, jede Befehlsadresse ein Einsprungpunkt.
- Modul, DOL, Runner und Konfiguration sind zwischen den Läufen bytegleich.
- Sechs Wiederholungen derselben Konfiguration ergeben denselben Wert.
- Weder Host-Calls noch fehlgeschlagene Kachelprüfungen sind beteiligt
  (`hostcall=0`, `unverified=0`).

## Text zum Abschicken

Englisch, weil das Projekt englisch geführt wird. Vor dem Abschicken prüfen,
ob die Zeilennummern noch zu dem Commit passen, auf den wir angeheftet sind
(`c6a600eb`).

---

**Subject: Expected share of native execution — static core leaves the module at the first exception**

Hello,

we are building a native Windows port of Super Mario Sunshine (GMSE01) on
DolRecomp plus ModernGekko, and we have measured something we would like to
understand before we build further on it. This is a question about intent,
not a bug report.

**Measurement.** Across 37 headless runs of the same game, the recompiled
module executes at most **0.18 %** of the guest cycles; typical runs are at
0.0002 %. Everything else runs in the fallback `Jit64`. We compute the share
as `m_charged_cycles` divided by emulated seconds times 486 MHz, where
emulated seconds come from the game's own intro movie, which declares
29.97 fps in its THP header and advances `PresentInfo::frame_count` at
exactly that rate.

**What we ruled out.** The build is complete: 221 chunks covering
3,604,224 of 3,604,224 text bytes, every instruction address a valid entry
point, 296 supervisor instructions on `ppc_fallback_instruction`, zero
unknown opcodes. Module, DOL, runner binary and configuration are byte
identical between runs, and six repetitions give the same counters.

**What we found.** We instrumented `StaticRecompCore::DispatchableAt` to
count calls and refusal reasons. Over a 3,000-frame run it is called
**18 times**: 17 times it returns true (17 bursts, 682 dispatches, all during
boot), once it returns false at `pc = 0x00000C00` — the System Call
exception vector. After that it is never asked again.

That address is never in any module: the OS installs its exception handlers
into RAM at boot, below the DOL's first text section at `0x80003100`. So the
first `sc` leaves the covered range, control passes to
`m_fallback_jit->Run()` (`StaticRecompCore_Run.cpp:216-218`), and `Jit64`'s
dispatcher only returns when the CPU state leaves `Running`.

There is a return path in `JitBaseBlockCache::Dispatch()`
(`JitCache.cpp:232-240`), but the generated dispatcher handles hits in
assembly (`JitAsm.cpp:109-111`, `assembly_dispatcher = true`) and only calls
the C++ function on a lookup miss. Over 3,000 frames that happened once.

**What we tried.** Forcing every lookup through the C++ path
(`assembly_dispatcher = false`) did make the static core reachable again, but
the emulator then did not present a single frame in 1,447 seconds, against
22 seconds normally. Our guess, not isolated: `DispatchableAt` calls
`RefreshHostCalls()`, looks up the chunk index and checks chunk state on
every block lookup.

**Questions.**

1. Is the observed behaviour the intended state at this stage — the module
   carries early boot, the JIT carries the rest?
2. If not, which configuration are we missing?
3. If yes, is a cheap re-entry planned? A per-chunk bitmap the assembly
   dispatcher could test in two instructions seems the obvious shape, but you
   will know the constraints.
4. `StaticRecompShouldYieldAt` (`StaticRecompCore.cpp:32`) is defined and
   declared but never called in either tree. Is that an unfinished hook?
5. Should a module built by `moderngekko-port build --backend c` export
   `ppc_set_mem_write_journal`? Ours does not, and
   `StaticRecompLockstep.cpp:60` therefore disables the lockstep verifier —
   which leaves us without a way to check native execution for correctness.

We are happy to share the instrumentation patches (about 40 and 45 lines) and
the run manifests. We cannot share the game data.

Thank you,
Astrr00

---

## Nach der Antwort

Je nach Antwort:

- **Vorgesehener Zustand.** Dann ist „nativer Port" für dieses Vorhaben neu
  zu fassen, und PLAN 0.1 („Spiellogik (CPU) nativ") braucht eine Korrektur.
  Der Auftraggeber muss das wissen, bevor WP2 Aufwand bindet.
- **Konfiguration fehlt.** Dann messen wir erneut und schreiben Dokument 13
  fort.
- **Unfertig.** Dann ist zu klären, ob wir warten, selbst beitragen oder den
  Umfang anpassen.
