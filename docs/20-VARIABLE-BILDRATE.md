# Variable Bildrate: der Weg in die Laufzeit (WP14)

Stand: 2026-09-16, am selben Tag um den Abschnitt „Was ein zweiter
Durchlauf sperren muss" ergänzt. Der Auftraggeber hat als Ziel genannt: „variable Fps ohne
die Spiellogik kaputt zu machen". Damit ist die Entscheidung aus
[PLAN.md](PLAN.md), Abschnitt 5.4 gefallen — die Simulation bleibt bei 30 Hz,
gerendert wird entkoppelt. Der Vorversuch WP13 ist abgeschlossen
([11-FRAMERATE-SPIKE.md](11-FRAMERATE-SPIKE.md)); er arbeitet **offline** auf
DFF-Dateien. Dieses Dokument ist der Plan, das in die **Laufzeit** zu bringen.

**Stand 2026-09-16, später am Tag: Schritte 1 und 2 sind gebaut und gemessen**
(Abschnitte „Schritt 1: gemessen" und „Schritt 2" unten). Alles Weitere ist ein Entwurf mit
Fundstellen, keine Messung — außer dort, wo ausdrücklich „gemessen" steht.

## Zwei Befunde, die bestehende Messungen berichtigen

**`present_count` ist kein Ausgabezähler.** `m_present_count` wird je
tatsächlicher Ausgabe **zweimal** erhöht: einmal in `ViSwap`
(`Present.cpp:174`) und einmal als erste Zeile von `Present` selbst
(`Present.cpp:904`). Dazu einmal je übersprungenem Duplikat und einmal je
Fortschrittsbild des Shader-Caches. Der in `PresentInfo` weitergereichte Wert
ist der Stand **vor** dem zweiten Inkrement.

Das erklärt eine Zahl, die in [12-TON.md](12-TON.md) unerklärt stehen blieb:
3,0053 Ausgaben je eindeutigem Bild. Wer Zwischenbilder an `present_count`
misst, misst falsch; WP14 braucht einen eigenen Zähler.

**In kopfloser Betriebsart wird überhaupt nicht präsentiert.**
`Presenter::Present` kehrt bei `IsHeadless()` sofort zurück
(`Present.cpp:906`), und `VKGfx::IsHeadless` ist `m_swap_chain == nullptr`
(`VKGfx.cpp:45-48`). Jede Aussage über den Präsentationspfad ist in dieser
Umgebung unprüfbar. Das bestätigt nachträglich, warum der Ausgabe-Skalierer
hier nicht messbar war ([18-SKALIERER.md](18-SKALIERER.md)).

## Der gewählte Weg

Von drei untersuchten Architekturen trägt eine den Inhalt:

| Entwurf | Urteil |
|---|---|
| **Befehlsstrom ein zweites Mal ausführen**, dabei nur die Matrixladungen durch interpolierte ersetzen | **gewählt.** Direkter Nachbau dessen, was `interpolate.py` offline schon tut und was WP13 als Bild geprüft hat |
| Im Präsentierer reprojizieren (Bewegungsvektoren aus den Matrizen) | verworfen als Hauptweg: extrapoliert, wo WP13 interpoliert gemessen hat; Lücken an Verdeckungskanten. Bleibt als benannter Rückfall |
| Präsentation vollständig vom Emulationstakt lösen | **später**, als Schritt 5 — nicht als Anfang |

Ausdrücklich verworfen wurde alles, was die Simulation beschleunigt:
VI-Overclock, `EmulationSpeed ≠ 1.0`, der 60-FPS-Gecko-Code, `VISkip`
(lässt unter Last VI-Interrupts ausfallen und kostet dem Spiel echte Bilder).
Das fällt am ersten Maßstab durch.

Ein eigener Präsentationsfaden ist **nicht möglich**: `AsyncRequests` ist eine
Single-Producer-Warteschlange (`AsyncRequests.h:63`).

## Sechs Schritte, jeder für sich messbar

**1. Trockenlauf.** Den GX-Befehlsstrom eines Frames mitschreiben und ein
zweites Mal dekodieren — aber **nichts zeichnen und nichts ausgeben**. Das
Nichtzeichnen kostet eine Zeile, weil Dolphin den Weg schon hat: `cullall` in
`VertexLoaderManager.cpp:443` lässt den Vertexlader in einen CPU-Puffer
laufen. Damit ist die teure, unbelegte GPU-Seite aus dem ersten Schritt heraus
und die prüfbare Frage bleibt: **Lässt sich der Strom ein zweites Mal
ausführen, ohne einen Zustand zu berühren, den das Spiel liest?**
Messung: derselbe Lauf mit und ohne Mitschnitt; Tonstrom und `frame_count`
müssen identisch sein.

> **Nachtrag vom 2026-09-16: `cullall` allein genügt nicht.** Die Antwort auf
> die Frage steht im Quelltext, und sie lautet: nein, nicht ohne weitere
> Sperren. Siehe den Abschnitt „Was ein zweiter Durchlauf sperren muss".

