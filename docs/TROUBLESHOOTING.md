# Fehler und sichere nächste Schritte

| Anzeige | Bedeutung | Vorgehen |
| --- | --- | --- |
| Vorbereitung fertig, wartet auf Downloads | Kein Entpackfehler | Gewählten Downloads-Ordner prüfen oder Archiv in `mods` legen; Übernahme aktivieren. |
| Archivliste stimmt nicht / ARCHIVE_MISMATCH | Pfade, Einzelgrößen oder Struktur weichen ab | 0.4.0 installieren; bei Fortbestand Diagnose speichern. Nicht erzwingen oder Prüfsperre abschalten. |
| Optional · nicht aktiv | Datei erkannt, nicht Teil des Standardprofils | Nur bewusst mit ihren Abhängigkeiten aktivieren. |
| Neue/abweichende Version | Lokale Fassung passt nicht zum geprüften Rezept | Richtige Originaldatei über die Karte beziehen oder Version/Unterordner manuell prüfen. |
| Zweite Archivfassung vorhanden | Mehrere unterschiedliche Downloads für ein Modul | Bewusst eine Variante wählen; keine automatische Wahl „neueste Datei gewinnt“. |
| Gesamtmenge noch offen | Tool liefert keinen verlässlichen Gesamtzähler | Protokoll prüfen, warten. Kein Stillstand allein wegen fehlender Prozentzahl. |
| START_NOT_READY | Journal, Dateien, EXE oder Spielstruktur passen nicht | Nicht starten; Abschlussprüfung wiederholen. Änderungen sichern, danach kontrolliert zurücknehmen. |
| Kein eigenes Fenster | Kein unterstütztes lokales Edge/Chrome gefunden oder Start fehlgeschlagen | `IM_BROWSER.cmd` verwenden; kein Browser-Sicherheitsfeature abschalten. |
| Download bleibt unbekannt | Dateiname/Metadaten nicht eindeutig oder noch unvollständig | Vollständig herunterladen; Karte „Archiv hinzufügen“ beziehungsweise Zuordnung nutzen. |
| Werkzeug-Hash falsch | Datei nicht wie erwartet | Offizielle Quelle/Version prüfen; keine fremde DLL/EXE einsetzen. |

## Diagnose weitergeben

Im Statusbereich „Diagnose speichern“. Zuerst selbst kontrollieren, dann als Datei an einen privaten Supportkanal oder späteres Issue hängen. Keine API-Schlüssel, kompletten `.local`-Ordner, Original-Spieldateien oder Modarchive in öffentliche Issues hochladen. Die Diagnose enthält keine Spielinhalte; Bereinigung ersetzt nicht die eigene Sichtprüfung.

## Bekannte Grenzen

Ein Prozessstart bestätigt keine aktive Modfunktion. Steam/Windows-Abhängigkeiten, echte ReShade-Runtime und die tatsächlichen Zusatzlevel müssen im Spiel getestet werden. Die bereitgelegten Fixes behandeln konkret erkannte Fehler, nicht beliebige neue Modformate. Datenzustand nach automatischer Installation bleibt nachvollziehbar und rücknehmbar.
