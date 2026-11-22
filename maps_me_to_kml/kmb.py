"""Decoder for MAPS.ME KMB files (format byte 10, "V10MM").

The layout follows Organic Maps' reader (libs/kml/serdes_binary.cpp, DeserializeV10MM), which is
itself partly reverse-engineered: fields whose meaning is unknown are checked to be zero, and a file
with unexpected content is rejected instead of being converted wrongly.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .reader import Source
from .textstorage import TextStorage

MERCATOR_MIN, MERCATOR_MAX = -180.0, 180.0
LINE_WIDTH_MIN, LINE_WIDTH_MAX = 0.0, 100.0


class KmbError(ValueError):
    pass


@dataclass
class Color:
    predefined: int = 0
    rgba: int = 0


@dataclass
class Bookmark:
    name: str
    description: str
    custom_name: str
    lat: float
    lon: float
    created: datetime | None
    color: Color
    icon: int
    feature_types: list[int] = field(default_factory=list)
    visible: bool = True


@dataclass
class Track:
    name: str
    description: str
    timestamp: datetime | None
    lines: list[list[tuple[float, float, int]]]   # lines of (lat, lon, altitude m)
    point_times: list[datetime]                    # per point, may be empty
    color: Color
    width: float
    visible: bool = True


@dataclass
class KmbFile:
    name: str
    description: str
    visible: bool
    last_modified: datetime | None
    bookmarks: list[Bookmark]
    tracks: list[Track]


def _u32_to_double(x: int, lo: float, hi: float, bits: int) -> float:
    d = lo + x * (hi - lo) / ((1 << bits) - 1)
    return min(max(d, lo), hi)


def _point(x: int, y: int, bits: int) -> tuple[float, float]:
    """Point stored in Organic Maps' Mercator square (both axes -180..180) -> (lat, lon)."""
    mx = _u32_to_double(x, MERCATOR_MIN, MERCATOR_MAX, bits)
    my = _u32_to_double(y, MERCATOR_MIN, MERCATOR_MAX, bits)
    lat = math.degrees(2.0 * math.atan(math.tanh(0.5 * math.radians(my))))
    return lat, mx


def _time(seconds: int) -> datetime | None:
    if seconds <= 0:
        return None
    try:
        return datetime.fromtimestamp(seconds, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def _maybe_millis(raw: int) -> int:
    # values between 1e9 and 1e12 are seconds, everything else milliseconds
    return raw if 1_000_000_000 <= raw < 1_000_000_000_000 else raw // 1000


def _zero(src: Source, what: str) -> None:
    if src.u8() != 0:
        raise KmbError(f"unsupported nonzero field ({what})")


def _strings(src: Source, storage: TextStorage, size: int) -> list[str]:
    """Localizable string index: `size` slots of {lang: string id} -> one string per slot.

    Known slots: category name/description; bookmark name/description/custom name; track
    name/description. Organic Maps rejects files with text in the other slots; here they are
    read too (MAPS.ME stores e.g. the list description there) and simply ignored by the KML writer.
    """
    n = src.varuint()
    if n != size:
        raise KmbError(f"unexpected string index size {n} (expected {size})")
    out = []
    for _ in range(n):
        values = {}
        for _ in range(src.varuint()):
            lang = src.i8()
            values[lang] = src.varuint()
        sid = values.get(0, next(iter(values.values()), 0))   # default language (code 0) first
        out.append(storage.get(sid) if values else "")
    return out


def _color(src: Source) -> Color:
    return Color(src.u8(), src.u32())


def _line(src: Source, bits: int) -> list[tuple[float, float, int]]:
    count = src.varuint()
    pts, x, y = [], 0, 0
    for _ in range(count):
        x += src.varint()
        y += src.varint()
        pts.append(_point(x, y, bits))
    out, alt = [], 0
    for lat, lon in pts:
        alt += src.varint()
        out.append((lat, lon, alt))
    return out


def read_kmb(data: bytes) -> KmbFile:
    if len(data) < 2:
        raise KmbError("file too short")
    if data[0] != 10:
        raise KmbError(f"unsupported KMB format byte {data[0]} (this tool reads MAPS.ME format 10)")
    bits = data[1]
    if not 1 <= bits <= 32:
        raise KmbError(f"bad coordinate precision {bits}")
    body = data[2:]
    head = Source(body)
    cat_off, bm_off, trk_off, str_off, eos_off = (head.u64() for _ in range(5))
    if not (cat_off == 40 and cat_off <= bm_off <= trk_off <= str_off <= eos_off == len(body)):
        raise KmbError("unsupported section layout")
    storage = TextStorage(body[str_off:eos_off])

    # category
    src = Source(body, cat_off, bm_off)
    src.u64()                                   # category id
    cat_visible = bool(src.u8())
    _zero(src, "category")
    cat_modified = _time(_maybe_millis(src.varuint()))
    _zero(src, "category")
    cat_name, cat_desc, *_ = _strings(src, storage, 5)
    if src.remaining():
        raise KmbError("trailing data in category section")

    # bookmarks
    src = Source(body, bm_off, trk_off)
    bookmarks = []
    for _ in range(src.varuint()):
        src.u64()                               # bookmark id
        types = [src.u32() for _ in range(src.varuint())]
        color = _color(src)
        icon = src.u16()
        src.u8()                                # viewport scale
        created = _time(_maybe_millis(src.varuint()))
        lat, lon = _point(src.varuint(), src.varuint(), bits)
        visible = bool(src.u8())
        _zero(src, "bookmark")
        src.varuint()                           # second timestamp (modification/sync)
        name, desc, custom, *_ = _strings(src, storage, 5)
        bookmarks.append(Bookmark(name, desc, custom, lat, lon, created, color, icon, types, visible))
    if src.remaining():
        raise KmbError("trailing data in bookmarks section")

    # tracks
    src = Source(body, trk_off, str_off)
    tracks = []
    track_count = src.varuint()
    for _ in range(track_count):
        src.u64()                               # track id
        src.u8()                                # local id
        layers = []
        for _ in range(src.varuint()):
            width = _u32_to_double(src.varuint(), LINE_WIDTH_MIN, LINE_WIDTH_MAX, bits)
            layers.append((width, _color(src)))
        ts = _time(src.varuint())
        lines = [_line(src, bits) for _ in range(src.varuint())]
        visible = bool(src.u8())
        _zero(src, "track")
        _zero(src, "track")
        raw_times = [src.varuint() for _ in range(src.varuint())]
        _zero(src, "track")
        # Organic Maps reads a zero byte here (its samples had 0); MAPS.ME files store a varint
        # epoch-millisecond time (modification/sync), like the second timestamp of bookmarks.
        src.varuint()
        name, desc, *_ = _strings(src, storage, 4)
        times = [t for t in (_time((r >> 7) // 1000) for r in raw_times) if t]
        npoints = sum(len(ln) for ln in lines)
        if len(times) == 1 and npoints > 1:     # a single document time, not per point
            ts = ts or times[0]
            times = []
        if not name and track_count == 1:
            name = cat_name
        width, color = layers[0] if layers else (5.0, Color())
        tracks.append(Track(name, desc, ts, lines, times, color, width, visible))
    if src.remaining():
        raise KmbError("trailing data in tracks section")

    return KmbFile(cat_name, cat_desc, cat_visible, cat_modified, bookmarks, tracks)
