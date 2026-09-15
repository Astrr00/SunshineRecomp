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
| `audio_min_seconds` | Länge des DSP-Mitschnitts |
| `audio_max_silence_share` | Anteil stiller Blöcke |
| `audio_seconds_per_present` | Schranken für Ton je Bildausgabe. Enthält den Startversatz; die reine Steigung liefert `tools/audio rate` |

## Vorhandene Szenarien

| Datei | Inhalt |
|---|---|
| `boot.json` | Start bis Frame 600 ohne Eingabe. Prüft Arena- und Heapgrenzen gegen die in [10-KOPFLOSER-PRUEFSTAND.md](../../docs/10-KOPFLOSER-PRUEFSTAND.md) belegten Werte, dazu Ton und Zähler. |
| `spielstart.json` | Eingabefolge bis in die Flugplatz-Sequenz (`fixtures/game-start.json`). |

Am 2026-09-15 auf Linux mit dem gewöhnlichen Modul ausgeführt: `boot`
bestanden, zehn von zehn Zusagen.

## Grenzen

- Kein Bild. Der Prüfstand ist kopflos; Bildabnahme bleibt Aufgabe am
  Windows-Rechner ([10](../../docs/10-KOPFLOSER-PRUEFSTAND.md)).
- Kein Ton am Gerät. Geprüft wird der emulierte Strom, nicht der Ausgabeweg
  ([12](../../docs/12-TON.md)).
- Die Zusagen sind so gut wie die Messung, aus der sie stammen. Eine falsche
  Zusage fällt beim ersten Lauf auf — beim Aufbau dieses Werkzeugs zweimal
  geschehen: Erst standen die Adressen statt der dort stehenden Werte in
  `boot.json`.
