# WP14 Schritt 4 — Code-Audit (bildliche Prüfung steht aus)

Stand: 2026-09-16. Gelesen aus `patches/recompcore-gx-trockenlauf.patch` und der
umgebenden Quelle in `ref/ModernGekko/vendor/dolphin/`. Keine Messung, keine
Aussage über Korrektheit zur Laufzeit — nur eine Source-Sicht darauf, was der
Patch tut und was beim nächsten Lauf bildlich zu prüfen ist.

## Was Schritt 4 im Patch tut

Schritt 4 wird mit der Umgebungsvariable `MODERNGEKKO_GX_DRYRUN_PRESENT=1`
aktiviert, **zusätzlich** zu `MODERNGEKKO_GX_DRYRUN=3` (Matrixinterpolation aus
Schritt 3). Der Patch setzt das Bit in `Initialize` (Zeile 741-742):

```cpp
const char* present = std::getenv("MODERNGEKKO_GX_DRYRUN_PRESENT");
g_present_mid = g_interpolate && present && present[0] == '1';
```

Damit wird `g_present_mid` nur dann wahr, wenn **gleichzeitig** `g_interpolate`
wahr ist. Wer `MODERNGEKKO_GX_DRYRUN_PRESENT=1` ohne Stufe 3 setzt, bekommt
ein Zwischenbild, das es gar nicht gibt — also nichts. Das ist eine sinnvolle
Sperre, kein Bug.

## Der Mechanismus

`PresentOverride` (Zeile 568-577) liefert den Schatten-EFB als `AbstractTexture*`
und setzt die Quell-Rechtecke:

```cpp
const AbstractTexture* PresentOverride(MathUtil::Rectangle<int>* source_rc)
{
  if (!s_mid_ready || !g_framebuffer_manager)
    return nullptr;
  const AbstractTexture* mid = g_framebuffer_manager->GetShadowColorTexture();
  if (!mid)
    return nullptr;
  *source_rc = s_mid_src_rect;
  return mid;
}
```

Zwei Aufrufer gibt es, beide im selben Patch: einer ersetzt das Bild des
FrameDumpers (`OpcodeDecoding.cpp`-Aufruf, Zeile 909-911), der andere das Bild
der echten Präsentation (`Present.cpp`-Aufruf, Zeile 921-923). Beide Pfade
bekommen dasselbe `mid` und dieselbe Quelle — das ist genau, was der Auftrag
verlangt: FrameDumper und Schirm sehen im Ersatz dasselbe Bild.

Der Zustand `s_mid_ready` wird in `SecondPass` (Zeile 628-733) gesetzt, und
zwar am Ende der Routine, **bevor** `SwapOutShadow` läuft (Zeile 713-721):

```cpp
if (g_present_mid && interpolate_this && !duplicate && previous_duplicate)
{
  s_mid_ready = true;
  s_mid_src_rect = s_frame_src_rect;
  ++s_presented_mid;
}
```

Vier Bedingungen zusammen:

| Bedingung | Bedeutung |
|---|---|
| `g_present_mid` | Stufe 4 aktiv |
| `interpolate_this` | Schritt 3 hat mehr als 60 % der Zeichenbefehle zugeordnet — kein Schnitt |
| `!duplicate` | die **anstehende** Präsentation bringt ein neues Bild |
| `previous_duplicate` | die **vorherige** Präsentation war eine Wiederholung |

Das ist genau das Muster, das `docs/20` beschreibt: das Spiel läuft mit 30 Hz,
jedes Bild wird zweimal präsentiert, und zwischen die Wiederholung und das
echte Bild wird das Zwischenbild geschoben. Logik im Code stimmt mit der
Beschreibung überein.

## Was an der bildlichen Prüfung aussteht

`docs/20` nennt den Befehl:

```bash
xvfb-run -a -s "-screen 0 1280x720x24" python3 tools/diagnostics/headless_probe.py \
  --runtime <run> --game <imported> --module <so> --output <dir> --frames 1 \
  --sequence tools/acceptance/fixtures/game-start.json \
  --graphics Vulkan --x11 \
  --core-setting "$(printf 'GXDryRunMarker=1\n[Interface]\nUsePanicHandlers=False')"
```

plus `--gfx-setting DumpFrames=True --gfx-setting DumpFramesAsImages=True` für
PNG je Präsentation. **Vier Erwartungen**, die am Code stehen und am Bild zu
prüfen sind:

