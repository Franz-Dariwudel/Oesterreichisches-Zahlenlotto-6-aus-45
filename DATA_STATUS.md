## Aktualisierung 18.09.2026 · Version 1.0.0

Offizielle Quellen geprüft und importiert: 3.683 Lotto-Ziehungen und
3.574 Joker-Ziehungen, jeweils bis 16.09.2026. Jeweils eine neue Ziehung,
zudem offizielle Joker-Quoten ergänzt. Keine neuen Konflikte/Importfehler.
Frühere Hinweise und historische Quotenlücken bleiben erhalten.
Vor der Schema-Erweiterung wurde das vollständige Archiv gesichert.

# Datenstand · 15.09.2026

- Lotto-Katalog: **8.145.060** eindeutige Tipps.
- Joker-Katalog: **1.000.000** eindeutige Nummern, `000000` bis `999999`.
- Lotto: **3.682** Ziehungen vom **07.09.1986 bis 13.09.2026**, **23.661** Quotenzeilen.
- Joker: **3.573** Ziehungen vom **02.10.1988 bis 13.09.2026**, **6.635** Rangzeilen.
- Joker: **1.093** Ziehungen ab 2017 stammen aus offiziellen Jahres-CSV-Dateien. **2.480** ältere Ziehungen wurden aus dem historischen Zusatzarchiv ergänzt; für 15 davon liegen nun einzeln belegte Gewinnquoten vor; die übrigen 2.465 enthalten weiterhin nur Zahlen. Der Bestand ist keine unabhängige Garantie für sämtliche historischen Ziehungstermine.
- Die Jahresarchive liefern für Joker-Ränge 2–6 nur Gewinnerzahlen. Durch belegte Einzelquoten wurden 1.810 fehlende Beträge ergänzt; 3.655 Quotenzeilen haben weiterhin keinen Betrag (NULL).
- **50 Prüfhinweise**: acht historische Lotto-Archivhinweise, 38 abweichende Lotto-Quoten zwischen zwei offiziellen 2017-Archiven sowie vier neue Hinweise zum Joker-Zusatzarchiv. Keine automatische Überschreibung. Beide Originalquellen bleiben gespeichert.
- Die 8 historischen Hinweise umfassen auch eine verschobene und eine entfallene Ziehung sowie einen erklärenden Archivtext. Diese Texte sind keine tatsächlich durchgeführten zusätzlichen Ziehungen.
- Bei Lotto ab 2018 liefern die eingelesenen Jahres-CSV-Dateien nur die sortierten Zahlen. Die Ziehungsreihenfolge wird nicht erfunden.

## Offizielle Quellen

- Lotto: https://www.win2day.at/lotterie/lotto/lotto-statistik-zahlen-ergebnisse-download
- Joker: https://www.win2day.at/lotterie/joker-statistik

40 Quellenstände sind in `import_quellen` archiviert: 25 originale Archiv-/Dienstantworten und 15 als geprüfte Datenauszüge gekennzeichnete historische OTS-Belege. Eine zweite Quelle für dieselbe Ziehung erzeugt keine neue Ziehung. Der Zeitraum ist der tatsächlich importierte Bestand; er ist keine unabhängige Vollständigkeitsbestätigung jedes historischen Ziehungstermins.

Die Statistikbereiche des Analyse-Dokuments sind seit Version 0.3.0 umgesetzt: Zahlendetails, Erwartungswerte, Ziehungskennzahlen, Verteilungen, Kombinationen, Ranglisten und acht Diagramme. Einzelheiten: STATISTICS.md. Die Auswertungen beziehen sich auf den oben beschriebenen importierten Lotto-Bestand und bestätigen keine Vollständigkeit historischer Daten. Noch keine GitHub-Veröffentlichung und daher noch keine produktive Projektadresse für den Sprachdownload.

## Anzeige und zusätzliche Quelle (0.4.0)

Fehlende Joker-Archivbeträge bleiben in der Datenbank NULL. Die Oberfläche kann im geprüften Zeitraum 04.07.2025–15.09.2026 markierte Standardbeträge aus dem offiziellen Gewinnplan anzeigen; dies ist keine nachträglich belegte Einzelziehungsquote. Die Zählung fehlender Beträge bleibt deshalb unverändert.

Die zusätzliche, zunächst inaktive GitHub-Quelle daowa89/lottery-archive liefert Lotto-Zahlen ohne Quoten. Am 15.09.2026 enthielt sie 3.680 Ziehungen vom 07.09.1986 bis 13.09.2026; bei 3.679 gemeinsamen Datumswerten stimmten Haupt- und Zusatzzahlen mit dem lokalen Archiv überein. Eine zusätzliche Datumszeile wurde dabei festgestellt. Die aktuelle, vom Benutzer neu aufgebaute Datenbank enthält auch die zusätzliche Datumszeile dieser Quelle. Der Lotto-Bestand wurde bei der Joker-Ergänzung nicht geändert.

## Joker-Ergänzung am 15.09.2026 (0.4.6)

Die offizielle Übersichtsseite verlinkt nur 2023–2026; direkte Jahres-CSV-Dateien für 2017–2022 sind ebenfalls verfügbar und werden jetzt beim Download berücksichtigt. Zusätzlich wurde das öffentliche historische Archiv von Norbert M. Säumel übernommen: http://mathematik.norbertsaeumel.at/serie/joker/statistik.php.

