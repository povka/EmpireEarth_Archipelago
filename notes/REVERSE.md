# Empire Earth — Archipelago reverse engineering notes

## Target

| | |
|---|---|
| Build | `EE-AOC.exe` (Art of Conquest), GOG "Empire Earth Gold" |
| Path | `C:\Program Files (x86)\GOG Galaxy\Games\Empire Earth Gold\Empire Earth - The Art of Conquest\EE-AOC.exe` |
| Machine | x86 (32-bit), PE32 |
| ImageBase | `0x00400000` (fixed) |
| SizeOfImage | `0x67B000` |
| DllCharacteristics | `0x0000` — **no ASLR, no DEP** |
| Sections | 7 |

Because the image base is fixed and ASLR is off, any address inside
`0x00400000 .. 0x00A7B000` is stable across launches. Heap addresses are not,
so anything found on the heap needs a static pointer chain back into the image.

Other builds present on this machine (each needs its own profile):

- GOG vanilla `Empire Earth.exe` — 6,321,664 bytes, SizeOfImage `0x682000`
- NeoEE `Empire Earth.exe` — 11,978,080 bytes, SizeOfImage `0xB70000`, 15 sections
- NeoEE `EE-AOC.exe` — 12,071,792 bytes

NeoEE loads `dreXmod.dll` and has a `<CheatDetector>` block in `dreXmod.config`.
That is a multiplayer concern; single-player memory writes are unaffected. Do not
use this against NeoEE ranked/online games.

## The find

**Player table at `0x00930DB4`** — an array of 32-bit pointers, one per player
slot. Observed in a 1v1 skirmish:

| slot | meaning |
|---|---|
| 0 | neutral / Gaia (all resources zero) |
| 1 | player 1 — the human in a standard skirmish |
| 2 | player 2 — the AI |
| 3+ | null until occupied |

**Resource array at `player + 0xAFC`** — five consecutive `int32`, stride 4:

```
+0x00  Food
+0x04  Wood
+0x08  Stone
+0x0C  Gold
+0x10  Iron
```

Resources are plain **signed 32-bit integers**, not floats. Writes take effect
immediately and are reflected in the HUD.

So the full chain for the local player is:

```
static  0x00930DB8      (= player table + 1*4)
offsets [0xAFC]
kind    i32, stride 4
```

Verified: `resolve(0x00930DB8, [0xAFC])` -> `0x2ECA1B24`, which held
`(200, 175, 210, 0, 0)` exactly matching the on-screen HUD.

## Method

Blind approaches tried and rejected:

1. *Runs of five equal plausible values* — 4555 (i32) / 442 (f32) hits. Too noisy.
2. *Differential scan* (two snapshots 12 s apart, groups of five monotonically
   non-decreasing slots) — 7355 hits. The window predicate also let through
   all-zero groups that should not have qualified; `tools/diffscan.py` needs its
   count logic rechecked before it is trusted again.

What actually worked:

1. Ask for the five on-screen values and scan for them as an exact contiguous
   tuple (`tools/find_resources.py tuple 200 175 210 0 0`). Two candidates,
   both `i32` stride 4.
2. Disambiguate by writing a distinct marker through each and seeing which one
   the HUD reflects. Candidate `0x2ECA1B24` won; the other was a stale copy.
3. Reverse pointer scan. The first attempt with `--max-offset 0x800` found
   *nothing*, because the resource array sits `0xAFC` into the player object.
   Widening the window to `0x40000` and filtering to holders inside the exe
   image produced `0x00930DB8` immediately.
4. Dumping the statics around `0x00930DB8` revealed the whole player table,
   which confirmed the interpretation: the neighbouring slot resolved to the
   AI's stockpile.

Lesson for the next build: pointer scans need a max offset comfortably larger
than the object size, not just the struct size.

## Status

- [x] Tooling: process attach, region walk, scan, read/write, pointer chains
- [x] apworld generates a valid seed under Archipelago 0.6.7
- [x] Resource array located and interpreted
- [x] Static pointer chain to the resource array
- [x] End-to-end: multiworld item -> +500 Food in game

## End-to-end verification

With the server holding a `Food Bundle` for slot `EEPlayer`:

