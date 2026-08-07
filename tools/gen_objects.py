"""Generate world/empire_earth/Objects.py from the game's own database.

Reads `data.ssa`'s object records and writes out the buildings, units, unit
families and wonders the world builds its checks from.

    python tools/gen_objects.py            # print what it would emit
    python tools/gen_objects.py --write

Buildings are listed by exact type, restricted to those with no epoch-specific
variants. Guard Towers, Walls and Gates come in per-epoch flavours that stop
being buildable when you advance, so they are left out.

Units are emitted twice over, because both views are needed:

* `UNIT_FAMILY_BY_NAME` maps every unit to its family. Checks are per unit
  now, but a family is still what says where a unit is produced
  (`Producers.py`) and which epoch it belongs to, so the grouping has not gone
  away - only the checks built on it have.
* `UNIT_FAMILIES` and `UNIT_FAMILY_MIN_EPOCH` are that grouping.

Reads the Art of Conquest database by default, because that is the edition the
client attaches to and the Space Age is an expansion epoch. `--edition base`
reads the original game's instead; the two ship a `data.ssa` each and the
expansion's holds 848 object records against 724. See install.EDITIONS.

Epochs need care. The database's field counts from 1 where this project counts
from 0, and it reads high for buildings - one for most, two for the Temple - so
`BuildingEpochs.py`, generated from the running game's tech tree, overrides it
and a building with no measured epoch is not offered as a check at all. Unit
epochs are corrected here instead; see unit_epoch.
"""

from __future__ import annotations

import argparse
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dbobjects import families, objects, record_name  # noqa: E402
from ssa_extract import DEFAULT_SSA, SSA_BY_EDITION  # noqa: E402
from install import DEFAULT_EDITION, EDITIONS  # noqa: E402

FAMILY_OFF = 0x68
# Category, and the earliest epoch the object can be built in. There is no
# corresponding "last epoch" field: things like Guard Tower - Paleo stop being
# buildable because a later variant supersedes them by name, not by data.
CATEGORY_OFF = 0x6C
MIN_EPOCH_OFF = 0x70
WONDER_CATEGORY = 28

# Wonders take the same one-indexed correction as everything else, and then a
# floor on top. Leaving the raw number in place put `Orbital Space Station` at
# epoch 15 - one past the Space Age - so no seed could offer it, and it was
# reported built in a Space Age match.
#
# The floor is the part that is not an off-by-one. It reads 1
# (Stone Age) for six of the seven, but wonders cannot actually be built until
# the Bronze Age. Established in game, not guessed:
#
#   start in Copper Age  -> no wonder buttons
#   advance to Bronze    -> they appear
#   start in Middle Ages -> available immediately
#
# The last case rules out "one epoch after you started" and pins it to a fixed
# floor. No per-object field carries it - searching for one that reads 3 for
# every early wonder finds only the family id, which is 3 for "Building" by
# coincidence - so the rule lives somewhere else in the engine and this is
# applied on top of the database value.
WONDER_EPOCH_FLOOR = 3

OUT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "world", "empire_earth", "Objects.py",
)

# Buildings whose name carries an epoch or is otherwise a variant: excluded,
# because they stop being buildable when you advance.
BUILDING_EXCLUDE_MARKERS = (
    " - paleo", " - copper", " - bronze", " - middle", " - imperial",
    " - ww1", " - ww2", " - digital", " - nano", " - space",
    "wall", "gate", "barbed", "obstacle", "runway", "improved",
    "aa10", "aa13", "steel mill",
    "iwo jima",
    # The Farm is kept out by choice, not because it is a variant. It is the
    # one building with no tech tree node the client can reach - the only icon
    # mentioning a farm is `but_farm_15t`, an epoch 14 variant - so it can
    # neither be gated nor have its epoch confirmed against the running game
    # the way every other building's is. That leaves its floor coming from
    # `dbobjects.dat` alone, which is the number this project does not trust
    # for buildings.
    "farm",
)

