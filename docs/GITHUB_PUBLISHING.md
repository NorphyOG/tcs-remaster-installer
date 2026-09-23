# GitHub-Repository – privater Entwurf

**Ein öffentlicher Release ist nicht freigegeben.** Das verifizierte GitHub-Profil ist [NorphyOG](https://github.com/NorphyOG). Der Quellstand soll zunächst ausschließlich in einem **privaten** Repository liegen. Rechte an Original-Spielinhalten oder fremden Mods werden dadurch nicht übertragen.

## Repository auffindbar beschreiben

Vorschlag Repository-Name: `tcs-remaster-installer`

Beschreibung zum Kopieren:

```text
Local Windows modpack installer for LEGO Star Wars: The Complete Saga. Safe extraction, conflict review, backups, Nexus download handoff and verified game launch. No game assets included.
```

Vorschlag Topics:

```text
lego-star-wars the-complete-saga tcs modding modpack mod-manager windows python nexusmods local-first
```

Die Begriffe beschreiben die tatsächliche Funktion. Keine „official“, „complete remake“, „fully tested“ oder garantierte Ein-Klick-Kompatibilität behaupten. README mit erster Anleitung und gekennzeichnetem Screenshot beibehalten; deutsche und englische Suchbegriffe sinnvoll, keine Keyword-Wiederholungen.

## Vor dem Upload

1. Im Installer „Weitergeben → GitHub-/Upload-ZIP erstellen“ wählen. **Nicht** deinen Arbeitsordner einschließlich `.local` hochladen.
2. Export separat entpacken und `SHA256SUMS.txt` sowie Dateiliste prüfen. Keine Modarchive, Diagnose-Personendaten oder Spielpfade hinzufügen.
3. Tests lokal ausführen; tatsächliche Grenzen in Release-Text und README behalten.
4. Repository `tcs-remaster-installer` unter `NorphyOG` mit Sichtbarkeit **Private** anlegen. Quellstand und die tatsächlich geprüften Testergebnisse hochladen. `git remote -v` und die GitHub-Einstellung **Private** danach kontrollieren.
5. Vor einem späteren Wechsel auf **Public** Quellstand, Commit-Historie, Lizenz-/Markenhinweise, Release-Archiv und echte Windows-/Spieltests erneut prüfen. Dieser Wechsel braucht eine eigene Entscheidung.
6. Für einen Release Versionsnummer, ZIP, SHA-256, Änderungsübersicht und Testbericht zusammen bereitstellen. Kein Auto-Publishing-Workflow enthalten.

## Profil optional

Ein GitHub-Profil-README ist ein separates Projekt. `PROFILE_TEMPLATE.md` enthält eine neutrale Vorlage ohne erfundene Benutzerkennung oder öffentliche Kontaktinformationen. Erst selbst ergänzen. Keinerlei Kontoerstellung oder Veröffentlichung wird vom Installer übernommen.

## Sicherheits-/Rechtecheck

Nexus-Downloadbedingungen respektieren; fremde Modarchive nicht rehosten. Eigenes Code-Repository hat MIT-Lizenz, Drittanbieterbedingungen bleiben separat. Spiel-/Markeninhaber nicht als Sponsor darstellen. Keine API-Schlüssel in Issues, Screenshots, Git-Historie oder Releases.
