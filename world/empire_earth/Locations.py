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
# 1000, not 600. There are exactly 100 technologies, so the block below ends at
# 599 — one technology added to the game and ids start meaning two things. The
# gap is deliberate, and tools/build_apworld.py fails the build on a collision.
UNIT_LOCATION_BASE = 1000
# The paired morale heroes, well clear of the unit block. `h2-` sorts into the
# middle of TRAINABLE_UNITS, so giving them ids there would have renumbered
# every unit after them — the entire navy.
PAIRED_UNIT_LOCATION_BASE = 2000

# One check per epoch entered.
EPOCH_LOCATIONS: dict[str, int] = {
    f"Reach {name}": BASE_ID + EPOCH_LOCATION_BASE + i
    for i, name in enumerate(EPOCH_NAMES)
    if i >= 1
}

# One check per building type, sorted by database name so ids stay stable.
#
# Only buildings with an epoch measured from the running tech tree. That's
# deliberate — `dbobjects.dat` reads an epoch high for most buildings and
# plainly wrong for some of the expansion's: the Teleporter and the FTL
# Research Center are Space Age structures stored as epoch 3. A floor that
# reads low lets generation hide an epoch item behind a check that needs it.
#
# An unmeasured building is not a check yet. Re-running
# tools/gen_building_epochs.py against a live match admits the rest, and
# nothing here needs changing when it does.
_BUILDINGS_ORDERED = sorted(
    (raw, display) for raw, display in BUILDINGS.items()
    if display in BUILDING_EPOCH
)
BUILD_LOCATIONS: dict[str, int] = {
    f"Build {display}": BASE_ID + BUILD_LOCATION_BASE + n
    for n, (_raw, display) in enumerate(_BUILDINGS_ORDERED)
}

# The 300 block was one check per unit *family*. Every unit has its own check
# now. The block stays unused rather than reassigned, so no id ever means two
# different things.

# Wonders are not checks. Building one sends nothing.
#
# They used to, and the 400 block stays unused for the same reason as the 300
# one. A wonder has an unlock item instead (`Items.wonder_item`), gated like a
# building. That's deliberate — under a wonder goal the wonder *is* the goal,
# so finding the item is the reward and raising it is what you do with it,
# rather than the same wonder paying out twice.
_WONDERS_ORDERED = sorted(WONDERS.items())

# Technologies a seed never offers, because the game doesn't reliably offer
# them either. Empty — that's the finding, not an oversight.
#
# `Oracle` sat here for one afternoon. It was reported missing from a live
# Temple with a run stuck behind `Building: Hospital` on its check, which looks
# exactly like a technology the game withholds. Vanilla Art of Conquest had it
# right where every source said — a Bronze Age Temple technology beside
# Monotheism.
#
# It was ours. Temple technologies form chains that share one button and differ
# only by epoch, like the wall and tower upgrades, and `Obsolescence` was
# clearing the expiry on every node in the tree. A tier that never retires
# keeps the slot and the next never appears. Fixed in Obsolescence.py.
#
# Excluding Oracle would have deleted a real check *and* hidden the bug eating
# it, while that same bug went on stranding runs on the tower upgrades. So: an
# absence in game is not evidence about the game until the client is ruled out.
#
# The mechanism stays — units and buildings have both turned out to have
# members no skirmish offers — but a name belongs here only on evidence that
# survives that question.
EXCLUDED_TECHNOLOGIES: frozenset[str] = frozenset()

# One check per technology. Nothing is hidden or unlocked, so a check is just
# researching one.
_TECHS_ORDERED = sorted(TECHNOLOGIES)
TECH_LOCATIONS: dict[str, int] = {
    f"Research {name}": BASE_ID + TECH_LOCATION_BASE + n
    for n, name in enumerate(_TECHS_ORDERED)
}

# One check per unit.
#
# These would be missable — Empire Earth withdraws a unit once a later tier
# replaces it — which is why they were family checks once. The engine retires a
# unit two ways, so two things keep them sendable:
#
# - an *expiry* ("not offered after epoch N") is cleared by Obsolescence.py, so
#   a Rock Thrower stays recruitable all match
# - a *replacement* ("this later unit took over") is left alone, and the
#   replacement sends the replaced unit's check. See LOCATION_ALSO_SENDS
#
# `x`-prefixed records are campaign and scenario props.
EXCLUDED_UNIT_PREFIXES = ("x",)

