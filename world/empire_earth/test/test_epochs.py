"""Epoch unlocks are the progression spine — sequential, and needed for the goal."""

from ..Epochs import EPOCH_NAMES
from .bases import EmpireEarthTestBase


class TestEpochProgression(EmpireEarthTestBase):
    """Default options, so the full Space Age run."""

    def test_goal_requires_final_epoch(self):
        self.collect_all_but([f"Epoch: {EPOCH_NAMES[14]}"])
        self.assertFalse(
            self.multiworld.completion_condition[1](self.multiworld.state)
        )

    def test_epochs_are_sequential(self):
        """Reaching epoch N has to require every unlock up to N, not just N."""
        loc = self.multiworld.get_location(f"Reach {EPOCH_NAMES[3]}", 1)
        self.collect_all_but([f"Epoch: {EPOCH_NAMES[2]}"])
        self.assertFalse(loc.can_reach(self.multiworld.state))
