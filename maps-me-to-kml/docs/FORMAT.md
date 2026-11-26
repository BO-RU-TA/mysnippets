# MAPS.ME KMB format 10

What `maps_me_to_kml` reads. Integers are little-endian. `varuint` is base-128 (7 bits per byte,
high bit = more bytes follow); `varint` is a zig-zag encoded `varuint`.

## File

| Bytes | Content |
|---|---|
| 1 | format, `0x0A` |
| 1 | coordinate precision in bits (30 in all known files) |
| 40 | five `uint64` section offsets, relative to the byte after the two above: category, bookmarks, tracks, strings, end |

The category section starts right after the offsets (offset 40). The end offset equals the size of
the rest of the file.

## Values

- **Point**: two `varuint` (x, y) in a 0..2^bits-1 grid over the Organic Maps Mercator square
  (x and y both -180..180). `lon = x`, `lat = degrees(2 * atan(tanh(radians(y) / 2)))`.
- **Time**: `varuint` seconds since 1970; "maybe milliseconds" fields hold milliseconds unless the
  value is between 10^9 and 10^12.
- **Colour**: `uint8` predefined colour + `uint32` RGBA (0xRRGGBBAA, 0 = use the predefined one).
- **String index**: `varuint` slot count, then per slot `varuint` entry count and entries
  `int8` language + `varuint` string number (0 = empty). Language 0 is the default one.

## Category

`uint64` id, `uint8` visible, `uint8` 0, `varuint` last modified (ms), `uint8` 0, string index with
5 slots: name, description, 3 unused.

## Bookmarks

`varuint` count, then per bookmark: `uint64` id, `varuint` count + `uint32` feature types, colour,
`uint16` icon, `uint8` viewport scale, `varuint` created (ms), point, `uint8` visible, `uint8` 0,
`varuint` second time (ms; modification/sync), string index with 5 slots: name, description, custom
name, 2 unused.

## Tracks

`varuint` count, then per track:

| Field | Encoding |
|---|---|
| id | `uint64` |
| local id | `uint8` |
| layers | `varuint` count; per layer: width as `varuint` in a 0..2^bits-1 grid over 0..100, colour |
| time | `varuint` seconds |
| geometry | `varuint` line count; per line: `varuint` point count, points as `varint` deltas of x and y from the previous point (starting at 0,0), then `varint` altitude deltas in metres (starting at 0) |
| visible | `uint8` |
| unknown | `uint8` 0 |
| point times | `varuint` count, each `varuint` = (milliseconds << 7) \| flags |
| unknown | `uint8` 0 |
| second time | `varuint` (ms). Organic Maps' reader expects a zero byte here; real MAPS.ME files store a time |
| strings | string index with 4 slots: name, description, 2 unused |

A single point time on a track with more points is a document time, not a per-point time.

## Strings

All texts are in one compressed storage at the strings offset:

1. `uint64` offset of the block index (from the start of the section).
2. Blocks. Each: `varuint` length of every string in the block, then one compressed block.
3. Index: `varuint` block count; per block `varuint` offset delta (first block relative to 8) and
   `varuint` string count.

A compressed block is a Burrows-Wheeler transform, move-to-front, then Huffman coding:

1. `varuint` BWT start (row of the original string).
2. Huffman table: `varuint` symbol count; per symbol `varuint` code bits, `varuint` code length,
   `varuint` symbol. Bit *j* of a code is read *j*-th.
3. `varuint` number of symbols, then the code bits, least significant bit of each byte first.
4. Undo move-to-front (start order 0..255), then the BWT with an implicit end-of-string marker
   (see `coding::RevBWT` in Organic Maps).

String numbers are global across blocks, starting at 0.
