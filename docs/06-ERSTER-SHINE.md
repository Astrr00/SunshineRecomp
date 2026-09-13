# Erster Shine und reguläre Fortschrittsspeicherung

Stand: 2026-09-09. Der Flugplatz-Boss wurde besiegt und der erste Shine
eingesammelt. Ein durchgehender Lauf vom regulär geladenen Slot aus hat
den Shine gespeichert; nach vollständigem Prozessneustart zeigt Slot A
**1 Shine**. Das ist eine Prüfung dieses frühen Fortschritts, keine Abnahme
des vollständigen Spiels oder aller Port-Anforderungen.

## Referenzcode und gemessene US-Strukturen

Als reine Lese-Referenz wurde `doldecomp/sms` nach `ref/sms` geklont, Commit
`464a206e793d539293d01c29bf8ecb1f507f405f`, Lizenz CC0.
Dieser Baum wurde nicht geändert oder gebaut; es wurden keine Disc-/DOL-/MAP-
Dateien geladen. Seine JP-Adressen wurden nicht übernommen. Gerade
`Player/WaterGun.cpp` ist dort als **NonMatching** markiert; Funktionsentwürfe
sind deshalb keine ungeprüfte Wahrheit über das US-Binary.

Verwendete Spielcode-Referenzen: `include/Player/Mario.hpp`, `WaterGun.hpp`,
`include/Enemy/GateKeeper.hpp`, `Enemy.hpp`, `src/Enemy/gatekeeper.cpp`,
`src/GC2D/CardSave.cpp` und `src/System/CardManager.cpp`.

Im laufenden GMSE01 Rev 0 wurde geprüft:

| Gegenstand | Gemessene Zuordnung |
|---|---|
| Mario-Objekt | Pointer an `0x8040E108`; Vtable `0x803DD660` |
| Mario-Position | Objekt + `0x10`; alternativ Pointer an `0x8040E10C` |
| FLUDD | Mario + `0x3E4`; dessen Owner an +`0x8` zeigt zurück auf Mario |
| Wasservorrat | FLUDD + `0x1C80`; anfangs 10.000, nimmt beim Spritzen ab |
| Düsenindex | FLUDD + `0x1C84`; Spray = 0 im Test |
| Boss-Vtable | `0x803BB71C`, Actor-Typ `0x10000022` an +`0x4C` |
| Boss-Position | `(-1500, 300, 1500)`; meine erste Positionsschätzung war falsch |
| Boss-Trefferpunkte | Byte an +`0x13C`, tatsächlich 3 → 2 → 1 → 0 |
| Kopfobjekt | Pointer an Boss + `0x174`; Owner an Kopf + `0x68` zeigt auf den Boss |
| Kopfposition / Verwundbarkeit | Kopf + `0x10` / `0x70`; Bewegung und 0/1-Wechsel beobachtet |

Der aktive Boss lag in diesen Läufen bei `0x81272674`, sein Kopf bei
`0x8127A980`. Ein zweiter vtable-gleicher Speicherbereich erwies sich durch
fehlenden Owner-Rückverweis als ungeeigneter Kandidat. **Heap-Adressen sind
keine dauerhaften Hooks.** Die Zuordnung muss nach Szenenwechseln erneut
geprüft werden. Der neue Leser `tools/diagnostics/sunshine_state.py` prüft
Revision, MEM1-Grenzen, Vtables und Owner-Beziehungen; er schreibt nicht ins
Spiel-RAM. Seine Einzelreads sind bei laufendem Core nicht atomar.

## Tatsächlicher Kampf

Alle Bewegungen und Treffer erfolgten über Controller-Automation. Keine
Position, HP, Shine-Zahl oder Fortschrittsflagge wurde ins RAM geschrieben.
Die Skripte lesen Position, Wasserrichtung, Kopfposition und HP, um die
Controller-Eingabe auszurichten. Der Boss wurde mit wiederholten R-Betätigungen
getroffen. Ein langes durchgehendes Halten zeigte zeitweise keinen weiteren
Wasserverbrauch; dieser Befund ist noch nicht als Runtimefehler eingeordnet
und nicht durch einen Spieleingriff „behoben“ worden.

