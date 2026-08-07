"""List and extract files from Empire Earth's `data.ssa` archives.

Format (little-endian), starting after an 8-byte header:

    magic  'rass'
    u32    version (1)
    u32    reserved
    u32    start of the data section (= end of the name table)
    repeated entries, from offset 16:
        u32   name length, including the trailing NUL
        char  name[name length]
        u32   start offset in the file
        u32   end offset (inclusive)
        u32   size  (== end - start + 1)

    py tools\\ssa_extract.py --list sounds
    py tools\\ssa_extract.py --extract "sounds\\buildingselect-8.wav" --out C:\\path\\out.wav
"""

from __future__ import annotations

import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from install import DEFAULT_EDITION, EDITIONS, data_ssa  # noqa: E402

# Art of Conquest unless asked otherwise; `base` is the original game's, kept
# for the base-game support that is still to come. See install.EDITIONS.
DEFAULT_SSA = data_ssa()
SSA_BY_EDITION = {name: data_ssa(edition=name) for name in EDITIONS}


def parse(path: str):
    """Yield (name, start, size) for every entry in the archive."""
    with open(path, "rb") as f:
        data = f.read()
    if data[:4] != b"rass":
        raise SystemExit(f"{path} is not an SSA archive")
    pos = 16
    n = len(data)
    while pos + 4 <= n:
        (name_len,) = struct.unpack_from("<I", data, pos)
        pos += 4
        if name_len == 0 or name_len > 512 or pos + name_len + 12 > n:
            break
        raw = data[pos: pos + name_len]
        pos += name_len
        start, end, size = struct.unpack_from("<III", data, pos)
        pos += 12
        name = raw.rstrip(b"\x00").decode("latin-1")
        if size != end - start + 1:
            # Table ended or we lost sync; stop rather than emit garbage.
            break
        yield name, start, size


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--edition", choices=sorted(EDITIONS),
                    default=DEFAULT_EDITION,
                    help="which edition's archive to read")
    ap.add_argument("--ssa", help="an explicit path, overriding --edition")
    ap.add_argument("--list", nargs="?", const="", help="list entries containing this text")
    ap.add_argument("--extract", help="exact entry name to extract")
    ap.add_argument("--out", help="destination path")
    ap.add_argument("--raw", action="store_true",
                    help="write the stored bytes without PK01 decompression")
    args = ap.parse_args()

    ssa = args.ssa or SSA_BY_EDITION[args.edition]
    entries = list(parse(ssa))
    print(f"{len(entries)} entries in {ssa}")

    if args.list is not None:
        needle = args.list.lower()
        shown = 0
        for name, start, size in entries:
            if needle in name.lower():
                print(f"  {name:<48s} @0x{start:08X}  {size:>9,d} bytes")
                shown += 1
                if shown >= 200:
                    print("  ...")
                    break
        if not shown:
            print("  (nothing matched)")
        return

    if args.extract:
        target = args.extract.lower()
        for name, start, size in entries:
            if name.lower() == target:
                with open(ssa, "rb") as f:
                    f.seek(start)
                    blob = f.read(size)
                packed = len(blob)
                if not args.raw:
                    from blast import unpack_pk01

                    try:
                        blob = unpack_pk01(blob)
                    except Exception as e:
                        print(f"warning: could not decompress ({e}); writing raw")
                out = args.out or os.path.basename(name)
                os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
                with open(out, "wb") as f:
                    f.write(blob)
                kind = "RIFF/WAVE" if blob[:4] == b"RIFF" else f"head={blob[:4]!r}"
                grew = f"{packed:,} -> " if len(blob) != packed else ""
                print(f"extracted {name} -> {out}  {grew}{len(blob):,} bytes, {kind}")
                return
        sys.exit(f"no entry named {args.extract!r}")

    ap.print_help()


if __name__ == "__main__":
    main()
 