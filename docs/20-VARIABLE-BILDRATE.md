# Variable Bildrate: der Weg in die Laufzeit (WP14)

Stand: 2026-09-16, am selben Tag um den Abschnitt „Was ein zweiter
Durchlauf sperren muss" ergänzt. Der Auftraggeber hat als Ziel genannt: „variable Fps ohne
die Spiellogik kaputt zu machen". Damit ist die Entscheidung aus
[PLAN.md](PLAN.md), Abschnitt 5.4 gefallen — die Simulation bleibt bei 30 Hz,
gerendert wird entkoppelt. Der Vorversuch WP13 ist abgeschlossen
([11-FRAMERATE-SPIKE.md](11-FRAMERATE-SPIKE.md)); er arbeitet **offline** auf
DFF-Dateien. Dieses Dokument ist der Plan, das in die **Laufzeit** zu bringen.

**Stand 2026-09-16, später am Tag: Schritt 1 ist gebaut und gemessen**
(Abschnitt „Schritt 1: gemessen" unten). Alles Weitere ist ein Entwurf mit
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

**Die Frage von Schritt 1 ist beantwortet: Ja.** Der Strom lässt sich
vollständig ein zweites Mal ausführen — jedes mitgeschriebene Byte wurde
erneut dekodiert —, ohne dass Tonstrom oder Zähler sich ändern. Die 1.111
gesperrten Schreibvorgänge sind der Beleg, dass der Riegel gebraucht wird:
gut drei je Bild, darunter die XFB-Kopie und die PE-Token, die sonst
Interrupts ausgelöst hätten.

Was Schritt 1 nicht zeigt: Zeitkosten (ein zweiter Durchlauf ohne Zeichnen
ist billig, 0,1 s über 300 Bilder liegen in der Streuung) und Bilder. Beides
kommt mit Schritt 2.

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
