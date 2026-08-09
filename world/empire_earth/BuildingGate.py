"""Hide buildings you haven't found the unlock for yet.

`EETechTreeNode + 0x06` decides whether an object appears in a build menu. Its
consumer is the node's own vtable[1] at `0x005CF686`:

    cmp byte [esi+6], 0          ; this byte - zero means unavailable
    je  unavailable
    call [eax+8]                 ; IsObsolete, node+0x18 vs tree+0x538
    ...
    mov ecx, [esi+0xc]           ; the owning tech tree
    mov eax, [ecx+0x538]         ; the epoch it is in
    cmp [esi+0x14], eax          ; the node's own epoch requirement
    jg  unavailable

Two things follow from that. The epoch requirement is a *separate* test in the
same predicate, so clearing `+0x06` gates a building without touching the
game's own epoch rules — `Building: Siege Factory` in the Copper Age still
won't let you build one before the Bronze Age. And `+0x20`, which correlates
beautifully with availability, is never read. Writing it does nothing, which is
how three theories about it survived until someone disassembled the predicate.

Nodes are found by scanning for their vtable. Every player owns a full copy of
the tree, so `node + 0x0C` — the owning `EETechTree` — picks out yours. A node
is identified by its button icon, the only handle these structures offer:
neither the object database nor the node's `+0x08` state object carries a name.
"""

from __future__ import annotations

import struct

NODE_VTABLE = 0x00846150
NODE_SIZE = 0x30
NODE_AVAILABLE = 0x06        # the gate
NODE_TREE = 0x0C             # owning EETechTree
NODE_BUTTON = 0x10           # EEButtonObject
NODE_EPOCH = 0x14            # epoch requirement, vs TREE_EPOCH
TREE_EPOCH = 0x538           # the tech tree's current epoch
BUTTON_TEXTURE = 0x04        # UString, e.g. 'textures\\but_barracks.sst'

# Most buildings follow `but_<lowercased name>.sst`. These five kept the name
# an earlier draft used — a Siege Factory's icon still says "siege workshop",
# and the Cyber buildings' still say "mech".
TEXTURE_ALIASES = {
    "Archery Range": "but_archery",
    "Cyber Factory": "but_mech factory",
    "Cyber Laboratory": "but_mech laboratory",
    "Navy Yard": "but_naval yard",
    "Siege Factory": "but_siege workshop",

    # Art of Conquest's own buildings, which drop the space the way the wonders
    # do and carry an epoch suffix. Without these the tech tree sweep found no
    # node for them, so they had no measured epoch and stayed out of the pool.
    "Space Dock": "but_spacedock_15t",
    "Space Turret": "but_turret_15t",

    # The wonders. Not one follows the rule, which is why the first attempt at
    # gating them found no node for any of the nine and left them all
    # buildable. Read out of `data.ssa`'s texture list rather than guessed:
    # spaces are dropped entirely, `Tower of Babylon` is stored the other way
    # round, the Lighthouse is "of" Alexandria rather than "at", and the
    # Coliseum's icon is misspelled with two Ls in the game's own assets.
    "Coliseum": "but_colliseum",
    "Ishtar gates": "but_ishtargates",
    "Library of Alexandria": "but_libraryofalexandria",
    "Pharos Lighthouse": "but_lighthouseofalexandria",
    "Temple of Zeus": "but_templeofzeus",
    "Time Machine": "but_timemachine",
    "Tower of Babylon": "but_babylontower",
    # Art of Conquest's, which do carry an epoch suffix like the unit icons.
    "Orbital Space Station": "but_orbital_15t",
    # `Future Research Sentinel` is deliberately absent. The candidates are
    # `but_sentinelmech_15t` and `but_sentinel_00t`, one of which is probably
    # the Sentinel infantry, and the names alone can't separate them. A wrong
    # icon here fails quietly: it would gate whatever that node really is, and
    # if that turned out to be a unit its check would sit behind a wonder item
    # and could strand a seed. One wonder staying buildable is the cheaper
    # mistake, and the client names it in the "no tech tree node found" line.
}

# BuildingEpochs.py is generated from this very field, so a node for the right
# building matches it exactly; the tolerance is kept only for late variants.
# Checking it catches a texture that matched the wrong node - `but_farm_15t`
# looks like a Farm but is the Space Age Robotic Farm technology, and gating it
# would have quietly done nothing.
EPOCH_OFFSET = 0
EPOCH_TOLERANCE = 1


def texture_stem(building: str) -> str:
    return TEXTURE_ALIASES.get(building, f"but_{building.lower()}")