# Campaign heroes. Art of Conquest ships a few no skirmish offers — Marius, the
# Greek Captain, Lt. Stock, Bulldog Ramsey, and a second Julius Caesar marked
# "Conscript" — and a check for one can never be sent.
#
# The Conscript did damage rather than just sitting there. It shares tier 5
# with the real Julius Caesar, so that tier held *three* heroes and the pairing
# matched Charlemagne to the campaign copy — leaving `h2-5 Julius Caesar
# (Morale)`, the one a skirmish actually offers, unpaired and unsendable once
# you took Charlemagne.
EXCLUDED_UNIT_MARKERS = ("conscript",)
EXCLUDED_UNIT_NAMES = frozenset({
    "Hero Bulldog Ramsey (Morale)",
    "h Greek Captain",
    "h Lt. Stock",
    # Scenario-only, reported from play. No `x ` prefix — the database's
    # marker for its other scenario records — and it sits in the Aircraft
    # Carrier family beside the Enterprise, indistinguishable by any field.
    "s11 Japanese Flattop Carrier",
})


def _is_excluded(name: str) -> bool:
    low = name.lower()
    return (low.startswith(EXCLUDED_UNIT_PREFIXES)
            or name in EXCLUDED_UNIT_NAMES
            or any(m in low for m in EXCLUDED_UNIT_MARKERS))

# The morale heroes, `h2-3` to `h2-14`, one per tier facing an `h1-` healing
# hero of the same tier. You can't have both — taking either forecloses the
# other — so two independent checks would leave one permanently unsendable.
#
# They aren't left out. Recruiting either hero of a tier sends *both* checks,
# so the pair is always satisfiable and which one you build stays your choice.
# The two become one check that pays out twice, which the fill can represent.
# A choice it cannot.
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


# Database name -> what to call it, where the game disagrees with its own
# database. `dbobjects.dat` says `Domestic Wolf`; the game says Canine Scout,
# and the display name is what you read in the client, in server messages and
# on the game's `--AP--` line.
#
# Cosmetic, and it can't break a check. Detection matches the *database* name
# reported by the running game (see Roster.type_name), and ids are assigned in
# database-name order — neither looks at the display name.
UNIT_DISPLAY_OVERRIDES: dict[str, str] = {
    "Domestic Wolf": "Canine Scout",
    # The tidy-up only strips a leading tier number, and this name has none, so
    # the check read `Recruit spc Spy Satellite`.
    "spc Spy Satellite": "Spy Satellite",
}


# `h1-3 Sargon of Akkad (heal)` and `h1 6 William the Conqueror (heal)` — the
# separator is a dash for all but one — into ('1', 3, 'Sargon of Akkad (heal)').
# The line separates healing heroes from morale ones; the tier pairs them up.
_HERO = re.compile(r"^h([12])\s*-?\s*(\d+)\s+(.+)$")

# The trailing role marker, dropped from the display name. The two heroes of a
# tier already have different names, and `Recruit Sargon of Akkad` is what you
# see in game. Matched exactly rather than "any trailing parenthesis", so a
# name that genuinely ends in brackets keeps them.
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
    # Heroes need their own pass. The general rule strips only the first
    # letters-and-digits run, so `h1-3 Sargon of Akkad (heal)` kept its tier
    # and read `3 Sargon of Akkad (heal)`. Tier and role marker both go, and
    # every hero is still distinct without them.
    hero = _hero_parts(db_name)
    if hero:
        return _HERO_ROLE.sub("", hero[2]).strip() or hero[2]
    match = _UNIT_PREFIX.match(db_name)
    tail = match.group(1).strip() if match else db_name
    # Some names put the tier last (`a Helicopter Sea King II 13`), leaving a
    # tail with no letters in it. Those keep their database name — ugly, but
    # unique and honest.
    return tail if any(c.isalpha() for c in tail) else db_name


_UNIT_PREFIX = re.compile(r"^[A-Za-z ]*?\d+\s*(?:-\s*)?(.+)$")


# Database name -> the unit whose check it also satisfies. Symmetric, because
# only one hero of a tier can ever exist.
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
# The tech tree's own number, not the database's — `dbobjects.dat` reads an
# epoch too high for most buildings and two too high for the Temple, which put
# a Granary in the Bronze Age when the game offers it in the Copper Age.
def building_epoch(display: str) -> int:
    return BUILDING_EPOCH.get(display, BUILDING_MIN_EPOCH.get(display, 0))


LOCATION_MIN_EPOCH.update({
    f"Build {display}": building_epoch(display)
    for _raw, display in _BUILDINGS_ORDERED
})
# A unit needs its own epoch AND somewhere to train it, so the floor is
# whichever comes later — the same rule technologies follow below.
#
# The epoch is the unit's own, never its family's. A family's floor is its
# *earliest* member, which is far too low for a late one: a Cataphract is a
# Dark Age unit in the Lancer family, and Lancer starts at a Copper Age
# Horseman. That put `Epoch: Dark Age` behind `Recruit Cataphract`, which needs
# the Dark Age to reach. The seed couldn't be finished, and wasn't.
#
# The producer half matters on its own. A Rock Thrower is a Prehistoric unit
# that comes from a Barracks, so it isn't obtainable until a Barracks is. Any
# producer will do, so the floor is the earliest of them.

