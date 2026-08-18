from BaseClasses import LocationProgressType, Region, Tutorial
from Options import OptionError
from worlds.AutoWorld import WebWorld, World
from worlds.LauncherComponents import Component, Type, components, launch_subprocess

from .Items import (
    BUILDING_PREREQS,
    TECH_ITEMS,
    building_item,
    wonder_item,
    ITEM_NAME_TO_ID,
    ITEM_TABLE,
    LOCKABLE_BUILDINGS,
    RESOURCE_ITEM_NAMES,
    EmpireEarthItem,
)
from .Locations import (
    ALWAYS_LOCATIONS,
    RECRUIT_LOCATION_PRODUCERS,
    building_terrains,
    wonder_terrains,
    NO_PROGRESSION_LOCATIONS,
    PRIORITY_LOCATIONS,
    LOCATION_MIN_EPOCH,
    LOCATION_NAME_TO_ID,
    EXCLUDED_TECHNOLOGIES,
    TECH_LOCATION_BUILDING,
    TECH_LOCATIONS,
    WONDER_MIN_EPOCH,
    EmpireEarthLocation,
)
from .TechUnlocks import TECH_REQUIRES
from .Options import EmpireEarthOptions


def launch_client(*args):
    from .Client import launch

    launch_subprocess(launch, name="EmpireEarthClient", args=args)


