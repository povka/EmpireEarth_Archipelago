from BaseClasses import ItemClassification, Region, Tutorial
from Options import OptionError
from worlds.AutoWorld import WebWorld, World
from worlds.LauncherComponents import Component, Type, components, launch_subprocess

from .Items import (
    ITEM_NAME_TO_ID,
    ITEM_TABLE,
    RESOURCE_ITEM_NAMES,
    EmpireEarthItem,
)
from .Locations import ALWAYS_LOCATIONS, LOCATION_NAME_TO_ID, EmpireEarthLocation
from .Options import EmpireEarthOptions


def launch_client(*args):
    from .Client import launch

    launch_subprocess(launch, name="EmpireEarthClient", args=args)


# Only the client is exposed. It starts the overlay itself, and the window
# manager stays a standalone script for anyone who wants it.
components.append(
    Component(
        "Empire Earth Client",
        func=launch_client,
        component_type=Type.CLIENT,
        description="Connect Empire Earth / Art of Conquest to a multiworld.",
    )
)


class EmpireEarthWeb(WebWorld):
    theme = "grass"
    tutorials = [
        Tutorial(
            "Multiworld Setup Guide",
            "A guide to setting up Empire Earth for Archipelago.",
            "English",
            "setup_en.md",
            "setup/en",
            ["you"],
        )
    ]


class EmpireEarthWorld(World):
    """
    Empire Earth is a 2001 real-time strategy game spanning 500,000 years of
    human history across fourteen epochs.
    """

    game = "Empire Earth"
    web = EmpireEarthWeb()

    options_dataclass = EmpireEarthOptions
    options: EmpireEarthOptions

    item_name_to_id = ITEM_NAME_TO_ID
    location_name_to_id = LOCATION_NAME_TO_ID

    origin_region_name = "Empire"

    @property
    def goal_epoch(self) -> int:
        return int(self.options.goal_epoch.value)

    @property
    def starting_epoch(self) -> int:
        return int(self.options.starting_epoch.value)

    def generate_early(self) -> None:
        from .Epochs import EPOCH_NAMES

        if self.starting_epoch >= self.goal_epoch:
            raise OptionError(
                f"Empire Earth: starting_epoch "
                f"({EPOCH_NAMES[self.starting_epoch]}) must come before "
                f"goal_epoch ({EPOCH_NAMES[self.goal_epoch]})."
            )

    def included_epochs(self) -> range:
        """Epochs that become items and checks.

        The epoch you start in is excluded: you are already there, so it is
        neither an unlock you need nor a check you could send.
        """
        return range(self.starting_epoch + 1, self.goal_epoch + 1)

    def create_regions(self) -> None:
        from .Epochs import EPOCH_NAMES

        # Building and unit-family checks are always present; epoch checks stop
        # at the goal.
        wanted = set(ALWAYS_LOCATIONS)
        wanted |= {f"Reach {EPOCH_NAMES[i]}" for i in self.included_epochs()}

        empire = Region("Empire", self.player, self.multiworld)
        for name, loc_id in LOCATION_NAME_TO_ID.items():
            if name not in wanted:
                continue
            empire.locations.append(
                EmpireEarthLocation(self.player, name, loc_id, empire)
            )
        self.multiworld.regions.append(empire)

    def create_item(self, name: str) -> EmpireEarthItem:
        classification = ITEM_TABLE[name][1]
        return EmpireEarthItem(name, classification, ITEM_NAME_TO_ID[name], self.player)

    def create_items(self) -> None:
        from .Epochs import EPOCH_NAMES

        pool = [
            self.create_item(f"Epoch: {EPOCH_NAMES[i]}")
            for i in self.included_epochs()
        ]
        # There are far more checks than epoch unlocks, so the rest of the
        # pool is resource bundles, dealt round-robin for an even spread.
        remaining = len(self.multiworld.get_unfilled_locations(self.player)) - len(pool)
        for n in range(max(0, remaining)):
            pool.append(
                self.create_item(RESOURCE_ITEM_NAMES[n % len(RESOURCE_ITEM_NAMES)])
            )
        self.multiworld.itempool += pool

    def get_filler_item_name(self) -> str:
        return self.random.choice(RESOURCE_ITEM_NAMES)

    def set_rules(self) -> None:
        from worlds.generic.Rules import set_rule

        from .Epochs import EPOCH_NAMES

        # Epochs are strictly sequential in game, so reaching epoch N needs
        # every unlock up to N, not just N itself.
        for i in self.included_epochs():
            # Only epochs after the starting one exist as items, so the
            # requirement chain must start there too.
            needed = [
                f"Epoch: {EPOCH_NAMES[j]}"
                for j in range(self.starting_epoch + 1, i + 1)
            ]
            set_rule(
                self.multiworld.get_location(f"Reach {EPOCH_NAMES[i]}", self.player),
                lambda state, n=needed: state.has_all(n, self.player),
            )

        goal_item = f"Epoch: {EPOCH_NAMES[self.goal_epoch]}"
        self.multiworld.completion_condition[self.player] = (
            lambda state: state.has(goal_item, self.player)
        )

    def fill_slot_data(self) -> dict:
        return {
            "starting_epoch": self.starting_epoch,
            "goal_epoch": self.goal_epoch,
            "bundle_size": self.options.bundle_size.value,
            "message_sound": bool(self.options.message_sound.value),
        }
