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
Mark Adler's blast.c and decompresses them, which is how the object database
below is read. Nothing is unpacked at runtime: the apworld ships the generated
tables instead.

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

### Two traps in the epoch data

Both were found by generation hanging rather than by reading the tables, and
both make a family or object look available far earlier than it is.

**`x `-prefixed entries are scenario props, not units.** `x Dragon ME` is in the
Helicopter family at epoch 1 and dragged that family's floor from 9 down to 1.
The same prefix already had to be excluded from wonders, where `x RADAR Wonder`
shares the wonder category.

**And every match starts you with a Capitol and citizens**, whatever epoch it
begins in, so `Build Capitol` and `Recruit Citizen` carry no epoch requirement.
Without that exemption a Prehistoric start has *no* reachable location - nothing
else can be built until the Stone Age - and the filler spins forever with
nowhere to put the first epoch unlock. That is what a 300-second generation
timeout turned out to mean.

### Being in a unit family does not make something a unit

Three records are abilities filed under a unit family: `Hurricane` and
`Torpedo` under Ship, `Anti Matter Storm` under Helicopter, all at epoch 0 with
9999 hitpoints. Nothing can recruit one, so a check for it could never be sent -
and taking a family's floor as the minimum over its members claimed helicopters
were recruitable in the Prehistoric Age.

The family floor never saw them, because it ignores epoch 0 and no real unit
sits there (the earliest is the Citizen at 1). The **per-unit** tables did, and
that is how they reached `Objects.py` as recruitable units. `gen_objects.py`
now excludes them by name, in `NON_UNIT_NAMES`.

The general shape, and it has now cost two rounds: a filter that protects the
family view does not protect the per-unit view. They are separate emissions from
the same records.

### The morale heroes: one check that pays out twice

`h2-3` through `h2-14` are real, recruitable units, each facing an `h1-`
healing hero of the same tier. You cannot have both - taking either forecloses
the other - so a check on each is a pair the fill would treat as independent
when it is not, and one of the two could never be sent.

They were excluded outright at first. The better answer is to stop modelling
them as a choice: **recruiting either hero of a tier sends both checks.** Only
one can exist, so the pair is always satisfied together, and logically it
becomes one check that pays out twice - a thing the fill can represent, unlike
a choice. Which hero you actually build stays a free decision with no
consequences for the seed.

`UNIT_PAIR` in `Locations.py` pairs them by tier off the name (`h([12])[-
]?(\d+)`), `PAIRED_LOCATIONS` is the same relation between location names, and
`Client.locations_for` returns both. It is symmetric on purpose: a one-way
pairing would leave the morale side unsendable, which is the state this
replaced.

Two details worth keeping:

* **They get an id block of their own** (`PAIRED_UNIT_LOCATION_BASE = 2000`).
  `h2-` sorts into the middle of `TRAINABLE_UNITS`, so appending twelve names
  there would have renumbered every unit after them - the whole navy. All 343
  existing ids survived; twelve were added.
* **The heroes were also misnamed.** The general display rule strips only the
  first letters-and-digits run, so `h1-3 Sargon of Akkad (heal)` came out as
  `Recruit 3 Sargon of Akkad (heal)`, tier number and all. Heroes now get their
  own pass, dropping the tier and the `(heal)` / `(Morale)` role marker, which
  leaves `Recruit Sargon of Akkad`. All twenty-four stay distinct without the
  marker - checked, because the dedupe would otherwise have started appending
  `(2)` and quietly renamed one of them.

This is a **logic** decision, not a data one, so all of it lives in
`Locations.py` - `Objects.py` stays a faithful dump of the database, and what
counts as a check is decided in one place.

### Never hand-edit a generated table

`Objects.py` says "do not edit by hand" and was, once: the exclusions above were
made by deleting rows and commenting others out. `gen_objects.py` knew about
none of them, so `--write` would have silently put all sixteen records back, and
the reasons existed nowhere.

Deleting `b  Farm` did more than that. Building ids are assigned by enumerating
the table in sorted order, so dropping a row **shifted the location and item ids
of the twelve buildings that sort after it** (Fortress through University) -
exactly what the "ids never shift" comments in `Items.py` and `Locations.py`
promise not to do. Seeds rolled before that change do not match the apworld
after it. The removal stands; the shift is spent, and reversing it would only
cost a second one.

The `ALWAYS_BUILDABLE` guard in `Items.py` does not help here. It keeps a
building in the table while withholding its *unlock*, so excluding one that way
shifts nothing. Deleting the row is the thing that moves ids, and Farm is now
excluded in `gen_objects.py` instead - which reproduces the current table rather
than the pre-removal one.

An exclusion belongs in the generator or in `Locations.py`. Never in the output.

### Wonders need the Bronze Age, and the database does not say so

`+0x70` reads **1** for six of the seven wonders, and that is wrong: they cannot
be built until the **Bronze Age (3)**. Established by playing, in three steps
that between them rule out the alternatives:

| start | wonders available? |
|---|---|
| Copper Age (2) | no |
| Bronze Age (3), reached by advancing | yes |
| Middle Ages (5), from the start | **immediately** |

The third case is the one that matters: it rules out "one epoch after you
started" and pins the rule to a fixed floor.

No per-object field carries it. Searching every record for a field reading 3
across all six early wonders finds only `+0x68`, the family id, which is 3 for
"Building" by coincidence. So the requirement lives somewhere else in the engine
and `tools/gen_objects.py` applies `WONDER_EPOCH_FLOOR = 3` on top of the
database value. The Time Machine keeps its own higher floor of 14.

This was a live unwinnable-seed bug: a `wonder_victory` seed with a goal epoch
below Bronze offered wonders that could never be built. Generation now refuses
it, and `tools/test_generation.py` covers both sides.

**The general lesson:** `+0x70` is right for ordinary buildings and wrong for
wonders, so it is the game that decides, not the table. Anything derived from it
wants checking in play before it is trusted.

### Every object has an epoch floor - and logic needs it

`dbobjects` record **`+0x70`** is the earliest epoch an object can be built in.
It was used for wonders from the start, and *not* for buildings or units, which
were treated as always available. That was a real logic bug: generation placed
`Epoch: Bronze Age` on `Build Siege Factory`, and the Siege Factory needs the
Dark Age - the item was behind a check that could not be reached without it.

Thirteen of the twenty building checks are gated:

```
epoch 1  Barracks, Town Center, House, Capitol, Settlement
epoch 2  Dock, Temple, Archery Range
epoch 3  Farm, Granary, University, Hospital, Stable, Fortress
epoch 4  Siege Factory
epoch 10 Navy Yard, Airport, Tank Factory
epoch 13 Cyber Factory, Cyber Laboratory
```

A unit family's floor is the earliest epoch any of its members appears in.

