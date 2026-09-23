# Installation und Update

## Neuinstallation

ZIP komplett entpacken. `README.html` ist die Offline-Anleitung, nicht das schreibende Programm. `STARTEN.cmd` startet den lokalen Python-Dienst und die Weboberfläche. Windows-Freigaben nicht ohne Prüfung bestätigen. Beim ersten Start kann der Starter nach Zustimmung eine lokale Python-Runtime unter `.runtime` einrichten.

Die Spielordnerauswahl muss die vorhandene `LEGOStarWarsSaga.exe` enthalten. Der Installer prüft die Struktur und das laufende Spiel. Original-DATs werden isoliert entpackt, kontrolliert und erst dann gesichert. Bereits vorbereitete Kopien werden wiedererkannt. Niemals manuell DLLs oder `.local` löschen, um eine Prüfung zu umgehen.

## Modarchive

Automatikfreigaben setzen, danach „Nächste fehlende Datei öffnen“. Die normale Browser-App wird für Nexus verwendet, damit dein vorhandenes Nexus-Login nutzbar bleibt. Download bestätigen, fertig herunterladen lassen. Nicht den Inhalt in den Spielordner kopieren.

Beobachtet werden nach Freigabe:

```text
<gewählter Downloadordner>\
<Installerordner>\mods\
```

Bei verschobenem Downloads-Ordner im Installer den tatsächlichen Ordner auswählen. Unvollständige Browserdateien und noch wachsende Archive werden zurückgestellt. Ein bekannter Dateiname erlaubt eine vorläufige Zuordnung, nicht das Umgehen von Struktur-, Pfad- oder Größenprüfungen.

Beim Standardprofil bleiben optionale Charakterstile und Vader-Addon aus. Für das Kapitel-6-Addon dessen Abhängigkeiten zusammen aktivieren, nicht nur den Patch. Unbekannte Versionsfassungen oder mehrere mögliche Classic-Ordner einmal prüfen.

## Abschluss

Nach dem Kopieren prüft der Installer jede installierte Moddatei gegen ihr Journal. „Geprüften Spielbuild starten“ beziehungsweise `START_SPIEL.cmd` führt diese Prüfung erneut aus und startet genau die ausgewählte Original-EXE. Steam gegebenenfalls geöffnet lassen. Ein gesendeter Startbefehl ist kein Nachweis, dass das Spiel sichtbar läuft oder die Mods korrekt geladen wurden.

Charaktere, Zusatzlevel und Speicherstand im Spiel prüfen. Erst danach im Installer den selbst durchgeführten Spieltest bestätigen. Neue Spielstände sind nicht automatisch Ersatz für deine eigenen Backups. ReShade und weitere Runtime-Erweiterungen können weiterhin separate Schritte erfordern.

## Update

Alten Assistenten/Spiel schließen. Neue ZIP separat entpacken. Neue `UPDATE.cmd` doppelklicken und den alten **Installer** auswählen. Nicht die Steam-Kopie. Der Updater sichert die alten Programmdateien und bewahrt private Daten. Der Ordnername darf eine ältere Versionsnummer behalten.

## Zurücknehmen

Erst Modinstallation zurücknehmen; anschließend bei Bedarf Spielvorbereitung zurücknehmen. Später von dir veränderte Dateien werden nicht ungefragt ersetzt. Bei Blockade Diagnose und Sicherung prüfen. Die Original-DATs und vorhandenen EXE/DLLs nicht von Hand löschen.
