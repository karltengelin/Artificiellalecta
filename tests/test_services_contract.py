"""Tester för operationskontraktet (tjänstelager.md §3)."""

import pytest
from pydantic import BaseModel

from services import OperationContext, OperationKind, OperationRegistry, ServiceConfigError, operation
from services.contract import AgentAccess, strictest


class In(BaseModel):
    x: int


class Out(BaseModel):
    y: int


def test_dekoratorn_laser_in_och_utdatamodell():
    registry = OperationRegistry()

    @operation(name="double", description="Dubblar", kind="compute", rules=["PR-X-1"], registry=registry)
    def double(ctx: OperationContext, data: In) -> Out:
        return Out(y=data.x * 2)

    op = registry.get("double")
    assert (op.input_model, op.output_model, op.kind, op.rules) == (In, Out, OperationKind.COMPUTE, ("PR-X-1",))


def test_ogiltigt_namn_avvisas():
    with pytest.raises(ServiceConfigError, match="Ogiltigt operationsnamn"):
        operation(name="Beräkna-premie", description="x", kind="compute")


def test_indata_maste_vara_pydantic():
    registry = OperationRegistry()
    with pytest.raises(ServiceConfigError, match="Pydantic"):
        @operation(name="bad", description="x", kind="read", registry=registry)
        def bad(ctx: OperationContext, data: dict) -> Out:
            return Out(y=1)


def test_dubbla_namn_avvisas():
    registry = OperationRegistry()

    @operation(name="same", description="x", kind="read", registry=registry)
    def first(ctx: OperationContext, data: In) -> Out:
        return Out(y=1)

    with pytest.raises(ServiceConfigError, match="redan registrerad"):
        @operation(name="same", description="x", kind="read", registry=registry)
        def second(ctx: OperationContext, data: In) -> Out:
            return Out(y=2)


def test_strangaste_niva_vinner():
    assert strictest(AgentAccess.AGENT, AgentAccess.APPROVAL) == AgentAccess.APPROVAL
    assert strictest(AgentAccess.HUMAN_ONLY, AgentAccess.AGENT) == AgentAccess.HUMAN_ONLY
