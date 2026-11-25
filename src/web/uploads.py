"""JSON-filer som handläggaren laddar upp i ett formulär (paket A steg 7, delad med paket B steg 8, Z7).

Filen lämnas i operationens format, till exempel från motpartssimulatorn (`simulation.counterparties`).
Märkningen `_label` följer inte med till operationen. Filen sparas aldrig – den läses i minnet och
lämnas till operationen.
"""

from __future__ import annotations

import json
from typing import Any

from web.presenters import ErrorView

#: Största fil som tas emot i formuläret
MAX_UPLOAD_BYTES = 5 * 1024 * 1024


class UploadError(Exception):
    """Den uppladdade filen kunde inte läsas som JSON i operationens format."""


async def read_upload(form) -> dict[str, Any]:
    """Den uppladdade JSON-filen som operationens indata; märkningen `_label` tas bort."""
    upload = form.get("file")
    if upload is None or isinstance(upload, str) or not getattr(upload, "filename", None):
        raise UploadError("Välj en fil att läsa in")
    content = await upload.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise UploadError(f"Filen är större än {MAX_UPLOAD_BYTES // (1024 * 1024)} MB")
    try:
        data = json.loads(content.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UploadError(f"Filen är inte giltig JSON ({exc.__class__.__name__})") from exc
    if not isinstance(data, dict):
        raise UploadError("Filen ska innehålla ett JSON-objekt i operationens format")
    data.pop("_label", None)
    return data


def upload_error(exc: UploadError) -> ErrorView:
    return ErrorView("invalid", "Filen kunde inte läsas", str(exc), 422, field_errors={"file": str(exc)},
                     nothing_changed=True)
