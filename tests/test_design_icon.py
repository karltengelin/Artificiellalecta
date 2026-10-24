"""Märket som ikon (B-034) – giltig ICO med inbäddade PNG, färgen ur tokenfilen och genomskinliga hörn."""

import struct
import zlib

from design.icon import ICO_SIZES, brand_mark_ico, brand_mark_rgba
from design.web_css import load_tokens


def _rgb(value):
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def test_ico_har_alla_storlekar_som_png():
    ico = brand_mark_ico()
    reserved, kind, count = struct.unpack_from("<HHH", ico, 0)
    assert (reserved, kind, count) == (0, 1, len(ICO_SIZES))
    for i, size in enumerate(ICO_SIZES):
        w, h, _, _, planes, bpp, length, offset = struct.unpack_from("<BBBBHHII", ico, 6 + 16 * i)
        assert (w or 256, h or 256, planes, bpp) == (size, size, 1, 32)
        png = ico[offset:offset + length]
        assert png.startswith(b"\x89PNG\r\n\x1a\n")
        assert struct.unpack(">II", png[16:24]) == (size, size)
        idat = png.index(b"IDAT")
        raw = zlib.decompress(png[idat + 4:idat + 4 + struct.unpack(">I", png[idat - 4:idat])[0]])
        assert len(raw) == size * (1 + size * 4)


def test_rutan_har_markets_farg_och_genomskinliga_horn():
    brand = _rgb(load_tokens()["color"]["brand"])
    size = 32
    rgba = brand_mark_rgba(size, brand)

    def pixel(x, y):
        i = (y * size + x) * 4
        return tuple(rgba[i:i + 4])

    assert pixel(16, 16) == (*brand, 255)
    assert pixel(0, 0)[3] == 0 and pixel(size - 1, size - 1)[3] == 0
    assert pixel(3, 3)[3] < 255  # rundat hörn