```
[Client]: Attached to EE-AOC.exe using profile 'GOG Empire Earth Gold - Art of Conquest'.
[Client]: Connected. Bundle size 500.
[Client]: Progress file: 13515657874892102023_EEPlayer.json (0 item(s) already applied).
[Client]: Received Food Bundle: +500 Food (now 1,700)
```

Reconnecting does not re-grant: the applied-item index is persisted per
seed+slot, because the server replays the full item list on every connect.

## Epochs

```
player + 0x9CC      -> EETechTree
  + 0x08            -> EETechTreeEpoch[15], stride 0x54
      + 0x04        -> flags; bit 0x10000 = "requirement satisfied"
      + 0x14        -> epoch index (self-describing, used as a write guard)
      + 0x40        -> qualifying buildings required (always 2)
      + 0x44        -> 1000 * (index + 1)  -- a score/SOL value, NOT the gate
      + 0x48        -> qualifying buildings built so far
  + 0x540           -> highest reachable epoch (14)
  + 0x544           -> epoch being advanced into (reads 1 while in Prehistoric)
```

Record `i` holds the requirements to **enter** epoch `i`. Epoch names come from
`Language.dll`'s ordered `EPOCHS` block at `0x100122D0`.

### The gate

Advancing needs two recruitment or technology buildings (walls, gates, towers
and houses do not count). The game evaluates this **when a building is
constructed** and caches the answer in the flag bit; the Capitol UI reads only
the cached flag. So:

- **lock** - clear bit `0x10000` and zero `+0x48`; the Advance button hides
- **unlock** - set the bit and set `+0x48` to `+0x40`; the button appears with
  no buildings needed, which is the "normal requirement disabled" part

Resource costs live elsewhere and are untouched. The Capitol's button panel is
built on selection, so a change only shows after re-selecting it.

### How this was found (four wrong guesses first)

Locking `+0x44`, zeroing `+0x44`, and zeroing `+0x40` (with and without a UI
refresh) all did nothing. The answer came from `tools/epoch_diff.py`:
snapshot the player object and tech tree with the button absent, build two
buildings so it appears, snapshot again, diff. The tech tree showed **exactly
two changed dwords**, both in epoch[1] - the count and the flag.

That also explains the `+0x40` failures: nothing re-runs the check, so lowering
the threshold after the fact can never help. **Measure the transition instead
of guessing at fields.**

## In-game chat

Empire Earth ships full MSVC **RTTI plus mangled import names**, so classes can
be recovered by name without a debugger. `tools/ee_rtti.py` turns a class name
into its vtable (and `--whatis` does the reverse). Assert strings even carry the
original source paths, e.g. `C:\EEX\Empire Earth\Communications\EEMessage.cpp`.

Relevant classes:

| class | meaning |
|---|---|
| `EEAAddChatMessage` | an `EEAction` carrying a chat line |
| `EEAction` | base class, refcounted, vtable `0x00838A90` |
| `EEUserInterface` | singleton at `[0x009318F8]` |
| `EEServer` | singleton at `[0x009319C8]`, null outside a match |

The game's own send path (`0x004BCD63`) does exactly this:

```
msg = operator new(0x24)                      ; 0x0069D178 -> MSVCRT ??2@YAPAXI@Z
EEAAddChatMessage::ctor(msg, &UWideString, type)  ; 0x004BDB42, __thiscall, ret 8
EEUserInterface::QueueAction(g_ui, msg)       ; 0x00678F79, __thiscall, ret 4
msg->Dereference()                            ; IAT 0x008371A8
```

`UWideString` is exported by **Low-Level Engine.dll** and, despite the name,
stores `char` — `??0UWideString@@QAE@PBD@Z` (RVA `0x83BB7`) constructs one from
a plain ASCII C string, and `??BUWideString@@QBEPBDXZ` returns `const char*`.
Confirmed empirically: injected text is found in memory as ASCII, never UTF-16.

The DLL **is relocated** (`ImageBase 0x10000000`, loaded at `0x01240000` in
testing) because it has a `.reloc` section — unlike the exe, its addresses must
be resolved at runtime via the module list.

`Chat.py` assembles a 109-byte x86 stub performing that sequence and runs it
with `CreateRemoteThread`. Before every injection it re-reads the constructor's
first 8 bytes (`56 8B F1 80 66 08 00 57`) and refuses to run if they differ, so
a different build can never execute the stub blind.

### Why it does not render (measured, not guessed)

