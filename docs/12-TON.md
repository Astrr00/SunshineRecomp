# Ton: gemessen, nicht angenommen

Stand: 2026-09-15. WP1 aus [PLAN.md](PLAN.md), Abschnitt 4. Der Plan sah die
Messung am Windows-Rechner per WASAPI-Loopback vor. Sie geht besser: Der
Emulator schreibt den **emulierten** Tonstrom selbst als WAV, unabhängig vom
Ausgabegerät. Das ist genauer als eine Aufnahme über die Soundkarte und läuft
kopflos ([10-KOPFLOSER-PRUEFSTAND.md](10-KOPFLOSER-PRUEFSTAND.md)).

Der Plan nannte als Ablage `docs/09-TON.md`; diese Nummer war bereits vergeben.

**Keine Spieldaten im Repository.** Die Mitschnitte sind Spielton und blieben
in der Sitzung. Hier stehen nur Messzahlen.

## Was der Mitschnitt ist

`[DSP] DumpAudio=True` in `Dolphin.ini` lässt `AudioCommon` zwei Dateien nach
`<Benutzerverzeichnis>/Dump/Audio/` schreiben:

| Datei | Inhalt | Rate |
|---|---|---|
| `…_dspdump.wav` | der AI-DMA-Strom, den die DSP-Emulation liefert | 32.028 Hz |
| `…_dtkdump.wav` | der ADPCM-Strom vom Disc-Streaming (DTK) | 48.042 Hz |

Beide werden **vor** dem Mischen und Nachtakten geschrieben, unabhängig vom
Ausgabe-Backend (der Schreibblock liegt außerhalb von
`IsOutputSampleRateValid`), und **einschließlich Stille**: `SetSkipSilence`
wird ausschließlich mit `false` aufgerufen. Damit ist die Länge einer Datei
ein direktes Maß für emulierte Zeit.

Die Raten sind nicht gerundet, sondern die echten GameCube-Raten:
`Mixer::FIXED_SAMPLE_RATE_DIVIDEND` ist `54.000.000 · 2`, der Teiler für den
DSP-Pfad `3372` und für den Disc-Pfad `2248`.

| | Datei | Hardware |
|---|---|---|
| DSP | 32.028 Hz | 108.000.000 / 3372 = 32.028,47 Hz |
| DTK | 48.042 Hz | 108.000.000 / 2248 = 48.042,70 Hz |

Den WAV-Kopf schließt der Emulator erst beim Herunterfahren; ein harter
Abbruch lässt die Platzhalter stehen (rund 95 MiB angebliche Daten). Der
Leser in `tools/audio/wav.py` nimmt deshalb die tatsächliche Dateilänge und
meldet den Fall als `truncated_header`.

## Werkzeug

`tools/audio`, Python ohne Fremdbibliotheken, 14 Tests an synthetischen
Signalen:

| Modul | Zweck |
|---|---|
| `wav.py` | 16-Bit-PCM lesen und schreiben, unvollständige Köpfe verkraften |
| `measure.py` | Hüllkurve, Stille, Übersteuerung, Fourier-Transformation, spektraler Schwerpunkt, Tonhöhenverhältnis, zeitliche Ausrichtung, abtastwertgleicher Anfang, Tempo als Steigung zweier Läufe |
| `__main__.py` | `inspect`, `compare`, `rate` |

```
python tools/audio inspect <mitschnitt.wav>
python tools/audio compare <a.wav> <b.wav> [--report <json>]
python tools/audio rate --run <manifest.json> --run <manifest.json> [--stream dsp|dtk]
```

`headless_probe.py` hat dafür `--audio-dump` (Mitschnitt einschalten),
`--jit` (Vergleichslauf ohne statisches Modul) und `--uncapped`
(Geschwindigkeitsbegrenzung aufheben) bekommen und schreibt jetzt die
Wanduhrzeit des Messfensters mit.

## Wie das Tempo gemessen wurde

Drei Fallstricke, alle ausgeräumt:

1. **Der Mitschnitt beginnt beim Startvorgang**, der Bildzähler erst später.
   Der Versatz fällt heraus, wenn man zwei verschieden lange Läufe nimmt und
   die Steigung bildet (`tools/audio rate`).