Both are now generated into `Objects.py` and applied twice: a check is left out
of a seed whose goal epoch cannot reach it, and one that is included requires
the epoch unlocks that get there. `tools/test_generation.py` asserts no spoiler
ever places an epoch item on a check that needs it.

Note the fandom wiki puts Siege Factory in the Bronze Age while the database
says Dark. **The database wins** - it is what the engine enforces - and being
stricter can only make logic safer, never unwinnable.

### Finished, or still a building site

A building enters the roster the moment its **foundation is placed**, not when
it is finished. That is harmless for a "you built one of these" check but wrong
for the wonder goal, which would otherwise complete as the last wonder *starts*.

**unit + 0x34C** is 0 while an object is a construction site and 1 once it
stands. Found by diffing an unfinished wonder against buildings known to be
complete, which left two boolean candidates:

| offset | citizens | finished buildings | unfinished wonder |
|---|---|---|---|
| `+0x038` | 0 | 1 | 0 |
| `+0x34C` | 1 | 1 | 0 |

`+0x038` is 0 for units too, so it marks "counts as a building" rather than
completion. `+0x34C` is 1 for everything finished — buildings, citizens, even
path points — and 0 only for the site. Confirmed by watching a Settlement: it
read 0 for the ten seconds it took to build, then flipped to 1
(`tools/watch_wonders.py`, `tools/wonder_state.py`).

Matching on the **name** rather than a numeric id is deliberate: it lines up
with the generated `Objects.py` tables directly, with no index translation.

### Useful fields in a dbobjects record

| offset | meaning |
|---|---|
| `+0x00` | internal name, NUL-terminated |
| `+0x68` | family index into `dbfamily.dat` |
| `+0x6C` | category — 8 ordinary building, 10 tower/wall, 28 wonder |
| `+0x70` | earliest epoch the object can be built in |
| `+0x74` | the object's own index |

`+0x70` was confirmed against buildings of known epoch: Barracks 1, Archery
Range 2, Stable 3, Airport 10, Cyber Factory 13. There is **no** matching
"last epoch" field — Guard Tower - Paleo and friends stop being buildable
because a later variant supersedes them by name, which is why the curated
building list excludes them by name marker rather than by data.

The seven wonders are the records whose name starts with `w ` **and** whose
category is 28. Category alone is not enough: `x RADAR Wonder` and
`x Lighthouse` share it, but the `x ` prefix marks scenario props (alongside
`x Eiffel Tower`, `x Buckingham Palace`, `x Greek Ruins`) rather than anything
a skirmish can build. Six wonders are available from epoch 1; the Time Machine
needs epoch 14.

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

## Skirmish setup settings

Every dropdown on the skirmish setup screen is a plain `int32` in `.data`, and
the checkboxes are single bytes. No pointer chain, no per-match allocation — the
screen edits these directly, so writing one is exactly equivalent to picking it.

| address | setting | encoding |
|---|---|---|
| `0x00931630` | Game Speed | 0 Slow, 1 Standard, 2 Fast, 3 Very Fast |
| `0x00931638` | Map Size | 0 Tiny … 5 Gigantic |
| `0x0093163C` | Starting Epoch | 0 Prehistoric … 14 Space |
| `0x00931640` | Ending Epoch | 0 … 14 |
| `0x00931644` | Game Variant | **1 Tournament, 2 Standard** |
| `0x00931648` | Resources | 0 Tournament-Low … 4 Deathmatch |
| `0x0093164C` | Game Unit Limit | literal, 50–1200 step 50 |
| `0x00931650` | Wonders For Victory | literal, 0–6 |
| `0x00931654` | Difficulty | 0 Easy, 1 Medium, 2 Hard |
| `0x0093165D` | Lock Teams | 0 or 1 |
| `0x0093165E` | Lock Speed | 0 or 1 |
| `0x0093165F` | Reveal Map | 0 or 1 |
| `0x00931660` | Cheat Codes | 0 or 1 |
| `0x00931662` | Use Custom Civs | 0 or 1 |

The checkbox bytes are **not** in screen order, **not contiguous**, and the run
they sit in is not five checkboxes: `0x0093165C` reacts to nothing on the setup
screen and `0x00931661` sits between Cheat Codes and Use Custom Civs. Assuming
top-to-bottom order got all five wrong and would have written Reveal Map into a
byte that is not a checkbox at all. Each was pinned down by toggling that box
alone and watching which byte moved (`tools/watch_checkboxes.py`).

Game Unit Limit was the way in: it is the only setting whose on-screen value is
also its stored value, so a plain value scan found it, and everything else in
the block sat within 0x30 bytes of it. The rest were read off by setting each
dropdown to a distinct value and diffing the block (`tools/watch_settings.py`).

Game Variant is the only field that is not 0-based, and it was originally
misread as Map Type: a test that changed three settings at once made the wrong
attribution look convincing. A two-toggle test settled it. Anything inferred
from a single sample here should be re-tested by toggling that one control.

**Map Type is not in this block and is not enforced.** `0x0093160C` tracks it
but is derived rather than the selector — Large Islands and Planets Earth both
settle at 13, Planets Mars and Planets Small both at 18 — so writing it would
not select a map. The real value lives in the registry as a *string*
(`Map Type = "Tournament Islands"`), which is why no numeric selector was ever
found.

It stays unenforced **by choice**, not because the registry route is
impossible: forcing a map would lock every seed to the maps that ship with the
game and break custom maps for no benefit.

## Stopping the game ending the run

A skirmish can end three ways that have nothing to do with the seed's goal: you
wipe the AI out, the AI wipes you out, or a wonder victory fires. All three cut
a run short.

**`0x0093165C` is "Victory Allowed"**, and holding it at 0 stops all of them.

It is the byte in the checkbox run that no setup-screen checkbox ever moved,
because it is not on that screen: it is a registry-backed game option under
`HKCU\Software\Mad Doc Software\EE-AOC\Game Options`, read at startup with a
default of 1. (The key is absent on a fresh install, so the default is what
runs.)

Found by disassembly rather than scanning. The options loader at `0x00535780`
reads a run of booleans into consecutive bytes of one object, and the offsets it
uses resolve against a single base:

| offset | setting | address | base |
|---|---|---|---|
| `+0x404` | Victory Allowed | `0x0093165C` | `0x00931258` |
| `+0x405` | Lock Teams | `0x0093165D` | `0x00931258` |
| `+0x406` | Lock Speed | `0x0093165E` | `0x00931258` |
| `+0x408` | Cheat Codes | `0x00931660` | `0x00931258` |

Lock Teams, Lock Speed and Cheat Codes were already known from toggling them one
at a time, so three independent agreements on base `0x00931258` pin Victory
Allowed at `+0x404` without needing a fourth experiment.

