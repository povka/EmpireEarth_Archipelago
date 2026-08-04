"""Hold back a technology's benefit until Archipelago sends it.

Researching a technology stays exactly as the game has it - same button, same
cost, same place - but the benefit is withheld and arrives later as an item.
That needs two things the engine keeps helpfully far apart.

`EETechTreeNode` vtable[6] at `0x005CFA53` completes a research:

    mov  byte [esi+4], 1         ; mark researched  (0x005CFA9C)
    push [ecx+0x534]             ; ecx = [esi+0xC], the tech tree
    push [eax+0x4C]              ; eax = [esi+8]; the technology id
    push [ecx+4]
    push [eax+0x50]              ; which effect set to apply
    call 0x005CA76C              ; apply it        (0x005CFAAF)

The flag and the effect are separate statements, so the flag can be left to the
game - which is what the check watches - while the effect is skipped.

`0x005CA76C` is data-driven: it indexes a table at `0x0095CF80` by the effect
set and runs each entry. Calling it later, with the same five arguments, is
what grants the benefit.

Only the local player is affected. At the call site `ecx` still holds the
node's tech tree, loaded three instructions earlier and never clobbered, so the
stub compares it against ours and lets every other player - the AI, who
research constantly - straight through. Suppression is off whenever that
pointer is zero, so a client that is not in a match changes nothing.

This and WinHook are the only places the client writes to the game's code. It
is in memory only, and `restore()` puts the original call back.
"""

from __future__ import annotations

import struct

CALL_SITE = 0x005CFAAF          # the `call` that applies a technology's effect
APPLY_FN = 0x005CA76C           # cdecl(effect_set, [tree+4], id, [tree+0x534], flag)
ORIGINAL = bytes.fromhex("e8b8acffff")      # call 0x005CA76C
PATCH_LEN = len(ORIGINAL)

PLAYER_TECHTREE = 0x9CC         # player object -> EETechTree
NODE_STATE = 0x08               # -> the object holding the effect set and id
NODE_TREE = 0x0C
STATE_ID = 0x4C
STATE_EFFECT_SET = 0x50
TREE_ARG = 0x04
TREE_CONTEXT = 0x534

SCRATCH = 0x1000
_CODE = 0x00                    # the suppression stub
_TREE = 0x80                    # the local player's tech tree, or 0 for "off"
_COUNT = 0x84                   # effect calls skipped, for diagnostics
_LAST = 0x88                    # id of the last technology suppressed
_DONE = 0x8C                    # set by the grant stub once it returns
_GRANT = 0xA0                   # scratch for one grant call
_TABLE = 0x400                  # bitmap of ids this client may suppress

# Ids seen so far sit around 0x3E8..0x3E7F; the bitmap covers 0..0x3FFF, which
# is 0x800 bytes. Anything outside is passed straight through.
MAX_ID = 0x4000


