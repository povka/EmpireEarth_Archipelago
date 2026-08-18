"""Notice when a technology has been researched.

`EETechTreeNode + 0x04` is the byte the game sets once a technology is done.
Found by measurement rather than inspection — snapshot every node, research
exactly one thing, diff. Twice, with a different technology each time, and only
that node's `+0x04` moved.

Two neighbouring fields look like they should mean this and don't.

`+0x22` is set on the same seven entries in every player's tree *and* in the
static template tree that belongs to nobody, so it marks entries switched off
for the game mode, not research.

`+0x21` is the byte that removes a researched technology from its menu.
Clearing `+0x04` alone doesn't bring the button back, clearing `+0x21` as well
does. So `+0x04` records that the work is done and `+0x21` acts on it — worth
knowing, though this module only reads.

Nothing here writes to the game. Technologies stay exactly where Empire Earth
puts them and cost what they always cost; withholding the benefit is
`TechEffects`' job, not this module's. All that changes here is that finishing
one sends a check.
"""

from __future__ import annotations

import struct

NODE_VTABLE = 0x00846150
NODE_SIZE = 0x30
NODE_RESEARCHED = 0x04
NODE_TREE = 0x0C
NODE_BUTTON = 0x10
NODE_EPOCH = 0x14
BUTTON_TEXTURE = 0x04


class ResearchWatch:
    """Reports which technologies the local player has researched."""

    def __init__(self, proc, roster, epochs):
        self.proc = proc
        self.roster = roster
        self.epochs = epochs
        self._tree: int | None = None
        self._nodes: dict[str, int] = {}

    def scan(self, keys) -> dict[tuple[str, int], int]:
        """(texture, epoch) -> node address, for the local player's tree.

        Keyed on the pair because a texture isn't unique — the seven wall and
        tower upgrades share one, and only the node's epoch separates them.

        Cached per match. Every player owns a full copy of the tree, so
        `node+0x0C` is what picks ours out. Without it we'd report the AI's
        research as our own.
        """
        tree = self.epochs.tech_tree()
        if not tree:
            return {}
        if tree == self._tree and self._nodes:
            if self._cache_intact(tree):
                return self._nodes
            self.forget()

        wanted = set(keys)
        found: dict[tuple[str, int], int] = {}
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
                if not button:
                    continue
                texture = self.roster.read_uwstring(button + BUTTON_TEXTURE)
                if not texture:
                    continue
                stem = texture.split("\\")[-1].lower()
                if stem.endswith(".sst"):
                    stem = stem[:-4]
                key = (stem, struct.unpack_from("<i", data, off + NODE_EPOCH)[0])
                if key in wanted:
                    found.setdefault(key, base + off)

        self._tree = tree
        self._nodes = found
        return found

    def _cache_intact(self, tree: int) -> bool:
        """Do the cached addresses still hold the technologies they were found as?

        The tree pointer alone can't tell a rebuilt tree from the one these
        addresses came from; see `BuildingGate.node_stem`. Reading stale
        addresses here doesn't break the game, it reports research nobody did —
        which is how a reconnect once sent a burst of checks that hadn't been
        earned.
        """
        try:
            from .BuildingGate import node_stem
        except ImportError:          # loaded as a top-level module by tools/
            from BuildingGate import node_stem

        for (stem, _epoch), addr in self._nodes.items():
            if node_stem(self.proc, self.roster, addr, tree) != stem:
                return False
        return True

    def forget(self) -> None:
        """Drop the cache, so the next match rescans."""
        self._tree = None
        self._nodes = {}

    def researched(self, keys) -> set[tuple[str, int]]:
        """Nodes whose technology is currently researched."""
        done = set()
        for key, addr in self.scan(keys).items():
            got = self.proc.read(addr + NODE_RESEARCHED, 1)
            if got and got[0]:
                done.add(key)
        return done

    def missing(self, keys) -> list[str]:
        """Technologies whose node wasn't found, for diagnostics."""
        return sorted(f"{t}@{e}" for t, e in set(keys) - set(self.scan(keys)))