1. **Ohne Stufe 4 sind aufeinanderfolgende Präsentationen bitgleich.** Der
   Schatten wird zwar gezeichnet (Stufe 3), aber `g_present_mid` ist falsch,
   `s_mid_ready` bleibt falsch, `PresentOverride` liefert `nullptr`, der
   `if`-Zweig greift nicht. Das Bild sollte dem EFB entsprechen.

2. **Mit Stufe 4 ist jede zweite Präsentation ersetzt.** `info.reason ==
   PresentInfo::PresentReason::VideoInterfaceDuplicate` ist die Bedingung in
   `SecondPass` für `duplicate`. Bei 30 Hz ist das genau jede zweite
   Präsentation. Die Zähler in `docs/20` (5.047 von 5.189 Wiederholungen
   ersetzt; 142 Wiederholungen ohne Ersatz) decken sich mit dieser Erwartung
   bis auf die 142 — die wären zu prüfen.

3. **Das ersetzte Bild liegt zwischen seinen Nachbarn.** `tools/framerate
   compare A mid B` mit A = vorherige echte Präsentation, B = nächste echte
   Präsentation, mid = die ersetzte. Erwartung: 75–80 % der Pixel im
   Intervall, wie in `docs/20` für Schritt 3 dokumentiert. **Achtung:** das
   gilt nur, wenn die Wiederholungs-Wiederholung selbst der "A" ist. Wenn A
   eine Wiederholung ist und B ein echtes Bild, ist A == B (keine Bewegung)
   und das mid dazwischen — die Erwartung wechselt.

4. **Das echte Bild erscheint eine Präsentation später.** Vor Stufe 4 wurde
   Bild N einmal gezeigt; mit Stufe 4 wird Bild N-1 zweimal gezeigt
   (Original-Wiederholung + mid), Bild N einmal (echte Präsentation), Bild N+1
   zweimal. Das ist eine Verschiebung um eine Präsentation — der
   FrameDumper-Index läuft mit dieser Verschiebung weiter, aber das **Bild**
   wechselt später als die Zählung suggeriert. Für einen Test, der Frame N
   mit Frame N+1 vergleicht, ist das eine zusätzliche Verzögerung.

## Was am Code selbst noch zu prüfen ist

Drei Stellen, die der Patch setzt, sind nicht offensichtlich richtig oder
brauchen einen weiteren Beleg:

### 1. `s_frame_src_rect` wird nur in `OnFrameEnd` gesetzt

Der Block in `OnFrameEnd` (Zeile 599-625) baut das Rechteck aus den
XFB-Kopierkoordinaten der letzten Kopie:

```cpp
s_frame_src_rect = MathUtil::Rectangle<int>(
    bpmem.copyTexSrcXY.x, bpmem.copyTexSrcXY.y, bpmem.copyTexSrcXY.x + bpmem.copyTexSrcWH.x + 1,
    bpmem.copyTexSrcXY.y + bpmem.copyTexSrcWH.y + 1);
```

Diese Koordinaten werden **einmal** je Bild gespeichert, dann in
`PresentOverride` an den Aufrufer weitergereicht. Wenn `PresentOverride` für
eine andere XFB-Kopie aufgerufen wird (EFB-Kopie mitten im Bild), bleibt das
Rechteck vom **vorigen** Bild — und der Schirm zeigt dann einen
falsch-positionierten Ausschnitt. Die Wahrscheinlichkeit, dass `mid` zwischen
zwei Bildern für die "falsche" Kopie geliefert wird, ist gering, weil die
genaue Reihenfolge `OnFrameEnd → SecondPass` ist und das Rechteck zum Bild
passt. **Belegt ist das nicht** — die bildliche Prüfung muss einen
Mitschnitt zeigen, bei dem `efb_<n>.png` und `schatten_<n>.png` an
verschiedenen Stellen gerendert werden (Ultrawide, HUD-Effekte).

### 2. `SwapInShadow` und `SwapOutShadow` umschließen den zweiten Durchlauf

`SecondPass` schaltet den Schatten ein (Zeile 660), zeichnet (Zeile 686), und
schaltet ihn wieder aus (Zeile 713). Dazwischen liegt der `Apply(s_end)` der
Endzustand-Wiederherstellung (Zeile 723) — das bedeutet, der Schatten wird
vor der Zustandswiederherstellung ausgetauscht. Richtig so: der EFB für die
nächste echte Präsentation muss der **echte** EFB sein, nicht der Schatten.
Der Schatten wird geleert (über den Constructor des Schatten-EFB in
`FramebufferManager.cpp:238-248`, in `docs/20` erwähnt).

