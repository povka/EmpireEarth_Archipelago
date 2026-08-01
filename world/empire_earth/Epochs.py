"""Epoch gating for Empire Earth.

Normally a player may advance whenever they can pay for it. This turns the
advance into an Archipelago unlock: receiving "Epoch: Stone Age" is what lets
you press Advance in the Capitol. Resource costs are untouched, and epochs
still have to be taken in order - unlocking one early just sits in the
background until you get there.

Layout, recovered from a live game (see notes/REVERSE.md):

    player object + 0x9CC        -> EETechTree*
    EETechTree + 0x08            -> EETechTreeEpoch[15], stride 0x54
        epoch + 0x04             -> flags; bit 0x1 = "entered",
                                    bit 0x10000 = "requirement satisfied"
        epoch + 0x14             -> epoch index (0..14), used as a sanity check
        epoch + 0x40             -> buildings required to enter (always 2)
        epoch + 0x48             -> qualifying buildings built so far
    EETechTree + 0x540           -> highest reachable epoch (the skirmish's
                                    end-epoch setting; writable to cap a match)

The player's current epoch is the highest record with the "entered" bit set,
not a counter. `EETechTree + 0x544` reads 1 in both Prehistoric and Copper Age,
so it is not the epoch; an earlier reading of it as "the epoch being advanced
to" came from a single sample and was wrong.

Record `i` holds the requirements to ENTER epoch `i`. Normally you satisfy it by
constructing two recruitment or technology buildings; the game evaluates that on
each construction and caches the answer in the flag bit. Lowering `+0x40`
afterwards does nothing, because nothing re-runs the check - the cached flag is
what the UI reads.

So gating is a pure data write:

    lock    clear the flag bit and zero the count -> the Advance button hides,
            exactly as if the buildings had never been built
    unlock  set the flag bit and the count -> the button appears without needing
            the buildings at all, which is the "normal requirement disabled" part

Resource costs live elsewhere and are untouched, so an unlocked epoch still has
to be paid for. Nothing is patched and no code is injected.
"""

from __future__ import annotations

EPOCH_NAMES = [
    "Prehistoric Age",
    "Stone Age",
    "Copper Age",
    "Bronze Age",
    "Dark Age",
    "Middle Ages",
    "Renaissance",
    "Imperial Age",
    "Industrial Age",
    "Atomic Age - WW1",
    "Atomic Age - WW2",
    "Atomic Age - Modern",
    "Digital Age",
    "Nano Age",
    "Space Age",
]
NUM_EPOCHS = len(EPOCH_NAMES)

PLAYER_TECHTREE = 0x9CC
EPOCH_ARRAY = 0x08
EPOCH_STRIDE = 0x54
EPOCH_FLAGS = 0x04
EPOCH_INDEX = 0x14
EPOCH_REQUIRED = 0x40
EPOCH_REQUIREMENT = 0x44      # 1000 * (index + 1); a score/SOL value, not the gate
EPOCH_BUILT = 0x48
TREE_END_EPOCH = 0x540
TREE_NEXT_EPOCH = 0x544

# Bit 0 of an epoch's flags marks it as entered; it is set for every epoch
# up to and including the player's current one.
EPOCH_ENTERED = 0x00000001

# Set once the two qualifying buildings exist; the Capitol UI reads this.
FLAG_REQUIREMENT_MET = 0x00010000


