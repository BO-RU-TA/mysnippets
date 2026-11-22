"""KML writer for decoded MAPS.ME KMB files (KML 2.2, Google extension gx:Track for timed tracks)."""

from __future__ import annotations

from datetime import datetime
from xml.sax.saxutils import escape

from .kmb import Color, KmbFile

# MAPS.ME predefined bookmark/track colours (kml::PredefinedColor) as RGB
PREDEFINED = {
    1: "e51b23", 2: "ff4182", 3: "9b24b2", 4: "0066ff", 5: "0066ff", 6: "00ad80", 7: "ffc800",
    8: "ff9600", 9: "804633", 10: "993321", 11: "a2a2a2", 12: "ffffff", 13: "000000",
}


def _kml_color(c: Color, default: str = "ff0000") -> str:
    """KML colour aabbggrr from a MAPS.ME colour (rgba 0xRRGGBBAA or a predefined colour)."""
    if c.rgba:
        r, g, b, a = (c.rgba >> 24) & 255, (c.rgba >> 16) & 255, (c.rgba >> 8) & 255, c.rgba & 255
        return f"{a or 255:02x}{b:02x}{g:02x}{r:02x}"
    rgb = PREDEFINED.get(c.predefined, default)
    return f"ff{rgb[4:6]}{rgb[2:4]}{rgb[0:2]}"


def _when(t: datetime | None) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ") if t else ""


def _text(tag: str, value: str, cdata: bool = False) -> str:
    if not value:
        return ""
    if cdata and "]]>" not in value:
        return f"<{tag}><![CDATA[{value}]]></{tag}>"
    return f"<{tag}>{escape(value)}</{tag}>"


def _coord(lat: float, lon: float, alt: int | None = None) -> str:
    return f"{lon:.7f},{lat:.7f}" + (f",{alt}" if alt is not None else "")


def to_kml(k: KmbFile) -> str:
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<kml xmlns="http://www.opengis.net/kml/2.2" xmlns:gx="http://www.google.com/kml/ext/2.2">',
           "<Document>", _text("name", k.name), _text("description", k.description, True),
           f"<visibility>{int(k.visible)}</visibility>"]
    styles: dict[str, str] = {}

    def style(kind: str, color: str, width: float = 0) -> str:
        sid = f"{kind}-{color}" + (f"-{width:g}" if width else "")
        if sid not in styles:
            if kind == "line":
                body = f"<LineStyle><color>{color}</color><width>{width:g}</width></LineStyle>"
            else:
                body = f"<IconStyle><color>{color}</color></IconStyle>"
            styles[sid] = f'<Style id="{escape(sid)}">{body}</Style>'
        return sid

    marks = []
    for b in k.bookmarks:
        sid = style("icon", _kml_color(b.color, "e51b23"))
        name = b.custom_name or b.name
        marks.append("".join([
            "<Placemark>", _text("name", name), _text("description", b.description, True),
            f"<TimeStamp><when>{_when(b.created)}</when></TimeStamp>" if b.created else "",
            f"<styleUrl>#{sid}</styleUrl>", f"<visibility>{int(b.visible)}</visibility>",
            f"<Point><coordinates>{_coord(b.lat, b.lon)}</coordinates></Point>", "</Placemark>"]))

    for t in k.tracks:
        sid = style("line", _kml_color(t.color), t.width or 5.0)
        npts = sum(len(line) for line in t.lines)
        if t.point_times and len(t.point_times) == npts and len(t.lines) == 1:
            geom = "<gx:Track>" + "".join(f"<when>{_when(w)}</when>" for w in t.point_times) + "".join(
                f"<gx:coord>{lon:.7f} {lat:.7f} {alt}</gx:coord>" for lat, lon, alt in t.lines[0]) + "</gx:Track>"
        else:
            lines = [
                "<LineString><tessellate>1</tessellate><altitudeMode>absolute</altitudeMode><coordinates>"
                + " ".join(_coord(lat, lon, alt) for lat, lon, alt in line) + "</coordinates></LineString>"
                for line in t.lines if len(line) > 1]
            geom = lines[0] if len(lines) == 1 else "<MultiGeometry>" + "".join(lines) + "</MultiGeometry>"
        marks.append("".join([
            "<Placemark>", _text("name", t.name), _text("description", t.description, True),
            f"<TimeStamp><when>{_when(t.timestamp)}</when></TimeStamp>" if t.timestamp else "",
            f"<styleUrl>#{sid}</styleUrl>", f"<visibility>{int(t.visible)}</visibility>", geom, "</Placemark>"]))

    out += list(styles.values()) + marks + ["</Document>", "</kml>", ""]
    return "\n".join(x for x in out if x)
