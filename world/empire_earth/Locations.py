from BaseClasses import Location

try:
    from .Epochs import EPOCH_NAMES
    from .Objects import BUILDINGS, UNIT_FAMILIES
except ImportError:  # loaded as a top-level module by tools/
    from Epochs import EPOCH_NAMES
    from Objects import BUILDINGS, UNIT_FAMILIES

BASE_ID = 8_950_000

# Id blocks are kept apart so new checks of one kind never shift another kind's
# ids, which would invalidate existing seeds.
EPOCH_LOCATION_BASE = 100
BUILD_LOCATION_BASE = 200
RECRUIT_LOCATION_BASE = 300

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

# One check per unit family, so a check cannot expire when its member units are
# replaced in a later epoch.
RECRUIT_LOCATIONS: dict[str, int] = {
    f"Recruit {family}": BASE_ID + RECRUIT_LOCATION_BASE + n
    for n, family in enumerate(UNIT_FAMILIES)
}

LOCATION_TABLE: dict[str, int] = {
    **EPOCH_LOCATIONS,
    **BUILD_LOCATIONS,
    **RECRUIT_LOCATIONS,
}
LOCATION_NAME_TO_ID = dict(LOCATION_TABLE)
LOCATION_ID_TO_NAME = {v: k for k, v in LOCATION_NAME_TO_ID.items()}

# Lookups the client uses to turn what the player owns into a check.
BUILD_LOCATION_BY_DBNAME: dict[str, str] = {
    raw: f"Build {display}" for raw, display in _BUILDINGS_ORDERED
}
RECRUIT_LOCATION_BY_FAMILY: dict[str, str] = {
    family: f"Recruit {family}" for family in UNIT_FAMILIES
}

# Checks that do not depend on the goal epoch.
ALWAYS_LOCATIONS: set[str] = set(BUILD_LOCATIONS) | set(RECRUIT_LOCATIONS)


class EmpireEarthLocation(Location):
    game = "Empire Earth"
