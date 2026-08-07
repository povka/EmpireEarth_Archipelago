"""Generation matrix test that runs against a frozen Archipelago install.

A frozen Archipelago ships no test framework, so the WorldTestBase tests in
world/empire_earth/test only run in a source checkout. This exercises the same
ground by driving ArchipelagoGenerate.exe over every option combination and
checking the resulting spoiler.

    py tools\\test_generation.py
    py tools\\test_generation.py --quick
"""

from __future__ import annotations

import argparse
import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

GENERATE = r"C:\ProgramData\Archipelago\ArchipelagoGenerate.exe"
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

GOALS = [
    ("stone_age", 1), ("copper_age", 2), ("bronze_age", 3), ("dark_age", 4),
    ("middle_ages", 5), ("renaissance", 6), ("imperial_age", 7),
    ("industrial_age", 8), ("atomic_age_ww1", 9), ("atomic_age_ww2", 10),
    ("atomic_age_modern", 11), ("digital_age", 12), ("nano_age", 13),
    ("space_age", 14),
]

YAML = """name: EETest
description: generation matrix
game: Empire Earth
requires:
  version: 0.6.7

Empire Earth:
  goal_epoch: {goal}
  bundle_size: {bundle}
"""

# The match settings are only enforced at runtime, but they still have to
# survive generation and reach the spoiler, which is where a bad option
# definition shows up.
SETTINGS_YAML = """name: EETest
description: match settings
game: Empire Earth
requires:
  version: 0.6.7

Empire Earth:
  # 'either' because this fixture sets wonders_for_victory above 0, which the
  # reach_epoch goal refuses by design.
  goal: either
  starting_epoch: copper_age
  goal_epoch: dark_age
  map_size: huge
  resources: deathmatch
  game_variant: tournament
  difficulty: hard
  game_speed: very_fast
  unit_limit: 1175
  wonders_for_victory: 4
  reveal_map: true
  use_custom_civs: true
  lock_teams: true
  lock_speed: true
"""

GOAL_YAML = """name: EETest
description: {label}
game: Empire Earth
requires:
  version: 0.6.7

Empire Earth:
  goal: {goal}
  goal_epoch: {goal_epoch}
  wonders_for_victory: {wonders}
"""

# (goal, goal_epoch, wonders, expected wonder checks, must generate)
GOAL_CASES = [
    ("reach_epoch", "space_age", 0, 0, True),
    ("wonder_victory", "space_age", 3, 7, True),
    ("wonder_victory", "bronze_age", 6, 6, True),   # Time Machine excluded
    ("either", "dark_age", 1, 6, True),
    # wonders_for_victory and goal must agree, or the match could end in a
    # victory the seed does not recognise.
    ("reach_epoch", "space_age", 2, 0, False),
    ("wonder_victory", "space_age", 0, 0, False),
    # Wonders cannot be built before the Bronze Age, so a wonder goal in a seed
    # that stops earlier is unwinnable and must be refused.
    ("wonder_victory", "copper_age", 1, 0, False),
    ("wonder_victory", "bronze_age", 1, 6, True),
]

SETTINGS_EXPECTED = [
    ("Goal", "Either"),
    ("Starting Epoch", "Copper Age"), ("Goal Epoch", "Dark Age"),
    ("Map Size", "Huge"), ("Resources", "Deathmatch"),
    ("Game Variant", "Tournament"), ("Difficulty Level", "Hard"),
    ("Game Speed", "Very Fast"), ("Game Unit Limit", "1175"),
    ("Wonders For Victory", "4"), ("Reveal Map", "Yes"),
    ("Use Custom Civs", "Yes"), ("Lock Teams", "Yes"), ("Lock Speed", "Yes"),
]


def world_modules():
    """Import the world's data modules outside Archipelago.

    They are written to load either as a package or standalone, but they still
    import names from BaseClasses, so it is stubbed with just enough to satisfy
    the class definitions - none of the data tables touch it.
    """
    import types as _types

    sys.path.insert(0, os.path.join(ROOT, "world", "empire_earth"))
    if "BaseClasses" not in sys.modules:
        fake = _types.ModuleType("BaseClasses")
        fake.Location = object
        fake.Item = object

        class _Classification:
            progression = "progression"
            filler = "filler"
            useful = "useful"

        fake.ItemClassification = _Classification
        sys.modules["BaseClasses"] = fake