# Families that hold no recruitable unit. Everything else in the database's
# family table is taken, rather than a hand-picked list.
#
# A curated list was right when a check meant "recruit anything in this
# family". Now that every unit has its own check, anything left out simply has
# no check at all - which is how `Inf01 - Rock Thrower` came to be unsendable:
# its family is `Human`, and `Human` was not on the list. Nor were `Hero`,
# `Aircraft Carrier Fighter`, or any of the six `Mech` families.
NON_UNIT_FAMILIES = {
    "No Family", "Resource", "Building", "Animal", "Fish", "Mines",
    "Ambient", "Towers", "Walls",
}

# Families Art of Conquest adds whose producer nothing shipped with the game
# names. `technology_tree.pdf` predates the expansion, so its unit tables have
# no heading for spaceships, and the building they come from - the Space Dock -
# has no measured epoch either, because `gen_building_epochs.py` has only ever
# been run against a base-game tech tree.
#
# Held back rather than guessed at. A wrong producer is the dangerous kind of
# error here: it tells logic that a building you cannot use is good enough, and
# `Producers.py` drops ambiguous labels for exactly that reason.
#
# What it costs is eight checks - three spaceships, three space fighters, a
# space corvette and a campaign ICBM. What admits them is one run of
# `tools/gen_building_epochs.py` against a live Art of Conquest match, plus a
# producer for each family.
NEEDS_MEASUREMENT_FAMILIES = {
    # `cp ICBM` only - a campaign object with no build menu anywhere.
    "ICBM",
}

# Records that sit in a unit family but are abilities rather than units, so
# nothing can ever recruit one and a check for it could never be sent.
# `Hurricane` and `Torpedo` are filed under Ship, `Anti Matter Storm` under
# Helicopter, all three at epoch 0 with 9999 hitpoints.
#
# The family floor already ignored them, because it skips epoch 0 - but the
# per-unit tables did not, so they arrived in Objects.py as recruitable units.
# Excluded here rather than deleted from the generated file by hand: this is
# the only place the exclusion survives a regeneration.
NON_UNIT_NAMES = {
    "Hurricane",
    "Torpedo",
    "Anti Matter Storm",
}



# `Arch02 - Slinger` -> 2, `Inf15 - Watchman` -> 15. The same one-indexed epoch
# the database stores, written into the name.
_NAME_TIER = re.compile(r"^[A-Za-z ]*?(\d+)\s*(?:-\s*)?.+$")


def name_tier(name: str) -> int:
    """The tier in a unit's name, or 0 when it has none to give.

    Deliberately forgiving: `h1-14 Molly Ryan` reads as 1 and `Field Medic 13`
    as nothing at all. Both are wrong, and neither matters, because this is
    only ever used to raise a floor - see unit_epoch.
    """
    match = _NAME_TIER.match(name)
    return int(match.group(1)) if match else 0


def unit_epoch(raw: int, name: str = "") -> int:
    """The database's epoch field, as an index into EPOCH_NAMES.

    The field counts from 1 at the Prehistoric Age; the rest of this project
    counts from 0. The off-by-one is measured, not assumed. `technology_tree.pdf`
    prints an epoch for every unit and building in Roman numerals, and for
    buildings all three sources can be lined up at once:

        Granary   PDF III   database 3   running game's tech tree 2 (Copper Age)

    which is the epoch the game actually offers a Granary in. So the PDF and the
    database share a numbering, and it is one above the tree's. For units the
    database agrees with the PDF for 410 of the 417 rows that name exactly one
    unit, and reads one *high* for the other seven (`Field Medic - Imperial` is
    printed VIII and stored 9) - never one low, so subtracting one can only ever
    over-state an epoch, which costs a check but cannot make a seed unwinnable.

    Leaving the +1 in place is what made `Recruit Cataphract` a Middle Ages
    check when a Cataphract is a Dark Age unit.

    The name's own tier is taken when it is *higher*, and only then. Three
    records added by Art of Conquest store an epoch one below the tier they are
    named for, and the direction is the dangerous one - a floor that reads low
    lets generation hide an epoch item behind a check that needs it:

        Inf15 - Watchman          stored 14, named 15, and the wiki agrees
        14 Anti Missile Battery   stored 13, named 14
        s11 LST Transport         stored 10, named 11

    Taking the higher of the two can only ever over-state an epoch, which is
    the side that costs a check rather than a run. It is also why the tier
    parse is allowed to be sloppy: every name it misreads, it misreads low.
    """
    return max(raw, name_tier(name)) - 1 if max(raw, name_tier(name)) else 0


