"""Shared base for the Empire Earth world tests.

Inheriting from `WorldTestBase` brings Archipelago's own preloaded tests with
it — reachability with every item, reachability with none, and a full fill — so
those run for each test class here without being written out.
"""

from test.bases import WorldTestBase


class EmpireEarthTestBase(WorldTestBase):
    game = "Empire Earth"
