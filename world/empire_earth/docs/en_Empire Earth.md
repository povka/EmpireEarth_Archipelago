# Empire Earth

## Where is the options page?

The [player options page](../player-options) lets you configure your game and
export a YAML file.

## What does randomization do to this game?

Epoch advancement is taken out of your hands. Normally you advance by building
two recruitment or technology buildings and paying a resource cost; here that
building requirement is removed entirely and replaced by an Archipelago item.

Each `Epoch: <name>` item unlocks the ability to advance to that epoch. The
resource cost still applies, and epochs remain strictly sequential — an item for
a late epoch received early simply waits in the background until you have worked
your way up to it.

Resource bundles arrive as items and are credited to your stockpile
immediately, so other players can accelerate your economy.

## What is the goal?

Reach the epoch chosen by the `goal_epoch` option, anywhere from Stone Age to
Space Age. Only epochs up to your goal appear as items and checks, so a short
goal produces a genuinely short game rather than a long one with dead entries.

## Which items can be in another player's world?

- `Epoch: <name>` — one per epoch up to your goal
- `Food Bundle`, `Wood Bundle`, `Stone Bundle`, `Gold Bundle`, `Iron Bundle`

## What does another world's item look like in Empire Earth?

There is no in-world representation. Items are applied by the client the moment
they arrive, and announced in the on-screen overlay along with an Empire Earth
sound effect.

## What locations get shuffled?

Reaching each epoch is a check, plus a small number of starting checks.

## Notes and limitations

- Only the GOG **Art of Conquest** build is currently mapped. Other builds,
  including NeoEE, need their own address profile.
- Single-player skirmish is what this is designed and tested for. The client
  writes to the running game's memory, so it should not be used in multiplayer
  against other people.
- Your game files are never modified.