Belege des ersten erfolgreichen Kampfes unter `build/gameplay-verification/auto/`:

- `boss-pulsed-trace.json`: HP-Abnahmen bis 0, Wasservorrat beim Ende 2.518.
- `boss-defeated.png`: Boss verschwunden, große Schleimfläche gereinigt,
  Shine erschienen. Der zuvor einsinkende NPC steht wieder auf dem Boden.
- `shine-collected.png`: Shine-Pose und HUD mit 1 Shine.

Die zuvor pauschal als „Geometriefehler“ bezeichneten Schleim-/Versinkanteile
müssen im Kontext der Spielmechanik bewertet werden. Software-Rendering und
Kampfverlauf rechtfertigen keine pauschale Behauptung eines defekten Renderers.
Umgekehrt ist damit noch nicht jedes sichtbare Detail als originalgetreu
abgenommen.

## Fehlgeschlagener erster Speicherversuch – eigener Testfehler

Nach diesem ersten Kampf blieb die GCI-Prüfsumme unverändert. Das Bild
`shine-saved.png` zeigt tatsächlich die Aufforderung, die originale Memory
Card einzulegen. Der Dateiname ist irreführend und **kein Erfolgsbeleg**.

Dieser Lauf hatte einen alten FLUDD-Savestate zurückgeladen, obwohl derselbe
Slot zwischenzeitlich regulär gespeichert worden war. Im Referenzcode
`CardSave.cpp` wird der Bookmark-Speicherzeitpunkt mit
`TFlagManager::getLastSaveTime()` verglichen; bei Abweichung wird der
Original-Card-Dialog gewählt. Ein Savestate ist daher nicht beliebig mit
einer neueren GCI kombinierbar. Ich habe die Schutzprüfung nicht umgangen.

Zusätzlich serialisiert Dolphins `GCMemcardDirectory::DoState` den
Speicherpfad und `GCIFile::DoState` die Dateinamen. Ein anderer `--user-dir`
allein garantiert bei fremden Savestates also keine isolierten Card-Ziele.
Diagnose-Savestates und GCI-Versionen müssen als zusammengehörig betrachtet
werden; keine alten Zustände gegen die aktuelle Fortschrittskarte testen.

## Wiederholung ohne Savestate-Rücksprung

Unter `build/shine-load-check/auto/` wurde der 0-Shine-Slot regulär geladen,
FLUDD erneut erreicht, der Boss erneut über 3 → 2 → 1 → 0 besiegt und der
Shine eingesammelt. Das Befehlsarchiv enthielt beim Save-Check 914 abgearbeitete
Befehle und **keinen einzigen `load_state`**. RAM-Schreibbefehle wurden ebenfalls
nicht zur Progression verwendet.

`fresh-shine-save.png` zeigt den regulären Save-and-Continue-Dialog,
`fresh-save-result.png` die danach fortgesetzte Handlung. Die 57.408-Byte-GCI
im separaten Testprofil änderte ihre SHA-256:

- vorher: `6f827b57065929abdf966d7a8ab03eab008efa2d3a20fd6458267b4c808ae0cd`
- danach: `8e1ac668415c553f18702d6c887d1b631b81cc93cf0e1af53070620ee11cae14`

Die GCI-Sicherung liegt lokal unter `build/shine-load-check/card-one-shine/`.
Die ursprüngliche Karte unter `build/userdir/` blieb bei
`887de755eb976093783ace7df22470cf285066e62ef2a484680e8ba51566a755`.

Nach regulärem Beenden wurde ein neuer Prozess **ohne `--load-state`** gestartet:
`build/one-shine-reload/auto/one-shine-slot.png` zeigt Slot A mit 1 Shine.
Der Slot wurde über das Menü gestartet; die Handlung nach dem Flugplatz
(einschließlich Polizei-Sequenz) wird fortgesetzt. Damit ist die Persistenz
des ersten abgeschlossenen Fortschritts belegt.