# Where the database's name is not the game's. `w  Lighthouse at Alexandria`
# is the Pharos Lighthouse - a wonder distinct from the Library of Alexandria,
# which the database also carries - and the display name is what a player reads
# in their item list, so it should be the one the game uses.
DISPLAY_OVERRIDES = {
    "Lighthouse at Alexandria": "Pharos Lighthouse",
}


def pretty(name: str) -> str:
    """'b  Barracks' -> 'Barracks', 'w  Coliseum' -> 'Coliseum'."""
    head, _, rest = name.partition(" ")
    if head in ("b", "w"):
        name = rest
    tidy = " ".join(name.split())
    return DISPLAY_OVERRIDES.get(tidy, tidy)


def wonders(ssa: str):
    """The buildable wonders, as (index, raw name, display name, min epoch).

    Category 28 alone is not enough: it also holds `x RADAR Wonder` and
    `x Lighthouse`, which are scenario props like `x Eiffel Tower` and
    `x Buckingham Palace` rather than anything a skirmish can build. The
    game's own `w ` prefix is what marks a real wonder, so both must agree.
    """
    out = []
    for i, r, _size in objects(ssa):
        name = record_name(r)
        if not name.startswith("w "):
            continue
        if struct.unpack_from("<i", r, CATEGORY_OFF)[0] != WONDER_CATEGORY:
            continue
        epoch = struct.unpack_from("<i", r, MIN_EPOCH_OFF)[0]
        out.append((i, name, pretty(name),
                    max(unit_epoch(epoch, name), WONDER_EPOCH_FLOOR)))
    return sorted(out, key=lambda t: t[1])


def build(ssa: str):
    fam = families(ssa)
    recs = [
        (i, record_name(r), struct.unpack_from("<i", r, FAMILY_OFF)[0])
        for i, r, _ in objects(ssa)
    ]
    recs = [(i, n, f) for i, n, f in recs if n.strip()]

    # Minimum epoch per object, straight from the database. Without it the
    # generator can place a progression item behind a check that needs that
    # very item - Epoch: Bronze Age landed on Build Siege Factory once.
    min_epoch = {}
    for i, r, _ in objects(ssa):
        n = record_name(r)
        if n.strip():
            min_epoch[n] = struct.unpack_from("<i", r, MIN_EPOCH_OFF)[0]

    buildings = []
    for i, n, f in recs:
        if not n.startswith("b "):
            continue
        low = n.lower()
        if any(m in low for m in BUILDING_EXCLUDE_MARKERS):
            continue
        buildings.append((i, n, pretty(n), min_epoch.get(n, 0)))

    unit_families = []
    members: list[tuple[str, str]] = []
    for idx, name in enumerate(fam):
        if name in NON_UNIT_FAMILIES or name in NEEDS_MEASUREMENT_FAMILIES:
            continue
        mine = [
            n for _i, n, f in recs
            if f == idx and not n.startswith("b ") and n not in NON_UNIT_NAMES
        ]
        if not mine:
            continue
        real = [
            (min_epoch.get(n, 0), n) for n in mine
            if min_epoch.get(n, 0) > 0 and not n.startswith("x ")
        ]
        earliest = min(unit_epoch(e, n) for e, n in real) if real else 0
        unit_families.append((idx, name, len(mine), earliest))
        members += [(n, name, unit_epoch(min_epoch.get(n, 0), n)) for n in mine]
    return buildings, unit_families, members


