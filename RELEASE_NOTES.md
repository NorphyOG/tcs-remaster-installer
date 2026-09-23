# 0.4.0 – Stufenanzeige, Patchimport und geprüfter Start

## Nachbesserung: automatische Dateiauflösung und Navigation

- Bekannte CHARS/STUFF-Modelle und Grafiken folgen der dokumentierten Autoren-Reihenfolge; zehn geprüfte Text-/Skriptdateien sind an vollständige SHA-256-Werte gebunden.
- Nicht überlappende Textänderungen werden mit bestätigter unveränderter Referenz automatisch vereint. Unbekannte Kombinationen stoppen mit Diagnose, ohne Dateiauswahl in der Oberfläche.
- Im schmalen Fenster bleiben alle sechs Schritte oben sichtbar. Der aktuelle Arbeitsschritt steht vor der langen Detailübersicht.
- Synthetischer Browserlauf auf Windows: 46 Prüfungen mit Test-Transportadapter; reale Spielkompatibilität und Browser-Sitzungsübergabe stehen aus.
- Windows-Entpackordner erben nun lesbare Workspace-Rechte für 7-Zip. Nicht mehr lesbare Import-Caches werden aus unveränderten, SHA-256-geprüften Archiven automatisch wiederhergestellt.
- Frischer lokaler Vergleich mit sechs importierten Modarchiven: 2.110 Zieldateien, 220 automatische Überlagerungen, 0 offene Konflikte. Keine Installation und kein Spieltest.

- Windows-Pfadtrenner aus 7-Zip normalisiert; jede Datei mit Einzelgröße geprüft. Keine Sicherheitsprüfung entfernt.
- Sieben persistente Fortschrittsstufen statt scheinbarer Gesamt-100-Prozent-Anzeige.
- Separater lokaler mods-Ordner plus Downloadordner; identifizierbare Varianten automatisch, optionale Module nicht ungefragt aktiviert.
- Eindeutige Patchzuordnung, gemeinsame Archivhüllen und Classic-Icons korrigiert; abweichende Versionen benötigen Prüfung.
- Letzte bekannte Original-Dateiseiten mit konkreter Dateiauswahl; Nexus-API prüft Metadaten. Keine automatisierte kostenlose Download-Bestätigung.
- Eigenes Edge-/Chrome-Web-Appfenster und lokales SVG/PNG/ICO-Symbol, normaler Browser als Fallback.
- Abschlussprüfung jeder installierten Moddatei und bewachter Start der tatsächlich gewählten EXE; Benutzer-Spieltest separat.
- GitHub-README, Anleitungen, Sicherheits-/Beitragsdateien, Issue-Vorlagen und CI vorbereitet. Nichts veröffentlicht.
- Automatik behält sichere Stops, Prüfungen, Wiederherstellung und bereits geprüfte PAK-/DAT-Zwischenstände.

Die sechs lokal importierten Modarchive wurden für den Dateivergleich gelesen. Aktuelle Nexus-API-Downloads, Installation, Windows-Appfenster und Spielstart wurden nicht durchgeführt. Synthetische Prüfungen und UI-Ergebnisse siehe docs/TEST_REPORT.json und docs/VERIFICATION_2026-09-23.md. Kein fertiges Komplett-Remake.

---

# 0.3.3 — AI.PAK: längengeprüfte Einträge und fortsetzbare Vorbereitung

- Der Fehlercode-3-Log passt zu einer unbedingten 32-Byte-Signaturprüfung in
  `DEFLATE_UNPACK`. Der gemeldete Offset/Größenfall wurde mit einem selbst
  erzeugten 10.201-Byte-PAK nachgestellt, nicht mit Originalspieldaten.
- Eigener begrenzter Leser für die bekannte `0x1234567a`-Tabelle. Namen,
  Eintragsanzahl, Offsets, Speicherbedarf und Nutzdatenlängen vorab prüfen.
