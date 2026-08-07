"""Per-build memory layout for Empire Earth.

Every EE executable is 32-bit with a fixed image base of 0x400000 and no ASLR,
so addresses found once stay valid across launches. Profiles are keyed by the
executable's name plus its size on disk, which distinguishes the stock GOG
builds from the NeoEE/dreXmod ones.

Layout (GOG Art of Conquest):

    0x00930DB4  player table: one 32-bit pointer per player slot
                  [0] neutral/Gaia
                  [1] player 1  <- the human in a standard skirmish
                  [2] player 2 ...
    player + 0xAFC   five consecutive int32: Food, Wood, Stone, Gold, Iron
"""

from __future__ import annotations

import os
from dataclasses import dataclass

EXE_NAMES = ("EE-AOC.exe", "Empire Earth.exe")

RESOURCE_NAMES = ("Food", "Wood", "Stone", "Gold", "Iron")

# How a player's match ended, on the player object. Found by resigning and
# watching: the resigning player went 0 -> 2 exactly as the game announced the
# other one victorious, and that opponent read 1.
#
# This matters because holding victory off stops the match *tearing down*, not
# the defeat itself: a defeated player is left unable to act in a match that
# never ends, and their units stay in the roster, so nothing else the client
# watches would notice.
OUTCOME_OFFSET = 0x0A28
OUTCOME_UNDECIDED = 0
OUTCOME_VICTORIOUS = 1
OUTCOME_DEFEATED = 2

# A stockpile above this is treated as a bad pointer rather than a real value.
SANE_MAX = 100_000_000


@dataclass
class Profile:
    name: str
    exe: str
    exe_size: int | None  # bytes on disk; None matches any size
    player_table: int  # static address of the player pointer table
    resource_offset: int  # offset of the resource array within a player object
    player_index: int = 1  # fallback slot if the live index cannot be read
    max_players: int = 16
    # Global holding the local player's index into player_table. The game uses
    # it as [player_table + [local_index_global]*4]; see EEUIEMGDisplayChat.
    local_index_global: int = 0
    stride: int = 4  # bytes between resource entries
    kind: str = "i32"  # i32 | u32 | f32 | f64

    @property
    def static(self) -> int:
        """Address of the local player's slot in the table."""
        return self.player_table + self.player_index * 4

    @property
    def offsets(self) -> list[int]:
        return [self.resource_offset]

    def matches(self, exe_path: str) -> bool:
        if os.path.basename(exe_path).lower() != self.exe.lower():
            return False
        if self.exe_size is None:
            return True
        try:
            return os.path.getsize(exe_path) == self.exe_size
        except OSError:
            return False


# The Steam release (26 May 2026) ships the *same* binary as GOG: all seven PE
# sections are byte-identical, and it has the same image base, section layout
# and (lack of) ASLR. Only the file is larger, by 15,720 bytes of appended data
# outside the sections - a signature or store wrapper. So every address here is
# valid for both, and the two profiles differ only in the size they match on.
_AOC_ADDRESSES = dict(
    exe="EE-AOC.exe",
    player_table=0x00930DB4,
    resource_offset=0xAFC,
    player_index=1,
    local_index_global=0x009318C4,
)

PROFILES: list[Profile] = [
    Profile(
        name="GOG Empire Earth Gold - Art of Conquest",
        exe_size=6_262_784,
        **_AOC_ADDRESSES,
    ),
    Profile(
        name="Steam Empire Earth Gold - Art of Conquest",
        exe_size=6_278_504,
        **_AOC_ADDRESSES,
    ),
]

def profile_for(exe_path: str) -> Profile | None:
    """The address profile matching this executable, or None."""
    for p in PROFILES:
        if p.matches(exe_path):
            return p
    # Same executable name but an unexpected size. Returned anyway so the
    # caller can warn rather than silently doing nothing, but a different build
    # will have different addresses and the layout checks should catch it.
    base = os.path.basename(exe_path).lower()
    for p in PROFILES:
        if p.exe.lower() == base:
            return p
    return None


class ResourceAccess:
    """Reads and writes a player's resource stockpile through a Profile."""

    def __init__(self, proc, profile: Profile):
        self.proc = proc
        self.profile = profile
        # None means "ask the game each time"; set it to pin a specific slot.
        self.player_index: int | None = None

    # --- addressing ------------------------------------------------------

    def local_index(self) -> int:
        """The slot the local human occupies, read live from the game.

        Falls back to the profile's default if the global is unavailable or
        implausible, so a bad read can never silently target another player.
        """
        p = self.profile
        if p.local_index_global:
            v = self.proc.read_u32(p.local_index_global)
            if v is not None and 0 < v < p.max_players:
                return v
        return p.player_index

    def player_object(self, index: int | None = None) -> int | None:
        if index is None:
            idx = self.player_index if self.player_index is not None else self.local_index()
        else:
            idx = index
        ptr = self.proc.read_u32(self.profile.player_table + idx * 4)
        if not ptr or ptr < 0x10000 or ptr > 0x7FFF0000:
            return None
        return ptr

    def base_address(self, index: int | None = None) -> int | None:
        """Address of the resource array, or None if we're not in a match."""
        obj = self.player_object(index)
        if obj is None:
            return None
        addr = obj + self.profile.resource_offset
        vals = self._read_at(addr)
        return addr if vals is not None else None

    def _read_at(self, addr: int) -> list[float] | None:
        p = self.profile
        out = []
        for i in range(len(RESOURCE_NAMES)):
            v = self.proc.read_value(addr + i * p.stride, p.kind)
            # A live stockpile is never negative and never absurdly large;
            # anything else means the pointer is stale.
            if v is None or v < 0 or v > SANE_MAX:
                return None
            out.append(v)
        return out

    # --- access ----------------------------------------------------------

    def read_all(self, index: int | None = None) -> list[float] | None:
        base = self.base_address(index)
        return self._read_at(base) if base is not None else None

    def all_players(self) -> list[tuple[int, list[float]]]:
        """[(slot index, resources)] for every occupied slot. Diagnostic aid."""
        out = []
        for i in range(self.profile.max_players):
            vals = self.read_all(i)
            if vals is not None:
                out.append((i, vals))
        return out

    def add(self, resource_index: int, amount: float) -> float | None:
        """Credit `amount` to a resource. Returns the new total, or None."""
        base = self.base_address()
        if base is None:
            return None
        p = self.profile
        addr = base + resource_index * p.stride
        cur = self.proc.read_value(addr, p.kind)
        if cur is None:
            return None
        new = max(0, cur + amount)
        if not self.proc.write_value(addr, p.kind, new):
            return None
        return new