**Confirmed empirically.** Wonders For Victory set to 1, Victory Allowed held at
0, one wonder built to completion: no victory screen, the match kept running.
That is the exact condition that normally ends a game instantly.

The game writes this byte itself (`0x005DCE1A`, `0x006970C7`) and compares it
for network sync (`0x005DB65C`), so it has to be held on every poll rather than
set once - which is what the client's settings enforcement already does.

### Holding the opponent at peace

The two dead ends below both tried to remove the opponent before the match
started, which is exactly where the game checks. Stance is per-player state
*inside* the match, so it can be set afterwards, when there is nothing left to
validate.

**`player + 0x09DC + slot*4`** is the stance toward that player slot:
`0` allied, `1` hostile.

Found by snapshotting the player objects, allying with the AI through the
diplomacy screen, and diffing (`tools/diplo_diff.py`): exactly one dword moved.
Guessing was hopeless first - the player object opens with the roster array at
`+0x40`, whose unit counts look just like team ids.

The encoding is pinned by every player reading `0` toward itself:

```
          ->gaia  ->you  ->ai
  gaia        0      1      1
  you         1      0      0     <- after allying from the diplomacy screen
  ai          1      1      0     <- still hostile toward you
```

Stance is **one-directional**. Allying from your side stops you attacking the
AI; it does nothing about the AI attacking you, so peace has to be written both
ways. Verified live: writing `0` into the AI's entry for the local player held.

Slot 0 is neutral nature and is left alone deliberately - making the animals
friendly would change how the map plays.

### Erasing a civilisation: not reachable by writing memory

Tried, because an opponent that does not exist beats one held at peace. It does
not work, and the reasons are worth keeping.

**Hitpoints are at `unit + 0x3C` (current) and `unit + 0x2A0` (max).** Both were
found by taking the database's max-HP field (`dbobjects` record `+0x78`) and
looking for that value inside a live object; they were told apart by the AI's
own construction sites, which ramp current HP toward a constant max
(1231 -> 941 -> 461 -> 171 -> 1 against 1450).

**Writing hitpoints does not kill anything.** A Spearman set to 0 stayed in the
roster at 0 hp indefinitely; set to -100 it stayed at -100. Empire Earth
evaluates death only inside its damage handling - there is no per-tick health
check - so no value that can be written triggers a death.

**Eliminating a player does not destroy their units either.** Resigning left
all six objects in the roster. So even with the elimination flag, setting it on
the AI would leave fifty units and buildings standing on the map, inert: worse
than simply leaving the opponent hostile.

That leaves calling the engine's own kill path per object, which means injecting
a remote thread - the first code execution in the project, and a good way to
leave dangling references in the world grid. Not attempted.

### The vtable swap does not work either (and how it fooled me)

`EEComputerPlayer` (vtable `0x0083A57C`) and `EEHumanPlayer` (`0x0083C330`) are
siblings; diffing the vtables shows the differing entries all pointing into
`0x0042D000-0x0043F000`, which really is the AI's own code. Pointing a computer
player's object at the human vtable is safe - the game runs happily for as long
as you like - but **it does not stop the AI**. Confirmed on a fresh match: with
the swap verified in place, the opponent went from 6 to 76 objects.

It was briefly believed to work, and the mistake is worth recording. The first
observation was a four-minute soak in which the AI's object count sat frozen at
128. That was a **Tiny map on which the AI had already saturated the available
space** - it had stopped building for its own reasons, and the swap had nothing
to do with it. No unswapped baseline was measured over the same window, so a
natural plateau was read as a result.

Lesson, and it is the same one as the Game Variant misattribution: *a value that
stops changing is not evidence that you stopped it.* Measure the control.

So the AI's decision-making is not dispatched through the player object at all.
It must live in the `EECP*` subsystem (`EECPIntelligencePlayerFile`,
`EECPPlayerInteractionManager`), which holds its own references and would have
to be found separately.

### Making the game declare *your* win does not work either

The obvious way to have a completed seed also win the match: mark the opponents
defeated, mark yourself victorious, then release the victory gate. Tried, and it
does the opposite - **you end up defeated**.

```
14:02:40,779  wrote: player 2 defeated, you victorious, gate released
14:02:41,294  the game had rewritten you to defeated
```

Half a second after the gate opened, the engine had re-evaluated the whole thing
and marked *both* players defeated. That is the same lesson as everywhere else
here: `+0x0A28` is a record the engine owns, and it only stays written while the
engine is not looking. Releasing the gate is precisely what makes it look.

There is also no victory condition left to satisfy honestly. Conquest needs the
opponent eliminated, which cannot be done; wonders are the only other route, and
they only exist in a wonder-goal seed. So for a `reach_epoch` seed there is
nothing to trigger.

The client therefore does not touch the outcome on goal completion. Finishing a
seed leaves the match running, and the player quits when they are ready.

### Two more ways of stopping a computer player that do not work

**Writing the outcome field does not eliminate anyone.** Setting an AI's
`+0x0A28` to 2 (defeated) holds - the engine does not overwrite it - but the AI
carries on completely unaffected: 10 objects to 31 in 44 seconds, units moving
throughout. The field *records* an outcome that the elimination path sets; it
does not *cause* one.

**Starving a computer player does not work either.** Holding all five of an AI's
resource slots at 0 for a minute did nothing: 54 objects to 85. Computer players
do not spend from the array at `+0xAFC` that drives the human economy, so it can
be emptied without slowing them at all. (The same array is definitely real for
the human player - granting resources through it updates the HUD.)

Together with hitpoints not killing and elimination not destroying units, that
is every data-level lever tried against a computer player. Anything further has
to reach the AI subsystem itself - the `EECP*` classes
(`EECPIntelligencePlayerFile`, `EECPPlayerInteractionManager`) - rather than the
player object.

### How a match outcome is recorded

**`player + 0x0A28`**: 0 undecided, 1 victorious, 2 defeated. Observed by
resigning: the resigning player went 0 -> 2 at the moment the game announced the
opponent victorious, and that opponent read 1.

This matters for a real defect rather than curiosity. Holding `Victory Allowed`
off stops the match **tearing down**, not the defeat itself, so a defeated
player is left unable to act in a match that never ends, with their units still
in the roster - a state nothing else the client watches would detect. The client
reads this field so it can say the seed is intact and the player should quit to
the menu.

### Two dead ends, so nobody retries them

Both were attempts to remove the opponent instead of suppressing victory, and
both are hard-blocked by the Start Game validator at `0x005DA876`:

- **Solo.** The player-slot array at `0x0093125C` (stride `0x38`, 16 slots,
  self-describing index at `+0x20`, type at `+0x00`: 1 human, 0 computer,
  4 closed) can be edited freely, and the UI honours it - but Start Game then
  refuses with *"You can't play a game with only one player."* The UI can close
  every slot on its own anyway, so the array was never the obstacle.
