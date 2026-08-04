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

With the optional `building_unlocks` setting, eighteen of the building
types are taken out of your hands too. A building you have not found
the `Unlock: <name>` item for is simply absent from its build menu. The epoch
requirement still applies on top: finding `Unlock: Siege Factory` in the Copper
Age does not let you build one until the Dark Age. Capitol is never locked, since every match starts with
one and it is what makes citizens, and neither is the Farm, which has no
build-menu entry the client can hold shut.

Bear in mind that units are produced at buildings, so a locked Stable means no
cavalry until it opens. The seed accounts for this — a check for a unit is
never placed behind the only building that could produce it.

With `technology_checks` on (the default), researching a technology is a check
too — a hundred of them across the fourteen epochs, at the Capitol, Temple,
University, Hospital and Granary. Nothing about researching changes: the
buttons stay where the game puts them, cost the same, and give their usual
benefit. Only technologies up to your goal epoch are included.

## What is the goal?

Whichever the `goal` option asks for:

- **`reach_epoch`** — reach the epoch chosen by `goal_epoch`, anywhere from Stone
  Age to Space Age.
- **`wonder_victory`** — build the number of wonders set by
  `wonders_for_victory`.
- **`either`** — whichever of the two you manage first.

Only epochs up to `goal_epoch` appear as items and checks, so a short goal
produces a genuinely short game rather than a long one with dead entries.

Empire Earth ends the match the moment a wonder victory is achieved, so a seed
is refused if wonders can win the game without also winning the seed:
`wonders_for_victory` must be 0 for `reach_epoch` and 1 or more otherwise.

## Which items can be in another player's world?

- `Epoch: <name>` — one per epoch up to your goal
- `Unlock: <building>` — one per building, with `building_unlocks` on
- `Tech: <name>` — one per technology, carrying its benefit
- `Food Bundle`, `Wood Bundle`, `Stone Bundle`, `Gold Bundle`, `Iron Bundle`

## What does another world's item look like in Empire Earth?

There is no in-world representation. Items are applied by the client the moment
they arrive, and announced on Empire Earth's own message line, prefixed
`--AP--`.

## What locations get shuffled?

Reaching each epoch up to your goal is a check, as is constructing each of 20
building types, recruiting each of the 147 units for the first time, and
researching each of 100 technologies.

Units would normally be missable: Empire Earth stops offering one once a later
tier replaces it, so a Rock Thrower you never got round to building in the
Copper Age could never be recruited again. The client switches that retirement
off for the whole match, so every unit stays available and no check can expire.

With wonders enabled, each of the seven wonders is a check too. Six are
available from the Stone Age; the Time Machine needs the Space Age, so it is
only included in a seed whose goal epoch reaches it.

## Notes and limitations

- The skirmish setup — map size, resources, difficulty, speed, unit limit and
  the rest — is chosen in your YAML, and the client holds the setup screen at
  those values while it runs. Cheat codes are always disabled. Map type is the
  only setting left to the player.
- Only the GOG **Art of Conquest** build is currently mapped. Other builds,
  including NeoEE, need their own address profile.
- Single-player skirmish is what this is designed and tested for. The client
  writes to the running game's memory, so it should not be used in multiplayer
  against other people.
- Your game files are never modified.
