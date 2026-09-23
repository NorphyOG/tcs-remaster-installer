# Sicherheitsmodell — 0.3

## Lokale API

Nur Loopback `127.0.0.1`, zufälliger Sitzungstoken, Host-/Origin-Prüfung, kein CORS für fremde Seiten. Zugriff nur auf feste Endpunkte und gewählte Dateien. Keine beliebigen Shellbefehle oder allgemeinen Dateidownloads. Der Browser-Transportadapter existiert ausschließlich in Tests. Der Starter verwendet einen freien Loopback-Port; bei belegtem Port keinen fremden Prozess beenden, sondern alten Assistenten schließen.

## Internet und Anmeldedaten

Tooldownload und Nexus-Zugriff sind neu in 0.3 und erfolgen erst nach den jeweiligen Freigaben. Nur HTTPS und geprüfte Hostlisten; Redirects werden erneut geprüft. Nexus-API-Header gehen ausschließlich an api.nexusmods.com. Signed Download URLs enthalten sensitive Parameter und werden nicht in den Export/Status übernommen. Persönlicher API-Schlüssel nur im Sitzungsspeicher, nicht auf Festplatte. Keine Telemetrie und kein Server-Upload der Mods.

NXM hat eine ausdrückliche Bestätigung und sichert die HKCU-Zuordnung. Es ist kein pro-Spiel-Browserhandler: Ein Umstellen betrifft die gesamte nxm-Zuordnung des Benutzers. Andere Spiele werden abgewiesen. Der Rückbau darf keine erkennbare Änderung eines anderen Managers überschreiben. Der beobachtete Ordner ist die Alternative ohne Registry-Änderung.

## Externe Werkzeuge

QuickBMS ZIP benötigt SHA-256 `b9d4f9efb55692994cd42a491cfea11f86e3375a618b9bd771583ce40ddb3828`, Quelle des Pins: Microsoft WinGet-Manifest. Quellen können ausfallen oder andere Bytes liefern; dann wird nichts ausgeführt. Eine lokal importierte QuickBMS-ZIP muss denselben Hash besitzen.

Das TT-Skript wird von einem konkret aufgelösten Repository-Commit geladen. Lokaler SHA-256 und Commit werden dokumentiert; es ist kein unabhängig vorab gepinnter Skripthash. Bekannte gefährliche Kommandos (CallDLL/Execute/Include und Execute-Comtype/Encryption) werden abgewiesen. Interaktive Ausführungsfreigaben sowie QuickBMS-Schreib-/Netzwerkschalter werden nicht aktiviert. Das ist **keine vollständige Skript-Sandbox**. Downloader/Parser bleiben uneleviert und müssen als zusätzliche Vertrauensgrenze behandelt werden.

7-Zip 26.03: vorhandene Systeminstallation oder offizielles GitHub-MSI mit Asset-SHA-256, lokal administrativ entpackt. Fehlt ein Herausgeber-Digest, kein automatischer Fallback auf ungeprüfte Binärdateien. Python-Bootstrap lädt offiziell von python.org und prüft die Python-EXE per Authenticode; der ZIP-Hash wird aufgezeichnet, ist aber nicht vorab unabhängig gepinnt. Globale PATH-/Execution-Policy-Einstellungen werden nicht verändert.

Native Extraktoren, Python-DLLs und Betriebssystem haben eigene Angriffsflächen. Diese Schutzmaßnahmen beweisen keine Virenfreiheit und wurden nicht unter Windows ausgeführt.

## Archive / Dateisystem

Modcode wird nicht ausgeführt. Programmdateien in Datenordnern werden blockiert. Keine Path-Traversal-, UNC-, ADS-, reservierten Windowsnamen-, Case-Kollision-, Symlink-/Junction- oder Spezialdateipfade. Bei 7z/RAR Listing vor Extraktion, Ergebnis danach erneut geprüft. Maximal 8 GiB Eingabearchiv, 24 GiB ausgepackte Daten und 160.000 Dateien. Staging liegt getrennt vom Originalspiel. QuickBMS listet auch vor dem Auspacken; Größen/Dateiliste/Links/Containerduplikate werden danach abgeglichen.

Ein lokaler Dateiname beweist nicht Herkunft oder Version eines Mods. Nexus-Metadaten ordnen den API-Abruf zu, ersetzen aber keine unabhängigen, vorab bekannten Autorenhashes. Diese liegen für die Modarchive noch nicht vor.

## Installation, UAC und Rücknahme

Nur feste Offline-Aktionen laufen bei erforderlichen Schreibrechten über den UAC-Helfer: geprüften Vorbereitungsplan übernehmen, Modplan übernehmen, jeweilige Rücknahme. JSON-Aufträge sind lokal, pfad-/hashgeprüft; kein allgemeiner Admin-Befehl, kein Netzwerk im erhöhten Helfer. Downloader/HTTP-Oberfläche laufen weiter uneleviert.

