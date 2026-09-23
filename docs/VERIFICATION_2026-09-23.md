# Lokale Prüfung vom 23.09.2026

## Herkunft und Umfang

- Grundlage: `TCS_Remaster_Installer_0.4.0.zip`, SHA-256 `F9FC0F83530CCF64A8D5BBC7909D480BCCB7D8C2400BDD681131F6392FF758E5`.
- Alle 90 ursprünglich in `SHA256SUMS.txt` aufgeführten Dateien stimmten vor Änderungen mit dem Archiv überein.
- Testrechner: Windows, Python 3.13.2. Die Tests nutzen künstliche Spiel- und Moddateien. Der Assistent wurde zusätzlich über einen lokalen Loopback-Dienst im Codex In-App-Browser geöffnet.

## Ergebnis

| Prüfung | Ergebnis |
| --- | --- |
| Python-Tests im eingeschränkten Workspace mit beschreibbaren temporären Verzeichnissen und simuliertem „Spiel läuft nicht“ | 354 Tests ausgeführt, 353 erfolgreich, 1 regulär übersprungen |
| Echte Windows-Prozessabfrage außerhalb der Sandbox | `tasklist /FI "IMAGENAME eq LEGOStarWarsSaga.exe" /FO CSV /NH`: Exitcode 0, kein laufendes Spiel gemeldet |
| Lokaler HTTP-Dienst und Browseroberfläche | Start erfolgreich, verbundenes UI, sieben Fortschrittsstufen und GitHub-Info-Link sichtbar |
| Exportfunktion | 95 freigegebene Dateien im ZIP; alle 94 zugehörigen SHA-256-Einträge stimmen; keine Spielarchive, `.local`-Dateien oder EXE/DLL im Export |
| Browser-Smoke-Suite mit Playwright | Nicht ausgeführt: Windows-Sandbox verweigert dem Chromium-Hilfsprozess den Start (`WinError 5`) |
| Echte Spieldateien, Original-Modarchive, Nexus-Konto, Appfenster und Gameplay | Nicht getestet |

Die zwei aus dem eingeschränkten Python-Lauf ausgenommenen Tests benötigen Windows-Funktionen, die die Sandbox sperrt: die **echte** `tasklist`-Prüfung und die Erstellung eines Symlinks. Die Produktlogik für den Prozesscheck blieb unverändert und stoppt bei einer fehlgeschlagenen Abfrage sicher. Die Testdaten für den dreiseitigen Textvergleich verwenden nun plattformunabhängige LF-Bytes; ein Test für Browser-Argumente vergleicht Pfade statt Slash-Schreibweisen.

## Verwendung und Freigabegrenze

Der Installer kann als **technische Vorschau** mit einer eigenen Spielkopie ausprobiert werden. Vorher Spiel und alten Assistenten schließen, neue ZIP vollständig separat entpacken und `README.html` lesen. Bei bereits vorbereiteten Daten `UPDATE.cmd` für den bisherigen **Installerordner** verwenden; keine Spielarchive, Backups oder `.local`-Daten manuell löschen.

Ein bestandener Dateitest ist keine Bestätigung, dass alle Mods im Spiel funktionieren. Vor einer öffentlichen Aussage „spielbar“ muss ein Durchlauf der [Playtest-Checkliste](PLAYTEST_CHECKLIST.md) mit eigenen Originaldateien auf Windows erfolgen. Unbekannte Modvarianten, Binärkonflikte und externe Runtime-Anforderungen bleiben bewusst zur Prüfung offen.
