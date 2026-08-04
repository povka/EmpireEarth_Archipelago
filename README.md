# Empire Earth Archipelago

An Archipelago multiworld randomizer for **Empire Earth: The Art of Conquest** (PC, GOG "Empire Earth Gold").

> **Note:** Supports the **GOG and Steam** releases of Art of Conquest — the
> two ship the same binary, so both work identically.
> Designed and tested for single-player skirmish.

## ⚠️ Playing on Steam? Run the Archipelago client as administrator

The Steam release ships a `RUNASADMIN` compatibility layer for its own install
path, so **Empire Earth always launches elevated**. Windows will not let a
normal-privilege program read or write an elevated one, so an ordinary
Archipelago client cannot see the game at all: it sits on *"Waiting for Empire
Earth to start"*, or reports that the game could not be opened.

**Right-click the Archipelago Launcher and choose *Run as administrator*.**

Do this *before* starting the game, not after. Elevating while a match is
running makes Windows re-prompt, which minimises Empire Earth — and a
minimised full-screen match can be awkward to get back.

The **GOG release does not elevate**, so nothing special is needed there.

Nothing is patched and no game files are modified — verified by hash after a
session. The client reads and writes the running game's memory, and shows
Archipelago messages on the game's own message line.

That last part runs code *inside* the game: a page is allocated in the running
process, a short stub written into it, and the game's own message function
called. It lives and dies with the process, touches no file, and can be turned
off with `ingame_messages`.

## Current scope (v0.1.0)

- **Epoch advancement is the progression spine.** The normal requirement to
  advance (constructing two recruitment or technology buildings) is removed and
  replaced by an Archipelago item. Receiving `Epoch: Bronze Age` is what makes
  the Advance button appear in the Capitol.
- **Epochs stay sequential.** Resource costs are untouched, and an unlock for a
  later epoch received early simply waits in the background until you reach it.
- **167 checks from what you build and recruit** — 20 building types and every
  one of the 147 units. Units normally retire when a later tier replaces them,
  which would make those checks missable; the client switches that off, so a
  Rock Thrower stays recruitable for the whole match.
- **100 checks from technologies**, one per technology, at the Capitol, Temple,
  University, Hospital and Granary. Researching one sends the check but gives
  no benefit — the benefit is a `Tech:` item that comes back through the
  multiworld.
- **`Unlock: <building>` items**, optionally, holding 17 of the building types
  out of your build menus until you find them.
- **One check per epoch entered**, scoped to your starting and goal epochs.
- **A check per wonder built**, when wonders are enabled — up to 7 more.
- **Resource bundles** as items, credited to your stockpile the moment they
  arrive.
- **Configurable start and goal epoch**, from a short Stone Age sprint to a full
  Space Age run.
- **Choice of goal** — reach your goal epoch, win by wonders, or either.
- **The game cannot end your run early.** A skirmish needs an opponent, so
  wiping the AI out, being wiped out, or a wonder victory would all cut a run
  short. The client holds Empire Earth's own victory conditions off, leaving
  Archipelago as the only thing that finishes a seed.
- **The opponent cannot be removed, only handled.** The game refuses a
  one-player match and refuses to let everyone share a team, and an opponent
  cannot be killed, eliminated or switched off afterwards. It can be allied
  so it never fights you, at the cost of sharing vision - or simply left
  alone, since it can never end your run either way.
- **The skirmish setup is chosen in your YAML, not in the game.** The client
  writes map size, resources, difficulty, speed, unit limit and the rest onto
  the setup screen and puts them back if they are changed, so every player on a
  seed plays the same match. Cheat codes are always off.
- **Messages on the game's own message line** — the same display Empire Earth
    uses for its own announcements, prefixed `--AP--`.

## Setup

### Prerequisites

