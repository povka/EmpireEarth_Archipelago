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
ITEM_TABLE: dict[str, tuple[int, ItemClassification, ResourceId | None]] = {
    "Food Bundle": (0, ItemClassification.progression, ResourceId.FOOD),
    "Wood Bundle": (1, ItemClassification.progression, ResourceId.WOOD),
    "Stone Bundle": (2, ItemClassification.progression, ResourceId.STONE),
    "Gold Bundle": (3, ItemClassification.progression, ResourceId.GOLD),
    "Iron Bundle": (4, ItemClassification.progression, ResourceId.IRON),
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
