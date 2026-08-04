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
# Resource bundles are `filler`, not progression: no rule anywhere asks for one,
# and nothing in the game becomes reachable because you have more wood. Only the
# epoch unlocks below gate anything.
#
# The distinction is not cosmetic. Progression balancing only moves progression
# items, so classifying ~40 bundles as progression spent its whole budget on
# items that change nothing, while the 14 unlocks that actually gate a run - in
# a world where epoch N needs every epoch before it - competed with them for
# attention. It also made the fill treat every bundle as a constrained
# placement, and told other players' worlds that our filler was worth
# prioritising.
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

# One unlock per epoch you can advance INTO, i.e. everything after the first.
# Receiving "Epoch: Stone Age" is what lets you press Advance in the Capitol.
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
    from .Objects import BUILDINGS
except ImportError:  # loaded as a top-level module by tools/
    from Objects import BUILDINGS

# Buildings that cannot be gated, and why:
#
# Capitol     - every match starts with one, so the unlock would do nothing,
#   and locking it would leave a run with no way to make citizens.
# Farm        - it has no tech tree node the client can reach. The only node
#   whose icon mentions a farm is `but_farm_15t`, an epoch 14 variant; there is
#   no node for the ordinary Farm at any epoch below that, so there is nothing
#   to clear. Shipping the item anyway would promise a lock that never happens.
# Town Center - it is not built at all. You garrison five citizens in a
#   Settlement and it becomes one, so there is no build button to hold shut.
#   What actually gates it is the Settlement, via BUILDING_PREREQS below.
ALWAYS_BUILDABLE = ("Capitol", "Farm", "Town Center")

# Buildings you reach through another building rather than from a build menu.
# The requirement is real even though no unlock of their own exists.
BUILDING_PREREQS: dict[str, str] = {
    "Town Center": "Settlement",
}

# Ids are assigned over every building, gated or not, so that excluding one
# never shifts another's id and invalidates existing seeds.
_ALL_BUILDINGS: tuple[str, ...] = tuple(
    display for _raw, display in sorted(BUILDINGS.items())
)
LOCKABLE_BUILDINGS: tuple[str, ...] = tuple(
    b for b in _ALL_BUILDINGS if b not in ALWAYS_BUILDABLE
)

# Only in the pool when the building_unlocks option is on.
UNLOCK_ITEM_BASE = 200
UNLOCK_ITEMS: dict[str, str] = {
    f"Unlock: {display}": display for display in LOCKABLE_BUILDINGS
}

for _n, _display in enumerate(_ALL_BUILDINGS):
    if _display in LOCKABLE_BUILDINGS:
        ITEM_TABLE[f"Unlock: {_display}"] = (
            UNLOCK_ITEM_BASE + _n, ItemClassification.progression, None,
        )

# AP item id -> building the client should make buildable.
ITEM_ID_TO_BUILDING = {
    BASE_ID + UNLOCK_ITEM_BASE + n: display
    for n, display in enumerate(_ALL_BUILDINGS)
    if display in LOCKABLE_BUILDINGS
}

try:
    from .Technologies import TECHNOLOGIES
except ImportError:  # loaded as a top-level module by tools/
    from Technologies import TECHNOLOGIES

# One item per technology, carrying the benefit researching it would have given.
# Researching sends the check and is deliberately left with no effect, so this
# is where the benefit actually comes from.
#
# `useful`, not `progression`: no rule anywhere asks for one. A technology makes
# your citizens quicker or your priests tougher; none of them is the difference
# between a check being reachable and not.
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
