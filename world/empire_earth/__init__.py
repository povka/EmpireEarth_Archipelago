from BaseClasses import ItemClassification, Region, Tutorial
from Options import OptionError
from worlds.AutoWorld import WebWorld, World
from worlds.LauncherComponents import Component, Type, components, launch_subprocess

from .Items import (
    BUILDING_PREREQS,
    TECH_ITEMS,
    ITEM_NAME_TO_ID,
    ITEM_TABLE,
    LOCKABLE_BUILDINGS,
    RESOURCE_ITEM_NAMES,
    EmpireEarthItem,
)
from .Locations import (
    ALWAYS_LOCATIONS,
    RECRUIT_LOCATION_FAMILY,
    LOCATION_MIN_EPOCH,
    LOCATION_NAME_TO_ID,
    TECH_LOCATION_BUILDING,
    TECH_LOCATIONS,
    WONDER_MIN_EPOCH,
    EmpireEarthLocation,
)
from .Options import EmpireEarthOptions


def launch_client(*args):
    from .Client import launch

    launch_subprocess(launch, name="EmpireEarthClient", args=args)


# Only the client is exposed. The window manager stays a standalone script
# for anyone who wants it.
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
            ["asapaska"],
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

    @property
    def wonders_needed(self) -> int:
        return int(self.options.wonders_for_victory.value)

    @property
    def wants_wonders(self) -> bool:
        """True when a wonder victory is one of the ways to finish."""
        return self.options.goal.value in (
            self.options.goal.option_wonder_victory,
            self.options.goal.option_either,
        )

    @property
    def gates_buildings(self) -> bool:
        return bool(self.options.building_unlocks.value)

    def unlock_items(self) -> list[str]:
        """`Unlock:` items this seed uses.

        A building whose epoch is past the goal can never be built, so an
        unlock for it would be an item that does nothing.
        """
        if not self.gates_buildings:
            return []
        return [
            f"Unlock: {b}" for b in LOCKABLE_BUILDINGS
            if LOCATION_MIN_EPOCH.get(f"Build {b}", 0) <= self.goal_epoch
        ]

    def researchable(self, epoch: int) -> bool:
        """Is this epoch's technology part of the seed?

        Everything up to the goal is, including the epochs below the one you
        start in. Those are researched for you as the match loads - a Copper
        Age start begins with seven already done - so their checks send
        themselves immediately. That is deliberate: it opens a run with a
        handful of checks rather than the two a match otherwise starts with,
        and the benefits still have to come back as items, because the client
        withholds them the same way it withholds the ones you research.
        """
        return epoch <= self.goal_epoch

    def tech_items(self) -> list[str]:
        """`Tech:` items this seed uses.

        One per technology check, so the pool balances: researching sends the
        check, and the benefit comes back as an item.
        """
        if not self.options.technology_checks.value:
            return []
        return [
            name for name in TECH_ITEMS
            if self.researchable(LOCATION_MIN_EPOCH.get(
                f"Research {name[len('Tech: '):]}", 0))
        ]

    def buildings_needed_for(self, name: str) -> list[tuple[str, list[str]]]:
        """Ways to satisfy `name`'s building requirement, as a disjunction.

        Each option is an unlock item paired with the epoch items needed to
        build that building. Both halves are required: holding
        `Unlock: Siege Factory` is no use in the Copper Age, because a siege
        factory cannot be built until the Dark Age.

        Leaving the epoch half out is enough to make a seed unwinnable. The
        Siege family can be recruited at a Barracks or a Siege Factory, so a
        run that started holding `Unlock: Siege Factory` looked able to recruit
        siege units immediately, and generation was free to put the epoch
        unlocks that reach the Dark Age behind that check.
        """
        if not self.gates_buildings:
            return []

        def option(building: str) -> tuple[str, list[str]]:
            floor = LOCATION_MIN_EPOCH.get(f"Build {building}", 0)
            return f"Unlock: {building}", self.epoch_items_up_to(floor)

        if name.startswith("Build "):
            building = name[len("Build "):]
            if building in LOCKABLE_BUILDINGS:
                # The epoch half is already required by the location's own floor.
                return [(f"Unlock: {building}", [])]
            # Something reached through another building - a Town Center is
            # five citizens garrisoned in a Settlement - needs whatever gates
            # the building it comes from.
            prereq = BUILDING_PREREQS.get(building)
            if prereq in LOCKABLE_BUILDINGS:
                return [option(prereq)]
            return []              # Capitol, Farm, and the wonders
        if name.startswith("Recruit "):
            family = RECRUIT_LOCATION_FAMILY.get(name)
            if family is None:
                return []
            from .Producers import UNIT_FAMILY_PRODUCERS

            producers = UNIT_FAMILY_PRODUCERS.get(family, ())
            if any(b not in LOCKABLE_BUILDINGS for b in producers):
                return []
            return [option(b) for b in producers]
        if name.startswith("Research "):
            # A technology is offered by exactly one building, so this is a
            # single requirement rather than a choice. Capitol technologies
            # need nothing: a Capitol is never locked.
            building = TECH_LOCATION_BUILDING.get(name)
            if building not in LOCKABLE_BUILDINGS:
                return []
            return [option(building)]
        return []

    @property
    def wants_epoch(self) -> bool:
        return self.options.goal.value in (
            self.options.goal.option_reach_epoch,
            self.options.goal.option_either,
        )

    def wonder_locations(self) -> list[str]:
        """Wonders this seed can actually build, earliest-available first.

        A wonder cannot be built before its own epoch and the client caps the
        match at the goal epoch, so anything above the goal is left out rather
        than shipped as a check nobody can send.
        """
        if not self.wants_wonders:
            return []
        usable = [
            (epoch, name)
            for name, epoch in WONDER_MIN_EPOCH.items()
            if epoch <= self.goal_epoch
        ]
        return [name for _epoch, name in sorted(usable)]

    def generate_early(self) -> None:
        from .Epochs import EPOCH_NAMES

        if self.starting_epoch >= self.goal_epoch:
            raise OptionError(
                f"Empire Earth: starting_epoch "
                f"({EPOCH_NAMES[self.starting_epoch]}) must come before "
                f"goal_epoch ({EPOCH_NAMES[self.goal_epoch]})."
            )

        # The game ends the match on a wonder victory. Allowing one that the
        # goal does not recognise would let the match finish with the seed
        # unfinishable, so the two options have to agree.
        if self.wants_wonders and self.wonders_needed < 1:
            raise OptionError(
                "Empire Earth: goal "
                f"'{self.options.goal.current_key}' needs wonders_for_victory "
                "to be at least 1."
            )
        if not self.wants_wonders and self.wonders_needed > 0:
            raise OptionError(
                "Empire Earth: wonders_for_victory is "
                f"{self.wonders_needed}, which lets the game end in a wonder "
                "victory, but goal is 'reach_epoch'. Set wonders_for_victory "
                "to 0, or pick the 'wonder_victory' or 'either' goal."
            )

        available = len(self.wonder_locations())
        if self.wants_wonders and self.wonders_needed > available:
            raise OptionError(
                f"Empire Earth: wonders_for_victory is {self.wonders_needed} "
                f"but only {available} wonder(s) can be built by "
                f"{EPOCH_NAMES[self.goal_epoch]}."
            )

    def included_epochs(self) -> range:
        """Epochs that become items and checks.

        The epoch you start in is excluded: you are already there, so it is
        neither an unlock you need nor a check you could send.
        """
        return range(self.starting_epoch + 1, self.goal_epoch + 1)

    def create_regions(self) -> None:
        from .Epochs import EPOCH_NAMES

        # A check is only in the seed if this run can actually reach the epoch
        # that unlocks it - there is no point offering "Build Cyber Factory" in
        # a game that stops at the Dark Age.
        wanted = self.included_object_locations()
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
        pool += [self.create_item(name) for name in self.unlock_items()]
        pool += [self.create_item(name) for name in self.tech_items()]
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

    def epoch_items_up_to(self, epoch: int) -> list[str]:
        """The unlocks needed to be in `epoch`.

        Epochs are strictly sequential in game, so being in epoch N needs every
        unlock up to N, not just N itself. Only epochs after the starting one
        exist as items, so the chain starts there.
        """
        from .Epochs import EPOCH_NAMES

        return [
            f"Epoch: {EPOCH_NAMES[j]}"
            for j in range(self.starting_epoch + 1, epoch + 1)
        ]

    def included_object_locations(self) -> set[str]:
        """Build/recruit/wonder/research checks this seed can actually reach."""
        wanted = {
            name for name in ALWAYS_LOCATIONS
            if LOCATION_MIN_EPOCH.get(name, 0) <= self.goal_epoch
        }
        if self.options.technology_checks.value:
            wanted |= {
                name for name in TECH_LOCATIONS
                if self.researchable(LOCATION_MIN_EPOCH.get(name, 0))
            }
        return wanted | set(self.wonder_locations())

    def set_rules(self) -> None:
        from worlds.generic.Rules import set_rule

        from .Epochs import EPOCH_NAMES

        wanted = self.included_object_locations()

        for i in self.included_epochs():
            needed = self.epoch_items_up_to(i)
            set_rule(
                self.multiworld.get_location(f"Reach {EPOCH_NAMES[i]}", self.player),
                lambda state, n=needed: state.has_all(n, self.player),
            )

        # Everything you build or recruit has an epoch floor, and a check for
        # something out of reach must require the unlocks that reach it.
        # Skipping this let generation place `Epoch: Bronze Age` on
        # `Build Siege Factory`, which cannot be built without it.
        for name in sorted(wanted):
            floor = LOCATION_MIN_EPOCH.get(name, 0)
            needed = ([] if floor <= self.starting_epoch
                      else self.epoch_items_up_to(floor))
            # The two requirements are independent and both apply: an unlock
            # does not skip the epoch (the game checks that separately, in the
            # same predicate) and reaching the epoch does not skip the unlock.
            unlocks = self.buildings_needed_for(name)
            if not needed and not unlocks:
                continue        # available from the moment the match starts
            set_rule(
                self.multiworld.get_location(name, self.player),
                lambda state, n=needed, u=unlocks: (
                    state.has_all(n, self.player)
                    and (not u or any(
                        state.has(item, self.player)
                        and state.has_all(eps, self.player)
                        for item, eps in u
                    ))
                ),
            )

        conditions = []
        if self.wants_epoch:
            goal_item = f"Epoch: {EPOCH_NAMES[self.goal_epoch]}"
            conditions.append(
                lambda state, item=goal_item: state.has(item, self.player)
            )
        if self.wants_wonders:
            # Building N wonders needs whichever epoch the Nth-earliest of them
            # becomes available in - nothing else gates them.
            usable = self.wonder_locations()
            deepest = max(
                WONDER_MIN_EPOCH[n] for n in usable[: self.wonders_needed]
            )
            needed = self.epoch_items_up_to(deepest)
            conditions.append(
                lambda state, n=needed: state.has_all(n, self.player)
            )

        self.multiworld.completion_condition[self.player] = (
            lambda state: any(c(state) for c in conditions)
        )

    def match_settings(self) -> dict:
        """The skirmish setup the client must force. Cheat codes are always
        off: leaving them available would undermine the whole seed."""
        o = self.options
        from .MatchSettings import clamp_unit_limit

        return {
            "map_size": o.map_size.value,
            "resources": o.resources.value,
            "game_variant": o.game_variant.value,
            "difficulty": o.difficulty.value,
            "game_speed": o.game_speed.value,
            "unit_limit": clamp_unit_limit(o.unit_limit.value),
            "wonders": o.wonders_for_victory.value,
            "starting_epoch": self.starting_epoch,
            "ending_epoch": self.goal_epoch,
            "reveal_map": int(bool(o.reveal_map.value)),
            "use_custom_civs": int(bool(o.use_custom_civs.value)),
            "lock_teams": int(bool(o.lock_teams.value)),
            "lock_speed": int(bool(o.lock_speed.value)),
            "cheat_codes": 0,
            # 0 stops the game ending the match by itself; leaving it at 1 hands
            # that back to Empire Earth's own win and loss conditions.
            "victory_allowed": 0 if o.prevent_match_end.value else 1,
        }

    def fill_slot_data(self) -> dict:
        return {
            "starting_epoch": self.starting_epoch,
            "goal_epoch": self.goal_epoch,
            "goal": self.options.goal.current_key,
            "opponents": self.options.opponents.current_key,
            "ingame_messages": bool(self.options.ingame_messages.value),
            "apply_ingame_win": bool(self.options.apply_ingame_win.value),
            # Kept so an older client still understands this seed.
            "force_peace": self.options.opponents.value
            == self.options.opponents.option_allied,
            "building_unlocks": self.gates_buildings,
            "technology_checks": bool(self.options.technology_checks.value),
            "wonders_needed": self.wonders_needed if self.wants_wonders else 0,
            "match_settings": self.match_settings(),
            "bundle_size": self.options.bundle_size.value,
        }
