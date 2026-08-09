"""Read and set diplomatic stance between players.

Empire Earth refuses to start a skirmish with fewer than two players, and
refuses to let them all share a team, so a run always begins with a hostile
opponent. Both of those checks live in the Start Game validator and run before
the match exists. Stance is per-player state inside the match, so you can set
it afterwards, when there's nothing left to validate.

Each player object carries an array of stances indexed by the target's player
slot:

    player + 0x09DC + slot*4     0 = allied, 1 = hostile

The encoding is pinned by every player reading 0 toward itself. Found by
snapshotting the player objects, allying with the AI through the diplomacy
screen, and diffing — exactly one dword moved.

Stance is one-directional. Allying from your side stops you attacking the AI,
it doesn't stop the AI attacking you, so peace has to be written both ways.
"""

from __future__ import annotations

STANCE_ARRAY = 0x09DC
STANCE_STRIDE = 4

ALLIED = 0
HOSTILE = 1

# Slot 0 is neutral nature, the animals. Left alone deliberately — making them
# friendly changes how the map plays, which isn't what peace is for.
GAIA_SLOT = 0


class Diplomacy:
    """Holds every other player at peace with the local one."""

    def __init__(self, proc, profile):
        self.proc = proc
        self.profile = profile

    # --- reading ---------------------------------------------------------

    def local_slot(self) -> int | None:
        idx = (
            self.proc.read_u32(self.profile.local_index_global)
            if self.profile.local_index_global else None
        )
        if idx is None or not (0 < idx < self.profile.max_players):
            idx = self.profile.player_index
        return idx

    def players(self) -> dict[int, int]:
        """Occupied player slots -> object address."""
        out: dict[int, int] = {}
        for slot in range(self.profile.max_players):
            ptr = self.proc.read_u32(self.profile.player_table + slot * 4)
            if ptr and 0x10000 < ptr < 0x7FFF0000:
                out[slot] = ptr
        return out

    def stance(self, src: int, dst: int) -> int | None:
        players = self.players()
        obj = players.get(src)
        if obj is None:
            return None
        return self.proc.read_i32(obj + STANCE_ARRAY + dst * STANCE_STRIDE)

    def matrix(self) -> dict[int, dict[int, int]]:
        players = self.players()
        out: dict[int, dict[int, int]] = {}
        for src, obj in players.items():
            row = {}
            for dst in players:
                v = self.proc.read_i32(obj + STANCE_ARRAY + dst * STANCE_STRIDE)
                if v is not None:
                    row[dst] = v
            out[src] = row
        return out

    # --- writing ---------------------------------------------------------

    def plausible(self) -> bool:
        """True if the array looks like stances.

        Every player has to read allied toward itself and every entry has to
        be a known value, or this isn't the array we think it is and nothing
        gets written.
        """
        players = self.players()
        if len(players) < 2:
            return False
        for slot, obj in players.items():
            own = self.proc.read_i32(obj + STANCE_ARRAY + slot * STANCE_STRIDE)
            if own != ALLIED:
                return False
            for dst in players:
                v = self.proc.read_i32(obj + STANCE_ARRAY + dst * STANCE_STRIDE)
                if v not in (ALLIED, HOSTILE):
                    return False
        return True

    def force_peace(self) -> list[str]:
        """Set mutual peace between the local player and every opponent.

        Returns a description of anything actually changed, so a caller can
        stay quiet on the polls where there's nothing to do.
        """
        changed: list[str] = []
        local = self.local_slot()
        if local is None or not self.plausible():
            return changed

        players = self.players()
        if local not in players:
            return changed

        for slot, obj in players.items():
            if slot in (local, GAIA_SLOT):
                continue
            # Both directions: theirs is what stops them attacking you.
            for src, dst, label in (
                (local, slot, f"you -> player {slot}"),
                (slot, local, f"player {slot} -> you"),
            ):
                addr = players[src] + STANCE_ARRAY + dst * STANCE_STRIDE
                if self.proc.read_i32(addr) == ALLIED:
                    continue
                if self.proc.write_value(addr, "i32", ALLIED):
                    changed.append(label)
        return changed
