"""Stop Empire Earth retiring units when you advance an epoch.

Normally a unit is withdrawn once a later tier replaces it: a Rock Thrower
stops being offered at the Barracks the moment you leave the Copper Age. That
makes a per-unit check missable - reach the next epoch without having built one
and it can never be sent - which would be fine for filler and fatal for
anything the run needs.

The engine decides this in `EETechTreeNode` vtable[2], `0x005CF742`:

    xor  eax, eax
    cmp  byte [ecx+5], al        ; superseded outright?
    jne  obsolete
    mov  edx, [ecx+0xc]          ; the tech tree
    mov  ecx, [ecx+0x18]         ; the epoch this expires after
    cmp  ecx, [edx+0x538]        ; against the current epoch
    jge  not_obsolete
    obsolete: return 1

So there are two ways to be retired - and only one of them is this module's
business, which took a bug to establish. The two fields are not the same kind
of thing:

    +0x18   an expiry date: "no longer offered after epoch N"
    +0x05   a replacement: "this specific later unit has taken over"

Clearing the expiry is right, and is what keeps a Rock Thrower recruitable for
the whole match. Clearing the replacement is not: it does not preserve the old
unit beside its successor, it *cancels the upgrade*. Observed in play - upgrade
a Slinger to a Simple Bowman, advance one more epoch, and the Archery Range is
offering Slingers again. That also left the Simple Bowman's own check
unsendable, and unit checks carry progression, so it could strand a seed.

So only `+0x18` is written now. Units still get replaced, exactly as the game
intends, and the check that would have been lost is carried by the replacement
instead: recruiting a Simple Bowman sends Slinger's check too
(`Locations.LOCATION_ALSO_SENDS`, built by tools/gen_upgrades.py).

This needs no name for anything. Every node on the local player's tree is
written, which sidesteps the problem that only 43 of 178 units can be tied to a
node at all - the icons the tree uses do not match database names.

Buildings are included and it costs nothing: the three that carry an expiry
(`but_archery`, `but_stable`, `but_tower`) each have a second node without one,
so they were never going to disappear anyway.
"""

from __future__ import annotations

import struct

NODE_VTABLE = 0x00846150
NODE_SIZE = 0x30
NODE_SUPERSEDED = 0x05       # non-zero retires the node outright
NODE_TREE = 0x0C
NODE_OBSOLETE_AFTER = 0x18   # retired once the current epoch passes this

NEVER = 15                   # what a unit that never expires already holds


class Obsolescence:
    """Holds every node on the local player's tree permanently available."""

    def __init__(self, proc, epochs):
        self.proc = proc
        self.epochs = epochs
        self._tree: int | None = None
        self._nodes: list[int] = []
        self._epoch: int | None = None
        self._written = 0

    def forget(self) -> None:
        """A new match builds a new tree, so the work has to be redone."""
        self._tree = None
        self._nodes = []
        self._epoch = None
        self._written = 0

    @property
    def written(self) -> int:
        return self._written

    def _scan(self, tree: int) -> list[int]:
        """Every node on this tree. Swept once, then reused."""
        found = []
        needle = struct.pack("<I", NODE_VTABLE)
        for base, data in self.proc.snapshot(want_image=False, want_private=True,
                                             want_mapped=False):
            off = -1
            while True:
                off = data.find(needle, off + 1)
                if off < 0:
                    break
                if off % 4 or off + NODE_SIZE > len(data):
                    continue
                if struct.unpack_from("<I", data, off + NODE_TREE)[0] == tree:
                    found.append(base + off)
        return found

    def apply(self) -> int:
        """Clear the expiry on every node, leaving replacements alone.

        Returns how many nodes were changed *by this call* - zero when the
        epoch has not moved since the last one.

        Redone whenever the epoch changes, not just once per match. The engine
        sets these as you cross an epoch, so writing once at match start would
        only postpone the problem to the next advance.

        The node addresses are swept once and reused, so a re-apply is a few
        hundred small writes rather than another pass over the heap.
        """
        tree = self.epochs.tech_tree()
        if not tree:
            return 0
        epoch = self.epochs.reached()
        if tree == self._tree and epoch == self._epoch:
            # Nothing done this call. Returning the previous count instead made
            # the caller log the same line every poll.
            return 0
        if tree != self._tree:
            self._nodes = self._scan(tree)

        changed = 0
        for addr in self._nodes:
            expires = self.proc.read_i32(addr + NODE_OBSOLETE_AFTER)
            if expires is None or expires >= NEVER:
                continue
            # `+0x05` is deliberately not touched; see the module docstring.
            if self.proc.write(addr + NODE_OBSOLETE_AFTER,
                               struct.pack("<i", NEVER)):
                changed += 1

        self._tree = tree
        self._epoch = epoch
        self._written = changed
        return changed