Original-DATs werden erst nach erfolgreichem Staging in `.tcs-preparation` verschoben. Lose Moddateien erhalten Backups in `.tcs-remaster`. Vorher-/Nachher-Hashes und Journal ermöglichen Rücknahme. Pro Datei atomarer Replace; die Gesamtinstallation ist **kein einzelner atomarer Betriebssystemvorgang**. Bei abgefangenem Fehler wird zurückgerollt. Prozessabbruch/Stromausfall und komplexe NTFS-ACLs sind nicht vollständig getestet; nach einem Abbruch vorhandene Journale nicht löschen. Extern veränderte Dateien führen zum Stopp.

Spielstände werden nicht gelesen/gesichert/migriert. Keine automatische Alt-Mod-Migration. Neuinstallation verlangt vorherige Rücknahme. Die EXE bleibt unverändert. Eigene Spielkopie/Steam-Lizenz erforderlich.

## Merge und Veröffentlichung

Textmerge nur mit passender unveränderter Referenz und Freigabe. Kein semantischer TCS-Parser. Ganze Autoren-Ersetzungen werden gesondert ausgewiesen; Modelle/GSC/DDs nicht generisch verschmolzen. Unbekannte Konflikte blockieren.

Export nur über feste Positivliste: keine `.local`, `.runtime`, Downloads, Accounts, Backups oder fremden Mod-/Spielarchive. Der Installer selbst und seine lokalen Profile sind nicht gegen einen Angreifer abgesichert, der bereits Schreibrechte auf den Benutzeraccount hat. Es wird keine Prüfung durch einen unabhängigen Sicherheitsdienst behauptet.


## Ergänzungen 0.3.1

Windows-Prozessprüfung liest Bytes statt lokalisierte tasklist-Ausgabe mit einer geratenen Codepage zu decodieren. Fehlende Ausgabe/Exitfehler werden nicht als geschlossenes Spiel interpretiert. Fortschrittslogs sind lokal und bereinigt; Diagnoseexport entfernt bekannte Schlüssel, URLs und private Pfadpräfixe. Keine Telemetrie.

Der Update-Helfer ersetzt nur mitgelieferte Dateien aus der expliziten Positivliste nach Integritätsprüfung. Vorherige Programmdateien werden im alten Installer gesichert. `.local`/`.runtime`, Spielordner und fremde Dateien sind keine Update-Nutzlast. Mitgelieferte Checksummen sind eine Integritätskontrolle, keine unabhängige digitale Signatur. Nach einem Prozess-/Stromabbruch vorhandene Sicherungen nicht löschen.

Vorbereitungs-Checkpoints werden anhand unveränderter Originalarchive und tatsächlicher Dateihashes revalidiert. Staging ist keine Quelle für ungeprüftes Weiterkopieren. Pause/Retry erteilt keine dauerhafte Installationsberechtigung nach Neustart. Native Windows-Ausführung und echte Spielarchive weiterhin nicht getestet.

## Ergänzungen 0.3.2: Originaldaten sind nicht Modarchive

`parse_listing` bleibt standardmäßig strikt. Nur die Vorbereitung eigener
Originalarchive setzt `original_data=True`: `.dll`, `.exe` und weitere bereits
blockierte ausführbare Formate werden vollständig gelistet/geprüft und danach
vom Extraktionsumfang ausgeschlossen. Kein generelles DLL-Allowlisting.

Ein statischer, nicht aus Dateinamen zusammengesetzter QuickBMS-Filter verhindert
die Extraktion. Die nachträgliche Dateiliste, Cachevalidierung, Manifestvalidierung
und der vorgezogene Schreibplan sperren Programmdateien zusätzlich. Ein ignorierter
Filter führt zum Stopp, nicht zur Freigabe. Caches enthalten nur Datenbelege und
separate Ausschlussmetadaten. Auch ausgelassene Pfade dürfen weder Traversal,
Windows-Sonderpfade noch Verzeichnis-/Datei-Kollisionen enthalten.

Der originale BINKW32.DLL-Eintrag ist **kein** Malware-Nachweis und **keine**
fehlende-DLL-Diagnose. Vorhandene Laufzeitdateien werden weder gelöscht noch
ersetzt. Die Archivkopie wird nicht zur Reparatur verwendet.

Neue Tests sind synthetisch. Weder QuickBMS selbst noch die kommerziellen
Originalarchive wurden in dieser Umgebung ausgeführt.


## 0.3.3 PAK-Grenzprüfung

Eigener Raw-Leser für TT-PAK-Signatur 0x1234567a; komprimierte Einträge bleiben
beim Codec mit eng begrenztem BMS-Signaturpatch. Kein Fehlercode-3-Bypass.
Details und Grenzen: [PAK_FORMAT_NOTES.md](PAK_FORMAT_NOTES.md).
