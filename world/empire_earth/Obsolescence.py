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

So there are two ways to be retired, and both have to go: clear `+0x05`, and
set `+0x18` to 15, which is the value units that never expire already carry.
The availability predicate calls this, so a node that is never obsolete stays
in its build menu for the rest of the match.

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
        """Clear both retirement paths on every node.

        Returns how many nodes were changed *by this call* - zero when the
        epoch has not moved since the last one.

        Redone whenever the epoch changes, not just once per match. The engine
        sets `+0x05` as you cross an epoch - that is how a Rock Thrower stops
        being offered on leaving the Copper Age - so writing once at match start
        would only postpone the problem to the next advance.

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
            node = self.proc.read(addr + NODE_SUPERSEDED, 1)
            expires = self.proc.read_i32(addr + NODE_OBSOLETE_AFTER)
            if node is None or expires is None:
                continue
            if not node[0] and expires >= NEVER:
                continue
            ok = True
            if node[0]:
                ok &= bool(self.proc.write(addr + NODE_SUPERSEDED, b"\x00"))
            if expires < NEVER:
                ok &= bool(self.proc.write(
                    addr + NODE_OBSOLETE_AFTER, struct.pack("<i", NEVER)))
            if ok:
                changed += 1

        self._tree = tree
        self._epoch = epoch
        self._written = changed
        return changed
