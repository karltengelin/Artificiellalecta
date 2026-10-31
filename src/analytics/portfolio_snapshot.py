"""Beståndsöversikt och premieflöden som aggregat – ren beräkning utan databas (A2, B-042).

Tjänstelagret (`services/operations/product_report_data.py`) läser raderna och lämnar hit
bara det som behövs för att räkna och dölja. Celler med 1–9 försäkringar döljs, och i en
grupp med känd total döljs fler celler tills de dolda tillsammans omfattar minst MIN_CELL –
annars kunde en dold cell räknas fram ur totalen (harness.md §5.1, samma regel som
`analytics.parameter_impact`).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date

from analytics.parameter_impact import COMPLEMENTARY, MIN_CELL, PRIMARY

__all__ = ["COMPLEMENTARY", "MIN_CELL", "PRIMARY", "birth_year", "cohort_of", "month_starts", "suppress_counts",
           "suppress_sets"]


def suppress_sets(cells: Mapping[date, set]) -> dict[date, str]:
    """Som `suppress_counts`, men för celler där samma individ kan finnas i flera (t.ex. månader).

    De dolda cellerna ska tillsammans omfatta minst MIN_CELL olika individer.
    """
    hidden = {key: PRIMARY for key, ids in cells.items() if 0 < len(ids) < MIN_CELL}
    union = set().union(*(cells[key] for key in hidden)) if hidden else set()
    candidates = sorted((len(ids), key) for key, ids in cells.items() if ids and key not in hidden)
    while hidden and len(union) < MIN_CELL and candidates:
        _, key = candidates.pop(0)
        hidden[key] = COMPLEMENTARY
        union |= cells[key]
    return hidden


def suppress_counts(cells: Mapping[str, int]) -> dict[str, str]:
    """Dolda celler med skäl för en grupp disjunkta celler vars total visas.

    Noll visas alltid. 1–9 döljs (primärt). Är de dolda tillsammans färre än MIN_CELL döljs
    den minsta synliga cellen med försäkringar, tills villkoret håller.
    """
    hidden = {key: PRIMARY for key, n in cells.items() if 0 < n < MIN_CELL}
    total = sum(cells[key] for key in hidden)
    candidates = sorted((n, key) for key, n in cells.items() if n and key not in hidden)
    while hidden and total < MIN_CELL and candidates:
        n, key = candidates.pop(0)
        hidden[key] = COMPLEMENTARY
        total += n
    return hidden


def birth_date(personal_id_number: str) -> date | None:
    """Födelsedagen ur ett tolvsiffrigt personnummer; None om det inte går att läsa."""
    if len(personal_id_number) != 12 or not personal_id_number.isdigit():
        return None
    year, month, day = int(personal_id_number[:4]), int(personal_id_number[4:6]), int(personal_id_number[6:8])
    try:
        return date(year, month, day - 60 if day > 60 else day)  # samordningsnummer har dag + 60
    except ValueError:
        return None


def birth_year(personal_id_number: str) -> int | None:
    """Födelseåret ur ett tolvsiffrigt personnummer; None om det inte går att läsa."""
    born = birth_date(personal_id_number)
    return born.year if born else None


def cohort_of(year: int | None) -> str:
    """Födelsedecennium som etikett, t.ex. 1960–1969; okänt år blir 'okänt'."""
    if year is None:
        return "okänt"
    start = year // 10 * 10
    return f"{start}–{start + 9}"


def month_starts(year: int, last: date) -> list[date]:
    """Månadsförsta från januari till och med månaden `last` i samma år."""
    return [date(year, m, 1) for m in range(1, last.month + 1)] if last.year == year else [
        date(year, m, 1) for m in range(1, 13)]
