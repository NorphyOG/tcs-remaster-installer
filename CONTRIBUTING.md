# Mitentwickeln

Vor einer Änderung den reproduzierbaren Fehlerfall mit künstlichen Daten ergänzen. Tests mit `python -m unittest discover -s tests -v` ausführen. Änderungen an UI zusätzlich in Chromium testen. Keine Original-Spieldateien oder Modarchive committen.

Sicherheitsregeln bleiben verpflichtend: keine globalen Fehlercode-Ausnahmen, kein Pfad-/DLL-Bypass, keine automatische Wahl unbekannter Binärkonflikte. Externe Metadaten und Downloadseiten getrennt von tatsächlich inspizierten Archiven dokumentieren. Version/Dateinummer nie nur durch Vermutung als kompatibel markieren.

Neue öffentliche Dateien in `publish-allowlist.json` aufnehmen; `SHA256SUMS.txt` regenerieren. Private Arbeitsdateien, Browserprofile und Testdiagnosen bleiben draußen. Für Regressionsberichte die Issuevorlage verwenden; kritische Sicherheitsdetails nicht ungeprüft öffentlich posten.