`tools/diag_chat.py` runs a stub that only calls `UIManager::GetFormByID` and
`UIManager::GetCurrentForm` and stores the results, then walks the rest from
Python. In a single-player skirmish:

```
GetFormByID(0x1A) = 0x2E8E8BD0
GetCurrentForm()  = 0x2E498118   -> form id 0x0B = EEUIFMainGame
```

They differ, so `EEAAddChatMessage::Execute` takes its early-out every time.
Form `0x1A`'s widget (`[[form+0xF8]+0x20]`) is NULL in single player anyway.

**`EEAAddChatMessage` is the multiplayer chat action.** The single-player
in-game form is `EEUIFMainGame` (id `0x0B`), and the `MG` in `EEUIEMGDisplayChat`
/ `EEUIFMGGChat` stands for MainGame — that is the local path.

Widgets hanging off `[form(0x0B) + 0xF8]` (an array of control pointers):

| slot | class |
|---|---|
| `+0x00`..`+0x64` | generic DLL controls, mostly `UITextLabel` |
| `+0x68` | `EEUIMiniMap` |
| `+0x6C` | **`EEUIFMGErrorLog`** — the on-screen message area |
| `+0x70` | `EEUICSelectUnits` |
| `+0x74` | `EEUICCommandUnits` |
| `+0x78`, `+0x7C` | `EEUIFMGStatusBar` |

`EEUIFMGErrorLog`'s vtable is almost entirely inherited stubs, so its
"add a message" entry point is a non-virtual method and has to be found from
the call side rather than the vtable.

### Bonus finding

`[0x009318C4]` is the **local player index**, used as
`[0x00930DB4 + index*4]` — the same player table the resource code uses. This
replaces the hardcoded `player_index = 1` assumption in `Addresses.Profile`.

### The single-player message log (decoded)

Typing `ZZTESTCHAT99` to All and tracing it (`tools/trace_string.py`) found the
real storage. There are **two string classes**, easily confused:

| class | vtable (runtime) | layout |
|---|---|---|
| `UString` | `0x012D9C24` | `{vtable, char* buf, len, capacity}` = 0x10 |
| `UWideString` | `0x012D9C2C` | `{vtable, char* buf, len, len, capacity}` = 0x14 |

Neither stores wide characters — both hold `char`.

Log entries are **0x3C bytes**, laid out as:

```
+0x00  0xC bytes of header
+0x0C  UWideString  sender      e.g. "asapaska"
+0x20  UWideString  text        e.g. "(All) ZZTESTCHAT99"
+0x34  tail: 0x1964 (dwell?), colours, 1.0f
```

Dumped live with `tools/dump_log.py`, five entries matching exactly what was
typed. The `(All) ` prefix is formatted from a **Language.dll string resource**
(`0x1001F822`), not an exe literal, so there is no exe string to cross-reference.

### What is still missing

The function that **appends** an entry. Searching 964 MiB (including mapped
regions) found no pointer to the entry array, `EEUIFMGErrorLog` does not
reference it, and `push 0x3C; call operator new` turns out to be
`NEMClientConnectionRequest` — a size coincidence, not the allocator for these.

### The UI is an event queue (important)

`EEUserInterface`'s methods are thin wrappers around
`?Post@TSThread@@QAEJKPAX0_N@Z` — `TSThread::Post(id, p1, p2, bool)`. The UI is
driven by a **cross-thread message queue** with numeric event ids.
`tools/ui_events.py` recovers all 98 wrappers by byte pattern
(`68 <id> FF 15 <Post>`), no debugger needed. Known ids so far:

| id | meaning |
|---|---|
| `0x414` | show form (used by `EEUIEMGDisplayChat` to open the chat input) |
| `0x419` | posted by `EEASaveGame::Execute` after a successful save |
| `0x40C`, `0x417`, `0x428`, `0x415`, `0x41F`, `0x41E`, `0x40D` | unidentified |

Two consequences:

1. The chat log is written on **whichever thread drains that queue**, not the
   window thread. Watching only the window thread could never have caught it.
2. Posting the right event id may be a much cleaner way to display a message
   than calling an append function directly — and needs no code injection.

### Hardware breakpoints: what was learned (and what went wrong)

`tools/hwbp.py` works, but three separate bugs had to be fixed, and the
approach still cost two game crashes:

