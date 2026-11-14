"""Skrivskyddad läsning av tidigare leveranser med sparad kontrollsumma."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from agents.errors import HarnessError
from agents.gateways.common import REPO_ROOT

DEFAULT_ROOT = REPO_ROOT / "logs" / "deliveries"
MANIFEST = "manifest.json"
FILE_NAMES = ("rapport.md", "rapport.pdf")
_FLOW_ID = re.compile(r"^FLOW-\d{6}$")


class DeliveryError(HarnessError):
    """Leveransen saknas eller stämmer inte med sina kontrollsummor."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class DeliveryStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root or DEFAULT_ROOT)

    def read(self, flow_id: str, version: int, name: str, expected_sha256: str) -> bytes:
        """En leveransfil – bara om den stämmer med kontrollsumman flödet har bundit."""
        if name not in (*FILE_NAMES, MANIFEST):
            raise DeliveryError(f"Okänd leveransfil: {name}")
        path = self._folder(flow_id, version) / name
        if not path.is_file():
            raise DeliveryError(f"Leveransfilen {name} saknas för {flow_id} v{version}")
        data = path.read_bytes()
        if sha256(data) != expected_sha256:
            raise DeliveryError(f"{name} för {flow_id} v{version} har ändrats sedan leveransen skapades")
        return data

    def _folder(self, flow_id: str, version: int) -> Path:
        if not _FLOW_ID.fullmatch(flow_id) or not isinstance(version, int) or not 1 <= version <= 999:
            raise DeliveryError("Ogiltig leveransreferens")
        return self.root / flow_id / f"v{version}"
