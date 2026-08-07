import re

from BaseClasses import Location

try:
    from .Epochs import EPOCH_NAMES
    from .Technologies import TECHNOLOGIES
    from .BuildingEpochs import BUILDING_EPOCH
    from .Producers import UNIT_FAMILY_PRODUCERS
    from .Upgrades import UNIT_SUPERSEDES
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
    from Upgrades import UNIT_SUPERSEDES
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
#
# Only buildings whose epoch was measured from the running game's tech tree.
# `dbobjects.dat` is not good enough for a building: it reads an epoch high for
# most and, among the records Art of Conquest adds, plainly wrong for some -
# the Teleporter and the FTL Research Center are Space Age structures stored as
# epoch 3. A floor that reads low is the direction that strands a seed, because
# it lets generation hide an epoch item behind a check that needs it.
#
# So an unmeasured building is simply not a check yet. Re-running
# tools/gen_building_epochs.py against a live Art of Conquest match is what
# admits the Space Dock, the Teleporter and the rest - nothing here needs
# changing when it does.
_BUILDINGS_ORDERED = sorted(
    (raw, display) for raw, display in BUILDINGS.items()
    if display in BUILDING_EPOCH
)
BUILD_LOCATIONS: dict[str, int] = {
    f"Build {display}": BASE_ID + BUILD_LOCATION_BASE + n
    for n, (_raw, display) in enumerate(_BUILDINGS_ORDERED)
}

# The 300 block held one check per unit *family*. Those are gone: every unit
# now has its own check, in the 600 block below. The block is left unused rather
# than reassigned, so an id can never mean two different things.

# Wonders are not checks. Building one sends nothing.
#
# They used to be, and the 400 block below is left unused rather than reassigned
# so an id can never come to mean two different things. What a wonder has now is
# an unlock item (`Items.wonder_item`): it is gated like a building, and under a
# wonder goal it is the goal, so the find is the reward and the construction is
# what you do with it - rather than the same wonder paying out twice.
_WONDERS_ORDERED = sorted(WONDERS.items())

# Technologies a seed never offers, because the game does not reliably offer
# them either. Empty, and that is the finding rather than an oversight.
#
# `Oracle` was listed here for one afternoon. It was reported missing from a
# live Temple, and the run was stuck behind `Building: Hospital` sitting on its
# check - but checking vanilla Art of Conquest afterwards found it exactly
# where every source said it would be, a Bronze Age Temple technology beside
# Monotheism. The button appears below the others and had been overlooked.
#
# Excluding it would have deleted a real check and, worse, hidden a client bug
# had there been one. There is not: nothing here clears a technology node's
# availability. `BuildingGate` only writes `+0x06` on nodes whose icon matches
# a gated building or wonder exactly, and `but_oracle_04` matches none.
#
# The mechanism stays because the hazard is real - units and buildings have
# both turned out to have members the game does not offer - but a name only
# belongs here on evidence stronger than one absence, since the cost of being
# wrong is a check that quietly leaves the pool.
EXCLUDED_TECHNOLOGIES: frozenset[str] = frozenset()

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
# tier replaces it - which is why they were once family checks instead. Two
# separate things keep them sendable, because the engine retires a unit in two
# different ways:
#
# * An *expiry* ("no longer offered after epoch N") is cleared outright by
#   Obsolescence.py, so a Rock Thrower stays recruitable for the whole match.
# * A *replacement* ("this later unit took over") is left alone - cancelling it
#   reverts the upgrade rather than preserving both - and the replacement sends
#   the replaced unit's check instead. See LOCATION_ALSO_SENDS below.
#
# `x`-prefixed records are campaign and scenario units, left out entirely.
EXCLUDED_UNIT_PREFIXES = ("x",)

