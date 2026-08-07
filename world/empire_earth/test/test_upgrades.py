"""A retired unit's check must still be sendable by whatever replaced it.

Empire Earth withdraws a unit when a later tier takes over, so a per-unit check
would be missable. The client no longer fights that - cancelling the engine's
replacement flag reverted the upgrade instead of preserving both units - so the
replacement carries the replaced unit's check.

The direction is what keeps this safe: recruiting a unit only ever sends *more*
checks. An extra send is a free check; a missing one can strand a seed.
"""

from BaseClasses import LocationProgressType

from ..Locations import (
    CIV_LOCKED_LOCATIONS,
    NO_PROGRESSION_LOCATIONS,
    LOCATION_ALSO_SENDS,
    LOCATION_NAME_TO_ID,
    PAIRED_LOCATIONS,
)
from .bases import EmpireEarthTestBase


class TestCivLockedChecks(EmpireEarthTestBase):
    """A unit only one civilisation can field must not be load-bearing.

    The client leaves civilisation choice to the player, so a Cyber Ninja is
    only recruitable by Japan or by a custom civilisation that took the right
    power. Nothing warns a player at generation time, and discovering that
    progression sits behind a unit your civilisation cannot build means
    starting a fresh match.
    """

    options = {"goal_epoch": "space_age"}

    def test_civ_locked_checks_hold_no_progression(self):
        self.assertTrue(CIV_LOCKED_LOCATIONS, "expected at least one")
        self.assertLessEqual(CIV_LOCKED_LOCATIONS, NO_PROGRESSION_LOCATIONS)
        for name in NO_PROGRESSION_LOCATIONS:
            location = self.multiworld.get_location(name, self.player)
            self.assertEqual(location.progress_type,
                             LocationProgressType.EXCLUDED, name)
            self.assertFalse(location.item.advancement, name)

    def test_they_are_still_real_checks(self):
        for name in CIV_LOCKED_LOCATIONS:
            self.assertIn(name, LOCATION_NAME_TO_ID)