- **Allying the only AI.** Also refused: *"All players can't be on the same
  team!"*

The validator cannot simply be stubbed to return true: it also loads the map and
scenario (it reads `0x931634` and `0x931608` and calls into the map loader), so
skipping it skips real setup work. Suppressing victory is both simpler and
strictly a data write.

## The `--GAME--` banner: found

The in-game message line (`--GAME-- Player 'Babylon - (Computer)' is
victorious!`) is produced by two functions, both callable.

Finding it needed one indirection: the text lives in `Language.dll` as
**STRINGTABLE resources**, loaded by numeric id, so searching the exe for the
string or for xrefs to its address finds nothing. Resolve the ids first, then
scan `.text` for `push imm32` of those ids.

| id | string |
|---|---|
| 31813 `0x7C45` | `--GAME--` |
| 31814 `0x7C46` | `Player '%s' has been defeated!` |
| 31815 `0x7C47` | `Player '%s' is victorious!` |
| 31808 `0x7C40` | `Player %s has resigned from the game` |
| 30401 `0x76C1` | `You are Victorious!` |

### The banner itself - `0x006794C6`

`__thiscall` on the **`EEUserInterface` singleton at `[0x009318F8]`**:

```
ecx  = [0x009318F8]
arg1 = float[3]      RGB; the caller passes 1.0, 1.0, 1.0 (white)
arg2 = UString*      prefix - the caller loads string 31813, "--GAME--"
arg3 = UString*      the message body
arg4 = int           colour index, from [[0x0092FCA8]+0x2CC] << 1
arg5 = 0
```

This is the target for putting the Archipelago log in the game. Strings are
built with `UWideString` from **Low-Level Engine.dll** (`??0UWideString@@QAE@PBD@Z`,
RVA `0x83BB7`), which despite the name takes a plain ASCII `char*` - see the
chat section.

### The outcome announcer - `0x0056AF5C`

`__thiscall` on a **player object**, one stack arg: `1` victorious, `2`
defeated.

```
0x0056AF93  cmp ebx, 1                 ; arg
0x0056AF98  cmp [esi+0xa28], ebx       ; already this outcome? -> return
0x0056AFA8  push 0x7c47                ; pick the string
0x0056B05E  call 0x6794c6              ; show the banner
0x0056B063  mov [esi+0xa28], ebx       ; and only then record the outcome
```

Note the order: **the outcome field is written last, by this function.** That is
exactly why writing `+0x0A28` directly never worked - it is the announcer's
bookkeeping, not a switch. Calling this function instead does the announcement
*and* the record, the engine's own way.

So a completed seed could plausibly announce a real win by calling
`0x0056AF5C(player, 1)`. Whether the match then *ends* is a separate question -
that still depends on the victory gate and the conditions behind it.

### Confirmed working, from an injected thread

`tools/inject.py` calls it and the banner appears in game:
`--AP-- Archipelago connected`.

The recipe, all from outside the process:

1. `VirtualAllocEx` an RWX page, write data and a short x86 stub, run it with
   `CreateRemoteThread`.
2. Build two `UWideString`s with `??0UWideString@@QAE@PBD@Z` (Low-Level Engine
   DLL, RVA `0x83BB7`, `__thiscall`, takes a plain `char*`). The DLL relocates,
   so resolve its base at runtime.
3. `ecx = [0x009318F8]`, push `(rgb, prefix, text, colour, 0)`, call
   `0x006794C6`. Callee cleans - `ret 0x14`.

`arg4` is computed exactly as the game does it, `[[0x0092FCA8]+0x2CC] << 1`
(observed 6500 -> 13000). It works copied verbatim; its meaning is still
unknown, and it is not obviously a colour.

Two things that were *feared* and turned out not to be problems:

- **Thread safety.** The function's first act is `operator new`, and it ends by
  dispatching into UI state, so calling it from our own thread while the game
  loop runs looked dangerous. It has been fine across repeated calls.
- **Cross-bitness injection.** A 64-bit Python creating a remote thread in the
  32-bit game works.

Both were blamed, at length, for crashes that were actually caused by the
harness allocating a page and never writing the stub into it - so the thread was
executing zeros. **Read the stub back out of the target before running it**;
`inject.py` now does. Disassembling the local copy proves nothing.

## Ending the match: the map, and why a foreign thread is not enough

The full chain, all found from the `--GAME--` string ids:

| address | what it is |
|---|---|
| `0x0053C9B4` | `EEWorld::CheckVictory()` - `__thiscall` on the static world object `0x00930D40`, no args, returns 0 if the match is not over. Walks the player table (at world `+0x74`, count at `+0xCC`), skips anyone whose `+0x0A28` is already set, and announces the rest. |
| `0x00551F3A` | **end the match** - `__thiscall(this, bool won)`, `ret 4`. Sets the game-over flag at `0x00929065`, announces every player victorious or defeated, then does the real end-of-match work. |
| `0x0056AF5C` | announce one player's outcome; writes `+0x0A28` last |
| `0x006794C6` | `ShowGameMessage` - draws the banner |

The caller ties them together:

```
mov ecx, 0x930d40
call 0x53c9b4              ; evaluate
test eax, eax / je ...     ; 0 -> nothing to do
mov [[0x931864]+0x200], eax ; record the result
cmp ecx, 1 / sete al
call 0x551f3a              ; end it, won/lost
```

`this` for `0x00551F3A` is dereferenced **once**, at the very end
(`mov byte [this+0xE6], 1`), so any writable address satisfies it - the rest
runs off globals.

**Calling it from an injected thread crashes the game.** The game-over flag does
get set, so execution reaches `0x00551F65`, and then it faults in what follows:
`player_table[local]`, string formatting through an imported helper, a virtual
call on `EEServer` at `[0x9319C8]`, and a screen transition.

That is the difference between this and the banner. `ShowGameMessage` allocates
one object and queues it - self-contained, and it survives being called from our
own thread. Ending the match mutates game-wide state and drives the UI, and it
does not.

**The fix is a hook, not a better call.** `0x00553082` - the function that calls
`CheckVictory` - looks to run every frame, and is `__thiscall`, so hooking its
entry gives both the game's own thread *and* the real `this` in `ecx`. A
one-shot detour there (restore the original bytes, call `0x00551F3A(ecx, 1)`,
jump to the original) is the shape that should work.

### Still to determine

- What `arg4` and `arg5` actually mean.
- The two `UWideString`s we construct are never destructed, so each message
  leaks its small buffer. `??1UWideString@@QAE@XZ` should be called after.

## Next: the `--GAME--` banner, and why injection is the unlock

Every failed attempt in this project shares one shape. The client can write the
engine's data, but cannot make the engine **act**:

