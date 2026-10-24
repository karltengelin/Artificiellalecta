"""Artificiellalectas märke som ikon – den indigofärgade rutan i Digital klarhet (B-034).

    data = brand_mark_ico()            # .ico med flera storlekar, t.ex. för skrivbordsgenvägen

Märket är den enkla indigorutan som designspecifikationen anger som grafisk
markör i v1 (`06_design/designsprak.md`, Typografi och ordmärke) – samma ruta
som i handläggar-UI:ts sidhuvud. Färgen hämtas ur tokenfilen. Bara
standardbiblioteket: PNG-bilder inbäddade i en ICO-fil (stöds sedan Windows Vista).
"""

from __future__ import annotations

import struct
import zlib
from typing import Any

from design.web_css import load_tokens

ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)
MARGIN = 0.06  # luft runt rutan, andel av sidan
RADIUS = 0.22  # hörnradie, andel av rutans sida (UI:ts markör: 4 px av 14)
SUPERSAMPLE = 4


def _hex_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def _inside(x: float, y: float, lo: float, hi: float, r: float) -> bool:
    """Punkten ligger i rundade rutan [lo, hi]² med hörnradie r."""
    if not (lo <= x <= hi and lo <= y <= hi):
        return False
    cx = min(max(x, lo + r), hi - r)
    cy = min(max(y, lo + r), hi - r)
    return (x - cx) ** 2 + (y - cy) ** 2 <= r * r


def brand_mark_rgba(size: int, color: tuple[int, int, int]) -> bytes:
    """RGBA-pixlar (rad för rad) med kantutjämning genom översampling."""
    lo = size * MARGIN
    hi = size - lo
    r = (hi - lo) * RADIUS
    step = 1 / SUPERSAMPLE
    offsets = [(i + 0.5) * step for i in range(SUPERSAMPLE)]
    total = SUPERSAMPLE * SUPERSAMPLE
    out = bytearray()
    for py in range(size):
        for px in range(size):
            hits = sum(_inside(px + dx, py + dy, lo, hi, r) for dy in offsets for dx in offsets)
            out += bytes((*color, round(255 * hits / total)))
    return bytes(out)


def _png(size: int, rgba: bytes) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    row = size * 4
    raw = b"".join(b"\x00" + rgba[y * row:(y + 1) * row] for y in range(size))
    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)  # 8 bitar, RGBA
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


def brand_mark_ico(tokens: dict[str, Any] | None = None, sizes: tuple[int, ...] = ICO_SIZES) -> bytes:
    color = _hex_rgb((tokens or load_tokens())["color"]["brand"])
    images = [_png(s, brand_mark_rgba(s, color)) for s in sizes]
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = len(header) + 16 * len(images)
    entries = b""
    for s, data in zip(sizes, images):
        dim = 0 if s >= 256 else s  # 0 betyder 256 i ICO-formatet
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    return header + entries + b"".join(images)
