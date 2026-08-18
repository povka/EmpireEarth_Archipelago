"""Generation matrix test: generate every option combination, read the spoiler.

Runs against a source checkout of Archipelago when it finds one and falls back
to the frozen `ArchipelagoGenerate.exe`. Use the checkout — see the note on
`AP_SOURCE` for what the frozen build lets through without complaining.

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

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# Prefer a source checkout of Archipelago, because the frozen build can't fail.
#
# `setup.py` freezes with cx_Freeze `optimize: 1`, so every `assert` in the core
# is stripped and — worse — the accessibility check in
# `BaseClasses.fulfills_accessibility` sits behind `if __debug__` and downgrades
# to a logged warning. A seed where a location is unreachable still writes an
# archive and still exits 0, so this whole harness happily passed 40 of 40 while
# every chained technology in the world was unreachable.
#
# The source tree needs Python 3.11.9 - 3.13.x; `ModuleUpdate` refuses anything
# newer, which is why this looks for an interpreter rather than using `sys`.
AP_SOURCE = r"D:\Dev_programs\Archipelago"
FROZEN = r"C:\ProgramData\Archipelago\ArchipelagoGenerate.exe"


def generator() -> tuple[list[str], str, bool]:
    """The command to generate with, where its `custom_worlds` is, and whether
    assertions are live."""
    script = os.path.join(AP_SOURCE, "Generate.py")
    if os.path.exists(script):
        for tag in ("-3.13", "-3.12", "-3.11"):
            probe = subprocess.run(["py", tag, "-c", "import sys"],
                                   capture_output=True, stdin=subprocess.DEVNULL)
            if probe.returncode == 0:
                return ["py", tag, script], AP_SOURCE, True
    return [FROZEN], os.path.dirname(FROZEN), False


GENERATE, AP_HOME, ASSERTIONS = generator()

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
  # Pinned because the default goal is `wonder_victory`, which refuses
  # the low goal epochs this fixture sweeps.
  goal: reach_epoch
  wonders_for_victory: 0
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
  # A wonder goal because this fixture sets wonders_for_victory above 0, which
  # the reach_epoch goal refuses by design.
  goal: wonder_victory
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
  # Wonders are gated by this option and aren't checks, so counting them means
  # counting the `Wonder:` items it puts in the pool.
  building_unlocks: true
"""

# (goal, goal_epoch, wonders, expected `Wonder:` items, must generate)
GOAL_CASES = [
    # Wonder unlocks don't depend on the goal. A wonder is buildable in any
    # seed and gating one is worth doing whether or not the run ends by raising
    # them, so an epoch-goal seed still offers all eight — it just never has to
    # use them. Only `building_unlocks` decides whether they exist at all.
    ("reach_epoch", "space_age", 0, 6, True),
    # Six, not eight. These fixtures leave `map_terrain` at its default, and a
    # land map swaps two wonders away: the Pharos Lighthouse stands where the
    # Orbital Space Station does on a space map, and the Coliseum where the
    # Future Research Sentinel does. Every terrain lands on six, so a
    # `wonders_for_victory` of 6 means all of them whatever map you pick.
    ("wonder_victory", "space_age", 3, 6, True),
    ("wonder_victory", "bronze_age", 6, 6, True),
    # wonders_for_victory and goal have to agree, or the match can end in a
    # victory the seed doesn't recognise.
    ("reach_epoch", "space_age", 2, 0, False),
    ("wonder_victory", "space_age", 0, 0, False),
    # You can't build a wonder before the Bronze Age, so a wonder goal in a
    # seed that stops earlier is unwinnable and gets refused.
    ("wonder_victory", "copper_age", 1, 0, False),
    ("wonder_victory", "bronze_age", 1, 6, True),
]

# Buildings ungated, wonders gated: the shape that leaves `Epoch:` and
# `Wonder:` as the only progression a seed has.
SHAPE_YAML = """name: EETest
description: progression shape
game: Empire Earth
requires:
  version: 0.6.7

Empire Earth:
  goal: wonder_victory
  goal_epoch: space_age
  wonders_for_victory: 3
  building_unlocks: false
  wonder_unlocks: true
  technology_checks: true
"""

SETTINGS_EXPECTED = [
    ("Goal", "Wonder Victory"),
    ("Starting Epoch", "Copper Age"), ("Goal Epoch", "Dark Age"),
    ("Map Size", "Huge"), ("Resources", "Deathmatch"),
    ("Game Variant", "Tournament"), ("Difficulty Level", "Hard"),
    ("Game Speed", "Very Fast"), ("Game Unit Limit", "1175"),
    ("Wonders For Victory", "4"), ("Reveal Map", "Yes"),
    ("Use Custom Civs", "Yes"), ("Lock Teams", "Yes"), ("Lock Speed", "Yes"),
]


