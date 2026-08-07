# Empire Earth Archipelago

Play **Empire Earth: The Art of Conquest** as part of an [Archipelago](https://archipelago.gg) multiworld.

Advance through the epochs, build your empire, recruit units, and research technology to send checks. The things that let you progress — epoch advances and, optionally, building unlocks — can arrive from any player in the seed.

This project supports single-player skirmish in the GOG and Steam releases of **Empire Earth Gold**. It is an early release, but intended to be playable.

## What is shuffled?

- **Epochs.** Advancing is controlled by `Epoch: <name>` items instead of the usual two-building requirement. Epochs still have to be reached in order and still cost their normal in-game resources.
- **Buildings and units.** Building 22 building types and recruiting any of the 247 unit types can send checks. No check disappears as you advance: units that would simply expire stay recruitable, and where a later tier replaces an earlier one, recruiting the replacement sends the earlier unit's check too — a Simple Bowman sends Slinger's, a Long Bow sends every archer below it.
- **Technologies.** Each of the 100 technologies can be a check. Researching sends the check; its effect returns as a `Tech:` item through Archipelago.
- **Building unlocks.** With `building_unlocks` enabled, 20 buildings and every wonder are removed from the build menu until their `Building: <building>` or `Wonder: <name>` item arrives.
- **Wonders.** Wonders are gated by `Wonder: <name>` items, under the same `building_unlocks` option as buildings. Building one sends no check — finding the item is the reward, and raising the wonder is what you do with it.
- **Resources.** Food, wood, stone, gold, and iron bundles are credited to your stockpile when received.

You choose a starting epoch, a goal epoch, and whether the goal is reaching that epoch, building wonders, or either one.

You also declare what kind of map you intend to play, with `map_terrain`. Empire Earth decides part of your build menu from the terrain — a land-only map has no Dock, and a space map replaces the Dock with a Space Dock rather than adding one — and the client never picks your map, so the seed has to be told. Checks the terrain rules out are left out. Nothing enforces it, so start a match that matches what you chose.

## Requirements

- Empire Earth: The Art of Conquest, included with [Empire Earth Gold on GOG](https://www.gog.com/game/empire_earth_gold_edition) or [Steam](https://store.steampowered.com/app/254760/Empire_Earth_Gold_Edition/)
- [Archipelago 0.6.7 or newer](https://github.com/ArchipelagoMW/Archipelago/releases)
- Windows for playing. Building, generating, and hosting work on other platforms; Wine/Proton play is untested.

No game files are patched or replaced. The client reads and writes the running game's memory to enforce item locks and report checks.

## Install and play

1. Download `empire_earth.apworld` from Releases.
2. Put it in Archipelago's `custom_worlds` folder, default:
   - Windows: `C:\ProgramData\Archipelago\custom_worlds`
   - Linux: `~/Archipelago/custom_worlds`
3. Restart the Archipelago Launcher.
4. Copy [`yaml/EmpireEarth.yaml`](yaml/EmpireEarth.yaml) to your Archipelago `Players` folder and set your slot name and options.
5. Generate and host the multiworld normally.
6. Open **Empire Earth Client** from the Archipelago Launcher and connect to the room.
7. Start a single-player skirmish. Choose your map type and civilisation; the client applies the remaining match settings from your YAML.

The client detects the game automatically and reconnects after returning to the menu or starting another match.

### Steam: run the Launcher as administrator

The Steam release starts Empire Earth elevated by default. Windows does not allow a normal process to inspect an elevated one, so the client will wait forever for the game or report that it cannot open it.

Run the **Archipelago Launcher as administrator before starting Empire Earth**. The GOG release normally does not need this.

## Important game behaviour

- The client can hold Empire Earth's own victory and defeat screens off. This prevents an AI defeat or an in-game wonder victory from ending an Archipelago run early. `prevent_match_end` controls this.
- A skirmish still needs an opponent. Use `allied` opponents for a peaceful game; they share vision, but will not attack.
- Match settings from the YAML are enforced while the client runs. Map choice and civilisation are intentionally left to the player.
- Cheat codes are always disabled.
- Archipelago messages can be shown on Empire Earth's message line with `ingame_messages`.

## Options

The complete commented template is [`yaml/EmpireEarth.yaml`](yaml/EmpireEarth.yaml). The important options are:

| Option | Description |
|---|---|
| `goal` | `reach_epoch`, `wonder_victory`, or `either`. |
| `starting_epoch` | Epoch at the start of the skirmish. |
| `goal_epoch` | Highest epoch available in the seed and the target for an epoch goal. |
| `building_unlocks` | Put building permissions in the item pool. |
| `technology_checks` | Turn research into checks and technology effects into items. |
| `wonders_for_victory` | Wonders needed for a wonder goal. Use `0` for `reach_epoch`; use `1`–`6` for a wonder or either goal. |
| `map_terrain` | `land_only`, `land_and_water`, or `space` — the kind of map you will play. The seed only offers checks that map can build, so start a match that matches. |
| `opponents` | `hostile` for a normal AI or `allied` for a non-hostile opponent. |
| `prevent_match_end` | Prevent Empire Earth from ending the match through its own win/loss rules. |
| `ingame_messages` | Display received items and AP status messages in game. |
| `apply_ingame_win` | End the match as a victory after Archipelago completion. |
| `bundle_size` | Amount of each resource in one bundle. |

`map_size`, `resources`, `game_variant`, `difficulty`, `game_speed`, `unit_limit`, `reveal_map`, `use_custom_civs`, `lock_teams`, and `lock_speed` map directly to skirmish setup settings.

## How the logic stays valid

Every check is tagged with the epoch and, where applicable, producer building it needs. For example, a Siege Factory check cannot be considered reachable until the player has both reached the Dark Age and received its building unlock. The same applies to units and technologies that depend on a particular producer.

That matters in a multiworld: the generator cannot hide `Epoch: Bronze Age` behind a location that itself cannot be reached until Bronze Age. Checks beyond the selected goal epoch are omitted entirely.

Wonders are counted only after construction completes. The game’s end epoch is also capped at the goal epoch, so a loaded save cannot bypass the seed’s progression.

## Troubleshooting

**The client says “Waiting for Empire Earth to start.”**  Make sure `EE-AOC.exe` is running under the same Windows account. On Steam, run the Archipelago Launcher as administrator.

**The game is running, but the client cannot open it.**  The game and the Launcher have different privilege levels. Elevate the Launcher, or disable the executable’s administrator compatibility setting.

**“No memory profile matches this build.”**  The executable does not match a supported GOG or Steam Art of Conquest build. NeoEE is not supported.

**Items are not doing anything.**  Resource and progression items are applied once a skirmish is active. Items received while at the menu wait until the next match.

**The game minimises.**  Empire Earth minimises when it loses focus. It also renders at the primary monitor’s resolution; moving it to a larger secondary monitor scales the image instead of changing its render resolution.

## Building the apworld

Only needed if you are changing the world. Install Python 3.10 or newer, then run:

```bash
python tools/build_apworld.py
```

On Windows, use `py` if `python` is not on your `PATH`.

The command validates the world and writes `empire_earth.apworld` to the repository root. Copy it to `custom_worlds` yourself and restart the Launcher.

```bash
python tools/build_apworld.py --check
```

Use `--check` to validate without producing an apworld. The build checks Python syntax, internal imports, and the structure of the generated data tables.

For the game-memory work, object data, and discarded approaches behind the project, see [`notes/REVERSE.md`](notes/REVERSE.md).

## Current limitations and roadmap

- GOG and Steam Art of Conquest are supported. The base game and NeoEE are not.
- Do not use the client in multiplayer games against other people. It writes to the running game process.
- Potential future check sources include quantity milestones, heroes, and prophet calamities.
- Building epochs have been verified against the tech tree. Some unit epochs still come from `dbobjects.dat` and need further validation.
- In-game message colours are still a future improvement.

## Credits

- **Stainless Steel Studios** and **Sierra** for Empire Earth.
- [Archipelago](https://github.com/ArchipelagoMW/Archipelago) for the multiworld framework and world API.
- **Mark Adler** for [`blast.c`](https://github.com/madler/zlib/tree/master/contrib/blast), ported here to read PKWARE-imploded `data.ssa` entries.
- **GOG.com** for the DirectX 1–7 wrapper used by Empire Earth Gold.
- The [Empire Earth Fandom wiki](https://empireearth.fandom.com/wiki) for useful reference material.
- [capstone](https://www.capstone-engine.org/), [pefile](https://github.com/erocarrera/pefile), and [numpy](https://numpy.org/) for reverse-engineering tools used during development. They are not required to run the world.

## AI disclosure

Claude was used as an assistance tool during development. The memory layouts, offsets, and supporting research are documented in [`notes/REVERSE.md`](notes/REVERSE.md).
