# Abnahmelauf

Der in [PLAN.md](../../docs/PLAN.md), Abschnitt 2.5 geforderte reproduzierbare
Abnahmelauf: Jedes Arbeitspaket, das Laufzeit, Modul oder Mods berührt, muss
ihn bestehen.

## Aufbau

Ein **Szenario** ist eine JSON-Datei neben diesem README. Sie nennt die
Eingabefolge, die zu lesenden Adressen und die Zusagen — und sonst nichts.
Spieldaten enthält sie nicht.

```
python tools/acceptance list
python tools/acceptance run  <szenario.json> --runtime <moderngekko-run> \
    --game <extrahiertes-spiel> --module <modul> --output <neues-verzeichnis>
python tools/acceptance check <szenario.json> --run <laufverzeichnis>
```

`run` startet den Lauf über `tools/diagnostics/headless_probe.py` und prüft
anschließend. `check` prüft ein vorhandenes Laufverzeichnis erneut, etwa nach
einer Änderung der Zusagen. Beide enden mit Exitcode 1, wenn eine Zusage nicht
gehalten wurde.

Die Trennung ist Absicht: `check.py` entscheidet und ist ohne Spielkopie
testbar (`tests/test_acceptance.py`, 10 Tests); `__main__.py` führt aus.

## Zusagen

Jeder Eintrag unter `expect` ist freiwillig. Fehlt er, wird nichts geprüft.
So steht in einem Szenario genau das, was wirklich zugesagt wird.

| Zusage | Bedeutung |
|---|---|
| `exit_code` | Exitcode der Laufzeit |
| `no_error` | die Sonde meldet keinen Fehler |
| `min_frames` | mindestens so viele eindeutige Bilder im Messfenster |
| `reads` | Name → erwarteter Wert (`u32` als `0x…`, sonst Hex der Bytes) |
| `smc_failed` | Zähler aus der `[staticrecomp] shutdown`-Zeile |
| `max_fallback` | Obergrenze für Interpreter-Einzelschritte. **Nicht** für native Ausführung verwendbar: siehe [13-STATISCHER-KERN.md](../../docs/13-STATISCHER-KERN.md) |
| `min_native_share` | Mindestanteil der Gasttakte, die im Rekompilat verbucht wurden: `cycles` geteilt durch `ticks` aus der Zählerzeile. Das ist die Zusage für native Ausführung ([16-RUECKWEG.md](../../docs/16-RUECKWEG.md)). Meldet die Laufzeit kein `ticks=`, fällt die Zusage durch, statt aus der Bildzahl geschätzt zu werden |
| `projection_aspect` | Sichtverhältnis der Hauptkamera aus einer FIFO-Aufzeichnung der Eingabefolge. Genommen wird die perspektivische Projektion mit den meisten Zeichenbefehlen; orthografische (HUD, Filme) haben keines. Damit wird Widescreen an einer Zahl geprüft statt an einem Bild ([19-ULTRAWIDE.md](../../docs/19-ULTRAWIDE.md)) |
| `audio_min_seconds` | Länge des DSP-Mitschnitts |
| `audio_max_silence_share` | Anteil stiller Blöcke |
| `audio_seconds_per_present` | Schranken für Ton je Bildausgabe. Enthält den Startversatz; die reine Steigung liefert `tools/audio rate` |
| `stack_low_water` | tiefste beschriebene Adresse im Stapelbereich, gemessen mit Mindestabstand zu `floor`. Damit wird der eingebackene Widescreen-Code gegen den Stapel gesichert ([10](../../docs/10-KOPFLOSER-PRUEFSTAND.md), Befund 1) |

## Vorhandene Szenarien

