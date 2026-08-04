"""Find an Empire Earth installation, whichever store it came from.

The GOG and Steam releases ship the *same* game: `Language.dll`,
`Low-Level Engine.dll`, `Default.dll` and both `data.ssa` archives are
byte-identical, and every PE section of `EE-AOC.exe` matches too. The Steam
executable is only 15,720 bytes larger, all of it appended outside the sections
- a signature or store wrapper. So every address, string id and generated table
in this project is valid for both, and the tools should not care which one they
are pointed at.

Override with the EE_ROOT environment variable if your install is somewhere
this does not guess:

    set EE_ROOT=D:\\Games\\Empire Earth Gold
"""

from __future__ import annotations

import os

# Checked in order. The first that looks like an install wins.
CANDIDATE_ROOTS = [
    os.environ.get("EE_ROOT", ""),
    r"C:\Empire Earth Gold - GOG",
    r"C:\Empire Earth Gold - Steam",
    r"C:\Empire Earth Gold",
    r"C:\Program Files (x86)\GOG Galaxy\Games\Empire Earth Gold",
    r"C:\Program Files (x86)\Steam\steamapps\common\Empire Earth Gold",
    r"C:\Program Files\Steam\steamapps\common\Empire Earth Gold",
    r"D:\SteamLibrary\steamapps\common\Empire Earth Gold",
]

AOC = "Empire Earth - The Art of Conquest"
BASE = "Empire Earth"


def _looks_like_install(root: str) -> bool:
    return bool(root) and os.path.isfile(os.path.join(root, AOC, "EE-AOC.exe"))


def find_root(explicit: str = "") -> str:
    """The install root. Raises with a useful message if there is none."""
    if explicit:
        if _looks_like_install(explicit):
            return explicit
        raise SystemExit(f"not an Empire Earth install: {explicit}")
    for root in CANDIDATE_ROOTS:
        if _looks_like_install(root):
            return root
    raise SystemExit(
        "No Empire Earth install found. Looked in:\n  "
        + "\n  ".join(r for r in CANDIDATE_ROOTS if r)
        + "\nSet EE_ROOT to point at yours."
    )


def aoc_exe(root: str = "") -> str:
    return os.path.join(find_root(root), AOC, "EE-AOC.exe")


def base_exe(root: str = "") -> str:
    return os.path.join(find_root(root), BASE, "Empire Earth.exe")


def language_dll(root: str = "") -> str:
    return os.path.join(find_root(root), AOC, "Language.dll")


def engine_dll(root: str = "") -> str:
    return os.path.join(find_root(root), AOC, "Low-Level Engine.dll")


def data_ssa(root: str = "", aoc: bool = False) -> str:
    """The archive holding the object database and assets.

    The base game's is the big one and is what the object tables were generated
    from; the Art of Conquest folder has a smaller one of its own.
    """
    return os.path.join(find_root(root), AOC if aoc else BASE, "Data", "data.ssa")


if __name__ == "__main__":
    root = find_root()
    print(f"install root : {root}")
    for label, path in (("AoC exe", aoc_exe()), ("Language.dll", language_dll()),
                        ("engine dll", engine_dll()), ("data.ssa", data_ssa())):
        size = os.path.getsize(path) if os.path.exists(path) else None
        print(f"  {label:13s} {path}"
              + (f"   ({size:,} bytes)" if size else "   MISSING"))
