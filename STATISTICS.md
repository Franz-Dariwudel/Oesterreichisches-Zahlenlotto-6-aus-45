# Lotto-Statistik · 0.4.0

Die Vorschläge aus `lotto_6_aus_45_statistiken.txt` sind wie folgt umgesetzt.
Alle Menüpfade beginnen bei **Statistik**. Bedienung und vollständige Definitionen stehen auch in `help/de.html` und `help/en.html`.

| Abschnitt im Konzept | Programmansicht | Umfang |
| --- | --- | --- |
| 1 Zahlenstatistik | Zahlen und Zeiträume → Zahlendetails; Zeiträume vergleichen | Alle 45 Zahlen, Häufigkeit/Anteil, letztes Datum, aktuelle Pause, Trefferabstände, abgeschlossene Pause, Zusatzzahl; sechs Zeitfenster |
| 2 Erwartungswert | Zahlen und Zeiträume → Erwartungswerte und Abweichungen | Ist, Erwartung, signierte/absolute/relative Abweichung, σ und z |
| 3 Ziehungsstatistik | Ziehungen und Verteilungen → Ziehungsdetails | Zahlenwerte, Muster und Abstände in drei Teilansichten; jede gespeicherte Lotto-Ziehung |
| 4 Zahlenbereiche | Ziehungen und Verteilungen → Zahlenbereiche | Fünf Bereiche, Häufigkeit/Anteil/Durchschnitt, ohne und mehrfach |
| 5 Gerade/ungerade | Ziehungen und Verteilungen → Gerade / ungerade | Alle sieben Verteilungen, Anzahl/Anteil/letztes Auftreten |
| 6 Niedrig/hoch | Ziehungen und Verteilungen → Niedrig / hoch | Alle sieben Verteilungen, Grenze 22/23 |
| 7 Zahlensumme | Ziehungen und Verteilungen → Zahlensummen | Minimum/Maximum/Mittelwert/Median und sieben Klassen; nach Häufigkeit sortierbar |
| 8 Paare | Kombinationen → Paare | Alle 990, auch ungezogene, mit Häufigkeit/Anteil/letztem Datum/Pause; auf- und absteigend sortierbar |
| 9 Dreier | Kombinationen → Dreierkombinationen | Alle 14.190 mit Häufigkeit, Anteil, letztem Datum und Pause |
| 10 Nachbarzahlen | Kombinationen → Nachbarzahlen und Folgen | Anteil mit mindestens einem Paar, Anzahl mit mindestens zwei; 44 Paare, 43 Dreier; maximale und längste Folgen |
| 11 Wiederholungen | Ziehungen und Verteilungen → Wiederholungen zur Vorziehung | Fünf Klassen 0/1/2/3/≥4 sowie Häufigkeiten je Zahl |
| 12 Endziffern | Kombinationen → Endziffern | Ziffern 0–9, Mehrfachauftreten und alle 185 möglichen Gruppen gleicher Endziffer |
| 13 Abstände | Ziehungen und Verteilungen → Abstände sortierter Zahlen | Fünf Nachbardifferenzen je Ziehung; Minimum/Maximum/Mittelwert, Häufigkeiten 1–44 |
| 14 Zeiträume | Zahlen und Zeiträume → Zeiträume vergleichen | 10/20/50/100/500/alle nebeneinander; tatsächliche Fenstergrößen |
| 15 Ranglisten | Zahlen und Zeiträume → Ranglisten | Alle zehn vorgeschlagenen Ranglisten, Gleichstände mit gemeinsamem Rang |
| 16 Diagramme | Diagramme | Alle acht Diagrammarten, Zeitfenster, Zahlenauswahl, exakte Werte per Maus |
| 17 Programm-Bereiche | Statistik-Untermenüs und Übersicht | Gruppierte normale Menüs ohne Icons |
| 18 Statistischer Hinweis | Ansichten und HTML-Hilfe | Deskriptive Auswertung, keine zuverlässige Vorhersage; keine „fälligen“ Zahlen |

## Berechnungsregeln