def sync_world() -> str:
    """Install the working tree into Archipelago before generating anything.

    `ArchipelagoGenerate.exe` loads the apworld from `custom_worlds`, never
    this checkout, so without this every seed here is built by whatever was
    installed last while the assertions read the current tables. The two
    disagreeing looks exactly like a logic bug: after the recruit floors were
    corrected, a stale install put `Recruit Sagitarian Cruiser` in a Dark Age
    seed and three tests failed for a bug that had already been fixed.
    """
    sys.path.insert(0, HERE)
    from build_apworld import build

    dest = os.path.join(os.path.dirname(GENERATE), "custom_worlds")
    if not os.path.isdir(dest):
        return f"no custom_worlds at {dest}; generating against whatever is installed"
    target = os.path.join(dest, "empire_earth.apworld")
    count, size = build(target)
    return f"installed {count} files ({size:,} bytes) -> {target}"


def spoiler_for(yaml_text: str) -> tuple[str | None, str]:
    """Generate one seed and hand back its spoiler, or a reason it failed."""
    work = tempfile.mkdtemp(prefix="ee_gen_")
    try:
        players = os.path.join(work, "players")
        out = os.path.join(work, "out")
        os.makedirs(players)
        os.makedirs(out)
        with open(os.path.join(players, "p.yaml"), "w") as f:
            f.write(yaml_text)

        proc = subprocess.run(
            [GENERATE, "--player_files_path", players, "--outputpath", out,
             "--seed", "424242"],
            capture_output=True, text=True, timeout=300,
            stdin=subprocess.DEVNULL,
        )
        if proc.returncode != 0:
            tail = (proc.stdout or "")[-400:] + (proc.stderr or "")[-400:]
            return None, f"generator exited {proc.returncode}: {tail.strip()}"

        zips = glob.glob(os.path.join(out, "*.zip"))
        if not zips:
            return None, "no output archive produced"
        with zipfile.ZipFile(zips[0]) as z:
            spoiler = next((n for n in z.namelist() if "Spoiler" in n), None)
            if not spoiler:
                return None, "no spoiler in archive"
            return z.read(spoiler).decode("utf-8", "replace"), ""
    finally:
        shutil.rmtree(work, ignore_errors=True)


def run_one(goal: str, epochs: int, bundle: int) -> tuple[bool, str]:
    text, why = spoiler_for(YAML.format(goal=goal, bundle=bundle))
    if text is None:
        return False, why

    # Every epoch up to the goal must exist as an item and a check,
    # and nothing beyond it may appear.
    reach = set(re.findall(r"^Reach (.+?):", text, re.M))
    # Require the ": Epoch: " placement so the spoiler's own
    # "Goal Epoch: <name>" header is not counted as an item.
    items = set(re.findall(r": Epoch: (.+?)$", text, re.M))
    if len(reach) != epochs:
        return False, f"expected {epochs} Reach checks, found {len(reach)}"
    if len(items) != epochs:
        return False, f"expected {epochs} epoch items, found {len(items)}"
    if "Goal Epoch:" not in text:
        return False, "spoiler has no Goal Epoch line"
    return True, f"{epochs} epochs, {len(reach)} checks"


WONDER_NAMES = [
    "Coliseum", "Ishtar gates", "Library of Alexandria",
    "Lighthouse at Alexandria", "Temple of Zeus", "Time Machine",
    "Tower of Babylon",
]


def run_goal(goal, goal_epoch, wonders, expect_checks, should_generate):
    label = f"goal={goal} epoch={goal_epoch} wonders={wonders}"
    text, why = spoiler_for(GOAL_YAML.format(
        label=label, goal=goal, goal_epoch=goal_epoch, wonders=wonders))

    if not should_generate:
        # The pairing rule has to be enforced, not merely documented.
        if text is None:
            return True, "refused, as it should be"
        return False, "generated a seed that should have been refused"

    if text is None:
        return False, why
    built = {w for w in WONDER_NAMES if re.search(
        rf"^Build {re.escape(w)}:", text, re.M)}
    if len(built) != expect_checks:
        return False, f"expected {expect_checks} wonder checks, found {len(built)}"
    # Time Machine needs the Space Age, so it may only appear in such a seed.
    if "Time Machine" in built and goal_epoch != "space_age":
        return False, "Time Machine check in a seed that cannot reach it"
    return True, f"{len(built)} wonder checks"


