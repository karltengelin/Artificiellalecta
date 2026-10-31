"""Läsbar presentation av antaganden; inga aktuariella beräkningar eller egna värden."""

from decimal import Decimal

from web.presenters import number

LABELS = {
    "net_interest_rate": "Nettoränta", "mortality": "Dödlighet", "table": "Dödlighetstabell",
    "male_weight": "Andel män i unisexvikten", "improvement_per_year": "Dödlighetsförbättring per år",
    "improvement_base_year": "Basår för förbättring", "risk_factor": "Faktor på dödsrisken",
    "tail_from_age": "Svans från ålder", "tail_intensity_growth": "Ökning av dödsintensitet i svansen",
    "tail_q_cap": "Övre gräns för dödssannolikhet", "curve_family": "Kurvfamilj",
    "tax": "Avkastningsskatt", "rate": "Skattesats", "slr_floor": "Golv för statslåneränta",
    "method": "Metod", "expenses": "Driftskostnader", "deferred_sek_per_year": "Före utbetalning, kronor per år",
    "payout_sek_per_year": "Under utbetalning, kronor per år", "indexation": "Årlig indexering",
    "reference_plan": "Referensplan", "option_adjustment": "Optionsjustering", "synthetic": "Syntetiskt underlag",
    "construction": "Konstruktion", "interpolation": "Interpolation", "extrapolation": "Extrapolation",
    "description": "Beskrivning", "definition": "Definition", "points": "Diskonteringskurva",
    "months": "Deklarerad månadsavkastning",
}
PERCENT = {"net_interest_rate", "male_weight", "improvement_per_year", "tail_intensity_growth", "tail_q_cap",
           "rate", "slr_floor", "indexation"}
VALUES = {"discount_reduction": "Diskontering med ränta efter skatt",
          "lifelong_from_66": "Livsvarigt från 66 år", "none": "Ingen", "linear": "Linjär",
          "flat": "Konstant efter sista löptiden",
          "after_direct_costs_before_fee_and_tax": "Efter direkta placeringskostnader, före avgift och skatt"}


def assumption_groups(data, heading="Antaganden"):
    groups, rows = [], []
    for key, value in data.items():
        title = LABELS.get(key, key.replace("_", " "))
        if isinstance(value, dict):
            groups.extend(assumption_groups(value, title))
        elif isinstance(value, list):
            if key == "points":
                groups.append({"title": title, "columns": ["Löptid, år", "Spotränta"],
                               "cells": [(p["term_years"], number(Decimal(p["spot_rate"]) * 100) + " %") for p in value]})
            elif key == "months":
                groups.append({"title": title, "columns": ["Månad", "Avkastning"],
                               "cells": [(p["month"][:7], number(Decimal(p["rate"]) * 100) + " %") for p in value]})
        else:
            if isinstance(value, bool):
                shown = "Ja" if value else "Nej"
            elif key in PERCENT:
                shown = number(Decimal(str(value)) * 100) + " %"
            else:
                shown = VALUES.get(str(value), str(value))
            rows.append((title, shown))
    return ([{"title": heading, "rows": rows}] if rows else []) + groups
