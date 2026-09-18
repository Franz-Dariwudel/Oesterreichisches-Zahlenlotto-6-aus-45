"""Standardgewinnplan für die Anzeige; Originalquoten werden nicht verändert.

Quelle: win2day-Spielbedingungen Joker ab 04.07.2025, Abschnitte 8 und 9.
Am 15.09.2026 überprüft. Nur bis zu diesem Datum ergänzen, damit spätere
Regeländerungen nicht unbemerkt mit veralteten Beträgen angezeigt werden.
Sonderdotierungen sind darin nicht enthalten; vorhandene Quoten haben Vorrang.
"""
SOURCE='https://www.win2day.at/fairplay/spielbedingungen/spielbedingungen-elektronische-lotterien/joker-spielbedingungen'
AMOUNTS={'2':1200000,'3':120000,'4':12000,'5':1200,'6':250}


def standard_amount(date,rank):
    return AMOUNTS.get(str(rank)) if '2025-07-04'<=date<='2026-09-15' else None
