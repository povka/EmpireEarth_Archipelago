"""PKWARE Data Compression Library "implode" decompressor (DCL explode).

Empire Earth stores nearly everything in data.ssa as DCL-imploded blobs behind
a small `PK01` header, which is why only a couple of dozen RIFF chunks are
visible in a 155 MB archive. Python has no decoder for this, so this is a
port of Mark Adler's public-domain blast.c.

    from blast import blast
    raw = blast(compressed_bytes)
"""

from __future__ import annotations

MAXBITS = 13

# Bit lengths in PKWARE's compact run-length form: each byte encodes
# (repeat - 1) in the high nibble and (length) in the low nibble.
LITLEN = bytes([
    11, 124, 8, 7, 28, 7, 188, 13, 76, 4, 10, 8, 12, 10, 12, 10, 8, 23, 8, 9,
    7, 6, 7, 8, 7, 6, 55, 8, 23, 24, 12, 11, 7, 9, 11, 12, 6, 7, 22, 5, 7, 24,
    6, 11, 9, 6, 7, 22, 7, 11, 38, 7, 9, 8, 25, 11, 8, 11, 9, 12, 8, 12, 5, 38,
    5, 38, 5, 11, 7, 5, 6, 21, 6, 10, 53, 8, 7, 24, 10, 27, 44, 253, 253, 253,
    252, 252, 252, 13, 12, 45, 12, 45, 12, 61, 12, 45, 44, 173,
])
LENLEN = bytes([2, 35, 36, 53, 38, 23])
DISTLEN = bytes([2, 20, 53, 230, 247, 151, 248])

LEN_BASE = [3, 2, 4, 5, 6, 7, 8, 9, 10, 12, 16, 24, 40, 72, 136, 264]
LEN_EXTRA = [0, 0, 0, 0, 0, 0, 0, 0, 1, 2, 3, 4, 5, 6, 7, 8]


class Huffman:
    __slots__ = ("count", "symbol")

    def __init__(self, rep: bytes):
        # Expand the compact representation into per-symbol bit lengths.
        lengths = []
        for b in rep:
            repeat = (b >> 4) + 1
            lengths.extend([b & 15] * repeat)

        self.count = [0] * (MAXBITS + 1)
        for ln in lengths:
            self.count[ln] += 1

        offs = [0] * (MAXBITS + 1)
        for i in range(1, MAXBITS):
            offs[i + 1] = offs[i] + self.count[i]
        self.symbol = [0] * len(lengths)
        for sym, ln in enumerate(lengths):
            if ln:
                self.symbol[offs[ln]] = sym
                offs[ln] += 1


class _State:
    __slots__ = ("data", "pos", "bitbuf", "bitcnt", "out")

    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0
        self.bitbuf = 0
        self.bitcnt = 0
        self.out = bytearray()

    def bits(self, need: int) -> int:
        val = self.bitbuf
        while self.bitcnt < need:
            if self.pos >= len(self.data):
                raise ValueError("out of input")
            val |= self.data[self.pos] << self.bitcnt
            self.pos += 1
            self.bitcnt += 8
        self.bitbuf = val >> need
        self.bitcnt -= need
        return val & ((1 << need) - 1)

    def decode(self, h: Huffman) -> int:
        """Decode one symbol. PKWARE stores codes inverted, hence the ^ 1."""
        code = first = index = 0
        length = 1
        bitbuf = self.bitbuf
        left = self.bitcnt
        while True:
            while left:
                left -= 1
                code |= (bitbuf & 1) ^ 1
                bitbuf >>= 1
                count = h.count[length]
                if code < first + count:
                    self.bitbuf = bitbuf
                    self.bitcnt = (self.bitcnt - length) & 7
                    return h.symbol[index + (code - first)]
                index += count
                first += count
                first <<= 1
                code <<= 1
                length += 1
                if length > MAXBITS:
                    raise ValueError("bad code")
            left = (MAXBITS + 1) - length
            if left == 0:
                raise ValueError("bad code")
            if self.pos >= len(self.data):
                raise ValueError("out of input")
            bitbuf = self.data[self.pos]
            self.pos += 1
            if left > 8:
                left = 8


_LITCODE = Huffman(LITLEN)
_LENCODE = Huffman(LENLEN)
_DISTCODE = Huffman(DISTLEN)


def blast(data: bytes) -> bytes:
    """Decompress a raw DCL-imploded stream (starting at the 2-byte header)."""
    s = _State(data)
    lit = s.bits(8)
    if lit > 1:
        raise ValueError(f"bad literal flag {lit}")
    dict_bits = s.bits(8)
    if not 4 <= dict_bits <= 6:
        raise ValueError(f"bad dictionary size {dict_bits}")

    out = s.out
    while True:
        if s.bits(1):
            # length / distance pair
            sym = s.decode(_LENCODE)
            length = LEN_BASE[sym] + s.bits(LEN_EXTRA[sym])
            if length == 519:
                break                      # end of stream
            shift = 2 if length == 2 else dict_bits
            dist = s.decode(_DISTCODE) << shift
            dist += s.bits(shift)
            dist += 1
            if dist > len(out):
                raise ValueError("distance before start of output")
            start = len(out) - dist
            for i in range(length):
                out.append(out[start + i])
        else:
            out.append(s.decode(_LITCODE) if lit else s.bits(8))
    return bytes(out)


def unpack_pk01(blob: bytes) -> bytes:
    """Decompress an Empire Earth `PK01` blob, or return it unchanged.

    Layout: 'PK01', u32 uncompressed size, 4 reserved bytes, then the DCL
    stream. Entries that are not PK01 are stored raw.
    """
    if blob[:4] != b"PK01":
        return blob
    import struct

    (size,) = struct.unpack_from("<I", blob, 4)
    raw = blast(blob[12:])
    if size and len(raw) != size:
        raise ValueError(f"expected {size} bytes, produced {len(raw)}")
    return raw


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 3:
        raise SystemExit("usage: blast.py <packed> <out>")
    data = open(sys.argv[1], "rb").read()
    out = unpack_pk01(data)
    open(sys.argv[2], "wb").write(out)
    print(f"{len(data):,} -> {len(out):,} bytes, head={out[:4]!r}")
