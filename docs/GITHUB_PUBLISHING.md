# GitHub-Veröffentlichung

Das [öffentliche Repository](https://github.com/NorphyOG/tcs-remaster-installer) enthält nur den Installer-Quellcode und eigene Dokumentation. Spiel, Mods, Backups und lokale Arbeitsdaten werden nicht verteilt. Die MIT-Lizenz betrifft nur unseren Code; die Rechte an Spiel und fremden Mods bleiben bei ihren Inhabern.

## Repository auffindbar beschreiben

Vorschlag Repository-Name: `tcs-remaster-installer`

Beschreibung zum Kopieren:

```text
Local Windows modpack installer for LEGO Star Wars: The Complete Saga. Automatic checked mod overlays, backups, Nexus download handoff and verified game launch. No game assets included.
```

Vorschlag Topics:

```text
lego-star-wars the-complete-saga tcs modding modpack mod-manager windows python nexusmods local-first
```

Die Begriffe beschreiben die tatsächliche Funktion. Keine „official“, „complete remake“, „fully tested“ oder garantierte Ein-Klick-Kompatibilität behaupten. README mit erster Anleitung und gekennzeichnetem Screenshot beibehalten; deutsche und englische Suchbegriffe sinnvoll, keine Keyword-Wiederholungen.

## Nutzung und Release

1. Unter [Releases](https://github.com/NorphyOG/tcs-remaster-installer/releases) die vorbereitete Installer-ZIP laden. Die GitHub-„Source code“-ZIP ist keine vollständige Installer-Verteilung.
2. ZIP außerhalb des Spielordners entpacken, `README.html` lesen und `STARTEN.cmd` ausführen. Mods selbst bei den Autoren herunterladen.
3. Für eine neue Version die Python- und Browserprüfungen ausführen, den öffentlichen Export prüfen und `SHA256SUMS.txt` neu erzeugen.
4. `publish-allowlist.json`, Git-Historie und Release-ZIP auf `.local`, Modarchive, Diagnosen, private Pfade und Schlüssel prüfen. Nie den gesamten Arbeitsordner hochladen.
5. Release mit ZIP, SHA-256, Änderungen und Testgrenzen versehen. Kein Auto-Publishing-Workflow ist eingerichtet.

Das neue [abstrakte Banner](media/installer-hero.jpg) enthält keine Spielfiguren oder Modinhalte und dient als GitHub Social Preview. Screenshots sind als Installer-Oberfläche mit künstlichen Testdaten gekennzeichnet.

## Profil optional

Ein GitHub-Profil-README ist ein separates Projekt. `PROFILE_TEMPLATE.md` enthält eine neutrale Vorlage ohne erfundene Benutzerkennung oder öffentliche Kontaktinformationen. Erst selbst ergänzen. Keinerlei Kontoerstellung oder Veröffentlichung wird vom Installer übernommen.

## Sicherheits-/Rechtecheck

Nexus-Downloadbedingungen respektieren; fremde Modarchive nicht rehosten. Eigenes Code-Repository hat MIT-Lizenz, Drittanbieterbedingungen bleiben separat. Spiel-/Markeninhaber nicht als Sponsor darstellen. Keine API-Schlüssel in Issues, Screenshots, Git-Historie oder Releases.
