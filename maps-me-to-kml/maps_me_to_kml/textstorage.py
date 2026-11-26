"""Compressed string storage of KMB files (Organic Maps / MAPS.ME `coding::BlockedTextStorage`).

Layout of the strings section:
    uint64 LE   offset of the block index (from the start of the section)
    blocks...   each: varuint lengths of its strings, then one BWT block
    index:      varuint number of blocks, then per block: varuint offset delta, varuint string count

A BWT block is: varuint start, Huffman table, Huffman-coded move-to-front bytes; decoding reverses
Huffman -> move-to-front -> Burrows-Wheeler transform.
"""

from __future__ import annotations

import bisect
import struct

from .reader import Source


class BitReader:
    """LSB-first bit reader (as coding::BitReader)."""

    def __init__(self, src: Source):
        self.src = src
        self.buf = 0
        self.bits = 0

    def bit(self) -> int:
        if self.bits == 0:
            self.buf = self.src.u8()
            self.bits = 8
        b = self.buf & 1
        self.buf >>= 1
        self.bits -= 1
        return b


def _huffman_decode(src: Source) -> bytes:
    # table: count, then (code bits, code length, symbol); code bit j is read j-th (LSB first)
    tree: dict = {}
    for _ in range(src.varuint()):
        bits, length, symbol = src.varuint(), src.varuint(), src.varuint()
        node = tree
        for j in range(length):
            node = node.setdefault((bits >> j) & 1, {})
        node["sym"] = symbol
    br = BitReader(src)
    count = src.varuint()  # read from the stream before the first bit
    out = bytearray()
    for _ in range(count):
        node = tree
        while "sym" not in node:
            node = node[br.bit()]
        out.append(node["sym"])
    return bytes(out)


def _move_to_front_decode(data: bytes) -> bytes:
    order = list(range(256))
    out = bytearray()
    for i in data:
        b = order[i]
        out.append(b)
        del order[i]
        order.insert(0, b)
    return bytes(out)


def _reverse_bwt(start: int, s: bytes) -> bytes:
    """Inverse BWT with an implicit end-of-string sentinel (port of coding::RevBWT)."""
    n = len(s)
    if n == 0:
        return b""
    counts = [0] * 256
    for c in s:
        counts[c] += 1
    starts, off = [0] * 256, 0
    for i in range(256):
        starts[i], off = off, off + counts[i]

    def first(i: int) -> int:  # first column, index 0 = sentinel
        if i == 0:
            return 256
        return bisect.bisect_right(starts, i - 1) - 1

    def rank(i: int) -> int:
        if i == 0:
            return 0
        i -= 1
        k = bisect.bisect_right(starts, i) - 1
        return i - starts[k]

    def last(i: int) -> int:  # last column
        if i == 0:
            return s[start]
        if i == start + 1:
            return 256
        return s[i - 1]

    table: list[list[int]] = [[] for _ in range(256)]
    for i in range(n + 1):
        b = last(i)
        if b != 256:
            table[b].append(i)

    out = bytearray()
    curr = start + 1
    for _ in range(n):
        b = first(curr)
        out.append(b)
        curr = table[b][rank(curr)]
    return bytes(out)


def decode_bwt_block(src: Source) -> bytes:
    start = src.varuint()
    data = _move_to_front_decode(_huffman_decode(src))
    if data and start >= len(data):
        raise ValueError("corrupt BWT block")
    return _reverse_bwt(start, data)


class TextStorage:
    """All strings of a KMB file, by index."""

    def __init__(self, section: bytes):
        self.strings: list[str] = []
        if len(section) < 8:
            return
        (index_offset,) = struct.unpack_from("<Q", section, 0)
        idx = Source(section, index_offset)
        blocks, prev = [], 8
        for _ in range(idx.varuint()):
            prev += idx.varuint()
            blocks.append((prev, idx.varuint()))
        for offset, subs in blocks:
            src = Source(section, offset)
            lengths = [src.varuint() for _ in range(subs)]
            value = decode_bwt_block(src)
            pos = 0
            for ln in lengths:
                self.strings.append(value[pos:pos + ln].decode("utf-8", "replace"))
                pos += ln

    def get(self, i: int) -> str:
        return self.strings[i] if 0 <= i < len(self.strings) else ""