| written | outcome |
|---|---|
| hitpoints 0 / negative | stored, ignored - death only happens in damage handling |
| outcome = defeated (on the AI) | stored, ignored - it is a record |
| outcome = victorious (on us) | stored, then overwritten the moment the engine evaluated |
| resources = 0 (on the AI) | stored, ignored - computer players do not spend from it |
| player vtable = human | stored, ignored - AI dispatch is not through the player object |

That single missing capability - running code in-process - blocks the in-game
win, removing the opponent, and in-game notifications alike. They are one
problem, not three.

**The `--GAME--` banner is the agreed next target.** It is the in-game message
line that shows e.g. `--GAME-- Player 'Babylon - (Computer)' is victorious!`,
and it appears **in single-player**, which contradicts the earlier conclusion in
the chat section that this display was multiplayer-only. The string is not a
literal in `EE-AOC.exe` or `Language.dll`, so it is assembled at runtime.

It is the right first target: the smallest useful feature, wanted in its own
right (the Archipelago log belongs there rather than only in the external
overlay), and it proves out injection before harder features depend on it.

Approaches, least to most invasive - note the first two leave game files
untouched:

1. **Remote-thread shellcode.** Allocate in the target, write an x86 stub that
   calls the game's own functions, `CreateRemoteThread`. Pure Python, no
   compiler, nothing shipped but source. Risk is thread safety: calling engine
   functions from a foreign thread while the game loop runs is how an RTS gets
   corrupted.
2. **Injected DLL hooking the game loop**, so calls happen on the game's own
   thread. Correct and robust; costs a C++ toolchain, a compiled binary in the
   apworld, and near-certain antivirus false positives.
3. **Patching the exe on disk.** Breaks GOG integrity. Avoid.

### GOG and Steam are the same game

Empire Earth Gold came to Steam on 26 May 2026. It is **not** a new build:

| file | GOG vs Steam |
|---|---|
| `EE-AOC.exe` | every PE section byte-identical; only the file is 15,720 bytes larger, appended outside the sections |
| `Language.dll` | identical |
| `Low-Level Engine.dll` | identical |
| `Default.dll` | identical |
| `data.ssa` (both) | identical |

Same image base, same section layout, no ASLR on either. So **every address,
string id and generated table here is valid for both**, and the two entries in
`PROFILES` differ only in the file size they match on. The tree difference is
store furniture: `steam_appid.txt` and `steam_autocloud.vdf` files on one side,
`EULA.txt` on the other.

`tools/install.py` locates whichever install is present, so nothing in the
tooling is tied to a store. Override with `EE_ROOT`.

**One real difference, and it is not in the files.** The Steam release ships an
AppCompat layer for its own install path:

```
HKCU\...\AppCompatFlags\Layers
  ...\Steam\steamapps\common\Empire Earth Gold Edition\...\ee-aoc.exe
      -> WIN7RTM RUNASADMIN HIGHDPIAWARE
```

so the Steam game **always runs elevated** and prompts for UAC, while GOG (which
gets only `HIGHDPIAWARE`) does not. Neither executable has an embedded
`requestedExecutionLevel`, so this is purely the registry layer.

The consequence for this project is total: a non-elevated client gets
`ERROR_ACCESS_DENIED` from `OpenProcess` for **every** right, including
`PROCESS_QUERY_INFORMATION`. Windows will not even report the elevated
process's executable path or command line. The client detects this and says so,
rather than repeating "waiting for Empire Earth to start" at a game that is
plainly running.

### Two installs

`C:\Empire Earth Gold` is a byte-identical copy kept so that a broken patch
does not mean re-downloading from GOG. **Anything that writes to game files
targets that copy**, not the GOG install.

This is not a constraint on the client, which may attach to any running
`EE-AOC.exe`. The RE tools default to the GOG path for *reading*, which is fine
as the two are identical.

## Locking individual buildings: solved

**`node + 0x06` is the gate.** Clear that byte and the object disappears from
the build menu; restore it and it comes back. Verified live on Barracks.

It was found by reading the **consumer** rather than by looking for a field that
correlates. `EETechTreeNode` vtable[1], **`0x005CF686`**, is the availability
predicate:

```
cmp byte [esi+6], 0          ; <- the gate. zero -> unavailable
je  fail
call [eax+8]                 ; vtable[2] = IsObsolete (0x005CF742):
                             ;   node+0x18 vs tree+0x538
test al, al / jne fail
cmp byte [esi+0x22], al      ; non-zero -> unavailable
jne fail
mov ecx, [esi+0xc]           ; the tech tree
mov eax, [ecx+0x538]         ; current epoch
cmp [esi+0x14], eax          ; the node's own epoch requirement
jg  fail
...                          ; further checks via [esi+8] +0x48 / +0x7C
push 1 / pop eax             ; available
```

Two things fall out of that listing:

* the **epoch requirement is separate**, at `+0x14` against the current epoch,
  so gating a building through `+0x06` leaves the game's own epoch rules intact
* **`+0x20` is never read**. Three separate theories about that field - bit
  `0x10000`, bit `0x1`, and `0x1|0x2|0x4` together - all correlated beautifully
  with availability and all did nothing when written, because nothing consumes
  it. It is a record, like `+0x0A28` for match outcomes.

### The node array

Scan for vtable **`0x00846150`**; nodes are `0x30` bytes in contiguous
per-player arrays (3112 in a 3-player match).

```
+0x04  read by the predicate
+0x06  AVAILABILITY - the gate
+0x08  object the predicate reads +0x48 and +0x7C from
+0x0C  the EETechTree
+0x10  EEButtonObject; its +0x04 is a UString icon texture, e.g.
       'textures\but_barracks.sst' - still the only way found to tell which
       object a node belongs to
+0x14  epoch requirement, compared against tree+0x538
+0x18  obsolete-after epoch (15 = never)
+0x20  bookkeeping, not consumed
+0x22  read by the predicate; non-zero blocks availability
```

## Technologies

### Open, next session

Both halves work when driven by hand; the end-to-end run through the client
found two things still to settle.

1. **The grant never fired through the client.** `Tech: Excommunication` was
   received and `granted_techs` stayed empty, with no `Applied ...` line.
   Calling `TechEffects.grant()` directly works, so it is the client path.
   `sync_tech_effects` wraps its body in a bare `except Exception: return`,
   which is exactly what hides this - make it log before anything else.

2. **The skip counter read 1 before any research happened.** Starting in a
   later epoch makes the game auto-research every earlier epoch's
   technologies, and those may run through the same completion routine - in
   which case suppression is denying benefits the game means to give away, and
   the player silently starts weaker. Confirm the cause before choosing a fix:
   either hold suppression off until the match has finished loading, or
   suppress only technologies this seed offers as items.

### Per-unit checks: real checks, with retirement switched off