- **Empire Earth: The Art of Conquest** — the GOG
  [Empire Earth Gold](https://www.gog.com/game/empire_earth_gold_edition) release,
  or the Steam one. Developed and tested on **Windows**; see
  [Linux](#does-this-work-on-linux) if that is what you are on.
- **Archipelago 0.6.7 or newer** — [releases](https://github.com/ArchipelagoMW/Archipelago/releases).

### Install

1. Download `empire_earth.apworld` from this repository.
2. Drop it into Archipelago's `custom_worlds` folder — `C:\ProgramData\Archipelago\custom_worlds`
   on Windows, `~/Archipelago/custom_worlds` on Linux.
3. Restart the Archipelago Launcher so it picks the world up.
4. Copy `yaml/EmpireEarth.yaml` into your `Players` folder and edit it to taste.
5. Generate and host a multiworld as usual.
6. In the Launcher, open **Empire Earth Client** and connect it to the room.
7. Start Empire Earth and create a skirmish. Pick a map type and your
   civilisation; everything else on the setup screen is filled in for you.

The client attaches to the game on its own and reconnects if you quit to the
menu and start another match.

### Building it yourself

Only needed if you are changing the world. Requires **Python 3.10+** and
nothing else — no Archipelago source checkout, no build tools.

```bash
python tools/build_apworld.py
```

On Windows, use `py` if `python` is not on your PATH.

That validates the world and writes `empire_earth.apworld` to the repository
root. Copy it into your Archipelago `custom_worlds` folder yourself and restart
the Launcher.

```bash
python tools/build_apworld.py --check    # validate without building
```

The build deliberately does **not** install for you. Where `custom_worlds`
lives depends on your platform, install method and Archipelago version, and a
build that quietly writes the file somewhere nothing loads it is worse than one
that just hands it to you.

#### Does this work on Linux?

**Building, generating and hosting: yes.** The world is plain Python data, and
`__init__.py` imports the client lazily, so nothing platform-specific loads
during generation. A Linux machine can build the apworld and host a multiworld
without the game being anywhere near it.

**Playing: untested, and we would like to hear from you.** The client works by
reading and writing the running game's memory through Win32 calls, so it needs
those calls to exist. Under Wine or Proton the game *is* a Windows process, so
running the Archipelago client in the same prefix may well work — nobody has
tried it, so the honest answer is that we do not know. Native Linux Python has
no `ctypes.WinDLL`, so the client's `Memory` module will not load there.

If you get it running under Wine, please open an issue and say how.

#### What the build checks

Nothing is packaged until three checks pass, because a world that fails to
import does not announce itself — Archipelago simply never registers the
client, and the Launcher opens its own window instead.

1. every file compiles;
2. every `from .Module import name` names something that module actually
   defines;
3. the data modules import for real, with Archipelago's own modules stubbed.

The third is the one that earns its keep: it catches a data table changing
shape, such as adding a field to `TECHNOLOGIES` while another module still
unpacks the old arity.

What none of them catch is a name used inside a function but never imported —
that still only shows up at runtime.

## Options

| Option | Meaning |
|---|---|
| `goal` | `reach_epoch`, `wonder_victory`, or `either`. |
| `starting_epoch` | The epoch your skirmish starts in. |
| `goal_epoch` | The epoch that completes a `reach_epoch` goal. Everything up to it becomes items and checks, and it caps the match's end epoch. |
| `map_size` | `tiny` … `gigantic`. |
| `resources` | `tournament_low`, `tournament_defensive`, `standard_low`, `standard_high`, `deathmatch`. |
| `game_variant` | `standard` or `tournament`. |
| `difficulty` | `easy`, `medium`, `hard`. |
| `game_speed` | `slow`, `standard`, `fast`, `very_fast`. |
| `unit_limit` | 50–1200, rounded to the nearest 50 the game offers. |
| `wonders_for_victory` | Wonders needed to win, in game and in Archipelago alike. Must be 0 for `reach_epoch` and 1–6 otherwise. |
| `reveal_map`, `use_custom_civs`, `lock_teams`, `lock_speed` | The setup screen's checkboxes. |
| `prevent_match_end` | Hold the game's own win/loss conditions off so only Archipelago ends the run. |
| `opponents` | `hostile` (normal AI) or `allied` (never fights you, but shares vision). |
| `ingame_messages` | Show Archipelago messages on the game's own `--GAME--` message line. |
| `apply_ingame_win` | Completing the goal ends the match as a win in game. |
| `bundle_size` | How much of a resource one bundle grants. |

Everything from `starting_epoch` to `lock_speed` is enforced continuously while
the client runs. **Cheat codes are always disabled** and cannot be turned on.

**Map choice is deliberately left to you.** It is the one setting the client
never touches, so you are free to play custom maps that are not part of the
base game. Enforcing it would have made every seed vanilla-only for no real
benefit.

## How does this work?

- The client attaches to the running game and gates epoch advancement by
  writing to the tech tree. Locking clears the cached "requirement satisfied"
  flag, so the Advance button hides exactly as if you had not built the two
  buildings; unlocking sets it, so you do not need them at all.
- Building and unit checks come from reading the player's roster and resolving
  each object's type name, which matches the game's own object database.
- Unit checks are grouped by **family**, so "recruit any Human Archer" stays
  satisfiable as its members are replaced across epochs.
- Building checks avoid every type with per-epoch variants (Guard Towers, Walls,
  Gates), so no check can become unobtainable.
- **Every check carries the epoch that unlocks it**, read from the game's own
  object database. A Siege Factory needs the Dark Age, so its check requires
  those unlocks, and a seed that stops earlier does not offer it at all.
  Without this, generation could place `Epoch: Bronze Age` on a check that
  cannot be reached without it.
- Wonders have no variants and never expire, so each is a check — except that
  the Time Machine needs the Space Age, so it only appears in a seed whose goal
  epoch reaches it.
- A building joins the roster when its foundation is placed, so wonders are
  counted from a separate "finished" flag on the object. A wonder only sends its
  check, or counts towards the goal, once it is actually standing.
- Empire Earth ends the match the instant a wonder victory happens. Generation
  therefore refuses a seed where wonders can win the game but not the seed:
  `wonders_for_victory` above 0 requires a goal that includes wonders, and
  `reach_epoch` requires it to be 0.
- The skirmish setup screen's dropdowns and checkboxes are plain values at fixed
  addresses, so the client writes your YAML onto them and rewrites them on every
  poll. Changing one in game is undone within half a second.
- The match's end epoch is capped to your goal in the tech tree as well, so a
  saved or restored game cannot run past it.
- In-game messages go through the game's own `EEUserInterface::ShowGameMessage`.
  Its text lives in `Language.dll` as string-table resources loaded by numeric
  id, which is why searching the executable for `--GAME--` finds nothing — the
  ids have to be resolved first. Calling it means building two of the engine's
  own string objects and invoking it on a thread in the game, all from outside.
- Diplomatic stance is an array on each player object indexed by the other
  player's slot, so peace is written both ways: allying from your side alone
  would stop you attacking the AI without stopping it attacking you.
- `/ee`, `/roster`, `/wonders`, `/settings` and `/diplomacy` in the client show
  attachment status, what you own, wonder progress, the match settings being
  held in place, and who is at peace with whom.

## Known issues

- Empire Earth minimises whenever it loses focus.
- The game renders at your **primary** monitor's resolution. Moving the window
  to a larger second monitor upscales rather than re-rendering.

## Troubleshooting

- **"Waiting for Empire Earth to start"** — the client looks for `EE-AOC.exe`.
  Make sure the game is running and started from the same Windows account.
- **"Empire Earth is running but could not be opened"** — the game is running
  as administrator and Archipelago is not, so Windows refuses this client access
  to it. **The Steam release does this by default**: it ships a `RUNASADMIN`
  compatibility layer for its own install path, so the game always elevates and
  you get a UAC prompt when it launches. The GOG release does not.

  Either **run Archipelago as administrator** so the two match, or clear the
  setting on the game: right-click `EE-AOC.exe` -> Properties -> Compatibility,
  and untick *Run this program as an administrator*.
- **"No memory profile matches this build"** — your executable differs from the
  ones the addresses were taken from. GOG and Steam Art of Conquest are both
  mapped. **NeoEE is deliberately unsupported** (see below).
- **Nothing happens when items arrive** — resources are only credited while you
  are in a match. Items received in a menu are applied once one starts.

## Notes

- Progress is stored per seed and slot under Archipelago's `data/empire_earth`
  folder, so reconnecting does not re-apply items you already received.
- Because the client writes to the running game's memory, it should not be used
  in multiplayer against other people.

## Roadmap

- An address profile for the base game (Empire Earth without Art of Conquest).
  The Steam profile exists but the generated data (technologies, building
  epochs, producers) was taken from the GOG build and has not been re-checked
  against it.
- More check sources: quantity milestones, heroes, and the prophet calamities.
- Unit epochs still come from `dbobjects.dat`, which reads an epoch high. The
  buildings were corrected from the tech tree; the units could not be, because
  only 43 of 178 of them can be tied to a node.
- Colouring in-game messages by kind.

## NeoEE is not supported, and will not be

This works with the **GOG** and **Steam** releases only. NeoEE will not be
added.

Empire Earth is still sold, and both releases are cheap and frequently
discounted. Supporting builds that route around buying it takes work away from
the two that pay Stainless Steel Studios' successors for the game this is built
on — and this project already leans on the developers' own choices, right down
to shipping the binary with full RTTI and readable class names.

Buy it on [GOG](https://www.gog.com/game/empire_earth_gold_edition) or
[Steam](https://store.steampowered.com/app/254760/Empire_Earth_Gold_Edition/).

NeoEE is also a multiplayer-focused build with its own cheat detection, and
this client works by writing to the running game's memory. Pointing it at that
is a bad idea regardless of the licensing question.

## Credits

- **Stainless Steel Studios** and **Sierra** for Empire Earth, and for shipping
  it with full RTTI and mangled symbol names — recovering classes like
  `EETechTreeEpoch` and `EEUCBuilding` by name is what made this tractable
  without a debugger.
- The [Archipelago](https://github.com/ArchipelagoMW/Archipelago) project and
  its world API.
- **Mark Adler** for [`blast.c`](https://github.com/madler/zlib/tree/master/contrib/blast),
  ported to Python to decompress the PKWARE-imploded entries in `data.ssa`.
  Without it the object database behind the building, unit and wonder checks
  would have stayed unreadable.
- **GOG.com** for the DirectX 1-7 wrapper bundled with Empire Earth Gold. It
  runs the game borderless-windowed, which is what lets an ordinary
  always-on-top window composite over it — no hooking required.
- The [Empire Earth Fandom wiki](https://empireearth.fandom.com/wiki/Epoch),
  whose notes were vital to building a functional version.
- [`capstone`](https://www.capstone-engine.org/),
  [`pefile`](https://github.com/erocarrera/pefile) and
  [`numpy`](https://numpy.org/) for the reverse-engineering tooling. None of
  them are needed to run this world — it uses only the standard library and
  Archipelago's own modules.

`notes/REVERSE.md` documents the memory layouts, struct offsets and archive
formats this world depends on, including the approaches that were tried and did
not work.

## AI usage disclosure

AI assistance (Claude) was used while building this project. The memory layouts
and offsets it relies on are documented in `notes/REVERSE.md`.
