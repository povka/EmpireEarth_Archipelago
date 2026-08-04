"""Parse Empire Earth's object database (db\\dbobjects.dat).

Layout: u32 count, u32 reserved, then `count` fixed-size records. The record
size is derived from the file rather than hardcoded, so it stays correct for
both the base game and Art of Conquest.

    py tools\\dbobjects.py --families
    py tools\\dbobjects.py --list Barracks
    py tools\\dbobjects.py --layout
"""

from __future__ import annotations

import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from blast import unpack_pk01  # noqa: E402
from ssa_extract import DEFAULT_SSA, parse  # noqa: E402


def load(ssa: str, member: str) -> bytes:
    for name, start, size in parse(ssa):
        if name.lower() == member.lower():
            with open(ssa, "rb") as f:
                f.seek(start)
                blob = f.read(size)
            return unpack_pk01(blob)
    raise SystemExit(f"{member} not found in {ssa}")


def families(ssa: str) -> list[str]:
    d = load(ssa, "db\\dbfamily.dat")
    (count,) = struct.unpack_from("<I", d, 0)
    rec = (len(d) - 4) // count
    out = []
    for i in range(count):
        raw = d[4 + i * rec: 4 + (i + 1) * rec]
        out.append(raw.split(b"\x00")[0].decode("latin-1"))
    return out


def objects(ssa: str):
    """Yield (index, record_bytes) for every object."""
    # u32 count, then `count` fixed records. 4 + 724*1948 == file size exactly.
    d = load(ssa, "db\\dbobjects.dat")
    (count,) = struct.unpack_from("<I", d, 0)
    rec = (len(d) - 4) // count
    for i in range(count):
        off = 4 + i * rec
        yield i, d[off: off + rec], rec


def record_name(rec: bytes) -> str:
    """The internal name, stored at the start of each record."""
    return rec.split(b"\x00")[0].decode("latin-1", "replace")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ssa", default=DEFAULT_SSA)
    ap.add_argument("--families", action="store_true")
    ap.add_argument("--list", nargs="?", const="")
    ap.add_argument("--layout", action="store_true")
    ap.add_argument("--limit", type=int, default=40)
    args = ap.parse_args()

    if args.families:
        fam = families(args.ssa)
        print(f"{len(fam)} families")
        for i, f in enumerate(fam):
            print(f"  {i:3d}  {f}")
        return

    recs = list(objects(args.ssa))
    if not recs:
        return
    print(f"{len(recs)} objects, record size {recs[0][2]} bytes")

    if args.layout:
        # Show the first record's leading fields to locate name and ids.
        i, rec, size = recs[0]
        print(f"\nrecord 0: name={record_name(rec)!r}")
        print("  first 0x80 bytes:")
        for off in range(0, 0x80, 16):
            row = rec[off:off + 16]
            txt = "".join(chr(b) if 32 <= b < 127 else "." for b in row)
            print(f"   +0x{off:03X}  " + " ".join(f"{b:02X}" for b in row) + f"  {txt}")
        return

    if args.list is not None:
        needle = args.list.lower()
        shown = 0
        for i, rec, _size in recs:
            name = record_name(rec)
            if needle and needle not in name.lower():
                continue
            print(f"  {i:4d}  {name}")
            shown += 1
            if shown >= args.limit:
                print("  ...")
                break
        if not shown:
            print("  (nothing matched)")
        return

    ap.print_help()


if __name__ == "__main__":
    main()
