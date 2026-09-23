# Automatik, Versionen und Fortschritt

## Sieben unabhängige Stufen

1. Spiel vorbereiten.
2. Modarchive übernehmen.
3. Varianten und Abhängigkeiten zuordnen.
4. Dateikonflikte prüfen und auflösen.
5. Dateien installieren und sichern.
6. Installierte Moddateien prüfen.
7. Spielstart anfordern, Spieltest selbst bestätigen.

Ein fertiger Unterprozess setzt nicht die gesamte Installation auf 100 %. Prozentwerte einer laufenden Stufe beziehen sich auf die jeweils benannte **Teilaufgabe** mit echter bekannter Gesamtmenge. Eine neue Unteraufgabe kann neu zählen. Ohne bekannte Gesamtmenge erscheint eine ruhige Kennzeichnung „Gesamtmenge noch offen“, keine Endlosanimation und keine Schätzung. Der Kopf zeigt „x / 7 Schritte fertig“, keine erfundene zeitliche Gesamtprozentzahl.

Stufen werden unter `.local/steps.json` gespeichert. Laufende Stufen werden nach Neustart pausiert; Schreibfreigabe wird nie automatisch über einen Neustart hinweg erneut erteilt. Bereits vorbereitete Struktur wird geprüft und wiedererkannt.

## Was selbstständig weiterläuft

Nach ausdrücklicher Aktivierung: passende fertige Downloads erkennen, sicher entpacken, eindeutige Rezeptzuordnung, bekannte Autoren-Überlagerungen und zulässige nicht überlappende Text-Merges ohne Dateiauswahl, konfliktfreien Plan installieren und Dateiprüfung. Kostenloses Nexus benötigt Browserbestätigungen; Premium/API können autorisierte Downloads erlauben, sind hier nicht mit einem echten Konto getestet.

## Wann der Installer anhält

Unbekannte oder abweichende Version, mehrere alternative Dateien, unsichere Pfade/Links, EXE/DLL im Modarchiv, unterschiedliche Binärdaten ohne zulässige Autor-Ersetzung, überlappende Textänderungen, Hashfehler, fehlende Abhängigkeit, veränderte installierte Datei. Es gibt keinen generischen „alles erlauben“- oder „Fehler ignorieren“-Schalter.

## Vorbereitete Fehlerbehandlung

Vorübergehende Downloadfehler werden begrenzt wiederholt. Gültige abgeschlossene Extraktionen werden anhand der Prüfsummen wiederverwendet. Windows-/ZIP-Pfadtrenner werden vereinheitlicht; echte Größen-/Inhaltsfehler bleiben blockierend. Ein fehlgeschlagenes optionales Archiv blockiert nicht das Erkennen anderer Downloads. Ein zweites abweichendes Archiv wird nicht automatisch über eine bestätigte Fassung gewählt. Nach misslungener Abschlussprüfung wird nur erneut geprüft, nicht doppelt installiert.

Unbekannte Fehler erzeugen eine bereinigte lokale Diagnose mit Schritt, Pfaddifferenzen und Handlungshinweis. Keine automatische Übertragung, keine selbstständig heruntergeladenen Reparaturskripte.