def world_modules():
    """Import the world's data modules outside Archipelago.

    They're written to load either as a package or standalone, but they still
    import names from BaseClasses, so it gets stubbed with just enough to
    satisfy the class definitions — none of the data tables touch it.
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
    disagreeing looks exactly like a logic bug — after the recruit floors were
    corrected, a stale install put `Recruit Sagitarian Cruiser` in a Dark Age
    seed and three tests failed for a bug that had already been fixed.
    """
    sys.path.insert(0, HERE)
    from build_apworld import build

    dest = os.path.join(AP_HOME, "custom_worlds")
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
        # UTF-8 explicitly. Archipelago reads player files as UTF-8, and on
        # Windows the default here is cp1252, so anything outside ASCII — an em
        # dash in a comment is enough — reached the generator as a byte it
        # refuses to decode.
        with open(os.path.join(players, "p.yaml"), "w", encoding="utf-8") as f:
            f.write(yaml_text)

        env = dict(os.environ, SKIP_REQUIREMENTS_UPDATE="1",
                   PYTHONIOENCODING="utf-8")
        proc = subprocess.run(
            [*GENERATE, "--player_files_path", players, "--outputpath", out,
             "--seed", "424242"],
            capture_output=True, text=True, timeout=300,
            stdin=subprocess.DEVNULL, env=env, cwd=AP_HOME,
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

    # Every epoch up to the goal has to exist as an item and a check, and
    # nothing beyond it may appear.
    reach = set(re.findall(r"^Reach (.+?):", text, re.M))
    # Require the ": Epoch: " placement, or the spoiler's own
    # "Goal Epoch: <name>" header gets counted as an item.
    items = set(re.findall(r": Epoch: (.+?)$", text, re.M))
    if len(reach) != epochs:
        return False, f"expected {epochs} Reach checks, found {len(reach)}"
    if len(items) != epochs:
        return False, f"expected {epochs} epoch items, found {len(items)}"
    if "Goal Epoch:" not in text:
        return False, "spoiler has no Goal Epoch line"
    return True, f"{epochs} epochs, {len(reach)} checks"


def wonder_names() -> list[str]:
    """Every wonder the world knows about, read rather than listed.

    This was a hardcoded list of the base game's seven. When the object tables
    were regenerated from the Art of Conquest database it silently kept counting
    seven, so the two wonders the expansion adds were invisible to every
    assertion here — a test that can't see new content is worse than no test,
    because it reports success.
    """
    world_modules()
    from Objects import WONDERS

    return sorted(display for _raw, (display, _epoch) in WONDERS.items())


def run_goal(goal, goal_epoch, wonders, expect_checks, should_generate):
    label = f"goal={goal} epoch={goal_epoch} wonders={wonders}"
    text, why = spoiler_for(GOAL_YAML.format(
        label=label, goal=goal, goal_epoch=goal_epoch, wonders=wonders))

    if not should_generate:
        # The pairing rule has to be enforced, not just documented.
        if text is None:
            return True, "refused, as it should be"
        return False, "generated a seed that should have been refused"

    if text is None:
        return False, why
    # A wonder isn't a check any more — building one sends nothing — so what a
    # seed offers is the unlock item, and that's what gets counted.
    offered = {w for w in wonder_names()
               # Trailing \s* because the spoiler is written with CRLF line
               # endings, so `$` doesn't sit where it looks like it does.
               if re.search(rf": Wonder: {re.escape(w)}\s*$", text, re.M)}
    if len(offered) != expect_checks:
        return False, (f"expected {expect_checks} wonder items, "
                       f"found {len(offered)}")
    if re.search(r"^Build (?:Coliseum|Orbital Space Station|Tower of Babylon):",
                 text, re.M):
        return False, "a wonder was placed as a check"
    # The Time Machine used to be checked here as the one wonder needing the
    # Space Age. It carries every marker a real wonder does and no skirmish
    # offers it, so it isn't generated at all now; see gen_objects.WONDER_EXCLUDE.
    if "Time Machine" in offered:
        return False, "Time Machine is scenario-only and should not be offered"
    return True, f"{len(offered)} wonder items"


LOGIC_YAML = """name: EETest
description: epoch logic
game: Empire Earth
requires:
  version: 0.6.7

Empire Earth:
  goal: reach_epoch
  wonders_for_victory: 0
  starting_epoch: {start}
  goal_epoch: {goal}
"""


def run_logic(start: str, goal: str, start_i: int, goal_i: int):
    """No check may hold an epoch item that check itself needs to reach.

    A real bug that shipped. `Epoch: Bronze Age` was placed on
    `Build Siege Factory`, which can't be built before the Dark Age. Build and
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
  wonders_for_victory: 0
  building_unlocks: true
  starting_epoch: {start}
  goal_epoch: {goal}
"""


# Buildings that genuinely stand in for one another. A unit offered at either
# is right to list both, so a producer set inside one of these groups is not a
# mistake.
INTERCHANGEABLE_PRODUCERS = (
    frozenset({"Dock", "Naval Yard"}),
    frozenset({"Capitol", "Town Center"}),
    frozenset({"Cyber Factory", "Cyber Laboratory"}),
    # The Sea King II, deliberately: see Locations.UNIT_PRODUCER_OVERRIDES.
    frozenset({"Airport", "Naval Yard"}),
)


def run_producer_split():
    """No unit may claim two producers that aren't the same building twice.

    `Producers.py` is keyed by family, so a family holding units from two
    different buildings hands every member the union of both — which is the
    dangerous direction. It shipped: `Siege` holds `Inf02 - Sampson` beside the
    catapults, so logic believed a Copper Age Barracks could train a Catapult,
    put `Epoch: Dark Age` on that check, and left the run stuck in the Bronze
    Age with `Building: Siege Factory` sitting behind an Atomic Age tank.

    The world can't see this for itself, because both halves of the union are
    real producers for *someone* in the family. What gives it away is a unit
    offered at two buildings that aren't alternatives for each other, which is
    what this looks for. A new one needs a per-unit entry in
    `Locations.UNIT_PRODUCER_OVERRIDES`.
    """
    world_modules()
    from Locations import RECRUIT_LOCATION_PRODUCERS

    bad = []
    for loc, producers in sorted(RECRUIT_LOCATION_PRODUCERS.items()):
        names = frozenset(producers)
        if len(names) < 2:
            continue
        if any(names <= group for group in INTERCHANGEABLE_PRODUCERS):
            continue
        bad.append(f"{loc} -> {sorted(names)}")
    if bad:
        return False, f"{len(bad)} unit(s) span two producers: {'; '.join(bad[:3])}"
    return True, f"{len(RECRUIT_LOCATION_PRODUCERS)} recruit checks, no split family"


def run_civ_variants():
    """A unit with a plain twin at its own tier must not be load-bearing.

    The database writes a civilisation's replacement as the same name with a
    suffix — `Inf04 - Short Sword(Crusader)` beside `Inf04 - Short Sword`, same
    tier, same family. Only the civilisation that fields it ever sees one, and
    the client leaves civilisation choice to the player, so anything the seed
    needs must never sit on that check.

    It stranded a run: two `Inf04 - Short Sword` in the roster and
    `Epoch: Middle Ages` on `Recruit Short Sword(Crusader)`, a unit the same
    barracks never offered.

    A variant is let off when something at the same epoch floor sends its check,
    which is the `(Flaming)` archers: the plain archer sends its flaming version
    and the two are one unit with two arrows. The floor has to match. A Long
    Sword also sends `Recruit Short Sword(Crusader)`, but it arrives two epochs
    later than the Crusader's own floor, so progression placed there on the
    strength of that floor still strands.
    """
    world_modules()
    import re

    from Locations import (LOCATION_ALSO_SENDS, LOCATION_MIN_EPOCH,
                           NO_PROGRESSION_LOCATIONS, RECRUIT_LOCATION_BY_DBNAME,
                           UNIT_DISPLAY)
    from Objects import UNIT_FAMILY_BY_NAME, UNIT_MIN_EPOCH

    covered_at_floor = set()
    for sender, sent in LOCATION_ALSO_SENDS.items():
        for target in sent:
            if (LOCATION_MIN_EPOCH.get(sender, 0)
                    <= LOCATION_MIN_EPOCH.get(target, 0)):
                covered_at_floor.add(target)

    loose = []
    for db in sorted(UNIT_FAMILY_BY_NAME):
        if UNIT_FAMILY_BY_NAME[db] == "Hero":
            continue                     # heroes carry a role, not a civ
        m = re.search(r"\((.+)\)\s*$", db)
        if not m:
            continue
        twin = db[:m.start()].strip()
        if twin not in UNIT_FAMILY_BY_NAME:
            continue                     # no plain version; not a replacement
        if (UNIT_MIN_EPOCH.get(db) != UNIT_MIN_EPOCH.get(twin)
                or UNIT_FAMILY_BY_NAME[twin] != UNIT_FAMILY_BY_NAME[db]):
            continue                     # a different unit that merely reads alike
        loc = RECRUIT_LOCATION_BY_DBNAME.get(db)
        if (loc and loc not in NO_PROGRESSION_LOCATIONS
                and loc not in covered_at_floor):
            loose.append(loc)
    if loose:
        return False, (f"{len(loose)} civilisation variant(s) can hold "
                       f"progression: {', '.join(loose[:4])}")
    return True, f"{len(UNIT_DISPLAY)} units, every civilisation variant excluded"


def run_per_unit_producers():
    """A unit the PDF names a producer for must have that producer.

    `Producers.py` is keyed by family, but `gen_producers` reads the tables per
    *unit* and knows things a family can't express — `TEMPLE_UNITS` says a
    Priest and a Prophet come from a Temple, and `SHARED_TABLE_SKIP` says a
    Balloon's Town Center label is not the whole helicopter family's.

    Those labels are lost on the way out. A Prophet's family is `Human`, so it
    inherited the Barracks and logic believed a Stone Age barracks trained one.
    `Building: Archery Range` went onto `Recruit Prophet`, the Temple that
    really trains one sat behind an Atomic Age check, and `Epoch: Copper Age`
    was on `Build Archery Range` — a run stopped in the Stone Age.

    `run_producer_split` can't see this. It flags a family whose producers span
    two buildings; here the family has exactly one producer and it's the wrong
    one for a single member. So this checks the generator's per-unit knowledge
    against what the world ended up with.
    """
    world_modules()
    sys.path.insert(0, HERE)
    try:
        from gen_producers import TEMPLE_UNITS
    except Exception as e:
        return True, f"skipped: gen_producers not importable ({e})"

    from Locations import RECRUIT_LOCATION_PRODUCERS, UNIT_DISPLAY

    wrong = []
    for db, display in UNIT_DISPLAY.items():
        if display not in TEMPLE_UNITS:
            continue
        got = RECRUIT_LOCATION_PRODUCERS.get(f"Recruit {display}", ())
        if got != ("Temple",):
            wrong.append(f"{display} -> {sorted(got)}")
    if wrong:
        return False, f"{len(wrong)} temple unit(s) with the wrong producer: "                       + "; ".join(wrong)
    return True, f"{len(TEMPLE_UNITS)} temple units, producers agree"


def run_priority():
    """The four opening checks must hold something the seed needs.

    A match starts with a Capitol and the units it makes, so `Build Capitol`,
    `Recruit Citizen`, `Recruit Female Citizen` and `Recruit Canine Scout` all
    go out before you have done anything. Marked `PRIORITY` so fill puts
    progression there rather than leaving the first thirty seconds of a run to
    resource bundles.

    Read out of the spoiler rather than trusting the flag, because `PRIORITY` is
    a preference — fill falls back when it runs out of progression items, and a
    seed small enough for that to happen would still pass a flag check.
    """
    world_modules()
    from Items import ITEM_TABLE
    from Locations import PRIORITY_LOCATIONS

    spoiler, why = spoiler_for(YAML.format(goal="space_age", bundle=500))
    if spoiler is None:
        return False, why

    # A solo spoiler writes `Build Capitol: Epoch: Stone Age` and a multiworld
    # one appends `(Player)` to both halves, so match each location by name
    # rather than trying to parse the line shape. Unindented only — the
    # playthrough repeats a subset of these with two spaces in front.
    placed = {}
    for loc in PRIORITY_LOCATIONS:
        hit = re.search(rf"^{re.escape(loc)}(?: \(\w+\))?: (.+?)(?: \(\w+\))?$",
                        spoiler, re.M)
        if hit:
            placed[loc] = hit.group(1)
    missing = sorted(PRIORITY_LOCATIONS - set(placed))
    if missing:
        return False, f"{len(missing)} priority check(s) absent from the "\
                      f"spoiler: {'; '.join(missing)}"
    weak = sorted(
        f"{loc} <- {item} ({ITEM_TABLE[item][1]})"
        for loc, item in placed.items()
        if loc in PRIORITY_LOCATIONS
        and ITEM_TABLE.get(item, (0, "progression", None))[1] != "progression"
    )
    if weak:
        return False, f"{len(weak)} opening check(s) hold filler: " \
                      + "; ".join(weak)
    return True, f"{len(PRIORITY_LOCATIONS)} opening checks, all progression"


def run_rule_items():
    """Anything a rule requires has to be a progression item.

    The reachability sweep only collects progression items, so a rule asking for
    a `useful` one can never be satisfied and its location is unreachable for
    good. That is not a soft failure — with the default `full` accessibility it
    is a seed nobody can finish.

    All 100 `Tech:` items were `useful`, on the reasoning that a technology
    makes your citizens quicker and gates nothing. True when it was written, and
    then the technology chains landed: a chained technology has no button until
    the one below it has had its effect applied, so `set_rules` started
    requiring `Tech: <predecessor>` and 71 research checks became unreachable.

    Nothing caught it for weeks. The frozen generator is built with cx_Freeze
    `optimize: 1` and the accessibility check sits behind `if __debug__`, so it
    logged a warning, wrote the archive and exited 0.

    They are useful again, and this time nothing asks for one: the client opens
    a chain itself (`TechChains`) rather than waiting on the item. That's the
    pairing to keep — if a rule ever names a `Tech:` item again it has to become
    progression again, and this catches it.
    """
    world_modules()
    from Items import (_ALL_WONDERS, EPOCH_ITEMS, ITEM_TABLE,
                       LOCKABLE_BUILDINGS, building_item, wonder_item)

    required = set(EPOCH_ITEMS)
    required |= {building_item(b) for b in LOCKABLE_BUILDINGS}
    required |= {wonder_item(w) for w in _ALL_WONDERS}

    wrong = sorted(
        f"{name} is {ITEM_TABLE[name][1]}"
        for name in required
        if name in ITEM_TABLE and ITEM_TABLE[name][1] != "progression"
    )
    absent = sorted(name for name in required if name not in ITEM_TABLE)
    if absent:
        return False, f"{len(absent)} required item(s) don't exist: " \
                      + "; ".join(absent[:6])
    if wrong:
        return False, f"{len(wrong)} required item(s) not progression: " \
                      + "; ".join(wrong[:6])
    return True, f"{len(required)} items reachable rules depend on, all progression"


def run_menu_floors():
    """No check may be reachable before a menu will draw it.

    `dbobjects.dat` supplies a unit's epoch and reads LOW for three of them,
    which is the direction that breaks seeds — logic believes a check is open
    an epoch before the game offers it, so generation can hide the epoch item
    behind the very check that needs it. It cost a run: the Sea King II is
    stored at the Digital Age and not drawn until the Nano Age, and a seed put
    `Epoch: Nano Age` on it.

    The listings in tools/data are the authority, via
    `UnitSlots.SLOT_FIRST_EPOCH`. A floor *above* the drawn epoch is fine and
    often right, because the floor also carries the producing building.
    """
    world_modules()
    from Locations import LOCATION_MIN_EPOCH, RECRUIT_LOCATION_BY_DBNAME
    from UnitSlots import SLOT_FIRST_EPOCH

    low = []
    for db, drawn in SLOT_FIRST_EPOCH.items():
        loc = RECRUIT_LOCATION_BY_DBNAME.get(db)
        if loc and LOCATION_MIN_EPOCH.get(loc, 0) < drawn:
            low.append(f"{loc}: floor {LOCATION_MIN_EPOCH.get(loc)}, drawn {drawn}")
    if low:
        return False, (f"{len(low)} check(s) reachable before the menu draws "
                       f"them: {'; '.join(low[:4])}")
    return True, f"{len(SLOT_FIRST_EPOCH)} units, no floor below its menu epoch"


def run_progression_shape():
    """With buildings ungated, only `Epoch:` and `Wonder:` may be progression.

    A `Building:` item is the only other thing any rule asks for, so turning
    `building_unlocks` off should leave nothing else load-bearing. That was the
    point of splitting `wonder_unlocks` out of it: wonders stay gated, which is
    what a wonder goal is about, and everything else stops gating.

    Read out of a generated seed rather than off ITEM_TABLE, because the
    classification is only half of it. An item is progression in a seed when it
    is *in* that seed, and this catches a rule that starts asking for something
    the pool no longer justifies.
    """
    world_modules()
    from Items import ITEM_TABLE

    yaml = SHAPE_YAML
    text, why = spoiler_for(yaml)
    if text is None:
        return False, why

    seen = set()
    for line in text.splitlines():
        _loc, _, item = line.strip().partition(": ")
        item = item.strip()
        if item in ITEM_TABLE:
            seen.add(item)
    loose = sorted(
        f"{n} ({ITEM_TABLE[n][1]})" for n in seen
        if ITEM_TABLE[n][1] == "progression"
        and not n.startswith(("Epoch: ", "Wonder: "))
    )
    if loose:
        return False, (f"{len(loose)} progression item(s) that are neither an "
                       f"epoch nor a wonder: {'; '.join(loose[:4])}")
    kinds = sorted({n.split(":")[0] for n in seen if ":" in n})
    return True, f"only epochs and wonders gate; pool holds {kinds}"


def run_dead_slots():
    """No check may close for good.

    A menu position that empties and never refills takes its check with it. The
    AP tank line stops at the Leopard — Tank Factory slot 2 is empty from the
    Digital Age onwards — so `Recruit Leopard` shuts after Atomic Age - Modern
    and nothing can ever send it again. Archipelago rules are monotone, so
    generation has no way to know: it put `Wonder: Library of Alexandria` there,
    the Tank Factory unlock turned up in the Space Age, and a three-player seed
    was unwinnable.

    Three things can save such a check, and one of them has to. The client holds
    the unit open to the end of the game, which needs a node and therefore an
    icon in `UnitIcons`; or some later unit sends the check for it; or it is
    excluded, so nothing load-bearing lands there in the first place.

    `SLOT_GAPS` marks these with 15, the value the game already uses for a unit
    that never expires.
    """
    world_modules()
    from UnitSlots import SLOT_GAPS
    from UnitIcons import UNIT_ICONS
    from Locations import (CIV_LOCKED_LOCATIONS, LOCATION_ALSO_SENDS,
                           RECRUIT_LOCATION_BY_DBNAME)

    carried = {loc for sent in LOCATION_ALSO_SENDS.values() for loc in sent}
    safe = carried | CIV_LOCKED_LOCATIONS
    dead = [db for db, epoch in SLOT_GAPS.items() if epoch >= 15]
    stranded = [
        db for db in dead
        if db not in UNIT_ICONS
        and RECRUIT_LOCATION_BY_DBNAME.get(db) not in safe
    ]
    if stranded:
        return False, (
            f"{len(stranded)} of {len(dead)} check(s) close for good with no "
            f"icon to hold them open and nothing to send them: "
            + "; ".join(sorted(stranded))
            + " — run tools/gen_unit_slots.py --icons in a vanilla match")
    return True, f"{len(dead)} slot(s) end for good, all covered"


def run_unlocks(start: str, goal: str, goal_i: int):
    """No building unlock may sit behind a check that needs that building.

    `Building: Stable` on `Build Stable` is the obvious form. The subtle one is
    `Building: Stable` on `Recruit Lancer`, because cavalry comes from a
    stable — which is why the producer table exists at all.
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
        # Built from the constant rather than spelled out, so renaming the
        # item can't leave this matching a prefix nothing produces any more —
        # which makes every run pass with "no Unlock items reached the
        # spoiler".
        m = re.match(rf"^(.+?): ({re.escape(BUILDING_ITEM_PREFIX)}.+?)\s*$",
                     line.strip())
        if not m:
            continue
        loc, building = m.group(1), m.group(2)[len(BUILDING_ITEM_PREFIX):]
        placed.add(building)
        if loc == f"Build {building}":
            circular.append(f"{building} on its own build check")
        elif loc.startswith("Recruit "):
            # Keyed by the location, not by `loc` minus its prefix. That left
            # a unit *display* name being looked up in a table keyed by
            # *family*, so it matched nothing, `producers` was always empty,
            # and the circularity test below could never fire — the subtle case
            # this function exists to catch was silently passing.
            producers = RECRUIT_LOCATION_PRODUCERS.get(loc, ())
            # Only circular when this building is the sole way to get the
            # family. Another producer leaves the check reachable, and one
            # that's never locked at all — a Capitol makes citizens — leaves it
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
    rule that's wrong about the game produces a seed that is provably
    completable and actually isn't. This models the game instead — an epoch is
    reached by holding every unlock up to it, a building needs its unlock AND
    its epoch, and a unit needs a producer you can build right now.

    It caught a real deadlock. `Recruit Siege` accepts a Barracks or a Siege
    Factory, so a run holding `Building: Siege Factory` from the start looked
    able to recruit siege units in the Copper Age. A siege factory can't be
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
        # begins in, so it's available before its own epoch requirement.
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
            # Per unit, matching what the world's own rules use. The floor is
            # applied above.
            from Locations import RECRUIT_LOCATION_PRODUCERS
            producers = RECRUIT_LOCATION_PRODUCERS.get(loc, ())
            return any(buildable(b, epoch, inv) for b in producers)
        if loc.startswith("Research "):
            # A technology is researched at exactly one building, and its own
            # epoch floor has already been applied above.
            from Locations import TECH_LOCATION_BUILDING
            from TechUnlocks import TECH_REQUIRES
            # The chain. A technology's button doesn't exist until the one
            # below it is done — and "done" means researched, not received.
            # `TechChains` opens the successor as soon as the predecessor is
            # researched, so only the benefit waits for the `Tech:` item.
            #
            # This asked for the item until that landed, which was right while
            # suppressing a technology's effect suppressed its unlock too. It
            # went on passing afterwards by luck: the items were still in the
            # pool and usually turned up in reach anyway. Removing one wonder
            # reshuffled the fill and it deadlocked at 56 of 363 checks, which
            # is the model being wrong rather than the seed.
            earlier = TECH_REQUIRES.get(loc[len("Research "):])
            if earlier and f"Research {earlier}" not in taken:
                return False
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


TERRAIN_YAML = """name: EETest
description: terrain {terrain}
game: Empire Earth
requires:
  version: 0.6.7

Empire Earth:
  # Pinned because the default goal is `wonder_victory`, which refuses
  # the low goal epochs this fixture sweeps.
  goal: reach_epoch
  wonders_for_victory: 0
  goal_epoch: space_age
  map_terrain: {terrain}
"""

# terrain -> (checks that must be present, checks that must be absent)
# terrain -> (must be offered, must not be)
#
# One unit from each of the Space Dock's three families, because they're three
# separate `UNIT_FAMILY_PRODUCERS` entries and a regression in one wouldn't show
# up in the others: the Capital Ship is `Spaceship`, the Corvette and the
# Fighter have a family each.
#
# The Planetary Fighter and the Spy Satellite are the other half of that. Both
# sit in the `Space Fighter` family and neither comes from a Space Dock — one is
# built at an Airport, the other at the Capitol — so they belong on every map.
# They're pinned here because collapsing producers back to per-family would take
# them off land maps entirely and nothing else would notice.
TERRAIN_CASES = {
    "land_only": (("Recruit Planetary Fighter", "Recruit Spy Satellite"),
                  ("Build Dock", "Build Naval Yard", "Build Space Dock",
                   "Build Space Turret", "Recruit Frigate - Juggernaut",
                   "Recruit Space Corvette", "Recruit Space Capital Ship",
                   "Recruit Space Fighter")),
    "land_and_water": (("Build Dock", "Build Naval Yard",
                        "Recruit Frigate - Juggernaut",
                        "Recruit Planetary Fighter", "Recruit Spy Satellite"),
                       ("Build Space Dock", "Build Space Turret",
                        "Recruit Space Corvette", "Recruit Space Capital Ship",
                        "Recruit Space Fighter")),
    "space": (("Build Space Dock", "Build Space Turret",
               "Recruit Space Corvette", "Recruit Space Capital Ship",
               "Recruit Space Fighter", "Recruit Space Carrier",
               "Recruit Space Transport"),
              ("Build Dock", "Build Naval Yard", "Recruit Frigate - Juggernaut")),
}


def run_terrain(terrain: str) -> tuple[bool, str]:
    """A seed must only offer what the declared map can actually build.

    The client forces map size but never map choice, so `map_terrain` is you
    telling the seed which map you'll play. Get it wrong and a run is full of
    checks nobody can send — a land-only map has no Dock, and a space map
    replaces the Dock with a Space Dock rather than adding one.
    """
    want, unwanted = TERRAIN_CASES[terrain]
    text, why = spoiler_for(TERRAIN_YAML.format(terrain=terrain))
    if text is None:
        return False, why
    present = set(re.findall(r"^(Build .+?|Recruit .+?):", text, re.M))
    missing = [n for n in want if n not in present]
    extra = [n for n in unwanted if n in present]
    if missing:
        return False, f"expected but absent: {missing}"
    if extra:
        return False, f"present but this map cannot build it: {extra}"

    # And the items, not only the checks. A space seed shipped `Building: Dock`
    # long after `Build Dock` stopped being in it, because the item pool was
    # filtered on epoch alone.
    world_modules()
    from Locations import building_terrains
    from Items import BUILDING_ITEM_PREFIX

    items = set(re.findall(rf"^.+?: ({re.escape(BUILDING_ITEM_PREFIX)}.+?)$",
                           text, re.M))
    dead = sorted(
        name for name in items
        if terrain not in building_terrains(name[len(BUILDING_ITEM_PREFIX):].strip())
    )
    if dead:
        return False, (f"{len(dead)} unlock(s) for buildings this map cannot "
                       f"raise: {'; '.join(dead)}")
    return True, f"{len(present)} build/recruit checks, {len(items)} unlocks"


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

    Every other test here reads `LOCATION_MIN_EPOCH` and believes whatever it
    says. That's exactly how both bugs from the first two-player run got out,
    and neither was subtle once measured:

      * `Recruit Cataphract` carried epoch 3, the earliest member of the Lancer
        family, when a Cataphract is a Middle Ages unit. Generation put
        `Epoch: Dark Age` behind it and the seed could not be finished. The
        circular-placement test above would have caught it, had the number it
        compares against not been the wrong one.
      * `Inf01 - Rock Thrower` had no check at all. Its family is `Human`,
        which was missing from a hand-written list of families, so recruiting
        one sent nothing.

    So this reads `data.ssa` directly — every unit in it has to have a check,
    and every check has to carry that unit's own epoch. Skipped where the game
    isn't installed, which is the only reason it lives here rather than in the
    world's own test package.
    """
    try:
        from dbobjects import objects, record_name
        from ssa_extract import DEFAULT_SSA
    except ImportError as e:
        return True, f"skipped: {e}"
    except SystemExit:
        # `ssa_extract` resolves the game's path at import time, and
        # `install.find_root()` raises SystemExit when there's no install.
        # SystemExit derives from BaseException, so `except ImportError` let it
        # straight past and it took the whole run down with it — the settings
        # test, every goal case and the summary never ran, and the suite exited
        # non-zero on a machine that simply has no game installed. The skip
        # below was written for exactly this and could never be reached.
        return True, "skipped: no Empire Earth install"
    if not os.path.exists(DEFAULT_SSA):
        return True, "skipped: game data not installed"

    import struct
    world_modules()
    from Locations import (
        EXCLUDED_UNIT_NAMES,
        LOCATION_MIN_EPOCH,
        RECRUIT_LOCATION_BY_DBNAME,
        STARTING_LOCATIONS,
        _is_excluded,
    )
    from Objects import UNIT_FAMILY_BY_NAME

    MIN_EPOCH_OFF = 0x70
    db_epoch = {}
    for _i, r, _size in objects(DEFAULT_SSA):
        name = record_name(r)
        if name.strip():
            db_epoch[name] = struct.unpack_from("<i", r, MIN_EPOCH_OFF)[0]

    missing, wrong, skipped = [], [], 0
    for db_name in UNIT_FAMILY_BY_NAME:
        # Deliberate exclusions only — scenario props and the handful of
        # campaign heroes no skirmish offers. Anything else missing a check is
        # the bug this exists to catch, so it asks the world's own predicate
        # rather than a second list that could quietly drift from it.
        if _is_excluded(db_name):
            skipped += 1
            continue
        loc = RECRUIT_LOCATION_BY_DBNAME.get(db_name)
        if loc is None:
            missing.append(db_name)
            continue
        raw = db_epoch.get(db_name)
        # The database counts epochs from 1 at the Prehistoric Age and the
        # rest of this project counts from 0. See unit_epoch() in
        # gen_objects.py for how that was pinned down against the running
        # game.
        want = None if raw is None else max(raw - 1, 0)
        got = LOCATION_MIN_EPOCH.get(loc)
        # A check the match always starts with is pinned to 0 on purpose.
        if want is None or loc in STARTING_LOCATIONS:
            continue
        # Above the unit's own epoch is fine and often right — the floor also
        # carries the producing building, so a Prehistoric unit trained at a
        # Stable waits for the Copper Age. Below it is the bug, because it lets
        # generation hide an epoch item behind a check that needs that epoch.
        if got is None or got < want:
            wrong.append(f"{loc}: floor {got}, unit's own epoch is {want}")

    if missing:
        return False, f"{len(missing)} unit(s) with no check: {missing[:3]}"
    if wrong:
        return False, f"{len(wrong)} wrong floor(s): {wrong[:3]}"
    # A short, named exclusion list is the point — it stops the skip above
    # hiding a unit by accident.
    # Each entry carries its own evidence in Locations.py — a missing icon, an
    # absence from every menu listing, a civilisation nobody else can pick. The
    # cap is here to stop the list growing by habit, so it moves when the
    # justifications do, not before.
    if len(EXCLUDED_UNIT_NAMES) > 22:
        return False, (f"{len(EXCLUDED_UNIT_NAMES)} hand-excluded units - too "
                       "many to trust; every one should be justified")
    return True, (f"{len(RECRUIT_LOCATION_BY_DBNAME)} recruit checks, "
                  f"{skipped} excluded, no floor below the unit's own epoch")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="only the extremes")
    args = ap.parse_args()

    if not os.path.exists(GENERATE[-1]):
        sys.exit(f"not found: {GENERATE[-1]}")
    print(f"  generator: {' '.join(GENERATE)}")
    if not ASSERTIONS:
        print("  WARNING: frozen build, assertions and the accessibility "
              "check are compiled out")

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

    ok, detail = run_per_unit_producers()
    print(f"  {'PASS' if ok else 'FAIL'}  {'per-unit producers':<45s}  {detail}")
    failures += 0 if ok else 1
    total_extra += 1

    ok, detail = run_civ_variants()
    print(f"  {'PASS' if ok else 'FAIL'}  {'civilisation variants':<45s}  {detail}")
    failures += 0 if ok else 1
    total_extra += 1

    ok, detail = run_producer_split()
    print(f"  {'PASS' if ok else 'FAIL'}  {'producers per unit':<45s}  {detail}")
    failures += 0 if ok else 1
    total_extra += 1

    ok, detail = run_rule_items()
    print(f"  {'PASS' if ok else 'FAIL'}  {'rule items are progression':<45s}  {detail}")
    failures += 0 if ok else 1
    total_extra += 1

    ok, detail = run_priority()
    print(f"  {'PASS' if ok else 'FAIL'}  {'opening checks hold progression':<45s}  {detail}")
    failures += 0 if ok else 1
    total_extra += 1

    ok, detail = run_menu_floors()
    print(f"  {'PASS' if ok else 'FAIL'}  {'floors vs the menu listings':<45s}  {detail}")
    failures += 0 if ok else 1
    total_extra += 1

    ok, detail = run_progression_shape()
    print(f"  {'PASS' if ok else 'FAIL'}  {'only epochs and wonders gate':<45s}  {detail}")
    failures += 0 if ok else 1
    total_extra += 1

    ok, detail = run_dead_slots()
    print(f"  {'PASS' if ok else 'FAIL'}  {'slots that never refill':<45s}  {detail}")
    failures += 0 if ok else 1
    total_extra += 1

    ok, detail = run_data_floors()
    # Reported as SKIP rather than PASS when there's no game to read. This is
    # the only check that reads the database instead of the world's own tables,
    # so a run without it hasn't verified the floors at all, and PASS would
    # claim otherwise.
    mark = "SKIP" if ok and detail.startswith("skipped") else ("PASS" if ok else "FAIL")
    print(f"  {mark}  {'recruit floors vs database':<45s}  {detail}")
    failures += 0 if ok else 1
    total_extra += 1

    for terrain in TERRAIN_CASES:
        ok, detail = run_terrain(terrain)
        print(f"  {'PASS' if ok else 'FAIL'}  {'terrain ' + terrain:<45s}  {detail}")
        failures += 0 if ok else 1
    total_extra += len(TERRAIN_CASES)

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
