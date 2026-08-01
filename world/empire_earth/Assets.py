"""Pull sound effects out of Empire Earth's `data.ssa` archive.

Entries are DCL-imploded behind a `PK01` header (see Blast.py). Assets are
extracted from the player's own installation on demand and cached next to the
Archipelago data folder - nothing game-owned is shipped with this world.

Archive layout (little-endian), entries starting at offset 16:

    'rass', u32 version, u32 reserved, u32 data-section start
    per entry: u32 name length (including NUL), name, u32 start, u32 end, u32 size
"""

from __future__ import annotations

import os
import struct

try:
    from .Blast import unpack_pk01
except ImportError:  # loaded as a top-level module by tools/
    from Blast import unpack_pk01

# The building-selection click, i.e. what you hear clicking the Capitol.
DEFAULT_SOUND = "sounds\\buildingselect-8.wav"

SEARCH_ROOTS = (
    r"C:\Program Files (x86)\GOG Galaxy\Games\Empire Earth Gold\Empire Earth",
    r"C:\Program Files (x86)\GOG Galaxy\Games\Empire Earth Gold\Empire Earth - The Art of Conquest",
    r"C:\Program Files (x86)\Neo Empire Earth\Empire Earth",
    r"C:\Program Files (x86)\Neo Empire Earth\Empire Earth - The Art of Conquest",
)


def find_archives() -> list[str]:
    out = []
    for root in SEARCH_ROOTS:
        p = os.path.join(root, "Data", "data.ssa")
        if os.path.exists(p):
            out.append(p)
    return out


def entries(path: str):
    """Yield (name, start, size) for every entry of an SSA archive."""
    with open(path, "rb") as f:
        data = f.read()
    if data[:4] != b"rass":
        return
    pos, n = 16, len(data)
    while pos + 4 <= n:
        (name_len,) = struct.unpack_from("<I", data, pos)
        pos += 4
        if name_len == 0 or name_len > 512 or pos + name_len + 12 > n:
            return
        raw = data[pos: pos + name_len]
        pos += name_len
        start, end, size = struct.unpack_from("<III", data, pos)
        pos += 12
        if size != end - start + 1:
            return
        yield raw.rstrip(b"\x00").decode("latin-1"), start, size


def extract(archive: str, name: str) -> bytes | None:
    target = name.lower()
    for entry, start, size in entries(archive):
        if entry.lower() == target:
            with open(archive, "rb") as f:
                f.seek(start)
                blob = f.read(size)
            try:
                return unpack_pk01(blob)
            except Exception:
                return None
    return None


def ensure_sound(dest_dir: str, name: str = DEFAULT_SOUND,
                 filename: str = "buildingselect.wav") -> str | None:
    """Return a path to the extracted WAV, extracting it once if needed."""
    dest = os.path.join(dest_dir, filename)
    if os.path.exists(dest) and os.path.getsize(dest) > 64:
        return dest
    for archive in find_archives():
        raw = extract(archive, name)
        if raw and raw[:4] == b"RIFF":
            try:
                os.makedirs(dest_dir, exist_ok=True)
                with open(dest, "wb") as f:
                    f.write(raw)
                return dest
            except OSError:
                return None
    return None


if __name__ == "__main__":
    import sys

    dest = sys.argv[1] if len(sys.argv) > 1 else "."
    print("archives:", find_archives())
    print("sound ->", ensure_sound(dest))
