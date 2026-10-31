"""Granskad ärendepolicy. Ingen global avstängning av godkännanden."""

from __future__ import annotations

import hashlib
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml
from pydantic import BaseModel, ConfigDict, Field

DEFAULT_POLICY = Path(__file__).with_name("case_policy.yaml")


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class DailySchedule(Strict):
    enabled: bool = False
    timezone: str = "Europe/Stockholm"
    hour: int = Field(default=7, ge=0, le=23)
    minute: int = Field(default=0, ge=0, le=59)


class CaseTypePolicy(Strict):
    review_required: bool = True
    auto_close: bool = True
    max_jobs_per_day: int = Field(default=20, ge=1, le=1000)
    max_daily_cost_usd: float = Field(default=5.0, gt=0, le=1000)
    schedule: DailySchedule = DailySchedule()


class CasePolicy(Strict):
    schema_version: int = Field(default=1, ge=1, le=1)
    policy_id: str = Field(min_length=1)
    case_types: dict[str, CaseTypePolicy]

    @classmethod
    def load(cls, path: Path = DEFAULT_POLICY) -> tuple[CasePolicy, str]:
        raw = path.read_bytes()
        # Samma försiktighet som ecosystem: dubbla nycklar får inte dölja en policy.
        class Loader(yaml.SafeLoader):
            pass

        def mapping(loader, node):
            result = {}
            for key, value in node.value:
                name = loader.construct_object(key)
                if name in result:
                    raise ValueError("Dubbla nycklar i ärendepolicyn")
                result[name] = loader.construct_object(value, deep=True)
            return result

        Loader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)
        policy = cls.model_validate(yaml.load(raw, Loader=Loader))
        for rule in policy.case_types.values():
            ZoneInfo(rule.schedule.timezone)
        if set(policy.case_types) - {"salary_report"}:
            raise ValueError("Ärendetypen har ännu ingen verifierad handläggare")
        return policy, hashlib.sha256(raw).hexdigest()

    def snapshot(self, case_type: str, version: str) -> dict:
        return {"policy_id": self.policy_id, "sha256": version, "case_type": case_type,
                **self.case_types[case_type].model_dump()}
