"""Show Archipelago messages on Empire Earth's own in-game message line.

The game's `--GAME--` banner (`--GAME-- Player 'Babylon' is victorious!`) is
drawn by `EEUserInterface::ShowGameMessage`. Nothing about it can be reached by
writing memory — it has to be *called* — so this allocates a page in the game,
writes a short x86 stub, and runs it. No game file is touched. The allocation
lives in the process and dies with it.

The stub does what the game's own caller does:

    prefix = UWideString("--AP--")           ??0UWideString@@QAE@PBD@Z
    text   = UWideString("...")
    ecx    = [0x009318F8]                    EEUserInterface*
    ShowGameMessage(rgb, prefix, text, colour, 0)     0x006794C6, ret 0x14
    prefix.~UWideString(); text.~UWideString()        ??1UWideString@@UAE@XZ

`colour` is computed exactly as the game computes it. Its meaning is unknown;
copied verbatim it works.

Everything is guarded. The bytes at the call target have to match what this was
written against, or nothing runs, so an unknown build fails silently instead of
jumping into the middle of some other function.
"""

from __future__ import annotations

import struct

# --- addresses (GOG and Steam Art of Conquest; the two are byte-identical) ---

BANNER_FN = 0x006794C6          # EEUserInterface::ShowGameMessage
UI_SINGLETON = 0x009318F8       # EEUserInterface*
COLOUR_GLOBAL = 0x0092FCA8
COLOUR_OFFSET = 0x2CC

ENGINE_DLL = "Low-Level Engine.dll"   # relocates; resolved at runtime
USTRING_CTOR_RVA = 0x83BB7      # ??0UWideString@@QAE@PBD@Z  (char*)
USTRING_DTOR_RVA = 0x83C38      # ??1UWideString@@UAE@XZ

# First bytes of BANNER_FN. If they don't match, the build isn't one this was
# written for and nothing gets called.
BANNER_SIG = bytes.fromhex("558bec5356576a3c8bd9")

SLOT = 0x200
# Several slots, used round-robin. The call fires without waiting for it to
# finish — blocking the client for even a fraction of a second per message
# isn't worth it, and waiting the full timeout stalled the watcher for five
# seconds a line. A ring keeps a slow thread's data from being overwritten by
# the next message before it has read it.
SLOTS = 8
SCRATCH = SLOT * SLOTS

_RGB, _PRE_S, _MSG_S, _PRE_O, _MSG_O, _CODE = (
    0x000, 0x010, 0x060, 0x100, 0x140, 0x180)

# Long enough to catch an immediate failure, short enough not to be felt. A
# thread still running after this is left alone rather than waited on.
WAIT_MS = 120

# The game truncates nothing for us, and a long line runs off screen.
MAX_TEXT = 120


class Banner:
    """Posts one-line messages to the game's own message display."""

    def __init__(self, proc):
        self.proc = proc
        self.scratch: int | None = None
        self._slot = 0
        self.ctor = 0
        self.dtor = 0
        self._checked = False
        self._usable = False

    # --- setup -----------------------------------------------------------

    def usable(self) -> bool:
        """True once we know this build is the expected one and can be called."""
        if self._checked:
            return self._usable
        self._checked = True

        if self.proc.read(BANNER_FN, len(BANNER_SIG)) != BANNER_SIG:
            return False
        base = self.proc.module_base(ENGINE_DLL)
        if not base:
            return False
        self.ctor = base + USTRING_CTOR_RVA
        self.dtor = base + USTRING_DTOR_RVA
        self._usable = True
        return True

    def _ensure_scratch(self) -> bool:
        if self.scratch:
            return True
        self.scratch = self.proc.alloc(SCRATCH) or None
        return self.scratch is not None

    def close(self):
        if self.scratch:
            self.proc.free(self.scratch)
            self.scratch = None

    # --- the stub --------------------------------------------------------

    def _build(self, base: int, prefix: bytes, text: bytes) -> bytes:
        s = base
        blob = bytearray(SLOT)
        struct.pack_into("<fff", blob, _RGB, 1.0, 1.0, 1.0)
        blob[_PRE_S:_PRE_S + len(prefix) + 1] = prefix + b"\x00"
        blob[_MSG_S:_MSG_S + len(text) + 1] = text + b"\x00"

        code = bytearray()
        code += b"\x55\x8b\xec"                                # push ebp; mov ebp,esp

        for obj, string in ((_PRE_O, _PRE_S), (_MSG_O, _MSG_S)):
            code += b"\x68" + struct.pack("<I", s + string)    # push char*
            code += b"\xb9" + struct.pack("<I", s + obj)       # mov ecx, UString*
            code += b"\xb8" + struct.pack("<I", self.ctor)
            code += b"\xff\xd0"                                # call (thiscall, ret 4)

        # colour, exactly as the game derives it
        code += b"\xa1" + struct.pack("<I", COLOUR_GLOBAL)
        code += b"\x8b\x80" + struct.pack("<I", COLOUR_OFFSET)
        code += b"\xd1\xe0"                                    # shl eax, 1

        code += b"\x6a\x00"                                    # push 0
        code += b"\x50"                                        # push colour
        code += b"\x68" + struct.pack("<I", s + _MSG_O)
        code += b"\x68" + struct.pack("<I", s + _PRE_O)
        code += b"\x68" + struct.pack("<I", s + _RGB)
        code += b"\x8b\x0d" + struct.pack("<I", UI_SINGLETON)  # mov ecx, ds:[UI]
        code += b"\xb8" + struct.pack("<I", BANNER_FN)
        code += b"\xff\xd0"                                    # call (ret 0x14)

        # The banner copies both strings into its own object, so ours are ours
        # to destroy. Without this every message leaks its buffer.
        for obj in (_MSG_O, _PRE_O):
            code += b"\xb9" + struct.pack("<I", s + obj)       # mov ecx, UString*
            code += b"\xb8" + struct.pack("<I", self.dtor)
            code += b"\xff\xd0"                                # call (thiscall)

        code += b"\x31\xc0\x5d\xc3"                            # xor eax,eax; pop ebp; ret
        blob[_CODE:_CODE + len(code)] = code
        return bytes(blob)

    # --- posting ---------------------------------------------------------

    def show(self, text: str, prefix: str = "--AP--") -> bool:
        """Put one line on the game's message display. Never raises."""
        try:
            if not self.usable() or not self._ensure_scratch():
                return False
            # The display is single-line, so a long message runs off screen.
            clipped = text[:MAX_TEXT]
            base = self.scratch + self._slot * SLOT
            self._slot = (self._slot + 1) % SLOTS

            blob = self._build(base, prefix.encode("latin-1", "replace"),
                               clipped.encode("latin-1", "replace"))
            if not self.proc.write(base, blob):
                return False
            # Never execute a page we only think we wrote.
            if self.proc.read(base + _CODE, 16) != blob[_CODE:_CODE + 16]:
                return False
            # None means "still running", which is fine. The message is on
            # its way and the slot ring keeps its data intact meanwhile.
            rc = self.proc.run_thread(base + _CODE, timeout_ms=WAIT_MS)
            return rc in (0, None)
        except Exception:
            return False