Das Zusatzarchiv meldete 3.570 Zeilen bis 09.09.2026, darunter zwei verschiedene Nummern für 25.03.2026. Beide mehrdeutigen Zeilen werden ausgelassen und als Prüfhinweise erhalten; der offizielle Datensatz bleibt bestehen. Bei 16.06.2024 und 22.06.2025 weichen die Nummern von win2day ab; die offiziellen Werte bleiben erhalten. Die offizielle Ziehung vom 10.12.2017 fehlt im Zusatzarchiv und wird über die Jahres-CSV abgedeckt. Aus der Zusammenführung entstehen 3.573 eindeutige gespeicherte Joker-Ziehungen.

Die andernorts angezeigte Nummer 3.351 ist eine dortige laufende Ziehungsnummer und kein Beleg für die Gesamtzahl dieses Archivs seit 1988. Quelle zum Vergleich: https://ziehungen.at/joker.

Vor der Ergänzung wurde eine konsistente Sicherung unter `data/backups/vor-joker-ergaenzung-20260915.sqlite3` angelegt. Bestehende Lotto-Daten sowie sämtliche vorherigen Joker-Ziehungen und Quoten wurden auf unveränderten Inhalt geprüft. SQLite-Integrität und Fremdschlüssel sind fehlerfrei.

## Dateiname ab Version 0.4.7

Die aktive Datenbank heißt `data/lotto_00.sqlite3`. Am 15.09.2026 wurde nur der lange Wiederherstellungsname gekürzt und die gespeicherte Auswahl angepasst; der Dateiinhalt blieb anhand der SHA-256-Prüfsumme unverändert. Weitere benötigte Wiederherstellungskopien erhalten fortlaufende kurze Namen.

## Belegte Joker-Quoten am 15.09.2026 (0.4.10)

- Offizieller Ergebnisdienst: https://lotterien.win2day.at/jam/drawgame/v1/public/drawResultInfo/joker?limit=5000&offset=0
- Der Dienst liefert 362 Ziehungen vom 17.09.2023 bis 13.09.2026 mit sechs vollständigen Rängen. Daraus wurden 1.810 bisher fehlende Beträge ergänzt. Bereits bekannte Beträge bleiben vorrangig erhalten.
- 15 historische Einzelbelege liefern 77 zusätzliche Quoten: acht Ziehungen aus 2000, fünf aus 2003 und zwei aus 2010. Quellenadressen und Zahlenangaben: `resources/joker_quotes_verified.json`. Diese Datenauszüge sind keine HTML-Originaldateien.
- Insgesamt haben 1.108 Joker-Ziehungen gespeicherte Quoten; 377 davon besitzen Beträge in allen gespeicherten Rängen. 2.465 Ziehungen haben weiterhin keine Quoten. Die Quotenansicht blendet diese aus; Zahlen und Datumssuche bleiben erhalten.
- **Kein lückenloser Nachweis ab 2000:** OTS enthält historische Einzelmeldungen, der direkte automatische Abruf wurde bei der Prüfung mit HTTP 403 / Zugriffsschutz abgelehnt. Eine vollständige Jahrgangsabdeckung wurde nicht bestätigt. Fehlende Werte werden nicht erfunden.
- Die Lotto-Daten, sämtliche Ziehungszahlen und bereits vorhandene Quotenbeträge blieben unverändert. Vorher wurde eine konsistente SQLite-Sicherung erstellt und der Import an einer Kopie geprüft. Wiederholter Download, Integrität und Fremdschlüssel sind fehlerfrei. Die Zahl der Prüfhinweise bleibt 50.

## Zusätzliche Quellenprüfung: 6richtige.at (15.09.2026)

Die vom Benutzer genannten zwölf Jahresarchive 1988–1999 unter https://www.6richtige.at/zahlenarchiv_at.html wurden neu geprüft. Alle 29 verlinkten GIF-Tabellen wurden im Browser geladen; die Spaltenüberschriften wurden visuell kontrolliert. Sie enthalten Datum, Lottozahlen, Zusatzzahl, Lottosechser und Ziehungsnummer, aber keine Joker-Tabellen. Die allgemeine Seitenüberschrift ist kein Beleg für historische Joker-Quoten. Auch die erste zusätzlich geprüfte Jahrestabelle 2000 enthält nur diese Lotto-Spalten.

Der getrennte Bereich https://www.6richtige.at/at_alle_ziehungsdatum.html nennt Einzelziehungsdetails ab 04.10.2017. Für diesen Termin wurde Joker 539350 mit sechs Gewinnrängen als Bild tatsächlich geprüft: https://www.6richtige.at/xx_at_db/xx171004.gif. Das ist ein brauchbarer einzelner Sekundärbeleg, keine bestätigte vollständige Abdeckung seit 2017 oder seit 2000.

Die Quelle wurde als Vergleichsquelle dokumentiert, aber derzeit nicht in die automatische Downloadliste aufgenommen: GIF-Texterkennung wird nicht unterstützt, und der direkte Python-Abruf der Jahresseite 2000 lieferte HTTP 403. Die historische Linkliste schließt keine Joker-Quotenlücken. Keine Datenbankänderung und kein neuer Import aus dieser Quelle.