# Campaign heroes. Art of Conquest ships a handful that no skirmish offers -
# the Roman campaign's Marius and Greek Captain, Lt. Stock, Bulldog Ramsey, and
# a second Julius Caesar marked "Conscript" - and a check for one can never be
# sent.
#
# The Conscript is the one that did damage rather than merely sitting there. It
# shares tier 5 with the real Julius Caesar, so the tier had *three* heroes in
# it, and the pairing matched Charlemagne to the campaign copy - leaving
# `h2-5 Julius Caesar (Morale)`, the one a skirmish actually offers, with no
# partner and no way to be sent once Charlemagne was taken.
EXCLUDED_UNIT_MARKERS = ("conscript",)
EXCLUDED_UNIT_NAMES = frozenset({
    "Hero Bulldog Ramsey (Morale)",
    "h Greek Captain",
    "h Lt. Stock",
})


def _is_excluded(name: str) -> bool:
    low = name.lower()
    return (low.startswith(EXCLUDED_UNIT_PREFIXES)
            or name in EXCLUDED_UNIT_NAMES
            or any(m in low for m in EXCLUDED_UNIT_MARKERS))

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
    if not _is_excluded(name)
    and not name.lower().startswith(PAIRED_UNIT_PREFIXES)
))

PAIRED_UNITS: tuple[str, ...] = tuple(sorted(
    name for name in UNIT_FAMILY_BY_NAME
    if name.lower().startswith(PAIRED_UNIT_PREFIXES) and not _is_excluded(name)
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
    # The tidy-up only strips a leading tier number, and this name has none, so
    # the check read `Recruit spc Spy Satellite`.
    "spc Spy Satellite": "Spy Satellite",
}


# `h1-3 Sargon of Akkad (heal)` and `h1 6 William the Conqueror (heal)` - the
# separator is a dash for all but one of them - into ('1', 3, 'Sargon of Akkad
# (heal)'). The line tells a healing hero from a morale one and the tier is what
# pairs them up.
_HERO = re.compile(r"^h([12])\s*-?\s*(\d+)\s+(.+)$")

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
    **TECH_LOCATIONS,
    **RECRUIT_LOCATIONS,
}
LOCATION_NAME_TO_ID = dict(LOCATION_TABLE)
LOCATION_ID_TO_NAME = {v: k for k, v in LOCATION_NAME_TO_ID.items()}

# Lookups the client uses to turn what the player owns into a check.
BUILD_LOCATION_BY_DBNAME: dict[str, str] = {
    raw: f"Build {display}" for raw, display in _BUILDINGS_ORDERED
}

# Database name -> display name, for the client's wonder counting and its
# `/wonders` display. Not a location lookup any more: nothing is sent for one.
WONDER_BY_DBNAME: dict[str, str] = {
    raw: display for raw, (display, _epoch) in _WONDERS_ORDERED
}

