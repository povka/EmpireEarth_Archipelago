import re

from BaseClasses import Location

try:
    from .Epochs import EPOCH_NAMES
    from .Technologies import TECHNOLOGIES
    from .BuildingEpochs import BUILDING_EPOCH
    from .Objects import (
        BUILDING_MIN_EPOCH,
        BUILDINGS,
        UNIT_FAMILIES,
        UNIT_FAMILY_BY_NAME,
        UNIT_FAMILY_MIN_EPOCH,
        WONDERS,
    )
except ImportError:  # loaded as a top-level module by tools/
    from Epochs import EPOCH_NAMES
    from Technologies import TECHNOLOGIES
    from BuildingEpochs import BUILDING_EPOCH
    from Objects import (
        BUILDING_MIN_EPOCH,
        BUILDINGS,
        UNIT_FAMILIES,
        UNIT_FAMILY_BY_NAME,
        UNIT_FAMILY_MIN_EPOCH,
        WONDERS,
    )

BASE_ID = 8_950_000

# Id blocks are kept apart so new checks of one kind never shift another kind's
# ids, which would invalidate existing seeds.
EPOCH_LOCATION_BASE = 100
BUILD_LOCATION_BASE = 200
RECRUIT_LOCATION_BASE = 300
WONDER_LOCATION_BASE = 400
TECH_LOCATION_BASE = 500
UNIT_LOCATION_BASE = 600

# One check per epoch entered.
EPOCH_LOCATIONS: dict[str, int] = {
    f"Reach {name}": BASE_ID + EPOCH_LOCATION_BASE + i
    for i, name in enumerate(EPOCH_NAMES)
    if i >= 1
}

# One check per building type. Sorted by database name so ids stay stable.
_BUILDINGS_ORDERED = sorted(BUILDINGS.items())
BUILD_LOCATIONS: dict[str, int] = {
    f"Build {display}": BASE_ID + BUILD_LOCATION_BASE + n
    for n, (_raw, display) in enumerate(_BUILDINGS_ORDERED)
}

# The 300 block held one check per unit *family*. Those are gone: every unit
# now has its own check, in the 600 block below. The block is left unused rather
# than reassigned, so an id can never mean two different things.

# One check per wonder. Unlike buildings these are not always in a seed: a
# wonder cannot be built before its own epoch, and the client caps the match at
# the goal epoch, so Time Machine only exists in a Space Age seed.
_WONDERS_ORDERED = sorted(WONDERS.items())
WONDER_LOCATIONS: dict[str, int] = {
    f"Build {display}": BASE_ID + WONDER_LOCATION_BASE + n
    for n, (_raw, (display, _epoch)) in enumerate(_WONDERS_ORDERED)
}

# One check per technology. Technologies are left exactly where the game puts
# them - nothing is hidden or unlocked - so a check is simply researching one.
_TECHS_ORDERED = sorted(TECHNOLOGIES)
TECH_LOCATIONS: dict[str, int] = {
    f"Research {name}": BASE_ID + TECH_LOCATION_BASE + n
    for n, name in enumerate(_TECHS_ORDERED)
}

# One check per individual unit.
#
# These would normally be missable - Empire Earth withdraws a unit once a later
# tier replaces it - which is why they were once family checks instead. The
# client now clears both of the engine's retirement paths on every node
# (Obsolescence.py), so a Rock Thrower stays recruitable for the whole match
# and these are as safe as any other check.
#
# `x`-prefixed records are campaign and scenario units, left out entirely.
TRAINABLE_UNITS: tuple[str, ...] = tuple(sorted(
    name for name in UNIT_FAMILY_BY_NAME if not name.lower().startswith("x")
))


def _unit_display(db_name: str) -> str:
    """`Inf01 - Clubman` -> `Clubman`, keeping the full name when unsure."""
    match = _UNIT_PREFIX.match(db_name)
    tail = match.group(1).strip() if match else db_name
    # Some names put the tier last (`a Helicopter Sea King II 13`), which leaves
    # a tail with no letters in it. Those keep their database name: ugly, but
    # unique and honest.
    return tail if any(c.isalpha() for c in tail) else db_name


_UNIT_PREFIX = re.compile(r"^[A-Za-z ]*?\d+\s*(?:-\s*)?(.+)$")

_seen: dict[str, int] = {}
UNIT_DISPLAY: dict[str, str] = {}
for _db in TRAINABLE_UNITS:
    _name = _unit_display(_db)
    if _name in _seen:                      # keep every check distinct
        _seen[_name] += 1
        _name = f"{_name} ({_seen[_name]})"
    else:
        _seen[_name] = 1
    UNIT_DISPLAY[_db] = _name

RECRUIT_LOCATIONS: dict[str, int] = {
    f"Recruit {UNIT_DISPLAY[db]}": BASE_ID + UNIT_LOCATION_BASE + n
    for n, db in enumerate(TRAINABLE_UNITS)
}
RECRUIT_LOCATION_BY_DBNAME: dict[str, str] = {
    db: f"Recruit {UNIT_DISPLAY[db]}" for db in TRAINABLE_UNITS
}

