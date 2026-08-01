from dataclasses import dataclass

from Options import Choice, DefaultOnToggle, PerGameCommonOptions, Range


class BundleSize(Range):
    """How much of a resource a single bundle item grants when received."""

    display_name = "Resource Bundle Size"
    range_start = 50
    range_end = 10000
    default = 500


class MessageSound(DefaultOnToggle):
    """
    Play a sound when the on-screen overlay shows an Archipelago message.

    Uses Empire Earth's own building-selection click, extracted from your
    installation. Turn this off if you find it distracting; messages still
    appear on screen either way.
    """

    display_name = "Overlay Message Sound"


class StartingEpoch(Choice):
    """
    The epoch your skirmish must start in.

    Set your skirmish's starting epoch to match this, or the client will warn
    you: starting later than the seed expects would skip checks that can then
    never be sent.
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


@dataclass
class EmpireEarthOptions(PerGameCommonOptions):
    starting_epoch: StartingEpoch
    goal_epoch: GoalEpoch
    bundle_size: BundleSize
    message_sound: MessageSound