- Unkomprimierte Einträge ohne QuickBMS lesen; 0–31 Byte kurze Dateien vollständig
  erhalten. Kein Padding, keine Auslassung und keine globale Fehlercodefreigabe.
- Für komprimierte PAKs eine exakt erkannte Signaturfunktion in einer getrennten
  Skriptkopie korrigieren; bestehende Codec-Unterstützung beibehalten. Quelle und
  Ableitung hashen; Dateiliste gegen unabhängige PAK-Tabelle abgleichen.
- Fortschritts-/Diagnosezusammenfassung für PAKs, kurze Einträge und Cache-Nutzung.
- Geprüfte 0.3.2-Zwischenstände weiterverwenden. Werkzeuge nur beim tatsächlichen
  Entpackbedarf einrichten; bei vollständigen Caches kein neuer Werkzeugabruf.
- Bestehender DLL-/EXE-Schutz, Konfliktstopp, Backups und Rücknahme unverändert.
- 37 neue Regressionstests mit selbst erzeugten binären PAKs, zusätzlich
  Browser-Prüfungen für echten lokalen PAK-Parser, Diagnose und Rücknahme.

Kein realer Windows-/Steam-DAT-/QuickBMS-Binary-/Mod-Kompatibilitäts-/Spieltest.
Die komprimierte BMS-Verzweigung ist synthetisch geprüft, nicht im Interpreter
ausgeführt. Die Modauswahl und separaten ReShade-/ASI-Schritte bleiben gleich.

---

# 0.3.2 — Original-DAT-Filter: BINKW32.DLL nicht installieren, Daten weiterverarbeiten

- Den vom Nutzer gelieferten Stacktrace in `preparation.parse_listing` reproduziert.
- Separate, explizite Originaldaten-Policy: ausführbare Dateien als Ausschlüsse erfassen, nicht das gesamte Originalarchiv ablehnen. Mod-Archivregeln unverändert.
- Statischer QuickBMS-Extraktionsfilter; danach vollständiger Abgleich gegen die freigegebene Datenliste. Keine DLL-/EXE-Übernahme und keine EXE-Patches.
- Schutz gegen Traversal, administrative Pfade, Datei-/Verzeichnis-Kollisionen und Dubletten gilt auch für ausgelassene Einträge. Ausschlüsse zählen gegen Dateilimits.
- Ausschlussbericht im Job-/Diagnosebereich, in Extraktionsbelegen und Vorbereitungsmanifest. Private Arbeitsberichte bleiben aus öffentlichen ZIPs ausgeschlossen.
- Fehlgeschlagene 0.3.1-Stagingordner kontrolliert neu aufbauen; kompatible geprüfte Datenbelege weiterverwenden. Unveränderte Downloads, .runtime und Backups bleiben erhalten.
- Regressionen für BINKW32.DLL, weitere ausführbare Dateitypen, Unterarchive, Filterfehler, manipulierte Caches, Installation und Rücknahme.

Modauswahl unverändert. Kein Windows-/Original-DAT-/echter QuickBMS-/Spieltest.
Die Autorendokumentation und der veröffentlichte Filtercode wurden geprüft; ein
Werkzeugdownload für reale Extraktionstests war in dieser Umgebung nicht möglich.

---

# 0.3.1 — Windows-Prozessprüfung, Wiederanlauf und Diagnose

