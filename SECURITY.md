# Sicherheit

Der Installer akzeptiert nur lokale Loopback-Verbindungen mit Sitzungstoken und passenden Host-/Origin-Headern. Keine Telemetrie. Nexus-Schlüssel bleiben im RAM. Downloads werden nur nach Freigabe ausgeführt. Modarchive dürfen weder Pfadtraversal, Links, gefährliche Windows-Pfade noch ausführbare/administrative Dateien einschleusen.

Originalarchive dürfen Laufzeitdateien enthalten: diese werden vor der Extraktion gefiltert, nicht installiert. Bereits vorhandene Spiel-EXE/DLLs bleiben unverändert. Die Vorbereitung kopiert nur geprüfte Daten. Fremde Spiele/Mods oder Werkzeuge werden nicht im öffentlichen Paket mitgeliefert.

Sicherheitslücken nach Einrichtung eines Repositories über dessen private Sicherheitsmeldung melden, sofern der Betreiber diese aktiviert hat. Bis dahin keine vertraulichen Daten öffentlich posten. Diese Datei behauptet keinen schon vorhandenen Meldekanal oder Dienst.

Detaillierte bestehende Sicherheitsgrenzen: [docs/SECURITY.md](docs/SECURITY.md). Neue Prüfsummen stärken die Integrität eines bestimmten Datenplans, beweisen jedoch nicht automatisch, dass eine unbekannte Originalquelle vertrauenswürdig oder ein Mod kompatibel ist.
