# Architektur

```text
STARTEN.cmd
  -> Python (lokal installierte oder freigegebene portable Runtime)
  -> app/server.py (127.0.0.1, zufälliger Port und Sitzungstoken)
  -> app/desktop.py (Edge/Chrome --app oder Browser-Fallback)
  -> web/ (HTML, CSS, JavaScript, lokales App-Symbol)

Workflow
  -> Tools / Nexus / DownloadWatch
  -> sichere Extraktion + normalisierte Inventare
  -> versionierte Rezeptzuordnung / Varianten
  -> Datei-/Konfliktplan
  -> transaktionale Installation + Backupjournal
  -> readiness.py: jede installierte Datei hashen
  -> Original-EXE im ausgewählten Spielordner
```

`steps.py` trennt fachliche Stufen von kurzlebigen Job-/Werkzeugphasen. `matching.py` enthält eng begrenzte Erkennungsregeln. `safety.py` bleibt gemeinsame Grenze für Pfade, Größen, Symlinks, ausführbaren Inhalt und Extraktionsprüfung. `diagnostics.py` bereinigt Logs und liefert feste Wiederherstellungshinweise. Die Original-DAT/PAK-Logik und der begrenzte native PAK-Parser aus 0.3.3 bleiben bestehen.

Der Browser hat keinen generischen Dateisystemzugriff. Mutationen gehen über freigegebene lokale Endpunkte, Token und Host-/Origin-Prüfung. Kein Remote-API-Listener, keine beliebige Shell-Schnittstelle. Administratorrechte werden nur bei Bedarf an einen begrenzten Schreibhelfer gegeben; Downloader läuft weiter ohne erhöhte Rechte.

`publish-allowlist.json` ist die öffentliche Dateigrenze. `app/updater.py` ersetzt nur freigegebene Programmdateien und bewahrt private Daten. `.gitignore` ist zusätzliche Hygiene, nicht die Sicherheitsgrenze des Exports.