- **`Wow64SetThreadContext` does not program the debug registers.** For a WOW64
  target the DRs live in the *native* 64-bit `CONTEXT`; they must be set with
  plain `Get/SetThreadContext` and a 1232-byte `CONTEXT64` (`Dr0` at `+0x48`,
  `Rip` at `+0xF8`, 16-byte aligned). The WOW64 call returns success while
  doing nothing, so the tool now **reads the registers back** and treats a zero
  `Dr7` as failure.
- **Threads must be suspended** around `Get/SetThreadContext`. Not doing so
  crashed the game on the first attempt.
- **Arming all 26 threads crashed the game twice**, even with suspend/resume
  and correct registers. Suspending many threads in sequence can deadlock a
  process when one holds a lock. UI-thread-only runs never crashed.
- The tool should log **every** exception, not just `EXCEPTION_SINGLE_STEP` —
  a crash inside the target is currently invisible to it.

Watch targets tried and rejected: the next predicted log slot (entry placement
is not predictable — consecutive entries were `0x318` apart, not `0x3C`), the
`"(All)"` prefix (never exists as a standalone string; formatted from a
Language.dll resource each time), and the persistent player-name buffers
(never read on the window thread — see the event queue above).

### Chat: what works, what does not

**Working:** injected text reliably becomes a real, game-recognised message and
appears in the **Previous Messages** panel (PageUp). Three independent routes
all reach it:

| route | code | result |
|---|---|---|
| `EESMDialogMessage` + UI event `0x422` | `Chat._build_dialog_stub` | history **and** a centre-screen dialog box (1 frame) |
| `UIListBox<UWideString>::AppendLine` on `EEUIFMGErrorLog` | `Chat.append_line` | history only |
| build a UI text object + `0x005D32BF` | `Chat._build_ticker_stub` | history only |

**Not working:** the transparent **top-left ticker**. Everything injected lands
in history instead.

Hypotheses tested and disproven, in order:

1. *Text truncation* — no; the buffer always holds the full string. The field
   read as a length was misidentified.
2. *Zero timestamp at `+0x2C`* — no; setting it from `TMGetTime()` changed
   nothing.
3. *`EEUIFMGErrorLog` is the ticker* — no. It derives from
   `UIListBox<UWideString>` (its `AppendLine` is exported at RVA `0x62CA9`),
   and appending to it populates **Previous Messages**, not the ticker.
4. *`0x005D340D` builds a chat-log entry* — **no, and this invalidates the
   model built on it.** `tools/find_entries.py` matches its signature
   (`1.0f,1.0f,1.0f` + `UWideString` at `+0x20`) and finds **409** objects,
   including `'GAME PAUSED'`, the resource HUD numbers `'200'/'175'/'210'`,
   and `'Previous Messages (PageUp)'`. It is a **generic UI text control**,
   not a chat entry. The "0x3C log entry" interpretation of the earlier
   `ZZTESTCHAT99` scan was reading a UI control, not a message record.

5. *Reuse a `UITextLabel` on the main game form* — no. `vtable+0x88` is
   `?AppendText@UITextLabel@@UAEXABVUWideString@@@Z` (the very call
   `EEAAddChatMessage::Execute` makes in multiplayer), and it was invoked
   successfully on **all 31** `UITextLabel` slots of form `0x0B`. **Nothing
   appeared on screen.** The widgets under `[form+0xF8]` are therefore not the
   visible HUD text.

**Conclusion:** the ticker is a separate widget fed by its own path, still
unidentified. Approaches from the UI side have now been exhausted without
success. The productive next step is the receive side of `EEMInGameChat` /
`EEMChat` (both exist in RTTI) — i.e. what consumes chat *after* the network
layer — rather than more work from the widget tree.

### Safety rule learned the hard way

`vtable+0x88` means `AppendText` **only on `UITextLabel`**. Sweeping it across
every widget slot called a different method with a different signature on
`EEUICPortrait` (slot `+0xA8`) and crashed the game. `Chat.append_text` now
resolves `UITextLabel`'s vtable from the DLL base and refuses to run on any
widget that does not match. Never call a vtable slot without confirming the
object's class first.

### Next step: catch the writer with a hardware breakpoint

