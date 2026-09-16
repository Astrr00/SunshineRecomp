# WP14 Schritt 5 — Vorbereitung Taktentkopplung

Stand: 2026-09-16. Aus dem Quelltext gelesen, nicht gemessen. Schritt 5
verlangt nach `docs/20`, Abschnitt "5. Taktentkopplung", dass der CPU-Faden
separat vom GPU-Faden läuft, sodass die Simulation vom Rendering entkoppelt
ist. Voraussetzung ist `m_separate_cpu_and_gpu_threads = true` (oder
historisch: `Config::MAIN_CPU_THREAD`). Der heutige Stand: dieser Schalter
existiert **nirgendwo als Setzer**.

## Der Befund: kein Setzer im Projektbaum

`docs/20` sagt: "im ganzen Projektbaum steht heute kein einziger Setzer
dafür". Diese Aussage wurde in dieser Sitzung am Quelltext nachgeprüft — und
sie stimmt, mit einer Verschärfung: das Symbol, das der einzige historische
Aufrufer verwendet, existiert **gar nicht** im Projekt.

`grep -rn "MAIN_CPU_THREAD" src/ tools/ include/ vendor/`:

| Datei | Zeile | Inhalt |
|---|---|---|
| `tools/netplay_session.cpp` | 526 | `Config::SetBase(Config::MAIN_CPU_THREAD, true);` |

Das ist der einzige Treffer im Projekt. Die Variable `Config::MAIN_CPU_THREAD`
ist **nirgendwo** definiert — weder in `vendor/dolphin/Source/Core/Common/Config/Config.h`,
noch in `ConfigInfo.cpp`, noch in einem moderngekko-eigenen Header. Der
Netplay-Code kompiliert nur, weil `netplay_session.cpp` nicht zum
`moderngekko-run`-Target gehört — er würde beim Netplay-Build einen
Linker-Fehler geben.

Der einzige **Leseort** ist in `vendor/dolphin/Source/Core/Core/System.cpp:119`:

```cpp
m_separate_cpu_and_gpu_threads = Config::Get(Config::MAIN_CPU_THREAD);
```

und `vendor/dolphin/Source/Core/Core/System.h:212`:

```cpp
bool m_separate_cpu_and_gpu_threads = false;
```

mit `IsDualCoreMode()` als Getter (Zeile 143):

```cpp
bool IsDualCoreMode() const { return m_separate_cpu_and_gpu_threads; }
```

Damit ist klar: das Lesen funktioniert, das Setzen ist nirgends. Das ist die
Lücke, die `docs/20` meint.

## Wie der heutige Faden läuft

`src/runtime/dolphin_runtime.cpp:814-889` ist `Runtime::Run()`. Die Struktur
ist:

```cpp
Runtime::Run() {
  // ... Boot-Parameter aufbauen ...
  BootManager::BootCore(...);
  // ... Hooks für Automation und FPS-Anzeige registrieren ...
  std::jthread title_thread;        // FPS-Anzeige
  std::jthread automation_thread;   // Eingaben
  m_impl->platform->MainLoop();     // <-- hier läuft die ganze Emulation
  // ... aufräumen ...
}
```

**`MainLoop()` ist die einzige Schleife.** Sie treibt CPU und GPU
sequentiell auf einem Faden. Das ist der Default in Dolphin-Emulator seit
Jahren — die Trennung in zwei Fäden ist eine **Optimierung**, kein
Korrektheits-Feature.

## Was Schritt 5 voraussetzt

Vier Dinge sind nötig, in dieser Reihenfolge:

### 1. Den Setzer einführen

In `Runtime::Run()`, vor `BootManager::BootCore()`, ein:

```cpp
Config::SetBase(Config::MAIN_CPU_THREAD, true);
```

(oder direkter Zugriff auf `system.SetSeparateCPUAndGPUThreads(true)`, falls
es einen Setter gibt — der wurde in dieser Sitzung nicht gefunden).