- Reproduzierter `NoneType.lower`-Fehlerpfad der alten tasklist-Abfrage abgesichert: Byteausgabe statt Windows-Codepage-Decodierung; fehlgeschlagene Prüfungen stoppen kontrolliert.
- Dauerhafte Fortschritts-/Fehleransicht, Diagnose-JSON, echte Byte-/Dateizähler und Werkzeug-Aktivitätshinweise.
- Begrenzte Wiederholungen nur bei vorübergehenden Netzwerkfehlern. Hashfehler bleiben blockierend.
- Hashgeprüfte Vorbereitungs-Checkpoints, sicherer Wiederanlauf und pausierter Download-Watcher nach Fehlern.
- Keine durch Hintergrund-Polling verlorenen Modulbestätigungen; identische bestätigte Archivimporte werden nicht zurückgesetzt.
- Nullwertprüfungen für API-/Werkzeugantworten; Vorbereitet-Häkchen folgt der tatsächlichen Struktur statt manueller Behauptung.
- `UPDATE.cmd`: gesichertes Programmdatei-Update im bestehenden Installerpfad; Downloads, Einstellungen und lokale Laufzeit bleiben erhalten.
- Neue Regressionstests einschließlich vollständiger synthetischer Vorbereitung, Modinstallation und Rücknahme.

Die Modauswahl bleibt die von 0.3. Keine echten Windows-/Nexus-/Spieltests; keine Spielbarkeitsfreigabe. Der gemeldete Fehlerpfad ist reproduziert, die konkrete Windows-Traceback-Datei des Nutzers lag nicht vor.

---

# 0.3.0 — Vorbereitung, Nexus und Desktop-Integration

## Neu
- Separate, kontrollierte Originaldaten-Vorbereitung über QuickBMS + TT-Parser, mit Dateilisting vor Extraktion, Staging, Journal, DAT-Backup und Rücknahme.
- Optionaler Download offizieller Hilfsprogramme nach Freigabe; Hashprüfung und Stopp bei nicht verifizierbaren Werkzeugdateien.
- Beobachteter Downloadordner; keine Beobachtung anderer Ordner, keine Übernahme beliebiger Dateien.
- Persönliche Nexus-API-Verbindung, versiongebundener Datei-Abgleich, Premium-Abruf und optionale NXM-Linkübergabe.
- NXM nur nach ausdrücklicher Benutzerfreigabe, bisherige Zuordnung gesichert; kein stiller Vortex-Ersatz.
- Kontrollierter Automatikmodus: vorbereitetes Spiel + gewählte, bestätigte Dateien + konfliktfreier Plan → Installation. Fehler und unbekannte Konflikte pausieren. Nach Neustart nicht automatisch erneut freigegeben.
- Eingeschränkter UAC-Schreibhelfer für geschützte Spielordner; Download-/Webprozess bleibt ohne Administratorrechte.
- Steam-Spielshortcut und separate Verwaltungsverknüpfung.
- Autoren-/Optionaldatei-Audit; Kapitel-6-Addon plus Infinities-Patch optional, übrige Alternativen nicht blind kombiniert.

## Korrigiert
- Alter „EXE nicht gefunden“-Toast wird nach erfolgreicher neuer Prüfung entfernt.
- Strukturprüfung unterscheidet lose Daten von noch aktiven Game-DATs.
- Neue Module und Dokumente im öffentlichen Export; keine versehentliche 0.2-Benennung.
- Nach fehlgeschlagener Vorbereitung keine weiterhin schreibbereite Automatik.
- Schnelle Hintergrundimporte werden in der Oberfläche nachgeladen.

## Bekannte Grenzen
- Keine Original-/Modarchive vorhanden; keine Windows-/Nexus-/Spieltests. Automatik ist implementiert, aber nicht auf einem echten Rechner freigegeben.
- QuickBMS-Upstreamdownload war bei der Recherche nicht durchgehend erreichbar. Hashgesicherte Fallbacks und manueller Import; keine unsichere Hash-Umgehung.
- ReShade-/ASI-Runtimes weiterhin separat. Keine allgemeine Migration fremder Alt-Mods und kein semantischer Binärmerge.
- Vier Standarddateien + zwei optionale Module; kein Paket sämtlicher erwähnter Communitymods.
- 167 lokale automatisierte Tests und 18 Browserchecks mit künstlichen Daten bestanden. Details in docs/TEST_REPORT.json.
