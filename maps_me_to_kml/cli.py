"""Command line interface: maps-me-to-kml INPUT... [-o DIR] [--zip FILE] [--merge FILE]."""

from __future__ import annotations

import argparse
import re
import sys
import zipfile
from pathlib import Path

from . import __version__
from .kmb import KmbFile, read_kmb
from .kml import to_kml


def _inputs(paths: list[str]) -> list[Path]:
    files: list[Path] = []
    for p in map(Path, paths):
        if p.is_dir():
            files += sorted(f for f in p.iterdir() if f.suffix.lower() == ".kmb" and f.is_file())
        elif p.is_file():
            files.append(p)
        else:
            print(f"warning: {p} not found", file=sys.stderr)
    return files


def _safe_name(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "_", name).strip(" .")
    return name or "unnamed"


def _merge(files: list[tuple[str, KmbFile]]) -> str:
    """One KML document with a folder per source file."""
    parts = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<kml xmlns="http://www.opengis.net/kml/2.2" xmlns:gx="http://www.google.com/kml/ext/2.2">',
             "<Document><name>MAPS.ME export</name>"]
    for _, k in files:
        body = to_kml(k)
        inner = body.split("<Document>", 1)[1].rsplit("</Document>", 1)[0]
        parts.append(f"<Folder>{inner}</Folder>")
    parts += ["</Document>", "</kml>", ""]
    return "\n".join(parts)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="maps-me-to-kml",
        description="Convert MAPS.ME bookmark and track files (.kmb) to KML.")
    ap.add_argument("inputs", nargs="+", help=".kmb files or folders containing them (e.g. MapsWithMe/bookmarks)")
    ap.add_argument("-o", "--output", default="kml", help="output folder for one .kml per input (default: ./kml)")
    ap.add_argument("--zip", metavar="FILE", help="also pack all .kml files into this .zip archive")
    ap.add_argument("--merge", metavar="FILE", help="also write everything into one .kml file (a folder per input)")
    ap.add_argument("--no-files", action="store_true", help="do not write the separate .kml files (use with --zip/--merge)")
    ap.add_argument("-q", "--quiet", action="store_true", help="print only the summary and errors")
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = ap.parse_args(argv)

    files = _inputs(args.inputs)
    if not files:
        print("error: no .kmb files found", file=sys.stderr)
        return 2

    out_dir = Path(args.output)
    if not args.no_files:
        out_dir.mkdir(parents=True, exist_ok=True)
    zf = zipfile.ZipFile(args.zip, "w", zipfile.ZIP_DEFLATED) if args.zip else None
    done: list[tuple[str, KmbFile]] = []
    used: set[str] = set()
    failed = bookmarks = tracks = points = 0

    for f in files:
        try:
            k = read_kmb(f.read_bytes())
        except Exception as e:  # noqa: BLE001 - report and continue with the next file
            failed += 1
            print(f"error: {f.name}: {e}", file=sys.stderr)
            continue
        name = _safe_name(f.stem)
        base, n = name, 2
        while name.lower() in used:
            name, n = f"{base} ({n})", n + 1
        used.add(name.lower())
        kml = to_kml(k)
        if not args.no_files:
            (out_dir / f"{name}.kml").write_text(kml, encoding="utf-8")
        if zf:
            zf.writestr(f"{name}.kml", kml)
        done.append((name, k))
        npts = sum(len(line) for t in k.tracks for line in t.lines)
        bookmarks, tracks, points = bookmarks + len(k.bookmarks), tracks + len(k.tracks), points + npts
        if not args.quiet:
            print(f"{f.name} -> {name}.kml  ({len(k.bookmarks)} bookmarks, {len(k.tracks)} tracks, {npts} points)")

    if zf:
        zf.close()
    if args.merge and done:
        Path(args.merge).write_text(_merge(done), encoding="utf-8")

    print(f"converted {len(done)} of {len(files)} files: {bookmarks} bookmarks, {tracks} tracks, {points} points"
          + (f"; {failed} failed" if failed else ""))
    return 1 if failed else 0
