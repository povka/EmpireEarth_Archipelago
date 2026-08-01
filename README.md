# Empire Earth Archipelago

An Archipelago multiworld randomizer for **Empire Earth: The Art of Conquest** (PC, GOG "Empire Earth Gold").

> **Note:** Only the GOG Art of Conquest build is currently supported. Other
> builds, including the base game and NeoEE, need their own address profile.
> Designed and tested for single-player skirmish.

Nothing is patched and no game files are modified. The client reads and writes
the running game's memory, and notifications are drawn by a separate
always-on-top window rather than by the game itself.

## Current scope (v0.1.0)

- **Epoch advancement is the progression spine.** The normal requirement to
  advance (constructing two recruitment or technology buildings) is removed and
  replaced by an Archipelago item. Receiving `Epoch: Bronze Age` is what makes
  the Advance button appear in the Capitol.
- **Epochs stay sequential.** Resource costs are untouched, and an unlock for a
  later epoch received early simply waits in the background until you reach it.
- **47 checks from what you build and recruit** — 20 building types and 27 unit
  families, curated so none of them can expire when you change epoch.
- **One check per epoch entered**, scoped to your starting and goal epochs.
- **Resource bundles** as items, credited to your stockpile the moment they
  arrive.
- **Configurable start and goal epoch**, from a short Stone Age sprint to a full
  Space Age run.
- **On-screen overlay** with an Empire Earth sound effect, started automatically
  by the client.

## Setup

### Prerequisites

- **Empire Earth: The Art of Conquest** — the GOG
  [Empire Earth Gold](https://www.gog.com/game/empire_earth_gold_edition) release.
- **Archipelago 0.6.7 or newer** — [releases](https://github.com/ArchipelagoMW/Archipelago/releases).

### Install

1. Download `empire_earth.apworld` from this repository.
2. Drop it into Archipelago's `custom_worlds` folder
   (`C:\ProgramData\Archipelago\custom_worlds` by default).
3. Restart the Archipelago Launcher so it picks the world up.
4. Copy `yaml/EmpireEarth.yaml` into your `Players` folder and edit it to taste.
5. Generate and host a multiworld as usual.
6. In the Launcher, open **Empire Earth Client** and connect it to the room.
7. Start Empire Earth and begin a skirmish, **starting in the epoch your YAML
   asks for**.

The client attaches to the game on its own and reconnects if you quit to the
menu and start another match.

## Options

| Option | Meaning |
|---|---|
| `starting_epoch` | The epoch your skirmish must start in. Create the skirmish to match. |
| `goal_epoch` | The epoch you must reach to win. Everything up to it becomes items and checks. |
| `bundle_size` | How much of a resource one bundle grants. |
| `message_sound` | Play Empire Earth's building-select click when a message appears. |

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
- Your skirmish settings are validated on entering a match. A wrong starting
  epoch is reported, and the match's end epoch is capped to your goal.
- The overlay is a separate click-through window that tails a feed file the
  client writes. It hides itself whenever the game is not on screen.
- `/ee`, `/roster` and `/epochs` in the client show attachment status, what you
  own, and epoch state.

## Known issues

- Empire Earth minimises whenever it loses focus, which also hides the overlay.
  `world/empire_earth/WindowManager.py` can pin the game to one monitor and stop
  it minimising, if that bothers you.
- The game renders at your **primary** monitor's resolution. Moving the window
  to a larger second monitor upscales rather than re-rendering.

## Troubleshooting

- **"Waiting for Empire Earth to start"** — the client looks for `EE-AOC.exe`.
  Make sure the game is running and started from the same Windows account.
- **"No memory profile matches this build"** — your executable differs from the
  one the addresses were taken from. Only GOG Art of Conquest is mapped.
- **Nothing happens when items arrive** — resources are only credited while you
  are in a match. Items received in a menu are applied once one starts.
- **The overlay never appears** — it hides when the game is not on screen,
  including while minimised. Run it with `--always` to test without the game.

## Notes

- Progress is stored per seed and slot under Archipelago's `data/empire_earth`
  folder, so reconnecting does not re-apply items you already received.
- The message sound is extracted from your own installation on first run.
  No game assets are distributed with this world.
- Because the client writes to the running game's memory, it should not be used
  in multiplayer against other people.

## Roadmap

- Address profiles for the base game and NeoEE builds.
- More check sources: technologies, wonders, and campaign scenarios.
- In-game notifications rather than an external overlay, if a usable
  single-player display path can be found.

## Credits

- **Stainless Steel Studios** and **Sierra** for Empire Earth, and for shipping
  it with full RTTI and mangled symbol names — recovering classes like
  `EETechTreeEpoch` and `EEUCBuilding` by name is what made this tractable
  without a debugger.
- The [Archipelago](https://github.com/ArchipelagoMW/Archipelago) project and
  its world API.
- **Mark Adler** for [`blast.c`](https://github.com/madler/zlib/tree/master/contrib/blast),
  ported to Python here to decompress the PKWARE-imploded entries in
  `data.ssa`. Without it the sound effects and the object database would have
  stayed unreadable.
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