def emit(buildings, unit_families, members, wonder_list) -> str:
    """Emit tables keyed by the database name, which is what the running game
    reports through a unit's type definition - so no id translation is needed."""
    lines = [
        '"""Curated object data, generated by tools/gen_objects.py.',
        "",
        "Do not edit by hand: re-run the generator against db\\\\dbobjects.dat.",
        "",
        "Buildings are exact types with no per-epoch variants, and units are",
        "grouped by family, so every check here stays obtainable for the whole",
        "game rather than expiring when you advance an epoch.",
        "",
        "Keys are the raw database names, exactly as the game reports them at",
        "runtime (see Roster.py), e.g. 'b  Settlement'.",
        '"""',
        "",
        "# database name -> display name",
        "BUILDINGS: dict[str, str] = {",
    ]
    for _i, raw, disp, _e in buildings:
        lines.append(f"    {raw!r}: {disp!r},")
    lines += [
        "}",
        "",
        "# family display names, in database order",
        "UNIT_FAMILIES: tuple[str, ...] = (",
    ]
    for _idx, name, _count, _e in unit_families:
        lines.append(f"    {name!r},")
    lines += [
        ")",
        "",
        "# database name of a unit -> the epoch it can first be recruited in.",
        "#",
        "# Per unit, not per family. A family's floor is its *earliest* member,",
        "# which is far too low for a late one: Cataphract is a Middle Ages",
        "# unit in the Lancer family, whose earliest member is a Copper Age",
        "# Horseman. Using the family's number let generation hide",
        "# `Epoch: Dark Age` behind a check that needs the Middle Ages, and the",
        "# seed could not be finished.",
        "UNIT_MIN_EPOCH: dict[str, int] = {",
    ]
    for raw, _family, epoch in sorted(members):
        lines.append(f"    {raw!r}: {epoch},")
    lines += [
        "}",
        "",
        "# database name of a unit -> the family it counts towards",
        "UNIT_FAMILY_BY_NAME: dict[str, str] = {",
    ]
    for raw, fam, _epoch in sorted(members):
        lines.append(f"    {raw!r}: {fam!r},")
    lines += [
        "}",
        "",
        "# display name -> earliest epoch it can be built in. A check for",
        "# something you cannot build yet must require the epochs that unlock",
        "# it, or generation can hide a progression item behind itself.",
        "BUILDING_MIN_EPOCH: dict[str, int] = {",
    ]
    for _i, _raw, disp, epoch in buildings:
        lines.append(f"    {disp!r}: {epoch},")
    lines += [
        "}",
        "",
        "# family -> earliest epoch any of its members appears in",
        "UNIT_FAMILY_MIN_EPOCH: dict[str, int] = {",
    ]
    for _idx, name, _count, epoch in unit_families:
        lines.append(f"    {name!r}: {epoch},")
    lines += [
        "}",
        "",
        "# database name -> (display name, earliest epoch it can be built in).",
        "# Wonders have no per-epoch variants, so none of them ever expires; the",
        "# epoch is a floor, and is why a wonder is only a usable check when the",
        "# seed's goal epoch reaches it.",
        "WONDERS: dict[str, tuple[str, int]] = {",
    ]
    for _i, raw, disp, epoch in wonder_list:
        lines.append(f"    {raw!r}: ({disp!r}, {epoch}),")
    lines += [
        "}",
        "",
        "FAMILY_FIELD_OFFSET = 0x68  # within a dbobjects.dat record",
        "",
    ]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--edition", choices=sorted(EDITIONS),
                    default=DEFAULT_EDITION,
                    help="which edition's database to read")
    ap.add_argument("--ssa", help="an explicit path, overriding --edition")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    ssa = args.ssa or SSA_BY_EDITION[args.edition]
    print(f"reading {ssa}")
    print()
    buildings, unit_families, members = build(ssa)
    wonder_list = wonders(ssa)
    print(f"{len(buildings)} buildings kept:")
    for i, raw, disp, epoch in buildings:
        print(f"   {i:4d}  epoch {epoch:2d}  {raw!r} -> {disp}")
    print(f"\n{len(unit_families)} unit families kept:")
    for idx, name, count, epoch in unit_families:
        print(f"   {idx:3d}  epoch {epoch:2d}  {name:<24s} {count} members")
    print(f"\n{len(members)} unit names mapped to a family")
    print(f"\n{len(wonder_list)} wonders:")
    for i, raw, disp, epoch in wonder_list:
        print(f"   {i:4d}  {raw!r} -> {disp} (from epoch {epoch})")
    print(f"\ntotal checks available: "
          f"{len(buildings) + len(unit_families) + len(wonder_list)}")

    if args.write:
        with open(OUT, "w", encoding="utf-8") as f:
            f.write(emit(buildings, unit_families, members, wonder_list))
        print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
