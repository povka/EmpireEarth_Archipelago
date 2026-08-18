from dataclasses import dataclass

from Options import (
    Choice,
    DefaultOnToggle,
    PerGameCommonOptions,
    Range,
    Toggle,
)


class BundleSize(Range):
    """How much of a resource a single bundle item grants when received."""

    display_name = "Resource Bundle Size"
    range_start = 50
    range_end = 10000
    default = 3500


class InGameMessages(DefaultOnToggle):
    """
    Show Archipelago messages on Empire Earth's own message line.

    The same one-line display the game uses for things like "Player 'Babylon'
    is victorious!", prefixed with `--AP--`.

    This is the only place Archipelago messages appear, so turning it off means
    you will only see them in the client window.

    This is the one feature that runs code inside the game rather than only
    reading and writing its memory. No game file is touched: a page is
    allocated in the running process and disappears with it. Turn it off if you
    would rather nothing was injected.
    """

    display_name = "In-Game Messages"


class Opponents(Choice):
    """
    What the client does about the computer players.

    Empire Earth won't start a skirmish without an opponent, won't let everyone
    share a team, and won't let you remove one afterwards — they can't be
    killed, eliminated, starved or switched off. So the only choice is how they
    behave.

    `hostile` leaves the game alone. The AI plays normally and can hurt you, but
    it can't end your run, because `prevent_match_end` holds the victory
    conditions off separately. The worst it manages is costing you buildings.

    `allied` holds both sides at allied about half a second into the match, so
    it never fights you. The catch is that allies share line of sight, so its
    exploration uncovers your map. Pick it if you'd rather not be attacked than
    keep the fog.
    """

    display_name = "Opponents"
    option_allied = 0
    option_hostile = 1
    default = 1


class MapTerrain(Choice):
    """
    What kind of map you intend to play. The seed builds its logic around it.

    Empire Earth decides some of your build menu from the terrain, and this is
    the one thing a seed cannot see for itself — map choice is left to you, so
    you have to tell it. Pick the wrong one and checks in the seed may be
    impossible to send, which can strand a run.

    `land_and_water` is the ordinary case. Docks and Naval Yards exist, and so
    does everything they build — frigates, transports, battleships, galleys,
    submarines and carriers.

    `land_only` is a map with no water at all. There is no Dock and no Navy
    Yard, so no ship of any kind is buildable, and none of them appears in the
    seed.

    `space` is a Planets map. It substitutes rather than adds: a Space Dock
    stands where the Dock would be, a Space Turret where the Naval Yard would,
    and an Orbital Space Station where the Pharos Lighthouse would. The ships
    are gone and the Space Dock's own craft take their place.

    Start a match that matches what you picked. Nothing enforces it, because
    the client does not choose your map — it only believes you.
    """

    display_name = "Map Terrain"
    option_land_only = 0
    option_land_and_water = 1
    option_space = 2
    default = 1


class PreventMatchEnd(DefaultOnToggle):
    """
    Stop Empire Earth from ending the match on its own.

    A skirmish needs at least one opponent, so a run can be cut short three ways
    that have nothing to do with your goal: you wipe the AI out, the AI wipes
    you out, or a wonder victory fires. With this on, the client holds the
    game's "Victory Allowed" option off, so only Archipelago decides when you
    are done. The wonder goal still works — the client counts wonders itself.

    Turn it off if you would rather play with the game's own win and loss
    conditions live. Your seed survives a match ending either way: checks are
    already on the server, so you lose the match, not the run.
    """

    display_name = "Prevent Match End"


class TechnologyChecks(DefaultOnToggle):
    """
    Make researching a technology a check.

    Adds one check per technology — a hundred of them across the full fourteen
    epochs, at the Capitol, Temple, University, Hospital and Granary. Nothing
    about researching changes: the buttons stay exactly where the game puts
    them, cost the same, and give their usual benefit.

    Only technologies up to your goal epoch are included, so a short seed gains
    a handful rather than a hundred.
    """

    display_name = "Technology Checks"


class BuildingUnlocks(DefaultOnToggle):
    """
    Put most building types behind Archipelago items.

    With this on, a building you have not found the unlock for is missing from
    its build menu, and `Building: <name>` items are added to the pool. The
    epoch requirement is unaffected: finding `Building: Siege Factory` in the
    Copper Age does not let you build one until the Dark Age, because the game
    checks the epoch separately.

    This changes the shape of a run considerably — units are produced at
    buildings, so a locked Stable means no cavalry — and it adds eighteen
    progression items, so seeds take longer to finish.

    Capitol is never locked: every match starts with one, and it is what makes
    citizens. The Farm is not locked either — it has no build-menu entry the
    client can hold shut.

    Wonders have their own option. Turning this off and leaving `wonder_unlocks`
    on leaves `Epoch:` and `Wonder:` as the only progression items in the seed,
    because a `Building:` item is the only other thing any rule asks for.
    """

    display_name = "Building Unlocks"


class WonderUnlocks(DefaultOnToggle):
    """
    Put wonders behind Archipelago items.

    A wonder you have not found the `Wonder: <name>` item for is missing from
    your build menu, exactly as a locked building is. This was part of
    `building_unlocks` and is its own option because the two do different jobs:
    a locked building shapes the whole run, while a locked wonder is the reward
    for finding it.

    Under a wonder goal that matters more, because the wonder *is* the goal —
    the item is what you were looking for and raising it is what you do with it,
    rather than the same wonder paying out twice.

    Building a wonder never sends a check either way.
    """

    display_name = "Wonder Unlocks"


