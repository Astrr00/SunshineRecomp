# Machbarkeitsanalyse: Nativer Sunshine-Port für Windows x86-64

Stand: 2026-09-09. Alle Aussagen unten sind am tatsächlichen Quellcode der genannten
Commits geprüft, nicht aus READMEs übernommen. Nicht geprüfte Punkte sind als solche
gekennzeichnet.

> **Umfang:** Auf Wunsch des Auftraggebers am 2026-09-09 auf einen reinen
> Windows-Port eingegrenzt. Android ist entfallen. Damit entfallen auch die
> ursprünglichen Anforderungen 6 (Android-App), die Touch-Belegungen aus
> Anforderung 7 und die Smartphone-Seitenverhältnisse (19,5:9, 20:9) aus
> Anforderung 3. Ultrawide (21:9, 32:9) bleibt.

## 1. Untersuchte Grundlagen

| Projekt | Geprüfter Commit | Datum | Lizenz | Nutzbar als |
|---|---|---|---|---|
| [doldecomp/sms](https://github.com/doldecomp/sms) | `fc449db5daaed61eebb18609b35c5c0c4876f721` | 2026-09-09 | CC0-1.0 | **Referenz**, nicht Spielcode |
| [TwilitRealm/dusklight](https://github.com/TwilitRealm/dusklight) | Repo-Übersicht | 2026-09 | CC0-1.0 | **Vorbild**, nicht übertragbar |
| [encounter/aurora](https://github.com/encounter/aurora) | `749d6ee7a22bdfab78c8ece9047bca5d79aa72ca` | 2026-09-04 | MIT | **Nicht auf dem kritischen Pfad** |
| [ExpansionPak/DolRecomp](https://github.com/ExpansionPak/DolRecomp) | `40637c4683bd2820ac5b23607ee344720beb26df` | 2026-09-05 | GPL-3.0 | **Basis (Recompiler)** |
| [ExpansionPak/ModernGekko](https://github.com/ExpansionPak/ModernGekko) | `5417826c31187d4dadf8588c7aa25bf107782936` | 2026-08-23 | GPL-3.0 | **Basis (Laufzeit)** |
| [chrissotraidis/sunpad](https://github.com/chrissotraidis/sunpad) | `ec20f8d843fa40a484c7455cacb90b19884867ec` | 2026-09-04 | GPL-3.0 | **Referenzport (Apple)** |

### 1.1 Die Decompilation trägt keinen Port

decomp.dev weist für `doldecomp/sms` **38,82 % dekompiliert bei 17,45 % vollständig
gelinkt** aus. Unterstützt werden `GMSJ01` (JP Rev 0) und `GMSP01` (PAL, im README
selbst als "slightly broken" markiert) — **die US-Fassung `GMSE01` gar nicht**.

Das ist der entscheidende Unterschied zu Dusklight: Dusklight steht auf einer nahezu
vollständigen Twilight-Princess-Decompilation und kann deshalb echten C++-Spielcode
gegen Aurora linken. Bei 17,45 % gelinktem Code existiert schlicht kein lauffähiges
Spiel. Eine matching Decompilation ist ohnehin nur der Nachweis, dass der Quellcode
byte-identisch zum Original kompiliert — sie ist **kein PC- oder Android-tauglicher
Spielcode**, weil sie gegen GameCube-SDK-Header, PowerPC-ABI und Big-Endian-
Speicherlayout gebaut ist.

**Folge:** Der Dusklight-Weg ist für Sunshine heute versperrt und wird es auf Jahre
bleiben. Der Rest der Analyse setzt darauf nicht auf.

### 1.2 Aurora passt nicht zu einem rekompilierten Binary

Aurora exportiert `include/dolphin/gx/*.h`, `include/dolphin/ai.h`, `card.h`, `dvd.h`
— es ist eine **quellcode-seitige Neuimplementierung des GameCube-SDK**, die auf
WebGPU/Dawn abbildet. Das setzt voraus, dass dekompilierter Spielcode `GXBegin(...)`
als linkbares Symbol aufruft.

Ein statisch rekompiliertes Binary tut das nicht: Es führt den rekompilierten
PowerPC-Code des SDK aus, der in die GX-FIFO-Register schreibt. Es gibt keine
Aufrufstelle, an die Aurora sich binden könnte.

**Bewertung:** Aurora ist technisch stark, aber für diesen Ansatz die falsche Schicht.
Theoretisch ließe sich die gesamte GX-SDK-Oberfläche per Symbol-Patch auf Aurora
umleiten; das sind mehrere hundert Funktionen inklusive Matrix- und Vertex-Zustand und
wäre ein eigenes Großprojekt mit hohem Regressionsrisiko. Wir verwenden Aurora in v1
**nicht**. Als späterer optionaler nativer Renderer bleibt es notiert.

### 1.3 Statische Recompilation ist der belegte Weg

DolRecomp übersetzt PowerPC-Code eines DOL ahead-of-time nach C beziehungsweise über
ein LLVM-Backend; ModernGekko liefert die Laufzeit (Dolphin-Abstammung über
RecompCore), die den erzeugten Modulcode als CPU-Kern `PowerPC::CPUCore::StaticRecomp`
ausführt.

Dass das für **genau dieses Spiel** funktioniert, ist keine Vermutung: SunPad bootet
Sunshine (`GMSE01`, USA Rev 0) auf physischem iPad mit Bild, Eingabe und Ton, und
ModernGekkos Hall of Fame nennt einen Sunshine-Recomp (ReShine, Linux).

## 2. Architekturentscheidung

**Statische Recompilation als Spielkern, plus symbolgesteuerte native Mods für die
Modernisierung.** Keine Decompilation, kein Aurora in v1.

```
Spielkopie des Nutzers (eine verifizierte Revision)
        |  Import + Integritaetspruefung + mario.MAP-Extraktion
        v
DolRecomp  --(MAP)-->  benannte Adresskonstanten
        |
        v  generiertes C  (nie im Repository)
        v
Windows x86-64 (MSVC)
        |
        v
ModernGekko-Laufzeit
   + Sunshine-Mods (Framerate, Widescreen, HUD)
        |
        v
Windows-Shell
```

### 2.1 Der Eingriffspunkt für die Anforderungen 1 bis 3

ModernGekkos Mod-ABI (`include/moderngekko/mod_abi.h`) bietet `RECOMP_PATCH`
(Spielfunktion durch nativen C-Code ersetzen), `RECOMP_HOOK` und
`RECOMP_HOOK_RETURN` (Entry- und Return-Hooks), dazu Exporte, Importe und Events —
alle auf `CPUState*`. Damit lassen sich Spielschleife, Projektionsaufbau und
HUD-Layout abfangen. Das ist dasselbe Muster, mit dem Zelda64Recomp entkoppeltes
Rendering umgesetzt hat.

Die Hooks binden an **rohe 32-Bit-Adressen** (`ModernGekkoModPatch.address`).
Symbolnamen sind eine Komfortfunktion beim Schreiben der Mods, keine Voraussetzung
des Mechanismus.

#### Korrektur: Die US-Disc liefert keine Symbol-Map

Eine frühere Fassung dieses Dokuments nahm an, die Retail-Disc enthalte eine
Symbol-Map (`mario.MAP`), aus der sich beim Import benannte Adressen für die
Revision des Nutzers gewinnen ließen. **Für `GMSE01` ist das nachweislich falsch.**

Am 2026-09-09 an einer echten Kopie geprüft: Die USA-Disc enthält 174 Dateien —
`opening.bnr`, `data/` (146) und `AudioRes/` (27). Es gibt keine `mario.MAP` und
keine andere Symboldatei. Das `extract_symbols.sh` der Decompilation bezieht sich
auf die japanische Fassung; genau deshalb zielt `doldecomp/sms` auf `GMSJ01`.

Damit bleibt die Adressbeschaffung für GMSE01 ein offener Arbeitspunkt. Drei
Quellen stehen zur Verfügung:

1. **Bekannte GMSE01-Adressen aus der Community.** Dolphin liefert
   `Data/Sys/GameSettings/GMSE01.ini` mit ActionReplay- und Gecko-Codes, darunter
   **zwei `$Widescreen`-Codes**. Das sind spielseitige Patches auf konkrete
   GMSE01-Adressen — ein belastbarer Ausgangspunkt gerade für Anforderung 3.
2. **Übertragung der CC0-Symbole von GMSJ01 nach GMSE01** durch Abgleich von
   Funktionsrümpfen. Die 38.262 Einträge der Decompilation sind adressverschieden,
   aber namens- und strukturgleich.
3. **DolRecomps eigene Analyse**: Ohne `--map` erzeugt der Recompiler
   adressbasierte Namen; die Aufrufgraphen bleiben nutzbar.

Der Wegfall der Symbol-Map macht die Anforderungen 1 und 3 nicht unmöglich, aber
aufwendiger: Vor dem Hooken steht jeweils eine Adressermittlung.

### 2.2 Zielrevision

`GMSE01` (USA Rev 0), SHA-256 `67cec1634e641227a4cd51e6a0b277730cb9a1adaa867530c9e66de45373e51d`,
1.459.978.240 Bytes — die von SunPad verifizierte und nachweislich lauffähige Fassung.

Die CC0-Symbolliste der Decompilation gilt für `GMSJ01` und `GMSP01` und ist **nicht
adressgleich**; sie dient ausschließlich als Namens- und Strukturreferenz. Die realen
Adressen stammen aus der `mario.MAP` der importierten Disc.

## 3. Konkret fehlende Komponenten

| # | Anforderung | Vorhanden | Fehlt |
|---|---|---|---|
| 5 | Windows | `PlatformWin32.cpp` in ModernGekko, Windows-Build in DolRecomp | Eigenständige Shell, Fenster- und Vollbildmodi, Einstellungs-UI |
| 2 | Hohe Auflösung | `GraphicsSettings.internal_resolution_scale`, Dolphins `iEFBScale` | Trennung interne und Ausgabe-Auflösung in der UI; HUD-Skalierung |
| 3 | Echtes Widescreen | Dolphins `bWidescreenHack`, `bCropToAspectRatio` | **Der generische Hack ist nachweislich defekt** (siehe 3.1) |
| 1 | Unbegrenzte Framerate | **Nichts** | Vollständig zu bauen (siehe 3.2) |
| 4 | HUD und Anker | — | Sunshine-spezifische J2D/JUT-Hooks |
| 7 | Analoge Schultertaste | Dolphin-PAD-Schicht führt Analogwerte | Belegungen, Touch-Ersatz, Totzonen |
| 9 | Datenimport | Disc-Unterstützung und SHA-256 in ModernGekko | Einrichtungsdialog, Fehlermeldungen, MAP-Extraktion |

### 3.1 Widescreen ist ein belegtes, kein vermutetes Problem

SunPads `KNOWN_ISSUES.md` (Punkt 9) dokumentiert für den experimentellen Breitbildmodus
**abgetrennte Schatten, harte Projektionsnähte und duplizierte Geometrie** und ordnet
das ausdrücklich dem dokumentierten Fehlerbild von Dolphins generischem
Widescreen-Hack zu. Zusätzlich musste ein Hitzeflimmer-Effekt unterdrückt werden, der
eine Geisterkopie der Szene erzeugte. 4:3 ist dort weiterhin die stabile
Voreinstellung.

Das bestätigt die Vorgabe des Auftrags: pauschales Strecken oder Hineinzoomen genügt
nicht. Notwendig ist ein Eingriff an der Projektionsmatrix des Spiels plus Korrektur
der Sichtbarkeitsprüfungen (Culling) — also genau der Mod-Weg aus 2.1, nicht der
Emulator-Hack. Himmel, Wasser, Spiegelungen, Schatten und Bildschirmeffekte sind
einzeln zu prüfen.

### 3.2 Unbegrenzte Framerate ist der härteste Posten

Kein untersuchtes Projekt liefert das. Sunshine ist an 30 Hz Spiellogik gebunden;
Physik, Timer und Wasserverbrauch hängen an dieser Taktung. Die Anforderung verlangt
ausdrücklich mehr als eine höhere FPS-Anzeige.

Realistischer Weg: feste Simulationsrate beibehalten, Rendering entkoppeln, Zustände
zwischen zwei Simulationsschritten interpolieren und Kameraschnitte, Teleports sowie
Szenenwechsel über ein Verwerfen-Signal von der Interpolation ausnehmen. Alle drei
Bausteine — Schleifen-Hook, Zustandserfassung, Verwerfen-Signal — sind Eigenbau.

Erschwerend: Der rekompilierte Code rendert über die Dolphin-Videoschicht, deren
Bildabschluss am emulierten VI-Interrupt hängt. Ob sich das sauber entkoppeln lässt
oder ob dafür zusätzlich in die Präsentationsschicht eingegriffen werden muss, ist
**noch nicht verifiziert** und das größte offene technische Risiko des Projekts.

### 3.3 Leistung

Der Wegfall von Android nimmt das größte Leistungsrisiko heraus: SunPad dokumentiert,
dass ein iPhone 14 schon bei 1× deutlich unter Volltempo laufen kann. Auf einem
Windows-PC mit x86-64 entfällt außerdem der dort nötige Interpreter-Rückfall ohne JIT.

Zwei Kostenstellen bleiben trotzdem zu messen, bevor Zusagen zu 4K oder hohen
Bildraten sinnvoll sind:

- **Interpreter-Rückfall** für nicht rekompilierte oder selbstmodifizierende
  Codebereiche (SMC). Wie viel Sunshine davon auslöst, ist ungeprüft.
- **Rekompilat-Qualität**: Das LLVM-Backend ist für die ModernGekko-Laufzeit
  ohnehin verpflichtend (siehe Abschnitt 5); die Wahl zwischen C- und
  LLVM-Backend stellt sich hier nicht.

## 4. Lizenzlage

DolRecomp, ModernGekko und SunPad stehen unter **GPL-3.0**; die Dolphin-Abstammung ist
GPL-2.0-or-later und im kombinierten Baum GPLv3-kompatibel. Ein Port, der ModernGekko
einbindet, **muss folglich GPL-3.0-or-later sein**. Aurora (MIT) und die Decompilation
(CC0) wären permissiver, stehen aber nicht auf dem kritischen Pfad.

Es werden **keine Original-Spieldaten** verteilt und keine automatisch
heruntergeladen. Disc-Abbild, extrahiertes Dateisystem, `mario.MAP`, Speicherstände
und das generierte Modul bleiben lokal und außerhalb der Versionskontrolle.

## 5. Toolchain auf diesem Rechner

Eine frühere Fassung dieses Dokuments meldete, es sei kein Compiler vorhanden. Das
war falsch: Die Prüfung hatte nur `C:\Program Files\Microsoft Visual Studio`
durchsucht, nicht den tatsächlichen Pfad unter `Program Files (x86)`.

Stand 2026-09-09, verifiziert durch echte Builds:

| Werkzeug | Version | Status |
|---|---|---|
| MSVC `cl.exe` x64 | 19.44.35228 (Toolset 14.44.35207) | vorhanden, baut |
| Windows SDK | 10.0.26100.0 | vorhanden |
| CMake | 4.4.3 (nachinstalliert), zusätzlich VS-eigenes | vorhanden |
| Ninja | 1.13.2 | vorhanden |
| Python | 3.14.7 | vorhanden |
| OpenJDK | 21.0.12.1 | vorhanden |
| Android SDK | vorhanden (Plattformen, Build-Tools) | NDK fehlt |

**Meilenstein 2 ist damit nicht blockiert.** DolRecomp (`40637c46`) ist mit
MSVC/Ninja im Release-Modus gebaut; die mitgelieferte Testsuite läuft mit
**19 von 19 bestandenen Tests** durch. Der Recompiler steht als `dolrecomp.exe`
bereit.

Offen bleibt nur:

- **LLVM 19 oder 20 Entwicklungsdateien.** Korrektur einer früheren Fassung: Das
  LLVM-Backend ist für diesen Port **keine Leistungsoption, sondern Pflicht**.
  DolRecomp bricht mit `error: the ModernGekko runtime requires the LLVM backend`
  ab, sobald `--runtime moderngekko` ohne LLVM-Backend gewählt wird. Der
  Recompiler muss also mit `-DDOLRECOMP_ENABLE_LLVM=ON` gebaut werden;
  akzeptiert wird ausschließlich LLVM 19.x oder 20.x.

Ein Android NDK wird nach der Umfangsänderung nicht mehr benötigt.

Vorgezogen und unabhängig davon umgesetzt: der Datenimport aus Anforderung 9, der
reine Python-Logik ist und lokal getestet ist.

## 6. Bewertung der Meilensteine

| Meilenstein | Einschätzung |
|---|---|
| 1 Analyse | Erledigt (dieses Dokument) |
| 2 Builds | Begonnen: DolRecomp gebaut und getestet; ModernGekko im Bau |
| 3 Import und Szene unter Windows | Import umgesetzt und getestet; Szene offen |
| 4 Android | **Entfallen** (Umfangsänderung) |
| 5 Auflösung, Widescreen, Framerate | Widescreen mittel, Framerate hoch riskant |
| 6 Vervollständigung | Nach 3 und 5 |

Die Einordnung "schwierig" bezieht sich auf Umfang, nicht auf Unmöglichkeit: Der
Referenzport zeigt, dass der Kern trägt. Die Modernisierungsanforderungen 1 bis 4 sind
jedoch Neuentwicklung, nicht Konfiguration.