- Datenbasis: importierte Lotto-Hauptzahlen, aufsteigend sortiert; Zusatzzahl ausschließlich separat. Keine Beispieldaten aus dem Konzept in die Datenbank übernehmen.
- Reihenfolge: Datum und Datenbank-ID. Mehrere Ziehungen eines Tages bleiben getrennt; eine tatsächliche Uhrzeitreihenfolge ist damit nicht belegt.
- N ist die tatsächlich ausgewertete Anzahl Ziehungen. Häufigkeitsanteil einer Zahl oder Kombination: `100 × Treffer/N`. Bereichs-/Endziffernanteile verwenden `6 × N`, Abstandsanteile `5 × N`.
- Erwartung je Zahl: `E = N × 6/45`; `σ = sqrt(N × 6/45 × 39/45)`; `z = (Treffer−E)/σ`. Relative Abweichung: `100 × (Treffer−E)/E`. Für N=0 sind z und relative Abweichung nicht bestimmbar. Dies setzt unabhängige reguläre Ziehungen voraus und ist kein Signifikanztest für alle 45 Zahlen.
- Trefferabstand zählt Ziehungsschritte; unmittelbar aufeinanderfolgende Treffer haben Abstand 1. Abgeschlossene Pause: Abstand minus 1. Nur vollständig beobachtete Intervalle im Fenster gehen in diese Kennzahlen ein.
- Aktuelle Pause: Ziehungen nach dem letzten Treffer im Fenster. Bei nie beobachteter Zahl ist die Fenstergröße eine Untergrenze (`≥N`). Bei Kombinationen ohne Treffer sind Datum/Pause nicht bestimmbar (`—`).
- Wiederholungen vergleichen mit dem vorherigen gespeicherten Datensatz, einschließlich des Vorgängers vor dem Fenster. Ohne Vorgänger kein Vergleich; Prozentanteile verwenden die Zahl gültiger Vergleiche.
- Nachbarfolgen: Zahlen unterscheiden sich um 1. Eine Folge 7–8–9 enthält zwei Nachbarpaare. Folgenlisten zeigen maximale zusammenhängende Gruppen, nicht nochmals alle darin enthaltenen Teilfolgen. Paare-/Dreiertabellen zählen diese Teilgruppen jeweils mit.
- Endzifferngruppen enthalten alle möglichen Untergruppen mit mindestens zwei Mitgliedern. Eine Ziehung kann mehrere Gruppen beitragen; deren Anteile summieren sich deshalb nicht zu 100 %.
- Diagramm-Zeitverläufe beginnen am Start des gewählten Fensters und enthalten einen Punkt je gespeicherter Ziehung. Häufigkeit: kumulativer Anteil; Abweichung: kumulative Treffer minus `i × 6/45`. Die Matrix ist symmetrisch, ihre Diagonale leer.
- Historische Datenlücken werden nicht ergänzt. Pausen zählen gespeicherte Ziehungen; bei Datenlücken kann der tatsächliche Abstand größer sein. Siehe DATA_STATUS.md und Daten → Import-Prüfhinweise.

## Technischer Aufbau

`lotto45/statistics.py` enthält GTK-unabhängige Berechnungen und eine SQLite-Lesetransaktion. Der Join beginnt bei den tatsächlichen Ziehungen; der komplette Tippkatalog wird nicht durchlaufen. Ein gemeinsamer Analysebestand liefert Tabellen und Diagramme. Es gibt keine Schemaänderung und keine zusätzlichen Statistik-Datenbanktabellen.

`lotto45/statistics_ui.py` lädt im Hintergrund und zeigt sortierbare, vollständig paginierte Tabellen (100 Zeilen). Ansichtswechsel oder neue Zeiträume verwerfen alte Ergebnisse. `lotto45/charts.py` zeichnet mit GTK/Cairo, Systemfarben und Systemschrift. Exakte Werte sind per Tooltip sichtbar. `python3-cairo` und `python3-gi-cairo` werden nur für die Diagramme benötigt; fehlende Module werden sichtbar als L001 gemeldet.

Die CLI `--stats` benötigt nur die Standardbibliothek und liefert JSON mit unformatierten Werten; Tabellenüberschriften sind Sprachschlüssel aus `languages/*.json`. Details und Beispiele stehen in README.md und der HTML-Hilfe. `tests/test_statistics.py` prüft bekannte Beispielwerte, Fenstergrenzen, fehlende Werte, alle Kombinationen, Summen, Folgen, Gleichstände, Diagrammdaten und den schreibgeschützten Datenzugriff.

## Joker und Darstellung ab 0.4.0