class Goal(Choice):
    """
    What completes the seed.

    `reach_epoch` requires wonders_for_victory to be 0, and `wonder_victory`
    requires it to be 1 or more. That pairing is deliberate — Empire Earth ends
    the match the moment a wonder victory is achieved, so a seed that allows one
    without Archipelago recognising it could be cut short with the goal
    unreachable.
    """

    display_name = "Goal"
    option_reach_epoch = 0
    option_wonder_victory = 1
    default = 1


class StartingEpoch(Choice):
    """
    The epoch your skirmish starts in.

    The client sets this on the setup screen for you, and puts it back if you
    change it: starting later than the seed expects would skip checks that can
    then never be sent.
    """

    display_name = "Starting Epoch"
    option_prehistoric_age = 0
    option_stone_age = 1
    option_copper_age = 2
    option_bronze_age = 3
    option_dark_age = 4
    option_middle_ages = 5
    option_renaissance = 6
    option_imperial_age = 7
    option_industrial_age = 8
    option_atomic_age_ww1 = 9
    option_atomic_age_ww2 = 10
    option_atomic_age_modern = 11
    option_digital_age = 12
    option_nano_age = 13
    default = 0


class GoalEpoch(Choice):
    """
    The epoch you must reach to win.

    Every epoch up to and including this one becomes an unlock item and a
    check; anything beyond it is left out of the pool entirely. Pick an early
    epoch for a short game or Space Age for a full run.
    """

    display_name = "Goal Epoch"
    option_stone_age = 1
    option_copper_age = 2
    option_bronze_age = 3
    option_dark_age = 4
    option_middle_ages = 5
    option_renaissance = 6
    option_imperial_age = 7
    option_industrial_age = 8
    option_atomic_age_ww1 = 9
    option_atomic_age_ww2 = 10
    option_atomic_age_modern = 11
    option_digital_age = 12
    option_nano_age = 13
    option_space_age = 14
    default = 14


class MapSize(Choice):
    """Map size. The client forces this on the skirmish setup screen."""

    display_name = "Map Size"
    option_tiny = 0
    option_small = 1
    option_medium = 2
    option_large = 3
    option_huge = 4
    option_gigantic = 5
    default = 5


class ResourceLevel(Choice):
    """Starting resources and gather rates, as on the setup screen."""

    display_name = "Resources"
    option_tournament_low = 0
    option_tournament_defensive = 1
    option_standard_low = 2
    option_standard_high = 3
    option_deathmatch = 4
    default = 3


class GameVariant(Choice):
    """Standard or Tournament rules."""

    display_name = "Game Variant"
    option_tournament = 1
    option_standard = 2
    default = 2


class Difficulty(Choice):
    """Computer player difficulty."""

    display_name = "Difficulty Level"
    option_easy = 0
    option_medium = 1
    option_hard = 2
    default = 0


class GameSpeed(Choice):
    """Simulation speed."""

    display_name = "Game Speed"
    option_slow = 0
    option_standard = 1
    option_fast = 2
    option_very_fast = 3
    default = 3


class UnitLimit(Range):
    """
    Population limit, rounded to the nearest 50 the game offers.
    """

    display_name = "Game Unit Limit"
    range_start = 50
    range_end = 1200
    default = 1200


class WondersToWin(Range):
    """
    Wonders needed for a wonder victory. 0 turns wonder victory off.

    This is the game's own victory condition and the Archipelago one at the
    same time, so it has to agree with `goal` — 0 for `reach_epoch`, 1 or more
    for `wonder_victory`.

    Building a wonder sends no check. The count is what finishes the seed, and
    wonders count when construction finishes rather than when the foundation
    goes down.
    """

    display_name = "Wonders For Victory"
    range_start = 0
    range_end = 6
    # Not 0, because the default goal is `wonder_victory` and that refuses a 0.
    # One wonder is the shortest honest version of the goal; raise it for a
    # longer run.
    default = 6


class RevealMap(Toggle):
    """Reveal the whole map at the start."""

    display_name = "Reveal Map"


class UseCustomCivs(Toggle):
    """Allow custom civilizations."""

    display_name = "Use Custom Civs"


class LockTeams(Toggle):
    """Lock teams for the whole match."""

    display_name = "Lock Teams"


class LockSpeed(Toggle):
    """Lock the game speed for the whole match."""

    display_name = "Lock Speed"


@dataclass
class EmpireEarthOptions(PerGameCommonOptions):
    goal: Goal
    starting_epoch: StartingEpoch
    goal_epoch: GoalEpoch
    building_unlocks: BuildingUnlocks
    wonder_unlocks: WonderUnlocks
    technology_checks: TechnologyChecks
    map_size: MapSize
    resources: ResourceLevel
    game_variant: GameVariant
    difficulty: Difficulty
    game_speed: GameSpeed
    unit_limit: UnitLimit
    wonders_for_victory: WondersToWin
    reveal_map: RevealMap
    use_custom_civs: UseCustomCivs
    lock_teams: LockTeams
    lock_speed: LockSpeed
    prevent_match_end: PreventMatchEnd
    opponents: Opponents
    map_terrain: MapTerrain
    ingame_messages: InGameMessages
    bundle_size: BundleSize
