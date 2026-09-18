# Drittkomponenten

Der eigene Quellcode von Josef Lehner steht unter GPL-3.0-only (LICENSE).
Drittbibliotheken behalten ihre eigenen Urheber- und Lizenzhinweise.

- Python: Python Software Foundation, PSF License.
- GTK / PyGObject: GTK-/PyGObject-Teams, LGPL.
- Cairo / Pycairo: Cairo-/Pycairo-Teams, jeweilige LGPL/MPL-Lizenzen.
- Poppler / pdftotext: Poppler-Entwickler, GPL; externes Systemprogramm.
- Matplotlib 3.11.2: Matplotlib Development Team, Matplotlib License.
- NumPy, ContourPy, Cycler, Pillow, fontTools, kiwisolver, packaging,
  pyparsing, python-dateutil und six: jeweilige Autoren und Lizenzen in
  den unveränderten `vendor/*.dist-info/METADATA` und Lizenzverzeichnissen.

Das kompilierte Paket bündelt die in requirements.txt verlangte Matplotlib-
Umgebung einschließlich Metadaten, Copyright- und Lizenzdateien. GTK, Cairo
und Poppler werden vom System verwendet. Die vollständigen Versionsangaben
sind in den mitgelieferten Paketmetadaten erhalten.

Die offiziellen Lotto-/Joker-Quelldaten sind kein Bestandteil der öffentlichen
Programmpakete. Ressourcen, Herkunft und Hinweise zu vorhandenen Grafiken
stehen bei den jeweiligen Dateien unter resources/.

Das win2day-Webseitenlogo ist eine fremde Markengrafik, siehe
`resources/site-logos/README.md`; es ist nicht als eigener GPL-Code lizenziert.

Für das GitHub-Mark gelten die Marken- und Grafikrechte von GitHub;
Herkunft siehe `resources/site-logos/README.md`.
