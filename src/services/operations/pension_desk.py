"""Läsningarna för handläggarsidan *Pensioner och utbetalningar* (paket B steg 8, B-056, Karls val Z4).

Tre operationer, alla `HUMAN_ONLY`; agenter nekas även i operationen (PB12, Z14):

- `get_pension_status` visar hela uttagsflödets läge utan personuppgifter: vilka av steg 1–7 som är införda
  med saknade tabeller, senast stängda och nästa öppna månad, delar per läge, öppna ärenden per typ och
  saldona för skulden, bolagskontot, skatteskulden och arvsvinstpoolen. Den fallerar aldrig på saknade
  tabeller – den svarar vad som saknas (Z9).
- `list_payout_parts` listar uttagsdelarna med försäkringsnummer, ägarens namn, 66-årsmånad, läge, senaste
  plan och öppna ärenden, med urval och sidor. Inget personnummer (Z6).
- `get_payout_person` visar en persons försäkringar och delar, skattestatus och utbetalningskonton i alla
  versioner med maskerade kontonummer.

Logiken ligger i `services.pension_desk`; modulen ändrar ingen av steg 1–7:s operationer.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from models.payout_part import PAYOUT_PART_STATES
from services import pension_desk as desk
from services.contract import OperationContext, OperationKind, operation
from services.errors import AccessDeniedError, NotFoundError
from services.operations import common
from services.operations.actuarial_analysis import JsonResult
from services.premium_month_inputs import Strict

RULES = ["PR-ITP1-025", "PR-ITP1-026", "UTTAG_GEMENSAMT"]
PartState = Literal[PAYOUT_PART_STATES]  # type: ignore[valid-type]
PensionCaseType = Literal[desk.PENSION_CASE_TYPES]  # type: ignore[valid-type]


def _no_agent(ctx: OperationContext, name: str) -> None:
    if ctx.actor.is_agent:
        raise AccessDeniedError("Pensionerna och utbetalningarna läses av människa eller betrodd systemkod (PB12, Z4)",
                                operation=name, actor_id=ctx.actor.id)


class StatusInput(Strict):
    pass


class PartsInput(Strict):
    state: PartState | None = Field(default=None, description="Delens nuvarande läge")
    turning_66: bool = Field(default=False, description="Bara ej startade delar vars ägare fyller 66 inom 12 månader")
    case_type: PensionCaseType | None = Field(default=None, description="Bara delar vars ägare har ett öppet ärende "
                                                                         "av typen")
    policy_number: str | None = Field(default=None, min_length=1, max_length=20, description="En viss försäkring")
    query: str | None = Field(default=None, min_length=2, max_length=60,
                              description="Sökning på försäkringsnummer eller namn – aldrig personnummer")
    limit: int = Field(default=100, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class PersonInput(Strict):
    policy_number: str | None = Field(default=None, min_length=1, max_length=20,
                                      description="En försäkring som personen äger")
    personal_id_number: str | None = Field(default=None, pattern=r"^\d{12}$", description="Den försäkrade, 12 siffror")

    @model_validator(mode="after")
    def _one(self):
        if (self.policy_number is None) == (self.personal_id_number is None):
            raise ValueError("Ange antingen försäkringsnummer eller personnummer")
        return self


@operation(
    name="get_pension_status",
    description="Visar uttagsflödets läge utan personuppgifter: vilka av paket B:s steg 1–7 som är införda i vald "
                "databas och vilka tabeller som saknas, senast stängda och nästa öppna månad, uttagsdelar per "
                "läge, öppna ärenden per typ och saldona för skulden, bolagskontot, skatteskulden och "
                "arvsvinstpoolen.",
    kind=OperationKind.READ,
    rules=RULES,
    pii=False,
)
def get_pension_status(ctx: OperationContext, data: StatusInput) -> JsonResult:
    _no_agent(ctx, "get_pension_status")
    return JsonResult(payload=desk.status(ctx.require_session(), common.today()))


@operation(
    name="list_payout_parts",
    description="Listar uttagsdelarna med försäkringsnummer, ägarens namn, 66-årsmånad, nuvarande läge, senaste "
                "planversion och ägarens öppna pensionsärenden. Urval på läge, 66 inom tolv månader, ärendetyp, "
                "försäkring eller namn. Inget personnummer.",
    kind=OperationKind.READ,
    rules=RULES,
    pii=True,
)
def list_payout_parts(ctx: OperationContext, data: PartsInput) -> JsonResult:
    _no_agent(ctx, "list_payout_parts")
    session = ctx.require_session()
    if not desk.introduced(desk.steps(session), 1):
        return JsonResult(payload={"parts": [], "count": 0, "total": 0, "offset": data.offset, "limit": data.limit,
                                   "plans_introduced": False, "introduced": False})
    result = desk.list_parts(session, common.today(), state=data.state, turning_66=data.turning_66,
                             case_type=data.case_type, policy_number=data.policy_number, query=data.query,
                             limit=data.limit, offset=data.offset)
    return JsonResult(payload={**result, "introduced": True})


@operation(
    name="get_payout_person",
    description="Visar en persons försäkringar och uttagsdelar, skattestatus per år och utbetalningskonton i alla "
                "versioner. Kontonumren visas maskerade.",
    kind=OperationKind.READ,
    rules=RULES,
    pii=True,
)
def get_payout_person(ctx: OperationContext, data: PersonInput) -> JsonResult:
    _no_agent(ctx, "get_payout_person")
    try:
        return JsonResult(payload=desk.person_view(ctx.require_session(), policy_number=data.policy_number,
                                                   personal_id_number=data.personal_id_number))
    except desk.DeskError as exc:
        raise NotFoundError(str(exc)) from exc