# Registering this at import time is what puts the client in the Launcher.
# `launch_client` imports `.Client` inside the function, not at module level —
# that's deliberate, because Client pulls in Memory, which calls
# `ctypes.WinDLL` as it loads. At module level it would raise on Linux, and
# Archipelago imports every world at startup, so the world would be unusable
# for generating and hosting too.
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
        return (self.options.goal.value
                == self.options.goal.option_wonder_victory)

    @property
    def terrain(self) -> str:
        """The map the player says they will play; see Options.MapTerrain.

        Nothing verifies it. The client forces map size but never map choice,
        so this is the seed taking your word. Everything terrain decides is
        filtered through it, so a wrong answer shows up as checks that can't be
        sent rather than as anything subtler.
        """
        return self.options.map_terrain.current_key

    def on_this_map(self, name: str) -> bool:
        """Is this check's building — or its unit's producer — on this map?"""
        if name.startswith("Build "):
            return self.terrain in building_terrains(name[len("Build "):])
        if name.startswith("Recruit "):
            producers = RECRUIT_LOCATION_PRODUCERS.get(name, ())
            # No producer recorded means nothing terrain-specific is known,
            # so the check stands. A unit with producers needs one of them
            # available here.
            return not producers or any(
                self.terrain in building_terrains(b) for b in producers)
        return True

    @property
    def gates_buildings(self) -> bool:
        return bool(self.options.building_unlocks.value)

    @property
    def gates_wonders(self) -> bool:
        """Its own option, because the two do different jobs.

        A `Building:` item is what every building, unit and technology rule
        asks for, so gating buildings is what makes those items progression.
        A `Wonder:` item gates only the wonder itself. Turning buildings off
        and leaving wonders on is what gets a seed down to `Epoch:` and
        `Wonder:` as the only progression there is.
        """
        return bool(self.options.wonder_unlocks.value)

    def unlock_items(self) -> list[str]:
        """`Building:` and `Wonder:` items this seed uses.

        Anything whose epoch is past the goal can never be built, so an unlock
        for it is an item that does nothing.

        Buildings and wonders have an option each. Wonders aren't checks —
        building one sends nothing, so the item is the whole reward.
        """
        out = []
        if self.gates_buildings:
            out += [
                building_item(b) for b in LOCKABLE_BUILDINGS
                if LOCATION_MIN_EPOCH.get(f"Build {b}", 0) <= self.goal_epoch
            ]
        if self.gates_wonders:
            out += [wonder_item(w) for w in self.usable_wonders()]
        return out

    def researchable(self, epoch: int) -> bool:
        """Is this epoch's technology part of the seed?

        Everything up to the goal, including epochs below the one you start
        in. Those are researched for you as the match loads — a Copper Age
        start begins with seven already done — so their checks send themselves
        immediately. That's deliberate: it opens a run with a handful of checks
        instead of the two a match otherwise starts with, and the benefits
        still come back as items, because the client withholds them exactly as
        it withholds the ones you research.
        """
        return epoch <= self.goal_epoch

    def tech_items(self) -> list[str]:
        """`Tech:` items this seed uses.

        One per technology check, so the pool balances. Researching sends the
        check; the benefit comes back as an item.
        """
        if not self.options.technology_checks.value:
            return []
        return [
            name for name in TECH_ITEMS
            if self.researchable(LOCATION_MIN_EPOCH.get(
                f"Research {name[len('Tech: '):]}", 0))
            # One item per technology check, so a technology the seed doesn't
            # offer must not leave its item behind — the pool would stop
            # balancing against the locations.
            and name[len("Tech: "):] not in EXCLUDED_TECHNOLOGIES
        ]

    def buildings_needed_for(self, name: str) -> list[tuple[str, list[str]]]:
        """Ways to satisfy `name`'s building requirement, as a disjunction.

        Each option is an unlock item paired with the epoch items needed to
        build that building. Both halves are required — holding
        `Building: Siege Factory` is no use in the Copper Age, because you
        can't build one until the Dark Age.

        Dropping the epoch half is enough to make a seed unwinnable. Siege
        units come from a Barracks or a Siege Factory, so a run starting with
        `Building: Siege Factory` looked able to recruit them immediately, and
        generation put the epochs that reach the Dark Age behind that check.
        """
        if not self.gates_buildings:
            return []

        def option(building: str) -> tuple[str, list[str]]:
            floor = LOCATION_MIN_EPOCH.get(f"Build {building}", 0)
            return building_item(building), self.epoch_items_up_to(floor)

        if name.startswith("Build "):
            building = name[len("Build "):]
            if building in LOCKABLE_BUILDINGS:
                # The epoch half is already required by the location's own floor.
                return [(building_item(building), [])]
            # Something reached through another building — a Town Center is
            # five citizens garrisoned in a Settlement — needs whatever gates
            # the building it comes from.
            prereq = BUILDING_PREREQS.get(building)
            if prereq in LOCKABLE_BUILDINGS:
                return [option(prereq)]
            return []              # Capitol, Farm, and the wonders
        if name.startswith("Recruit "):
            # Per unit, not per family. A family can hold units trained at
            # different buildings, and one unlockable producer among them must
            # not be demanded of a unit that doesn't use it.
            producers = RECRUIT_LOCATION_PRODUCERS.get(name, ())
            if not producers:
                return []
            # One never-locked producer is enough to make the unit reachable
            # with no unlock at all.
            if any(b not in LOCKABLE_BUILDINGS for b in producers):
                return []
            return [option(b) for b in producers]
        if name.startswith("Research "):
            # Exactly one building offers a technology, so this is a single
            # requirement rather than a choice. Capitol technologies need
            # nothing — a Capitol is never locked.
            building = TECH_LOCATION_BUILDING.get(name)
            if building not in LOCKABLE_BUILDINGS:
                return []
            return [option(building)]
        return []

    @property
    def wants_epoch(self) -> bool:
        return (self.options.goal.value
                == self.options.goal.option_reach_epoch)

    def usable_wonders(self) -> list[str]:
        """Wonders this seed can actually build, earliest-available first.

        A wonder can't be built before its own epoch and the client caps the
        match at the goal epoch, so anything above the goal is left out. No
        point offering an unlock for something nobody can raise.

        Unlike buildings this doesn't depend on the goal. A wonder is buildable
        in any seed, and gating one is worth doing whether or not the run ends
        by building them.
        """
        usable = [
            (epoch, name)
            for name, epoch in WONDER_MIN_EPOCH.items()
            if epoch <= self.goal_epoch
            and self.terrain in wonder_terrains(name)
        ]
        return [name for _epoch, name in sorted(usable)]

    def wonder_options(self) -> list[tuple[int, list[str]]]:
        """Wonders this seed can *guarantee*, as (epoch, unlocks needed).

        Substituted wonders need no special case, because `map_terrain` already
        said which of a pair this match has — a space map offers the Orbital
        Space Station and not the Pharos Lighthouse, and neither is counted on
        a map that can't raise it.

        This is what the goal counts and what `generate_early` measures
        `wonders_for_victory` against, so the two can't disagree. They did once,
        and the seed generated with a goal nothing could satisfy.
        """
        out: list[tuple[int, list[str]]] = []
        for name in self.usable_wonders():
            epoch = WONDER_MIN_EPOCH[name]
            unlocks = [wonder_item(name)] if self.gates_wonders else []
            out.append((epoch, unlocks))
        return out

    def generate_early(self) -> None:
        from .Epochs import EPOCH_NAMES

        if self.starting_epoch >= self.goal_epoch:
            raise OptionError(
                f"Empire Earth: starting_epoch "
                f"({EPOCH_NAMES[self.starting_epoch]}) must come before "
                f"goal_epoch ({EPOCH_NAMES[self.goal_epoch]})."
            )

        # The game ends the match on a wonder victory. Allowing one the goal
        # doesn't recognise lets the match finish with the seed unfinished, so
        # the two options have to agree.
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
                "to 0, or pick the 'wonder_victory' goal."
            )

        available = len(self.wonder_options())
        if self.wants_wonders and self.wonders_needed > available:
            raise OptionError(
                f"Empire Earth: wonders_for_victory is {self.wonders_needed} "
                f"but only {available} wonder(s) can be built by "
                f"{EPOCH_NAMES[self.goal_epoch]}."
            )

        # The next epoch goes in an early sphere, which in practice means one of
        # the four opening checks.
        #
        # Those four are the whole of sphere 1 — a match starts with a Capitol
        # and the units it makes, and everything else needs an epoch or an
        # unlock first. `PRIORITY` alone deadlocked the fill: the priority pass
        # sweeps with every progression item in hand, so all four looked
        # reachable, it locked four items that opened nothing, and the 43
        # remaining progression items had nowhere to go.
        #
        # `distribute_early_items` runs before the priority pass and prefers
        # priority locations, so this puts the one item that opens the seed
        # where it has to be and the other three fill normally.
        self.multiworld.early_items[self.player][
            f"Epoch: {EPOCH_NAMES[self.starting_epoch + 1]}"] = 1

    def included_epochs(self) -> range:
        """Epochs that become items and checks.

        The epoch you start in is excluded — you're already there, so it's
        neither an unlock you need nor a check you could send.
        """
        return range(self.starting_epoch + 1, self.goal_epoch + 1)

    def create_regions(self) -> None:
        from .Epochs import EPOCH_NAMES

        # A check is only in the seed if this run can actually reach the epoch
        # that unlocks it - aka space age check can't be earlier
        wanted = self.included_object_locations()
        wanted |= {f"Reach {EPOCH_NAMES[i]}" for i in self.included_epochs()}

        empire = Region("Empire", self.player, self.multiworld)
        for name, loc_id in LOCATION_NAME_TO_ID.items():
            if name not in wanted:
                continue
            location = EmpireEarthLocation(self.player, name, loc_id, empire)
            # Some checks are real but not guaranteed: a unit only one
            # civilisation fields, or a building nobody has yet seen in a build
            # menu. Nothing the seed needs may rest on those.
            if name in NO_PROGRESSION_LOCATIONS:
                location.progress_type = LocationProgressType.EXCLUDED
            elif name in PRIORITY_LOCATIONS:
                location.progress_type = LocationProgressType.PRIORITY
            empire.locations.append(location)
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
        # Far more checks than epoch unlocks, so the rest of the pool is
        # resource bundles, dealt round-robin for an even spread.
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

        Epochs are strictly sequential in game, so being in epoch N needs
        every unlock up to N, not just N itself. Only epochs after the starting
        one exist as items, so the chain starts there.
        """
        from .Epochs import EPOCH_NAMES

        return [
            f"Epoch: {EPOCH_NAMES[j]}"
            for j in range(self.starting_epoch + 1, epoch + 1)
        ]

    def included_object_locations(self) -> set[str]:
        """Build, recruit and research checks this seed can actually reach."""
        wanted = {
            name for name in ALWAYS_LOCATIONS
            if LOCATION_MIN_EPOCH.get(name, 0) <= self.goal_epoch
            and self.on_this_map(name)
        }
        if self.options.technology_checks.value:
            techs = {
                name for name in TECH_LOCATIONS
                if self.researchable(LOCATION_MIN_EPOCH.get(name, 0))
                and name[len("Research "):] not in EXCLUDED_TECHNOLOGIES
            }
            # A chained technology has no button until its predecessor's effect
            # is applied, so one whose predecessor this seed never offers can
            # never be researched. Dropped rather than shipped as a check
            # nobody can send. Repeated because dropping one can orphan the
            # next; EXCLUDED_TECHNOLOGIES is empty today, so this settles on
            # the first pass.
            while True:
                gone = {
                    name for name in techs
                    if (earlier := TECH_REQUIRES.get(name[len("Research "):]))
                    and f"Research {earlier}" not in techs
                }
                if not gone:
                    break
                techs -= gone
            wanted |= techs
        return wanted

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

        # Everything you build or recruit has an epoch floor, and a check out
        # of reach must require the unlocks that reach it. Skipping this let
        # generation put `Epoch: Bronze Age` on `Build Siege Factory`, which
        # can't be built without it.
        for name in sorted(wanted):
            floor = LOCATION_MIN_EPOCH.get(name, 0)
            needed = ([] if floor <= self.starting_epoch
                      else self.epoch_items_up_to(floor))
            # A chained technology used to require the `Tech:` item below it,
            # because suppressing a technology's effect suppressed the unlock
            # it carried along with the benefit. The client puts the unlock
            # back itself now (`TechChains`), so researching opens the next
            # tier and only the benefit waits for the item.
            #
            # Dropping the requirement is what makes a `Tech:` item ordinary.
            # An item a rule names has to be progression — the reachability
            # sweep collects nothing else — so while this line existed, 72 of
            # them were progression and a research check could never hold an
            # epoch or a wonder without the technology below it being
            # load-bearing too.
            # Independent, and both apply. An unlock doesn't skip the epoch —
            # the game tests that separately in the same predicate — and
            # reaching the epoch doesn't skip the unlock.
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
            # A wonder needs its epoch and, with gating on, its unlock. Any N
            # will do, so the condition counts rather than naming which — the
            # fill decides what a run actually finds, and demanding a
            # particular set would be wrong in both directions.
            wanted_wonders = [
                (self.epoch_items_up_to(epoch), unlocks)
                for epoch, unlocks in self.wonder_options()
            ]

            def enough_wonders(state, need=self.wonders_needed,
                               options=wanted_wonders) -> bool:
                built = 0
                for epochs, unlocks in options:
                    if not state.has_all(unlocks, self.player):
                        continue
                    if not state.has_all(epochs, self.player):
                        continue
                    built += 1
                    if built >= need:
                        return True
                return False

            conditions.append(enough_wonders)

        self.multiworld.completion_condition[self.player] = (
            lambda state: any(c(state) for c in conditions)
        )

    def match_settings(self) -> dict:
        """The skirmish setup the client forces.

        Cheat codes are always off. Leaving them available undermines the whole
        seed.
        """
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
            # 0 stops the game ending the match by itself. 1 hands that back
            # to Empire Earth's own win and loss conditions.
            "victory_allowed": 0 if o.prevent_match_end.value else 1,
        }

    def fill_slot_data(self) -> dict:
        return {
            "starting_epoch": self.starting_epoch,
            "goal_epoch": self.goal_epoch,
            "goal": self.options.goal.current_key,
            "opponents": self.options.opponents.current_key,
            "ingame_messages": bool(self.options.ingame_messages.value),
            # Kept so an older client still understands this seed.
            "force_peace": self.options.opponents.value
            == self.options.opponents.option_allied,
            "building_unlocks": self.gates_buildings,
            # Which wonders this seed actually gates. The client can't work
            # that out — it knows every wonder, but a seed only ships unlock
            # items for those its goal epoch reaches, and gating one whose item
            # can never arrive locks it for the whole run with no way to open
            # it.
            "gated_wonders": self.usable_wonders() if self.gates_wonders else [],
            "technology_checks": bool(self.options.technology_checks.value),
            "wonders_needed": self.wonders_needed if self.wants_wonders else 0,
            "match_settings": self.match_settings(),
            "bundle_size": self.options.bundle_size.value,
        }