These were filler-only for a while. A unit stops being offered once a later
tier replaces it, so a check for one can become unsendable, and `node+0x18`
would say which - except only **43 of 178** units can be tied to a node at all.
Rather than guess, every unit check was marked `LocationProgressType.EXCLUDED`.

That is no longer the trade. The engine has two retirement paths and
`Obsolescence.py` clears both on every node of the local tree - `+0x05`
(superseded) to zero and `+0x18` (obsolete-after) to 15, meaning never - so
nothing is ever withdrawn. Verified in a live match: a Rock Thrower survived
Stone -> Copper -> Bronze, and 0 of 778 nodes were left retirable. The checks
are ordinary progression checks now.

> **This is only half true, and the other half is a live bug.** Clearing
> `+0x05` does not preserve an old unit beside its replacement - it cancels the
> upgrade. See "Clearing `+0x05` cancels the upgrade" below before trusting
> anything in this section.

Two bugs came out of the first two-player run, and both were about which units
exist rather than about the memory work:

* **`Inf01 - Rock Thrower` sent nothing.** Its family is `Human`, and the
  generator took units from a hand-written list of 27 families that did not
  include it - nor `Hero`, `Aircraft Carrier Fighter`, or any of the six `Mech`
  families. A curated list was right when a check meant "recruit anything in
  this family"; once each unit had its own check, anything left out simply had
  no check. `gen_objects.py` now takes every family except a small set that
  holds no recruitable unit, and the count went 147 -> 218.
* **`Epoch: Dark Age` was placed behind `Recruit Cataphract`**, which is a Dark
  Age unit, so the seed could not be finished. Per-unit checks had inherited
  their *family's* floor, and a family's floor is its earliest member: the
  Lancer family starts at a Copper Age Horseman.

The lesson the second one repeats: the circular-placement test would have
caught it, but that test reads `LOCATION_MIN_EPOCH` - the same table that was
wrong. `tools/test_generation.py` now also checks the floors against
`data.ssa` directly, which is the only reading a wrong table cannot pass.

### Clearing `+0x05` cancels the upgrade - OPEN, and it breaks seeds

Observed in play: upgrade a Slinger to a Simple Bowman, advance one more epoch,
and the Archery Range is offering **Slingers again**.

`Obsolescence.py` clears both retirement paths on every node, and the two are
not the same kind of thing:

| field | meaning | clearing it |
|---|---|---|
| `+0x18` | "expires after epoch N" | correct - this is what keeps a Rock Thrower recruitable |
| `+0x05` | "a specific later unit **has replaced** this one" | wrong - this is the upgrade link itself |

`+0x05` is not a expiry date, it is the engine's record that the upgrade
happened. Zeroing it does not keep the Slinger available *alongside* the Simple
Bowman; it un-does the replacement, and the menu falls back to the earlier tier.

**This is a seed-breaking bug, not a cosmetic one.** If the menu reverts, the
replacement's own check cannot be sent, and per-unit checks hold progression -
so a seed can be left unfinishable. It is the same severity as
`Epoch: Bronze Age` on `Build Siege Factory`, arriving by a different route.

#### The fix, and why it cannot be written yet

The right shape is to stop fighting the engine: leave `+0x05` alone, let
upgrades happen, and make **recruiting a unit send the checks for everything it
supersedes** - build a Simple Bowman and Slinger's check goes too.

That needs a table of which unit supersedes which. **The repo does not have
one, and nothing shipped with the game yields it reliably.**

*Family is not the chain.* `Human` holds `Domestic Wolf`, `Inf01 - Rock
Thrower`, `Prophet`, three Field Medics and several separate infantry lines.

*Names are not the chain either*, though they look like it. Tier numbers give
`Arch02 -> Arch03 -> Arch05 -> Arch06`, and then twenty groups turn out to hold
several units at the same tier - which are **alternatives, not upgrades**. The
clearest case is the `Ship` family at tier 4:

```
s04 Bronze Catapult Ship   s04 Bronze Frigate
s04 Bronze Transport       s04 Fishing Boat Bronze
```

A Fishing Boat does not upgrade into a Frigate. The real chain runs per *role* -
Fishing Boat Stone -> Bronze -> Imperial -> Modern -> Digital - and the role is
in the descriptive text, not the tier prefix. `Siege04 - Ram` vs
`Siege04 - Tower` and the three `Inf10` weapons are the same story.

Scale: **118 of the 203 units are not the top tier of their group**, so this
governs most of the check pool.

#### The asymmetry that should drive the design

* A **missing** link - A is superseded, nothing sends A's check - is
  unwinnable.
* An **extra** link - a check sent for something never built - is a free check,
  and the seed still completes.

Errors are survivable in one direction only. That argues against a tight
heuristic and in favour of finding the real relation.

#### Where to look first: `dbobjects.dat`

A record is **1948 bytes** and this project has identified about six fields. An
"upgrades to" object index is exactly the sort of thing that would live in one,
and `+0x74` already gives every record its own index, so a link would be
immediately recognisable.

The test is mechanical and needs only `data.ssa`:

1. Take `Arch02 - Slinger`'s record, scan its 1948 bytes for a dword equal to
   `Arch03 - Simple Bowman`'s index.
2. Check the same offset holds Maceman's index in `Inf01 - Clubman`'s record,
   and Cataphract's in `Cav03 - Horseman`'s.

Three agreements pin it, the same way `+0x404` was pinned for Victory Allowed.
If the field is not there, one run has ruled it out.

Two fallbacks, in order of preference:

* **Read it from the live game.** The engine sets `+0x05` on the superseded
  node at the epoch transition, so the client could watch which nodes are
  retired and pair them with what appeared. Exact and self-maintaining; needs
  the pairing handle found first - `node+0x10`'s `EEButtonObject` is the
  obvious candidate, since an upgrade plausibly reuses the build-menu slot.
* **Name heuristic plus a manual correction table** for the twenty ambiguous
  groups. Works with no game at all, but it is a guess spread over 118 checks,
  in a place where guessing wrong is unwinnable.

#### Interim safety, if the chain is still unknown

Stop clearing `+0x05` and demote unit checks to non-progression again. The game
then behaves correctly and no seed can be broken; the cost is that unit checks
stop carrying anything, which is where they were before this section was
written. Worth taking if the chain hunt stalls - a correct game with weaker
checks beats a seed that cannot be finished.

### Unit epochs: settled by the shipped PDF

`UNIT_MIN_EPOCH` was long suspected of reading an epoch high, the same way the
buildings did, and `tools/gen_unit_epochs.py` could not settle it. That join
goes from a database name to a tech tree node with the icon as its only handle:
name alone linked `but_a10_10t` to `AA10 - Stinger Soldier`, an aircraft to a
foot soldier, and adding the tier number left only 16 of 27 families matching,
most on one or two members out of a dozen. Since a family's floor is its
earliest member, a partial match *overestimates* - `Aircraft` came out Digital
Age off a single late-tier plane - so the database value stayed.

