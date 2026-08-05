"""Item and location tables: every name unique, every id unique, nothing missing.

Ids are handed out in blocks with a base per kind, so a kind that outgrows its
block silently starts issuing ids that already mean something else. The
technology block held exactly 100 technologies against 100 slots before the
unit block was moved out to 1000.
"""

from ..Epochs import EPOCH_NAMES
from ..Items import ITEM_NAME_TO_ID
from ..Locations import (
    LOCATION_NAME_TO_ID,
    RECRUIT_LOCATION_BY_DBNAME,
    TRAINABLE_UNITS,
)
from .bases import EmpireEarthTestBase


class TestTables(EmpireEarthTestBase):
    def test_item_ids_are_unique(self):
        self.assertEqual(len(set(ITEM_NAME_TO_ID.values())), len(ITEM_NAME_TO_ID))

    def test_location_ids_are_unique(self):
        self.assertEqual(
            len(set(LOCATION_NAME_TO_ID.values())), len(LOCATION_NAME_TO_ID)
        )

    def test_all_epoch_items_exist(self):
        for i in range(1, len(EPOCH_NAMES)):
            self.assertIn(f"Epoch: {EPOCH_NAMES[i]}", ITEM_NAME_TO_ID)

    def test_every_unit_has_a_check(self):
        """A unit with no check is a unit that can never be sent.

        `Inf01 - Rock Thrower` had none for a while: units were taken from a
        hand-written list of families that did not include its own, so
        recruiting one sent nothing and the player had no way to tell.
        """
        missing = [db for db in TRAINABLE_UNITS
                   if db not in RECRUIT_LOCATION_BY_DBNAME]
        self.assertEqual(missing, [])

    def test_every_recruit_check_is_a_real_location(self):
        for db, name in RECRUIT_LOCATION_BY_DBNAME.items():
            self.assertIn(name, LOCATION_NAME_TO_ID, f"{db} -> {name}")
