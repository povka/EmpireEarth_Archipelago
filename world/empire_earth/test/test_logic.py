"""Every check must actually require the epochs that reach it.

What this catches is a rule that stopped being applied - if `set_rules` ever
drops the epoch requirement, generation becomes free to hide `Epoch: Bronze
Age` behind `Build Siege Factory`, which is a seed nobody can finish.

What it cannot catch is a floor that is simply wrong, because it reads the same
`LOCATION_MIN_EPOCH` the rules are built from. `Recruit Cataphract` once
carried the Copper Age because per-unit checks inherited their family's
earliest member, and a test written this way would have agreed with it - both
sides of the comparison were wrong together. Only a reading taken from outside
the world settles that, which is what the recruit-floor test in
`tools/test_generation.py` does against `data.ssa`.
"""

from ..Epochs import EPOCH_NAMES
from ..Locations import LOCATION_MIN_EPOCH
from .bases import EmpireEarthTestBase


class TestEpochFloors(EmpireEarthTestBase):
    options = {"goal_epoch": "dark_age"}

    def test_checks_need_the_epochs_that_reach_them(self):
        goal = 4                                   # Dark Age, per the options
        everything = self.multiworld.get_all_state(False)
        locations = self.multiworld.get_locations(self.player)

        for epoch in range(1, goal + 1):
            name = f"Epoch: {EPOCH_NAMES[epoch]}"
            item = next(
                (i for i in self.multiworld.itempool if i.name == name), None
            )
            self.assertIsNotNone(item, f"{name} is not in the item pool")

            # Epochs are sequential, so dropping one also puts every later
            # epoch out of reach - hence `floor >= epoch` rather than `==`.
            state = everything.copy()
            state.remove(item)
            for loc in locations:
                floor = LOCATION_MIN_EPOCH.get(loc.name)
                if floor is None:
                    continue
                if floor >= epoch:
                    self.assertFalse(
                        loc.can_reach(state),
                        f"{loc.name} (epoch {floor}) is reachable without {name}",
                    )
                else:
                    self.assertTrue(
                        loc.can_reach(state),
                        f"{loc.name} (epoch {floor}) needs {name} and should not",
                    )
