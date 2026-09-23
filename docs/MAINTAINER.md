# Wartung / Architektur

## Eigene Komponenten

- `app/engine.py`: Quellen, Pläne, Data-Mod-Build, Journale, Installation/Rücknahme und Public Export.
- `app/safety.py`: Archiv-/Pfadprüfung, 7z/RAR-Adapter.
- `app/merge.py`: konservativer Drei-Wege-Textmerge.
- `app/nettools.py`: begrenzte HTTPS-Abfragen, Tooldownload und Prüfsummen.
- `app/preparation.py`: DAT-/Container-Staging und getrennte Originaldaten-Rücknahme.
- `app/nexus.py`: persönliche offizielle API, Fileauflösung, Signed NXM und Downloadordner.
- `app/windows.py`, `elevated_worker.py`, `nxm_handler.py`: feste lokale Windows-Aktionen, ohne generischen Shellzugriff.
- `app/workflow.py`: Freigaben, Automatik, Pause bei unbekannten Eingaben.
- `app/server.py`: tokengebundene lokale HTTP-Oberfläche.
- `web/app.js`, `web/auto.js`: Browserassistent ohne Framework-/CDN-Abhängigkeiten.

## Rezeptpflege

`profile.json` ist schema 3. Module in Installationsreihenfolge, Pflichtabhängigkeiten in `requires`, optionale standardmäßig deaktiviert. Kein neuer beliebiger Fallback auf „latest“. Bei Known File ID Name und Version prüfen. Bei fehlenden IDs nur eindeutige Namens-/Versionsübereinstimmung verwenden. `mod-audit.json` hält Autorenquelle und Grund für Auswahl/Ausschluss fest. Dateiseitenprüfung nicht als Archivtest ausgeben.

Infinities kann mehrere gleichzeitige gemeinsame Ordner haben. Die aktuelle Automapper-Heuristik akzeptiert nur eindeutige Kombinationen; echte Archive können deshalb eine einmalige manuelle Wurzelauswahl verlangen. Dies ist gewollt, bis konkrete Archivstrukturen als getestete Rezeptversion hinterlegt werden. Additional Levels (MO) und eigenständiges Additional Levels dürfen nicht gleichgesetzt werden.

Für ReShade/ASI braucht es einen separaten Runtime-Adapter mit Herkunfts-/Signatur-/Hashprüfung und Prüfung der DLL-Ketten. Nicht die Datenmod-Sperre pauschal lockern. Ein Steam-Shortcut ist nicht mit jeder Steam-unabhängigen Ultrawide-Startanweisung gleichzusetzen.

## Netzwerk-/Downloadgrenzen

Nexus-Key nur RAM. Free-Accounts über offizielle Browserbestätigung oder autorisierten NXM-Link; Premium optional für Sammeldownload. Kein Premium-/Wartezeit-/SSO-Bypass. Keine Downloadlinks mit fremden Zugangsdaten in Releases. Kein Nexus-SSO-Login vortäuschen; dafür wäre eine offiziell genehmigte Appintegration notwendig.

QuickBMS-Pin stammt aus WinGet; der Autorendownload war bei dieser Recherche zeitweise nicht erreichbar. Ein anderer Hash muss zuerst anhand vertrauenswürdiger Primärquellen und echter Bytes geprüft werden. Nie einen Fehler durch Entfernen der Hashprüfung „reparieren“. TT-Skriptcommit wird erst beim Nutzer aufgelöst und protokolliert, kein reproduzierbar vorab gepinnter Quellstand. Ein fest getesteter Commit/Hash ist vor Stable sinnvoll.

## Tests / Release

`python -m unittest discover -s tests -v` benötigt nur stdlib. Browserprüfung benötigt Playwright und Chromium und verwendet im aktuellen Linux-Test einen dokumentierten lokalen Transportadapter. Keine Umgehung von Browserpolicies in Produktivcode. Der Adapter beweist weder normalen Browserbootstrap noch native Windowsdateidialoge.

Vor Stable `PLAYTEST_CHECKLIST.md` vollständig abarbeiten. `TEST_REPORT.json` mit tatsächlichem Ergebnis aktualisieren, nicht bloß Version hochzählen. Änderungen in docs/Abbildungen können den Browser-Testzustand zeigen, müssen als synthetisch markiert sein.

Alle neuen Produktivdateien in `publish-allowlist.json` aufnehmen. Export in einem frischen Ordner entpacken, Python-Imports testen und auf Geheimnisse/fremde Dateien prüfen. `SHA256SUMS.txt` nach finaler Änderung neu erzeugen. GitHub Actions ist vorbereitet, aber ein lokaler Test ist kein bestandenes CI-Ergebnis.


## 0.3.1 release

Publish the full public allowlist, now including processes.py, diagnostics.py,
updater.py, UPDATE.cmd and test_hotfix.py. Regenerate SHA256SUMS.txt for every
allowlisted entry except SHA256SUMS.txt itself. Never export private .local or
.runtime. The updater depends on these checksums; do not alter a published ZIP
without bumping or regenerating its checksums. Test from a fresh export.
Browser checks use synthetic data; docs/TEST_REPORT.json records all untested
Windows/game boundaries. Screenshot badges explicitly identify synthetic fixtures.


## 0.3.2: original-DAT runtime exclusions

Do not remove `.dll` / `.exe` from `safety.BLOCKED`. `parse_listing` defaults to
strict rejection. Only `extract_one` for original archives requests the data-only
policy, validates the FULL listing, then uses a static QuickBMS `-f` exclude list.
The output is checked again against the data-only manifest. Exclusions are
metadata, never permission to copy a program.

`tests/test_original_runtime_filter.py` covers the user traceback, selected
output, malicious paths, cache resume, nested archives, rollback and preserved
DLL hashes. The fake QuickBMS implementation is test-only. A subprocess fixture
checks actual command transport but is Python, not the real tool. Obtain a real
Windows/owned-DAT trace before declaring the extraction path game-tested.

Add `docs/06-original-filter.png` and this new test file to the public allowlist.
Existing screenshots and test logs are regenerated for 0.3.2 using synthetic
fixtures; the screenshot explicitly labels its test status.


## 0.3.3 PAK-Grenzprüfung

Eigener Raw-Leser für TT-PAK-Signatur 0x1234567a; komprimierte Einträge bleiben
beim Codec mit eng begrenztem BMS-Signaturpatch. Kein Fehlercode-3-Bypass.
Details und Grenzen: [PAK_FORMAT_NOTES.md](PAK_FORMAT_NOTES.md).
