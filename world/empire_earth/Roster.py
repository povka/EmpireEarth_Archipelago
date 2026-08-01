"""Read what the player currently owns, by type name.

The roster is an array of `(EEComplexUnit*, count)` pairs at `player + 0x40`.
Each unit points at its type definition at `+0x2C`, and the definition holds
its name as a UWideString at `+0x1C` - the same name used in the game's
`db\\dbobjects.dat`, so it maps onto the generated Objects.py tables directly.

Only reads are performed here; nothing in this module writes to the game.
"""

from __future__ import annotations

ROSTER_OFFSET = 0x40
ROSTER_STRIDE = 8
ROSTER_MAX = 4096            # generous upper bound on slots to inspect
ROSTER_GAP_TOLERANCE = 128   # empty slots to skip before deciding the list ended
UNIT_VTABLE = 0x00846DDC     # EEComplexUnit
UNIT_DEF_OFFSET = 0x2C       # -> type definition
# The definition embeds two strings: a behaviour label at +0x0C and the object
# name at +0x18. They are UString (vtable RVA 0x99C24), not UWideString
# (0x99C2C) - the two sit 8 bytes apart in the DLL and are easy to confuse.
DEF_NAME_OFFSET = 0x18
USTRING_VTABLE_RVA = 0x99C24
UWSTRING_VTABLE_RVA = 0x99C2C
ENGINE_DLL = "Low-Level Engine.dll"


class Roster:
    """Enumerates the local player's objects and names their types."""

    def __init__(self, proc, profile):
        self.proc = proc
        self.profile = profile
        self._uw_vtable = None
        self._def_cache: dict[int, str] = {}

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

        The array is sparse - freed slots leave nulls behind - so this tolerates
        gaps and only stops after a long run of empty entries.
        """
        obj = self.player_object()
        if obj is None:
            return []
        out = []
        empty_run = 0
        for i in range(ROSTER_MAX):
            ptr = self.proc.read_u32(obj + ROSTER_OFFSET + i * ROSTER_STRIDE)
            if ptr and 0x10000 < ptr < 0x7FFF0000 and \
                    self.proc.read_u32(ptr) == UNIT_VTABLE:
                out.append(ptr)
                empty_run = 0
            else:
                empty_run += 1
                if empty_run >= ROSTER_GAP_TOLERANCE and out:
                    break
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
        for unit in self.units():
            name = self.type_name(unit)
            if name:
                out[name] = out.get(name, 0) + 1
        return out