**Voraussetzung dafür:** das Symbol `Config::MAIN_CPU_THREAD` muss definiert
werden. Es ist ein alter Dolphin-Config-Key; die Quelle ist im
`vendor/dolphin_legacy/`-Baum oder in einem historischen Branch. Wenn der
Key reaktiviert wird, braucht es einen Eintrag in `Config.cpp`/`Config.h`
oder einem der `*.def`-Dateien.

### 2. Den CPU-Faden tatsächlich starten

Heute macht `MainLoop()` beides: CPU-Takte verbuchen und GPU rendern. Im
Dualcore-Modus müsste `MainLoop()` nur das Rendering machen, und der
CPU-Faden — in `vendor/dolphin/Source/Core/Core/CPU.cpp` oder einer der
`Host_*`-Funktionen — läuft in einer eigenen Schleife. Konkret: der
FifoPlayer / `Fifo::RunLoop` oder `CPU::Run` wird in einem `std::jthread`
gestartet.

Dolphins historische Implementierung hat das in `Core::CPUThread` (siehe
`vendor/dolphin_legacy/Core/Core.cpp`). Im neuen `vendor/dolphin`-Baum ist
die entsprechende Logik möglicherweise in `Core::System::GetInstance().Run()`
oder `BootManager::BootCore(...)` mit anschließendem `Core::CPUThread`-Start.

### 3. Synchronisation herstellen

Wenn CPU und GPU auf zwei Fäden laufen, müssen sie synchronisiert werden.
Dafür gibt es `Core::CPUThreadGuard` — ein RAII-Wrapper, der die richtige
Speicher-Reihenfolge erzwingt. Im neuen Dolphin-Chassis wird das
wahrscheinlich über atomare Variablen und Mutexe gemacht; im alten über
`Common::Event` und Spinlocks.

Die Synchronisation muss mindestens diese drei Stellen abdecken:

- **Befehlsstrom**: Wenn die CPU einen BP-Befehl (z.B. `BPMEM_TRIGGER_EFB_COPY`)
  schreibt, muss die GPU das mitbekommen, **bevor** sie ihre EFB-Kopie macht.
  Heute ist das trivial, weil CPU und GPU auf demselben Faden laufen.
- **XFB**: Die XFB-Kopie läuft auf der GPU, der Lesezugriff durch den Gast
  läuft auf der CPU. Im Dualcore muss die GPU dem Gast **signalisieren**,
  dass die Kopie fertig ist, **bevor** der Gast liest.
- **Gast-RAM**: Schreibzugriffe der CPU müssen vor Lesezugriffen der GPU
  sichtbar sein und umgekehrt. Dolphin hat dafür ein Memory-Coherency-
  Protokoll; ob es auf modernen CPUs ohne `dcbf` auskommt, ist eine offene
  Frage (siehe `recompcore-dcbf-bleibt-im-modul.patch`, der genau dieses
  Problem vermeidet, indem er `dcbf` im Modul hält).

### 4. Sicherheit gegen Race Conditions

Dolphins JIT hatte ein **Invalidierungssystem**: wenn die CPU einen
`icbi`-Befehl ausführt (instruction cache block invalidate), wird der JIT
informiert, dass der entsprechende Block neu übersetzt werden muss. Im
statischen Kern passiert das **nicht** (es gibt keinen JIT), aber die
Sperre selbst wird weiterhin gesetzt, weil `icbi` ein SMC-Indikator ist.

Im Dualcore-Modus muss diese Sperre **atomar** zwischen den Fäden
funktionieren. Der Patch `recompcore-rueckweg.patch` hat den Rückweg
schon so gebaut, dass er die Sperre nicht selbst braucht; aber der
statische Kern mit Rückweg **bricht** im Dualcore-Modus, wenn die Sperre
nicht zwischen Fäden serialisiert ist. **Belegt ist das nicht** — es ist
eine Hypothese, die aus dem Code-Sicht plausibel ist.

## Was das für WP14 Schritt 5 konkret heißt

Drei Arbeitspakete, jedes mit eigener Belegbarkeit:

### A. Setzer wieder einführen

