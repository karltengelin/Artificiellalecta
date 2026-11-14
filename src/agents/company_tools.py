"""Verktygskontrakt för bolagsorkestratörens uppdragsgateway."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from agents.gateways.regulatory import HANDLE_PATTERN

TEAM = "operator_central"
SKILL = "coordinate_company_work"


class CoordinationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["catalog", "status", "order", "review"]
    target_team: str | None = Field(default=None, max_length=40)
    review_kind: Literal["approve_interpretation", "prepare_parameter_activation", "prepare_development"] | None = None
    key: str | None = Field(default=None, pattern=r"^[a-z0-9_-]{1,48}$")
    source: str | None = Field(default=None, pattern=HANDLE_PATTERN)
    basis: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")
    goal: str | None = Field(default=None, max_length=500)


class CoordinationResult(BaseModel):
    data: dict[str, Any]