# Wonder -> the epoch it first becomes buildable in. Still needed even though
# it is not a check: the goal has to know when N wonders can exist.
WONDER_MIN_EPOCH: dict[str, int] = {
    display: epoch for _raw, (display, epoch) in _WONDERS_ORDERED
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
# `Building: Barracks` for a check that is available before anything is built.
#
# Over-constraining is the safe direction and can never make a seed unwinnable,
# which is why this was not a live bug. It costs reachability instead: in a
# Prehistoric start with building unlocks on, only three checks need no unlock
# at all, and this is a fourth.
UNIT_PRODUCER_OVERRIDES: dict[str, tuple[str, ...]] = {
    "Domestic Wolf": ("Capitol", "Town Center"),
    # Trained at both, which no family can express: its family is Helicopter
    # and every other member comes from the Airport alone. Missing the second
    # building would not strand a seed - the check stays reachable through the
    # Airport - but it would tell logic a Navy Yard is no help when it is.
    "a Helicopter Sea King II 13": ("Airport", "Navy Yard"),
    # Two members of the `Space Fighter` family that the Space Dock does not
    # build, reported from the game: the Airport's Space Age fighter, and a
    # satellite launched from the Capitol.
    "a Fighter15 Planetary Fighter": ("Airport",),
    "spc Spy Satellite": ("Capitol",),
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


# Units only some civilisations can field. Their checks are real and sendable,
# but nothing the seed needs is ever placed on one.
#
# The client deliberately leaves civilisation choice to the player - it forces
# the rest of the skirmish setup, not that - so a civilisation-locked unit is
# only recruitable if the player happened to pick the right one. Nothing warns
# them at generation time, and by the time progression turns out to sit behind
# a unit their civilisation cannot build, the only way out is a fresh match.
#
# `Inf15 - Cyber Ninja` needs Japan, or a custom civilisation taking the power
# that grants it. Marked EXCLUDED rather than dropped: it stays a check worth
# sending, it just cannot be load-bearing.
CIV_LOCKED_UNITS: tuple[str, ...] = (
    "Inf15 - Cyber Ninja",
)

# The same, as location names, for the world to mark EXCLUDED. Filtered through
# the lookup so a name that stops being a check cannot leave a stale entry.
CIV_LOCKED_LOCATIONS: frozenset[str] = frozenset(
    RECRUIT_LOCATION_BY_DBNAME[db]
    for db in CIV_LOCKED_UNITS
    if db in RECRUIT_LOCATION_BY_DBNAME
)

# Buildings that are real, and buildable only in some matches.
#
# A tech tree node and a measured epoch say a building exists, not that this
# match can raise one. All three below are listed as buildings by the game's
# own wiki and measured cleanly - Pyramid at the Prehistoric Age, Space Dock
# and Space Turret at the Space Age - yet a Space Age match offered none of
# them.
#
# The Space Dock and the Space Turret turn out to be a *map* dependency rather
# than an epoch one. The dock can only be placed "on the border between land
# and space", which no ordinary map has; on a `Planets Earth` map both appear
# and can be built. That is the same shape as a Dock needing water, except this
# project leaves map choice to the player, so no seed can promise the terrain.
#
# The Pyramid is still unexplained - absent from a Space Age match on a normal
# map, and not obviously map-dependent - so it stays here on the same terms.
#
# So they stay as checks and stop being load-bearing: sendable when a match
# does offer them, harmless when it does not. Remove an entry only when
# something guarantees the conditions - forcing the map type would do it.
UNCONFIRMED_BUILDINGS: tuple[str, ...] = (
    "Pyramid",
)

# Buildings that *replace* another on some maps rather than joining it.
#
# A `Planets` map has no Dock and no Navy Yard: the Space Dock and the Space
# Turret stand in their place. So on those maps `Build Dock` can never be sent,
# and on every other map `Build Space Dock` cannot - and both are ordinary
# progression-bearing checks, so either way round strands a seed.
#
# `map_terrain` decides which half of each pair a seed contains, so only one is
# ever a check. The cascade below is kept anyway, and it earns its place as
# insurance: a player who declares the wrong terrain still sends the check they
# do have, because a Space Dock reports `Build Dock` too. Sending a location the
# seed does not contain costs nothing.
BUILDING_PAIRS: dict[str, str] = {
    "Dock": "Space Dock",
    "Navy Yard": "Space Turret",
}

# Which terrains a building exists on. Anything absent is on all of them.
#
# This is the one thing about a match a seed cannot see: the client forces map
# *size* but never map choice, so the `map_terrain` option is the player saying
# which of these they will play. Everything the terrain decides - the build
# checks, the units those buildings train, and the substituted wonder - is
# filtered through it, which is what lets those checks stay load-bearing rather
# than being written off as things that might not exist.
LAND_ONLY = "land_only"
LAND_AND_WATER = "land_and_water"
SPACE = "space"
ALL_TERRAINS = frozenset({LAND_ONLY, LAND_AND_WATER, SPACE})

BUILDING_TERRAINS: dict[str, frozenset[str]] = {
    # No water, no Dock; on a Planets map a Space Dock stands in its place.
    "Dock": frozenset({LAND_AND_WATER}),
    "Navy Yard": frozenset({LAND_AND_WATER}),
    "Space Dock": frozenset({SPACE}),
    "Space Turret": frozenset({SPACE}),
}

WONDER_TERRAINS: dict[str, frozenset[str]] = {
    "Pharos Lighthouse": frozenset({LAND_ONLY, LAND_AND_WATER}),
    "Orbital Space Station": frozenset({SPACE}),
}


def building_terrains(display: str) -> frozenset[str]:
    return BUILDING_TERRAINS.get(display, ALL_TERRAINS)


def wonder_terrains(display: str) -> frozenset[str]:
    return WONDER_TERRAINS.get(display, ALL_TERRAINS)

# Wonders with the same map dependency. They are not checks, so nothing here
# can go unsendable - but the wonder goal counts how many you could raise, and
# counting one that needs terrain the seed cannot promise would call a run
# finished while the player was still short a wonder.
# The building pairs above, both ways round, as location names.
_PAIRED_BUILD_LOCATIONS: dict[str, str] = {}
for _a, _b in BUILDING_PAIRS.items():
    _la, _lb = f"Build {_a}", f"Build {_b}"
    if _la in BUILD_LOCATIONS and _lb in BUILD_LOCATIONS:
        _PAIRED_BUILD_LOCATIONS[_la] = _lb
        _PAIRED_BUILD_LOCATIONS[_lb] = _la




def _recruit_location(db_name: str) -> str | None:
    return RECRUIT_LOCATION_BY_DBNAME.get(db_name)


# Location name -> every other check that recruiting it also sends.
#
# Two different relations, both of which exist to stop a check becoming
# unsendable, and both of which the fill can represent because they only ever
# add sends.
#
# *Heroes* are a mutually exclusive pair: one of the two can exist in a match,
# so each sends the other and the pair is always satisfiable together.
#
# *Upgrades* run one way. Empire Earth retires a unit when a later tier
# replaces it, so a Slinger stops being offered once you have Simple Bowmen.
# The client used to prevent that by clearing the engine's superseded flag,
# which does not hold the old unit alongside the new one - it cancels the
# upgrade, and the Archery Range goes back to offering Slingers. So the upgrade
# is left alone and the replacement carries the replaced unit's check instead:
# build a Simple Bowman and Slinger's check goes with it, build a Long Bow and
# all four below it go.
#
# The epoch floors are unaffected. A check's floor is the earliest point it can
# be sent, and that is still the unit's own tier - a Slinger sends Slinger.
LOCATION_ALSO_SENDS: dict[str, tuple[str, ...]] = {}
for _here, _partner in _PAIRED_BUILD_LOCATIONS.items():
    LOCATION_ALSO_SENDS[_here] = (_partner,)

for _db in ALL_RECRUITABLE:
    _here = RECRUIT_LOCATION_BY_DBNAME[_db]
    _also = [PAIRED_LOCATIONS[_here]] if _here in PAIRED_LOCATIONS else []
    # Some superseded units are not checks at all (scenario props), so the
    # lookup is filtered rather than assumed.
    _also += [loc for loc in map(_recruit_location, UNIT_SUPERSEDES.get(_db, ()))
              if loc is not None]
    if _also:
        LOCATION_ALSO_SENDS[_here] = tuple(dict.fromkeys(_also))

# Location name -> the buildings that can train it. Resolved here, per unit, so
# the rules never have to go back to the family - which is what got the Canine
# Scout wrong.
RECRUIT_LOCATION_PRODUCERS: dict[str, tuple[str, ...]] = {
    f"Recruit {UNIT_DISPLAY[db]}": unit_producers(db) for db in ALL_RECRUITABLE
}

# Every check that must never hold anything the seed needs.
#
# Terrain-specific checks are not here. `map_terrain` says which map the player
# will play, so a check the terrain rules out is left out of the seed entirely
# rather than shipped as something nothing may depend on.
NO_PROGRESSION_LOCATIONS: frozenset[str] = (
    CIV_LOCKED_LOCATIONS
    | frozenset(f"Build {b}" for b in UNCONFIRMED_BUILDINGS
                if f"Build {b}" in BUILD_LOCATIONS)
)

# Location name -> the building that researches it. A technology is offered by
# one building only, so with building unlocks on, a check for it needs that
# building as well as the epoch: Printing Press is a Renaissance Temple
# technology, so it can hold neither `Building: Temple` nor any epoch up to the
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
