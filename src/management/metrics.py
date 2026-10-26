"""Gemensamma måttdefinitioner och daterade läsobservationer, OC-0 §3."""

from __future__ import annotations

import hashlib
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator


class MetricDefinition(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1] = 1
    metric_id: str
    definition_version: str = "1.0"
    name: str
    definition: str
    unit: str
    population: str
    time_basis: Literal["as_of", "period"]
    source: str
    owner_team: str
    review_ref: str = "B-038 / OC-0 §3.3"
    dimensions: tuple[str, ...] = ()
    additivity: str = "Får inte summeras över miljöer eller överlappande populationer."
    freshness_seconds: int = 86400
    controls: str
    privacy: str = "Inga personuppgifter. Personbaserade celler med 1–9 individer undertrycks."


class MetricObservation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1] = 1
    observation_id: str
    metric_id: str
    definition_version: str = "1.0"
    environment_id: str
    dataset_ref: str
    kind: Literal["actual"] = "actual"
    availability: Literal["available", "missing", "not_calculated", "suppressed", "stale"]
    quality: Literal["verified", "provisional", "failed", "unknown"]
    value: Decimal | int | None
    computed_at: datetime
    data_through: datetime | None
    as_of_date: date | None = None
    period_from: date | None = None
    period_to: date | None = None
    evidence_refs: tuple[str, ...] = ()
    note: str

    @model_validator(mode="after")
    def consistent(self):
        if self.availability not in {"available", "stale"} and self.value is not None:
            raise ValueError("Ett saknat eller undertryckt mått får inget talvärde")
        if self.computed_at.tzinfo is None or (self.data_through is not None and self.data_through.tzinfo is None):
            raise ValueError("Loggtider kräver tidszon")
        if self.as_of_date is not None:
            if self.period_from is not None or self.period_to is not None:
                raise ValueError("Datumvärde och periodflöde hålls isär")
        elif self.period_from is None or self.period_to is None or self.period_from >= self.period_to:
            raise ValueError("Ett periodmått kräver ett halvöppet datumintervall")
        return self


DEFINITIONS = {
    d.metric_id: d for d in (
        MetricDefinition(
            metric_id="insured_registered_count", name="Registrerade försäkrade", unit="personer",
            definition="Antal unika registrerade försäkrade, alla statusar, vid läsningen.",
            population="Samtliga insured_persons i vald datakälla.", time_basis="as_of",
            source="Försäkringstjänsten · insured_persons", owner_team="forsakring",
            controls="En SQL-ögonblicksbild, unik primärnyckel, minsta cellstorlek 10. Ingen historik bakdateras.",
        ),
        MetricDefinition(
            metric_id="premium_paid_recorded_sek", name="Registrerat betalda premier", unit="SEK",
            definition="Summa signerade premium- och adjustment-rader med status paid efter betaldatum. Avgifter exkluderas.",
            population="Betalmarkerade premier i vald kalendermånad, inte bankavstämt kassainflöde.",
            time_basis="period", source="Försäkringstjänsten · premium_transactions", owner_team="forsakring",
            controls="En SQL-ögonblicksbild, paid kräver betaldatum, inga framtida betalmarkeringar, minst 10 berörda personer.",
        ),
        MetricDefinition(
            metric_id="agent_cost_known_usd", name="Känd agentkostnad", unit="USD",
            definition="Summa känd kostnad för unika synliga anropsförsök i vald UTC-månad, inklusive fel och reserv.",
            population="Deklarerade loggkällor i vald miljö och dataset. Oallokerade poster exkluderas.",
            time_basis="period", source="Lokalt telemetry-index · AI-anropslogg", owner_team="utveckling",
            freshness_seconds=900, privacy="Endast tekniska metadata. Ingen rå prompt- eller uppdragstext.",
            controls="Idempotent import och källkonfliktkontroll. Alltid partiell täckning; SDK-omförsök och prisversion kan saknas.",
        ),
        MetricDefinition(
            metric_id="agent_unknown_attempts_count", name="Försök med okänd kostnad", unit="försök",
            definition="Antal unika synliga försök med nullkostnad. Dolda SDK-försök går inte att räkna.",
            population="Samma deklarerade källor och period som agent_cost_known_usd.",
            time_basis="period", source="Lokalt telemetry-index · AI-anropslogg", owner_team="utveckling",
            freshness_seconds=900, privacy="Endast tekniska metadata.",
            controls="Nullkostnad är aldrig gratis. Saknat försöksunderlag ger null, inte noll.",
        ),
        *(
            MetricDefinition(
                metric_id=key, name=name, unit=unit, definition=definition,
                population="Bolagets hela avgränsade ITP1-bestånd.", time_basis="as_of",
                source=source, owner_team=owner, controls="Verifierad domänmotor och grundversion krävs.",
            )
            for key, name, unit, definition, source, owner in (
                ("capital_market_value_sek", "Förvaltat kapital", "SEK", "Marknadsvärde enligt verifierad kapitalvärdering.", "Kapitalvärdering saknas", "kapital"),
                ("fta_sek", "Försäkringstekniska avsättningar", "SEK", "Värderade åtaganden enligt beslutad aktuariell grund.", "Aktuariell motor saknas", "aktuarie"),
                ("consolidation_ratio", "Kollektiv konsolidering", "%", "Kräver beslutad fördelningsmodell och jämförbara värderingsunderlag.", "Fördelningsmodell och värdering saknas", "aktuarie"),
                ("liquidity_coverage", "Likviditetstäckning", "kvot", "Kräver likvida tillgångar och framtida betalningar på samma grund.", "Likviditets- och betalningsunderlag saknas", "ekonomi"),
            )
        ),
    )
}


def observation(metric_id: str, *, environment_id: str, dataset_ref: str, now: datetime,
                value=None, availability="not_calculated", quality="unknown", note: str,
                as_of_date: date | None = None, period: tuple[date, date] | None = None,
                evidence_refs: tuple[str, ...] = (), data_through: datetime | None = None) -> MetricObservation:
    result = MetricObservation(
        observation_id="pending", metric_id=metric_id, environment_id=environment_id,
        dataset_ref=dataset_ref, computed_at=now,
        data_through=(data_through or now) if availability in {"available", "suppressed", "stale"} else None, value=value,
        availability=availability, quality=quality, note=note, as_of_date=as_of_date,
        period_from=period[0] if period else None, period_to=period[1] if period else None,
        evidence_refs=evidence_refs,
    )
    fingerprint = hashlib.sha256(result.model_dump_json().encode()).hexdigest()
    return result.model_copy(update={"observation_id": fingerprint})
