"""Stop Empire Earth retiring units when you advance an epoch.

A unit is withdrawn once a later tier replaces it. A Rock Thrower leaves the
Barracks the moment you leave the Copper Age, and a per-unit check you can miss
that way is one that strands the run.

`EETechTreeNode` vtable[2] at `0x005CF742` decides it:

    xor  eax, eax
    cmp  byte [ecx+5], al        ; superseded outright?
    jne  obsolete
    mov  edx, [ecx+0xc]          ; the tech tree
    mov  ecx, [ecx+0x18]         ; the epoch this expires after
    cmp  ecx, [edx+0x538]        ; against the current epoch
    jge  not_obsolete
    obsolete: return 1

Two fields, two different things:

    +0x18   an expiry: "not offered after epoch N"
    +0x05   a replacement: "this specific later unit took over"

Only `+0x18` gets written. That's deliberate — clearing `+0x05` doesn't keep the
old unit beside its successor, it cancels the upgrade. Upgrade a Slinger to a
Simple Bowman, advance once more, and the Archery Range is offering Slingers
again with the Simple Bowman's own check now unsendable. Units get replaced as
the game intends and the replacement carries the replaced check instead, in
`Locations.LOCATION_ALSO_SENDS`.

Technologies are skipped entirely, which took a second stranded run to work
out. A technology chain can share one button and be separated only by epoch —
all seven wall and tower upgrades carry `but_upgrade wall and tower` — and the
engine retires the current tier so the next can take the slot. Held open
forever, the slot never advances and the later tiers never appear. That killed
a two-player run with `Epoch: Industrial Age` sitting on the Middle Ages
upgrade.

So `_scan` drops any node whose icon belongs to a technology. Everything else
still needs no name: only 43 of 178 units can be tied to a node at all, which
is why this writes to nodes rather than to a list of units.

Buildings come along for free. The three carrying an expiry (`but_archery`,
`but_stable`, `but_tower`) each have a second node without one, so they were
never going to disappear anyway.
"""

from __future__ import annotations

import struct

NODE_BUTTON = 0x10           # EEButtonObject, whose +0x04 is the icon
BUTTON_TEXTURE = 0x04

NODE_VTABLE = 0x00846150
NODE_SIZE = 0x30
NODE_SUPERSEDED = 0x05       # non-zero retires the node outright
NODE_TREE = 0x0C
NODE_OBSOLETE_AFTER = 0x18   # retired once the current epoch passes this

NEVER = 15                   # what a unit that never expires already holds


class Obsolescence:
    """Holds every node on the local player's tree permanently available."""

    def __init__(self, proc, epochs, roster):
        self.proc = proc
        self.epochs = epochs
        # Only for reading a node's icon, which is the sole handle these
        # structures offer for telling a technology from a unit.
        self.roster = roster
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

    def _tech_textures(self) -> set[str]:
        try:
            from .Technologies import TECHNOLOGIES
        except ImportError:          # loaded as a top-level module by tools/
            from Technologies import TECHNOLOGIES
        return {v[2] for v in TECHNOLOGIES.values()}

    def _scan(self, tree: int) -> list[int]:
        """Every node on this tree that is *not* a technology.

        Technologies are deliberately left exactly as the game keeps them, and
        clearing their expiry breaks them. Several form chains that share one
        button and are separated only by epoch - the seven wall and tower
        upgrades all carry `but_upgrade wall and tower` - and the engine
        retires the current tier so the next can take the slot. Held open
        forever, the slot never advances: reported from a two-player run as the
        tower upgrade button never appearing, with `Epoch: Industrial Age`
        sitting on the Middle Ages one, which ended the run.

        A node is identified the only way these structures allow, by its
        button icon.
        """
        tech = self._tech_textures()
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
                if struct.unpack_from("<I", data, off + NODE_TREE)[0] != tree:
                    continue
                button = struct.unpack_from("<I", data, off + NODE_BUTTON)[0]
                if button:
                    texture = self.roster.read_uwstring(button + BUTTON_TEXTURE)
                    if texture:
                        stem = texture.split("\\")[-1].lower()
                        if stem.endswith(".sst"):
                            stem = stem[:-4]
                        if stem in tech:
                            continue      # a technology; leave it alone
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
