"""Minimal writer of MAPS.ME format-10 KMB files, used only to build test fixtures.

It mirrors the reader, so tests do not need real (private) user files.
"""

from __future__ import annotations

import math
import struct


def varuint(v: int) -> bytes:
    out = bytearray()
    while True:
        b = v & 0x7F
        v >>= 7
        if v:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def varint(v: int) -> bytes:
    return varuint((v << 1) ^ (v >> 63) if v < 0 else v << 1)


def bwt(s: bytes) -> tuple[int, bytes]:
    """Same convention as coding::BWT (suffix array without a sentinel)."""
    n = len(s)
    sa = sorted(range(n), key=lambda i: s[i:])
    out, start = bytearray(n), 0
    for i, p in enumerate(sa):
        if p:
            out[i] = s[p - 1]
        else:
            start, out[i] = i, s[n - 1]
    return start, bytes(out)


def mtf(data: bytes) -> bytes:
    order, out = list(range(256)), bytearray()
    for b in data:
        i = order.index(b)
        out.append(i)
        del order[i]
        order.insert(0, b)
    return bytes(out)


def huffman(data: bytes) -> bytes:
    """A valid (not optimal) prefix code: every used symbol gets an 8-bit code equal to itself."""
    symbols = sorted(set(data)) or [0]
    out = bytearray(varuint(len(symbols)))
    for s in symbols:
        out += varuint(s) + varuint(8) + varuint(s)      # code bits, length, symbol
    out += varuint(len(data))
    # bit j of a code is read j-th, bits are packed LSB first -> the byte itself
    out += bytes(data)
    return bytes(out)


def text_storage(strings: list[str]) -> bytes:
    raw = [s.encode("utf-8") for s in strings]
    joined = b"".join(raw)
    start, transformed = bwt(joined)
    block = b"".join(varuint(len(r)) for r in raw) + varuint(start) + huffman(mtf(transformed))
    index = varuint(1) + varuint(0) + varuint(len(raw))   # one block right after the 8-byte offset
    return struct.pack("<Q", 8 + len(block)) + block + index


BITS = 30


def point(lat: float, lon: float) -> tuple[int, int]:
    y = math.degrees(math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)))
    to = lambda v: round((v + 180.0) * ((1 << BITS) - 1) / 360.0)   # noqa: E731
    return to(lon), to(y)


class Kmb:
    def __init__(self, name: str, description: str = ""):
        self.strings = [""]
        self.category = (name, description)
        self.bookmarks: list[bytes] = []
        self.tracks: list[bytes] = []

    def _sid(self, s: str) -> int:
        if not s:
            return 0
        self.strings.append(s)
        return len(self.strings) - 1

    def _index(self, values: list[str], size: int) -> bytes:
        out = bytearray(varuint(size))
        for i in range(size):
            v = values[i] if i < len(values) else ""
            out += varuint(1) + struct.pack("<b", 0) + varuint(self._sid(v)) if v else varuint(0)
        return bytes(out)

    def bookmark(self, name: str, lat: float, lon: float, description: str = "", created_ms: int = 0,
                 rgba: int = 0, predefined: int = 1) -> None:
        x, y = point(lat, lon)
        self.bookmarks.append(
            struct.pack("<Q", len(self.bookmarks) + 1) + varuint(0) + struct.pack("<BIHB", predefined, rgba, 0, 0)
            + varuint(created_ms) + varuint(x) + varuint(y) + b"\x01\x00" + varuint(created_ms)
            + self._index([name, description], 5))

    def track(self, name: str, pts: list[tuple[float, float, int]], times_s: list[int] | None = None,
              rgba: int = 0xFF0000FF, width: float = 5.0) -> None:
        line, px, py = bytearray(varuint(len(pts))), 0, 0
        for lat, lon, _ in pts:
            x, y = point(lat, lon)
            line += varint(x - px) + varint(y - py)
            px, py = x, y
        alt = 0
        for _, _, a in pts:
            line += varint(a - alt)
            alt = a
        w = round(width * ((1 << BITS) - 1) / 100.0)
        times = times_s or []
        self.tracks.append(
            struct.pack("<QB", len(self.tracks) + 1, 0) + varuint(1) + varuint(w) + struct.pack("<BI", 0, rgba)
            + varuint(0) + varuint(1) + bytes(line) + b"\x01\x00\x00"
            + varuint(len(times)) + b"".join(varuint((t * 1000) << 7) for t in times)
            + b"\x00" + varuint(0) + self._index([name], 4))

    def build(self) -> bytes:
        cat = struct.pack("<QBB", 7, 1, 0) + varuint(1_700_000_000_000) + b"\x00" + self._index(list(self.category), 5)
        bms = varuint(len(self.bookmarks)) + b"".join(self.bookmarks)
        trs = varuint(len(self.tracks)) + b"".join(self.tracks)
        strings = text_storage(self.strings)
        offs, pos = [], 40
        for section in (cat, bms, trs, strings):
            offs.append(pos)
            pos += len(section)
        offs.append(pos)
        return bytes([10, BITS]) + struct.pack("<5Q", *offs) + cat + bms + trs + strings
