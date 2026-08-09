"""Read what the player owns, by type name.

The roster is an array of `(EEComplexUnit*, count)` pairs at `player + 0x40`.
Each unit points at its type definition at `+0x2C`, and the definition holds
the object's name at `+0x18` — the same name `dbobjects.dat` uses, so it drops
onto the generated Objects.py tables with no id translation.

Reads only. Nothing here writes to the game.
"""

from __future__ import annotations

import struct

ROSTER_OFFSET = 0x40
ROSTER_STRIDE = 8
ROSTER_MAX = 32768           # slots to sweep; see units() for why overshooting
                             # is safe now
UNIT_OWNER_OFFSET = 0x18     # -> the owning player object
UNIT_VTABLE = 0x00846DDC     # EEComplexUnit
UNIT_DEF_OFFSET = 0x2C       # -> type definition
# The definition embeds two strings: a behaviour label at +0x0C and the object
# name at +0x18. They are UString (vtable RVA 0x99C24), not UWideString
# (0x99C2C) - the two sit 8 bytes apart in the DLL and are easy to confuse.
DEF_NAME_OFFSET = 0x18
USTRING_VTABLE_RVA = 0x99C24
UWSTRING_VTABLE_RVA = 0x99C2C
ENGINE_DLL = "Low-Level Engine.dll"

# 0 while an object is still a construction site, 1 once it stands. The roster
# lists a building the moment its foundation is placed, so this is the only
# thing separating "started" from "finished". Verified live: a Settlement read
# 0 here for the ten seconds it took to build, then 1; every finished object -
# buildings, citizens, path points alike - reads 1.
CONSTRUCTED_OFFSET = 0x34C


class Roster:
    """Enumerates the local player's objects and names their types."""

    def __init__(self, proc, profile):
        self.proc = proc
        self.profile = profile
        self._uw_vtable = None
        self._def_cache: dict[int, str] = {}
        # Diagnostics for `/roster`: how far the last walk reached, and how
        # many objects it found whose type name would not read. Both were
        # guesswork the last time a unit went missing from the list.
        self.last_slot = -1
        self.unnamed = 0

    # --- helpers ---------------------------------------------------------

    def string_vtables(self) -> tuple[int, ...]:
        """Accept either string class; both appear in these structures."""
        if self._uw_vtable is None:
            base = self.proc.module_base(ENGINE_DLL)
            self._uw_vtable = (
                (base + USTRING_VTABLE_RVA, base + UWSTRING_VTABLE_RVA)
                if base else ()
            )
        return self._uw_vtable

    def read_uwstring(self, addr: int) -> str | None:
        """Read a UString/UWideString, verifying its vtable before trusting it."""
        vts = self.string_vtables()
        if not vts or self.proc.read_u32(addr) not in vts:
            return None
        buf = self.proc.read_u32(addr + 4)
        length = self.proc.read_u32(addr + 8)
        if not buf or not length or length > 512:
            return None
        raw = self.proc.read(buf, length)
        return raw.decode("latin-1", "replace") if raw else None

    def player_object(self) -> int | None:
        table = self.profile.player_table
        idx = self.proc.read_u32(self.profile.local_index_global) if \
            self.profile.local_index_global else None
        if idx is None or not (0 < idx < self.profile.max_players):
            idx = self.profile.player_index
        ptr = self.proc.read_u32(table + idx * 4)
        return ptr if ptr and 0x10000 < ptr < 0x7FFF0000 else None

    # --- the roster -------------------------------------------------------

    def units(self) -> list[int]:
        """Addresses of every EEComplexUnit the local player owns.

        The array is sparse and its end is not marked. Two earlier versions
        looked for that end by counting empty slots. Each was wrong in one
        direction:

        - Stopping after 128 empties stopped *inside* the array. An Archery
          Range, a Chariot Archer and a hero all sent no check while a Capitol
          and a Domestic Wolf sent theirs.
        - Not stopping swept the heap past it, where other players' objects
          live. Every one is a real EEComplexUnit with a readable name, so the
          AI's buildings were reported as the player's and a run's worth of
          unearned checks went to the server, where you can't take them back.

        Neither is needed. An object says who owns it: `+0x18` is the owning
        player object. Measured live — every object of the local player held
        the local player object, every AI's held theirs, and 118 foreign
        objects lying past the array were rejected on that alone with nothing
        misclassified.

        So the sweep is deliberately generous and ownership decides. Sweeping
        past the end also turns up your *own* objects a second time, listed in
        other structures — all six in that match reappeared around slot 26,400
        — so results are deduplicated by address. Without that `/roster` counts
        everything twice.
        """
        obj = self.player_object()
        if obj is None:
            return []
        blob = self.proc.read(obj + ROSTER_OFFSET, ROSTER_MAX * ROSTER_STRIDE)
        if not blob:
            return []

        out, seen = [], set()
        self.last_slot = -1
        for off in range(0, len(blob) - 3, ROSTER_STRIDE):
            ptr = struct.unpack_from("<I", blob, off)[0]
            if not (ptr and 0x10000 < ptr < 0x7FFF0000) or ptr in seen:
                continue
            if self.proc.read_u32(ptr) != UNIT_VTABLE:
                continue
            if self.proc.read_u32(ptr + UNIT_OWNER_OFFSET) != obj:
                continue                   # another player's, or Gaia's
            seen.add(ptr)
            out.append(ptr)
            self.last_slot = off // ROSTER_STRIDE
        return out

    def type_name(self, unit: int) -> str | None:
        """The object's database name, e.g. 'b  Settlement' or 'Citizen'."""
        definition = self.proc.read_u32(unit + UNIT_DEF_OFFSET)
        if not definition or not (0x10000 < definition < 0x7FFF0000):
            return None
        cached = self._def_cache.get(definition)
        if cached is not None:
            return cached
        name = self.read_uwstring(definition + DEF_NAME_OFFSET)
        if name:
            self._def_cache[definition] = name
        return name

    def is_complete(self, unit: int) -> bool:
        """False while the object is still a construction site."""
        raw = self.proc.read(unit + CONSTRUCTED_OFFSET, 1)
        return bool(raw and raw[0])

    def survey(self) -> tuple[set[str], set[str]]:
        """(every type owned, types with at least one finished instance).

        Both come from one pass over the roster, because the callers want them
        together and each pass costs a read per object.
        """
        owned: set[str] = set()
        finished: set[str] = set()
        for unit in self.units():
            name = self.type_name(unit)
            if not name:
                continue
            owned.add(name)
            if self.is_complete(unit):
                finished.add(name)
        return owned, finished

    def owned_type_names(self) -> set[str]:
        """Every distinct type the player currently owns."""
        names = set()
        for unit in self.units():
            name = self.type_name(unit)
            if name:
                names.add(name)
        return names

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        self.unnamed = 0
        for unit in self.units():
            name = self.type_name(unit)
            if name:
                out[name] = out.get(name, 0) + 1
            else:
                self.unnamed += 1
        return out
