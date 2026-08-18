"""Close the gaps where a build menu shows nothing at all.

This used to stop the game retiring units entirely, on the theory that a unit
you can always recruit is a check you can never miss. That was wrong, and the
reason is worth keeping: a menu is a fixed row of positions, one per line,
showing the single unit of that line valid right now. Hold every unit open and
each position stays pinned to its first tier — a run reached the Imperial Age
with the Rock Thrower still in Barracks slot 1 and no way to build a Musketeer,
and the Airport and Tank Factory never appeared because the Archery Range and
Stable never vacated their positions in the build menu.

So units retire as they always did, and their checks travel with the slot
instead; see UnitSlots.py and Locations.LOCATION_ALSO_SENDS. What is left here
is the handful of positions that sit *empty* for an epoch or two between one
occupant and the next, which is a different problem — a check that closes and
reopens later. Archipelago rules are monotone and cannot say "reachable until
epoch 6", so generation puts progression on a check that has already shut. Those
gaps get held open until their successor arrives.

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

Only `+0x18` gets written, and only for the handful of gaps below. `+0x05` is
never touched — clearing it doesn't keep the old unit beside its successor, it
cancels the upgrade. Upgrade a Slinger to a Simple Bowman, advance once more,
and the Archery Range is offering Slingers again with the Simple Bowman's own
check now unsendable.

Technologies are skipped entirely, which took a second stranded run to work
out. A technology chain can share one button and be separated only by epoch —
all seven wall and tower upgrades carry `but_upgrade wall and tower` — and the
engine retires the current tier so the next can take the slot. Held open
forever, the slot never advances and the later tiers never appear. That killed
a two-player run with `Epoch: Industrial Age` sitting on the Middle Ages
upgrade.

So `_scan` drops any node whose icon belongs to a technology, and what it
keeps is matched against the gap tables by icon — a node carries no name, and
its button is the only handle these structures offer.
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
    """Holds open the menu positions that would otherwise sit empty."""

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
        button and are separated only by epoch — the seven wall and tower
        upgrades all carry `but_upgrade wall and tower` — and the engine
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

    # Icon -> the epoch it should stay buildable through.
    #
    # The only *building* with a gap. The Archery Range holds build-menu
    # position 7 until epoch 6 and the Airport does not take it until epoch 9,
    # so for two epochs neither exists and `Build Archery Range` cannot be sent
    # by anything. That cost a run: `Epoch: Industrial Age` sat on a check that
    # had already closed, and it stopped in the Imperial Age.
    #
    # Holding it to epoch 8 closes the gap and hands over exactly when the
    # Airport arrives. Every other building's successor is waiting in the same
    # epoch. The unit gaps come from `UnitSlots.SLOT_GAPS`; see `_gaps`.
    GAPS = {"but_archery": 8}

    def _gaps(self) -> dict[str, int]:
        """Icon -> the epoch it stays buildable through.

        The building above, plus every unit whose menu position sits empty for
        a while before the next line takes it — `UnitSlots.SLOT_GAPS`, derived
        from the observed listings in tools/data. Those name units, and a node
        carries no name, so `UnitIcons` bridges the two. It is the one thing
        here that has to come from a running game.

        An epoch of 15 there means nothing ever takes the position. Those are
        the ones worth holding: the position is free for the rest of the game,
        so nothing can be squatted, and without the hold the check is gone for
        good. The AP tank line ends at the Leopard and cost a seed that way.
        """
        out = dict(self.GAPS)
        try:
            try:
                from .UnitSlots import SLOT_GAPS
                from .UnitIcons import UNIT_ICONS
            except ImportError:      # loaded as a top-level module by tools/
                from UnitSlots import SLOT_GAPS
                from UnitIcons import UNIT_ICONS
        except ImportError:
            return out               # no icon map generated yet
        for db, epoch in SLOT_GAPS.items():
            icon = UNIT_ICONS.get(db)
            if icon:
                out[icon] = epoch
        return out

    def apply(self) -> int:
        """Close the one gap in the menus, and nothing else.

        This used to clear the expiry on every node so a unit stayed
        recruitable all match. That is not something the game can express: a
        menu is a fixed row of positions showing the one unit of each line
        valid now, so holding everything open pinned every position to its
        first tier — the Rock Thrower sat in Barracks slot 1 into the Imperial
        Age and the Musketeer never appeared, and the Airport and Tank Factory
        never appeared either.

        Checks travel with the slot instead (see UnitSlots.py and
        Locations.LOCATION_ALSO_SENDS). All that is left to write is GAPS.
        """
        tree = self.epochs.tech_tree()
        if not tree:
            return 0
        if tree != self._tree:
            self._nodes = self._scan(tree)
            self._tree = tree
        try:
            from .BuildingGate import node_stem
        except ImportError:          # loaded as a top-level module by tools/
            from BuildingGate import node_stem

        gaps = self._gaps()
        changed = 0
        for addr in self._nodes:
            stem = node_stem(self.proc, self.roster, addr, tree)
            want = gaps.get(stem)
            if want is None:
                continue
            if self.proc.read_i32(addr + NODE_OBSOLETE_AFTER) == want:
                continue
            if self.proc.write(addr + NODE_OBSOLETE_AFTER,
                               struct.pack("<i", want)):
                changed += 1
        self._written = changed
        return changed

