"""Byte reader with the integer encodings used by KMB files."""

from __future__ import annotations

import struct


class Source:
    def __init__(self, data: bytes, pos: int = 0, end: int | None = None):
        self.data = data
        self.pos = pos
        self.end = len(data) if end is None else end

    def remaining(self) -> int:
        return self.end - self.pos

    def take(self, n: int) -> bytes:
        if self.pos + n > self.end:
            raise EOFError("unexpected end of data")
        b = self.data[self.pos:self.pos + n]
        self.pos += n
        return b

    def u8(self) -> int:
        return self.take(1)[0]

    def i8(self) -> int:
        return struct.unpack("<b", self.take(1))[0]

    def u16(self) -> int:
        return struct.unpack("<H", self.take(2))[0]

    def u32(self) -> int:
        return struct.unpack("<I", self.take(4))[0]

    def u64(self) -> int:
        return struct.unpack("<Q", self.take(8))[0]

    def varuint(self) -> int:
        """Little-endian base-128 varint (7 bits per byte, high bit = continuation)."""
        result, shift = 0, 0
        while True:
            b = self.u8()
            result |= (b & 0x7F) << shift
            if not b & 0x80:
                return result
            shift += 7
            if shift > 70:
                raise ValueError("varint too long")

    def varint(self) -> int:
        """Zig-zag encoded signed varint."""
        v = self.varuint()
        return (v >> 1) ^ -(v & 1)