class TechEffects:
    """Suppresses the local player's technology effects, and grants them later."""

    def __init__(self, proc, profile=None):
        self.proc = proc
        self.scratch: int | None = None
        # The stub resolves the local tech tree from these, so it does not
        # depend on the client having seen a match yet.
        self.local_index = getattr(profile, "local_index_global", 0x009318C4)
        self.player_table = getattr(profile, "player_table", 0x00930DB4)

    # --- the detour ------------------------------------------------------

    def usable(self) -> bool:
        """True if the call site looks like the build this was written for."""
        return self.proc.read(CALL_SITE, PATCH_LEN) == ORIGINAL

    def armed(self) -> bool:
        got = self.proc.read(CALL_SITE, PATCH_LEN)
        return got is not None and got != ORIGINAL

    def _stub(self, scratch: int) -> bytes:
        """cmp ecx,[tree] / je skip / jmp apply / skip: inc count / ret

        The counter is what makes suppression observable. Nothing else about a
        withheld technology is visible from outside - the effect simply never
        happens - so without it there would be no way to tell a working hook
        from one that silently did nothing.
        """
        # Suppress:  it is our tree, the id is in range, and its bit is set.
        # Anything else tail-jumps to the applier and behaves normally.
        #
        # The id test is what stops this eating things it cannot give back.
        # Towers, walls and the ship unlocks all complete through this same
        # routine, and none of them is a technology the seed hands out - so
        # skipping their effects destroyed them outright. Only ids the client
        # has published, meaning ones with a `Tech:` item behind them, are
        # withheld.
        suppress = (
            b"\xff\x05" + struct.pack("<I", scratch + _COUNT)     # inc [count]
            + b"\xa3" + struct.pack("<I", scratch + _LAST)        # mov [last],eax
            + b"\xc3"                                             # ret
        )
        body = b"\x8b\x44\x24\x0c"                                # mov eax,[esp+0xC]
        body += b"\x3d" + struct.pack("<I", MAX_ID)               # cmp eax,MAX_ID
        # Past `bt` (7 bytes) and `jnc` (2) as well as the suppress block.
        body += b"\x73" + bytes([len(suppress) + 9])              # jae pass
        body += b"\x0f\xa3\x05" + struct.pack("<I", scratch + _TABLE)  # bt [table],eax
        body += b"\x73" + bytes([len(suppress)])                  # jnc pass
        body += suppress

        # Resolve the local player's tech tree here rather than being told it.
        #
        #     eax = [local_index]           ; which slot is the human
        #     eax = [player_table + eax*4]  ; the player object
        #     eax = [eax + 0x9CC]           ; its EETechTree
        #     cmp ecx, eax
        #
        # Waiting for the client to publish the pointer lost the race every
        # time: the game researches the earlier epochs' technologies while a
        # match loads, before a tech tree is resolvable from outside, and a
        # benefit already applied cannot be taken back. Doing it in the stub
        # means suppression is correct from the first call.
        lead = b"\xa1" + struct.pack("<I", self.local_index)       # mov eax,[idx]
        lead += b"\x8b\x04\x85" + struct.pack("<I", self.player_table)  # mov eax,[tbl+eax*4]
        lead += b"\x85\xc0"                                        # test eax,eax
        lead += b"\x74\x0a"                                        # jz  -> tail jump
        lead += b"\x8b\x80" + struct.pack("<I", PLAYER_TECHTREE)   # mov eax,[eax+0x9CC]
        lead += b"\x3b\xc8"                                        # cmp ecx,eax
        lead += b"\x74\x05"                                        # je  -> over the tail jump
        # Anything that is not our tree falls into the tail jump immediately
        # after; our own calls skip it and go on to the id test.
        code = lead
        code += b"\xe9" + struct.pack("<i", APPLY_FN - (scratch + len(code) + 5))
        head = len(code)
        code += body
        # `pass` is the tail-jump, reached by both id tests failing.
        code += b"\xe9" + struct.pack("<i", APPLY_FN - (scratch + len(code) + 5))
        assert len(code) - head == len(body) + 5
        return code

    def set_suppressible(self, ids) -> bool:
        """Publish the technology ids this client is allowed to withhold."""
        if self.scratch is None:
            return False
        table = bytearray(MAX_ID // 8)
        for value in ids:
            if isinstance(value, int) and 0 <= value < MAX_ID:
                table[value >> 3] |= 1 << (value & 7)
        return self.proc.write(self.scratch + _TABLE, bytes(table))

    def suppressed(self) -> int:
        """How many effect calls have been skipped for the local player."""
        if self.scratch is None:
            return 0
        return self.proc.read_u32(self.scratch + _COUNT) or 0

    def last_suppressed_id(self) -> int:
        """The technology id of the most recent skip, or 0."""
        if self.scratch is None:
            return 0
        return self.proc.read_u32(self.scratch + _LAST) or 0

    def reset_counters(self) -> None:
        if self.scratch is None:
            return
        self.proc.write(self.scratch + _COUNT, struct.pack("<I", 0))
        self.proc.write(self.scratch + _LAST, struct.pack("<I", 0))

    def adopt(self) -> bool:
        """Take ownership of a stub a previous client left behind.

        The patch lives in the game, not in this process, so a client that
        restarts mid-match finds the call site already redirected. Returning
        early on that leaves `scratch` unset, and every later use of it -
        publishing the tech tree, granting anything - fails silently while
        still reporting success. The stub's address is recoverable from the
        patched call, so it is adopted rather than abandoned.
        """
        raw = self.proc.read(CALL_SITE, PATCH_LEN)
        if not raw or raw == ORIGINAL or raw[0] != 0xE8:
            return False
        stub = (CALL_SITE + 5 + struct.unpack("<i", raw[1:5])[0]) & 0xFFFFFFFF
        # Only adopt something that is byte-for-byte the stub we would build.
        if self.proc.read(stub, len(self._stub(stub))) != self._stub(stub):
            return False
        self.scratch = stub
        return True

    def arm(self) -> bool:
        """Route the effect call through the stub. Idempotent."""
        if self.armed():
            if self.scratch is not None or self.adopt():
                return True
            # A stub from an older client, whose layout we no longer recognise.
            # Leaving it in place would keep suppressing through code we cannot
            # aim or account for, so take the call site back and arm our own.
            self.restore()
        if not self.usable():
            return False
        if self.scratch is None:
            self.scratch = self.proc.alloc(SCRATCH) or None
            if self.scratch is None:
                return False
            # Off until a tech tree is published, so arming alone is inert.
            self.proc.write(self.scratch + _TREE, struct.pack("<I", 0))
            self.proc.write(self.scratch + _COUNT, struct.pack("<I", 0))
            self.proc.write(self.scratch + _LAST, struct.pack("<I", 0))
        stub = self._stub(self.scratch)
        if not self.proc.write(self.scratch + _CODE, stub):
            return False
        if self.proc.read(self.scratch + _CODE, len(stub)) != stub:
            return False        # never execute a page we have not read back
        if self.proc.protect(CALL_SITE, PATCH_LEN) is None:
            return False
        rel = self.scratch + _CODE - (CALL_SITE + 5)
        return self.proc.write(CALL_SITE, b"\xe8" + struct.pack("<i", rel))

    def restore(self) -> bool:
        if not self.armed():
            return True
        self.proc.protect(CALL_SITE, PATCH_LEN)
        return self.proc.write(CALL_SITE, ORIGINAL)

    def set_local_tree(self, tree: int | None) -> bool:
        """Suppress effects for this tech tree, or none when given None."""
        if self.scratch is None:
            return False
        return self.proc.write(self.scratch + _TREE,
                               struct.pack("<I", tree or 0))

    # --- granting --------------------------------------------------------

    def tech_id(self, node: int) -> int | None:
        """The id the applier is called with for this node."""
        state = self.proc.read_u32(node + NODE_STATE)
        return self.proc.read_u32(state + STATE_ID) if state else None

    def args_for(self, node: int) -> tuple[int, ...] | None:
        """The five arguments the game would have passed for this node."""
        state = self.proc.read_u32(node + NODE_STATE)
        tree = self.proc.read_u32(node + NODE_TREE)
        if not state or not tree:
            return None
        values = (
            self.proc.read_u32(state + STATE_EFFECT_SET),
            self.proc.read_u32(tree + TREE_ARG),
            self.proc.read_u32(state + STATE_ID),
            self.proc.read_u32(tree + TREE_CONTEXT),
            0,
        )
        return None if any(v is None for v in values) else values

    def grant(self, node: int) -> bool:
        """Apply one technology's effect, as researching it would have.

        Runs on a thread of its own. The applier walks a static table and
        adjusts player stats, which is self-contained in a way the engine's
        end-of-match routine was not.

        Success is decided by a marker the stub writes after the call returns,
        not by the thread's exit code. The applier is a void function, so `eax`
        on return is whatever its loop happened to leave - judging by that
        reported failure for a call that had in fact worked, and the technology
        was never recorded as granted.
        """
        if self.scratch is None:
            return False
        args = self.args_for(node)
        if args is None:
            return False

        self.proc.write(self.scratch + _DONE, struct.pack("<I", 0))
        code = b""
        for value in reversed(args):        # cdecl: last argument pushed first
            code += b"\x68" + struct.pack("<I", value)
        code += b"\xe8" + struct.pack(
            "<i", APPLY_FN - (self.scratch + _GRANT + len(code) + 5))
        code += b"\x83\xc4\x14"             # add esp, 0x14
        code += b"\xff\x05" + struct.pack("<I", self.scratch + _DONE)  # inc [done]
        code += b"\xc2\x04\x00"             # ret 4  (thread procedure)
        if not self.proc.write(self.scratch + _GRANT, code):
            return False
        if self.proc.read(self.scratch + _GRANT, len(code)) != code:
            return False
        self.proc.run_thread(self.scratch + _GRANT, 0, timeout_ms=2000)
        return bool(self.proc.read_u32(self.scratch + _DONE))
