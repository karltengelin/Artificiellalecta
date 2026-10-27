"""Versionerade leveranser från bolagsfrågor (OC-3a, B-041 val G).

    store = DeliveryStore()
    receipt = store.publish("FLOW-000007", {"rapport.md": md, "rapport.pdf": pdf}, manifest)
    pdf = store.read("FLOW-000007", 1, "rapport.pdf", receipt["files"]["rapport.pdf"])

Leveranserna hamnar i `logs/deliveries/<flow_id>/v<version>/` (gitignorerat) med `manifest.json`.
Bara flödets systemsteg skriver; ingen överskrivning – en version skrivs en gång och en ny
leverans är en ny version. Kontrollsummorna binds i flödets steg, så en ändrad fil upptäcks
när den läses. En fil här är inte ett gällande dokument och skickas eller publiceras aldrig.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from pathlib import Path
from typing import Any

from agents.errors import HarnessError
from agents.gateways.common import REPO_ROOT

DEFAULT_ROOT = REPO_ROOT / "logs" / "deliveries"
MANIFEST = "manifest.json"
FILE_NAMES = ("rapport.md", "rapport.pdf")
MAX_FILE_BYTES = 5 * 1024 * 1024
_FLOW_ID = re.compile(r"^FLOW-\d{6}$")


class DeliveryError(HarnessError):
    """Leveransen kunde inte skrivas eller stämmer inte med sina kontrollsummor."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class DeliveryStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root or DEFAULT_ROOT)

    def publish(self, flow_id: str, files: dict[str, bytes], manifest: dict[str, Any], *, version: int = 1) -> dict:
        """Skriver en leveransversion en gång. Returnerar kvittot som flödet binder."""
        folder = self._folder(flow_id, version)
        if set(files) - set(FILE_NAMES) or not files:
            raise DeliveryError(f"Leveransen får bara innehålla {', '.join(FILE_NAMES)}")
        for name, data in files.items():
            if not data or len(data) > MAX_FILE_BYTES:
                raise DeliveryError(f"{name}: tom eller större än {MAX_FILE_BYTES // (1024 * 1024)} MiB")
        if folder.exists():
            raise DeliveryError(f"Leveransen {flow_id} v{version} finns redan – en version skrivs bara en gång")
        checksums = {name: sha256(data) for name, data in files.items()}
        body = {**manifest, "flow_id": flow_id, "version": version, "files": checksums}
        encoded = json.dumps(body, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
        folder.mkdir(parents=True)
        for name, data in {**files, MANIFEST: encoded}.items():
            self._write_once(folder / name, data)
        return {"version": version, "folder": f"{flow_id}/v{version}", "files": checksums,
                "manifest_sha256": sha256(encoded)}

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
        if not _FLOW_ID.match(flow_id) or not isinstance(version, int) or not 1 <= version <= 999:
            raise DeliveryError("Ogiltig leveransreferens")
        return self.root / flow_id / f"v{version}"

    @staticmethod
    def _write_once(path: Path, data: bytes) -> None:
        """Skriv till en tillfällig fil och länka in den under sitt namn – misslyckas om namnet finns."""
        tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            tmp.write_bytes(data)
            os.link(tmp, path)
        except FileExistsError as exc:
            raise DeliveryError(f"{path.name} finns redan") from exc
        finally:
            tmp.unlink(missing_ok=True)
