# Datenbank · Schema 1

`data/lotto.sqlite3` ist eine SQLite-Datei. Jede Verbindung muss `PRAGMA foreign_keys=ON` verwenden. Das Programm aktiviert dies automatisch. Schreibaktionen laufen transaktional; WAL ermöglicht gleichzeitiges Lesen. Ungeordnete Kombinationen werden niemals durch ihre Ziehung ersetzt oder gelöscht.

| Tabelle | Inhalt / Eindeutigkeit |
|---|---|
| lotto_tipps | 8.145.060 Kombinationen mit sechs aufsteigend sortierten Zahlen; UNIQUE(n1,…,n6); stabile lexikografische ID |
| joker_tipps | 1.000.000 Nummern als TEXT, exakt sechs ASCII-Ziffern, inklusive `000000` |
| lotto_ziehungen | Datum, Ziehungskennung, Tipp-Fremdschlüssel, Zusatzzahl, zusätzliche JSON-Metadaten |
| joker_ziehungen | Datum, Ziehungskennung, Joker-Fremdschlüssel und zusätzliche JSON-Metadaten |
| lotto_ziehungszahlen | Ursprüngliche Position 1–6; nur verlässliche Reihenfolgen werden strukturiert übernommen |
| gewinnklassen | Spiel, Regelwerk, Klasse; Platz für belegte Gültigkeitsgrenzen |
| lotto_quoten / joker_quoten | Gewinner, Originalwährung, Betrag in ganzen Hundertsteln, Bedeutung, Status und originale Quotenfelder |
| import_quellen | Originaldatei als BLOB, SHA-256, Herkunft und Importzeit |
| lotto_quellen / joker_quellen | Beziehungen zwischen Ziehungen und allen importierten Quellen einschließlich Zeilennummer |
| import_fehler | Unlesbare oder widersprüchliche Angaben mit Originalinhalt |
| aenderungen | Vorher-/Nachher-Abbild jeder Änderung mit Quelle und UTC-Zeit |
| metadata | Schemaversion und Abschlussmarken der Katalogerzeugung |

Eine Kombination darf in vielen Ziehungen auftreten. Nur `(datum, kennung)` ist je Spiel eindeutig. Die offiziellen Jahresarchive verwenden `haupt`, da sie pro Kalendertag nur eine Ziehung ausweisen. Weitere oder Sonderziehungen am selben Datum benötigen eine eigene stabile `kennung`. Unterschiedliche Kombinationen desselben Datums werden ohne Kennung nicht stillschweigend als neue Ziehungen angelegt.

Gültigkeitsgrenzen der Gewinnklassen bleiben NULL, solange kein Regelwerk sie ausdrücklich belegt. Fünf- und Acht-Rang-Systeme von Lotto sind getrennt. Die Joker-Regelwerkskennung `6_rang_pdf` wird für die gleich aufgebauten offiziellen CSV-/PDF-Archive gemeinsam genutzt.

`betrag_hundertstel=12345` bedeutet 123,45 ATS oder EUR; keine Gleitkommazahl und keine automatische Währungsumrechnung. `betrag_art=jackpot` bedeutet ausgeschriebener Jackpot-Pool, `je_gewinn` Betrag je Gewinner, `unbekannt` keine belegte Zuordnung. Fehlende Werte bleiben NULL. Die Joker-Jahresarchive liefern für Rang 2–6 nur Gewinnerzahlen; die fehlenden Beträge bleiben NULL. Eine vollständig gezogene Kombination wird durch unveränderte Lotto-Tipps referenziert, nie dupliziert.

## JSON-Import

Eine UTF-8-Datei enthält eine Liste von Objekten. Beispiel:

```json
[
  {
    "spiel": "lotto",
    "datum": "2026-01-01",
    "kennung": "beispiel-sonderziehung",
    "zahlen": [1, 2, 3, 4, 5, 6],
    "zusatzzahl": 7,
    "reihenfolge": [6, 1, 3, 2, 5, 4],
    "quoten": [{
      "klasse": "6er",
      "regelwerk": "8_rang",
      "gewinner": 1,
      "waehrung": "EUR",
      "betrag_hundertstel": 120000000,
      "betrag_art": "je_gewinn",
      "status": ""
    }],
    "hinweis": "Reines Formatbeispiel, keine echte Ziehung"
  },
  {
    "spiel": "joker",
    "datum": "2026-01-01",
    "kennung": "beispiel-sonderziehung",
    "nummer": "001234",
    "quoten": []
  }
]
```

Nicht als echte Ziehung importieren: Das obige Beispiel dient nur der Formatbeschreibung.
Unbekannte Objektfelder werden zusätzlich als JSON-Metadaten gespeichert; sämtliche Quelldaten bleiben ohnehin bytegenau erhalten. Für abweichende Daten sind die Quelle und eine manuelle Entscheidung erforderlich. Neue Korrektur-JSON-Datei mit `--allow-corrections` importieren. Vorherige Zahlen, Reihenfolgen und Quoten sind im Änderungsprotokoll wiederherstellbar. Fehlende Werte eines Ergänzungsimports bedeuten nicht „löschen“.

## Beispielabfragen

```sql
-- Alle wiederholt gezogenen Lotto-Kombinationen
SELECT tipp_id, count(*) FROM lotto_ziehungen
GROUP BY tipp_id HAVING count(*) > 1;

-- Lotto-Zahlen, Datum und Zusatzzahl
SELECT d.datum, t.n1,t.n2,t.n3,t.n4,t.n5,t.n6,d.zusatzzahl
FROM lotto_ziehungen d JOIN lotto_tipps t ON t.id=d.tipp_id
ORDER BY d.datum;

-- Originalquelle exportieren: mit Python sqlite3 als Bytes schreiben.
SELECT id, uri, sha256, length(original) FROM import_quellen;
```

Die vollständige Katalogprüfung nutzt die Anzahl sowie UNIQUE-/CHECK-Bedingungen. `--check` prüft SQLite-Integrität und Fremdschlüssel. Bei SQL-Änderungen außerhalb des Programms zusätzlich die fachlichen Bedingungen beachten: Zusatzzahl außerhalb der sechs Hauptzahlen, Reihenfolge identisch zur Zahlenmenge und gültiges ISO-Datum. Für reguläre Änderungen den geprüften Importweg verwenden.


## Erweiterung in Version 1.0.0

`metadata.extension_version=1` ergänzt das unveränderte Archivschema 1.
Vor der ersten Erweiterung eines befüllten Archivs wird eine konsistente
SQLite-Sicherung unter `data/backups/` erzeugt.

- `stat_profile`: (game,name) eindeutig; vollständige JSON-Regeln und Zeitstempel.
- `tip_batch`: Spiel, Erstellungszeit UTC, Anzahl, Profilschnappschuss, RNG-Modus, Test-Seed.
- `batch_tip`: Reihenfolge und Textwert; UNIQUE(batch_id,value), Fremdschlüssel zur Serie.
- `data_source`: Quellendefinition, Status, letzter Check/Erfolg.
- `source_cache`: URL, ETag, Last-Modified und SHA-256 bereits importierter Bytes.
- `import_run`: Zeitpunkt, URL, SHA-256, Status, gelesene/geänderte/abgewiesene Zeilen und Bericht.

`selected_profile_lotto` / `selected_profile_joker` in metadata wählen das
CLI-Profil. Die Batchwerte sind eigenständig und hängen nicht vom Fortbestand
eines Profils ab. Lotto-/Joker-Quoten und alle früheren Rohdaten bleiben erhalten.
