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

Die [lokale Windows-Prüfung vom 23.09.2026](VERIFICATION_2026-09-23.md) dokumentiert den aktuellen eingeschränkten Testlauf und die noch offenen Echtspiel-Nachweise getrennt vom ursprünglichen ZIP-Testbericht.

Browserprüfungen benutzen echte Chromium-Darstellung und lokalen Python-HTTP-Dienst. In eingeschränkten Umgebungen ist ein dokumentierter Test-Transportadapter nötig; dieser testet dann ausdrücklich nicht die reale Browsernavigation/-Sitzungsübergabe. Ein Edge-/Chrome-Appfenster unter Windows und Spielstart sind separat auf einem echten Rechner zu testen.

`TEST_REPORT.json` enthält die ursprüngliche 0.4.0-Abnahme. Die aktuelle Nachprüfung der Automatik steht in `VERIFICATION_2026-09-23.md`, `BROWSER_TEST_REPORT.json` und `UNIT_TEST_LOG.txt`. Screenshots sind als künstliche Testinstallation gekennzeichnet. CI ist für Linux und Windows vorbereitet; eine lokale Browserprobe ersetzt keinen echten Spieltest.

Freigabe als spielgetestetes Paket erfordert einen realen Durchlauf der [Playtest-Checkliste](PLAYTEST_CHECKLIST.md). Kein Wert `game_tested=true` wird aus bestandenen Unit-Tests abgeleitet.
