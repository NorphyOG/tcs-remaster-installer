# Modrezept und Dateiauswahl

Quellenstand: **23.09.2026**, öffentliche Autoren-Dateilisten. Es wurden nicht die tatsächlichen Modarchive im Spiel geprüft. Versionsnummern beziehen sich auf die konkrete Datei, nicht zwangsläufig die Gesamt-Modseite. Ein neuer Upload wird nicht automatisch als kompatibel angenommen.

| Modul | Datei / Version | Auswahl | Quelle |
| --- | --- | --- | --- |
| Modern Overhaul | Hauptdatei 2.2.2, Rezept-ID 583 | Standard | [Autoren-Dateiliste](https://www.nexusmods.com/legostarwarsthecompletesaga/mods/54?tab=files) |
| Additional Levels | **Modern Overhaul** 1.4, Optional File, Rezept-ID 578 | Standard, nicht Standalone 2.3.1 | [Autoren-Dateiliste](https://www.nexusmods.com/legostarwarsthecompletesaga/mods/32?tab=files) |
| Infinities | Refinement Overhaul, History-ID 634, Upload 02.03.2026 | Gemeinsame Dateien + genau Classic Icons | [Autoren-Dateiliste](https://www.nexusmods.com/legostarwarsthecompletesaga/mods/133?tab=files) |
| Infinities AL-Patch | Compatibility Patches – Additional Levels 1.1, History-ID 615 | Standard, abhängig von Infinities und Additional Levels | [Autoren-Dateiliste](https://www.nexusmods.com/legostarwarsthecompletesaga/mods/133?tab=files) |
| Ep3 Ch6 Addon | 1.8, Rezept-ID 579 | Optional | [Modern Overhaul Dateien](https://www.nexusmods.com/legostarwarsthecompletesaga/mods/54?tab=files) |
| Vader-Patch | Compatibility Patches – Vader Enhancer Addon 1.0, History-ID 620 | Optional, abhängig von Infinities und Ep3 Ch6 Addon | [Infinities Dateien](https://www.nexusmods.com/legostarwarsthecompletesaga/mods/133?tab=files) |

Die öffentlichen History-IDs werden als letzte bekannte Datei-Auswahl verwendet; ein echter autorisierter Nexus-API-Abgleich/Download dieser IDs wurde hier nicht durchgeführt. Bei API-Nutzung werden die zurückgegebenen Metadaten gegen das Rezept geprüft. Ohne API sind Dateiname/Struktur nur lokale Erkennung, keine Signatur des Autors.

## Importfehler aus 0.3.3

Die Diagnose für `Compatibility Patches - Vader Enhancer Addon-133-1-0-1770092331.7z` zeigte einen Listen-/Entpackvergleichsfehler. Im alten Code waren Backslashes aus 7-Zip nicht mit den normalisierten `/`-Pfaden der entpackten Dateien vereinheitlicht. 0.4.0 normalisiert beide Seiten und prüft **jeden** Dateipfad und seine Größe. Das ist ein nachvollziehbarer Fehlerfall, kein Beweis über die Inhalte des nicht mitgelieferten Originalarchivs.

## Zusammenführen

Unterschiedliche Pfade werden übernommen, identische Dateien dedupliziert. Die im Profil festgelegte Reihenfolge überlagert bekannte CHARS/STUFF-Modell- und Grafikdateien automatisch: Modern Overhaul → Infinities → passender Additional-Levels- oder Vader-Patch. Das folgt der [Installationsanleitung des Infinities-Autors](https://www.nexusmods.com/legostarwarsthecompletesaga/mods/133). Dabei wird **eine vollständige Autorendatei gewählt**, nicht der Inhalt zweier Binärdateien verschmolzen.

Zehn zusätzlich geprüfte Text-/Skriptkollisionen des aktuellen Rezepts sind an die SHA-256-Werte **aller** beteiligten Dateien gebunden. Dazu gehören die Kombination aus Episode-III-Addon und Additional Levels: Die gewählte Episode-III-Datei enthält die geprüften Additional-Levels-Ergänzungen. Ändert sich ein Hash, ein Modul oder dessen Reihenfolge, greift die Regel nicht mehr. Sonstige Textänderungen werden nur mit bestätigter unveränderter Referenz und ohne überlappende Änderungen automatisch per Drei-Wege-Merge vereint. Unbekannte Konflikte blockieren die Installation; eine bestandene Datei-Auflösung beweist keine Spielkompatibilität oder Herkunft der Modarchive.

Die übrigen optionalen Infinities-Stile, alternative Icons, separate Character-Packs, ReShade-/ASI-Runtimes sind nicht automatisch Teil des Standardprofils. Sie können überschneidende Dateien oder zusätzliche Voraussetzungen mitbringen. Die volle bisherige Entscheidungsübersicht steht in `mod-audit.json`.
