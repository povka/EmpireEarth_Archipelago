import re

from BaseClasses import Location

try:
    from .Epochs import EPOCH_NAMES
    from .Technologies import TECHNOLOGIES
    from .BuildingEpochs import BUILDING_EPOCH
    from .Producers import UNIT_FAMILY_PRODUCERS
    from .Objects import (
        BUILDING_MIN_EPOCH,
        BUILDINGS,
        UNIT_FAMILIES,
        UNIT_FAMILY_BY_NAME,
        UNIT_FAMILY_MIN_EPOCH,
        UNIT_MIN_EPOCH,
        WONDERS,
    )
except ImportError:  # loaded as a top-level module by tools/
    from Epochs import EPOCH_NAMES
    from Technologies import TECHNOLOGIES
    from BuildingEpochs import BUILDING_EPOCH
    from Producers import UNIT_FAMILY_PRODUCERS
    from Objects import (
        BUILDING_MIN_EPOCH,
        BUILDINGS,
        UNIT_FAMILIES,
        UNIT_FAMILY_BY_NAME,
        UNIT_FAMILY_MIN_EPOCH,
        UNIT_MIN_EPOCH,
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
# 1000, not 600: there are exactly 100 technologies, so the block below this one
# ends at 599 and a single technology added to the game's tech tree would have
# started handing out ids that already meant a unit. The gap is deliberate, and
# tools/build_apworld.py fails the build if any two ids ever do collide.
UNIT_LOCATION_BASE = 1000
# The paired morale heroes. Their own block, well clear of the unit block above,
# so that giving them checks renumbers nothing: `h2-` sorts into the middle of
# TRAINABLE_UNITS, and appending them there would have moved every id after it.
PAIRED_UNIT_LOCATION_BASE = 2000

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
EXCLUDED_UNIT_PREFIXES = ("x",)

# The morale heroes, `h2-3` .. `h2-14`, one per tier facing an `h1-` healing
# hero of the same tier. You cannot have both: taking either forecloses the
# other, so a check on each would be a pair the fill treats as independent when
# it is not, and one of the two could never be sent.
#
# They are not left out. Recruiting either hero of a tier sends *both* checks
# (see UNIT_PAIR below, and Client.locations_for), so the pair is always
# satisfiable together and which one you actually build stays your choice.
# Logically the two are then one check that happens to pay out twice, which is
# something the fill can represent - unlike a choice.
#
# They get an id block of their own rather than joining TRAINABLE_UNITS,
# because `h2-` sorts into the middle of it: adding twelve names there would
# renumber every unit sorting after them, which is the entire navy.
PAIRED_UNIT_PREFIXES = ("h2-",)

TRAINABLE_UNITS: tuple[str, ...] = tuple(sorted(
    name for name in UNIT_FAMILY_BY_NAME
    if not name.lower().startswith(EXCLUDED_UNIT_PREFIXES + PAIRED_UNIT_PREFIXES)
))

PAIRED_UNITS: tuple[str, ...] = tuple(sorted(
    name for name in UNIT_FAMILY_BY_NAME
    if name.lower().startswith(PAIRED_UNIT_PREFIXES)
))

ALL_RECRUITABLE: tuple[str, ...] = TRAINABLE_UNITS + PAIRED_UNITS


# Database name -> the name to show, where the game disagrees with its own
# database. `Domestic Wolf` is what `dbobjects.dat` calls it; the game's UI
# calls it a Canine Scout, and the display name is what the player actually
# reads - in the client, in the server's messages, and on the game's own
# `--AP--` line - so it should be the name they see while playing.
#
# This is cosmetic and cannot break a check. A recruit location is matched by
# the *database* name, which is what the running game reports through a unit's
# type definition (see Roster.type_name), and ids are assigned over
# TRAINABLE_UNITS in database-name order - so neither detection nor numbering
# looks at the display name at all.
UNIT_DISPLAY_OVERRIDES: dict[str, str] = {
    "Domestic Wolf": "Canine Scout",
}


# `h1-3 Sargon of Akkad (heal)` and `h1 6 William the Conqueror (heal)` - the
# separator is a dash for all but one of them - into ('1', 3, 'Sargon of Akkad
# (heal)'). The line tells a healing hero from a morale one and the tier is what
# pairs them up.
_HERO = re.compile(r"^h([12])[-\s]\s*(\d+)\s+(.+)$")

# The trailing role marker. Dropped from the display name: the two heroes of a
# tier already have different names, and `Recruit Sargon of Akkad` is what the
# player sees in game. Matched exactly rather than "any trailing parenthesis",
# so a name that genuinely ends in brackets keeps them.
_HERO_ROLE = re.compile(r"\s*\((?:heal|morale)\)\s*$", re.IGNORECASE)


def _hero_parts(db_name: str):
    """(line, tier, name) for a hero, or None for anything else."""
    match = _HERO.match(db_name)
    return (match.group(1), int(match.group(2)), match.group(3).strip()) \
        if match else None


def _unit_display(db_name: str) -> str:
    """`Inf01 - Clubman` -> `Clubman`, keeping the full name when unsure."""
    override = UNIT_DISPLAY_OVERRIDES.get(db_name)
    if override:
        return override
    # Heroes need their own pass: the general rule strips only the first
    # letters-and-digits run, so `h1-3 Sargon of Akkad (heal)` kept its tier and
    # read `3 Sargon of Akkad (heal)`. Both the tier and the role marker go, and
    # every hero is still distinct without them.
    hero = _hero_parts(db_name)
    if hero:
        return _HERO_ROLE.sub("", hero[2]).strip() or hero[2]
    match = _UNIT_PREFIX.match(db_name)
    tail = match.group(1).strip() if match else db_name
    # Some names put the tier last (`a Helicopter Sea King II 13`), which leaves
    # a tail with no letters in it. Those keep their database name: ugly, but
    # unique and honest.
    return tail if any(c.isalpha() for c in tail) else db_name


_UNIT_PREFIX = re.compile(r"^[A-Za-z ]*?\d+\s*(?:-\s*)?(.+)$")


# Database name -> the database name of the unit whose check it also satisfies.
# Symmetric: recruiting either hero of a tier sends both checks, because only
# one of them can ever exist.
def _build_pairs() -> dict[str, str]:
    by_tier: dict[int, dict[str, str]] = {}
    for db in ALL_RECRUITABLE:
        hero = _hero_parts(db)
        if hero:
            by_tier.setdefault(hero[1], {})[hero[0]] = db
    pairs: dict[str, str] = {}
    for sides in by_tier.values():
        # Only a tier with both halves pairs up; a hero with no counterpart is
        # an ordinary check.
        if "1" in sides and "2" in sides:
            pairs[sides["1"]] = sides["2"]
            pairs[sides["2"]] = sides["1"]
    return pairs


UNIT_PAIR: dict[str, str] = _build_pairs()

_seen: dict[str, int] = {}
UNIT_DISPLAY: dict[str, str] = {}
# TRAINABLE_UNITS first, so the paired heroes can only ever take a `(2)` suffix
# from a collision rather than hand one to a name that already exists.
for _db in ALL_RECRUITABLE:
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
# A block of their own; see PAIRED_UNIT_PREFIXES for why they are not simply
# appended to the list above.
RECRUIT_LOCATIONS.update({
    f"Recruit {UNIT_DISPLAY[db]}": BASE_ID + PAIRED_UNIT_LOCATION_BASE + n
    for n, db in enumerate(PAIRED_UNITS)
})
RECRUIT_LOCATION_BY_DBNAME: dict[str, str] = {
    db: f"Recruit {UNIT_DISPLAY[db]}" for db in ALL_RECRUITABLE
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
# A unit needs its own epoch AND somewhere to be recruited from, so the floor
# is whichever of the two comes later - the same rule technologies follow below.
#
# The epoch is the unit's own, never its family's. A family's floor is its
# *earliest* member, which is far too low for a late one: a Cataphract is a
# Dark Age unit in the Lancer family, whose earliest member is a Copper Age
# Horseman. Using the family's number let generation put `Epoch: Dark Age`
# behind `Recruit Cataphract`, which needs the Dark Age to reach - a seed that
# could not be finished, and was not.
#
# The producer half matters on its own: a Rock Thrower is a Prehistoric unit,
# but it comes from a Barracks, so it is not obtainable until a Barracks is.
# Any of a unit's producers will do, so the floor is the earliest of them.

# Database name -> the buildings that actually train this unit, overriding what
# its family says.
#
# `Producers.py` is generated per *family*, and a family is not always uniform.
# `Domestic Wolf` - the Canine Scout - is filed under `Human` alongside
# `Inf01 - Clubman` and `Inf01 - Rock Thrower`, which genuinely do come from a
# Barracks. It comes from the Capitol, so the family's answer demanded
# `Unlock: Barracks` for a check that is available before anything is built.
#
# Over-constraining is the safe direction and can never make a seed unwinnable,
# which is why this was not a live bug. It costs reachability instead: in a
# Prehistoric start with building unlocks on, only three checks need no unlock
# at all, and this is a fourth.
UNIT_PRODUCER_OVERRIDES: dict[str, tuple[str, ...]] = {
    "Domestic Wolf": ("Capitol", "Town Center"),
}


def unit_producers(db_name: str) -> tuple[str, ...]:
    """The buildings that can train this unit, per unit rather than per family."""
    override = UNIT_PRODUCER_OVERRIDES.get(db_name)
    if override is not None:
        return override
    return UNIT_FAMILY_PRODUCERS.get(UNIT_FAMILY_BY_NAME.get(db_name, ""), ())


def _producer_epoch(db_name: str) -> int:
    return min((building_epoch(b) for b in unit_producers(db_name)), default=0)


LOCATION_MIN_EPOCH.update({
    f"Recruit {UNIT_DISPLAY[db]}": max(
        UNIT_MIN_EPOCH.get(
            db, UNIT_FAMILY_MIN_EPOCH.get(UNIT_FAMILY_BY_NAME[db], 0)),
        _producer_epoch(db),
    )
    for db in ALL_RECRUITABLE
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
    f"Recruit {UNIT_DISPLAY[db]}": UNIT_FAMILY_BY_NAME[db] for db in ALL_RECRUITABLE
}

# Location name -> the location its check also satisfies. The two heroes of a
# tier are mutually exclusive, so whichever is recruited sends both.
PAIRED_LOCATIONS: dict[str, str] = {
    f"Recruit {UNIT_DISPLAY[db]}": f"Recruit {UNIT_DISPLAY[other]}"
    for db, other in UNIT_PAIR.items()
}

# Location name -> the buildings that can train it. Resolved here, per unit, so
# the rules never have to go back to the family - which is what got the Canine
# Scout wrong.
RECRUIT_LOCATION_PRODUCERS: dict[str, tuple[str, ...]] = {
    f"Recruit {UNIT_DISPLAY[db]}": unit_producers(db) for db in ALL_RECRUITABLE
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
