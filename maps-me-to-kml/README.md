# maps-me-to-kml

Convert **MAPS.ME bookmarks and tracks** (`.kmb` files) to **KML** - all of them at once.

MAPS.ME keeps every bookmark list and every imported/recorded track in its own binary `.kmb` file.
The app can export lists one by one, which is not an option with hundreds or thousands of them.
This tool reads the `.kmb` files directly (copied from the phone) and writes standard KML that opens
in Google Earth, QGIS, Organic Maps, OsmAnd, Locus, GPS Visualizer, etc.

- bookmarks -> `Placemark` with `Point` (name, description, creation time, colour)
- tracks -> `LineString` with altitude, or `gx:Track` when the file has per-point times
- list name and description -> KML `Document`
- one `.kml` per `.kmb`, optionally a single **ZIP** archive and/or one **merged** KML
- no dependencies: Python 3.9+ standard library only

Tested on 924 real files (920 tracks, 934 bookmarks, 2.6 million points): all converted, decoded
coordinates match the original GPS files to within 2 cm.

## Supported files

MAPS.ME **format 10** - the first byte of the file is `0x0A`. This is what current MAPS.ME
versions write (seen in files from 2020 to 2026, re-saved by the app). Other formats are reported as
errors and skipped. Check a file with:

```
python3 -c "import sys; print(open(sys.argv[1], 'rb').read(1)[0])" "My list.kmb"
```

## Getting the files from the phone

The bookmarks live in **`MapsWithMe/bookmarks/`** in the phone's internal storage (not in
`Android/data`), one `.kmb` file per list or track.

- **Windows, USB cable (MTP):** This PC -> phone -> Internal storage -> `MapsWithMe` -> `bookmarks`,
  copy the whole folder.
- **adb:** `adb pull /sdcard/MapsWithMe/bookmarks ./bookmarks`
- Newer installs may keep the data in `Android/data/com.mapswithme.maps.pro/files/` instead; on
  Android 11+ that folder is hidden from MTP, use `adb pull` on it.

## Install

```
pip install "git+https://github.com/BO-RU-TA/mysnippets#subdirectory=maps-me-to-kml"
```

or just clone the repository and run it with `python3 -m maps_me_to_kml` from the `maps-me-to-kml` folder.

## Usage

```
maps-me-to-kml bookmarks/                    # -> ./kml/<file>.kml for every .kmb
maps-me-to-kml bookmarks/ -o out --zip mapsme-kml.zip
maps-me-to-kml bookmarks/ --no-files --merge all.kml
maps-me-to-kml "Trip 2024.kmb" "Favourites.kmb"
```

| Option | Meaning |
|---|---|
| `INPUT...` | `.kmb` files and/or folders containing them |
| `-o, --output DIR` | folder for the separate `.kml` files (default `./kml`) |
| `--zip FILE` | also pack all `.kml` files into a ZIP archive |
| `--merge FILE` | also write one KML with a folder per input file |
| `--no-files` | do not write the separate files (use with `--zip` / `--merge`) |
| `-q, --quiet` | only the summary and errors |

The exit code is 0 when everything was converted, 1 when some files failed, 2 when nothing was found.
Output file names follow the input names; characters not allowed in file names are replaced.

As a library:

```python
from maps_me_to_kml import read_kmb, to_kml

data = read_kmb(open("Trip.kmb", "rb").read())
print(data.name, len(data.bookmarks), len(data.tracks))
open("Trip.kml", "w", encoding="utf-8").write(to_kml(data))
```

## Notes and limits

- Coordinates are stored by MAPS.ME with 30-bit precision (about 4 cm at the equator); altitudes in
  whole metres.
- Bookmark icons and feature types are not exported (KML has no equivalent); colours are.
- The format is not documented by MAPS.ME. Fields whose meaning is unknown are checked and a file
  that does not match the known layout is rejected rather than converted wrongly. See
  [docs/FORMAT.md](docs/FORMAT.md).
- Privacy: tracks usually start and end where you slept. Think twice before sharing the KML.

## Development

```
python3 -m unittest discover -s tests
```

The tests build synthetic `.kmb` files (`tests/kmb_builder.py`), so no real user data is needed.

## Credits

The file layout was worked out from the open-source KMB reader of
[Organic Maps](https://github.com/organicmaps/organicmaps) (`libs/kml/serdes_binary.cpp`,
`libs/coding/text_storage.hpp`, Apache 2.0). This project is an independent Python implementation
and contains no Organic Maps code. MAPS.ME is a trademark of its owners; this tool is not affiliated
with them.

## License

MIT - see [LICENSE](../LICENSE).