class TestUpgradeCascade(EmpireEarthTestBase):
    def test_every_name_is_a_real_location(self):
        for name, extras in LOCATION_ALSO_SENDS.items():
            self.assertIn(name, LOCATION_NAME_TO_ID)
            for other in extras:
                self.assertIn(other, LOCATION_NAME_TO_ID, f"{name} -> {other}")

    def test_nothing_sends_itself(self):
        for name, extras in LOCATION_ALSO_SENDS.items():
            self.assertNotIn(name, extras)

    def test_the_relation_is_acyclic(self):
        """Upgrades run one way only.

        A cycle would mean two units each claiming to replace the other, which
        no ordering of tiers can produce - so this is really a check that the
        chain was built from tiers and not from something symmetric like the
        hero pairing, which is deliberately two-way and lives in its own table.
        """
        for start in LOCATION_ALSO_SENDS:
            seen, stack = set(), [start]
            while stack:
                here = stack.pop()
                for nxt in LOCATION_ALSO_SENDS.get(here, ()):
                    if nxt in PAIRED_LOCATIONS:
                        continue          # heroes are symmetric by design
                    self.assertNotEqual(nxt, start, f"cycle through {start}")
                    if nxt not in seen:
                        seen.add(nxt)
                        stack.append(nxt)

    def test_the_archer_line(self):
        """The line this whole mechanism was written for.

        Slinger -> Simple Bowman -> Composite Bow -> Long Bow, which is what
        the game's wiki describes: the Archer line "starts in the Stone age
        with the Slinger" and "ends with Long Bow in the Middle Ages".
        """
        self.assertEqual(
            LOCATION_ALSO_SENDS.get("Recruit Simple Bowman"),
            ("Recruit Slinger",),
        )
        self.assertEqual(
            LOCATION_ALSO_SENDS.get("Recruit Composite Bow"),
            ("Recruit Slinger", "Recruit Simple Bowman"),
        )
        self.assertEqual(
            LOCATION_ALSO_SENDS.get("Recruit Long Bow"),
            ("Recruit Slinger", "Recruit Simple Bowman",
             "Recruit Composite Bow"),
        )
        # The bottom of a line replaces nothing.
        self.assertNotIn("Recruit Slinger", LOCATION_ALSO_SENDS)

    def test_the_crossbow_is_its_own_line(self):
        """A Crossbow is not a rung on the archer ladder.

        It sits at the same tier as the Composite Bow and below the Long Bow,
        so a tier-ordered rule folded it in - but the wiki is explicit that
        "The Crossbow is the only of its line". It neither replaces anything
        nor is replaced, so it sends only its own check and no other check
        depends on it.
        """
        self.assertNotIn("Recruit Cross Bow", LOCATION_ALSO_SENDS)
        for name, extras in LOCATION_ALSO_SENDS.items():
            self.assertNotIn("Recruit Cross Bow", extras, f"sent by {name}")

    def test_rock_thrower_is_its_own_line(self):
        """Nothing replaces a Rock Thrower.

        It shares a family and a name prefix with the late infantry, so the
        tier rule had every one of them carrying its check.
        """
        self.assertNotIn("Recruit Rock Thrower", LOCATION_ALSO_SENDS)
        for name, extras in LOCATION_ALSO_SENDS.items():
            self.assertNotIn("Recruit Rock Thrower", extras, f"sent by {name}")

    def test_the_late_infantry_are_four_lines_and_three_singles(self):
        """Ten units share the `Human` family and the `Inf` prefix.

        A tier-ordered rule read them as one ladder from Rock Thrower to Heavy
        Mortar. None of it is guessable from the names: a Sharpshooter becomes
        a Sniper, a Hand Cannoneer becomes a Trench Mortar, and three of the
        ten are replaced by nothing at all.
        """
        self.assertEqual(LOCATION_ALSO_SENDS.get("Recruit Sniper"),
                         ("Recruit Sharpshooter",))
        self.assertEqual(LOCATION_ALSO_SENDS.get("Recruit Trench Mortar"),
                         ("Recruit Hand Cannoneer",))
        self.assertEqual(LOCATION_ALSO_SENDS.get("Recruit Heavy Mortar"),
                         ("Recruit Hand Cannoneer", "Recruit Trench Mortar"))
        self.assertEqual(LOCATION_ALSO_SENDS.get("Recruit Bazooka Infantry"),
                         ("Recruit Grenade Launcher",))

        for lone in ("Recruit Partisan", "Recruit Flame Thrower"):
            self.assertNotIn(lone, LOCATION_ALSO_SENDS)
            for name, extras in LOCATION_ALSO_SENDS.items():
                self.assertNotIn(lone, extras, f"{lone} sent by {name}")

    def test_the_sword_line_skips_the_barbarian(self):
        """Clubman -> Maceman -> Short Sword -> Long Sword.

        A Barbarian sits between the last two by tier and is not a rung: the
        wiki lists Barbarians *beside* Short Swords in the Dark Age and Middle
        Ages, never as an upgrade of one.
        """
        self.assertEqual(
            LOCATION_ALSO_SENDS.get("Recruit LongSword"),
            ("Recruit Clubman", "Recruit Maceman", "Recruit Short Sword"),
        )
        self.assertNotIn("Recruit Barbarian", LOCATION_ALSO_SENDS)
        for name, extras in LOCATION_ALSO_SENDS.items():
            self.assertNotIn("Recruit Barbarian", extras, f"sent by {name}")

    def test_an_upgrade_that_crosses_families(self):
        """A Stinger Soldier replaces a Bazooka Infantry.

        They share neither family nor name prefix - `Land AA` against `Human` -
        so nothing about the data connects them and the tier rule cannot see
        the link at all. Without it the Bazooka's check died on reaching the
        Modern epoch.

        The Grenade Launcher comes too: a cross-group link lands mid-chain, so
        the rungs below it have to be carried or they are lost at the same
        moment.
        """
        self.assertEqual(
            LOCATION_ALSO_SENDS.get("Recruit Stinger Soldier"),
            ("Recruit Grenade Launcher", "Recruit Bazooka Infantry"),
        )

    def test_the_frigate_line_runs_through_warrington(self):
        """The one frigate not named "Frigate".

        Matching no role word left it in the whole `Ship` bundle, sending 21
        checks across frigates, transports and fishing boats alike. The wiki
        puts it between Good Hope and Juggernaut, which is where its tier
        already sat.
        """
        self.assertEqual(
            LOCATION_ALSO_SENDS.get("Recruit Warrington"),
            ("Recruit Stone Frigate [War Raft]", "Recruit Copper Frigate",
             "Recruit Bronze Frigate", "Recruit Byzantine Frigate",
             "Recruit Middle Age Frigate", "Recruit Renaissance Frigate",
             "Recruit Imperial Frigate", "Recruit Royal Frigate",
             "Recruit Good Hope Frigate"),
        )
        # The rung above it carries it, which is what stops it being missable.
        self.assertIn("Recruit Warrington",
                      LOCATION_ALSO_SENDS["Recruit Juggernaut Frigate"])
