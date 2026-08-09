from enum import IntEnum

from BaseClasses import Item, ItemClassification


BASE_ID = 8_950_000


class ResourceId(IntEnum):
    """Index of each resource inside the in-game player resource array."""

    FOOD = 0
    WOOD = 1
    STONE = 2
    GOLD = 3
    IRON = 4


# item name -> (offset from BASE_ID, classification, resource granted or None)
#
# Bundles are `filler`, not progression. No rule asks for one and nothing
# becomes reachable because you have more wood.
#
# That's not cosmetic. Progression balancing only moves progression items, so
# calling ~40 bundles progression spent the entire budget on items that change
# nothing, while the 14 unlocks that actually gate a run competed with them for
# attention. It also made the fill treat every bundle as a constrained
# placement, and told other worlds our filler was worth prioritising.
ITEM_TABLE: dict[str, tuple[int, ItemClassification, ResourceId | None]] = {
    "Food Bundle": (0, ItemClassification.filler, ResourceId.FOOD),
    "Wood Bundle": (1, ItemClassification.filler, ResourceId.WOOD),
    "Stone Bundle": (2, ItemClassification.filler, ResourceId.STONE),
    "Gold Bundle": (3, ItemClassification.filler, ResourceId.GOLD),
    "Iron Bundle": (4, ItemClassification.filler, ResourceId.IRON),
}

# The five resource bundles, before epoch unlocks are appended below.
RESOURCE_ITEM_NAMES = tuple(ITEM_TABLE)

try:
    from .Epochs import EPOCH_NAMES
except ImportError:  # loaded as a top-level module by tools/
    from Epochs import EPOCH_NAMES

# One unlock per epoch you can advance INTO, so everything after the first.
# Receiving `Epoch: Stone Age` is what lets you press Advance in the Capitol.
EPOCH_ITEM_BASE = 100
EPOCH_ITEMS: dict[str, int] = {
    f"Epoch: {name}": i for i, name in enumerate(EPOCH_NAMES) if i >= 1
}

for _name, _idx in EPOCH_ITEMS.items():
    ITEM_TABLE[_name] = (EPOCH_ITEM_BASE + _idx, ItemClassification.progression, None)

# AP item id -> epoch index, consumed by the client.
ITEM_ID_TO_EPOCH = {
    BASE_ID + EPOCH_ITEM_BASE + idx: idx for idx in EPOCH_ITEMS.values()
}

try:
    from .Objects import BUILDINGS, WONDERS
    from .BuildingEpochs import BUILDING_EPOCH
except ImportError:  # loaded as a top-level module by tools/
    from Objects import BUILDINGS, WONDERS
    from BuildingEpochs import BUILDING_EPOCH

# Buildings that can't be gated, and why:
#
# - **Capitol** — every match starts with one, so the unlock would do nothing,
#   and locking it leaves a run with no way to make citizens.
# - **Farm** — no tech tree node the client can reach. The only node whose icon
#   mentions a farm is `but_farm_15t`, an epoch 14 variant, so there's nothing
#   to clear. Shipping the item would promise a lock that never happens.
# - **Town Center** — not built at all. You garrison five citizens in a
#   Settlement and it becomes one, so there's no button to hold shut. The
#   Settlement is what gates it, via BUILDING_PREREQS below.
ALWAYS_BUILDABLE = ("Capitol", "Farm", "Town Center")

# Buildings reached through another building rather than a build menu. The
# requirement is real even with no unlock of their own.
BUILDING_PREREQS: dict[str, str] = {
    "Town Center": "Settlement",
}

# Ids run over every building, gated or not, so excluding one never shifts
# another's id and invalidates existing seeds.
_ALL_BUILDINGS: tuple[str, ...] = tuple(
    display for _raw, display in sorted(BUILDINGS.items())
)
# Gated buildings, restricted to those with an epoch measured from the running
# tech tree. An unlock for anything else gates nothing: the client finds a
# node by icon and the epoch says where the check sits, and neither exists for
# a building the sweep has never seen. Art of Conquest adds ten such, and
# without this they arrived as progression items that did nothing while taking
# places in the pool from items that do.
#
# Map substitutes aren't gated either. Whether a match has a Dock or a Space
# Dock is the map's decision, which the seed never made, so an unlock naming
# one would gate a building half of all matches don't have. The pair still
# sends both checks; see Locations.BUILDING_PAIRS.
MAP_SUBSTITUTE_BUILDINGS = frozenset({"Space Dock", "Space Turret"})