LOGIC_YAML = """name: EETest
description: epoch logic
game: Empire Earth
requires:
  version: 0.6.7

Empire Earth:
  goal: reach_epoch
  starting_epoch: {start}
  goal_epoch: {goal}
"""


def run_logic(start: str, goal: str, start_i: int, goal_i: int):
    """No check may hold an epoch item that check itself needs to reach.

    This is a real bug that shipped: `Epoch: Bronze Age` was placed on
    `Build Siege Factory`, which cannot be built before the Dark Age. Build and
    recruit checks had no epoch requirements at all.
    """
    world_modules()
    from Locations import LOCATION_MIN_EPOCH
    from Epochs import EPOCH_NAMES

    text, why = spoiler_for(LOGIC_YAML.format(start=start, goal=goal))
    if text is None:
        return False, why

    circular, beyond = [], []
    for line in text.splitlines():
        m = re.match(r"^(.+?): (Epoch: .+?)\s*$", line.strip())
        if not m:
            continue
        loc, item = m.group(1), m.group(2)
        floor = LOCATION_MIN_EPOCH.get(loc)
        if floor is None:
            continue
        if floor > goal_i:
            beyond.append(loc)
        grants = EPOCH_NAMES.index(item[len("Epoch: "):])
        if floor >= grants:
            circular.append(f"{item} on {loc} (needs epoch {floor})")

    if circular:
        return False, "circular: " + "; ".join(circular[:3])
    if beyond:
        return False, f"{len(beyond)} check(s) past the goal epoch: {beyond[:3]}"
    return True, "no circular or unreachable placements"


UNLOCK_YAML = """name: EETest
description: building unlocks
game: Empire Earth
requires:
  version: 0.6.7

Empire Earth:
  goal: reach_epoch
  building_unlocks: true
  starting_epoch: {start}
  goal_epoch: {goal}
"""


def run_unlocks(start: str, goal: str, goal_i: int):
    """No building unlock may sit behind a check that needs that building.

    `Building: Stable` on `Build Stable` is the obvious form. The subtle one is
    `Building: Stable` on `Recruit Lancer`, because cavalry is produced at a
    stable - which is why the producer table exists at all.
    """
    world_modules()
    from Locations import LOCATION_MIN_EPOCH, RECRUIT_LOCATION_PRODUCERS
    from Items import BUILDING_ITEM_PREFIX, LOCKABLE_BUILDINGS

    text, why = spoiler_for(UNLOCK_YAML.format(start=start, goal=goal))
    if text is None:
        return False, why

    # A placement appears in both the Locations and Playthrough sections, so
    # count the buildings rather than the lines.
    placed, circular = set(), []
    for line in text.splitlines():
        # Built from the constant rather than spelled out, so renaming the item
        # cannot leave this matching a prefix nothing produces any more - which
        # would make every run pass with "no Unlock items reached the spoiler".
        m = re.match(rf"^(.+?): ({re.escape(BUILDING_ITEM_PREFIX)}.+?)\s*$",
                     line.strip())
        if not m:
            continue
        loc, building = m.group(1), m.group(2)[len(BUILDING_ITEM_PREFIX):]
        placed.add(building)
        if loc == f"Build {building}":
            circular.append(f"{building} on its own build check")
        elif loc.startswith("Recruit "):
            # Keyed by the location, not by `loc` minus its prefix. That left a
            # unit *display* name being looked up in a table keyed by *family*,
            # so it matched nothing, `producers` was always empty, and the
            # circularity test below could never fire - the subtle case this
            # function exists to catch was silently passing.
            producers = RECRUIT_LOCATION_PRODUCERS.get(loc, ())
            # Only circular when this building is the sole way to get the
            # family. Another producer leaves the check reachable, and one that
            # is never locked at all - a Capitol makes citizens - leaves it
            # free regardless.
            if any(p not in LOCKABLE_BUILDINGS for p in producers):
                continue
            if set(producers) == {building}:
                circular.append(f"{building} on {loc}, its only producer")

    if circular:
        return False, "circular: " + "; ".join(circular[:3])
    if not placed:
        return False, "no Unlock items reached the spoiler"

    expected = {b for b in LOCKABLE_BUILDINGS
                if LOCATION_MIN_EPOCH.get(f"Build {b}", 0) <= goal_i}
    if placed != expected:
        return False, (f"expected {len(expected)} unlocks, found {len(placed)}"
                       f" (missing {sorted(expected - placed)},"
                       f" extra {sorted(placed - expected)})")
    return True, f"{len(placed)} unlocks, none circular"