Klein: ein 5-Zeilen-Patch in `src/runtime/dolphin_runtime.cpp` und ein
`Config::MAIN_CPU_THREAD`-Eintrag in `vendor/dolphin/Source/Core/Common/Config/Config.cpp`.
**Belegt durch:** das Modul lässt sich mit dem Schalter laden, die
`IsDualCoreMode()`-Abfrage liefert `true`.

### B. CPU-Faden starten

Größer: ~50 Zeilen in `Runtime::Run()` oder einem neuen
`CpuThread::Start()`. Synchronisation über `CPUThreadGuard`. **Belegt
durch:** zwei identische Läufe, einfädig und zweifädig, müssen im
Tonvergleich **abtastwertgleich** sein (siehe `docs/20`, Vorprüfung 1
"Tonvergleich").

Diese Vorprüfung ist schon erledigt — der Vergleich steht in
`docs/20`, Abschnitt "Was vorab zu prüfen war":

| Gegenstand | einfädig | zweifädig |
|---|---|---|
| `native` | 192.014.501 | 192.024.166 |
| `cycles` | 1.441.772.981 | 1.442.041.571 |
| `smc_failed`, `fallback` | 0, 0 | 0, 0 |
| Tonvergleich | abtastwertgleich 100,0 % | abtastwertgleich 100,0 % |

**Aber:** dieser Vergleich wurde mit dem Rückweg **ohne** explizites
`MAIN_CPU_THREAD = true` gefahren. Es ist plausibel, dass die
Synchronisation schon jetzt funktioniert, weil CPU und GPU auf demselben
Faden laufen und der Rückweg nur einen einzigen Faden kennt. Eine **echte**
Dualcore-Trennung ist es nicht.

### C. Geschwindigkeit messen

Das ist Schritt 6, nicht Schritt 5. Wenn B funktioniert, ist Schritt 5
abgeschlossen; Schritt 6 misst die echte GPU-Geschwindigkeit.

## Was diese Sitzung nicht konnte

- **`Runtime::Run()` mit Dualcore fahren** — ModernGekko baute in dieser
  Sandbox nicht (`dolphin_runtime.cpp`-Build-Fehler wegen C++23
  `std::jthread`/`std::ranges::contains`, nicht in libstdc++-12/libc++-19
  verfügbar, GCC 14 nicht installierbar). Der Schritt 5 müsste **nach**
  der Build-Reparatur erfolgen.
- **Den `Config::MAIN_CPU_THREAD`-Eintrag schreiben** — setzt voraus, dass
  die Symbol-Definition aus der Dolphin-Historie reaktiviert wird. Das ist
  ein Vendor-Patch und bricht die Bootstrap-Reihenfolge.
- **Synchronisation validieren** — erfordert einen laufenden Build.

## Empfehlung

Schritt 5 ist **kein** Patch, der in 30 Minuten fertig wird. Es ist eine
substantielle Architekturänderung mit drei Teilen (Setzer, Faden-Start,
Synchronisation), und der dritte Teil ist der riskanteste, weil er
möglicherweise den Lockstep-Verifizierer aufdeckt.

**Wer das angeht**, sollte:

1. Erst `Config::MAIN_CPU_THREAD` reaktivieren und das Modul weiterhin
   laden (Schritt A). Das ist ein 5-Zeilen-Patch mit minimalem Risiko.
2. Dann den CPU-Faden in einer **zweiten** `Runtime::Run`-Variante
   (`Runtime::RunDualCore()` oder per `Config::MAIN_CPU_THREAD`-Schalter
   bedingt) starten (Schritt B). Das ist 50 Zeilen mit klarem Plan.
3. Dann die Synchronisation mit dem Lockstep-Verifizierer prüfen. Das ist
   der teuerste Teil — wenn er 19 Meldungen über die ganze Eingabefolge
   zeigt (Stand aus `docs/20`), ist Schritt 5 abgeschlossen; wenn er mehr
   zeigt, ist der Rückweg in einer Race-Condition und braucht eine
   zweite Schutzschicht.