`lotto45/joker_statistics.py` verwendet eine eigene schreibgeschützte SQLite-Transaktion für Joker. Die sechs Ziffern einschließlich führender Nullen bleiben Text. Ziffernzählung berücksichtigt Wiederholungen innerhalb einer Nummer; der Ziffernanteil verwendet sechs Stellen je Ziehung. Positions- und Endstellenanteile verwenden die ausgewertete Ziehungsanzahl. Letzte Stellen enthalten sämtliche 10/100/1.000 Möglichkeiten; unbekannte letzte Daten und Pausen bleiben fehlend. Vollständige Nummern enthalten nur tatsächlich gezogene Nummern. Der Zeitraumvergleich verwendet stets das komplette geladene Joker-Archiv.

`lotto45/widgets.py` stellt einheitliche löschbare Eingabefelder und Tabellen bereit. Kopf und Zeilen teilen sich horizontale Position und Spaltenbreiten; nur die Zeilen scrollen vertikal. Lotto-Zahlen werden in der Oberfläche zweistellig formatiert, JSON-Werte bleiben numerisch. Formeltexte sind aus Oberfläche und HTML-Hilfen entfernt; die technischen Rechenregeln dieses Dokuments bleiben als Entwicklerreferenz erhalten.

`lotto45/joker_rules.py` enthält belegte Standardbeträge für die Anzeige, zeitlich begrenzt und mit Herkunftslink. Diese ergänzen keine Datenbankquoten. Tests prüfen unter anderem Stellen, führende Nullen, alle Endstellen, Zeitfenster, Leseschutz und die Datumsgrenzen des Gewinnplans.

## Einheitliche Datumsanzeige und Live-Suche (0.4.1)

`date_display.py` formatiert Oberflächendaten in beiden Sprachen als TT.MM.JJJJ. Sortierung und JSON-Daten verwenden weiterhin ISO-Werte. Der Statistik-Zahlenfilter reagiert bereits auf jede Änderung. Tipp- und Datumssuche bündeln Eingaben durch einen 200-ms-Zeitgeber; lesende Hintergrundabfragen erhalten Abbruchsignale. Ergebnisse werden nur übernommen, wenn die betreffende Abfrage weiterhin aktuell ist. Teileingaben in der Datumssuche werden gegen gespeicherte Datumsbestandteile geprüft. Joker verwendet zusammenhängende Teilfolgen an beliebiger Stelle; die erwartete Anzahl von Katalogtreffern wird über Präfixzustände berechnet, sodass überlappende Vorkommen nicht doppelt zählen.


## Konzept-Erweiterungen 1.0.0

Kalender-, Wochentags- und Typfilter werden vor dem letzten-N-Fenster angewendet.
Rollierende Diagramme verwenden höchstens die letzten 20 ausgewählten Ziehungen
pro Punkt. Frequenz = 100*k/n, Z = (k - n*6/45)/sqrt(n*(6/45)*(1-6/45)).
Anfangspunkte haben ein verkürztes Fenster. Summenquantile werden linear zwischen
geordneten Summen interpoliert. Die Chi-Quadrat-Zahl ist deskriptiv ohne p-Wert.

Primzahlen bis 45, Birthday-Anteil <=31, Spiegelpaare mit Summe 46,
Dekaden 1–9/10–19/20–29/30–39/40–45, maximale direkte Folge,
gleiche arithmetische Abstände und gewichtete Paarstärke werden ausgewertet.
Paarstärke ist die Summe aller beobachteten Kantenhäufigkeiten je Zahl;
bei Sechserziehungen exakt fünfmal die Häufigkeit, keine neue Prognosegröße.

Joker-Entropie = -sum(p*log2(p)) über die sechs Ziffern einer Nummer.
Symmetrie zählt gleiche gegenüberliegende Stellen (0–3); Palindrom entspricht 3.
Übergänge zählen die fünf geordneten Nachbarpaare. Gleiche Nachbarn sind
von maximaler Häufigkeit einer Ziffer unabhängig. Wochentage sind 0=Montag
bis 6=Sonntag und zeigen absolute Ziffernhäufigkeiten; unterschiedliche
Stichprobengrößen erklären unterschiedliche Balkenhöhen.

Generatorgewichte: (historische Häufigkeit+1)^Stärke, Stärke -5 bis +5.
Lotto zieht gewichtet ohne Zurücklegen, Joker je Stelle unabhängig. Paar- und
Endstellenpräferenzen verwenden begrenzte Akzeptanzgewichte. Ungewöhnlich heißt
Summe <80 oder >=190, ausschließlich gerade/ungerade oder eine Folge >=4.
Kein Gewicht und kein Filter erhöht die mathematische Gewinnchance.
