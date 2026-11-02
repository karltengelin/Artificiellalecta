"""Reproducerbar erfarenhetsanalys. Inga databaser, modellanrop eller syntetiska utfall.

Dödlighet använder central exponering i personår och intensiteten -log(1-q).
Poissonmodellen gäller antal dödsfall. Garwood-intervall är exakta för denna
modell, inte för modellfel eller osäker exponering. Kandidater är forsknings-
och scenarioresultat; de ändrar aldrig en antagen grund.
"""

from __future__ import annotations

import math
from dataclasses import replace

from skills.calculation.actuarial_annuity import MortalityBasis, annual_q


def poisson_interval(deaths: int) -> tuple[float, float]:
    from scipy.stats import chi2

    return (float(chi2.ppf(.025, 2*deaths))/2 if deaths else 0.0,
            float(chi2.ppf(.975, 2*(deaths+1)))/2)


def expected(row: dict, basis: MortalityBasis) -> float:
    q = annual_q(basis, row["age"], row["year"], row["year"] - row["age"])
    if not 0 < q < 1:
        raise ValueError("Dödsrisken ska ligga strikt mellan noll och ett")
    return row["exposure_years"] * -math.log1p(-q)


def mortality_experience(rows: list[dict], basis: MortalityBasis, prior_expected_deaths: float = 20) -> dict:
    observed = sum(r["deaths"] for r in rows)
    e = sum(expected(r, basis) for r in rows)
    if e <= 0:
        raise ValueError("Exponeringen ger inget förväntat dödsfall")
    low, high = poisson_interval(observed)
    by_year = []
    for year in sorted({r["year"] for r in rows}):
        subset = [r for r in rows if r["year"] == year]
        d, exp = sum(r["deaths"] for r in subset), sum(expected(r, basis) for r in subset)
        # Även härledning från kvot/konfidensintervall skyddas när dödsfallen är få.
        hidden = 0 < d < 10 or any(r["lives"] < 10 for r in subset)
        by_year.append({"year": year, "observed": None if hidden else d,
                        "expected": None if hidden else round(exp, 6),
                        "ae_ratio": None if hidden else round(d / exp, 6), "suppressed": hidden})
    hidden = 0 < observed < 10 or any(r["lives"] < 10 for r in rows)
    if any(r["suppressed"] for r in by_year):
        # Ingen restcell får kunna härledas som total minus synliga år.
        by_year = [{"year": r["year"], "observed": None, "expected": None,
                    "ae_ratio": None, "suppressed": True} for r in by_year]
    return {
        "method": "Poisson med central exponering; exakt Garwood-intervall 95 % för A/E",
        "observed": None if hidden else observed, "expected": None if hidden else round(e, 6),
        "ae_ratio": None if hidden else observed / e,
        "ae_lower_95": None if hidden else low / e, "ae_upper_95": None if hidden else high / e,
        "credibility_intensity_factor": None if hidden else (observed + prior_expected_deaths) / (e + prior_expected_deaths),
        "prior_expected_deaths": prior_expected_deaths, "suppressed": hidden, "rows": by_year,
        "limitations": ["Priorens vikt är ett analysval, inte en antagen grund.",
                         "Osäkerheten är villkorad på given exponering och referensmodell.",
                         "Summerade personår är inte ett antal unika personer.",
                         "Statistisk avvikelse kräver även kontroll av data, urval och ekonomisk betydelse."],
    }


def _deviance(observed: int, mean: float) -> float:
    return 2 * (mean - observed + (observed * math.log(observed / mean) if observed else 0))


def fit_mortality(rows: list[dict], basis: MortalityBasis) -> dict:
    years = sorted({r["year"] for r in rows})
    if len(years) < 4:
        return {"status": "insufficient_data", "rows": [],
                "limitations": ["Minst fyra kalenderår krävs: tre för skattning och sista året för tidsvalidering."]}
    train = [r for r in rows if r["year"] < years[-1]]
    test = [r for r in rows if r["year"] == years[-1]]
    d_train, d_test = sum(r["deaths"] for r in train), sum(r["deaths"] for r in test)
    if d_train < 10 or d_test < 10 or any(r["lives"] < 10 for r in rows):
        return {"status": "insufficient_data", "rows": [],
                "limitations": ["För få observerade dödsfall eller för små celler för publicerad modelljämförelse."]}
    fits = []
    for improvement in [i / 1000 for i in range(0, 41, 2)]:
        candidate = replace(basis, improvement_per_year=improvement)
        exp_train = [expected(r, candidate) for r in train]
        factor = d_train / sum(exp_train)
        score = sum(_deviance(r["deaths"], e * factor) for r, e in zip(train, exp_train))
        exp_test = sum(expected(r, candidate) for r in test) * factor
        fits.append({"improvement": improvement, "intensity_factor": factor,
                     "training_deviance": score, "validation_deviance": _deviance(d_test, exp_test),
                     "validation_expected": exp_test})
    best = min(fits, key=lambda x: x["training_deviance"])
    baseline_e = sum(expected(r, basis) for r in test)
    return {"status": "research_candidate", "training_through": years[-2], "validation_year": years[-1],
            "candidate": best, "baseline_validation_deviance": _deviance(d_test, baseline_e),
            "rows": fits, "limitations": [
                "Extern tabell är förankring; nivån skattas som en multiplikator på dödsintensiteten.",
                "Förbättring väljs på träningsperioden; sista året används bara för validering.",
                "Begränsad modellfamilj och ett valideringsår; ingen validering av livslång extrapolation.",
                "Kandidaten är inte en antagen värderingsgrund. Syntetiskt utfall bevisar inte verklig lämplighet."]}


def expense_experience(rows: list[dict]) -> dict:
    out = []
    for r in rows:
        hidden = r["lives"] < 10
        out.append({"year": r["year"], "state": r["state"],
                    "actual_sek": None if hidden else r["actual_sek"],
                    "expected_sek": None if hidden else r["expected_sek"],
                    "difference_sek": None if hidden else r["actual_sek"] - r["expected_sek"],
                    "cost_per_policy_year": None if hidden else r["actual_sek"] / r["exposure_years"],
                    "suppressed": hidden})
    return {"rows": out, "limitations": ["Förväntad kostnad kommer från importens dokumenterade budgetgrund.",
            "Kostnadsfördelningens varians saknas; inget konfidensintervall beräknas.",
            "Engångskostnader, inflation och kostnadsallokering behöver prövas separat."]}


def behavior_experience(rows: list[dict]) -> dict:
    out = []
    for r in rows:
        n, events = r["eligible"], r["events"]
        p, z = events / n, 1.959963984540054
        centre = (p + z*z/(2*n))/(1+z*z/n)
        half = z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/(1+z*z/n)
        hidden = n < 10 or 0 < events < 10 or 0 < n - events < 10
        out.append({"year": r["year"], "event": r["event"], "observed_rate": None if hidden else p,
                    "expected_rate": None if hidden else r["expected_rate"],
                    "lower_95": None if hidden else max(0, centre-half),
                    "upper_95": None if hidden else min(1, centre+half), "suppressed": hidden})
    return {"rows": out, "limitations": ["Wilson-intervall 95 %, binomial modell för definierad valmöjlighet.",
            "Beroende mellan observationer och förändrad beståndssammansättning ingår inte i intervallet."]}
