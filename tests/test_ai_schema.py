"""Tester för strikta scheman och verktygsdefinitioner."""

import pytest
from pydantic import BaseModel, Field

from ai.schema import schema_name, strict_json_schema
from ai.types import Message, ToolCall, ToolResult, ToolSpec


class Adress(BaseModel):
    gata: str
    ort: str | None = None


class Dokument(BaseModel):
    title: str = Field(description="En egenskap som råkar heta title")
    adress: Adress
    taggar: list[str] = []


def _objects(node):
    """Alla objekt-scheman i ett schema, rekursivt."""
    if isinstance(node, dict):
        if "properties" in node:
            yield node
        for value in node.values():
            yield from _objects(value)
    elif isinstance(node, list):
        for value in node:
            yield from _objects(value)


class TestStriktSchema:
    def test_alla_objekt_ar_slutna_och_har_alla_falt_som_obligatoriska(self):
        schema = strict_json_schema(Dokument)
        objects = list(_objects(schema))
        assert len(objects) == 2  # Dokument + Adress (under $defs)
        for obj in objects:
            assert obj["additionalProperties"] is False
            assert obj["required"] == list(obj["properties"])

    def test_valfritt_falt_blir_nullbart_och_obligatoriskt(self):
        adress = strict_json_schema(Dokument)["$defs"]["Adress"]
        assert "ort" in adress["required"]
        assert {"type": "null"} in adress["properties"]["ort"]["anyOf"]

    def test_titel_och_default_tas_bort_men_inte_egenskaper_med_samma_namn(self):
        schema = strict_json_schema(Dokument)
        assert "title" not in schema  # nyckelordet på modellnivå
        assert "title" in schema["properties"]  # egenskapen finns kvar
        assert "default" not in schema["properties"]["taggar"]

    def test_schemanamn_ar_ascii(self):
        class Bedömning(BaseModel):
            ok: bool

        assert schema_name(Bedömning) == "Bed_mning"


class TestToolSpec:
    def test_from_model_ger_strikt_verktyg(self):
        tool = ToolSpec.from_model("register_document", "Registrerar ett dokument", Dokument)
        assert tool.strict is True
        assert tool.parameters["additionalProperties"] is False

    def test_verktygsnamn_med_svenska_tecken_avvisas(self):
        with pytest.raises(ValueError):
            ToolSpec(name="beräkna_premie", description="x", parameters={"type": "object"})


class TestMeddelanden:
    def test_user_kan_inte_ha_verktygsanrop(self):
        with pytest.raises(ValueError):
            Message(role="user", text="x", tool_calls=(ToolCall(id="1", name="t"),))

    def test_assistant_kan_inte_ha_verktygsresultat(self):
        with pytest.raises(ValueError):
            Message(role="assistant", tool_results=(ToolResult(call_id="1", content="x"),))

    def test_tomt_user_meddelande_avvisas(self):
        with pytest.raises(ValueError):
            Message.user("")

    def test_meddelanden_kan_serialiseras_for_journal(self):
        msg = Message.assistant("Svar", (ToolCall(id="c1", name="t", arguments={"a": 1}),))
        assert Message.model_validate_json(msg.model_dump_json()) == msg