**2. Schatten-EFB.** Der zweite Durchlauf zeichnet wirklich, in ein eigenes
Farb- und Tiefenpaar. Der Mechanismus existiert (`FramebufferManager.cpp:238-248`
legt bereits ein zweites Farbziel an).

**3. Matrixinterpolation, Zuordnung, Schnitterkennung.** Beide Ladewege melden
ihre **aufgelösten** Wortwerte; der indizierte Weg liest sonst zur
Ausführungszeit lebenden Gast-RAM (`XFStructs.cpp:281-286`). Interpoliert wird
**ausschließlich** im XF-Matrixspeicher: 0x000–0x0FF, 0x400–0x45F, 0x500–0x5FF
und die Projektion 0x1020–0x1026. Zuordnung über gemeinsamen Anfang und
gemeinsames Ende plus ein Fenster von ±32 — **nicht** die vollständige
LCS-Tabelle aus `spike.py`, die bei 8.817 Zeichenbefehlen 77,7 Millionen Felder
materialisieren würde.

> **Nachtrag vom 2026-09-16:** gebaut und gemessen, Abschnitt „Schritt 3:
> gebaut und gemessen". Abweichend vom Plan mit der vollen LCS-Tabelle,
> begrenzt auf 1.500 × 1.500 Felder à 2 Byte; was darüber liegt, wird nur
> über Anfang und Ende zugeordnet.

**4. Das Zwischenbild wird sichtbar**, bei unveränderter Ausgaberate. Enthält
die Zählerbereinigung aus dem Befund oben. Ab hier ist erstmals ein Bild zu
prüfen.

**5. Taktentkopplung** auf dem GPU-Faden, Dualcore. Setzt `CPUThread = True`
voraus — im ganzen Projektbaum steht heute kein einziger Setzer dafür.

**6. Kosten auf der Zielhardware.** Bilder je Sekunde und 99. Perzentil bei
n = 2, 3, 4 und interner Skalierung 1x, 2x, 3x sowie 4K. **Das geht nur auf dem
Windows-Rechner des Auftraggebers.**

## Was ein zweiter Durchlauf sperren muss

Stand: 2026-09-16, **aus dem Quelltext gelesen, nicht gemessen.**

Dolphin führt die Liste selbst. `BPWritten` überspringt einen BP-Schreibvorgang,
dessen Wert sich nicht geändert hat — außer bei elf Registern
(`VideoCommon/BPStructs.cpp:82-87`). Genau diese elf sind die Register mit
gastseitiger Nebenwirkung, und damit die Liste, die ein zweiter Durchlauf
sperren muss:

| BP-Register | Wirkung, die der Gast sieht | Fundstelle |
|---|---|---|
| `BPMEM_TRIGGER_EFB_COPY` | schreibt Gast-RAM bei `copyTexDest << 5`; je nach Ziel zusätzlich `ImmediateSwap` oder `FakeVIUpdate` | `BPStructs.cpp:246`, `:364`, `:371` |
| `BPMEM_SETDRAWDONE` | `PixelEngine::SetFinish` — **erzeugt einen Interrupt** | `:180` |
| `BPMEM_PE_TOKEN_ID` | `PixelEngine::SetToken`; der Gast liest das Token zurück | `:202` |
| `BPMEM_PE_TOKEN_INT_ID` | `SetToken(..., true)` — **erzeugt einen Interrupt** | `:218` |
| `BPMEM_CLEARBBOX1`, `BPMEM_CLEARBBOX2` | setzen die Bounding-Box-Register, die der Gast über die PE liest | `:519` |
| `BPMEM_LOADTLUT0`, `BPMEM_LOADTLUT1` | lesen Gast-RAM in den TMEM | `:397` |
| `BPMEM_TEXINVALIDATE`, `BPMEM_PRELOAD_MODE` | Zustand des Texturspeichers | `:594` |
| `BPMEM_CLEAR_PIXEL_PERF` | setzt die Pixel-Zähler, die der Gast liest | `:582` |