Was hier offen ist: Werden beim Austausch wirklich alle Nutzer des EFB
umgehängt? `docs/20` sagt "jeder Nutzer des EFB … landet dadurch ohne eigene
Änderung im Schatten". Das ist eine starke Behauptung über den Code, die ich
am `FramebufferManager` prüfen würde — nicht im Patch, sondern im RecompCore-
Quelltext `Source/Core/VideoCommon/FramebufferManager.cpp:238-248`. Das habe
ich in dieser Sitzung nicht getan; es ist der nächste Schritt.

### 3. `g_active = true; … g_active = false;` umgibt den zweiten Lauf

`g_active` ist das, was `BPWritten` als Sperre für die elf BP-Register liest
(siehe `docs/20`, Abschnitt "Was ein zweiter Durchlauf sperren muss"). Im
**ersten** Durchlauf ist `g_active` falsch; im **zweiten** wahr. Die Zählung
in `docs/20` (25.808 gesperrte Schreibvorgänge über 2.403 Bilder) zeigt, dass
die Sperre greift — ohne Sperre würden diese Schreibvorgänge durchgehen und
den Gastzustand ändern.

Belegt ist, **dass** sie greift. Nicht belegt ist, **was passiert wäre** ohne
Sperre — die Schritt-1-Messung in `docs/20` zählte 25.808 gesperrte
Schreibvorgänge über die ganze Eingabefolge, aber kein Vergleichslauf ohne
Sperre wurde gemessen. Wenn die Sperre fehlt, würde Schritt 4 (oder Schritt 3)
mit hoher Wahrscheinlichkeit **andere** Bilder zeigen als ohne, und der
Gastzustand — insbesondere die Bounding Box und die PE-Token-Interrupts —
würde kippen. Das ist eine Plausibilitätsaussage, kein Beleg.

## Was die bildliche Prüfung können muss

Vier Fälle, am Code orientiert. Die Reihenfolge entspricht der Reihenfolge,
in der sie im `headless_probe`-Lauf auftreten sollten:

| Fall | Eingabe | Erwartung am Bild |
|---|---|---|
| ohne Stufe 4 | `--gfx-setting DumpFrames=True` | Präsentation N und N+1 sind **gleich** (beide zeigen den EFB desselben Bildes, weil SkipDuplicateXFBs=true ohnehin an ist) — Wait: SkipDuplicate ist default an? `docs/20` sagt "der vorhandene Duplikatpfad, der heute nur durch `SkipDuplicateXFBs = true` abgeschaltet ist". Das ist Default true. Also zeigen aufeinanderfolgende Präsentationen dasselbe Bild. |
| mit Stufe 4, Bildwechsel | erste Präsentation eines neuen Bildes nach einer Wiederholung | mid-Bild sichtbar, liegt **zwischen** A (vorige Wiederholung) und B (echtes Bild) |
| mit Stufe 4, kein Bildwechsel | zwei Wiederholungen in Folge (kommt bei 30 Hz nicht vor, aber theoretisch) | mid wird **nicht** gezeigt — Bedingung `interpolate_this && !duplicate && previous_duplicate` schlägt fehl, `s_mid_ready` bleibt falsch |
| mit Stufe 4, Schnitt | Bild mit erkanntem Schnitt | mid wird **nicht** gezeigt — Bedingung `interpolate_this` schlägt fehl (`matched * 10 < larger * 6`) |

Fall 1 ist der Kontrolllauf: ohne Stufe 4 muss alles beim alten Stand
bleiben. Fall 2 ist der eigentliche Test. Fall 3 und 4 sind negative Tests,
die zeigen, dass der Code **nicht** in unkontrollierten Situationen ein
Bild einsetzt.

## Werkzeug-Hinweis

`tools/framerate compare A mid B` ist der eigentliche Schritt-4-Vergleich.
Das Werkzeug akzeptiert drei Bilder und meldet:

- Pixel A→B verschieden
- davon im Intervall [A, B] ± 8
- außerhalb des Intervalls
- nur im Zwischenbild verschieden

Erwartung für Schritt 4 (aus Schritt 3 in `docs/20`, Tabelle "1880–1887"):
75–80 % im Intervall, 250–400 Pixel "nur im Zwischenbild verschieden" (das
sind die Kanten vom schrumpfenden START-Schriftzug in der Dateiauswahl).
Wenn der Wert signifikant abweicht — insbesondere wenn er **über** 90 %
liegt —, dann läuft die Logik mit Stufe 4 nicht wie beabsichtigt: das
Zwischenbild wäre dann **kein** Zwischenbild, sondern das echte Bild B.

