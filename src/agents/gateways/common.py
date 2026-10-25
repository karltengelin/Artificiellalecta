"""Gemensamt för gatewayerna: fel och kontroll av verkliga sökvägar (harness.md §5.2).

Gatewayerna utgår alltid från en egen rot och egna handtag. Kontrollerna nedan avvisar
symlänkar och Windows junctions/reparse points i varje led, och att den verkliga sökvägen
hamnar utanför roten. De kompletterar – ersätter inte – isolering med OS-rättigheter.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


class GatewayError(Exception):
    """Ett nej från en gateway. `code` säger vilket slags nej; `security` att anropet bröt mot en gräns."""

    def __init__(self, code: str, message: str, *, security: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.security = security


def is_link_or_reparse(path: Path) -> bool:
    """Symlänk, junction eller annan reparse point (Windows)."""
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return False
    if stat.S_ISLNK(info.st_mode):
        return True
    attributes = getattr(info, "st_file_attributes", 0)
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def checked_path(root: Path, relative: Path, *, must_exist: bool = True) -> Path:
    """`root / relative` om varje led är en vanlig katalog eller fil och resultatet ligger under roten.

    `relative` kommer alltid från gatewayens egen katalog eller ett validerat namn – aldrig
    direkt från modellen. Kontrollen görs ändå fullt ut, så att ett fel i den koden inte blir
    en väg ut ur roten.
    """
    if relative.is_absolute() or any(part in ("", ".", "..") for part in relative.parts):
        raise GatewayError("security", f"Otillåten sökväg: {relative.as_posix()}", security=True)
    real_root = root.resolve(strict=True)
    current = root
    for part in relative.parts:
        current = current / part
        if is_link_or_reparse(current):
            raise GatewayError("security", f"Länkar och reparse points är inte tillåtna: {relative.as_posix()}", security=True)
    resolved = current.resolve(strict=must_exist)
    if not resolved.is_relative_to(real_root):
        raise GatewayError("security", f"Sökvägen hamnar utanför gatewayens rot: {relative.as_posix()}", security=True)
    return resolved