LOCKABLE_BUILDINGS: tuple[str, ...] = tuple(
    b for b in _ALL_BUILDINGS
    if b not in ALWAYS_BUILDABLE
    and b in BUILDING_EPOCH
    and b not in MAP_SUBSTITUTE_BUILDINGS
)

# Only in the pool when the building_unlocks option is on.
UNLOCK_ITEM_BASE = 200

# A constant because four places across three modules build this name, plus
# the test harness. A prefix that drifts in one of them produces an item
# nothing recognises — `create_item` raises on a name absent from ITEM_TABLE,
# but a rule referring to the old name is silently never satisfiable.
BUILDING_ITEM_PREFIX = "Building: "


def building_item(display: str) -> str:
    """The item name that unlocks this building."""
    return f"{BUILDING_ITEM_PREFIX}{display}"


for _n, _display in enumerate(_ALL_BUILDINGS):
    if _display in LOCKABLE_BUILDINGS:
        ITEM_TABLE[building_item(_display)] = (
            UNLOCK_ITEM_BASE + _n, ItemClassification.progression, None,
        )

# AP item id -> building the client should make buildable.
ITEM_ID_TO_BUILDING = {
    BASE_ID + UNLOCK_ITEM_BASE + n: display
    for n, display in enumerate(_ALL_BUILDINGS)
    if display in LOCKABLE_BUILDINGS
}

# Wonders are gated the same way and by the same option, but they aren't
# checks — building one sends nothing. That's deliberate: under a wonder goal
# the wonder is the goal, so the item is the reward and raising it is the use
# of it, rather than both at once.
#
# Their own id block, so adding a wonder never renumbers a building. Ids run
# over every wonder, gated or not, for the same reason.
WONDER_UNLOCK_ITEM_BASE = 300

WONDER_ITEM_PREFIX = "Wonder: "

_ALL_WONDERS: tuple[str, ...] = tuple(
    display for _raw, (display, _epoch) in sorted(WONDERS.items())
)


def wonder_item(display: str) -> str:
    """The item name that unlocks this wonder."""
    return f"{WONDER_ITEM_PREFIX}{display}"


for _n, _display in enumerate(_ALL_WONDERS):
    ITEM_TABLE[wonder_item(_display)] = (
        WONDER_UNLOCK_ITEM_BASE + _n, ItemClassification.progression, None,
    )

# AP item id -> wonder the client should make buildable. Kept apart from the
# building map: same gating mechanism, different purpose in the client.
ITEM_ID_TO_WONDER = {
    BASE_ID + WONDER_UNLOCK_ITEM_BASE + n: display
    for n, display in enumerate(_ALL_WONDERS)
}

try:
    from .Technologies import TECHNOLOGIES
except ImportError:  # loaded as a top-level module by tools/
    from Technologies import TECHNOLOGIES

# One item per technology, carrying the benefit researching it would have
# given. Researching sends the check and is deliberately left with no effect,
# so this is where the benefit comes from.
#
# `useful`, not `progression` — no rule asks for one. A technology makes your
# citizens quicker or your priests tougher; none is the difference between a
# check being reachable and not.
TECH_ITEM_BASE = 400
_TECHS_ORDERED = tuple(sorted(TECHNOLOGIES))

for _n, _tech in enumerate(_TECHS_ORDERED):
    ITEM_TABLE[f"Tech: {_tech}"] = (
        TECH_ITEM_BASE + _n, ItemClassification.useful, None,
    )

TECH_ITEMS: tuple[str, ...] = tuple(f"Tech: {t}" for t in _TECHS_ORDERED)

# AP item id -> technology, consumed by the client to apply the benefit.
ITEM_ID_TO_TECH = {
    BASE_ID + TECH_ITEM_BASE + n: tech for n, tech in enumerate(_TECHS_ORDERED)
}

ITEM_NAME_TO_ID = {name: BASE_ID + off for name, (off, _c, _r) in ITEM_TABLE.items()}
ITEM_ID_TO_NAME = {v: k for k, v in ITEM_NAME_TO_ID.items()}

# Consumed by the client: AP item id -> resource index to credit.
ITEM_ID_TO_RESOURCE = {
    BASE_ID + off: int(res)
    for _n, (off, _c, res) in ITEM_TABLE.items()
    if res is not None
}


class EmpireEarthItem(Item):
    game = "Empire Earth"
