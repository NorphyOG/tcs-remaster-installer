# Öffentliche Fassung · Prüfung am 24.09.2026

## Nutzerbestätigung und Grenzen

Der Nutzer hat nach der lokalen Installation bestätigt, dass **Spiel und Mods in seiner Installation funktionieren**. Der vorherige [Installationsbericht](VERIFICATION_2026-09-23.md) dokumentiert 2.110 installierte und per SHA-256 geprüfte Dateien. Die Bestätigung ist ein tatsächlicher Spieltest dieser einen Installation, keine automatische Aussage über jede Variante, ReShade, andere Rechner oder die vollständige [Playtest-Checkliste](PLAYTEST_CHECKLIST.md).

## Aktuelle Code- und Oberflächenprüfungen

- `python -m unittest discover -s tests -q`: **363 Tests, 0 Fehler, 2 übersprungen**. Die Fixtures verwenden künstliche Daten; Laufzeit etwa 147 Sekunden.
- `TCS_FORCE_BRIDGE=1 python tests/browser_smoke.py`: **52 Browserprüfungen, 0 Fehler**. Der lokale Test-Transportadapter umgeht in der Testumgebung nur die Chromium-Navigationssperre. Echte Browser-Sitzungsübergabe, Download-Dialoge und Spielstart sind dadurch nicht Teil dieser 52 Prüfungen.
- Aktuelle Browserfälle prüfen, dass die Downloadaktion vor optionalen Einstellungen steht und nach der Installation der Spielstart erscheint, während erneute Installation und Rücknahme eingeklappt bleiben.
- Der lokale Assistent wurde im bereits installierten Nutzerzustand geöffnet und zeigt „Bereit zum Spielen“ und die bestätigte Dateiprüfung. Der Nutzer hat den Spieltest selbst bestätigt; Codex hat ihn nicht erneut ausgeführt.

## Öffentlicher Dateiumfang

`publish-allowlist.json` begrenzt die ZIP auf Quellcode, Startskripte, eigene Grafik, Dokumentation und Tests. Ein Git-Historien- und Positivlistencheck fand keine aktuellen unaufgelisteten Dateien oder typischen Schlüssel-/Privatpfad-Muster in Text-Blobs. Das ist keine Garantie für verborgene Inhalte in Binärdateien. Die neuen README-Bilder wurden visuell auf private Pfade und Spielinhalte geprüft; das Banner enthält abstrakte Symbole.

**Keine Spiel- oder Moddateien sind Teil der öffentlichen ZIP.** Die Links führen zu den Originalseiten der Modautoren.
