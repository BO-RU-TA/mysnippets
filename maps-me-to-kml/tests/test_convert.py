import sys, os
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import io
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile
from contextlib import redirect_stdout
from pathlib import Path

from maps_me_to_kml import KmbError, read_kmb, to_kml
from maps_me_to_kml.cli import main
from maps_me_to_kml.reader import Source
from maps_me_to_kml.textstorage import TextStorage, _reverse_bwt

from kmb_builder import Kmb, bwt, text_storage, varint, varuint

NS = {"k": "http://www.opengis.net/kml/2.2", "gx": "http://www.google.com/kml/ext/2.2"}


def sample() -> bytes:
    k = Kmb("Tenerife trip", "Generated for tests")
    k.bookmark("Plaza de la Constitución", 28.39094, -16.52291, "Main square", created_ms=1_601_471_892_000)
    k.bookmark("Teide", 28.27240, -16.64250)
    k.track("Chinyero loop", [(28.2842, -16.76181, 1300), (28.2851, -16.7630, 1320), (28.2860, -16.7642, 1310)],
            times_s=[1_601_471_000, 1_601_471_060, 1_601_471_120])
    return k.build()


class Encodings(unittest.TestCase):
    def test_varints(self):
        for v in (0, 1, 127, 128, 300, 2**40):
            self.assertEqual(Source(varuint(v)).varuint(), v)
        for v in (0, -1, 1, -64, 64, -100000):
            self.assertEqual(Source(varint(v)).varint(), v)

    def test_reverse_bwt(self):
        for s in (b"banana", b"a", b"mississippi river", "zażółć gęślą jaźń".encode()):
            start, t = bwt(s)
            self.assertEqual(_reverse_bwt(start, t), s)

    def test_text_storage(self):
        strings = ["", "Track 20251010-160855", "Zakładki", "Distance = 56,1 km<br>Duration = 02:55:27"]
        self.assertEqual(TextStorage(text_storage(strings)).strings, strings)


class Decode(unittest.TestCase):
    def test_file(self):
        k = read_kmb(sample())
        self.assertEqual(k.name, "Tenerife trip")
        self.assertEqual(k.description, "Generated for tests")
        self.assertEqual([b.name for b in k.bookmarks], ["Plaza de la Constitución", "Teide"])
        self.assertAlmostEqual(k.bookmarks[0].lat, 28.39094, places=5)
        self.assertAlmostEqual(k.bookmarks[0].lon, -16.52291, places=5)
        self.assertEqual(k.bookmarks[0].created.year, 2020)
        t = k.tracks[0]
        self.assertEqual(t.name, "Chinyero loop")
        self.assertEqual([p[2] for p in t.lines[0]], [1300, 1320, 1310])
        self.assertAlmostEqual(t.lines[0][-1][0], 28.2860, places=5)
        self.assertEqual(len(t.point_times), 3)

    def test_rejects_other_formats(self):
        with self.assertRaises(KmbError):
            read_kmb(bytes([9, 30]) + bytes(60))

    def test_kml(self):
        root = ET.fromstring(to_kml(read_kmb(sample())).encode())
        names = [n.text for n in root.iter("{%s}name" % NS["k"])]
        self.assertIn("Teide", names)
        self.assertEqual(len(root.findall(".//gx:Track/gx:coord", NS)), 3)
        coords = root.find(".//k:Point/k:coordinates", NS).text
        lon, lat = map(float, coords.split(","))
        self.assertAlmostEqual(lat, 28.39094, places=5)


class Cli(unittest.TestCase):
    def test_folder_zip_merge(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d, "bookmarks")
            src.mkdir()
            (src / "Trip.kmb").write_bytes(sample())
            (src / "broken.kmb").write_bytes(b"\x0a\x1e garbage")
            out = io.StringIO()
            with redirect_stdout(out):
                code = main([str(src), "-o", str(Path(d, "kml")), "--zip", str(Path(d, "all.zip")),
                             "--merge", str(Path(d, "all.kml")), "-q"])
            self.assertEqual(code, 1)                      # one file failed
            self.assertIn("converted 1 of 2 files", out.getvalue())
            self.assertTrue(Path(d, "kml", "Trip.kml").is_file())
            self.assertEqual(zipfile.ZipFile(Path(d, "all.zip")).namelist(), ["Trip.kml"])
            ET.parse(Path(d, "all.kml"))                   # merged file is valid XML


if __name__ == "__main__":
    unittest.main()
