"""End the match as a win when the Archipelago goal is complete.

The client normally holds the game's victory conditions off, so finishing a seed
would otherwise leave the match running as if nothing had happened. This closes
that loop by having the game end the match itself.

Getting there took three attempts, and the two failures are the interesting
part:

* Writing `player + 0x0A28` does nothing. It is a record the engine owns, and
  releasing the victory gate made it re-evaluate and decide we had *lost*.
* Calling the engine's end-of-match routine from an injected thread sets the
  game-over flag and then crashes. What follows walks the player table, formats
  strings, makes a virtual call on `EEServer` and drives a screen change - none
  of which survives being run mid-frame from outside.

What works is a **one-shot detour**, so the game calls it on its own thread:

    0x00553082   the per-frame victory evaluation, __thiscall
    0x00551F3A   end the match: __thiscall(this, bool won), ret 4

`0x00553082` already receives the real game object in `ecx` - the same value the
engine's own call site passes to the end-of-match routine. Detour its first six
bytes to a stub that saves `ecx`, puts the prologue back so the hook fires
exactly once, calls the end-of-match routine, and jumps to the restored
prologue.

Six bytes, not five: the prologue is `push ebp / mov ebp,esp / sub esp,0x1c`,
and a five-byte jump would land inside the third instruction. Restoring all six
avoids relocating anything.

This is the only place the client writes to the game's **code**. It is in memory
only, it undoes itself the moment it fires, and nothing on disk is touched.
"""

from __future__ import annotations

import struct

HOOK_SITE = 0x00553082          # per-frame victory evaluation, __thiscall
END_MATCH_FN = 0x00551F3A       # __thiscall(this, bool won), ret 4
GAME_OVER_FLAG = 0x00929065

# push ebp / mov ebp,esp / sub esp,0x1c
PROLOGUE = bytes.fromhex("558bec83ec1c")
PATCH_LEN = len(PROLOGUE)

SCRATCH = 0x100
_THIS = 0x80                    # where the stub stashes ecx
_CODE = 0x00


class WinHook:
    """Arms a one-shot detour that ends the match as a win."""

    def __init__(self, proc):
        self.proc = proc
        self.scratch: int | None = None

    def usable(self) -> bool:
        """True if the hook site holds the prologue this was written against."""
        return self.proc.read(HOOK_SITE, PATCH_LEN) == PROLOGUE

    def armed(self) -> bool:
        return self.proc.read(HOOK_SITE, PATCH_LEN) not in (PROLOGUE, None)

    def _stub(self, scratch: int, won: bool) -> bytes:
        this_addr = scratch + _THIS
        code = bytearray()
        code += b"\x89\x0d" + struct.pack("<I", this_addr)   # mov [this], ecx
        code += b"\x60\x9c"                                  # pushad; pushfd
        # Put the prologue back first - the hook must fire once, and the jump
        # at the end of this stub lands on it.
        code += b"\xc7\x05" + struct.pack("<I", HOOK_SITE) + PROLOGUE[0:4]
        code += b"\x66\xc7\x05" + struct.pack("<I", HOOK_SITE + 4) + PROLOGUE[4:6]
        code += b"\x6a" + bytes([1 if won else 0])           # push won
        code += b"\x8b\x0d" + struct.pack("<I", this_addr)   # mov ecx, [this]
        code += b"\xb8" + struct.pack("<I", END_MATCH_FN)    # mov eax, end
        code += b"\xff\xd0"                                  # call eax (ret 4)
        code += b"\x9d\x61"                                  # popfd; popad
        back = scratch + _CODE + len(code) + 5
        code += b"\xe9" + struct.pack("<i", HOOK_SITE - back)
        blob = bytearray(SCRATCH)
        blob[_CODE:_CODE + len(code)] = code
        return bytes(blob)

    def arm(self, won: bool = True) -> bool:
        """Arm the detour. It fires on the game's next frame. Never raises."""
        try:
            if not self.usable():
                return False
            if self.scratch is None:
                self.scratch = self.proc.alloc(SCRATCH) or None
            if self.scratch is None:
                return False

            blob = self._stub(self.scratch, won)
            if not self.proc.write(self.scratch, blob):
                return False
            # Never let the game jump into a page we only think we wrote.
            if self.proc.read(self.scratch, 24) != blob[:24]:
                return False

            if self.proc.protect(HOOK_SITE, PATCH_LEN) is None:
                return False
            rel = self.scratch + _CODE - (HOOK_SITE + 5)
            patch = b"\xe9" + struct.pack("<i", rel) + b"\x90"
            return self.proc.write(HOOK_SITE, patch)
        except Exception:
            return False

    def restore(self) -> bool:
        """Put the prologue back, for a hook that never fired."""
        try:
            if not self.armed():
                return True
            self.proc.protect(HOOK_SITE, PATCH_LEN)
            return self.proc.write(HOOK_SITE, PROLOGUE)
        except Exception:
            return False
