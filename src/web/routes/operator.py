"""OC-1/2: läsbar ledningsöversikt. Inga modell- eller verksamhetsskrivningar."""

from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi import APIRouter, Request

from agents.ecosystem import Ecosystem
from ai import load_config
from management.metrics import DEFINITIONS, observation
from management.telemetry import TEAM_NAMES, read_telemetry
from web.handler import read, render, settings

router = APIRouter()


def months(today: date) -> list[date]:
    index = today.year * 12 + today.month - 1
    return [date((index - i) // 12, (index - i) % 12 + 1, 1) for i in range(12)]


@router.get("/central")
@router.get("/central/team")
@router.get("/central/kostnader")
@router.get("/central/underlag")
def operator_overview(request: Request, month: str = ""):
    config = settings(request)
    today = date.today()
    choices = months(today)
    try:
        selected = date.fromisoformat(month + "-01") if month else choices[0]
        if selected not in choices:
            raise ValueError("Otillåten period")
    except ValueError:
        return render(request, "operator.html", {"operator_page": True, "invalid_month": True}, status_code=422)
    period = (selected, date(selected.year + (selected.month == 12), selected.month % 12 + 1, 1))
    now = datetime.now(UTC)
    metrics = []
    source_failed = False
    try:
        data = read(request, "get_company_metrics", {"month": selected})
        reference = f"service:get_company_metrics:{data.read_at.isoformat()}"
        metrics.extend([
            observation(
                "insured_registered_count", environment_id=config.database, dataset_ref=config.dataset_ref,
                now=data.read_at, as_of_date=data.as_of_date, value=data.insured_count,
                availability="suppressed" if data.insured_suppressed else "available", quality="verified",
                note="Små persongrupper döljs." if data.insured_suppressed else "Alla registrerade statusar vid läsningen. Ingen historisk beståndsserie.",
                evidence_refs=(reference,),
            ),
            observation(
                "premium_paid_recorded_sek", environment_id=config.database, dataset_ref=config.dataset_ref,
                now=data.read_at, period=period, value=data.paid_sek,
                availability="missing" if data.paid_state == "failed" else data.paid_state,
                quality="failed" if data.paid_state == "failed" else "provisional",
                note={"failed": "Underlaget innehåller paid utan giltigt betaldatum. Ingen summa visas.",
                      "suppressed": "Färre än tio personer i underlaget. Beloppet döljs.",
                      "available": "Betalmarkeringar, inte bankavstämt kassainflöde. Rättelser ingår, avgifter exkluderas."}[data.paid_state],
                evidence_refs=(reference,),
            ),
        ])
    except Exception:  # noqa: BLE001 – sanera databasfel, ingen demo-reserv eller exponerad anslutning
        source_failed = True
        for key in ("insured_registered_count", "premium_paid_recorded_sek"):
            metrics.append(observation(
                key, environment_id=config.database, dataset_ref=config.dataset_ref, now=now,
                as_of_date=today if key == "insured_registered_count" else None,
                period=period if key != "insured_registered_count" else None,
                availability="missing", quality="unknown", note="Vald datakälla kunde inte läsas. Ingen annan källa används.",
            ))
    for key in ("capital_market_value_sek", "fta_sek", "consolidation_ratio", "liquidity_coverage"):
        metrics.append(observation(key, environment_id=config.database, dataset_ref=config.dataset_ref,
                                   now=now, as_of_date=today, note=DEFINITIONS[key].source + "."))
    profile_error = False
    try:
        ecosystem = Ecosystem.load()
        configured = {key: ecosystem.agents[team.lead].name for key, team in ecosystem.teams.items()}
        profile_ref = ecosystem.checksum
    except Exception:  # noqa: BLE001 – trasig profil är okänd konfiguration, inte ett planerat team
        configured, profile_ref, profile_error = {}, None, True
    try:
        model_refs = set(load_config().models)
    except Exception:  # noqa: BLE001 – okänd modellkatalog får inga fria modellnamn ur loggen
        model_refs = set()
    telemetry = read_telemetry(config.operator_manifest, environment_id=config.database, dataset_ref=config.dataset_ref,
                               period=period, known_models=model_refs, now=now)
    cost_metrics = [observation(
        key, environment_id=config.database, dataset_ref=config.dataset_ref, now=now, period=period,
        value=value, availability="missing" if value is None else "stale" if telemetry.freshness == "stale" else "available",
        quality="unknown" if value is None else "provisional", data_through=telemetry.last_success_at,
        note="Känd del av synliga försök. Full SDK-/pristäckning saknas." if value is not None else "Källunderlag saknas.",
        evidence_refs=(f"local-telemetry-index:{now.isoformat()}",) if value is not None else (),
    ) for key, value in (("agent_cost_known_usd", telemetry.known), ("agent_unknown_attempts_count", telemetry.unknown))]
    teams = [{"id": key, "name": name, "configured": key in configured,
                  "lead": configured.get(key), "states": telemetry.runs.get(key, {})} for key, name in TEAM_NAMES.items()]
    response = render(request, "operator.html", {
        "operator_page": True, "active_view": request.url.path.rsplit("/", 1)[-1],
        "metrics": metrics, "cost_metrics": cost_metrics, "definitions": DEFINITIONS, "telemetry": telemetry, "teams": teams,
        "months": choices, "selected_month": selected.strftime("%Y-%m"), "period": period,
        "now": now, "source_failed": source_failed, "profile_error": profile_error, "profile_ref": profile_ref,
        "dataset_ref": config.dataset_ref,
    })
    response.headers["Cache-Control"] = "no-store"
    return response
