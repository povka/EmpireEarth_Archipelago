"""Open the next technology in a chain the moment its predecessor is researched.

A technology's effect does two separate things: it grants the benefit, and it
makes the next tier of its chain available. `TechEffects` suppresses the whole
effect so the benefit can arrive as an item — which took the chain with it, and
that is what forced 72 `Tech:` items to be progression. `Research Monotheism`
needed `Tech: Ancestor Worship` in hand, so generation had to treat the item as
gating, and a seed could not put an epoch or a wonder on a research check
without the item being load-bearing too.

So the unlock half is put back here, by hand. Researching opens the successor's
button; the benefit still waits for the item. Nothing in the rules depends on a
`Tech:` item any more, and all 100 of them are ordinary useful items.

`+0x06` is the same availability byte `BuildingGate` writes, and the engine owns
it the same way: it holds a node at 0 until you reach its epoch, then sets it.
So a successor is only opened once the current epoch has reached the node's own
`+0x14` — above that the 0 is the game's and overwriting it would offer a
technology two epochs early.

That it gates a *technology* the way it gates a building was measured, not
assumed. In a Bronze Age match with Ancestor Worship unresearched, Monotheism
read `+0x14 = 3` and `+0x06 = 0` — its epoch already reached, so the only thing
holding it shut was its predecessor. Writing 1 put the button on the Temple.

Idempotent, and re-derived from the tree every poll rather than remembered. A
client that reconnects mid-match has no record of what it opened, and the
technologies it opened last time are still open in the game.
"""

from __future__ import annotations

NODE_AVAILABLE = 0x06        # the gate, as in BuildingGate
NODE_EPOCH = 0x14            # the epoch this node belongs to
TREE_EPOCH = 0x538


class TechChains:
    """Keeps a researched technology's successors available."""

    def __init__(self, proc, epochs, research):
        self.proc = proc
        self.epochs = epochs
        # Only to find nodes. `ResearchWatch.scan` already keys every
        # technology node by (icon, epoch), which is the one handle these
        # structures offer.
        self.research = research
        self._opened = 0

    @property
    def opened(self) -> int:
        return self._opened

    def forget(self) -> None:
        self._opened = 0

    def apply(self) -> int:
        """Open every successor of a researched technology. Returns how many."""
        try:
            from .Technologies import TECHNOLOGIES
            from .TechUnlocks import TECH_UNLOCKS
            from .Locations import TECH_LOCATION_BY_NODE
        except ImportError:          # loaded as a top-level module by tools/
            from Technologies import TECHNOLOGIES
            from TechUnlocks import TECH_UNLOCKS
            from Locations import TECH_LOCATION_BY_NODE

        tree = self.epochs.tech_tree()
        if not tree:
            return 0
        epoch = self.proc.read_u32(tree + TREE_EPOCH)
        if epoch is None:
            return 0

        nodes = self.research.scan(TECH_LOCATION_BY_NODE)
        if not nodes:
            return 0
        done = self.research.researched(TECH_LOCATION_BY_NODE)

        wanted = set()
        for key in done:
            name = TECH_LOCATION_BY_NODE.get(key)
            if not name:
                continue
            for successor in TECH_UNLOCKS.get(name[len("Research "):], ()):
                entry = TECHNOLOGIES.get(successor)
                if entry:
                    wanted.add((entry[2], entry[3]))

        changed = 0
        for key in wanted:
            addr = nodes.get(key)
            if not addr:
                continue
            got = self.proc.read(addr + NODE_AVAILABLE, 1)
            node_epoch = self.proc.read_i32(addr + NODE_EPOCH)
            if got is None or node_epoch is None:
                continue
            if got[0] or node_epoch > epoch:
                continue             # already open, or the game's 0 to own
            if self.proc.write(addr + NODE_AVAILABLE, b"\x01"):
                changed += 1
        self._opened = changed
        return changed