2. **`frame_count` ist keine Uhr.** Es zählt nur *eindeutige* Bilder
   (`VideoEvents.h`: „The number of (unique) frames since the emulated console
   booted"), hängt also am Inhalt. `present_count` zählt jede Bildausgabe.
3. **Die Wanduhr hilft nicht.** Die Emulation ist auf 100 % gedrosselt, aber
   der Regler zielt auf die emulierte Zeit des Kerns selbst; er ist also keine
   unabhängige Uhr. Ein früher Versuch, der die Wanduhr heranzog, lief
   außerdem neben anderen Messungen und war schon deshalb wertlos.

Die unabhängige Uhr liefert **die Disc**: Alle Filme deklarieren im
THP-Kopf ihre Bildrate, und der Vorspann läuft beim Start von selbst.

| Film | deklarierte Rate | Bilder | Tonabtastwerte |
|---|---|---|---|
| `Entrance.thp` | 29,97 fps | 2.816 | 3.009.416 bei 32.000 Hz |
| `openingBA.thp` | 29,97 fps | 3.138 | 3.353.532 |
| `autodemoA.thp` | 29,97 fps | 1.199 | 1.281.353 |

Während des Vorspanns erzeugt das Spiel je Filmbild genau ein eindeutiges
Bild. Damit ist `frame_count` in diesem Abschnitt eine Uhr mit bekanntem
Gang.

## Messwerte

Zwei Läufe je Kern (600 und 3.600 Bilder), gleiche Eingaben (keine), gleiche
Konfiguration, nur der CPU-Kern unterscheidet sich (`CPUCore=6` gegen `1`):

| | statische Rekompilation | JIT64 |
|---|---|---|
| Bilder je Sekunde Ton | 29,8917 | 29,8850 |
| Abweichung von 29,97 (Film) | −0,26 % | −0,28 % |
| Bildausgaben je Sekunde Ton | 89,8344 | 89,8142 |
| Bildausgaben je eindeutigem Bild | 3,0053 | 3,0053 |

Der Vergleich der beiden Mitschnitte:

| Gegenstand | Wert |
|---|---|
| abtastwertgleicher Anfang | **108,812 s** von 122,6 s |
| gleiche Abtastwerte insgesamt | **92,50 %** |
| Korrelation der Hüllkurven (100-ms-Blöcke) | 0,9998 |
| zeitlicher Versatz | 0 ms |
| Ähnlichkeit der Spektren im gemeinsamen Bereich | 0,997 |

Der DTK-Strom ist in allen Läufen **vollständig still** (Spitzenwert 0,
100 % Stille) und exakt so lang wie der DSP-Strom (122,641 s gegen
122,642 s). Sunshine gibt seinen Ton also über den DSP-Pfad aus, auch den
Filmton; der Disc-Streaming-Pfad läuft leer mit.

Unterläufe: keine Meldung in den Protokollen von fünf Läufen.

## Was das beantwortet

1. **Kein Zeitbasisfehler.** Der Plan nennt SunPads zwölffach zu schnelle
   Timebase als Warnung. Nichts dergleichen: Ton und Bild laufen im
   Rekompilat innerhalb von 0,3 % zu der Rate, die der Film selbst auf der
   Disc deklariert. 0,3 % sind rund 5 Cent und liegen weit unter der
   Hörschwelle.
2. **Das Rekompilat klingt nicht anders als der Referenzkern.** Die ersten
   108,8 Sekunden sind abtastwertgleich mit dem JIT64-Lauf. Das ist schärfer
   als jeder Spektrenvergleich: Es ist dasselbe Signal, Wert für Wert. Die
   Abweichung danach kommt daher, dass die beiden Läufe an leicht
   verschiedenen Stellen endeten.
3. **Die Abtastraten stimmen.** 32.028 und 48.042 Hz sind die aus dem
   54-MHz-Takt abgeleiteten Hardwareraten, nicht gerundete Werte.

Die 0,26 % Abweichung des Bildzählers vom Filmwert entsprechen rund acht
wiederholten Bildern auf 3.000 und passen zu den 3,0053 Bildausgaben je
eindeutigem Bild (statt genau 3,0).

## Was damit nicht belegt ist

- **Der echte Ausgabeweg.** Gemessen wurde der Strom *vor* Mischer,
  Nachtaktung und Gerät. Kopflos ist das Backend `No Audio Output`; es gibt
  keinen Verbraucher, also sagen die fehlenden Unterlaufmeldungen nichts
  über cubeb oder WASAPI. Aussetzer durch zu kleine Puffer auf einem echten
  Gerät sind damit ausdrücklich **nicht** ausgeschlossen.
- **Die Hörprobe.** Ob es richtig *klingt*, kann nur ein Mensch sagen. Die
  Mitschnitte bleiben lokal; der Auftraggeber kann sie mit diesem Werkzeug
  selbst erzeugen (`--audio-dump`) und anhören.
- **DSP-LLE.** Voreinstellung ist HLE. Ein Vergleich gegen LLE steht aus.
- **Interne Skalierung 1 gegen 6.** Der Plan verlangt beide; gemessen wurde
  bei Skalierung 1, weil kopflos kein Bild entsteht. Ein Einfluss der
  Grafiklast auf den Ton ist damit nicht geprüft.
- **Lange Abschnitte und Spielszenen mit Sprachausgabe.** Die Messung deckt
  den Vorspann ab (zwei Minuten). Ein Lauf durch die Flugplatz-Sequenz
  liefert wegen der Eingaben keinen abtastwertgleichen Vergleich mehr: Dort
  gingen die beiden Kerne nach 12,3 s auseinander, weil Tastendrücke auf
  unterschiedliche Bilder fallen.

## Nebenbefund

Ohne Geschwindigkeitsbegrenzung (`--uncapped`, `[Core] EmulationSpeed=0`)
läuft derselbe Abschnitt mit JIT64 rund **6,7-mal schneller** als mit dem
statischen Kern (483 gegen 72 Bildausgaben je Sekunde Wanduhr, je zwei
Läufe). Das ist kein Tonbefund, aber es passt nicht zum Zweck der statischen
Rekompilation und führte zu der Untersuchung in
[13-STATISCHER-KERN.md](13-STATISCHER-KERN.md).
