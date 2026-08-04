"""Enforce the skirmish setup settings the seed was generated for.

Every dropdown on the skirmish setup screen is a plain int32 at a fixed address
in the executable's .data section, and the five checkboxes are single bytes.
Empire Earth has no ASLR and a fixed image base, so these addresses are stable
across launches.

    0x0093160C  (map type - see below, NOT enforced)
    0x00931630  Game Speed        0 Slow .. 3 Very Fast
    0x00931638  Map Size          0 Tiny .. 5 Gigantic
    0x0093163C  Starting Epoch    0 Prehistoric .. 14 Space
    0x00931640  Ending Epoch      0 .. 14
    0x00931644  Game Variant      1 Tournament, 2 Standard   (note: not 0-based)
    0x00931648  Resources         0 Tournament-Low .. 4 Deathmatch
    0x0093164C  Game Unit Limit   literal, 50..1200 in steps of 50
    0x00931650  Wonders To Win    literal, 0 (off) .. 6
    0x00931654  Difficulty        0 Easy, 1 Medium, 2 Hard
    0x0093165D  Lock Teams        0 or 1
    0x0093165E  Lock Speed        0 or 1
    0x0093165F  Reveal Map        0 or 1
    0x00931660  Cheat Codes       0 or 1
    0x00931662  Use Custom Civs   0 or 1
    0x0093165C  Victory Allowed   0 or 1  (not on the setup screen; see below)

The checkbox bytes are NOT in screen order, are not contiguous, and the run of
bytes they sit in holds things that are not checkboxes: 0x0093165C reacts to
nothing on the setup screen, so it is never written. Each box was confirmed by
toggling it on its own and seeing which byte moved
(tools/watch_checkboxes.py) - the top-to-bottom order looked obvious and was
wrong for every one of the five.

Map Type is deliberately absent. The field at 0x0093160C tracks it but is a
derived property rather than the selector - Large Islands and Planets Earth
both settle at 13, Planets Mars and Planets Small both at 18 - so writing it
would not select a map.

Values were recovered by setting every dropdown to a distinct value and reading
the block back; see notes/REVERSE.md.
"""

from __future__ import annotations

# --- addresses -------------------------------------------------------------

GAME_SPEED = 0x00931630
MAP_SIZE = 0x00931638
STARTING_EPOCH = 0x0093163C
ENDING_EPOCH = 0x00931640
GAME_VARIANT = 0x00931644
RESOURCES = 0x00931648
UNIT_LIMIT = 0x0093164C
WONDERS = 0x00931650
DIFFICULTY = 0x00931654

# Start of the run of bytes the checkboxes live in. Only used by the tooling
# that maps them; nothing writes relative to it.
CHECKBOX_BASE = 0x0093165C

# Not a checkbox and not on the setup screen at all, which is why toggling
# every box left this byte alone. It is a registry-backed game option
# (HKCU\Software\Mad Doc Software\EE-AOC\Game Options, "Victory Allowed"),
# read at startup with a default of 1.
#
# Found by disassembly rather than by scanning: the loader at 0x00535780 reads
# the options into consecutive bytes of one global, and the offsets it uses for
# Lock Teams (+0x405), Lock Speed (+0x406) and Cheat Codes (+0x408) all resolve
# against base 0x00931258 to the addresses those checkboxes were empirically
# found at. "Victory Allowed" is +0x404 of the same object.
#
# Held at 0 so the game cannot end the match on its own. Without it a run dies
# early three ways that have nothing to do with the seed's goal: you wipe the
# AI, the AI wipes you, or someone completes a wonder victory. The wonder goal
# is unaffected because the client counts wonders itself.
VICTORY_ALLOWED = 0x0093165C

# name -> address. Each was confirmed by toggling that box alone; they are not
# in screen order, are not contiguous, and the run they sit in contains
# non-checkbox bytes, so they are addressed individually rather than by
# position.
CHECKBOXES: dict[str, int] = {
    "lock_teams": 0x0093165D,
    "lock_speed": 0x0093165E,
    "reveal_map": 0x0093165F,
    "cheat_codes": 0x00931660,
    "use_custom_civs": 0x00931662,
    # Not a checkbox, but the same shape - a single 0/1 byte in the same block -
    # so it rides the same read/write path.
    "victory_allowed": VICTORY_ALLOWED,
}

# name -> (address, human label). Ints only; checkboxes are handled separately.
FIELDS: dict[str, tuple[int, str]] = {
    "game_speed": (GAME_SPEED, "Game Speed"),
    "map_size": (MAP_SIZE, "Map Size"),
    "starting_epoch": (STARTING_EPOCH, "Starting Epoch"),
    "ending_epoch": (ENDING_EPOCH, "Ending Epoch"),
    "game_variant": (GAME_VARIANT, "Game Variant"),
    "resources": (RESOURCES, "Resources"),
    "unit_limit": (UNIT_LIMIT, "Game Unit Limit"),
    "wonders": (WONDERS, "Wonders To Win"),
    "difficulty": (DIFFICULTY, "Difficulty"),
}

