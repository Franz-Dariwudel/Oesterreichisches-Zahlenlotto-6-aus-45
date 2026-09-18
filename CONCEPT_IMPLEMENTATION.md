# Umsetzung des Konzepts vom 17.09.2026

Version 1.0.0, 18.09.2026. Arbeitsordner: bestehendes Projekt 6aus45.
Das Konzept wurde als fachlicher Auftrag auf die vorhandene Architektur
übertragen. Vorhandene Daten und Funktionen wurden erhalten.

| Konzeptbereich | Umsetzung |
|---|---|
| Zielbild, Menütrennung | GTK-4-Menüs Lotto/Joker/Gemeinsam; gemeinsame Statuszeile und Datencheck |
| Universum vs. Historie | Bestehende Kataloge erhalten; kein vollständiger Katalogaufbau bei neuen Archiven |
| Datenbank | Bestehendes normalisiertes Archiv plus Profile, Batches, Batch-Tipps, Quellenstatus, HTTP-Cache und Importläufe |
| Identität/Dubletten | Bestehende Datum+Kennung-Schlüssel; SHA-256; UNIQUE(batch_id,value); atomare Übernahme |
| Quellen | Ressourcenliste, konfigurierbare URL/Spiel/Format/Priorität/Aktivierung, Parserprüfung, offizielle Quellen bevorzugt |
| Download | Eigener gesperrter /tmp-Bereich, begrenzte Dateigröße, Längenprüfung, Abbruch, Prüfsummen/HTTP-Validatoren |
| Lotto | Bestehende Statistiken plus Muster, Quantile und rollierende Häufigkeit/Z-Score |
| Joker | Positionen, Summen, E/O-Muster, Mehrfachziffern, Folgen, Symmetrie, Übergänge, Endstellen, Entropie, Wochentage |
| Filter | Kalenderbeginn/Ende, letzte N, Wochentag und Typ; Werte auf Statistikseiten gespeichert, Generator mit Aktivierungshäkchen (1.0.4) |
| Tippgenerator | SystemRandom; getrennter Testmodus; begrenzte Versuche mit Ablehnungsgründen; persistenter Profilschnappschuss |
| Drucken | GTK-Systemdruckdialog; Historie unverändert; Tipp-CSV verfügbar; andere Dateiexporte entfernt (1.0.2) |
| Grafik | Matplotlib GTK4, Systemthema, Tooltip; keine Dateiexporte (1.0.2) |
| Fehlerbehandlung | L001–L014, Config-.broken, vorherige DB-Sicherung, geschützte Originale, Wiederherstellung als neue Datei |
| Start | Eigene Temp-Reste, Config, Datenbankintegrität/Fremdschlüssel, additive Migration, Standardquellen |
| Sicherung/Diagnose | SQLite-Backup, Integritätsprüfung, Wiederherstellung, anonymisierter Diagnosebericht |
| CLI/Pakete | Tatsächliche Profilausführung, vollständiger Quellcode und installierbarer Python-3.12-Bytecode |

## Bewusste Architekturentscheidungen

Die vorhandenen deutschen Archivtabelle-Namen bleiben erhalten. Ein Austausch
gegen neue englische Namen hätte die bewährten Abfragen und archivierten
Schlüssel unnötig verändert. `schema_version=1` bezeichnet das vorhandene
Archiv; `extension_version=1` die additive Konzept-Erweiterung.

Die bestehende Auswahl in `config/download_sources.json` bleibt bestehen,
auch wenn früher ausdrücklich Fremdarchive aktiviert wurden. Neue
Installationen aktivieren ausschließlich die offiziellen Quellen.

Die im Konzept ausdrücklich optionalen vollständigen Universum-Tabellen,
Netzwerkgraphen und automatischen rotierenden Sicherungen gehören nicht zur
Standardfunktion. Der frühere manuelle CLI-Universum-Aufbau bleibt kompatibel.
Die gewichtete Paar-Zentralität wird als Tabelle dargestellt. Sie entspricht
bei vollständig gezogenen Sechsergruppen fünfmal der Zahlenhäufigkeit und
liefert deshalb keine zusätzliche Prognoseinformation.

## Prüfung und Grenzen

Automatisierte Tests decken bestehende Archiv-/Suchfunktionen und die neuen
Generator-, Profil-, Migrations-, Temp- und Fehlerpfade ab. GTK-Seiten
wurden in der tatsächlichen grafischen Sitzung geöffnet und bildlich geprüft.
PDF-Seiten wurden gerendert; Textvollständigkeit und Seitenumbrüche geprüft.
Der offizielle Onlineabruf wurde am 18.09.2026 ausgeführt und brachte jeweils
eine neue Lotto- und Joker-Ziehung vom 16.09.2026 sowie die offiziellen
Joker-Quoten. Es gab dabei keine Importfehler oder Konflikte.

Ein physischer Papierausdruck ist kein Bestandteil des Tests; Druckausgabe
wird über GTK und dessen PDF-Ausgabepfad geprüft. Eine optionale
GitHub-Sprachquelle ist noch nicht veröffentlicht und bleibt konfigurierbar.
Historische Quotenlücken werden weiterhin sichtbar ausgewiesen und nicht
mit erfundenen Daten gefüllt. Siehe DATA_STATUS.md.

Die bisher importierten Jahresarchive verwenden durchgehend die vorhandene
Rundenkennung `haupt`; einen verlässlich belegten zusätzlichen Ziehungstyp
liefern diese gespeicherten Datensätze nicht. Der Typfilter arbeitet mit den
tatsächlich gespeicherten Kennungen. Bonusziehungen werden nicht allein aus
dem Wochentag als neue Datensätze erfunden; der Wochentagsfilter ist unabhängig.
