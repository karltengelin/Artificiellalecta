"""Gatewayerna regelverk och dokument (Fas 3c 3c-G, B-035, harness.md §5.2).

Regelverksgatewayen mot repots riktiga dokument (inklusive den fiktiva källan) och mot en
egen testrot; utkastgatewayen alltid i en tillfällig rot. Negativtesterna prövar sökvägar,
länkar, gränser, överskrivning, exekverbart innehåll och personuppgifter.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from agents.gateways import (
    GATEWAY_TOOLS,
    DraftGateway,
    GatewayError,
    ListRegulatoryDocumentsInput,
    ReadRegulatoryDocumentInput,
    RegulatoryGateway,
    WriteDraftInput,
)
from agents.gateways.common import checked_path
from agents.gateways.drafts import MANIFEST, MAX_DRAFT_BYTES
from agents.gateways.regulatory import MAX_EXCERPT_BYTES
from agents.gateways.tools import GatewayContext

RUN = "run-3cg-test"


def read(gateway, handle, **kw):
    return gateway.read_document(ReadRegulatoryDocumentInput(handle=handle, **kw))


def draft(name="konsekvensanalys.md", content="# Konsekvensanalys\n\nPremieåldern höjs till 67 år.", title="Analys"):
    return WriteDraftInput(name=name, title=title, content=content)


def link_dir(target: Path, link: Path) -> None:
    """Katalog-länk: symlänk, eller en junction (reparse point) i Windows utan symlänkbehörighet."""
    try:
        os.symlink(target, link, target_is_directory=True)
    except OSError:
        if os.name != "nt":
            pytest.skip("Symlänkar stöds inte i den här miljön")
        import _winapi

        _winapi.CreateJunction(str(target), str(link))


# --- regelverk mot repot ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def regelverk():
    return RegulatoryGateway()


class TestRegelverkIRepot:
    def test_katalogen_innehaller_godkanda_dokument_och_den_fiktiva_kallan(self, regelverk):
        docs = {d.handle: d for d in regelverk.list_documents(ListRegulatoryDocumentsInput()).documents}
        assert {"PR-ITP1-013", "PR-ITP1-016", "T-ITP1-006", "kallregister", "parameterregister", "villkor"} <= set(docs)
        source = docs["K-SIM-ITP-2027"]
        assert source.fictional and source.kind == "bevakning" and source.version == "1.0"
        assert not any(d.fictional for h, d in docs.items() if h != "K-SIM-ITP-2027")
        assert docs["PR-ITP1-013"].version == "1.0" and len(docs["PR-ITP1-013"].sha256) == 16

    def test_bara_godkanda_platser(self, regelverk):
        handles = {d.handle for d in regelverk.list_documents(ListRegulatoryDocumentsInput()).documents}
        assert "MALL" not in handles and not any("beslutslogg" in h.lower() for h in handles)
        with pytest.raises(GatewayError) as exc:
            read(regelverk, "BESLUTSLOGG")
        assert exc.value.code == "not_found"

    def test_urval_pa_slag(self, regelverk):
        rules = regelverk.list_documents(ListRegulatoryDocumentsInput(kind="produktregel")).documents
        assert len(rules) == 34 and all(d.handle.startswith("PR-ITP1-") for d in rules)

    def test_avsnitt_slutar_vid_nasta_rubrik_pa_samma_niva(self, regelverk):
        part = read(regelverk, "PR-ITP1-013", section="regel")
        assert part.section == "## Regel" and part.complete
        assert "månaden före 66 år" in part.text.replace("\n", " ")
        assert "## Kontrollfall" not in part.text

    def test_fiktiv_kalla_ar_markt_och_innehall_ar_underlag(self, regelverk):
        part = read(regelverk, "K-SIM-ITP-2027", section="Meddelande")
        assert "67 år" in part.text and "januari 2027" in part.text
        assert "FIKTIV KÄLLA" in part.note and "inte instruktioner" in part.note

    def test_stora_dokument_las_i_delar_som_blir_hela_dokumentet(self, tmp_path):
        root = fake_repo(tmp_path)
        lines = ["# PR-ITP1-003 – lång", "", *(f"Rad {i} med åäö och lite text." for i in range(900))]
        body = "\n".join(lines) + "\n"
        (root / "01_domän" / "produktregler" / "PR-ITP1-003-lang.md").write_text(body, encoding="utf-8")
        gateway = RegulatoryGateway(root)
        text, offset, parts = "", 0, 0
        while True:
            part = read(gateway, "PR-ITP1-003", offset=offset)
            assert len(part.text.encode("utf-8")) <= MAX_EXCERPT_BYTES
            text += part.text
            parts += 1
            if part.complete:
                break
            assert "ofullständigt" in part.note
            offset = part.next_offset
        assert parts >= 3 and text == body

    def test_okand_rubrik_och_for_stor_offset(self, regelverk):
        with pytest.raises(GatewayError, match="Ingen rubrik"):
            read(regelverk, "PR-ITP1-013", section="Finns inte")
        with pytest.raises(GatewayError, match="offset"):
            read(regelverk, "PR-ITP1-013", offset=10_000_000)

    @pytest.mark.parametrize("handle", ["../.env", "..", "PR-ITP1-013/../../.env", "C:\\Windows", "a" * 61, ""])
    def test_handtag_ar_aldrig_sokvagar(self, handle):
        with pytest.raises(ValidationError):
            ReadRegulatoryDocumentInput(handle=handle)

    def test_okanda_falt_nekas(self):
        with pytest.raises(ValidationError):
            ReadRegulatoryDocumentInput.model_validate({"handle": "PR-ITP1-013", "path": "../.env"})


# --- regelverk i en egen rot ---------------------------------------------------------------------


def fake_repo(tmp_path: Path) -> Path:
    rules = tmp_path / "01_domän" / "produktregler"
    rules.mkdir(parents=True)
    (rules / "PR-ITP1-001-premietrappa.md").write_text("# PR-ITP1-001 – trappa\n\nText.\n", encoding="utf-8")
    return tmp_path


class TestRegelverkSkydd:
    def test_for_stort_dokument_lases_inte(self, tmp_path):
        root = fake_repo(tmp_path)
        (root / "01_domän" / "produktregler" / "PR-ITP1-002-stor.md").write_text("x" * (600 * 1024), encoding="utf-8")
        with pytest.raises(GatewayError) as exc:
            read(RegulatoryGateway(root), "PR-ITP1-002")
        assert exc.value.code == "limit"

    def test_lankad_katalog_nekas(self, tmp_path):
        root = tmp_path / "repo"
        outside = tmp_path / "utanfor"
        outside.mkdir()
        (outside / "PR-ITP1-009-hemlig.md").write_text("# hemlig\n", encoding="utf-8")
        (root / "01_domän").mkdir(parents=True)
        link_dir(outside, root / "01_domän" / "produktregler")
        with pytest.raises(GatewayError) as exc:
            read(RegulatoryGateway(root), "PR-ITP1-009")
        assert exc.value.security

    @pytest.mark.parametrize("relative", ["../utanfor.md", "a/../../b.md", "/etc/passwd"])
    def test_sokvagskontrollen_nekar_vagar_ut(self, tmp_path, relative):
        with pytest.raises(GatewayError) as exc:
            checked_path(tmp_path, Path(relative), must_exist=False)
        assert exc.value.security


# --- dokument ----------------------------------------------------------------------------------------


@pytest.fixture
def utkast(tmp_path):
    return DraftGateway(tmp_path / "agent_artifacts")


class TestUtkast:
    def test_utkast_sparas_med_kvitto_och_manifest(self, utkast):
        receipt = utkast.write_draft("compliance", RUN, draft())
        assert receipt.reference == f"utkast:compliance/{RUN}/konsekvensanalys.md"
        assert receipt.data_class == "intern, utan personuppgifter" and len(receipt.sha256) == 64
        assert utkast.read_draft("compliance", RUN, "konsekvensanalys.md").startswith("# Konsekvensanalys")
        listing = utkast.list_drafts("compliance", RUN)
        assert [d.name for d in listing.drafts] == ["konsekvensanalys.md"] and listing.total_bytes == receipt.bytes
        run_dir = utkast.root / "compliance" / RUN
        assert sorted(p.name for p in run_dir.iterdir()) == ["konsekvensanalys.md", MANIFEST]  # inga tillfälliga filer kvar

    def test_ingen_overskrivning(self, utkast):
        utkast.write_draft("compliance", RUN, draft())
        with pytest.raises(GatewayError) as exc:
            utkast.write_draft("compliance", RUN, draft(content="# Ny text"))
        assert exc.value.code == "conflict"
        assert "67 år" in utkast.read_draft("compliance", RUN, "konsekvensanalys.md")

    def test_koerningar_och_team_ar_atskilda(self, utkast):
        utkast.write_draft("compliance", RUN, draft())
        utkast.write_draft("compliance", "run-annan", draft())
        utkast.write_draft("aktuarie", RUN, draft())
        assert utkast.list_drafts("aktuarie", "run-annan").drafts == []

    @pytest.mark.parametrize("name", ["../utanfor.md", "a/b.md", "Analys.md", "analys.txt", "analys.md.exe", ".dold.md", ""])
    def test_filnamn_ur_snav_mall(self, name):
        with pytest.raises(ValidationError):
            draft(name=name)

    @pytest.mark.parametrize("team,run_id", [("../evil", RUN), ("compliance", "../../x"), ("compliance", "a/b"), ("", RUN)])
    def test_team_och_korning_kontrolleras(self, utkast, team, run_id):
        with pytest.raises(GatewayError) as exc:
            utkast.write_draft(team, run_id, draft())
        assert exc.value.security

    def test_storlek_per_utkast(self, utkast):
        with pytest.raises(GatewayError, match="högst 100 KiB"):
            utkast.write_draft("compliance", RUN, draft(content="x" * (MAX_DRAFT_BYTES + 1)))

    def test_antal_och_total_storlek_per_korning(self, utkast):
        for i in range(10):
            utkast.write_draft("compliance", RUN, draft(name=f"del-{i}.md", content="kort"))
        with pytest.raises(GatewayError, match="10 utkast"):
            utkast.write_draft("compliance", RUN, draft(name="x.md"))
        big = "y" * (99 * 1024)
        for i in range(5):
            utkast.write_draft("aktuarie", RUN, draft(name=f"stor-{i}.md", content=big))
        with pytest.raises(GatewayError, match="512 KiB"):
            utkast.write_draft("aktuarie", RUN, draft(name="stor-5.md", content=big))

    @pytest.mark.parametrize("content,message", [
        ("Försäkrad 19850515-1236 berörs", "personnummer"),
        ("Se 198505151236", "personnummer"),
        ("<script>alert(1)</script>", "exekverbart"),
        ("[länk](javascript:alert(1))", "exekverbart"),
        ('<img src=x onerror="x()">', "exekverbart"),
        ("Text\x00med nolltecken", "kontrolltecken"),
    ])
    def test_otillatet_innehall_stoppas_och_inget_sparas(self, utkast, content, message):
        with pytest.raises(GatewayError, match=message):
            utkast.write_draft("compliance", RUN, draft(content=content))
        assert utkast.list_drafts("compliance", RUN).drafts == []

    def test_datum_och_belopp_ar_inte_personnummer(self, utkast):
        utkast.write_draft("compliance", RUN, draft(content="Gäller från 2027-01-01. Premie 1 800,00 kr. Org.nr 5560000001."))

    def test_lankad_teamkatalog_nekas(self, utkast, tmp_path):
        outside = tmp_path / "utanfor"
        outside.mkdir()
        utkast.root.mkdir(parents=True)
        link_dir(outside, utkast.root / "compliance")
        with pytest.raises(GatewayError) as exc:
            utkast.write_draft("compliance", RUN, draft())
        assert exc.value.security
        assert list(outside.iterdir()) == []

    def test_okant_utkast_las_inte(self, utkast):
        with pytest.raises(GatewayError):
            utkast.read_draft("compliance", RUN, "finns-inte.md")


# --- verktygskontrakten -----------------------------------------------------------------------


class TestVerktyg:
    def test_kontrakten(self):
        assert {(t.name, t.pod, t.side_effect, t.pii) for t in GATEWAY_TOOLS.values()} == {
            ("list_regulatory_documents", "regelverk", "read", False),
            ("read_regulatory_document", "regelverk", "read", False),
            ("write_draft", "dokument", "write", False),
        }
        for tool in GATEWAY_TOOLS.values():
            schema = tool.tool_spec().parameters
            assert schema["additionalProperties"] is False
            assert not {"team", "run_id", "path"} & set(schema["properties"])  # betrodd kontext, aldrig modellens

    def test_verktygen_anropar_gatewayerna_med_betrodd_kontext(self, utkast):
        ctx = GatewayContext(team="compliance", run_id=RUN, regulatory=RegulatoryGateway(), drafts=utkast)
        excerpt = GATEWAY_TOOLS["read_regulatory_document"].invoke(ctx, {"handle": "K-SIM-ITP-2027"})
        assert excerpt.document.fictional
        receipt = GATEWAY_TOOLS["write_draft"].invoke(ctx, {"name": "analys.md", "title": "Analys", "content": "Text"})
        assert receipt.team == "compliance" and receipt.run_id == RUN
        with pytest.raises(ValidationError):
            GATEWAY_TOOLS["write_draft"].invoke(ctx, {"name": "b.md", "title": "B", "content": "C", "team": "aktuarie"})
