"""Find an Empire Earth installation, whichever store it came from.

The GOG and Steam releases ship the *same* game. `Language.dll`,
`Low-Level Engine.dll`, `Default.dll` and both `data.ssa` archives are
byte-identical, and every PE section of `EE-AOC.exe` matches too. The Steam
executable is only 15,720 bytes larger, all of it appended outside the
sections — a signature or store wrapper. So every address, string id and
generated table in this project is valid for both, and the tools don't care
which one you point them at.

Override with the `EE_ROOT` environment variable when your install is somewhere
this doesn't guess:

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

# The two editions ship a `data.ssa` each, in their own folder. They aren't
# versions of one file — each is the database for its own executable — so which
# one a tool reads has to be a decision, not a default nobody looked at.
EDITIONS = {
    "aoc": AOC,
    "base": BASE,
}

# Art of Conquest. The client attaches to `EE-AOC.exe`, the world offers the
# Space Age as a goal, and the Space Age is an Art of Conquest epoch, so this is
# the edition the project describes.
#
# Reading the base game's by default was a real bug. Its archive is four times
# the size (163 MB against 45 MB) because it carries the shared assets, which
# made it look like the complete one, but its object database is the smaller of
# the two — 724 records against 848. Everything the expansion adds went missing
# from the generated tables: `Inf15 - Watchman`, `Inf15 - Cyber Ninja`, five
# kinds of spaceship, the Space Dock, the Teleporter, and the Orbital Space
# Station wonder. A Space Age seed contained no Space Age content.
#
# `base` stays here rather than being deleted — supporting the original game is
# on the roadmap, and it needs its own tables generated from its own database.
DEFAULT_EDITION = "aoc"


def _looks_like_install(root: str) -> bool:
    return bool(root) and os.path.isfile(os.path.join(root, AOC, "EE-AOC.exe"))


def find_root(explicit: str = "") -> str:
    """The install root. Raises with a useful message when there's none."""
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


def data_ssa(root: str = "", edition: str = DEFAULT_EDITION) -> str:
    """The archive holding an edition's object database and assets.

    Defaults to Art of Conquest. Pass `edition="base"` for the original game.
    See `EDITIONS` above for why this is a choice rather than a default.
    """
    folder = EDITIONS.get(edition)
    if folder is None:
        raise SystemExit(
            f"unknown edition {edition!r}; expected one of "
            f"{', '.join(sorted(EDITIONS))}"
        )
    return os.path.join(find_root(root), folder, "Data", "data.ssa")


if __name__ == "__main__":
    root = find_root()
    print(f"install root : {root}")
    for label, path in (("AoC exe", aoc_exe()), ("Language.dll", language_dll()),
                        ("engine dll", engine_dll()), ("data.ssa", data_ssa())):
        size = os.path.getsize(path) if os.path.exists(path) else None
        print(f"  {label:13s} {path}"
              + (f"   ({size:,} bytes)" if size else "   MISSING"))
