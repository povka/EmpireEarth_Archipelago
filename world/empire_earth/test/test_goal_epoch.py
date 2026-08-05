"""An early goal must trim both the item pool and the location list."""

from ..Epochs import EPOCH_NAMES
from ..Items import RESOURCE_ITEM_NAMES
from .bases import EmpireEarthTestBase


class TestShortGoal(EmpireEarthTestBase):
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
        """Archipelago requires exactly one item per unfilled location."""
        pool = len(self.multiworld.itempool)
        locs = len(self.multiworld.get_unfilled_locations(1))
        self.assertEqual(pool, locs)


class TestEarliestGoal(EmpireEarthTestBase):
    """The tightest configuration the world allows."""

    options = {"goal_epoch": "stone_age"}

    def test_only_one_epoch_item(self):
        names = {item.name for item in self.multiworld.itempool}
        self.assertEqual(
            names & {f"Epoch: {n}" for n in EPOCH_NAMES}, {"Epoch: Stone Age"}
        )

    def test_pool_is_epoch_plus_bundles(self):
        self.assertEqual(
            len(self.multiworld.itempool), 1 + len(RESOURCE_ITEM_NAMES)
        )
