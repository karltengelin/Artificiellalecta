"""Gatewayen `dokument`: Markdown-utkast i körningens egen arbetsyta (harness.md §5.2).

    gateway = DraftGateway()
    gateway.write_draft("compliance", run_id, WriteDraftInput(name="konsekvensanalys.md", title=..., content=...))

Utkasten hamnar i `logs/agent_artifacts/<team>/<run_id>/` (gitignorerat). Team och run-id
kommer från betrodd kod, aldrig från modellen; modellen anger bara ett filnamn ur en snäv
mall. Gatewayen kan inte röra produktregler, regelverk, styrdokument, kod, beslutslogg,
konfiguration eller `.env` – den skriver bara under sin egen rot.

Gränser (harness.md §5.2): högst 100 KiB per utkast, 10 utkast och 512 KiB per körning. Ingen
överskrivning, inget exekverbart innehåll och inga personuppgifter – den allmänna
dokumentpodden är utan PII. Publiceringen är atomisk: utkastet skrivs till en tillfällig fil
och länkas sedan in under sitt namn, vilket misslyckas om namnet redan finns. Id, kontrollsumma,
författande körning och klassificering sparas i körningens `manifest.jsonl`.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from agents.gateways.common import REPO_ROOT, GatewayError, checked_path

DEFAULT_ROOT = REPO_ROOT / "logs" / "agent_artifacts"
MAX_DRAFT_BYTES = 100 * 1024
MAX_DRAFTS_PER_RUN = 10
MAX_RUN_BYTES = 512 * 1024
DATA_CLASS = "intern, utan personuppgifter"
MANIFEST = "manifest.jsonl"

NAME_PATTERN = r"^[a-z0-9][a-z0-9_-]{0,58}\.md$"
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$")
#: Personnummer ÅÅÅÅMMDD-NNNN, ÅÅÅÅMMDDNNNN, ÅÅMMDD-NNNN – den allmänna dokumentpodden är utan PII
_PERSONAL_ID = re.compile(r"(?<!\d)(?:19|20)?\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])[-+]?\d{4}(?!\d)")
_EXECUTABLE = re.compile(r"<\s*(script|iframe|object|embed|form)\b|javascript\s*:|on[a-z]+\s*=\s*[\"']", re.IGNORECASE)
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class WriteDraftInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=NAME_PATTERN, description="Filnamn, t.ex. konsekvensanalys.md – gemener, siffror, - och _")
    title: str = Field(min_length=1, max_length=200, description="Utkastets rubrik")
    content: str = Field(min_length=1, description="Markdown, högst 100 KiB. Inga personuppgifter")


class DraftReceipt(BaseModel):
    name: str
    title: str
    team: str
    run_id: str
    sha256: str
    bytes: int
    data_class: str
    created_at: str
    reference: str = Field(description="Referens för flödet och körjournalen: utkast:<team>/<run_id>/<namn>")


class DraftList(BaseModel):
    team: str
    run_id: str
    drafts: list[DraftReceipt]
    total_bytes: int


class DraftGateway:
    """Utkast per team och körning under en egen rot (standard `logs/agent_artifacts/`)."""

    def __init__(self, root: Path = DEFAULT_ROOT) -> None:
        self.root = root

    # --- betrodd kod: team och körning ---------------------------------------------------------

    @staticmethod
    def _check_ids(team: str, run_id: str) -> None:
        for what, value in (("team", team), ("run_id", run_id)):
            if not _ID.match(value):
                raise GatewayError("security", f"Ogiltigt {what}: {value!r}", security=True)

    def _run_dir(self, team: str, run_id: str, *, create: bool) -> Path | None:
        self._check_ids(team, run_id)
        if create:
            self.root.mkdir(parents=True, exist_ok=True)
            for relative in (Path(team), Path(team) / run_id):
                target = checked_path(self.root, relative, must_exist=False)
                target.mkdir(exist_ok=True)
        relative = Path(team) / run_id
        if not (self.root / relative).exists():
            return None
        return checked_path(self.root, relative)

    def list_drafts(self, team: str, run_id: str) -> DraftList:
        run_dir = self._run_dir(team, run_id, create=False)
        drafts = []
        if run_dir is not None and (run_dir / MANIFEST).exists():
            manifest = checked_path(self.root, Path(team) / run_id / MANIFEST)
            drafts = [DraftReceipt(**json.loads(line)) for line in manifest.read_text(encoding="utf-8").splitlines() if line]
        return DraftList(team=team, run_id=run_id, drafts=drafts, total_bytes=sum(d.bytes for d in drafts))

    def read_draft(self, team: str, run_id: str, name: str) -> str:
        """Utkastets text, för flödet och operatörens granskning (betrodd kod)."""
        self._check_ids(team, run_id)
        if not re.match(NAME_PATTERN, name):
            raise GatewayError("security", f"Ogiltigt filnamn: {name!r}", security=True)
        if not any(d.name == name for d in self.list_drafts(team, run_id).drafts):
            raise GatewayError("not_found", f"Inget utkast {name} i {team}/{run_id}")
        return checked_path(self.root, Path(team) / run_id / name).read_text(encoding="utf-8")

    # --- verktyget -------------------------------------------------------------------------------

    def write_draft(self, team: str, run_id: str, data: WriteDraftInput) -> DraftReceipt:
        content = data.content if data.content.endswith("\n") else data.content + "\n"
        raw = content.encode("utf-8")
        if len(raw) > MAX_DRAFT_BYTES:
            raise GatewayError("limit", f"Utkastet är {len(raw) // 1024} KiB – högst {MAX_DRAFT_BYTES // 1024} KiB per utkast")
        _check_content(data.title + "\n" + content)

        self._check_ids(team, run_id)
        existing = self.list_drafts(team, run_id)
        if any(d.name == data.name for d in existing.drafts):
            raise GatewayError("conflict", f"Utkastet {data.name} finns redan i körningen – utkast skrivs aldrig över; välj ett nytt namn")
        if len(existing.drafts) >= MAX_DRAFTS_PER_RUN:
            raise GatewayError("limit", f"Körningen har redan {MAX_DRAFTS_PER_RUN} utkast – högsta antalet")
        if existing.total_bytes + len(raw) > MAX_RUN_BYTES:
            raise GatewayError("limit", f"Körningens utkast skulle bli större än {MAX_RUN_BYTES // 1024} KiB")

        run_dir = self._run_dir(team, run_id, create=True)
        final = run_dir / data.name
        if final.exists() or os.path.lexists(final):
            raise GatewayError("conflict", f"Utkastet {data.name} finns redan – utkast skrivs aldrig över")
        temporary = run_dir / f".{data.name}.{uuid.uuid4().hex}.tmp"
        with open(temporary, "xb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, final)  # misslyckas om namnet redan finns – ingen överskrivning
        except FileExistsError:
            raise GatewayError("conflict", f"Utkastet {data.name} finns redan – utkast skrivs aldrig över") from None
        finally:
            temporary.unlink(missing_ok=True)

        receipt = DraftReceipt(
            name=data.name, title=data.title, team=team, run_id=run_id,
            sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw), data_class=DATA_CLASS,
            created_at=datetime.now(UTC).isoformat(timespec="seconds"),
            reference=f"utkast:{team}/{run_id}/{data.name}",
        )
        with open(run_dir / MANIFEST, "a", encoding="utf-8") as manifest:
            manifest.write(json.dumps(receipt.model_dump(), ensure_ascii=False) + "\n")
            manifest.flush()
            os.fsync(manifest.fileno())
        return receipt


def _check_content(text: str) -> None:
    if _CONTROL.search(text):
        raise GatewayError("invalid", "Utkastet innehåller otillåtna kontrolltecken")
    if _EXECUTABLE.search(text):
        raise GatewayError("blocked", "Utkastet innehåller exekverbart innehåll (skript, inbäddning eller händelseattribut) – bara Markdown är tillåtet")
    if _PERSONAL_ID.search(text):
        raise GatewayError("blocked", "Utkastet ser ut att innehålla ett personnummer – dokumentpodden är utan personuppgifter")