> **Nachtrag vom 2026-09-16:** `BPMEM_TRIGGER_EFB_COPY` wird seit der
> Berichtigung der Bildgrenze (Abschnitt „Nachtrag zu Schritt 2") nicht
> mehr gesperrt, sondern gesondert behandelt: keine Kopie, aber ihr Löschen.
> Gesperrt bleiben die zehn übrigen.

Dazu kommt der indizierte XF-Ladeweg: `LoadIndexedXF` liest zur
Ausführungszeit lebenden Gast-RAM (`XFStructs.cpp:281-286`) — für den
Trockenlauf harmlos, weil nur gelesen wird, aber er liefert im zweiten
Durchlauf möglicherweise andere Werte als im ersten. Schritt 3 verlangt
deshalb ohnehin die **aufgelösten** Wortwerte.

**Folge für Schritt 1.** Die Formulierung „das Nichtzeichnen kostet eine
Zeile" war zu knapp: `cullall` hält nur die Geometrie zurück. Der Trockenlauf
braucht zusätzlich einen Riegel vor diesen elf Registern — am billigsten als
Frühausstieg in `BPWritten`, gesetzt für die Dauer des zweiten Durchlaufs.
Drei davon (`SETDRAWDONE`, beide Token) erzeugen Interrupts; sie im zweiten
Durchlauf durchzulassen hieße, die Spiellogik zu ändern. Das ist genau der
Maßstab, den der Auftraggeber gesetzt hat.

## Schritt 1: gemessen

`patches/recompcore-gx-trockenlauf.patch` (`VideoCommon/GXDryRun.cpp` und
vier Einhängepunkte). Mit `MODERNGEKKO_GX_DRYRUN=1` schreibt der Dekodierer
jeden GP-Befehl des ersten Durchlaufs mit (Display-Listen bereits aufgelöst,
so wie es auch `FifoRecorder` tut), und `after_present_event` — das auch
kopflos feuert — dekodiert die Mitschrift auf demselben Faden ein zweites
Mal. Währenddessen sperrt `BPWritten` die elf Register aus der Tabelle oben,
und der Vertexlader läuft mit `cullall`. Ohne die Variable ist nichts davon
aktiv.

Zwei kopflose Läufe, 300 Bilder, Tonmitschnitt, `dcbf`-Modul:

| | ohne Trockenlauf | mit Trockenlauf |
|---|---|---|
| Bilder | 303 | 301 |
| `native` / `cycles` | 65.095.713 / 1.829.259.366 | 64.973.212 / 1.817.312.509 |
| zweite Durchläufe | — | **307** |
| mitgeschrieben / erneut dekodiert | — | 1.283.456 / **1.283.456** Bytes |
| gesperrte BP-Schreibvorgänge | — | 1.111 |
| Wanduhr | 14,37 s | 14,27 s |

Und der Tonvergleich:

```
Ausrichtung: Versatz +0 ms, Huellkurven-Korrelation 1.0000
Abtastwertgleich: die ersten 12.165 s (100.0% der kuerzeren Aufnahme),
                  insgesamt 100.00% gleiche Abtastwerte
```

**Die Frage von Schritt 1 ist beantwortet: Ja — mit einer Bedingung, die
erst die ganze Eingabefolge gezeigt hat.** Über den Boot allein wurde jedes
Byte erneut dekodiert. Über die 2.400 Bilder bis in die Flugplatz-Sequenz
aber blieben zunächst **15 von 2.403** zweite Durchläufe vorzeitig stehen
(der erste bei Bild 861: 5.553 von 327.343 Bytes), einer davon mit einer
Zusicherung im Dekodierer (`GX_LOAD_XF_REG` mit unsinniger Länge). Der
Grund: Der Strom eines Bildes setzt nicht jedes Register neu, sondern erbt
vom Vorbild — etwa Vertexformat und -beschreibung. Der zweite Durchlauf
begann mit dem Stand vom Bild*ende*; wo das Bild diese Register unterwegs
geändert hatte, las er die ersten Zeichenbefehle mit falscher Vertexgröße und
lief versetzt.

Deshalb sichert die Mitschrift jetzt den CP-, XF- und BP-Stand an ihrem
Anfang und stellt ihn vor dem zweiten Durchlauf wieder her; danach kommt der
Endstand zurück, mit denselben Markierungen wie nach einem Sicherungsstand
(`VideoCommon_DoState`). Damit über die ganze Eingabefolge:

| | erster Durchlauf | zweiter Durchlauf |
|---|---|---|
| Bytes | 704.218.560 | **704.205.153** (Rest: das letzte, beim Beenden offene Bild) |
| vorzeitig beendete Durchläufe | — | **0** von 2.407 |
| geladene Vertices | 40.453.287 | **40.453.287** |
| gesperrte BP-Schreibvorgänge | — | 25.808 |
| `gpMarioAddress` am Ende | `0x80E9AD44` | `0x80E9AD44` |

Der zweite Durchlauf lädt exakt so viele Vertices wie der erste. Die
gesperrten Schreibvorgänge — gut zehn je Bild, darunter XFB-Kopie und
PE-Token — sind der Beleg, dass der Riegel gebraucht wird. Ein Maß, das
hier **nicht** taugt: der Tonvergleich über die Eingabefolge. Die Eingaben
werden je Bildzähler per Datei zugestellt, mit Zustellungsjitter; zwei
Läufe derselben Folge weichen im Ton nach der ersten Eingabe ohnehin
voneinander ab. Abtastwertgleich ist nur der eingabefreie Boot zu erwarten,
und der war es (oben).

## Schritt 2: gebaut und gemessen, mit Bild

`MODERNGEKKO_GX_DRYRUN=2`: Der zweite Durchlauf zeichnet wirklich. Dafür
hält `FramebufferManager` einen **Schatten-EFB** — ein eigenes Farb-,
Tiefen- und Konvertierungspaar in EFB-Größe —, das für die Dauer des
Durchlaufs per Zeigertausch (`SwapInShadow`/`SwapOutShadow`) an die Stelle
des EFB tritt. Jeder Nutzer des EFB, ob Zeichnen, Löschen oder
Pixelformatwechsel, landet dadurch ohne eigene Änderung im Schatten; der
eigentliche EFB bleibt unberührt. Der Schatten wird beim Eintausch geleert,
weil die EFB-Kopie mit Löschen, die ein Bild sonst einleitet, gesperrt ist.
Zwei weitere Dinge, die der Gast liest, sind im zweiten Durchlauf aus: die
Bounding Box (wird im Pixelshader fortgeschrieben) und die Pixelzähler.

Über die ganze Eingabefolge, Null-Grafik:

| | erster Durchlauf | zweiter Durchlauf |
|---|---|---|
| Zeichenaufrufe | 416.274 | **416.268** |
| geladene Vertices | 40.475.202 | 40.473.826 |
| vorzeitig beendete Durchläufe | — | 0 von 2.403 |
| `gpMarioAddress` am Ende | `0x80E9AD44` | `0x80E9AD44` |

Die Differenzen sind das letzte, beim Beenden offene Bild. Mit dem
Null-Backend der kopflosen Läufe wird allerdings nichts gerastert — alle
Schattenbilder sind dort schwarz, und ebenso der eigentliche EFB. Und
kopflos kann `moderngekko-run` kein Vulkan: Die kopflose Plattform hat keine
Ausgabefläche, die Laufzeit stürzt damit ab, auch ohne Trockenlauf. Deshalb
kennt `headless_probe` jetzt `--x11` und `--graphics`.

**Das Bild, auf Vulkan/Lavapipe unter Xvfb, ganze Eingabefolge:**

| | Wert |
|---|---|
| Bilder / Wanduhr | 2.377 / 299,6 s (7,9 je Sekunde — Lavapipe rastert doppelt) |
| zweite Durchläufe, vorzeitig beendet | 2.379, **0** |
| Zeichenaufrufe erster / zweiter Durchlauf | 373.495 / 373.449 |
| `gpMarioAddress` am Ende, `smc_failed` | `0x80E9AD44`, 0 |
| Schattenbilder | 40, alle 60 Bilder eines |

Alle 60 Bilder wurden der Schatten und, zum Vergleich, der eigentliche EFB
zum selben Zeitpunkt als PNG gesichert. Der Anteil nicht-schwarzer Pixel
läuft in beiden Bildreihen gleich: 0 % im schwarzen Vorspann, 29,5 % beim
Aufblenden (Bild 300), dann 80 bis 84 % durch Titel und Dateiauswahl bis in
die Flugplatz-Sequenz. Pixel für Pixel:

| Bild | mittlere Abweichung je Kanal | Pixel verschieden |
|---|---|---|
| 360 | 0,08 | 0,2 % |
| 1.200 | 1,14 | 13,3 % |
| 1.800 | 1,13 | 6,3 % |
| 1.920 | 1,30 | 6,0 % |
| 2.340 | 0,56 | 1,8 % |
| 600 | 15,2 | 46,0 % |

Der Schatten trägt das Bild. Die verbleibenden Abweichungen sind erwartbar:
Der eigentliche EFB wird nach dem Präsentieren gelesen, wenn die CPU im
Zweikernbetrieb schon Befehle des nächsten Bildes abgesetzt haben kann,
während der Schatten genau das eine Bild zeigt; Bild 600 fällt in den
Titelbildschirm mit bewegten Elementen. **Schritt 2 ist damit erbracht**:
Der zweite Durchlauf zeichnet wirklich, in ein eigenes Paar, und der Gast
merkt nichts davon.

## Nachtrag zu Schritt 2: die Bildgrenze war falsch

Stand: 2026-09-16, gemessen.

Die Mitschrift eines „Bildes" reichte bisher von einem Präsentieren zum
nächsten (`after_present_event`). Das ist nicht die Bildgrenze des Spiels.
Beleg: Zum Zeitpunkt des Präsentierens zeigt der eigentliche EFB in der
Dateiauswahl Himmel, Palme und Mario, aber **kein HUD** — das Spiel hat mit
dem nächsten Bild schon begonnen, bevor das Präsentieren kommt, und ist noch
nicht beim HUD. Die Mitschrift enthielt damit den Schluss eines Bildes (das
HUD) und den Anfang des nächsten; der Schatten zeichnete beides in ein Bild,
das HUD über den geleerten Schatten statt über die Szene. Daher rührten die
6 Prozent verschiedener Pixel in der Dateiauswahl der Schritt-2-Tabelle,
nicht aus dem Zweikernbetrieb, wie dort vermutet — der ist hier gar nicht
an. Auch die 0,44 Prozent von A nach B geänderter Pixel, mit denen die
erste Messung der Stufe 3 die Dateiauswahl als „kaum bewegt" einstufte,
verglichen zwei halbe Bilder.

Die Bildgrenze ist die XFB-Kopie. Dolphin löst dort `after_frame_event`
aus (`BPStructs.cpp`: „This is as closest as we have to an end of the
frame"), nach der Kopie und vor dem Löschen, das die Kopie auslösen kann.
Die Mitschrift wird jetzt dort geschnitten; das abgeschlossene Bild wartet
auf das nächste Präsentieren und läuft dann ein zweites Mal. Der Befehl der
XFB-Kopie selbst steht am Anfang der nächsten Mitschrift (der Dekodierer
meldet einen Befehl erst nach dessen Ausführung) und wird im zweiten
Durchlauf gesondert behandelt: keine Kopie — weder Texturcache noch RAM
noch XFB, und kein `after_frame_event` —, aber das Löschen, damit der
Schatten so beginnt wie der EFB. Dasselbe gilt für EFB-Kopien mitten im
Bild. Die Sperrliste hat damit zehn Register; die Kopie ist der elfte Fall
mit eigener Behandlung. Das Vergleichsbild `efb_<n>.png` entsteht seither
an der Bildgrenze, nicht mehr beim Präsentieren; `<n>` zählt XFB-Kopien.

Mit dieser Grenze, Stufe 3 aktiv, ganze Eingabefolge auf Vulkan/Lavapipe
(Stand nach allen Korrekturen dieses Abschnitts und des nächsten): 2.083
abgeschlossene Bilder bei 2.081 Schritten des Bildzählers, keines verworfen
(zwei Kopien zwischen zwei Präsentierungen zählt der Zähler `verworfen`).
Der Bildzähler der Sonde zählt eindeutige Bilder, nicht Präsentierungen —
ein Irrtum, der erst beim Bau von Schritt 4 aufgefallen ist: **Das Spiel
läuft durchgehend mit 30 Bildern je Sekunde und präsentiert jedes Bild
zweimal, auch in den Menüs** (Null-Lauf, Eingabefolge plus 3.000 Bilder
Vorspann: 10.343 Präsentierungen, 5.189 Wiederholungen, 5.154 XFB-Kopien).
Schatten gegen eigentlichen EFB **desselben Bildes**, alle 60 Bilder:

| Bilder | mittlere Abweichung je Kanal | Pixel verschieden |
|---|---|---|
| 0–360 (Vorspann) | 0,00 | 0,0 % |
| 420 (Aufblenden des Titels) | 1,77 | 12,3 % |
| 480–1.500 (Titel) | 0,08–0,32 | 0,0–0,8 % |
| 1.560 (Übergang zur Dateiauswahl) | 1,32 | 1,3 % |
| 1.620–2.040 (Dateiauswahl) | 0,10–0,88 | 0,1–1,4 % |

Die Werte enthalten die Interpolation der Stufe 3: Der Schatten ist das
Zwischenbild, der EFB das Bild B, und in der Dateiauswahl bewegen sich
Mario, das Wasser und der pulsierende START-Schriftzug. Bild 1.560 lag,
solange der Schnappschuss die Shader-Verwalter nur neu markierte statt
ihren Stand zurückzulesen (siehe Absturz unten), bei 4,89 und 11,8 Prozent.
Der verbliebene Ausreißer ist das Aufblenden des Titels; woran es dort
liegt, ist nicht untersucht. Naheliegend, aber Vermutung: Kopiert das Spiel
innerhalb eines Bildes mehrfach aus dem EFB und zeichnet die Kopie zurück,
hält der Texturcache im zweiten Durchlauf den Stand vom Ende des ersten,
nicht den vom jeweiligen Zeichenbefehl, weil die Kopie gesperrt ist.

## Schritt 3: gebaut und gemessen

`MODERNGEKKO_GX_DRYRUN=3`. Der Vertexlader meldet jeden Zeichenbefehl mit
Signatur (Primitiv, VAT, Vertexzahl, Vertexgröße, Positionsformat, Matrix
je Vertex) und dem XF-Matrixstand zu diesem Zeitpunkt: 0x000–0x0FF,
0x400–0x45F, 0x500–0x5FF und die Projektion 0x1020–0x1026, 608 + 7 Wörter.
Das sind die aufgelösten Werte: Was der indizierte Ladeweg aus dem Gast-RAM
geholt hat, steht in diesem Moment im XF-Speicher. Vor dem zweiten
Durchlauf von Bild B werden dessen Zeichenbefehle denen von A zugeordnet
(gemeinsamer Anfang und gemeinsames Ende direkt, der Rest per längster
gemeinsamer Teilfolge, Tabelle bis 1.500 × 1.500); Schnitt, wenn weniger
als 60 Prozent zugeordnet sind (Schwelle aus dem Spike). Vor jedem
zugeordneten Zeichenbefehl werden die Wörter, die sich von A nach B
geändert haben, über den regulären Weg (`LoadXFReg`, mit Flush und
Schmutzmarkierung) auf den Zwischenwert t = 0,5 gesetzt; die Projektion
nur, wenn ihr Typ gleich blieb.

**Ein Fehler beim ersten Bauen.** Geladen wurde vor jedem zugeordneten
Zeichenbefehl, auch wenn der Zwischenwert schon anlag. Jedes Laden erzwingt
einen Flush; der zweite Durchlauf hatte dadurch zehnmal so viele
Zeichenaufrufe wie der erste (3.783.741 gegen 375.146 über die
Eingabefolge). Seit der zweite Durchlauf den lebenden XF-Speicher
vergleicht und nur lädt, was noch nicht anliegt, sind die Zeichenaufrufe
gleich; von 779 Millionen geänderten Wörtern brauchten 7,8 Millionen ein
Laden. (Die Zeichenaufrufe je Bild schwanken zwischen Läufen um einige
Prozent, 153 bis 161 je Bild in vier Läufen derselben Eingabefolge; das
Verhältnis der beiden Durchläufe zueinander nicht.)

Ganze Eingabefolge, Vulkan/Lavapipe, Bildgrenze an der XFB-Kopie:

| | Wert |
|---|---|
| zweite Durchläufe / vorzeitig beendet | 2.084 / 0 |
| Bilder interpoliert / Schnitte | 2.055 / 29 |
| Zeichenaufrufe zweiter / erster Durchlauf | 318.621 / 318.770 |
| zugeordnete Zeichenbefehle | 3.938.567 |
| davon mit geladenen Wörtern | 144.533 (70 je Bild) |
| geladene Wörter / schon anliegend | 7.761.036 / 779.470.535 |
| Projektion geladen | 1 |
| `smc_failed`, Exit-Code | 0, 0 |

**Was der zweite Durchlauf die CPU kostet**, Null-Backend (kein Rastern),
ungedrosselt, ganze Eingabefolge, vier Kerne der Messumgebung, Wanduhr
einschließlich rund 17 s Start:

| | Wanduhr | Bilder | Exit-Code |
|---|---|---|---|
| ohne Trockenlauf | 72,8 s | 2.106 | 0 |
| Stufe 1 (dekodieren, Vertices laden, nichts zeichnen) | 75,3 s (+3 %) | 2.104 | 0 |
| Stufe 3 (in den Schatten zeichnen, Matrizen interpolieren) | 86,0 s (+18 %) | 2.102 | 0 |

Ohne den Start sind das rund 56 s gegen 70 s für 2.100 Bilder: Der volle
zweite Durchlauf kostet hier gut 6 ms je Bild an CPU-Zeit, ein Viertel der
Bildzeit dieses ungedrosselten Laufs. Das ist die Dekodierung und die
Vertexverarbeitung; was das Rastern auf einer Grafikkarte kostet, sagt nur
Schritt 6.

**Liegt das Zwischenbild zwischen den Nachbarn?** Dateiauswahl, Bilder
1.880 bis 1.887: Mario steht am Strand und atmet, das Wasser läuft, der
START-Schriftzug pulsiert. A ist der eigentliche EFB von Bild n − 1, B der
von Bild n, das Zwischenbild der Schatten von Bild n (`tools/framerate
compare A mid B`):

| Bild | Pixel A→B verschieden | davon im Intervall [A, B] ± 8 | außerhalb | nur im Zwischenbild verschieden |
|---|---|---|---|---|
| 1.881 | 7.786 (2,30 %) | 6.130 (78,7 %) | 1.656 | 424 |
| 1.883 | 7.581 (2,24 %) | 5.751 (75,9 %) | 1.830 | 369 |
| 1.885 | 6.246 (1,85 %) | 4.909 (78,6 %) | 1.337 | 253 |
| 1.887 | 5.547 (1,64 %) | 4.295 (77,4 %) | 1.252 | 373 |

Zum Vergleich die erste Messung mit der falschen Bildgrenze (Bilder 1.901
bis 1.905): 92 bis 94 Prozent im Intervall, aber 19.300 Pixel, die nur im
Zwischenbild anders waren — das HUD über dem geleerten Schatten. Jetzt sind
es 253 bis 424.

Drei Befunde aus den Bildern selbst:

- Das Zwischenbild liegt näher an B als an A (mittlere Abweichung 0,33
  gegen 0,59 je Kanal bei Bild 1.881). Was nicht in Matrizen steckt — die
  Texturanimation des Wassers, die Vertexdaten selbst —, hat im
  Zwischenbild den Stand von B, weil der Strom von B läuft.
- Von den Pixeln außerhalb des Intervalls liegen 96 bis 97 Prozent im
  START-Schriftzug. Der schrumpft von A nach B; im Zwischenbild steht er auf
  halbem Weg, und ein Pixel, das in A Schrift und in B Himmel ist, ist dort
  oft Umriss, weder das eine noch das andere. Das Pixelmaß ist für bewegte
  Kanten zu grob. Mario zeigt im vergrößerten Ausschnitt eine plausible
  Zwischenstellung; von seinen Pixeln liegen 94 bis 95 Prozent im Intervall.
- Einen Strahlenkranz, den A um den Schriftzug zeichnet und B nicht mehr,
  hat das Zwischenbild nicht: Was nur A zeichnet, gibt es im Strom von B
  nicht.

**Was Schritt 3 nicht belegt.** Eine Szene mit Kamerabewegung gibt die
Eingabefolge nicht her, sie endet in der Dateiauswahl. Die 900 Bilder
danach (eigene, nicht eingecheckte Folge) zeigen den Vorspannfilm: dort
ändert sich keine Matrix, das Zwischenbild ist Pixel für Pixel Bild B — der
Weg über Matrizen interpoliert keinen Film. Eine Messung im Spiel braucht
eine Eingabefolge, die durch Film und Landung ins Spiel läuft, und dann
Schritt 4, der das Zwischenbild überhaupt sichtbar macht.

**Ein Absturz beim Beenden, bis zum Grund verfolgt.** Mit Trockenlauf auf
Vulkan endete die Laufzeit beim Beenden mit Signal 11 oder mit `free():
invalid next size`, nach dem Schreiben aller Zähler, in
`InputConfig::ClearControllers` — fern vom Trockenlauf; zuletzt auch auf
dem Null-Backend. valgrind (60 Bilder, Stufe 2, Vulkan; 21.205 Fehler aus
vier Stellen, ohne Trockenlauf keine davon) zeigte den Schreibzugriff:
`VertexShaderManager::SetConstants` kopierte Nachtransformationsmatrizen
hinter das Ende des Konstantenpuffers. Der Grund lag in meiner
Wiederherstellung des Zustands: Sie rief `InvalidateXFRange(0, 0x1000)`,
und diese Funktion rechnet für einen Bereich, der vor den
Nachtransformationsmatrizen beginnt, deren Anfang absolut (0x500) statt
relativ (0) — ebenso für die Lichter (`XFStateManager.cpp`). Ein latenter
Fehler in Dolphin, der in diesem Baum sonst nie ausgelöst wird, weil kein
anderer Aufrufer einen bereichsübergreifenden Bereich übergibt. Behoben,
indem der Schnappschuss die vier Shader-Verwalter über ihre
`DoState`-Serialisierung sichert und zurückliest, wie ein Sicherungsstand,
statt sie neu zu markieren; danach `BPReload` und `MarkAllDirty` wie in
`VideoCommon_DoState`. Exit-Code seither 0. Zwei weitere Fehler fielen
dabei auf und sind behoben: Der erste Durchlauf hat beim Präsentieren meist
schon Vertices des nächsten Bildes gesammelt, aber noch nicht gezeichnet —
die landeten im Schatten oder wurden in Stufe 1 mit dem `cullall`-Stapel
verworfen (jetzt ein Flush vor dem zweiten Durchlauf); und in Stufe 1
löschte die nachgestellte EFB-Kopie den eigentlichen EFB, weil dort kein
Schatten eingetauscht ist (jetzt ausgelassen).

## Schritt 4: gebaut, Bild noch nicht geprüft

`MODERNGEKKO_GX_DRYRUN_PRESENT=1` zusätzlich zu Stufe 3. Der zweite
Durchlauf läuft jetzt vor dem Präsentieren (`before_present_event`).
Bringt eine Präsentation ein neues Bild und war die vorige eine
Wiederholung — das Spiel läuft also gerade mit 30 Bildern je Sekunde —,
tritt das Zwischenbild an die Stelle des XFB: `Presenter::Present` und der
Bildmitschnitt fragen `GXDryRun::PresentOverride`, das den Schatten samt
EFB-Ausschnitt der XFB-Kopie liefert. Die Wiederholung danach zeigt das
echte Bild. Die Ausgaberate bleibt, die Reihenfolge stimmt (A, Zwischenbild,
B), das echte Bild erscheint eine Präsentation später als zuvor. Bei einem
Schnitt oder ohne Wiederholung davor bleibt alles beim XFB.

Gemessen bisher nur die Zähler, Null-Backend, Eingabefolge plus 3.000
Bilder: 10.343 Präsentierungen, 5.189 Wiederholungen, 5.047 davon mit dem
Zwischenbild belegt, Exit-Code 0. **Nicht geprüft ist das Bild** — ob das
ersetzte Bild wirklich auf dem Schirm oder im Mitschnitt erscheint. Der
Weg dafür steht: `headless_probe --gfx-setting DumpFrames=True
--gfx-setting DumpFramesAsImages=True` (neu) legt je Präsentation ein PNG
unter `user/Dump/Frames` ab; ohne Stufe 4 müssen die Paare gleich sein, mit
Stufe 4 muss das erste Bild jedes Paares zwischen seinen Nachbarn liegen
(`tools/framerate compare`). Alternativ der Bildschirm selbst über
`tools/diagnostics/window_capture.py` (docs/18).

## Was vorab zu prüfen war

**1. Dualcore-Gleichheit — erledigt und bestanden.** Schritt 5 setzt
`CPUThread = True` voraus, und im ganzen Projektbaum stand dafür bisher kein
einziger Setzer. Ob der statische Kern mit Rückweg zweifädig genauso rechnet,
war offen. Gemessen, je 180 Bilder mit Tonmitschnitt:

| Gegenstand | einfädig | zweifädig |
|---|---|---|
| `native` | 192.014.501 | 192.024.166 |
| `cycles` | 1.441.772.981 | 1.442.041.571 |
| `smc_failed`, `fallback` | 0, 0 | 0, 0 |
| Lockstep über 30 Bilder | 3.408 geprüft, **4** Meldungen | 3.409 geprüft, **4** Meldungen |

Und der Tonvergleich, das schärfste der drei Maße:

```
Ausrichtung: Versatz +0 ms, Huellkurven-Korrelation 1.0000
Abtastwertgleich: die ersten 8,208 s (100,0 % der kuerzeren Aufnahme),
                  insgesamt 100,00 % gleiche Abtastwerte
Tonhoehe: Verhaeltnis 1.0000 (+0 Cent)
```

**Der statische Kern mit Rückweg erzeugt zweifädig einen abtastwertgleichen
Tonstrom.** Die Zählerunterschiede von 0,005 % sind die übliche Streuung
zwischen zwei Läufen. Schritt 5 hat damit seine Grundlage.

**2. Referenzlauf als Vergleichsbasis — erledigt.** Ohne ihn ist in den
Schritten 1 bis 4 nichts falsifizierbar, weil dort jede Aussage die Form
„identisch zum Referenzlauf" hat. Der Lauf ist gefahren und hier
festgeschrieben.

Aufruf (ohne Spieldaten hier reproduzierbar, sobald eine eigene Kopie
vorliegt; gefahren wurde er noch mit `STATICRECOMP_YIELD=1`, was seit dem
2026-09-16 die Voreinstellung ist und deshalb entfällt):

```bash
python3 tools/diagnostics/headless_probe.py     --runtime <moderngekko-run> --game <spiel> --module <modul>     --output <neu> --frames 180 --audio-dump
```

| Gegenstand | Wert |
|---|---|
| Bilder | 181 |
| `native` | 192.014.501 |
| `cycles` / `ticks` | 1.441.772.981 / 3.988.899.486 |
| Anteil nativ | 36,14 % |
| `smc_failed`, `fallback`, `noprogress` | 0, 0, 0 |
| `bursts` | 371.831 |
| Rückwege / abgelehnt | 8.922 / 6.403 |
| Tonmitschnitt | 32.028 Hz, 2 Kanäle, 262.872 Abtastwerte, **8,208 s** |
| Ton: Spitze / Effektivwert / Stille | 0,420 / 0,00983 / 87,8 % |

Die Zähler streuen zwischen Läufen um etwa 0,005 % (an der Dualcore-Messung
oben abgelesen); der **Tonstrom streut nicht** — er war dort über die vollen
8,208 s abtastwertgleich. Deshalb ist er das Maß, an dem die Schritte 1 bis 4
zu prüfen sind: `tools/audio compare <referenz> <neu>` muss 100,00 % gleiche
Abtastwerte und Versatz 0 ms melden. Alles andere ist weicher.

Zusätzlich der Lockstep-Bezugswert (30 Bilder, Prüfmodul): **3.408 geprüft,
4 Meldungen** ([17-LOCKSTEP.md](17-LOCKSTEP.md)).

## Größtes Risiko

**Jede EFB-Kopie im zweiten Durchlauf schreibt Gastspeicher — auf beiden
Zweigen.** `TextureCacheBase::CopyRenderTargetToTexture` entscheidet in
`TextureCacheBase.cpp:2193-2197`: Ist `copy_to_ram` wahr, schreibt
`WriteEFBCopyToRAM`; ist es falsch, schreibt `UninitializeEFBMemory` den
Bereich mit Nullen zu. **Einen dritten Zweig gibt es nicht.** Ein zweiter
Durchlauf, der die EFB-Kopien einfach mitmacht, zerstört Spielzustand.

Dazu die bereits in dieser Sitzung an den vorhandenen Aufzeichnungen
**gemessene** Entschärfung: je Frame gibt es genau drei EFB-Kopien, davon genau
eine mit `copy_to_xfb`, und diese ist der letzte Befehl des Frames. Der
Framerand ist also sauber bestimmbar.

## Zahlen aus den vorhandenen Aufzeichnungen

Am Rande der Untersuchung gemessen, nützlich für die Pufferauslegung:

| Gegenstand | Menü und Dateiauswahl | Flugplatz (aus [11](11-FRAMERATE-SPIKE.md)) |
|---|---|---|
| Befehlsstrom je Frame | 277.811 – 379.075 Bytes | 650.000 – 900.000 |
| Zeichenbefehle je Frame | 1.257 – 3.206 | 8.800 – 9.700 |
| Matrixladungen je Frame | 500–556 unmittelbar, 422–708 indiziert | 551 + 664 |

## Was der Nutzer am Ende sieht

Die Ausgabe läuft mit Bildschirmrate oder einer wählbaren Obergrenze, die
Simulation bleibt bei 30 Hz. Kamerafahrten, Schwenks und die Bewegung aller
zuordenbaren Objekte sind flüssig. Die Funktion ist abschaltbar.

**Was ausdrücklich in 30-Hz-Schritten bleibt:** alles, was nicht im
XF-Matrixspeicher steht — Partikel, Wasseranimation, HUD-Animationen,
vorgerenderte Filme. Die Eingabeabtastung bleibt bei 30 Hz.

Ein sichtbares Zwischenergebnis gibt es schon nach Schritt 4: 60 Hz Ausgabe bei
30 Hz Simulation über den vorhandenen Duplikatpfad, der heute nur durch
`SkipDuplicateXFBs = true` abgeschaltet ist (`GraphicsSettings.cpp:204`).
