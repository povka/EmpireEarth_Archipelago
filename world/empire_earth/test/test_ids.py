"""Item and location tables: every name unique, every id unique, nothing missing.

Ids are handed out in blocks with a base per kind, so a kind that outgrows its
block silently starts issuing ids that already mean something else. The
technology block held exactly 100 technologies against 100 slots before the
unit block was moved out to 1000.
"""

from ..Epochs import EPOCH_NAMES
from ..Items import ITEM_NAME_TO_ID
from ..Locations import (
    ALL_RECRUITABLE,
    LOCATION_NAME_TO_ID,
    PAIRED_LOCATIONS,
    RECRUIT_LOCATION_BY_DBNAME,
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
        missing = [db for db in ALL_RECRUITABLE
                   if db not in RECRUIT_LOCATION_BY_DBNAME]
        self.assertEqual(missing, [])

    def test_every_recruit_check_is_a_real_location(self):
        for db, name in RECRUIT_LOCATION_BY_DBNAME.items():
            self.assertIn(name, LOCATION_NAME_TO_ID, f"{db} -> {name}")

    def test_hero_pairs_are_symmetric_and_real(self):
        """Each hero of a tier must send the other's check, both ways.

        Only one of the two can exist in a match, so a one-way pairing would
        leave the other side unsendable - which is the state this replaced.
        """
        for name, partner in PAIRED_LOCATIONS.items():
            self.assertIn(name, LOCATION_NAME_TO_ID)
            self.assertIn(partner, LOCATION_NAME_TO_ID)
            self.assertEqual(PAIRED_LOCATIONS.get(partner), name)
