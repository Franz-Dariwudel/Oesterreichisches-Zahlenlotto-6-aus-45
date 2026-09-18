# Österreichisches Zahlenlotto 6 aus 45

Version 1.0.28 · einschließlich Joker

Lokales Python-/GTK-4-Programm für Österreichs Lotto und Joker. Historische
Ziehungen und Quoten, getrennte Statistiken, profilbasierte Tippserien,
Druck. Autor: Josef Lehner. Lizenz: GPL-3.0-only; vollständiger
Lizenztext in LICENSE. Kontakt: https://dogtruck.eu.

Jede Kombination hat bei fairer Ziehung dieselbe Chance. Historische Filter
strukturieren Tipps und verbessern keine Gewinnwahrscheinlichkeit.

## Downloads

- [Datenbank herunterladen (ZIP)](https://github.com/Franz-Dariwudel/Oesterreichisches-Zahlenlotto-6-aus-45/releases/latest/download/lotto-datenbank.zip)
- [Programm und vollständiger Quellcode](https://github.com/Franz-Dariwudel/Oesterreichisches-Zahlenlotto-6-aus-45/releases/latest)

Die Datenbank enthält 3.683 Lotto- und 3.574 Joker-Ziehungen bis 16.09.2026,
Quoten sowie 8.145.060 Lotto-Kombinationen und 1.000.000 Joker-Nummern.
Persönliche Tippserien, Profile, Caches und Sitzungsprotokolle sind nicht enthalten.
ZIP entpacken und im Programm **Gemeinsam → Datenbank auswählen …** öffnen.
Die vorhandene Arbeitsdatenbank nicht überschreiben. Eine Prüfsumme liegt dem
Download bei. Quelldaten und Marken behalten die Rechte ihrer jeweiligen Anbieter;
die GPL-Lizenz des Programmcodes ist keine Neulizenzierung fremder Inhalte.

## Voraussetzungen und Installation

Linux Mint mit Python 3.12, GTK 4, PyGObject, Pycairo und Poppler.
Systempakete: `python3-gi`, `python3-gi-cairo`, `gir1.2-gtk-4.0`,
`python3-cairo`, `poppler-utils`. Matplotlib für Diagramme; das installierbare
Python-3.12-Linux-Paket enthält Matplotlib und dessen Python-Abhängigkeiten
unter `vendor/` einschließlich Lizenzinformationen. GTK/Poppler bleiben
Systemabhängigkeiten. Kein Administratorstart notwendig.

Quellcodeversion: System-Matplotlib (`python3-matplotlib`) verwenden oder
`python3 -m venv --system-site-packages .venv` und anschließend
`.venv/bin/python -m pip install -r requirements.txt`.

```bash
python3 install.py
python3 -B -m lotto45
```

Die Installation legt Programmdateien, Desktop- und Menü-Starter sowie ein
Dateijournal an. Standardziel: `~/.local/share/6aus45`. Bereits vorhandene
Installationen nicht überschreiben. Individuelles Ziel: `--prefix /pfad`.
`--desktop-dir` und `--menu-dir` erlauben alternative Starterordner.

```bash
python3 ~/.local/share/6aus45/install.py --uninstall
```

Die Deinstallation entfernt unveränderte Installationsdateien, erzeugte
Konfigurations-/Logdateien und beide Starter; geänderte Dateien und später erstellte Datenbanken bleiben
Benutzerdaten und werden gemeldet. Fremde Ordner bleiben erhalten.

## Bedienung

- **Lotto 6 aus 45 / Joker:** letzte Ziehung, Suche, Ziehung nach Datum,
  Quoten, getrennte Statistiken, Tipps erstellen, Tipp-Historie und Drucken.
- **Gemeinsam:** Auf neue Daten prüfen, Quellen verwalten/prüfen,
  Importprotokoll, Datenbestand, Prüfhinweise, Datenbank prüfen/sichern,
  Wiederherstellen, lokale Datei importieren, Diagnose.
- **Bearbeiten → Einstellungen:** Sprache, Sprach-/Hilfedownload und
  Sicherheitsgrenze für Tippserien (Standard 10.000, maximal 1.000.000).
- **Profil:** gespeichertes Profil im Tippformular laden, speichern oder
  löschen. Lotto und Joker haben getrennte Profilnamenräume. Laden/Speichern
  setzt das eingestellte Profil für den parameterisierten CLI-Aufruf.
- **Hilfe:** HTML-Hilfe in zehn Sprachen, Über, Komponenteninformationen
  und sitzungsbezogenes Fehlerprotokoll.

Ziehungsdaten erscheinen mit berechnetem Wochentag. Datumssuche akzeptiert
Jahr, Monat/Jahr oder Tag; Wochentag und Ziehungstyp grenzen weiter ein.
Joker bleibt sechsstelliger Text einschließlich führender Nullen. Quoten
bewahren ATS/EUR, unbekannte Werte, Nullwerte und Jackpotkennzeichnungen.

## Tippserien und Profile

„Reiner Zufall“ ist unabhängig von den Filterregeln. Bei „Statistisch gefiltert“
werden die gewünschten Regeln ausschließlich mit Häkchen aktiviert. Die aktuellen
Werte und die zuständige Statistik stehen neben dem Häkchen.

Die Werte unter **Statistiken → jeweilige Auswertung → Tippfilter einstellen**
ändern und speichern: Summen/Quantile unter Summen, gerade Zahlen unter Parität,
niedrige Zahlen unter Niedrig/Hoch, Folgen unter Nachbarn, Wiederholungen unter
Wiederholung, Spannweite unter Zahlenbereichen, Paarpräferenz unter Paaren und
Zahlengewichtung unter Zahlen. Weitere Lotto-Muster unter Muster und Verteilungen.
Bei Joker: Positionsgewichtung unter Joker-Statistik, übrige Regeln unter Muster
und Verteilungen. Der Bezugszeitraum für Tippfilter wird je Spiel gemeinsam
verwendet; die Anzeige-Filter der Statistik bleiben davon unabhängig.
Die Werte liegen in `config/settings.json` unter `tip_rule_settings`.
Ein Min-/Max-Paar wird mit Komma eingegeben, etwa `2,4`.
Laden eines Profils übernimmt seine Werte in diese Einstellungen; die Historie
bestehender Tippserien bleibt unverändert.

Lotto: Zahlengewichtung, Zeitraum, Summen/Quantile, gerade und niedrige Zahlen,
Folgen, Wiederholung aus letzter ausgewählter Ziehung, Spannweite, Primzahlen,
Birthday-Zahlen, Dekadenbelegung, Paarpräferenz und ungewöhnliche Strukturen.
Joker: Positionsgewichtung, Summe, verschiedene Ziffern, benachbarte Folgen,
maximale Mehrfachziffern, Palindrome und gewichtete letzte zwei Stellen.

Jede fertige Serie wird atomar mit vollständigem Profilschnappschuss und
RNG-Modus gespeichert. Duplikate innerhalb einer Serie sind ausgeschlossen.
Abbruch oder unerfüllbare Filter speichern keine Teilserie. Nach begrenzten
Versuchen nennt L012 die ablehnenden Regeln. Die Historie bleibt auch nach
dem Drucken erhalten. SystemRandom ist Standard; `--seed` ist ein
explizit markierter Testmodus.

Ziehungs-, Statistik- und Diagrammexporte werden nicht angeboten. Tipps können als CSV gespeichert und gedruckt werden. Druck öffnet den
Systemdialog, ohne automatisch einen physischen Druckauftrag abzusenden.

## Daten und Quellen

`resources/default_sources.json` enthält die Standardquellen; eigene
Einstellungen liegen in `config/download_sources.json`. Offizielle CSVs
werden bevorzugt, Joker-PDF hat einen eigenen Parser. Vorbelegte Fremdarchive
sind standardmäßig deaktiviert. Bestehende Benutzerauswahlen bleiben erhalten.
Fehlende Standards werden beim GUI-Start deaktiviert ergänzt, damit keine
zusätzlichen Downloads ungefragt eingeschaltet werden.

Quellen besitzen Name, Spiel, URL, Format, Priorität und Aktivierung. CSV/PDF
müssen dem bekannten Archivformat entsprechen; Formatwahl ist kein beliebiger
CSV-Spaltenmapper. Die Jahreszahl muss im Jahresdateinamen stehen. Quellenprüfung
prüft Abruf und tatsächliche Parserstruktur ohne Import. HTTP-Fehler,
leere/zu große/abgeschnittene Dateien und Formatabweichungen werden gemeldet.

Downloads verwenden ausschließlich eigene gesperrte Unterordner unter `/tmp`.
Sie werden nach jedem Lauf gelöscht; verwaiste eindeutig markierte Ordner
werden beim Start beseitigt, aktive und fremde Ordner bleiben erhalten.
Fehlerhafte heruntergeladene Rohdateien werden, soweit schreibbar, dauerhaft
unter `data/rejected/<sha256>.bin` zur Diagnose erhalten. Dies ist kein Cache.
Sprachdownloads nutzen gemäß persönlicher Vorgabe einen eigenen temporären
Unterordner im Benutzer-Downloadordner.

Prüfsummen verhindern doppelte Verarbeitung. HTTP-Validatoren reduzieren
Wiederholungsdownloads, wenn der Server diese bereitstellt. Neue/geänderte
Jahresdateien werden normalisiert und transaktionell übernommen. Konflikte
werden sichtbar protokolliert und nicht stillschweigend ersetzt. Explizite
Korrekturen über `--allow-corrections`; Originalbytes und Änderungshistorie
bleiben erhalten. Importprotokoll ist dauerhaft, `logs/error.log` beginnt je
Programmsitzung neu.

Vorhandene vollständige Tippkataloge bleiben erhalten. Neue Datenbanken und
Wiederherstellungen bauen kein Universum mit Millionen Kombinationen auf.
Die historischen Fremdschlüssel benutzen weiterhin nur benötigte Tipps.
Datenlücken und Quotenabdeckung sind in DATA_STATUS.md dokumentiert.

## Statistiken

Die Spalte Kennung ist ausgeblendet, solange das jeweilige Spielarchiv nur
Hauptziehungen enthält. Sobald ein anderer Wert vorliegt, erscheint sie beim
Aktualisieren oder erneuten Öffnen automatisch, auch außerhalb des Zeitfilters.

Alle bisherigen Lotto-Statistiken bleiben erhalten. Zusätzlich: echte
rollierende Häufigkeit/Z-Scores (Fenster bis 20 Ziehungen), Summenquantile,
Primzahlen/Birthday-Anteil, Spiegelpaare, Abstände, arithmetische Muster und
gewichtete Paar-Zentralität. Chi-Quadrat ist rein deskriptiv ohne p-Wert.
Joker ergänzt Positionsheatmap, Summe, Parität, Mehrfachziffern, gleiche
Nachbarn, längste Serie, Symmetrie, Übergänge, Endstellen, Shannon-Entropie
und Wochentagsvergleich. Optionaler Netzwerkgraph ist nicht Bestandteil 1.0.

Zeitraum: alle/letzte N, Von/Bis, Wochentag und Ziehungstyp. Zuerst
Kalenderfilter, anschließend letzte N anwenden. Filter mit „Aktualisieren“
übernehmen. Diagramme nennen Zeitraum, Stichprobengröße und
aktive Filter. Matplotlib zeichnet lokal und übernimmt Schrift/Farben des
Systemthemas. Unter X11 wird standardmäßig Cairo ohne DRI3 verwendet;
eine explizite Auswahl über GSK_RENDERER wird respektiert.
Statistische Regeldefinitionen: STATISTICS.md.

## Sicherung und Fehlerbehandlung

Vor der einmaligen additiven Schema-Erweiterung wird ein befülltes Archiv
über die SQLite-Backup-API unter `data/backups/` gesichert. Archivschema 1
bleibt kompatibel; `metadata.extension_version=1` kennzeichnet die neuen
Tabellen. Unbekannte Versionen werden abgewiesen. Die GUI-Startprüfung
prüft Integrität und Fremdschlüssel; fehlende DB wird leer angelegt und
sichtbar gemeldet. Beschädigte Originale werden nicht überschrieben.
Wiederherstellung erzeugt eine neue geprüfte Datei; Auswahl wird erst danach
gespeichert. Manuelle Sicherung verlangt einen freien Dateinamen.

Ungültige Einstellungen werden als `.broken` gesichert, dann Standards
angelegt und die Ursache angezeigt. Der Diagnosebericht enthält Versionen,
Integritätsresultat, Import- und Quellenstatus ohne lokale Pfade/Rohdaten.
Alle Fehlercodes L001–L014 und Abhilfen stehen in der HTML-Hilfe.

## Kommandozeile

```bash
python3 -B -m lotto45 --help
python3 -B -m lotto45 --summary --check
python3 -B -m lotto45 --download
python3 -B -m lotto45 --tips 12 --game lotto
python3 -B -m lotto45 --tips 12 --game joker --profile
python3 -B -m lotto45 --tips 12 --game lotto --profile MeinProfil
python3 -B -m lotto45 --db /pfad/test.sqlite3 --tips 6 --game joker --seed 42
python3 -B -m lotto45 --backup /pfad/neue-sicherung.sqlite3
python3 -B -m lotto45 --diagnose
python3 -B -m lotto45 --stats patterns --game joker --last 100
python3 -B -m lotto45 --stats charts --chart zscore --stats-number 17 --from-date 2025-01-01 --weekday 6
python3 -B -m lotto45 --import-csv /pfad/NN_W2D_STAT_Lotto_2026.csv
python3 -B -m lotto45 --import-joker-pdf /pfad/NN_W2D_STAT_Joker_2026.pdf
python3 -B -m lotto45 --import-json /pfad/ziehungen.json --allow-corrections
```

`--profile` führt das eingestellte Profil aus; fehlend/ungültig ergibt einen
Fehler, kein stilles Ersatzprofil. `--generate` bleibt ausschließlich als
optionaler CLI-Universum-Aufbau erhalten. Exitcode 0 bedeutet Erfolg,
1 Aktionsfehler, 2 falsche Parameter. Lese-CLI legt keine fehlende DB an.

## Sprachen, Quellen und Auslieferung

Sprachdateien: `languages/<code>.json`, UTF-8-Objekt mit Textschlüsseln und
Stringwerten; `en.json` liefert fehlende Texte. Genau eine Sprache wird
automatisch genutzt. Dateien werden beim Öffnen der Einstellungen erneut
erkannt. HTML-Hilfe `help/<code>.html` mit passendem `lang`-Attribut folgt
ausschließlich der gewählten Sprache. Fehlende Hilfe wird direkt gemeldet.

Sprach-/Hilfedownload installiert nur fehlende Dateien aus einer explizit
zugeordneten GitHub-Projektquelle, validiert Inhalt und entfernt eigene
Zwischendateien. Die öffentliche Projektquelle ist
`Franz-Dariwudel/Oesterreichisches-Zahlenlotto-6-aus-45`. Alle zehn Sprachen
und die zugehörigen Hilfen sind vollständig enthalten.

Build: `python3 build.py`. `auslieferung/` enthält vollständigen dokumentierten
Quellcode und das fertige DEB-Paket. Der Python-3.12-Bytecode liegt als Zwischenpaket unter `work/build/`. Keine Benutzerdaten,
Einstellungen, Logs, Testarchive oder privaten Starter werden paketiert.
Tests: `.venv/bin/python -m unittest discover -s tests -v` (GTK-Tests benötigen
eine grafische Sitzung). Systemkomponenten und Drittbibliotheken behalten
ihre eigenen Lizenzen; siehe THIRD_PARTY.md und `vendor/*.dist-info`.

Datumsfelder bieten einen Kalender neben dem Eingabefeld. TT.MM.JJJJ, beispielsweise 11.1.2000, und YYYY-MM-DD werden akzeptiert; gespeichert wird das ISO-Format. Leere Felder begrenzen den Zeitraum nicht.

Unter Gemeinsam vereint „Daten aktualisieren und prüfen“ den Datenabruf, die Datenbankprüfung und einen automatisch unter `logs/` gespeicherten Diagnosebericht.

Der gemeinsame Prüfablauf beginnt mit der Quellenprüfung und zeigt alle vier Schritte einzeln an.

## Sprachen und Menühilfe

Alle zehn Sprachen sind lokal enthalten: de, en, es, fr, pt, zh, hi, ar, ru, tr. Unter Bearbeiten → Einstellungen die gewünschte Sprache auswählen und speichern. Hilfe → Erhalten öffnet die passende HTML-Hilfe mit Inhaltsverzeichnis und 53 Menübeschreibungen. Die zusätzlichen acht Übersetzungen wurden maschinell erstellt und technisch sowie bei zentralen Menübegriffen geprüft; eine vollständige muttersprachliche Prüfung steht aus. Die Sprachdateien bleiben frei bearbeitbar. Der Sprachdownload verwendet Franz-Dariwudel/Oesterreichisches-Zahlenlotto-6-aus-45 als Standardquelle.

## DEB-Paket für Linux Mint 22 / Ubuntu 24.04 (amd64)

Für Version 1.0.28 wird vorerst kein neues DEB erstellt oder veröffentlicht.
Die folgenden Angaben beschreiben den bisherigen lokalen Paketstand 1.0.27 und den optionalen Bauweg.

`oesterreichisches-zahlenlotto_1.0.27_amd64.deb` per Doppelklick oder mit
`sudo apt install ./oesterreichisches-zahlenlotto_1.0.27_amd64.deb` installieren.
Python 3.12 und GTK 4 werden vorausgesetzt; benötigte Systempakete löst apt auf.
Ein Menüeintrag und ein Desktop-Starter mit dem 3D-Programmicon werden eingerichtet.
Ist keine eindeutige grafische Sitzung aktiv, erfolgt die Desktop-Einrichtung bei
der nächsten Anmeldung. Benutzerdateien liegen unter
`~/.local/share/oesterreichisches-zahlenlotto/`. Die Entwicklungsinstallation bleibt separat.

Entfernen: `sudo apt remove oesterreichisches-zahlenlotto`. Erfasste Programmdateien,
Desktop-Starter und erzeugte Einstellungen werden entfernt; eigene Datenbanken und
Exporte bleiben erhalten. Vorher das Programm schließen.

Bauen: `.venv/bin/python build.py`, anschließend `python3 build_deb.py`.
Das DEB enthält die bereinigte Lotto-/Joker-Datenbank. Bei der Einrichtung wird sie
für den Benutzer installiert, sofern noch keine Datenbank vorhanden ist. Bestehende
Datenbanken werden nicht überschrieben. Ein separates Herunterladen ist bei einer
Neuinstallation nicht nötig. Unveränderte mitgelieferte Datenbanken werden bei der
Deinstallation entfernt, später bearbeitete Datenbanken bleiben erhalten.

Fertige Ausgaben: `auslieferung/`. Zwischenpakete: `work/build/`.
`dist/` wird nicht mehr verwendet. Der DEB-Bau verwendet als Datenbankeingabe
`work/publication/lotto-datenbank.zip` (bereinigtes Datenbankarchiv).

## Bebilderte Programmhilfe

Alle zehn Hilfesprachen enthalten die ausführliche Einstellungsreferenz mit Standardwerten, Wertebereichen und Wirkungen.
Alle zehn Hilfen führen sämtliche 53 Menüaktionen auf und enthalten echte
GTK-Aufnahmen mit ausdrücklich gekennzeichneten Beispieldaten. Die Bilder liegen
unter `help/images/` und funktionieren ohne Internet.

Aufnahmen erneuern: `.venv/bin/python tools/capture_help.py`.
Kapitel erzeugen: `python3 tools/illustrated_help.py`.
Prüfen: `.venv/bin/python -m unittest discover -s tests -p test_localization.py`.
Fertige Pakete liegen in `auslieferung/`; temporäre Bau- und Prüfdaten in `work/`.
