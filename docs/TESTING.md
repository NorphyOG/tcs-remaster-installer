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

Die Tests verwenden eigene künstliche ZIP-/PAK-/Archivlisten, Modtexte und eine **nicht ausführbare** EXE-Attrappe. Sie sind keine Kopie eines Spiels. Windows-spezifische Prozessabfragen werden auf Nicht-Windows übersprungen. 7-Zip-Prozessausgaben werden für den fehlerhaften Listen-/Pfadfall simuliert; echte Nexus-Modarchive fehlen.

Die [lokale Windows-Prüfung vom 23.09.2026](VERIFICATION_2026-09-23.md) dokumentiert den aktuellen eingeschränkten Testlauf und die noch offenen Echtspiel-Nachweise getrennt vom ursprünglichen ZIP-Testbericht.

Browserprüfungen benutzen echte Chromium-Darstellung und lokalen Python-HTTP-Dienst. In eingeschränkten Umgebungen ist ein dokumentierter Test-Transportadapter nötig; dieser testet dann ausdrücklich nicht die reale Browsernavigation/-Sitzungsübergabe. Ein Edge-/Chrome-Appfenster unter Windows und Spielstart sind separat auf einem echten Rechner zu testen.

Messbare Ergebnisse dieser Auslieferung stehen in `TEST_REPORT.json`, `BROWSER_TEST_REPORT.json` und `UNIT_TEST_LOG.txt`. Screenshots sind als künstliche Testinstallation gekennzeichnet. CI ist für Linux und Windows vorbereitet, aber ein beigelegter Workflow bedeutet nicht, dass eine öffentliche GitHub-CI bereits ausgeführt wurde.

Freigabe als spielgetestetes Paket erfordert einen realen Durchlauf der [Playtest-Checkliste](PLAYTEST_CHECKLIST.md). Kein Wert `game_tested=true` wird aus bestandenen Unit-Tests abgeleitet.