# Database name -> the buildings that actually train this unit, overriding its
# family.
#
# `Producers.py` is generated per *family*, and families aren't uniform. The
# Canine Scout is filed under `Human` beside the Clubman and Rock Thrower,
# which do come from a Barracks. It comes from the Capitol, so the family
# demanded `Building: Barracks` for a check available before anything is built.
#
# Over-constraining is the safe direction and can't make a seed unwinnable,
# which is why this was never a live bug. It costs reachability instead: a
# Prehistoric start with unlocks on has only three checks needing no unlock,
# and this was nearly a fourth.
UNIT_PRODUCER_OVERRIDES: dict[str, tuple[str, ...]] = {
    "Domestic Wolf": ("Capitol", "Town Center"),
    # Trained at both, which no family can express — its family is Helicopter
    # and every other member is Airport-only. Missing the second wouldn't
    # strand a seed, since the Airport still reaches it, but it would tell
    # logic a Navy Yard is no help when it is.
    "a Helicopter Sea King II 13": ("Airport", "Navy Yard"),
    # Two members of the `Space Fighter` family the Space Dock doesn't build,
    # reported from the game: the Airport's Space Age fighter, and a satellite
    # launched from the Capitol.
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
# the floor is whichever comes later. Most sit in the same epoch as their
# building; the late Cyber ones don't, and the technology's epoch alone let
# generation place them before the building existed. The playability simulation
# caught that as a deadlock.
LOCATION_MIN_EPOCH.update({
    f"Research {name}": max(epoch, building_epoch(building))
    for name, (epoch, building, _t, _n, _i) in TECHNOLOGIES.items()
})

RECRUIT_LOCATION_FAMILY: dict[str, str] = {
    f"Recruit {UNIT_DISPLAY[db]}": UNIT_FAMILY_BY_NAME[db] for db in ALL_RECRUITABLE
}

# Location name -> the check it also satisfies. The two heroes of a tier are
# mutually exclusive, so whichever you recruit sends both.
PAIRED_LOCATIONS: dict[str, str] = {
    f"Recruit {UNIT_DISPLAY[db]}": f"Recruit {UNIT_DISPLAY[other]}"
    for db, other in UNIT_PAIR.items()
}


# Units only some civilisations can field. Their checks are real and sendable,
# but nothing the seed needs is ever placed on one.
#
# The client deliberately leaves civilisation choice to the player — it forces
# the rest of the skirmish setup, not that — so a civilisation-locked unit is
# only recruitable if the player happened to pick the right one. Nothing warns
# them at generation time, and by the time progression turns out to sit behind
# a unit your civilisation can't build, the only way out is a fresh match.
#
# `Inf15 - Cyber Ninja` needs Japan, or a custom civilisation with the power
# that grants it. Marked EXCLUDED rather than dropped — still a check worth
# sending, just never load-bearing.
CIV_LOCKED_UNITS: tuple[str, ...] = (
    "Inf15 - Cyber Ninja",
)

# The same as location names, for the world to mark EXCLUDED. Filtered through
# the lookup so a name that stops being a check can't leave a stale entry.
CIV_LOCKED_LOCATIONS: frozenset[str] = frozenset(
    RECRUIT_LOCATION_BY_DBNAME[db]
    for db in CIV_LOCKED_UNITS
    if db in RECRUIT_LOCATION_BY_DBNAME
)

# Buildings that are real, and buildable only in some matches.
#
# A tech tree node and a measured epoch say a building exists, not that this
# match can raise one. The Pyramid is listed as a building by the game's own
# wiki and measures cleanly at the Prehistoric Age, and a Space Age match
# offered it nowhere.
#
# Why is still unexplained. The Space Dock and Space Turret looked identical
# until they turned out to be a *map* dependency — both appear on a `Planets`
# map — and those moved to BUILDING_TERRAINS below. The Pyramid isn't obviously
# map-dependent, so it stays here.
#
# It remains a check and stops being load-bearing: sendable if a match offers
# it, harmless if not. Remove an entry only when something guarantees the
# conditions.
UNCONFIRMED_BUILDINGS: tuple[str, ...] = (
    "Pyramid",
)

# Buildings that *replace* another on some maps rather than joining it.
#
# A `Planets` map has no Dock and no Navy Yard — the Space Dock and Space
# Turret stand in their place. So `Build Dock` can never be sent there, and
# `Build Space Dock` can never be sent anywhere else. Both are ordinary
# progression-bearing checks, so either way round strands a seed.
#
# `map_terrain` decides which half a seed contains, so only one is ever a
# check. The cascade below is kept as insurance: declare the wrong terrain and
# you still send the check you do have, because a Space Dock reports
# `Build Dock` too. Sending a location the seed doesn't contain costs nothing.
BUILDING_PAIRS: dict[str, str] = {
    "Dock": "Space Dock",
    "Navy Yard": "Space Turret",
}

# Which terrains a building exists on. Anything absent is on all of them.
#
# This is the one thing about a match a seed can't see. The client forces map
# *size* but never map choice, so `map_terrain` is the player saying which
# they'll play. Everything terrain decides — build checks, the units those
# buildings train, the substituted wonder — is filtered through it. That's what
# lets those checks stay load-bearing instead of being written off as things
# that might not exist.
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
# which does not hold the old unit alongside the new one — it cancels the
# upgrade, and the Archery Range goes back to offering Slingers. So the upgrade
# is left alone and the replacement carries the replaced unit's check instead:
# build a Simple Bowman and Slinger's check goes with it, build a Long Bow and
# all four below it go.
#
# The epoch floors are unaffected. A check's floor is the earliest point it can
# be sent, and that is still the unit's own tier — a Slinger sends Slinger.
LOCATION_ALSO_SENDS: dict[str, tuple[str, ...]] = {}
for _here, _partner in _PAIRED_BUILD_LOCATIONS.items():
    LOCATION_ALSO_SENDS[_here] = (_partner,)

for _db in ALL_RECRUITABLE:
    _here = RECRUIT_LOCATION_BY_DBNAME[_db]
    _also = [PAIRED_LOCATIONS[_here]] if _here in PAIRED_LOCATIONS else []
    # Some superseded units aren't checks at all (scenario props), so the
    # lookup is filtered rather than assumed.
    _also += [loc for loc in map(_recruit_location, UNIT_SUPERSEDES.get(_db, ()))
              if loc is not None]
    if _also:
        LOCATION_ALSO_SENDS[_here] = tuple(dict.fromkeys(_also))

# Location name -> the buildings that can train it. Resolved per unit, so the
# rules never go back to the family — which is what got the Canine Scout
# wrong.
RECRUIT_LOCATION_PRODUCERS: dict[str, tuple[str, ...]] = {
    f"Recruit {UNIT_DISPLAY[db]}": unit_producers(db) for db in ALL_RECRUITABLE
}

# Every check that must never hold anything the seed needs.
#
# Terrain-specific checks aren't here. `map_terrain` says which map you'll
# play, so a check the terrain rules out is left out of the seed entirely
# rather than shipped as something nothing may depend on.
NO_PROGRESSION_LOCATIONS: frozenset[str] = (
    CIV_LOCKED_LOCATIONS
    | frozenset(f"Build {b}" for b in UNCONFIRMED_BUILDINGS
                if f"Build {b}" in BUILD_LOCATIONS)
)

# Location name -> the building that researches it. One building each, so with
# unlocks on a check needs that building as well as the epoch. Printing Press
# is a Renaissance Temple technology, so it can hold neither `Building: Temple`
# nor any epoch up to the Renaissance.
TECH_LOCATION_BUILDING: dict[str, str] = {
    f"Research {name}": building
    for name, (_e, building, _t, _n, _i) in TECHNOLOGIES.items()
}

# (texture, node epoch) -> location, which is how the client turns a researched
# node into a check. Texture alone doesn't identify one — all seven wall and
# tower upgrades share a texture and only the epoch separates them.
TECH_LOCATION_BY_NODE: dict[tuple[str, int], str] = {
    (texture, node_epoch): f"Research {name}"
    for name, (_e, _b, texture, node_epoch, _i) in TECHNOLOGIES.items()
}

# Every match starts you with a Capitol and citizens whatever the epoch, so
# these two are satisfiable immediately and carry no epoch requirement. Without
# it a Prehistoric start has no reachable location at all — nothing else is
# buildable until the Stone Age — and generation has nowhere to put the first
# epoch unlock.
STARTING_LOCATIONS = ("Build Capitol", "Recruit Citizen")
for _name in STARTING_LOCATIONS:
    if _name in LOCATION_MIN_EPOCH:
        LOCATION_MIN_EPOCH[_name] = 0

# Build and recruit checks, regardless of epoch. LOCATION_MIN_EPOCH against
# the goal epoch decides which a seed actually includes.
ALWAYS_LOCATIONS: set[str] = set(BUILD_LOCATIONS) | set(RECRUIT_LOCATIONS)


class EmpireEarthLocation(Location):
    game = "Empire Earth"
