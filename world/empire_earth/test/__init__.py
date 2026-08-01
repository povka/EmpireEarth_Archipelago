"""Archipelago unit tests for Empire Earth.

These use AP's WorldTestBase and run inside an Archipelago source checkout
(`python -m pytest worlds/empire_earth`). They are not runnable against a
frozen Archipelago install, which ships no test framework - see
`tools/test_generation.py` for a matrix test that does run there.
"""

from test.bases import WorldTestBase

from ..Epochs import EPOCH_NAMES
from ..Items import ITEM_NAME_TO_ID, RESOURCE_ITEM_NAMES
from ..Locations import CACHE_LOCATIONS, LOCATION_NAME_TO_ID


class EmpireEarthTestBase(WorldTestBase):
    game = "Empire Earth"


class TestDefaults(EmpireEarthTestBase):
    """Default options: the full Space Age run."""

    def test_all_epoch_items_exist(self):
        for i in range(1, len(EPOCH_NAMES)):
            self.assertIn(f"Epoch: {EPOCH_NAMES[i]}", ITEM_NAME_TO_ID)

    def test_ids_are_unique(self):
        self.assertEqual(len(set(ITEM_NAME_TO_ID.values())), len(ITEM_NAME_TO_ID))
        self.assertEqual(
            len(set(LOCATION_NAME_TO_ID.values())), len(LOCATION_NAME_TO_ID)
        )

    def test_goal_requires_final_epoch(self):
        """The goal must not be reachable without the last epoch unlock."""
        self.collect_all_but([f"Epoch: {EPOCH_NAMES[14]}"])
        self.assertFalse(self.multiworld.completion_condition[1](
            self.multiworld.state))

    def test_epochs_are_sequential(self):
        """Reaching epoch N must require every unlock up to N."""
        loc = self.multiworld.get_location(f"Reach {EPOCH_NAMES[3]}", 1)
        self.collect_all_but([f"Epoch: {EPOCH_NAMES[2]}"])
        self.assertFalse(loc.can_reach(self.multiworld.state))


class TestShortGoal(EmpireEarthTestBase):
    """An early goal must trim both the item pool and the location list."""

    options = {"goal_epoch": "bronze_age"}

    def test_pool_is_trimmed(self):
        names = {item.name for item in self.multiworld.itempool}
        self.assertIn("Epoch: Bronze Age", names)
        self.assertNotIn("Epoch: Dark Age", names)
        self.assertNotIn("Epoch: Space Age", names)

    def test_locations_are_trimmed(self):
        names = {loc.name for loc in self.multiworld.get_locations(1)}
        self.assertIn("Reach Bronze Age", names)
        self.assertNotIn("Reach Dark Age", names)

    def test_counts_balance(self):
        """One item per location: 3 epochs + 5 bundles against 3 + 5 checks."""
        pool = len(self.multiworld.itempool)
        locs = len(self.multiworld.get_unfilled_locations(1))
        self.assertEqual(pool, locs)
        self.assertEqual(pool, 3 + len(RESOURCE_ITEM_NAMES))


class TestEarliestGoal(EmpireEarthTestBase):
    """The tightest configuration the world allows."""

    options = {"goal_epoch": "stone_age"}

    def test_generates(self):
        names = {item.name for item in self.multiworld.itempool}
        self.assertEqual(names & {f"Epoch: {n}" for n in EPOCH_NAMES},
                         {"Epoch: Stone Age"})
        self.assertEqual(
            len(self.multiworld.itempool), 1 + len(RESOURCE_ITEM_NAMES)
        )
