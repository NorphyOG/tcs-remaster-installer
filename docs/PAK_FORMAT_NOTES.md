# PAK-Prüfung in 0.3.3

## Befund aus dem Nutzerprotokoll

Das äußere GAME.DAT wurde erfolgreich aufgelistet und extrahiert. Der Abbruch
trat danach beim Unterarchiv
`LEVELS/NEWBONUS/NB_KASHYYYK/NB_KASHYYYK_A/AI/AI.PAK` auf.
Gemeldet: 10.201 Bytes Gesamtgröße, Dateiposition `0x27d9`, 19 fehlende Bytes
beim Befehl `getdstring SIGN 0x20`. Vorher sichtbar waren:

| Eintrag | Offset | Größe |
|---|---:|---:|
| ATTACK.SCP | 0xba | 1120 |
| LEVEL.SCP | 0x51a | 1625 |
| NB_KASHYYYK_A.AI2 | 0xb73 | 7257 |

Die dritte Datei endet bei 10.188. Bis zum gemeldeten Archivende bleiben
13 Bytes. Ein unbedingtes Lesen von 32 Bytes aus diesem Bereich würde genau
19 fehlende Bytes melden. Das ist eine durch Quellprüfung gestützte Erklärung,
kein Beweis über den Inhalt des nicht hochgeladenen Original-PAKs.

## Quellenprüfung (23.09.2026)

- [TT-QuickBMS-Skript](https://raw.githubusercontent.com/linterniGamer/Tt-Games-quickbms-scripts/main/files/ttgames.bms):
  `EXTRACT_1234567a` definiert 24-Byte-Header und 28-Byte-Einträge.
  `DEFLATE_UNPACK` liest ohne Längenprüfung 32 Bytes zur Signaturerkennung.
- [Unabhängige PAK-Implementierung](https://github.com/AcK77/TTGames-Explorer-Rebirth/blob/6e6b4e2917b261fe82605a4d962516b154c72b9a/src/TTGamesExplorerRebirthLib/Formats/PAK.cs):
  bestätigt dieselbe Tabelle. Einige reservierte Felder und Dateiflags sind
  nicht vollständig dokumentiert und werden deshalb nicht geraten.
- [QuickBMS Codec-Auswahl](https://raw.githubusercontent.com/LittleBigBug/QuickBMS/master/src/perform.c):
  DFLT verwendet `undflt`; kein ungeprüfter Austausch gegen einen beliebigen
  Zlib-Decoder. Kompression bleibt beim vorhandenen Werkzeug.

Es wird kein Quellcode aus diesen Projekten im Installer mitverteilt. Der
Tabellenleser ist eine eigene Implementierung der beschriebenen Datenstruktur.
Das lokale TT-Skript wird nur bei bekannter komprimierter PAK-Struktur und exakt
passender Signaturfunktion in einer separaten, gehashten Ableitung angepasst.
Die unveränderte Downloadfassung und ihr Prüfbeleg bleiben erhalten.

## Prüfgrenzen

Dateitabelle, nullterminierte ASCII-Pfade, Groß-/Kleinschreibungskollisionen,
Windows-Sonderpfade, Eintragsgrenzen und Ausgabegrößen werden unabhängig geprüft.
Laufzeit-/Skriptdateien bleiben vom Installationspayload ausgeschlossen.
Unkomprimierte Nutzdaten werden exakt nach Tabellenlänge gelesen, danach wird
die Ausgabe nochmals gegen Pfade und Größen geprüft. Originaldateien werden
vor und nach dem Kopieren gehasht. Keine Daten werden aufgefüllt oder erraten.

Das interne PAK-Checksum-Feld ist **nicht verifiziert**; SHA-256 sichert hier die
lokale Unverändertheit, nicht die offizielle Authentizität des Spiels.
`header_size_field` wird erfasst; entscheidend für Grenzprüfungen ist die echte
Dateigröße. Unbekannte Signaturen gehen an den bisherigen Parser und dürfen bei
Fehlern nicht als erfolgreich gelten. Bei bekannter Signatur und ungültiger
Tabelle wird nicht mit einem toleranteren Parser weiterprobiert.

## Tatsächliche Tests

Ein künstliches 10.201-Byte-PAK bildet die drei sichtbaren Offset-/Größenpaare
und einen vierten 13-Byte-Eintrag nach. **Dessen Name und alle Nutzdaten sind
synthetisch.** Der ursprüngliche 32-Byte-Leseversuch wird in Python emuliert;
es wird kein echter QuickBMS-Lauf behauptet.

Der neue rohe PAK-Leser verarbeitet diese Binärdatei tatsächlich und erhält
alle vier Einträge bytegenau. Varianten prüfen 0–32 Byte, abgeschnittene Daten,
manipulierte Tabellen/Pfade, komprimierte Header, Output-Limits, Runtimefilter,
Pause, Cache-Wiederanlauf, Installation und Rücknahme. Die komprimierte
Verzweigung verwendet in Tests einen ausdrücklich simulierten Codecprozess.

Windows, Original-GAME.DAT, der originale AI.PAK-Inhalt, echte Nexus-Modarchive
und das Spiel selbst wurden nicht ausgeführt. Es gibt keine Spielbarkeitsfreigabe.