def run_simulation(start: str, goal: str, start_i: int, goal_i: int,
                   unlocks: bool):
    """Play the seed with a model of the game and check it can be finished.

    Generation only proves a seed consistent with the world's own rules, so a
    rule that is wrong about the game produces a seed that is provably
    completable and actually is not. This models the game instead: an epoch is
    reached by holding every unlock up to it, a building needs its unlock AND
    its epoch, and a unit needs a producer you can build right now.

    It caught a real deadlock. `Recruit Siege` accepts a Barracks or a Siege
    Factory, so a run holding `Building: Siege Factory` from the start looked able
    to recruit siege units in the Copper Age - but a siege factory cannot be
    built until the Dark Age, and the epoch unlocks to get there were behind
    that very check.
    """
    world_modules()
    from Locations import LOCATION_MIN_EPOCH, LOCATION_NAME_TO_ID
    from Locations import building_epoch
    from Objects import BUILDINGS
    from Items import LOCKABLE_BUILDINGS, BUILDING_PREREQS, building_item
    from Epochs import EPOCH_NAMES

    yaml = (UNLOCK_YAML if unlocks else LOGIC_YAML).format(start=start, goal=goal)
    text, why = spoiler_for(yaml)
    if text is None:
        return False, why

    placements = {}
    for line in text.splitlines():
        loc, _, item = line.strip().partition(": ")
        if loc in LOCATION_NAME_TO_ID and item:
            placements[loc] = item

    def buildable(building, epoch, inv):
        # A match starts with a Capitol already standing, whatever epoch it
        # begins in, so it is available before its own epoch requirement.
        if building == "Capitol":
            return True
        if building_epoch(building) > epoch:
            return False
        # Reached through another building rather than a build menu.
        prereq = BUILDING_PREREQS.get(building)
        if prereq and not buildable(prereq, epoch, inv):
            return False
        if unlocks and building in LOCKABLE_BUILDINGS \
                and building_item(building) not in inv:
            return False
        return True

    def reachable(loc, epoch, inv):
        if LOCATION_MIN_EPOCH.get(loc, 0) > epoch:
            return False
        if loc.startswith("Build "):
            name = loc[len("Build "):]
            if name not in set(BUILDINGS.values()):
                return True                     # a wonder; its floor applied
            return buildable(name, epoch, inv)
        if loc.startswith("Recruit "):
            # Per unit, matching what the world's own rules use; the floor is
            # applied above.
            from Locations import RECRUIT_LOCATION_PRODUCERS
            producers = RECRUIT_LOCATION_PRODUCERS.get(loc, ())
            return any(buildable(b, epoch, inv) for b in producers)
        if loc.startswith("Research "):
            # A technology is researched at exactly one building, and its own
            # epoch floor has already been applied above.
            from Locations import TECH_LOCATION_BUILDING
            return buildable(TECH_LOCATION_BUILDING[loc], epoch, inv)
        if loc.startswith("Reach "):
            # Not covered by LOCATION_MIN_EPOCH, which only carries build and
            # recruit floors. Treating these as free let the simulation collect
            # an item from `Reach Dark Age` while still in the Copper Age.
            name = loc[len("Reach "):]
            return name in EPOCH_NAMES and EPOCH_NAMES.index(name) <= epoch
        return True

    inv, taken = set(), set()
    while True:
        epoch = start_i
        while epoch < goal_i and f"Epoch: {EPOCH_NAMES[epoch + 1]}" in inv:
            epoch += 1
        progress = False
        for loc, item in placements.items():
            if loc not in taken and reachable(loc, epoch, inv):
                taken.add(loc)
                inv.add(item)
                progress = True
        if not progress:
            break

    want = f"Epoch: {EPOCH_NAMES[goal_i]}"
    if want not in inv:
        stuck = sorted(set(placements) - taken)
        return False, (f"deadlock: {len(taken)}/{len(placements)} checks, "
                       f"never got {want}; unreachable e.g. {stuck[:3]}")
    return True, f"completable, {len(taken)}/{len(placements)} checks reachable"


