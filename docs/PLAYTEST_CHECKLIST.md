# Freigabecheck — echte Windows-/Steam-Installation erforderlich

Alle Punkte unten sind **offen**. Die lokalen synthetischen Tests ersetzen diese Prüfung nicht.

## Installation / Originalschutz
- [ ] Frisches Windows 10/11 x64, Standardbenutzer, sauberer Installerordner; STARTEN.cmd inkl. optionaler Python-Einrichtung.
- [ ] Normaler Browserstart, Sitzungstoken, Vivaldi/Chrome/Edge und native Ordnerauswahl.
- [ ] Steam in Program Files und zweite Steam-Bibliothek; Pfade mit Leerzeichen/Umlauten.
- [ ] Saubere originale TCS-Installation identifizieren; EXE-/DAT-Hashes vorab sichern.
- [ ] Freigaben nicht gesetzt: keinerlei Tooldownload oder Spieländerung.
- [ ] QuickBMS-Download und fester Hash tatsächlich erfolgreich; TT-Commit/Skript dokumentiert.
- [ ] Echte Game*.DAT, verschachtelte PAK/FPK und lose Daten: vollständige Extraktion, Duplikate, Sprache, Speicherkalkulation.
- [ ] UAC bestätigen/abbrechen; keine halbe Veröffentlichung der vorbereiteten Daten.
- [ ] EXE und Spielstände unverändert; Original-DAT-Backup vollständig und hashgleich.

## Quellen / Varianten
- [ ] Autorendownloads mit Datum, echten File-IDs und SHA-256 dokumentieren.
- [ ] Modern Overhaul 2.2.2; Additional Levels (Modern Overhaul) 1.4.
- [ ] Refinement Overhaul: tatsächliche gemeinsame Wurzeln und eine Classic-Icon-Variante prüfen.
- [ ] AL-Kompatibilitätspatch: korrekte Wurzeln und Iconvariante prüfen.
- [ ] Optionales Kapitel-6-Addon plus Vader-Patch separat testen.
- [ ] Alle Überschneidungen anhand echter Inhalte prüfen. Keine erfundenen semantischen Merges.
- [ ] Deutsche Spielsprache/ENGLISH.TXT-Abhängigkeiten gezielt testen.

## Nexus / Übergabe
- [ ] Free-Account, manuelle Bestätigung und tatsächlicher Downloadordnername.
- [ ] Download läuft noch/unterbrochen/falsch benannt: keine vorzeitige oder falsche Installation.
- [ ] Eigener API-Key: gültig/ungültig, Rate Limit, Premium/Free.
- [ ] Tatsächliche Dateien abgleichen und gültige CDN-Downloads prüfen.
- [ ] Autorenseite mit/ohne Mod-Manager-Button; NXM gültig/abgelaufen/falscher User/falsches Spiel.
- [ ] Vorhandener Vortex-Handler gesichert, übernommen und vollständig wiederhergestellt.
- [ ] Keine Secrets in Logs, Status, ZIP, Quellenmanifest oder GitHub-Export.

## Spiel
- [ ] Originalspiel startet nach Vorbereitung weiterhin über Steam.
- [ ] Modbuild startet; Cantina, Shop, Charakterkauf und Free Play funktionieren.
- [ ] Boba Fett: Modell, Bewegung, Jetpack, Blaster und Fähigkeiten bleiben passend zum gewünschten TCS-Gefühl.
- [ ] Storylevel, Zusatzlevel, Cutscenes, Controller, Koop, Speichern/Laden testen.
- [ ] Neues Testsave benutzen; bestehende Saves nicht zum ersten Kompatibilitätstest überschreiben.
- [ ] Optionales ReShade-Profil separat im Spiel/GPU testen; kein Effekt als geprüft ausgeben, bevor tatsächlich sichtbar.
- [ ] Spiel- und Verwaltungs-Desktopshortcut nach Programmneustart funktionieren.

## Rücknahme / Release
- [ ] Modrollback vor Vorbereitungsrollback; Originalzustand anhand Hashliste vergleichen.
- [ ] Später manuell geänderte Datei verursacht sicheren Stopp statt Datenverlust.
- [ ] Downloadausfall, voller Datenträger, Prozessabbruch und unterbrochene Transaktion testen.
- [ ] ZIP aus Public Export in sauberer Umgebung startfähig, ohne Arbeitsdaten oder Fremdarchive.
- [ ] Testergebnisse und weiterhin offene Grenzen veröffentlichen. Erst danach „spielgetestet“ kennzeichnen.

## Zusätzliche Freigabeprüfung für 0.3.2

- [ ] Bestehende Spiel-EXE und binkw32.dll vor dem Test lokal hashen.
- [ ] Mit eigenem GAME.DAT starten: BINKW32.DLL wird sichtbar ausgeschlossen; kein Abbruch an diesem Eintrag.
- [ ] QuickBMS-Ausgabe und Auswahl stimmen überein; keine DLL/EXE/Skriptdatei im bereitgestellten Datenbestand.
- [ ] Auflisten/Entpacken anhalten, Assistent beenden, UPDATE.cmd aus separatem Paket ausführen, wieder fortsetzen.
- [ ] Bereits heruntergeladene Mods und lokale Laufzeit bleiben vorhanden.
- [ ] Nach Installation und Rücknahme: EXE-/DLL-Hashes unverändert, Original-DAT-Backup intakt.
- [ ] Spiel/Cutscenes/Charaktere und alle aktivierten Modmodule tatsächlich testen.