| Datei | Inhalt |
|---|---|
| `boot.json` | Start bis Frame 600 ohne Eingabe. Prüft Arena- und Heapgrenzen gegen die in [10-KOPFLOSER-PRUEFSTAND.md](../../docs/10-KOPFLOSER-PRUEFSTAND.md) belegten Werte, dazu Ton und Zähler. |
| `spielstart.json` | Eingabefolge bis in die Flugplatz-Sequenz (`fixtures/game-start.json`). Prüft unter anderem, dass `gpMarioAddress` (`0x8040E108`) auf ein Objekt in MEM1 zeigt. |
| `nativ.json` | Kurzer Start, der **den Anteil nativer Ausführung zusagt**. Braucht den Rückweg, der seit dem 2026-09-16 Voreinstellung ist ([16-RUECKWEG.md](../../docs/16-RUECKWEG.md)); mit `STATICRECOMP_NO_YIELD=1` fällt dasselbe Szenario ausdrücklich durch — sonst wäre die Zusage wertlos. |
| `widescreen.json` | Eingabefolge bis zur 3D-Szene der Dateiauswahl, dort 20 Bilder als FIFO aufgezeichnet, und sagt das **Sichtverhältnis 1,777778** zu. Gilt für eine mit 16:9 gebackene Spielkopie; gegen eine 64:27-Kopie fällt sie ausdrücklich durch. |

Am 2026-09-15 auf Linux mit dem gewöhnlichen Modul ausgeführt:

| Szenario | Ergebnis | Messwerte |
|---|---|---|
| `boot` | **bestanden**, 10 von 10 | 607 Bilder, Arena und Heap wie in Dokument 10, 22,35 s Ton, 34,1 % Stille |
| `spielstart` | **bestanden**, 9 von 9 | 2.401 Bilder, `gpMarioAddress` = `0x80E9AD44`, 82,60 s Ton, 11,5 % Stille |

Am 2026-09-16 mit dem `dcbf`-Modul (`dolrecomp-dcbf-bleibt-im-modul.patch`,
Dokument 21) wiederholt — `nativ` 8 von 8 (35,45 % nativ), `boot` 10 von 10
(606 Bilder, 22,32 s Ton), `spielstart` 11 von 11 (`gpMarioAddress` =
`0x80E9AD44`, 2.396 Bilder, 82,53 s Ton); der Boot-Tonstrom ist gegen das
alte Modul zu 100,00 % abtastwertgleich.

Am selben Tag mit dem Rückweg (Dokument 16) wiederholt:

| Szenario | Ergebnis | Messwerte |
|---|---|---|
| `boot` | **bestanden**, 10 von 10 | 605 Bilder, Arena und Heap byteweise gleich, 22,29 s Ton |
| `spielstart` | **bestanden**, 11 von 11 | 2.399 Bilder, `gpMarioAddress` = `0x80E9AD44` — **derselbe Wert**, 82,62 s Ton |
| `nativ` | **bestanden**, 8 von 8 | 35,58 % der Gasttakte nativ; ohne Rückweg fällt dasselbe Szenario mit 0,00 % durch |

Die Läufe brauchen rund 1, 12 bzw. 1 Minute.

## Grenzen

- Kein Bild. Der Prüfstand ist kopflos; Bildabnahme bleibt Aufgabe am
  Windows-Rechner ([10](../../docs/10-KOPFLOSER-PRUEFSTAND.md)).
- Kein Ton am Gerät. Geprüft wird der emulierte Strom, nicht der Ausgabeweg
  ([12](../../docs/12-TON.md)).
- Die Zusagen sind so gut wie die Messung, aus der sie stammen. Eine falsche
  Zusage fällt beim ersten Lauf auf — beim Aufbau dieses Werkzeugs dreimal
  geschehen: In `boot.json` standen erst die Adressen statt der dort
  stehenden Werte; in `spielstart.json` waren die Schwellen für Bilder und
  Tonlänge geraten (3.500 statt 2.401 Bilder, 100 statt 82,6 s); und
  `gpMarioAddress` wurde zunächst an der falschen Adresse gelesen. Genau
  dafür ist der Lauf da.

## `fixtures/game-airstrip.json`

Führt `game-start.json` fort: Start-Taste im Vorspann, A-Tasten, Stick, in
Schritten von höchstens 300 Bildern (die Sonde wartet je Schritt 120 s auf
die Bestätigung; auf Lavapipe sind das rund 30 s). Erreicht nach etwa 4.300
Bildern den Flugplatz von Isle Delfino als Spielszene (Peach, Mario,
Sprechblase). Keine Zusage, nur Messfolge für docs/20.