def run_settings() -> tuple[bool, str]:
    """Every match setting must survive generation with the value asked for."""
    text, why = spoiler_for(SETTINGS_YAML)
    if text is None:
        return False, why
    wrong = [
        label for label, want in SETTINGS_EXPECTED
        # Trailing \s* because the spoiler is written with CRLF line endings.
        if not re.search(rf"^{re.escape(label)}: +{re.escape(want)}\s*$", text, re.M)
    ]
    if wrong:
        return False, "not set as asked: " + ", ".join(wrong)
    # Starting in Copper Age leaves Bronze and Dark as the only epoch checks.
    reach = set(re.findall(r"^Reach (.+?):", text, re.M))
    if reach != {"Bronze Age", "Dark Age"}:
        return False, f"unexpected epoch checks: {sorted(reach)}"
    return True, f"{len(SETTINGS_EXPECTED)} settings, 2 epoch checks"


def run_data_floors() -> tuple[bool, str]:
    """Check the recruit checks against the game's database, not the world's.

    Every other test here reads `LOCATION_MIN_EPOCH` and so believes whatever
    it says. That is exactly how both bugs from the first two-player run got
    out, and neither was subtle once measured:

      * `Recruit Cataphract` carried epoch 3, the earliest member of the Lancer
        family, when a Cataphract is a Middle Ages unit. Generation put
        `Epoch: Dark Age` behind it and the seed could not be finished. The
        circular-placement test above would have caught it, had the number it
        compares against not been the wrong one.
      * `Inf01 - Rock Thrower` had no check at all. Its family is `Human`,
        which was missing from a hand-written list of families, so recruiting
        one sent nothing.

    So this reads `data.ssa` directly: every unit in it must have a check, and
    every check must carry that unit's own epoch. Skipped where the game is not
    installed, which is the only reason it is here rather than in the world's
    own test package.
    """
    try:
        from dbobjects import objects, record_name
        from ssa_extract import DEFAULT_SSA
    except ImportError as e:
        return True, f"skipped: {e}"
    except SystemExit:
        # `ssa_extract` resolves the game's path at import time, and
        # `install.find_root()` raises SystemExit when there is no install.
        # SystemExit derives from BaseException, so `except ImportError` let it
        # straight past and it took the whole run down with it - the settings
        # test, every goal case and the summary never ran, and the suite exited
        # non-zero on a machine that simply has no game installed. The skip
        # below was written for this and could never be reached.
        return True, "skipped: no Empire Earth install"
    if not os.path.exists(DEFAULT_SSA):
        return True, "skipped: game data not installed"

    import struct
    world_modules()
    from Locations import (
        LOCATION_MIN_EPOCH,
        RECRUIT_LOCATION_BY_DBNAME,
        STARTING_LOCATIONS,
    )
    from Objects import UNIT_FAMILY_BY_NAME

    MIN_EPOCH_OFF = 0x70
    db_epoch = {}
    for _i, r, _size in objects(DEFAULT_SSA):
        name = record_name(r)
        if name.strip():
            db_epoch[name] = struct.unpack_from("<i", r, MIN_EPOCH_OFF)[0]

    missing, wrong = [], []
    for db_name in UNIT_FAMILY_BY_NAME:
        if db_name.lower().startswith("x"):
            continue                       # scenario and campaign props
        loc = RECRUIT_LOCATION_BY_DBNAME.get(db_name)
        if loc is None:
            missing.append(db_name)
            continue
        raw = db_epoch.get(db_name)
        # The database counts epochs from 1 at the Prehistoric Age and the rest
        # of this project counts from 0; see unit_epoch() in gen_objects.py for
        # how that was pinned down against the running game.
        want = None if raw is None else max(raw - 1, 0)
        got = LOCATION_MIN_EPOCH.get(loc)
        # A check the match always starts with is pinned to 0 on purpose.
        if want is None or loc in STARTING_LOCATIONS:
            continue
        # Above the unit's own epoch is fine and often right - the floor also
        # carries the producing building, so a Prehistoric unit trained at a
        # Stable waits for the Copper Age. Below it is the bug: it lets
        # generation hide an epoch item behind a check that needs that epoch.
        if got is None or got < want:
            wrong.append(f"{loc}: floor {got}, unit's own epoch is {want}")

    if missing:
        return False, f"{len(missing)} unit(s) with no check: {missing[:3]}"
    if wrong:
        return False, f"{len(wrong)} wrong floor(s): {wrong[:3]}"
    return True, (f"{len(RECRUIT_LOCATION_BY_DBNAME)} recruit checks, "
                  "no floor below the unit's own epoch")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="only the extremes")
    args = ap.parse_args()

    if not os.path.exists(GENERATE):
        sys.exit(f"not found: {GENERATE}")

    # Seeds are generated by the installed apworld, so install this one first.
    print(f"  {sync_world()}")
    print()

    cases = []
    goals = [GOALS[0], GOALS[2], GOALS[-1]] if args.quick else GOALS
    for goal, epochs in goals:
        cases.append((goal, epochs, 500))
    # A couple of option edges regardless of mode.
    cases.append(("bronze_age", 3, 50))
    cases.append(("space_age", 14, 10000))

    failures = 0
    for goal, epochs, bundle in cases:
        ok, detail = run_one(goal, epochs, bundle)
        label = f"goal={goal:<18s} bundle={bundle:<6d}"
        print(f"  {'PASS' if ok else 'FAIL'}  {label}  {detail}")
        failures += 0 if ok else 1

    for start, goal, si, gi in (("copper_age", "dark_age", 2, 4),
                               ("prehistoric_age", "space_age", 0, 14),
                               ("copper_age", "bronze_age", 2, 3)):
        ok, detail = run_logic(start, goal, si, gi)
        label = f"logic {start} -> {goal}"
        print(f"  {'PASS' if ok else 'FAIL'}  {label:<45s}  {detail}")
        failures += 0 if ok else 1
    total_extra = 3

    for start, goal, gi in (("prehistoric_age", "space_age", 14),
                            ("copper_age", "dark_age", 4)):
        ok, detail = run_unlocks(start, goal, gi)
        label = f"unlocks {start} -> {goal}"
        print(f"  {'PASS' if ok else 'FAIL'}  {label:<45s}  {detail}")
        failures += 0 if ok else 1
    total_extra += 2

    # The only check that models the game rather than the world's own rules.
    for start, goal, si, gi, gated in (
        ("copper_age", "dark_age", 2, 4, True),
        ("prehistoric_age", "space_age", 0, 14, True),
        ("copper_age", "dark_age", 2, 4, False),
    ):
        ok, detail = run_simulation(start, goal, si, gi, gated)
        label = f"playable {start} -> {goal}{' +unlocks' if gated else ''}"
        print(f"  {'PASS' if ok else 'FAIL'}  {label:<45s}  {detail}")
        failures += 0 if ok else 1
    total_extra += 3

    ok, detail = run_data_floors()
    # Reported as SKIP rather than PASS when there is no game to read: this is
    # the only check that reads the database instead of the world's own tables,
    # so a run without it has not verified the floors at all, and saying PASS
    # would claim otherwise.
    mark = "SKIP" if ok and detail.startswith("skipped") else ("PASS" if ok else "FAIL")
    print(f"  {mark}  {'recruit floors vs database':<45s}  {detail}")
    failures += 0 if ok else 1
    total_extra += 1

    ok, detail = run_settings()
    print(f"  {'PASS' if ok else 'FAIL'}  {'match settings':<45s}  {detail}")
    failures += 0 if ok else 1

    for goal, epoch, wonders, expect, should in GOAL_CASES:
        ok, detail = run_goal(goal, epoch, wonders, expect, should)
        label = f"goal={goal:<14s} epoch={epoch:<11s} wonders={wonders}"
        print(f"  {'PASS' if ok else 'FAIL'}  {label}  {detail}")
        failures += 0 if ok else 1

    total = len(cases) + 1 + len(GOAL_CASES) + total_extra

    print(f"\n{total - failures}/{total} passed")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