`technology_tree.pdf` settles it without the join. Page 2 prints an epoch for
every unit and building in Roman numerals, and for buildings all three sources
line up at once:

```
Granary      PDF III      database 3      running game's tech tree 2
```

Epoch 2 is the Copper Age, which is where the game actually offers a Granary.
So the PDF and the database share a numbering that starts at I for the
Prehistoric Age, and it is one above the tree's. The same comparison across
units: the database agrees with the PDF on **410 of the 417** rows that name
exactly one unit, and reads one *high* on the other seven (`Field Medic -
Imperial` is printed VIII and stored 9) - never one low.

So the correction is `max(raw - 1, 0)`, and its error can only ever be an epoch
late, which costs a check but cannot make a seed unwinnable. This is what made
a Cataphract a Dark Age unit rather than a Middle Ages one, and a Citizen a
Prehistoric one rather than a Stone Age one.

A recruit floor is `max(unit epoch, earliest producer's epoch)`. The producer
half is not redundant: a Rock Thrower is a Prehistoric unit, so its own epoch
requires nothing, and what actually gates it is having a Barracks.


`node + 0x04` is set when a technology has been researched. Measured, twice:
snapshot every node, research exactly one thing, diff. Only that node moved.

`node + 0x21` is what removes a researched technology from its menu. Clearing
`+0x04` alone does not bring the button back; clearing `+0x21` as well does,
and the control (a second technology left researched) stayed gone.

`node + 0x22` looks like research state and is not. It is set on the same seven
entries in every player's tree **and** in the static template tree that belongs
to nobody, so it marks entries switched off for the game mode.

### Where research completes, and where the effect is applied

`EETechTreeNode` vtable[6], **`0x005CFA53`**, completes a research:

```
cmp  byte [esi+0x22], 0      ; mode-disabled
cmp  byte [esi+6], 0         ; available
mov  byte [esi+4], 1         ; mark researched
push [ecx+0x534]             ; ecx = [esi+0xC], the tech tree
push [eax+0x4C]              ; eax = [esi+8]; the technology id
push [ecx+4]
push [eax+0x50]              ; which effect set to apply
call 0x005CA76C              ; apply the effect
```

`0x005CA76C` is data-driven: it indexes a table at **`0x0095CF80`** (stride
0x10) by the effect set, and calls `0x005CA7CF` once per entry.

Two things follow, and they are what an "AP grants the benefit" mode needs.
The flag write and the effect call are *separate statements*, so research can
be made to send a check and do nothing else. And at the call site
`0x005CFAAF`, `ecx` still holds the node's tech tree - loaded three
instructions earlier and never clobbered - so a detour can suppress only the
local player's effects and leave the AI's research working.

### Both halves verified

**Suppression.** Patch the `call` at `0x005CFAAF` to a stub that compares `ecx`
against the local tech tree and skips when it matches. The stub counts its own
skips, because a withheld technology is otherwise invisible from outside -
there is no way to tell a working hook from one silently doing nothing. One
research produced exactly one skip, the AI's research passed through, and the
game stayed up.

**Granting.** Call `0x005CA76C` on an injected thread with the five arguments
rebuilt from the node: `[node+8]+0x50`, `[tree+4]`, `[node+8]+0x4C`,
`[tree+0x534]`, 0. Unlike the end-of-match routine, this one survives being
called from outside - it walks a static table and adjusts player state.

Proving it took a technology with a *visible discrete* effect. Sanitation is
+5 population capacity: three grants moved the cap 150 -> 165. Diffing the
player object showed nothing, so the effects do not land in its first 0xB10
bytes; the HUD is what settled it.

`[tree+0x534]` is the player object, and `[player+0x45C]` is the player's slot
index - which is what the applier passes down as `ebx`, not a pointer.

**Granting is cumulative, not idempotent.** Three calls gave three bonuses. So
the client persists which technologies it has granted, keyed by the match's
tech tree: a reconnect mid-match must not reapply them, while a new match must,
because the game starts it with none.

This was found statically, from the vtable, after the hardware breakpoint
approach crashed the game at the exact moment the write happened.
`tools/hwbp.py` reports the write but does not survive it here; its own help
calls `--all-threads` riskier, and that is what it cost. Reading the vtable was
both safer and faster.

### A patch outlives the client, and the game does not notice

Everything the client writes lives in the *game's* address space. Closing the
client frees nothing: the detour at `0x005CFAAF` still points at a page that is
still mapped, and the stub still runs on every research. So a client that exited
mid-match left technology benefits suppressed **forever** - the half that
withholds kept working, and the half that gives them back was gone. Same shape
for a building held out of the build menu: the engine only writes `+0x06` on the
epoch transition that would have opened it anyway, so one already past its epoch
is never reconsidered.

Nothing in the game detects this. There is no owner, no timeout, no handle
whose closing undoes it - the patched five bytes are simply what the code says
now.

`EmpireEarthContext.release_game()` undoes the three that do not heal on their
own: the effect detour, the win detour if it was armed and never fired, and the
building locks. It runs after the watcher is cancelled and awaited, because a
poll already in flight will otherwise re-arm what was just taken back.

Two deliberate omissions:

* **The pages are not freed.** 4 KB apiece, and freeing one while a game thread
  is inside it is a crash. The code patches are gone by then, so nothing new
  can enter them.
* **The epoch locks are left as they are.** They *do* heal: the game re-runs
  the two-building check on every construction and caches the answer in the
  flag, so the next qualifying building restores whatever the client cleared.

None of it helps a client that is killed outright, which is what
`TechEffects.adopt()` and `BuildingGate`'s ask-the-node rule are for. Both let
the next client pick a game up mid-patch rather than finding a state it cannot
account for. Best-effort cleanup on the way out, recovery on the way back in.

### The engine writes `+0x06` too

It is not a static flag to take a copy of. The engine holds a building at 0
until you reach the epoch it belongs to, and sets it when you get there - so a
node found at 0 is the game's to manage, not ours.

That matters for how the gate releases a building, and it took two attempts.

Caching the value found at scan time and restoring it on unlock pins the
building shut for the whole match: `Unlock: Siege Factory` received in the
Copper Age caches a 0, and writing that back every poll keeps the factory
hidden long after the Dark Age makes it legal.

Recording which nodes the client closed, and reopening only those, is wrong in
a quieter way - it works until the client restarts, and then the record is
empty while the nodes are still shut, so an unlock arrives to no effect.

What works is asking the node. Below the current epoch the game would have the
flag set, so a 0 there is the client's doing and can be cleared; at or above it
the 0 is the game's and must be left alone. No state, and a client that
reconnects mid-match behaves the same as one that was there all along.