LOCATION_TABLE: dict[str, int] = {
    **EPOCH_LOCATIONS,
    **BUILD_LOCATIONS,
    **WONDER_LOCATIONS,
    **TECH_LOCATIONS,
    **RECRUIT_LOCATIONS,
}
LOCATION_NAME_TO_ID = dict(LOCATION_TABLE)
LOCATION_ID_TO_NAME = {v: k for k, v in LOCATION_NAME_TO_ID.items()}

# Lookups the client uses to turn what the player owns into a check.
BUILD_LOCATION_BY_DBNAME: dict[str, str] = {
    raw: f"Build {display}" for raw, display in _BUILDINGS_ORDERED
}

WONDER_LOCATION_BY_DBNAME: dict[str, str] = {
    raw: f"Build {display}" for raw, (display, _epoch) in _WONDERS_ORDERED
}

# Location name -> the epoch that wonder first becomes buildable in.
WONDER_MIN_EPOCH: dict[str, int] = {
    f"Build {display}": epoch for _raw, (display, epoch) in _WONDERS_ORDERED
}

# Location name -> the epoch that unlocks it. Everything a seed offers has a
# floor: you cannot build a Siege Factory in the Copper Age, so a check for one
# must require the epochs that get you there. Without this, generation is free
# to hide `Epoch: Bronze Age` behind `Build Siege Factory`, which needs it.
LOCATION_MIN_EPOCH: dict[str, int] = {}
# The tech tree's own number, not the database's - `dbobjects.dat` reads an
# epoch too high for most buildings and two too high for the Temple, which put
# a Granary in the Bronze Age when the game offers it in the Copper Age.
def building_epoch(display: str) -> int:
    return BUILDING_EPOCH.get(display, BUILDING_MIN_EPOCH.get(display, 0))


LOCATION_MIN_EPOCH.update({
    f"Build {display}": building_epoch(display)
    for _raw, display in _BUILDINGS_ORDERED
})
LOCATION_MIN_EPOCH.update({
    f"Recruit {UNIT_DISPLAY[db]}": UNIT_FAMILY_MIN_EPOCH.get(UNIT_FAMILY_BY_NAME[db], 0)
    for db in TRAINABLE_UNITS
})
LOCATION_MIN_EPOCH.update(WONDER_MIN_EPOCH)
# A technology needs its building, and the building has an epoch of its own, so
# the floor is whichever comes later. Most technologies sit in the same epoch as
# their building, but the late Cyber ones do not, and using the technology's
# epoch alone let generation place them before the building existed - which the
# playability simulation caught as a deadlock.
LOCATION_MIN_EPOCH.update({
    f"Research {name}": max(epoch, building_epoch(building))
    for name, (epoch, building, _t, _n, _i) in TECHNOLOGIES.items()
})

RECRUIT_LOCATION_FAMILY: dict[str, str] = {
    f"Recruit {UNIT_DISPLAY[db]}": UNIT_FAMILY_BY_NAME[db] for db in TRAINABLE_UNITS
}

# Location name -> the building that researches it. A technology is offered by
# one building only, so with building unlocks on, a check for it needs that
# building as well as the epoch: Printing Press is a Renaissance Temple
# technology, so it can hold neither `Unlock: Temple` nor any epoch up to the
# Renaissance.
TECH_LOCATION_BUILDING: dict[str, str] = {
    f"Research {name}": building
    for name, (_e, building, _t, _n, _i) in TECHNOLOGIES.items()
}

# (texture, node epoch) -> location, which is how the client turns a researched
# node into a check. The texture alone does not identify one: all seven wall and
# tower upgrades share a texture and only their epoch separates them.
TECH_LOCATION_BY_NODE: dict[tuple[str, int], str] = {
    (texture, node_epoch): f"Research {name}"
    for name, (_e, _b, texture, node_epoch, _i) in TECHNOLOGIES.items()
}

# Every match starts you with a Capitol and citizens, whatever epoch it begins
# in, so these two checks are satisfiable immediately and must not carry an
# epoch requirement. Without this a Prehistoric start has no reachable location
# at all - nothing else can be built until the Stone Age - and generation has
# nowhere to place the first epoch unlock.
STARTING_LOCATIONS = ("Build Capitol", "Recruit Citizen")
for _name in STARTING_LOCATIONS:
    if _name in LOCATION_MIN_EPOCH:
        LOCATION_MIN_EPOCH[_name] = 0

# Build and recruit checks, regardless of epoch. Which of them a seed actually
# includes is decided by LOCATION_MIN_EPOCH against its goal epoch.
ALWAYS_LOCATIONS: set[str] = set(BUILD_LOCATIONS) | set(RECRUIT_LOCATIONS)


class EmpireEarthLocation(Location):
    game = "Empire Earth"
