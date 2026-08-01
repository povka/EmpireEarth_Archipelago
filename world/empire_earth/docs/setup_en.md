# Empire Earth Setup Guide

## Required Software

- Empire Earth: The Art of Conquest. The GOG **Empire Earth Gold** release is
  what this world is developed against.
- The Archipelago client component, installed with this apworld.

No patching is required. Nothing is copied into the game folder, and no game
files are modified — the client reads and writes the running game's memory, and
the on-screen overlay is a separate always-on-top window.

## Installing

1. Put `empire_earth.apworld` in your Archipelago `custom_worlds` folder.
2. Restart the Archipelago Launcher so it picks the world up.

## Configuring your YAML

```yaml
Empire Earth:
  # Epoch you must reach to win. Everything up to it becomes items and checks.
  goal_epoch: space_age

  # How much of a resource one bundle grants.
  bundle_size: 500

  # Play Empire Earth's building-select click when a message appears.
  message_sound: true
```

## Playing

1. Start the Archipelago Launcher and run **Empire Earth Client**, then connect
   it to the room.
2. Optionally run **Empire Earth Overlay** for on-screen notifications.
3. Start Empire Earth and begin a skirmish.

The client attaches to the game automatically once a match is running, and
reconnects on its own if you quit to the menu and start another match.

## How the randomizer plays

You begin unable to advance beyond your starting epoch. Advancing normally
requires two recruitment or technology buildings; that requirement is removed
and replaced by an Archipelago item.

- **`Epoch: <name>`** items unlock the ability to advance to that epoch. You
  still have to pay the resource cost in the Capitol, and epochs are still
  strictly sequential — receiving a late epoch early simply sits dormant until
  you have worked up to it.
- **Resource bundle** items grant food, wood, stone, gold or iron immediately.
- **Reaching each epoch** sends a check.

Reaching your goal epoch completes the game.

## Client commands

Type these in the client window:

| Command | Effect |
|---|---|
| `/ee` | Attachment status and your current resource stockpile |
| `/epochs` | Which epochs are unlocked, and your current epoch |
| `/grant <resource> <amount>` | Debug: add resources directly |

## Troubleshooting

**The client says it is waiting for Empire Earth.** It looks for `EE-AOC.exe`
or `Empire Earth.exe`. Make sure the game is actually running, and start the
client from the same Windows account.

**"No memory profile matches this build."** Your executable differs from the
one the addresses were taken from. Only the GOG Art of Conquest build is
currently mapped.

**The overlay does not appear.** It hides itself whenever the game is not on
screen, which includes while the game is minimised. Empire Earth minimises when
it loses focus, so alt-tabbing hides the overlay too — this is intentional.

**Nothing happens when items arrive.** Resources are only credited while you
are in a match; items received in a menu are applied as soon as one starts.