class EpochAccess:
    """Reads and gates the local player's epoch progression."""

    def __init__(self, proc, resources):
        self.proc = proc
        self.res = resources          # ResourceAccess, for the player object
        self.original: dict[int, int] = {}

    # --- addressing ------------------------------------------------------

    def tech_tree(self) -> int | None:
        obj = self.res.player_object()
        if not obj:
            return None
        tree = self.proc.read_u32(obj + PLAYER_TECHTREE)
        if not tree or tree < 0x10000 or tree > 0x7FFF0000:
            return None
        return tree

    def epoch_struct(self, index: int) -> int | None:
        """Address of one epoch record, verified by its own index field."""
        tree = self.tech_tree()
        if tree is None or not 0 <= index < NUM_EPOCHS:
            return None
        addr = tree + EPOCH_ARRAY + index * EPOCH_STRIDE
        # The record stores its own index; if that does not match, the layout
        # is not what we expect and we must not write anything.
        if self.proc.read_i32(addr + EPOCH_INDEX) != index:
            return None
        return addr

    # --- state -----------------------------------------------------------

    def reached(self) -> int | None:
        """Highest epoch the player has entered (0-based), or None if not in a
        match.

        Each epoch record carries an "entered" bit, set for every epoch up to
        and including the current one, so the highest set bit is the current
        epoch. Observed in Copper Age: records 0, 1 and 2 have it, 3+ do not.

        `TREE_NEXT_EPOCH` is deliberately not used - it reads 1 both in
        Prehistoric and in Copper Age, so it is not the epoch at all. The
        earlier reading of it was inferred from a single sample and was wrong.
        """
        tree = self.tech_tree()
        if tree is None:
            return None
        best = None
        for i in range(NUM_EPOCHS):
            addr = self.epoch_struct(i)
            if addr is None:
                continue
            flags = self.proc.read_u32(addr + EPOCH_FLAGS)
            if flags is not None and flags & EPOCH_ENTERED:
                best = i
        return best

    def highest(self) -> int | None:
        tree = self.tech_tree()
        if tree is None:
            return None
        v = self.proc.read_i32(tree + TREE_END_EPOCH)
        return v if v is not None and 0 <= v < NUM_EPOCHS else None

    def set_highest(self, index: int) -> bool:
        """Cap the epoch the match can reach (the skirmish 'end epoch').

        Writing this stops the player advancing past the seed's goal even if
        they configured the skirmish to run all the way to Space Age.
        """
        tree = self.tech_tree()
        if tree is None:
            return False
        return self.proc.write_value(tree + TREE_END_EPOCH, "i32", index)

    def state(self, index: int):
        """(flag_set, built, required) for one epoch, or None."""
        addr = self.epoch_struct(index)
        if addr is None:
            return None
        flags = self.proc.read_u32(addr + EPOCH_FLAGS)
        built = self.proc.read_i32(addr + EPOCH_BUILT)
        need = self.proc.read_i32(addr + EPOCH_REQUIRED)
        if flags is None or built is None or need is None:
            return None
        return bool(flags & FLAG_REQUIREMENT_MET), built, need

    # --- gating ----------------------------------------------------------

    def set_locked(self, index: int, locked: bool) -> bool:
        addr = self.epoch_struct(index)
        if addr is None:
            return False
        flags = self.proc.read_u32(addr + EPOCH_FLAGS)
        need = self.proc.read_i32(addr + EPOCH_REQUIRED)
        if flags is None:
            return False
        if locked:
            new_flags = flags & ~FLAG_REQUIREMENT_MET
            built = 0
        else:
            new_flags = flags | FLAG_REQUIREMENT_MET
            built = need if need and need > 0 else 2
        ok = self.proc.write_value(addr + EPOCH_FLAGS, "u32", new_flags)
        return ok and self.proc.write_value(addr + EPOCH_BUILT, "i32", built)

    def apply(self, unlocked: set[int]) -> tuple[int, int]:
        """Lock every future epoch not in `unlocked`. Returns (locked, opened).

        Epochs already entered are left alone - retracting an epoch you are
        standing in would be nonsense, and the flag there is historical.
        """
        reached = self.reached()
        if reached is None:
            return 0, 0
        n_lock = n_open = 0
        for i in range(reached + 1, NUM_EPOCHS):
            should_open = i in unlocked
            if self.set_locked(i, not should_open):
                if should_open:
                    n_open += 1
                else:
                    n_lock += 1
        return n_lock, n_open

    def snapshot(self) -> list[tuple[int, str, bool, int, int]]:
        """[(index, name, flag_set, built, required)] for diagnostics."""
        out = []
        for i in range(NUM_EPOCHS):
            st = self.state(i)
            if st is None:
                continue
            out.append((i, EPOCH_NAMES[i], *st))
        return out
