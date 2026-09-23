# Testumfang

```bash
python -m unittest discover -s tests -v
```

Python-Standardbibliothek für die Kern-/HTTP-Tests. Browserentwicklertests benötigen separat Playwright und Chromium:

```bash
python -m pip install playwright
python -m playwright install chromium
python tests/browser_smoke.py
```

Die Unit-Tests verwenden eigene künstliche ZIP-/PAK-/Archivlisten, Modtexte und eine **nicht ausführbare** EXE-Attrappe. Sie sind keine Kopie eines Spiels. Windows-spezifische Prozessabfragen werden auf Nicht-Windows übersprungen. 7-Zip-Prozessausgaben werden für den fehlerhaften Listen-/Pfadfall simuliert. Der separate lokale Dateivergleich mit sechs bereits importierten Modarchiven steht im aktuellen Prüfbericht.

Die [lokale Windows-Prüfung vom 23.09.2026](VERIFICATION_2026-09-23.md) dokumentiert die echte Dateiinstallation getrennt vom ursprünglichen ZIP-Testbericht. Der Nutzer hat anschließend Spielstart und Modfunktion in dieser Installation bestätigt. Andere Varianten und die vollständige Playtest-Checkliste sind damit nicht abgedeckt.

Browserprüfungen benutzen echte Chromium-Darstellung und lokalen Python-HTTP-Dienst. In eingeschränkten Umgebungen ist ein dokumentierter Test-Transportadapter nötig; dieser testet dann ausdrücklich nicht die reale Browsernavigation/-Sitzungsübergabe. Ein Edge-/Chrome-Appfenster unter Windows und Spielstart sind separat auf einem echten Rechner zu testen.

`TEST_REPORT.json` enthält die ursprüngliche 0.4.0-Abnahme. Die aktuelle [Nachprüfung](VERIFICATION_2026-09-24.md) und die [lokale Dateiinstallation](VERIFICATION_2026-09-23.md) sind getrennt dokumentiert. Der neue Lauf umfasst 363 Python-Tests (2 übersprungen) und 52 Browser-Prüfungen mit lokalem Test-Transportadapter. Browser-Screenshots zeigen künstliche Testdaten; eine lokale Browserprobe und bestandene Dateihashes ersetzen keinen echten Spieltest. CI ist für Linux und Windows vorbereitet.

Die Nutzerbestätigung gilt für die getestete Installation. Für einen umfassenden Spieltest aller Varianten ist die [Playtest-Checkliste](PLAYTEST_CHECKLIST.md) weiterhin erforderlich. Kein Wert `game_tested=true` wird aus bestandenen Unit-Tests abgeleitet.