class BuildingGate:
    """Holds locked buildings out of the build menu."""

    def __init__(self, proc, roster, epochs):
        self.proc = proc
        self.roster = roster
        self.epochs = epochs
        self._tree: int | None = None
        self._nodes: dict[str, list[int]] = {}
        self._stems: dict[str, str] = {}

    # --- discovery -------------------------------------------------------

    def _plausible(self, building: str, epochs: list[int]) -> bool:
        """Does any node for this building unlock in the epoch it should?

        The test is on the building rather than on each node. A building can
        own several nodes - a late-epoch variant reuses the icon, and both must
        be gated or the variant becomes a way round the lock - so what matters
        is that at least one of them lands where the building is expected. When
        none does, the icon matched something else entirely, as `but_farm_15t`
        did for the Farm.
        """
        try:
            from .BuildingEpochs import BUILDING_EPOCH
        except ImportError:      # loaded as a top-level module by tools/
            from BuildingEpochs import BUILDING_EPOCH

        want = BUILDING_EPOCH.get(building)
        if want is None:
            return True
        return any(abs(e - (want - EPOCH_OFFSET)) <= EPOCH_TOLERANCE
                   for e in epochs)

    def scan(self, buildings) -> dict[str, list[int]]:
        """The local player's nodes for each building, swept once per match.

        A list, not a single address: Granary and University own two nodes
        each, and gating only the first leaves the other as a way round the
        lock.
        """
        tree = self.epochs.tech_tree()
        if not tree:
            return {}
        if tree == self._tree and self._nodes:
            return self._nodes

        self._stems = {texture_stem(b): b for b in buildings}
        found: dict[str, list[int]] = {}
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
                addr = base + off
                button = struct.unpack_from("<I", data, off + NODE_BUTTON)[0]
                if not button:
                    continue
                texture = self.roster.read_uwstring(button + BUTTON_TEXTURE)
                if not texture:
                    continue
                stem = texture.split("\\")[-1].lower()
                if stem.endswith(".sst"):
                    stem = stem[:-4]
                name = self._stems.get(stem)
                if not name:
                    continue
                epoch = struct.unpack_from("<i", data, off + NODE_EPOCH)[0]
                found.setdefault(name, []).append((addr, epoch))

        kept = {}
        for name, hits in found.items():
            if not self._plausible(name, [e for _a, e in hits]):
                continue
            kept[name] = [addr for addr, _e in hits]

        self._tree = tree
        self._nodes = kept
        return kept

    def forget(self) -> None:
        """Drop everything cached, so the next match rescans."""
        self._tree = None
        self._nodes = {}

    # --- writing ---------------------------------------------------------

    def current_epoch(self) -> int | None:
        tree = self.epochs.tech_tree()
        return self.proc.read_u32(tree + TREE_EPOCH) if tree else None

    def apply(self, unlocked: set[str], buildings) -> tuple[int, int]:
        """Lock every building not in `unlocked`. Returns (locked, freed).

        The engine writes `+0x06` itself: it holds a building at 0 until you
        reach the epoch it belongs to, then sets it. So the node's own epoch
        says who a 0 belongs to. Below the current epoch the game would have it
        open, and a 0 there is this client's doing; at or above it, the 0 is the
        game's and must be left alone or the building is pinned shut for the
        whole match.

        Deciding that from the node rather than from a record of what this
        client closed is what makes it survive a restart. Tracking it in memory
        looked equivalent and was not: a client that reconnected mid-match had
        an empty record, so it could never reopen a building an earlier run had
        closed, and `Building: Stable` arrived to no effect.
        """
        nodes = self.scan(buildings)
        epoch = self.current_epoch()
        if epoch is None:
            return 0, 0
        locked_n = freed_n = 0
        for name, addrs in nodes.items():
            want_open = name in unlocked
            for addr in addrs:
                got = self.proc.read(addr + NODE_AVAILABLE, 1)
                node_epoch = self.proc.read_i32(addr + NODE_EPOCH)
                if got is None or node_epoch is None:
                    continue
                if want_open:
                    # Above the current epoch the game owns the flag.
                    if got[0] or node_epoch > epoch:
                        continue
                    if self.proc.write(addr + NODE_AVAILABLE, b"\x01"):
                        freed_n += 1
                elif got[0]:
                    if self.proc.write(addr + NODE_AVAILABLE, b"\x00"):
                        locked_n += 1
        return locked_n, freed_n

    def restore(self) -> int:
        """Reopen every gated building the game would have open by now."""
        epoch = self.current_epoch()
        n = 0
        for addrs in self._nodes.values():
            for addr in addrs:
                node_epoch = self.proc.read_i32(addr + NODE_EPOCH)
                if epoch is None or node_epoch is None or node_epoch > epoch:
                    continue
                if self.proc.write(addr + NODE_AVAILABLE, b"\x01"):
                    n += 1
        return n

    def missing(self, buildings) -> list[str]:
        """Buildings whose node was not found, for diagnostics."""
        return sorted(set(buildings) - set(self.scan(buildings)))
