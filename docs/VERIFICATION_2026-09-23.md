# Lokale Prüfung vom 23.09.2026

## Aktueller Nachtrag: automatisches Zusammenführen und Navigation

Der ursprüngliche ZIP-Befund unten bleibt als Eingangskontrolle erhalten. Nach der UI- und Merge-Änderung wurden **359 Python-Tests** außerhalb der eingeschränkten Dateisandbox ausgeführt: 358 bestanden, einer regulär übersprungen. Der zusätzliche Test zur Symlink-Erstellung wurde ausgelassen, weil diesem Windows-Konto das dafür erforderliche Recht fehlt (`WinError 1314`). Die aktuelle Browser-Smoke-Suite bestand **46 Prüfungen** mit installiertem Chrome auf Windows und einem **lokalen Test-Transportadapter**; Browsernavigation/Sitzungsübergabe und echte OS-Downloads wurden damit nicht geprüft.

Ein gespeicherter lokaler Prüfplan mit **66 offenen Konflikten** wurde zunächst ausschließlich gelesen: Alle 66 Dateikombinationen passen zu den jetzt kodierten Rezeptregeln. Danach wurde ein **frischer Dateivergleich** mit den sechs bereits lokal importierten Archiven ausgeführt: **2.110 Zieldateien, 220 automatische Überlagerungen, 0 offene Konflikte**. Drei alte 7z-Entpackordner waren nicht mehr lesbar. Die gehashten Originalarchive wurden nach einer Windows-ACL-Korrektur erneut geprüft und entpackt; Pfade und Dateigrößen aller 364 betroffenen Einträge stimmten. Das Spielverzeichnis wurde dabei nicht installiert oder gestartet. Die synthetische Browserprobe löste außerdem zwei Autorendatei-Überlagerungen und einen nicht überlappenden Text-Merge automatisch, erstellte eine Mod-ZIP und prüfte deren kombinierten Text. Unbekannte Dateikombinationen bleiben blockiert.

Der schmale Browser-Test bei 390 px hatte keinen horizontalen Seitenüberlauf. Die sechs Navigationsziele bleiben oben erreichbar; die Detailübersicht folgt nach dem aktiven Schritt. Aktuelle [Browser-Prüfungen](BROWSER_TEST_REPORT.json), [Merge-Regeln](MOD_COMPATIBILITY.md), [Vergleichsansicht](03-conflicts.png) und [schmale Navigation](11-narrow-navigation.png) sind beigefügt. Die privaten Spiel- und Modarchive wurden weder eingebaut noch im Spiel gestartet. Ein öffentlicher „spielbar“-Status ist weiterhin nicht begründet.

Das aktualisierte private Prüf-ZIP enthält 98 Dateien der Positivliste und 97 verifizierte SHA-256-Einträge. `.local`, Laufzeitumgebung, Modarchive und Spieldaten stehen nicht auf der Positivliste.

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
| Echte Spieldateien, Original-Modarchive, Nexus-Konto, Appfenster und Gameplay | Zum Zeitpunkt der Eingangskontrolle nicht getestet; der spätere lokale Mod-Dateivergleich steht im Nachtrag oben |

Die zwei aus dem eingeschränkten Python-Lauf ausgenommenen Tests benötigen Windows-Funktionen, die die Sandbox sperrt: die **echte** `tasklist`-Prüfung und die Erstellung eines Symlinks. Die Produktlogik für den Prozesscheck blieb unverändert und stoppt bei einer fehlgeschlagenen Abfrage sicher. Die Testdaten für den dreiseitigen Textvergleich verwenden nun plattformunabhängige LF-Bytes; ein Test für Browser-Argumente vergleicht Pfade statt Slash-Schreibweisen.

## Verwendung und Freigabegrenze

Der Installer kann als **technische Vorschau** mit einer eigenen Spielkopie ausprobiert werden. Vorher Spiel und alten Assistenten schließen, neue ZIP vollständig separat entpacken und `README.html` lesen. Bei bereits vorbereiteten Daten `UPDATE.cmd` für den bisherigen **Installerordner** verwenden; keine Spielarchive, Backups oder `.local`-Daten manuell löschen.

Ein bestandener Dateitest ist keine Bestätigung, dass alle Mods im Spiel funktionieren. Vor einer öffentlichen Aussage „spielbar“ muss ein Durchlauf der [Playtest-Checkliste](PLAYTEST_CHECKLIST.md) mit eigenen Originaldateien auf Windows erfolgen. Unbekannte Modvarianten, Binärkonflikte und externe Runtime-Anforderungen bleiben bewusst zur Prüfung offen.