`build/one-shine-reload/auto/plaza-playable.png` belegt anschließend das
steuerbare Delfino Plaza nach diesem normalen Laden. Mario wurde bewegt und
die Kamera gedreht. Der Zustandsleser wurde dort tatsächlich ausgeführt:
Mario liegt nun bei `0x81322DA0`, FLUDD bei `0x8135C004`; die Rückverweise
stimmen, die Position ist `(6500, 300, −2953,667)`, Wasser 10.000, Düse 0.
Das unterstreicht, warum die Heap-Adressen nicht fest verdrahtet werden dürfen.

## Weitergeprüfte R-Dauerbetätigung

Ein separater Test in Plaza hielt R durchgehend, ohne Boss-Tutorial:

| Framezähler | Wasser | ausgelesenes R |
|---|---|---|
| 36152 | 9381 | noch nicht gedrückt |
| 36311 | 8906 | Digitalbit `0x20`, Triggerwert 150 |
| 36460 | 8762 | weiterhin gedrückt |
| 36608 | 8762 | weiterhin gedrückt |

Beleg: `build/one-shine-reload/auto/plaza-long-r.json`. Das Plateau ist
reproduziert, seine Einordnung bleibt offen. Der Wasserpartikel-Manager
hatte im anschließend pausierten Zustand Kapazität 256 und aktive Anzahl 0;
eine erschöpfte Partikelliste ist dadurch nicht als Ursache belegt.
Als nächster gezielter Vergleich eignen sich JIT64 und der tatsächliche
Düsen-Druckzähler. Es wurde kein Cheat zur Änderung des Wasservorrats benutzt.

Während des ersten Dauer-Tests trat eine kurzzeitige Windows-Dateisperre bei
`status.txt` auf. Die Statusdatei wird von der Laufzeit fortlaufend neu
geschrieben. `scripts/automation.py::read_status` behandelt jetzt temporäre
Sharing-Fehler und unvollständige Dateien mit begrenzten Wiederholungen.
Render-Probe und Zustandsleser verwenden diesen Helfer. 100 vollständige
Lesezugriffe gegen die laufende Automationsausgabe wurden geprüft.

## Aktueller Fortsetzungspunkt

Der einzige Spielprozess ist in Delfino Plaza pausiert; Automation:
`build/one-shine-reload/auto/`. Unter `build/one-shine-reload/checkpoint/`
liegen `plaza.sav`, die dazu gesicherte `GC/`-Karte und `hashes.json`.
Diese Paarung nur bewusst für Diagnose verwenden; nicht später mit einer
weitergespielten GCI mischen. Für die normale Fortsetzung genügt `resume`.

## Weiter offen

Der Port ist nicht fertig: entkoppeltes/unbegrenztes Rendering, getrennte
Ausgabeauflösung, vollständiges Widescreen/Ultrawide samt Filmen und Culling,
Windows-Produktoberfläche, reale Controller-Konfiguration und Tonabnahme
bleiben offen bis teilweise geprüft. Auch die Spielprüfung deckt bislang
nur den Beginn ab. Nichts committed oder gepusht.

## Nachtrag: R-Plateau gegen JIT64 verglichen

Die Messreihen `build/trigger-investigation/static.json` und `jit.json`
zeigen bei Analog-R=1.0 und Druck=150 denselben Endzustand:
Düsenzähler 38400, Ausstoßkraft 0, Partikelpool 0. Restwasser statisch 8134,
JIT64 8142 (zeitlich nicht exakt gleich angesetzte Proben). Damit ist das
Plateau nicht als spezifischer Fehler der statischen Recompilation belegt.
Es wurde kein Spieleingriff zur Änderung dieses Verhaltens vorgenommen.
Die damaligen Diagnoseprozesse sind beendet; Anzeige-Fortsetzung in Dokument 07.