## Was diese Sitzung nicht konnte

Drei Wege zur Bestätigung sind hier nicht gegangen worden:

1. **Bildlauf mit `--graphics Vulkan --x11`.** `xvfb-run` ist verfügbar,
   Lavapipe ist verfügbar, aber `moderngekko-run` ließ sich in dieser
   Sandbox nicht bauen — die `dolphin_runtime.cpp` im ModernGekko-Wrapper
   braucht C++23-Features (`std::jthread`, `std::ranges::contains`), die
   weder in libstdc++-12 (Debian Bookworm) noch in libc++-19 vorhanden sind,
   und GCC 14 ist im Repo nicht abrufbar (Sandbox-TLS gegen apt.llvm.org).

2. **FrameDumper-Vergleich ohne Schirm.** Der Patch ersetzt sowohl das
   FrameDumper-Bild als auch das Präsentationsbild (Zeilen 909-911 und
   921-923). Ein Mitschnitt zeigt also den Schatten-EFB an genau der
   Stelle, an der das Bild auf den Schirm käme. Das ist gut, weil es
   keine Bildschirm-zu-Schirm-Synchronisation braucht. Aber: der
   FrameDumper wird durch `--gfx-setting DumpFrames=True` aktiviert; ob
   diese Einstellung den Schatten-Pfad auch ohne `--x11` (also im
   kopflosen Pfad) durchläuft, ist eine Frage, die ich am Code nicht
   beantworten kann — sie hängt von `PlatformHeadless::GetWindowSystemInfo`
   ab und davon, ob der FrameDumper den Pfad nimmt, der `PresentOverride`
   aufruft, oder einen früheren.

3. **Lockstep-Test mit und ohne Stufe 4.** Schritt 4 ändert nichts am
   Gastzustand (Sperrliste unverändert, XFB-Kopie separat behandelt).
   Theoretisch muss der Lockstep-Verifizierer mit und ohne Stufe 4
   dieselben Werte sehen. Das wäre eine starke Bestätigung, dass die
   Sperre greift, ohne den Schirm zu bemühen. Diese Messung ist hier
   nicht gelaufen.

## Empfehlung für die nächste Sitzung

Auf einer Windows-Maschine mit gebautem ModernGekko (MSVC, der Standard-Workflow):

```powershell
python tools/diagnostics/headless_probe.py `
  --runtime build\moderngekko-run.exe `
  --game build\game `
  --module build\mod\GMSE01\<hash>\gGMSE01_recomp.dll `
  --output build\wp14-step4 `
  --frames 2400 `
  --sequence tools/acceptance/fixtures/game-start.json `
  --graphics Vulkan --x11 `
  --core-setting "$(printf 'GXDryRunMarker=1\n[Interface]\nUsePanicHandlers=False')" `
  --gfx-setting DumpFrames=True `
  --gfx-setting DumpFramesAsImages=True `
  --video-setting "scaler=nearest"
```

zweimal: einmal ohne `MODERNGEKKO_GX_DRYRUN_PRESENT` (Kontrolle), einmal mit.
`tools/framerate compare` über die Paare der `--output/user/Dump/Frames`-PNGs.
Erwartung an die Auswertung steht oben.

Falls die Windows-Maschine nicht verfügbar ist: die Linux-Sandbox kann mit
einem GCC-14-Patch (`patches/dolrecomp-msvc-popcount.patch` als Vorbild) das
Problem möglicherweise umgehen — `std::jthread` durch `std::thread` +
`std::condition_variable` ersetzen, `std::ranges::contains` durch
`std::find(...) != end`. Das ist **kein** trivialer Patch und bricht die
Bootstrap-Reihenfolge (Patch gegen den Pin). Es ist eine Option für eine
spätere Linux-Sitzung, nicht für jetzt.

## Was diese Quelle nicht zeigt

`docs/20` erwähnt, dass `PresentOverride` von **beiden** Pfaden aufgerufen
wird (FrameDumper und echte Präsentation). Im Patch finde ich nur die
beiden Aufrufe; den umgebenden Code (`OpcodeDecoding.cpp`,
`Present.cpp`) habe ich nicht gelesen. Das ist eine Lücke dieses Audits.