Nothing is lost by reopening. A released node is filtered by the same predicate
as everything else, so the epoch test at `+0x14` still hides it until its time.

### Picking the local player's nodes

Every player has a full copy of the tree - 778 nodes each in a 3-player match,
plus a static template at `0x0092FD98`. `node + 0x0C` is the owning
`EETechTree`, and `EpochAccess.tech_tree()` already resolves the local player's,
so filtering on it isolates exactly the human's 778 nodes.

### Name to node

The button's icon texture is the only handle. Fourteen of the nineteen buildings
match `but_<name>.sst` directly; the other five need aliases:

```
Archery Range     but_archery.sst          Navy Yard      but_naval yard.sst
Cyber Factory     but_mech factory.sst     Siege Factory  but_siege workshop.sst
Cyber Laboratory  but_mech laboratory.sst
```

`Granary` and `University` have **two** nodes each, so gating has to write every
node for a building rather than the first one found - University's second node
is an epoch 12 variant, and leaving it open would be a way round the lock.

An icon is not enough on its own to be sure a node is the right one. `Farm`
matched `but_farm_15t`, an epoch 14 variant, and there is **no node for the
ordinary Farm at any epoch below that** - so the item was bound to something
that never appears and the Farm was never gated at all. The client now checks
that at least one of a building's nodes unlocks in the epoch the database
expects (`node+0x14` runs exactly one below the database epoch, consistently
across every building) and drops the building when none does. That is what put
Farm out of the table altogether; of the nineteen that remain, 17 are gated -
Capitol and Town Center are the two that never can be.

### Which building produces which unit

`Recruit <family>` checks depend on this: a seed that hides `Unlock: Stable`
behind `Recruit Lancer` is unwinnable, the same shape of bug as
`Epoch: Bronze Age` on `Build Siege Factory`.

It is **not** in dbobjects.dat. Building records carry no train list and unit
records carry no producer; every apparent reference is a small integer colliding
with a building index, which is what a search for one finds.

It is in `technology_tree.pdf`, shipped with the game, whose second page lists
every unit in eleven tables headed by the category that produces it.
`tools/gen_producers.py` reads those tables and writes `Producers.py`.

Page 1 of that PDF is the flow chart, and it is a trap: its rows are per
producer but uneven and unmarked - no separator rules or row boxes exist in the
vector layer - so every rule for inferring a row boundary (last heading above,
midpoint between heading tops, midpoint between row centres) misfiled the units
nearest the edges. Spitfire came out of a Siege Factory and a Priest out of a
Town Center. The tables need no geometry at all.

One derived fact worth keeping: the `Siege` family floors at epoch 2 not because
the floor was polluted, but because `Sampson` is a genuine Barracks infantry
unit in that family. Its producers are `Barracks` **or** `Siege Factory`.

### A family is not always uniform

`Producers.py` answers per family, and that is one building too coarse.
`Domestic Wolf` - the Canine Scout - is filed under `Human` next to
`Inf01 - Clubman` and `Inf01 - Rock Thrower`, which really are Barracks units.
The Canine Scout comes from the **Capitol**, so the family's answer demanded
`Unlock: Barracks` for a check that is available before anything is built.

That is the safe direction - over-constraining can shorten nothing but the
fill's options, and can never make a seed unwinnable - which is exactly why it
sat there unnoticed. What it costs is reachability where there is least of it:
in a Prehistoric start with building unlocks on, **three** checks need no unlock
at all, and this is a fourth.

`UNIT_PRODUCER_OVERRIDES` in `Locations.py` carries the exceptions, and
`RECRUIT_LOCATION_PRODUCERS` resolves every recruit check to its producers once,
per unit, so no rule has to consult the family again.

### A Settlement produces nothing

`gen_producers.py` mapped the heading `Town Center / Capitol Units & Temple
Units` to **three** buildings, and the third was an assumption: the heading
names two, and `Settlement` was added by hand. A Settlement trains nothing. It
becomes a Town Center when five citizens garrison in it, and *that* trains
things - which `BUILDING_PREREQS` already models as `Town Center -> Settlement`.

It reached three families - `Citizen`, `Hero`, `Helicopter` - and changed no
logic in any of them, because all three also list the Capitol, which is never
locked and sits at epoch 0. So the union was wrong without being harmful: the
right answer was already in the tuple next to it.

That is the trap in a disjunction. `any(...)` over a producer list is satisfied
by its most permissive member, so a wrong entry beside a correct one is
invisible - it cannot make a check unreachable, and it cannot be caught by a
test that only asks whether generation succeeds. Corrected in the generator and
in `Producers.py` together, the two being identical here because the fix is one
name removed from one tuple.

### The test for this could never have caught it

`run_unlocks` in `tools/test_generation.py` exists to catch `Unlock: Stable`
landing on `Recruit Lancer` - a building unlock behind a check that needs that
building. Its docstring calls that "the subtle one". It was looking up

```python
UNIT_FAMILY_PRODUCERS.get(loc[len("Recruit "):], ())
```

which asks a table keyed by **family** for a unit **display name**. It matched
nothing, every time; `producers` was always empty, so the circularity branch
below it could never fire. The test passed by never testing.

Both sites now go through `RECRUIT_LOCATION_PRODUCERS`, keyed by the location,
which is the same thing the world's own rules use - so the simulation and the
rules can no longer disagree about what produces what.

**The lesson is about the shape, not this bug.** A lookup that silently returns
empty is indistinguishable from a lookup that found nothing wrong. Both read as
a pass.

Once fixed it does real work, and it passes: `17 unlocks, none circular` for a
full Prehistoric -> Space run, `12` for Copper -> Dark.

### `SystemExit` is not an `Exception`, and it ended the test run

`run_data_floors` is the one check that reads `data.ssa` instead of the world's
own tables, so it is written to skip where the game is not installed:

```python
except ImportError as e:
    return True, f"skipped: {e}"
```

It could never reach that. `ssa_extract` resolves the game's path **at import
time**, and `install.find_root()` raises `SystemExit` when there is none.
`SystemExit` derives from `BaseException`, not `Exception`, so `except
ImportError` let it past, the interpreter printed its "No Empire Earth install
found" message, and the process died mid-suite.

What that cost was invisible: the run simply stopped after the last `playable`
line. The `match settings` test, all eight goal/wonder cases and the final
`N/N passed` summary never ran, and the suite exited **1** on a machine whose
only sin was having no game installed. It looked like a full pass followed by a
note.

Now caught explicitly, and reported as **SKIP** rather than PASS - a run
without it has not checked the floors against anything, and PASS would claim it
had. With the skip in place the suite completes: **34/34**.

The same shape as the empty lookup above, and worth the same suspicion: a test
run that ends early looks a lot like a test run that finished.

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
