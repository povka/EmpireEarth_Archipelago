import re

from BaseClasses import Location

try:
    from .Epochs import EPOCH_NAMES
    from .Technologies import TECHNOLOGIES
    from .BuildingEpochs import BUILDING_EPOCH
    from .Producers import UNIT_FAMILY_PRODUCERS
    from .Upgrades import UNIT_SUPERSEDES
    from .UnitSlots import SLOT_FIRST_EPOCH, SLOT_PREDECESSORS, UNIT_SLOTS
    from .Objects import (
        BUILDING_MIN_EPOCH,
        BUILDING_TIERS,
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
    from UnitSlots import SLOT_FIRST_EPOCH, SLOT_PREDECESSORS, UNIT_SLOTS
    from Objects import (
        BUILDING_MIN_EPOCH,
        BUILDING_TIERS,
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
# replaces it — which is why they were family checks once. Units retire exactly
# as the game intends now, and the check travels rather than the unit:
#
# - an *upgrade* is carried by the tier above it, so a Long Bow sends every
#   archer below it
# - a *menu position* is carried by whatever takes it next, which is not the
#   same relation — Barracks slot 4 runs Sampson, Viking, Hand Cannoneer,
#   Trench Mortar, Heavy Mortar, and no upgrade connects any of them
#
# Both live in LOCATION_ALSO_SENDS. Obsolescence.py only holds open the
# positions that would otherwise sit empty between occupants.
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
    # Same shape, and this one the game's own assets settle. `Emissary` shares
    # the `Priest` family with the Priest and carries no `x ` prefix, but
    # neither `data.ssa` holds a texture matching `emissar` — while the Priest
    # has four button icons and the Prophet three. No icon, no build button,
    # no way to recruit one. It cost a run: `Epoch: Dark Age` sat on
    # `Recruit Emissary`, in a match with a Temple that only ever offered
    # Priests and Prophets.
    "Emissary",
    # Reported from play, all scenario-only or absent. The Scorpion and the LST
    # Transport have no `x ` prefix and sit in ordinary families; the SAS
    # Explosive Expert has an icon (`but_sasexplosives_11t`) and still appears
    # in no build menu. `Field Medic 13` is the odd one out — it exists and is
    # buildable, and it is the Digital medic under a second name, so keeping
    # both put one unit in a menu position twice.
    "Gun Spear04 Scorpion",
    "Inf10 - SAS Explosive Expert",
    "Inf10 - Radio Man",
    "a Strafe Fighter11 Zero",
    "Field Medic 13",
    "s11 LST Transport",
    # Both Catapult Ships. Scenario-only, reported from play — and the menu
    # listings agree: neither appears in any of the Dock's fourteen rows in
    # tools/data/remaining_slots.tsv, while every other warship of their epochs
    # does. A unit no menu ever draws is a check nobody can send.
    "s04 Bronze Catapult Ship",
    "s06 Middle Age Catapult Ship",
    # `Hovercraft 1` is in the database and in no menu — not the Dock's
    # fourteen rows, not the Naval Yard's six. A seed put the goal behind it.
    "Hovercraft 1",
    # Scenario-only, reported from play. The database name is a bare
    # `a Catalina` with no tier and no `x ` prefix, so nothing marks it out.
    "a Catalina",
    # Carrier aircraft. They come from an aircraft carrier rather than a
    # building, so they appear in no build menu this project models and the
    # producer table can only guess at an Airport they never use.
    "a Carrier Fighter11 Dauntless",
    "a Carrier Fighter11 Zero",
    "a CarrierFighter11 Corsair1",
    "a CarrierFighter12 F-14",
    "a CarrierFighter13 Avenger",
    # Japan's alone, with no equivalent for anyone else — unlike the
    # `(Crusader)` units, which have a plain twin their civilisation fields
    # instead. A check only one civilisation can ever send is one most runs
    # cannot, so it stops being a check rather than sitting there as a dead
    # entry.
    "Inf15 - Cyber Ninja",
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
    # The database runs the two words together and nothing else does — the
    # game's own screen, the wiki and the rest of the sword line all say
    # "Long Sword".
    "Inf06 - LongSword": "Long Sword",
    "Inf06 - LongSword(Crusader)": "Long Sword (Crusader)",
    # Eight names below are chosen over the screen's, on purpose, so don't
    # "correct" them against tools/data: `Bazooka`, `Crossbow`,
    # `Medic - Imperial`, `Field Medic - Digital`, `P51 Fighter`,
    # `Battleship Bismarck`, `Cruiser - Dardo`, `Cruiser - Sagittarian`.
    #
    # The rest are the game's own screen names, read off a vanilla build menu.
    # The database is inconsistent about ships in particular — `s03 Copper
    # Frigate`, `s07 Renaissance Battleship [Galleon]`, `s10 Cruiser` — while
    # every one of them is drawn as `Frigate - Copper`, `Battleship -
    # Renaissance`, `Cruiser - Dardo`. Matching the screen is what makes a hint
    # findable.
    's02 Fishing Boat Stone': 'Fishing Raft',
    's04 Fishing Boat Bronze': 'Fishing Boat - Bronze',
    's02 Stone Transport': 'Transport Raft',
    's03 Copper Transport': 'Transport - Copper',
    's04 Bronze Transport': 'Transport - Bronze',
    's03 Copper Battleship [Galley]': 'Battleship - Copper',
    's04 Bronze Battleship [Pentakonter]': 'Battleship - Bronze',
    's05 Byzantine Battleship [Septrireme]': 'Battleship - Byzantine',
    's02 Stone Frigate [War Raft]': 'War Raft',
    's03 Copper Frigate': 'Frigate - Copper',
    's04 Bronze Frigate': 'Frigate - Bronze',
    's05 Byzantine Frigate': 'Frigate - Byzantine',
    's03 Copper Galley': 'Galley - Copper',
    's04 Bronze Galley': 'Galley - Bronze',
    's05 Byzantine Galley': 'Galley - Byzantine',
    'Gun Spear06 Balistae': 'Ballista',
    'Siege06 - Heavy Tower': 'Heavy Siege Tower',
    's06 Middle Ages Battleship [Decereme]': 'Battleship - Middle Ages',
    's06 Middle Age Frigate': 'Frigate - Middle Ages',
    's06 Middle Age Galley': 'Galley - Middle Ages',
    'Arch05 - Cross Bow': 'Crossbow',
    'Gun Cannon07 - Culverin Cannon': 'Culverin',
    'Gun Siege07 Basilisk Cannon': 'Basilisk',
    's07 Renaissance Battleship [Galleon]': 'Battleship - Renaissance',
    's07 Renaissance Galleon': 'Galleon - Renaissance',
    's08 Fishing Boat Imperial': 'Fishing Boat - Imperial',
    's08 Imperial Transport': 'Transport - Imperial',
    's08 Imperial Battleship': 'Battleship - Imperial',
    's08 Imperial Frigate': 'Frigate - Imperial',
    's08 Imperial Galleon': 'Galleon - Imperial',
    's08 Gunboat Cruiser': 'Cruiser - Gunboat',
    'h1-9 Otto Von Bismarck (heal)': 'Otto von Bismarck',
    'Gun Siege09 Serpentine Cannon': 'Serpentine',
    's09 Royal Battleship': 'Battleship - Royal',
    's09 Royal Frigate': 'Frigate - Royal',
    's09 Royal Galleon': 'Galleon - Royal',
    's10 Atomic Age Transport': 'Transport - Atomic',
    's10 Dreadnought Battleship': 'Battleship - Dreadnought',
    's10 Good Hope Frigate': 'Frigate - Good Hope',
    's10 Cruiser': 'Cruiser - Dardo',
    'a Strafe Fighter10 Fokker DR.1': 'Fokker Fighter/Bomber',
    'a Fighter10 Sopwith Camel F.1': 'Sopwith Fighter',
    'a Bomber 10 Gotha': 'Gotha Bomber',
    'h1-11 Rommel (heal)': 'Erwin Rommel',
    's11 Fishing Boat Modern': 'Fishing Boat - Trawler',
    's11 Bismarck Battleship': 'Battleship Bismarck',
    's11 Warrington': 'Frigate - Warrington',
    'a Strafe Fighter11 ME109': 'ME109 Fighter/Bomber',
    'a Strafe Fighter11 ME262': 'ME262 Fighter/Bomber',
    'a Fighter11 Spitfire': 'Spitfire Fighter',
    'a Fighter11 P51': 'P51 Fighter',
    'a Bomber 11 Heinkel 111': 'Heinkel Bomber',
    'a Bomber 11 B-17': 'B-17 Bomber',
    'a BomberNuc11 B-29': 'B-29 Bomber',
    'a AT Fighter11 Typhoon': 'Typhoon Anti-Tank',
    'Inf11 - Bazooka Infantry': 'Bazooka',
    'Field Medic - Imperial': 'Medic - Imperial',
    'Field Medic 11': 'Medic - Atomic',
    'h1-12 R.W. Bresden (heal)': 'RW Bresden',
    'Gun AT12 120mm At Gun': '120mm AT Gun',
    'a Strafe Fighter12 Stealth Fighter': 'F-117 Fighter/Bomber',
    'a Fighter12 F-15': 'F-15 Fighter',
    'a Bomber 12 Stealth B-2': 'B-2 Bomber',
    'a BomberNuc12 B-52': 'B-52 Bomber',
    'a AT Fighter12 A-10': 'A-10 Anti-Tank',
    'a Helicopter Sea King 12': 'Sea King',
    'a HelicopterXprt12 Chinook Transport 12': 'Helicopter Transport',
    'a Helicopter Apache Longbow 12': 'Helicopter Anti-Tank',
    'a HelicopterGunShip12 Gun Ship': 'Helicopter Gunship',
    'Gun Artillery13 Colossus': 'Colossus Artillery',
    'Field Medic WWII': 'Field Medic - Digital',
    'a Strafe Fighter13 Talon': 'Talon Fighter/Bomber',
    'a Fighter13 F-48 Jackal': 'Jackal Fighter',
    'a Bomber 13 B-122 Wyvern': 'B-122 Wyvern Bomber',
    'a BomberNuc13 Titan': 'Titan Bomber',
    'a HelicopterXprt13 Pegasus': 'Pegasus Transport',
    'a HelicopterAT13 Spectre': 'Spectre AT Helicopter',
    'a HelicopterGunShip13 Reaper': 'Reaper Gunship',
    's13 Digital Fishing Boat': 'Fishing Boat - Digital',
    's13 Leviathon Battleship': 'Battleship - Leviathan',
    's13 Juggernaut Frigate': 'Frigate - Juggernaut',
    's13 Sagitarian Cruiser': 'Cruiser - Sagittarian',
    's13 Gargantua Transport': 'Transport - Gargantua',
    'Tank10  Mk V': 'MkV Tank (HE)',
    'Tank11 Sherman': 'Sherman Tank (HE)',
    'Tank12  M1A1': 'M1 Tank (HE)',
    'Tank13 Gladiator': 'Gladiator Tank',
    '10 AA - Tank': 'Flak Halftrack',
    '13 AA Tank Skywatcher': 'Skywatcher AA',
    'Mech Apollo': 'Apollo',
    'Mech Hyperion': 'Hyperion',
    'Mech Furies': 'Furies',
    'Mech Ares': 'Ares',
    'Mech Tempest': 'Tempest',
    'Mech Pandora': 'Pandora',
    'Mech Minotaur': 'Minotaur',
    's10 U Boat': 'Sub - U-Boat',
    's12 Nautilus Submarine': 'Sub - Nautilus',
    'Mech Ares II': 'Ares II',
    'Mech Hades': 'Hades',
    'Mech Hyperion II': 'Hyperion II',
    'Mech Minotaur II': 'Minotaur II',
    'Mech Pandora II': 'Pandora II',
    'Mech Poseidon': 'Poseidon',
    'Mech Zeus': 'Zeus',
    'Siege04 - Tower': 'Siege Tower',
    'Sp15 - Capital Ship': 'Space Capital Ship',
    'Tank10 A7V': 'A7V Tank (AP)',
    'Tank11 Panzer': 'Panzer Tank (AP)',
    'Tank12 Leopard': 'Leopard Tank (AP)',
    'Tank14 Centurion': 'Centurion Tank',
    'a Fighter14 F-96 Nebula': 'Nebula Fighter',
    'a Helicopter Sea King II 13': 'Sea King II',
    'a Strafe Fighter14 Phoenix': 'Phoenix Fighter/Bomber',
    'h1 - 15 Khan Sun Do (Strategist)': 'Khan Sun Do',
    'h1-7 Isabella (heal)': 'Isabella of Castile',
    'h2 - 15 Hu Kwan Do (Warrior)': 'Hu Kwan Do',
    'h2-10 von Richtofen (Morale)': 'Manfred von Richthofen',
    'h2-11 Shackelford (Morale)': 'Travis Shackelford',
    'h2-12 St. Albans (Morale)': 'Dennis St. Albans',
    's07 Renaissance Frigate': 'Frigate - Renaissance',
    's11 Enterprise Aircraft Carrier': 'Carrier - Enterprise',
    's12 Trident Submarine': 'Sub - Trident',
    's13 Nexus Carrier': 'Carrier - Nexus',
    's14 Hammerhead Submarine': 'Sub - Hammerhead',
    's14 Triton Submarine': 'Sub - Triton',
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


# `a Helicopter Sea King II 13` reads as a database row rather than a unit. The
# leading `a ` marks an aircraft and the trailing number repeats the tier, and
# neither belongs in something the player reads off a check.
_AIR_PREFIX = re.compile(r"^a\s+")
_TRAILING_TIER = re.compile(r"\s+\d+$")


def _tidy_air(name: str) -> str:
    return _TRAILING_TIER.sub("", _AIR_PREFIX.sub("", name)).strip()


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
    if any(c.isalpha() for c in tail):
        return tail
    # Some names put the tier last (`a Helicopter Sea King II 13`), so the
    # general rule strips the leading `a` and leaves a tail of digits. Drop the
    # aircraft marker and the trailing tier from the whole name instead.
    return _tidy_air(db_name) or db_name


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

# Every tier of a defence line reports its own database name — a tower built in
# the Prehistoric Age is `b  Guard Tower - Paleo`, and the Copper upgrade
# renames what you already own to `b  Guard Tower - Copper`. The check is the
# line, so every tier resolves to the base tier's check. Without this an
# upgraded tower stops sending anything, and a run that upgraded before the
# check went out could never send it at all.
_BUILD_LOCATION_BY_BASE = {
    raw: loc for raw, loc in BUILD_LOCATION_BY_DBNAME.items()
}
BUILD_LOCATION_BY_DBNAME.update({
    tier: _BUILD_LOCATION_BY_BASE[base]
    for tier, base in BUILDING_TIERS.items()
    if base in _BUILD_LOCATION_BY_BASE
})

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
    # logic a Naval Yard is no help when it is.
    "a Helicopter Sea King II 13": ("Airport", "Naval Yard"),
    # Two members of the `Space Fighter` family the Space Dock doesn't build,
    # reported from the game: the Airport's Space Age fighter, and a satellite
    # launched from the Capitol.
    "a Fighter15 Planetary Fighter": ("Airport",),
    "spc Spy Satellite": ("Capitol",),

    # A Prophet comes from the Temple, and the database files it under `Human`
    # beside the Rock Thrower and the Trench Mortar — so the family handed it a
    # Barracks. `gen_producers.TEMPLE_UNITS` names it a Temple unit, but that
    # label is per unit and `Producers.py` is emitted per family, so it was
    # lost on the way out.
    #
    # It shipped a seed nobody could finish. `Building: Archery Range` sat on
    # `Recruit Prophet`, which logic thought a Barracks reached in the Stone
    # Age; the Temple that really trains one was behind `Recruit Trench
    # Mortar` in the Atomic Age, and `Epoch: Copper Age` was on
    # `Build Archery Range`. A run got as far as the Stone Age and stopped.
    "Prophet": ("Temple",),

    # The two balloons come from the Capitol, not the Airport. The database
    # files them under `Helicopter` with the gunships and transports, so they
    # inherited the Airport when `gen_producers` dropped the `Balloon` label
    # from the shared Town Center/Capitol table — that fix was right for every
    # helicopter and took the balloons' own producer with it.
    #
    # The menu listings settle it: both appear in the Capitol's rows at epochs
    # 8 to 11 and in none of the Airport's. See tools/data/remaining_slots.tsv.
    "a Balloon09 Hot Air Balloon": ("Capitol", "Town Center"),
    "a Balloon10 Observation Balloon": ("Capitol", "Town Center"),

    # `Siege` and `Land AA` each hold one Barracks infantryman among units
    # built somewhere else entirely, so the family union handed a Barracks to
    # every siege engine and every AA tank. That's the dangerous direction, and
    # it shipped: `Epoch: Dark Age` landed on `Recruit Catapult`, which logic
    # thought a Copper Age Barracks could reach. The Catapult is a Siege
    # Factory unit, `Building: Siege Factory` was behind `Recruit A7V` in the
    # Atomic Age, and the run stopped at the Dark Age with no way forward.
    #
    # Split per unit, because the split is per unit — `Inf02 - Sampson` really
    # is a Barracks unit and really is family `Siege`.
    "Gun Siege04 Catapult": ("Siege Factory",),
    "Gun Siege06 Trebuchet": ("Siege Factory",),
    "Gun Siege07 Basilisk Cannon": ("Siege Factory",),
    "Gun Siege09 Serpentine Cannon": ("Siege Factory",),
    "Gun Siege10 Howitzer Cannon": ("Siege Factory",),
    "Gun Siege13 Paladin Cannon": ("Siege Factory",),
    "Inf02 - Sampson": ("Barracks",),

    # The same shape in `Land AA`. The Stinger Soldier is the Barracks unit —
    # the wiki's Barracks list has it replacing the Bazooka Infantry, which is
    # also why `gen_upgrades.EXTRA_SUPERSEDES` carries that link.
    "10 AA - Tank": ("Tank Factory",),
    "13 AA Tank Skywatcher": ("Tank Factory",),
    "14 Anti Missile Battery": ("Tank Factory",),
    "AA10 - Stinger Soldier": ("Barracks",),
}


def unit_producers(db_name: str) -> tuple[str, ...]:
    """The buildings that can train this unit, per unit rather than per family."""
    override = UNIT_PRODUCER_OVERRIDES.get(db_name)
    if override is not None:
        return override
    return UNIT_FAMILY_PRODUCERS.get(UNIT_FAMILY_BY_NAME.get(db_name, ""), ())


def _producer_epoch(db_name: str) -> int:
    return min((building_epoch(b) for b in unit_producers(db_name)), default=0)


# Three sources, and the latest wins. The database's own figure, the epoch the
# producing building arrives in, and the epoch a vanilla menu first draws the
# unit.
#
# That last one is there because `dbobjects.dat` reads an epoch LOW for three
# units, which is the direction that breaks seeds: logic believes a check is
# reachable before it is, and can hide the epoch item behind it. The Sea King II
# is stored at the Digital Age and not offered until the Nano Age, and a seed
# put `Epoch: Nano Age` on it — you needed the Nano Age to build the helicopter
# that held the Nano Age. Khan Sun Do and Hu Kwan Do are stored an epoch early
# the same way. See UnitSlots.SLOT_FIRST_EPOCH.
LOCATION_MIN_EPOCH.update({
    f"Recruit {UNIT_DISPLAY[db]}": max(
        UNIT_MIN_EPOCH.get(
            db, UNIT_FAMILY_MIN_EPOCH.get(UNIT_FAMILY_BY_NAME[db], 0)),
        _producer_epoch(db),
        SLOT_FIRST_EPOCH.get(db, 0),
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
#
# The four `(Crusader)` units are the same thing with a clearer tell: each sits
# at the same tier and in the same family as a plain twin, which is what a
# civilisation replacement looks like in this database. A run reached the
# Bronze Age with two `Inf04 - Short Sword` in the roster and
# `Epoch: Middle Ages` sitting on `Recruit Short Sword(Crusader)`, which is a
# different unit the same building never offered.
CIV_LOCKED_UNITS: tuple[str, ...] = (
    "Cav04 - Bronze Spear Cavalry(Crusader)",
    "Cav06 - Knight(Crusader)",
    "Inf04 - Short Sword(Crusader)",
    "Inf06 - LongSword(Crusader)",
)

# Each variant and the unit it stands in for, so the pair carries each other's
# checks. Both ways, because a civilisation fields one or the other and never
# both — a Crusader has no plain Short Sword to send with.
#
# The tier above used to carry them, which is the wrong relation and it showed:
# `Recruit Long Sword` sent `Recruit Short Sword(Crusader)` two epochs after the
# Crusader's own floor, and `Recruit Long Sword (Crusader)` had no sender at all
# because nothing supersedes it. Same fix as FLAMING_VARIANTS below, same
# reason: the thing that stands in for a unit is its twin at the same tier, not
# whatever replaces it later.
CIV_VARIANTS: dict[str, str] = {
    "Cav04 - Bronze Spear Cavalry": "Cav04 - Bronze Spear Cavalry(Crusader)",
    "Cav06 - Knight": "Cav06 - Knight(Crusader)",
    "Inf04 - Short Sword": "Inf04 - Short Sword(Crusader)",
    "Inf06 - LongSword": "Inf06 - LongSword(Crusader)",
}

# The `(Flaming)` archers, and the archer each one is a version of.
#
# They arrive from the Archery Range's flaming-arrow upgrade rather than from a
# build button, so they used to be excluded — a requirement the rules can't see
# stranded three runs. Then the upgrade cascade carried them, which is worse
# than it sounds: a Composite Bow sent `Recruit Simple Bowman(Flaming)`, so the
# check needed a tier you might never reach, and a seed that ends the epoch
# before the Composite Bow could never send it at all.
#
# A flaming archer is the same archer with a different arrow, so the plain one
# sends both. That makes the variant exactly as reachable as its base, which is
# why they are ordinary checks again rather than excluded ones.
FLAMING_VARIANTS: dict[str, str] = {
    "Arch03 - Simple Bowman": "Arch03 - Simple Bowman(Flaming)",
    "Arch05 - Composite Bow": "Arch05 - Composite Bow(Flaming)",
    "Arch06 - Long Bow": "Arch06 - Long Bow(Flaming)",
}

UPGRADE_LOCKED_UNITS: tuple[str, ...] = ()

# Units whose check closes for good and can't be held open.
#
# A menu position that empties and never refills takes its check with it. Most
# of those are fixed by holding the unit open past its expiry — see
# UnitSlots.SLOT_GAPS — which works because a position nothing else wants can't
# be squatted.
#
# The galleons defeat it. All three tiers hang off one node, `but_galleon_07`,
# whose expiry already reads 15, so there is nothing to write: the Royal Galleon
# is hidden by something other than expiry. Dock position 6 runs galley tiers to
# the Renaissance, Imperial and Royal Galleons, and is empty from Atomic Age -
# WWI on. Excluded on the same terms as a civilisation variant — real, sendable
# in the Industrial Age, and never carrying the run.
SLOT_CLOSED_UNITS: tuple[str, ...] = (
    "s09 Royal Galleon",
)

# The same as location names, for the world to mark EXCLUDED. Filtered through
# the lookup so a name that stops being a check can't leave a stale entry.
CIV_LOCKED_LOCATIONS: frozenset[str] = frozenset(
    RECRUIT_LOCATION_BY_DBNAME[db]
    for db in CIV_LOCKED_UNITS + UPGRADE_LOCKED_UNITS + SLOT_CLOSED_UNITS
    if db in RECRUIT_LOCATION_BY_DBNAME
)

# Buildings that are real, and buildable only in some matches.
#
# A tech tree node and a measured epoch say a building exists, not that this
# match can raise one. An entry here stays a check and stops being
# load-bearing: sendable if a match offers it, harmless if not.
#
# Empty, and both former entries left in different directions. The Space Dock
# and Space Turret turned out to be a *map* dependency — both appear on a
# `Planets` map — and moved to BUILDING_TERRAINS below. The Pyramid turned out
# to be offered by nothing at all, at which point demoting a check nobody can
# send is worse than not generating it, so it moved to the exclusions in
# tools/gen_objects.py and stopped being a building.
UNCONFIRMED_BUILDINGS: tuple[str, ...] = ()

# Buildings that *replace* another on some maps rather than joining it.
#
# A `Planets` map has no Dock and no Naval Yard — the Space Dock and Space
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
    "Naval Yard": "Space Turret",
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
    "Naval Yard": frozenset({LAND_AND_WATER}),
    "Space Dock": frozenset({SPACE}),
    "Space Turret": frozenset({SPACE}),
}

# A space map swaps two wonders as well as two buildings: the Future Research
# Sentinel stands where the Coliseum does everywhere else. A land seed offered
# the Sentinel, which no such match can build.
WONDER_TERRAINS: dict[str, frozenset[str]] = {
    "Coliseum": frozenset({LAND_ONLY, LAND_AND_WATER}),
    "Future Research Sentinel": frozenset({SPACE}),
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
# Buildings share build-menu positions the way units do, and only two ever
# change hands: the Airport takes the Archery Range's, the Tank Factory takes
# the Stable's. Read off a vanilla game across all fifteen epochs; see
# tools/data/building_slots.tsv.
BUILDING_SUCCESSORS: dict[str, str] = {
    "Archery Range": "Airport",
    "Stable": "Tank Factory",
}

_CIV_PLAIN_BY_VARIANT: dict[str, str] = {v: k for k, v in CIV_VARIANTS.items()}
_CIV_VARIANT_UNITS: frozenset[str] = frozenset(CIV_VARIANTS.values())

LOCATION_ALSO_SENDS: dict[str, tuple[str, ...]] = {}
for _here, _partner in _PAIRED_BUILD_LOCATIONS.items():
    LOCATION_ALSO_SENDS[_here] = (_partner,)

# A building that takes another's position carries its check, and so does
# everything it trains. The slot cascade is per position; this is per building,
# and deliberately more generous — once the Airport is up, an Archery Range can
# never be built again, so *any* aircraft has to be able to send *any* archer's
# check or those checks are stranded. Extra sends cost a free check; a missing
# one costs the run.
for _earlier, _later in BUILDING_SUCCESSORS.items():
    _a, _b = f"Build {_earlier}", f"Build {_later}"
    if _a in BUILD_LOCATIONS and _b in BUILD_LOCATIONS:
        LOCATION_ALSO_SENDS[_b] = tuple(
            dict.fromkeys(LOCATION_ALSO_SENDS.get(_b, ()) + (_a,)))

# Which building position each unit occupies, for filtering the upgrade
# cascade below.
_SEATS: dict[str, set[tuple[str, int]]] = {}
for _b, _seats in UNIT_SLOTS.items():
    for _n, _seat in enumerate(_seats):
        for _member in _seat:
            _SEATS.setdefault(_member, set()).add((_b, _n))


def _same_seat(later: str, earlier: str) -> bool:
    """Do these two ever share a build-menu position?

    True when either is missing from the tables, because a unit with no
    observed position can't be shown to be somewhere else, and dropping its
    cascade on a guess is how a check goes missing.
    """
    a, b = _SEATS.get(later), _SEATS.get(earlier)
    return not a or not b or bool(a & b)


for _db in ALL_RECRUITABLE:
    _here = RECRUIT_LOCATION_BY_DBNAME[_db]
    _also = [PAIRED_LOCATIONS[_here]] if _here in PAIRED_LOCATIONS else []
    # Only where the two share a menu position. `dbobjects.dat` calls the
    # Bazooka a replacement for the Hand Cannoneer and the Sharpshooter, which
    # the menu flatly contradicts — the Bazooka is Barracks slot 3, the Hand
    # Cannoneer slot 4, the Sharpshooter slot 5, and all three are drawn at
    # once. An upgrade that replaces a unit does so in place, so a pair in two
    # different positions isn't one. 32 of the 303 pairs go this way.
    #
    # Safe to drop because the position still carries the check: whatever takes
    # slot 4 next sends the Hand Cannoneer's. `run_dead_slots` is what proves
    # it, and it covers the positions nothing takes next.
    #
    # Some superseded units aren't checks at all (scenario props), so the
    # lookup is filtered rather than assumed.
    _also += [loc for loc in
              map(_recruit_location,
                  (u for u in UNIT_SUPERSEDES.get(_db, ())
                   if _same_seat(_db, u) and u not in _CIV_VARIANT_UNITS))
              if loc is not None]
    # And everything that held this unit's menu position before it. A slot is
    # not the upgrade chain — Barracks slot 4 runs Sampson, Viking, Hand
    # Cannoneer, Trench Mortar, Heavy Mortar, and no upgrade connects any of
    # them — but it is what decides whether a unit is still offered. When the
    # next line takes the position the one before it is gone for the rest of
    # the match, so its check has to travel with the slot or it stops being
    # sendable. See UnitSlots.py.
    _also += [loc for loc in map(_recruit_location, SLOT_PREDECESSORS.get(_db, ()))
              if loc is not None]
    # A plain archer sends its flaming version, because they are one unit with
    # two arrows. See FLAMING_VARIANTS.
    if _db in FLAMING_VARIANTS:
        _flaming = _recruit_location(FLAMING_VARIANTS[_db])
        if _flaming is not None:
            _also.append(_flaming)
    # A unit and the civilisation variant that stands in for it, each way. See
    # CIV_VARIANTS.
    for _twin in (CIV_VARIANTS.get(_db), _CIV_PLAIN_BY_VARIANT.get(_db)):
        if _twin:
            _loc = _recruit_location(_twin)
            if _loc is not None:
                _also.append(_loc)
    if _also:
        LOCATION_ALSO_SENDS[_here] = tuple(dict.fromkeys(_also))

# The same, per unit. Built after the loop above so it can extend what the
# slot and upgrade cascades already put there.
_BY_BUILDING: dict[str, list[str]] = {}
for _db in ALL_RECRUITABLE:
    for _b in unit_producers(_db):
        _BY_BUILDING.setdefault(_b, []).append(_db)

for _earlier, _later in BUILDING_SUCCESSORS.items():
    _olds = [_recruit_location(d) for d in _BY_BUILDING.get(_earlier, ())]
    _olds = [x for x in _olds if x is not None]
    for _db in _BY_BUILDING.get(_later, ()):
        _here = _recruit_location(_db)
        if _here is None or not _olds:
            continue
        LOCATION_ALSO_SENDS[_here] = tuple(
            dict.fromkeys(LOCATION_ALSO_SENDS.get(_here, ()) + tuple(_olds)))

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

# The four checks you can send in the first thirty seconds, reserved for things
# the seed needs.
#
# A match starts with a Capitol and the units it makes, so these are sendable
# before you have done anything at all — no epoch, no unlock, no building. Fill
# treats them as ordinary checks otherwise, and a run that opens with four
# resource bundles has nothing to do with them.
#
# `PRIORITY` is a preference, not a guarantee: fill takes progression items for
# these first and falls back to whatever is left if it runs out. With over a
# hundred progression items against four locations that doesn't come up.
PRIORITY_LOCATIONS: frozenset[str] = frozenset({
    "Build Capitol",
    "Recruit Citizen",
    "Recruit Female Citizen",
    "Recruit Canine Scout",
})

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