Snapshot diffing cannot reveal *who* wrote memory. The decisive move is to
attach as a debugger and set a **hardware write breakpoint (DR registers) on the
next free entry slot**, then type a chat message in game. The trap gives EIP =
the exact instruction that fills in a log entry, and its enclosing function is
the append routine we can then call directly.

Everything needed for that already exists in `Memory.py` (process handle,
read/write, remote threads); it needs `DebugActiveProcess` plus
`Get/SetThreadContext`.

### Status

The injection machinery is proven: stub assembly, remote thread execution,
`UWideString` construction (verified `{vtable, buf, len, len, cap}` with the
right length), and validation that refuses to run against a mismatched build.
The game stayed responsive across many injections. **Chat output is not working
yet** — the machinery is aimed at a function that is unreachable in single
player, and the local append entry point has not been found.

## Game data archives (data.ssa)

`data.ssa` is a `rass` archive: `'rass'`, u32 version, u32 reserved, u32
data-section start, then entries of `u32 name_len` / name / `u32 start` /
`u32 end` / `u32 size`, with `size == end - start + 1` as a self-check. Entries
start at **offset 16**. Base game: 3,739 entries; AoC: 826.

Almost every entry is **PKWARE DCL-imploded** behind a `PK01` header
(`'PK01'`, u32 uncompressed size, 4 reserved, then the DCL stream). That is why
a 155 MB archive shows only 22 `RIFF` chunks. `tools/blast.py` is a port of
Mark Adler's blast.c and decompresses them; `Assets.py` is the apworld-side
copy used to pull the message sound from the player's own install.

### db\dbobjects.dat - the object database

`u32 count`, then `count` fixed records of **1948** bytes
(`4 + 724*1948 == 1,410,356`, the exact file size). The internal name is at
record offset **+0x000**, NUL-terminated. The record index is the object id:

| index | name |
|---|---|
| 1 | `Priest` |
| 34 | `b  Barracks` |
| 41 | `b  Capitol` |

724 records, 612 named: **46 buildings** (names prefixed `b `) and 566 units.
`db\dbfamily.dat` is `u32 count` + fixed-size name records and lists 55
families (`Building`, `Human`, `Tank`, `Priest`, `Ship`, ...).

## Detecting what the player owns

The player's roster is an array of `(EEComplexUnit*, count)` pairs starting at
**player + 0x40**, stride 8, terminated by a null pointer. Units are recognised
by vtable `0x00846DDC`.

Each unit points at its **type definition** at **unit + 0x2C**. The definition
is one of the `EEUC*` classes (`EEUCBuilding`, `EEUCLandCitizen`,
`EEUCAmbient`, ...), so RTTI on its vtable gives the broad category. The
object's name is a `UWideString` at **definition + 0x1C**, and it matches the
record name in `db\dbobjects.dat` exactly:

```
unit +0x2C -> definition
definition +0x1C -> UWideString "b  Settlement"
definition +0x0C -> UWideString "Land Garrison"   (behaviour, not identity)
```

Verified live: six `Citizen`, two `b  Settlement`, one
`b  Guard Tower - Paleo` - matching what was actually on the map.

Matching on the **name** rather than a numeric id is deliberate: it lines up
with the generated `Objects.py` tables directly, with no index translation.

### What this is not

Several plausible-looking things were checked and ruled out, so they do not get
retried:

- The unit stores **no** `dbobjects` index, at any width, anywhere in its first
  0x800 bytes.
- `player + 0x698`, `+0x0B18`, `+0x0C44` are **aggregate** counters (they moved
  by +2 for two buildings, +1 for one), not per-type.
- `player + 0x1760` is a bitfield but only ~192 bits, far too small to be
  indexed by object id.
- The `EEDbObject` instances found by vtable scan are a 10-entry sub-block with
  nothing pointing into them; they are not the definition table.

## Gotchas hit along the way

- `ArchipelagoLauncher.exe` needs the component name as one quoted argument and
  a `--` before client flags, otherwise it parses `Empire` as the component and
  falls back to its GUI.
- `get_base_parser()` in 0.6.7 does **not** define `--name` or `--nogui`; the
  client adds them itself. An unrecognised flag raises `SystemExit`, which an
  `except Exception` will not catch — the client looked like it was dying
  silently.
- `CommonContext.seed_name` was empty when `Connected` arrived, so the seed key
  is read directly off the `RoomInfo` packet instead.