# --- value tables ----------------------------------------------------------

MAP_SIZES = ("Tiny", "Small", "Medium", "Large", "Huge", "Gigantic")
RESOURCE_SETS = (
    "Tournament - Low", "Tournament - Defensive",
    "Standard - Low", "Standard - High", "Deathmatch",
)
DIFFICULTIES = ("Easy", "Medium", "Hard")
GAME_SPEEDS = ("Slow", "Standard", "Fast", "Very Fast")
# The one setting that is not 0-based.
GAME_VARIANTS = {1: "Tournament", 2: "Standard"}
VARIANT_TO_VALUE = {"tournament": 1, "standard": 2}

UNIT_LIMIT_MIN, UNIT_LIMIT_MAX, UNIT_LIMIT_STEP = 50, 1200, 50

# Sanity bounds: a write is refused if the desired value is out of range, so a
# bad option can never poke an arbitrary number into the game.
LIMITS: dict[str, tuple[int, int]] = {
    "game_speed": (0, len(GAME_SPEEDS) - 1),
    "map_size": (0, len(MAP_SIZES) - 1),
    "starting_epoch": (0, 14),
    "ending_epoch": (0, 14),
    "game_variant": (1, 2),
    "resources": (0, len(RESOURCE_SETS) - 1),
    "unit_limit": (UNIT_LIMIT_MIN, UNIT_LIMIT_MAX),
    "wonders": (0, 6),
    "difficulty": (0, len(DIFFICULTIES) - 1),
}


def describe(name: str, value: int) -> str:
    """Human-readable form of a raw setting value."""
    if name in CHECKBOXES:
        return "on" if value else "off"
    table = {
        "map_size": MAP_SIZES,
        "resources": RESOURCE_SETS,
        "difficulty": DIFFICULTIES,
        "game_speed": GAME_SPEEDS,
    }.get(name)
    if table and 0 <= value < len(table):
        return table[value]
    if name == "game_variant":
        return GAME_VARIANTS.get(value, str(value))
    if name in ("starting_epoch", "ending_epoch"):
        try:
            from .Epochs import EPOCH_NAMES
        except ImportError:
            from Epochs import EPOCH_NAMES
        if 0 <= value < len(EPOCH_NAMES):
            return EPOCH_NAMES[value]
    if name == "wonders":
        return "Off" if value == 0 else str(value)
    return str(value)


class MatchSettings:
    """Reads and enforces the skirmish setup block."""

    def __init__(self, proc):
        self.proc = proc

    # --- reading ---------------------------------------------------------

    def read(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for name, (addr, _label) in FIELDS.items():
            v = self.proc.read_i32(addr)
            if v is not None:
                out[name] = v
        for name, addr in CHECKBOXES.items():
            raw = self.proc.read(addr, 1)
            if raw:
                out[name] = raw[0]
        return out

    def plausible(self) -> bool:
        """True if the block currently holds values that make sense.

        Guards against writing into a process whose layout is not what we
        expect - every int field must already be inside its own valid range.
        """
        cur = self.read()
        if not cur:
            return False
        for name, (lo, hi) in LIMITS.items():
            v = cur.get(name)
            if v is None or not (lo <= v <= hi):
                return False
        return True

    # --- writing ---------------------------------------------------------

    def apply(self, desired: dict[str, int]) -> list[str]:
        """Force the block to `desired`. Returns labels of anything corrected.

        Only fields present in `desired` are touched, and only when they differ,
        so this is cheap to call on every poll.
        """
        changed: list[str] = []
        if not self.plausible():
            return changed

        for name, want in desired.items():
            if name in FIELDS:
                lo, hi = LIMITS[name]
                if not (lo <= want <= hi):
                    continue
                addr, label = FIELDS[name]
                cur = self.proc.read_i32(addr)
                if cur == want:
                    continue
                if self.proc.write_value(addr, "i32", want):
                    changed.append(
                        f"{label}: {describe(name, cur)} -> {describe(name, want)}"
                    )
            elif name in CHECKBOXES:
                addr = CHECKBOXES[name]
                raw = self.proc.read(addr, 1)
                cur = raw[0] if raw else None
                want_b = 1 if want else 0
                if cur is None or cur == want_b:
                    continue
                if self.proc.write(addr, bytes([want_b])):
                    label = name.replace("_", " ").title()
                    changed.append(f"{label}: {'on' if cur else 'off'} -> "
                                   f"{'on' if want_b else 'off'}")
        return changed


def clamp_unit_limit(value: int) -> int:
    """Round to the nearest selectable unit limit."""
    value = max(UNIT_LIMIT_MIN, min(UNIT_LIMIT_MAX, int(value)))
    return int(round(value / UNIT_LIMIT_STEP)) * UNIT_LIMIT_STEP
