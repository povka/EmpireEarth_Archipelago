# Empire Earth Archipelago

Play **Empire Earth: The Art of Conquest** in an [Archipelago](https://archipelago.gg) multiworld.

Advancing an epoch stops being something you do and becomes something you find. Building, recruiting and researching send checks. Everything else arrives from the seed.

---

## What gets shuffled

- **Epochs** — `Epoch: <name>` items replace the usual two-building requirement. Order and resource costs are unchanged.
- **Buildings and units** — 22 building types and 248 unit types can send checks.
- **Technologies** — all 100. Researching sends the check; the effect comes back as a `Tech:` item.
- **Building unlocks** — with `building_unlocks` on, 18 buildings and all 9 wonders leave your build menu until their `Building:` or `Wonder:` item arrives.
- **Resources** — food, wood, stone, gold and iron bundles land in your stockpile on receipt.

No check can expire. Units that would normally be withdrawn stay recruitable, and where a later tier replaces an earlier one the replacement carries the earlier check too — a Simple Bowman sends Slinger's, a Long Bow sends every archer below it. That's deliberate — a per-unit check you can miss by advancing an epoch is a check that can strand the run.

Building a wonder sends nothing. The `Wonder:` item is the reward and raising the wonder is what you do with it.

---

## Requirements

- **Empire Earth: The Art of Conquest** — from [GOG](https://www.gog.com/game/empire_earth_gold_edition) or [Steam](https://store.steampowered.com/app/254760/Empire_Earth_Gold_Edition/)
- **Archipelago 0.6.7 or newer** — [releases](https://github.com/ArchipelagoMW/Archipelago/releases)
- **Windows** — to play. Building, generating and hosting work anywhere; Wine and Proton are untested.

Nothing is patched. The client reads and writes the running game's memory.

---

## Install and play

1. Download `empire_earth.apworld` from Releases.
2. Drop it in Archipelago's `custom_worlds` — `C:\ProgramData\Archipelago\custom_worlds` on Windows, `~/Archipelago/custom_worlds` on Linux.
3. Restart the Launcher.
4. Copy [`yaml/EmpireEarth.yaml`](yaml/EmpireEarth.yaml) into `Players` and set your slot name and options.
5. Generate and host as normal.
6. Open **Empire Earth Client** from the Launcher and connect.
7. Start a single-player skirmish. You pick the map and civilisation; the client applies the rest from your YAML.

The client finds the game on its own and reconnects when you return to the menu or start another match.

**Warning:** don't run the client in multiplayer against other people. It writes to the game process.

### Steam: run the Launcher as administrator

The Steam build starts elevated, and Windows won't let a normal process inspect an elevated one. The client will sit there waiting for a game that's already running.

Start the **Archipelago Launcher as administrator before Empire Earth**. GOG doesn't need this.

---

## Options

Full commented template: [`yaml/EmpireEarth.yaml`](yaml/EmpireEarth.yaml).

- **`goal`** — `reach_epoch`, `wonder_victory`, or `either`
- **`starting_epoch`** — where the skirmish begins
- **`goal_epoch`** — the highest epoch in the seed, and the target for an epoch goal
- **`building_unlocks`** — put building and wonder permissions in the item pool
- **`technology_checks`** — turn research into checks and effects into items
- **`wonders_for_victory`** — `0` for `reach_epoch`, otherwise how many wonders finish the run
- **`map_terrain`** — `land_only`, `land_and_water`, or `space`
- **`opponents`** — `hostile` for a normal AI, `allied` for one that won't attack
- **`prevent_match_end`** — stop Empire Earth ending the match by its own win and loss rules
- **`ingame_messages`** — show received items on the game's message line
- **`apply_ingame_win`** — end the match as a victory once Archipelago is complete
- **`bundle_size`** — how much of a resource one bundle is worth

`map_size`, `resources`, `game_variant`, `difficulty`, `game_speed`, `unit_limit`, `reveal_map`, `use_custom_civs`, `lock_teams` and `lock_speed` map straight onto skirmish setup.

### Telling the seed what map you'll play

`map_terrain` is the one thing the seed can't work out for itself. The client forces map *size* but never map choice, so you have to say.

Terrain decides part of your build menu. A land-only map has no Dock. A space map *replaces* the Dock with a Space Dock rather than adding one, and does the same to the Navy Yard and the Pharos Lighthouse. Checks the terrain rules out are left out of the seed entirely.

Nothing enforces it. Start a match that matches what you picked, or you'll be holding checks nobody can send.

---

## How the logic stays valid

Every check carries the epoch it needs and, where one applies, the building that produces it. `Build Siege Factory` isn't reachable until you've reached the Dark Age *and* received its unlock. Units inherit the same treatment through their producer, technologies through the building that researches them.

That's what stops the generator hiding `Epoch: Bronze Age` behind a check that needs the Bronze Age. Anything past your goal epoch is left out rather than shipped as a check you can't send.

A few checks are real but not guaranteed — a unit only one civilisation fields, a building nobody has confirmed in a build menu. Those stay in the seed and are marked so the fill never puts anything load-bearing on them.

Wonders count only once construction finishes. The match's end epoch is capped at your goal epoch, so a loaded save can't skip past the seed.

---

## Troubleshooting

**"Waiting for Empire Earth to start."** — `EE-AOC.exe` needs to be running under the same Windows account. On Steam, elevate the Launcher.

**The game is running and the client can't open it.** — privilege mismatch. Elevate the Launcher, or turn off the executable's administrator compatibility setting.

**"No memory profile matches this build."** — the executable isn't a supported GOG or Steam Art of Conquest build.

---

## Building the apworld

Only if you're changing the world. Python 3.10 or newer:

```bash
python tools/build_apworld.py
```

Use `py` on Windows if `python` isn't on your `PATH`. The build validates, then writes `empire_earth.apworld` to the repo root — you copy it to `custom_worlds` yourself. Where Archipelago keeps that folder differs by platform and install method, and a build that writes an apworld somewhere nothing loads it is worse than one that hands you the file.

`--check` validates without building. Six checks run before anything is packaged: every file compiles, every relative import names something real, the data modules import for real, no two ids collide, nothing needs a Python newer than 3.11, and no name is read that nothing binds.

### Renaming things

Checks are named after the game's database, which is not always what the game
calls something on screen. Two tables fix that, and neither can break a check —
detection matches on the database name and ids are assigned in database order,
so nothing looks at the display name.

- **`UNIT_DISPLAY_OVERRIDES`** in `Locations.py` — renames a unit. `Domestic
  Wolf` reads `Canine Scout` because that's what the game calls it.
- **`DISPLAY_OVERRIDES`** in `tools/gen_objects.py` — renames a building or
  wonder, and needs a regenerate to take effect. `Lighthouse at Alexandria` is
  the Pharos Lighthouse.

Add a line to either if a name annoys you.

For the memory layouts, offsets and the approaches that didn't work, see [`notes/REVERSE.md`](notes/REVERSE.md).

---

## What it won't do

- **Run on the base game or NeoEE.** GOG and Steam Art of Conquest only. Buy the game.
- **Work in multiplayer against people.** It writes to the game process.
- **Verify your map choice.** `map_terrain` is you telling the seed what you'll play, and nothing checks you meant it.
- **Guarantee every unit epoch.** Building epochs come from the running game's tech tree. Some unit epochs still come from `dbobjects.dat`, which is all over the place, pretty much none of it matches what it should and i still don't fully understand how it resolves the data in-game but i coded around everything i could find WeirdChamp
- **Colour its in-game messages.** Still on the list.

---

## Credits

- **Stainless Steel Studios** and **Sierra** for Empire Earth.
- [**Archipelago**](https://github.com/ArchipelagoMW/Archipelago) for the multiworld framework and world API.
- **Mark Adler** for [`blast.c`](https://github.com/madler/zlib/tree/master/contrib/blast), ported here to read PKWARE-imploded `data.ssa` entries.
- **GOG.com** for the DirectX 1–7 wrapper Empire Earth Gold ships with.
- The [**Empire Earth Fandom wiki**](https://empireearth.fandom.com/wiki), which settled several unit lines the game's own data couldn't.
- [**capstone**](https://www.capstone-engine.org/), [**pefile**](https://github.com/erocarrera/pefile) and [**numpy**](https://numpy.org/) for the reverse-engineering tools. Not needed to run the world.

---

## AI disclosure

Claude was used as an assistance tool during development. The memory layouts, offsets and supporting research are in [`notes/REVERSE.md`](notes/REVERSE.md).
