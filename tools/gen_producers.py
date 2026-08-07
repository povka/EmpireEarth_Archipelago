"""Write Producers.py: which building produces each unit family.

Gating buildings behind Archipelago items needs this. A `Recruit <family>`
check is only reachable if you can build something that produces that family,
so without it generation is free to hide `Building: Stable` behind
`Recruit Lancer` - the same circular placement that once put
`Epoch: Bronze Age` on `Build Siege Factory`.

The relationship is not in dbobjects.dat: building records carry no train list,
and unit records carry no producer, so every apparent reference there is a small
integer that happens to collide with a building index.

It is in `technology_tree.pdf`, which ships with the game. Page 2 lists every
unit in eleven tables, each headed by the category that produces it ("Archers",
"Ships & Subs", "Siege & Artillery (Epochs IV-VI)"), so a unit's producer is
just the heading of the table it is listed in.

Page 1 of the same PDF is a flow chart whose rows are also per-producer, but
its rows are uneven and unmarked - there are no separator rules or row boxes in
the vector layer - so every way of inferring a row boundary put units near the
edges in the wrong row (Spitfire under Siege Factory, Priest under Town
Center). The tables need no such inference.

    py tools\\gen_producers.py [--check]

A family is produced by ANY of its buildings, not all of them, so the rule this
feeds is a disjunction. That makes a spurious producer the dangerous kind of
error - it would tell logic a building you cannot use is good enough - which is
why ambiguous labels are dropped rather than guessed.
"""
import argparse
import collections
import os
import re
import sys
import types

try:
    import fitz
except ImportError:
    sys.exit("PyMuPDF is needed: py -m pip install pymupdf")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "world", "empire_earth"))
_f = types.ModuleType("BaseClasses")
_f.Location = object
sys.modules.setdefault("BaseClasses", _f)
from Objects import UNIT_FAMILIES, UNIT_FAMILY_BY_NAME  # noqa: E402

# Shipped with every edition, GOG and Steam alike.
PDF_CANDIDATES = [
    r"C:\Empire Earth Gold - GOG\technology_tree.pdf",
    r"C:\Empire Earth Gold - Steam\technology_tree.pdf",
    r"C:\Empire Earth Gold\technology_tree.pdf",
    r"C:\Program Files (x86)\GOG Galaxy\Games\Empire Earth Gold\technology_tree.pdf",
]
PDF = next((p for p in PDF_CANDIDATES if os.path.exists(p)), None)

OUT = os.path.join(ROOT, "world", "empire_earth", "Producers.py")

# Table heading -> the building(s) that produce everything listed under it.
# A unit is buildable if you have ANY of them, so these sets are unions.
HEADING_BUILDINGS = {
    # This one table covers two different producers, so it is split below by
    # unit rather than unioned - a Priest does not come from a Town Center.
    #
    # `Settlement` is deliberately NOT here, though it was once. The heading
    # names two buildings and a Settlement is neither: it trains nothing at all
    # until five citizens garrison in it and it becomes a Town Center, which is
    # what BUILDING_PREREQS already models. Listing it claimed citizens and
    # Canine Scouts could be made at one.
    "Town Center / Capitol Units & Temple Units":
        ("Town Center", "Capitol"),
    "Archers": ("Archery Range",),
    "Infantry": ("Barracks",),
    "Cavalry": ("Stable",),
    "Siege & Artillery": ("Siege Factory",),
    "Ships & Subs": ("Dock", "Navy Yard"),
    "Tanks": ("Tank Factory",),
    "Aircraft": ("Airport",),
    "Cybers": ("Cyber Factory", "Cyber Laboratory"),
}


# Families whose members the tables never name, resolved by hand.
#
# `Ship Galley` is every galley and galleon from Copper to Royal. The tables
# list warships by hull name under headings the matcher reads, but these seven
# appear nowhere in them; the flow chart on page 1 puts them with the rest of
# the navy. They are warships and come from the same places every other warship
# does. Written down rather than inferred, because a wrong producer here is the
# dangerous direction: it would tell logic a check is reachable when it is not.
FAMILY_FALLBACK = {
    "Ship Galley": ("Dock", "Navy Yard"),
}


def heading_buildings(heading):
    base = re.sub(r"\s*\(Epochs[^)]*\)", "", heading).strip()
    return HEADING_BUILDINGS.get(base)


def unit_tables(page):
    """Every (heading, [unit name]) table on the page."""
    lines = []
    for blk in page.get_text("dict")["blocks"]:
        for line in blk.get("lines", []):
            text = " ".join(s["text"] for s in line["spans"]).strip()
            if text:
                lines.append((line["bbox"][0], line["bbox"][1], text))

    anchors = sorted(((x, y) for x, y, t in lines if t == "Unit Name"))
    tables = []
    for i, (ax, ay) in enumerate(anchors):
        above = sorted((y, t) for x, y, t in lines
                       if abs(x - ax) < 26 and ay - 14 < y < ay - 1)
        if not above:
            continue
        heading = above[-1][1]
        # The table ends where the next table in the same column begins.
        later = [b for b in anchors[i + 1:] if abs(b[0] - ax) < 3]
        stop = (later[0][1] - 15) if later else 1e9
        names = [t for x, y, t in lines
                 if abs(x - ax) < 3 and ay < y < stop and len(t) > 2]
        tables.append((heading, names))
    return tables


# The chart's "Temple Units", which the shared table heading names separately.
TEMPLE_UNITS = ("Priest", "Prophet")

# `x `-prefixed records are scenario and campaign props, not units a skirmish
# can ever produce. Counting them would let a family look obtainable from a
# building that cannot in fact produce any of its real members.
REAL_NAMES = {n: f for n, f in UNIT_FAMILY_BY_NAME.items()
              if not n.startswith("x ")}


def _squash(s):
    # The tables print "Club Man" where the database says "Clubman".
    return re.sub(r"[^a-z0-9]", "", s.lower())


def families_for(label):
    # The tables footnote some names ("Priest*") and pluralise others.
    for cand in (label, label.rstrip("*").strip(),
                 re.sub(r"s\*?$", "", label).strip()):
        if len(cand) < 4:
            continue
        key = _squash(cand)
        fams = {f for n, f in REAL_NAMES.items() if key and key in _squash(n)}
        if fams:
            return fams
    return set()


def derive():
    doc = fitz.open(PDF)
    producers = collections.defaultdict(set)
    members = collections.defaultdict(list)
    unknown, unmatched, ambiguous = [], [], []

    for page in doc:
        for heading, names in unit_tables(page):
            blds = heading_buildings(heading)
            if blds is None:
                unknown.append((heading, len(names)))
                continue
            for label in names:
                # The one table that names two producers is split by unit.
                here = ("Temple",) if label.rstrip("*") in TEMPLE_UNITS else blds
                fams = families_for(label)
                if not fams:
                    unmatched.append(label)
                elif len(fams) > 1:
                    ambiguous.append((label, sorted(fams)))
                else:
                    fam = fams.pop()
                    producers[fam].update(here)
                    members[fam].append(label)
    return producers, members, unknown, unmatched, ambiguous


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="report without rewriting Producers.py")
    args = ap.parse_args()

    if PDF is None:
        sys.exit("technology_tree.pdf not found; tried:\n  "
                 + "\n  ".join(PDF_CANDIDATES))
    print(f"reading {PDF}")

    producers, members, unknown, unmatched, ambiguous = derive()

    for family, buildings in FAMILY_FALLBACK.items():
        if family in UNIT_FAMILIES and family not in producers:
            producers[family] = set(buildings)
            members[family] = ["(by hand)"]

    for fam in UNIT_FAMILIES:
        blds = producers.get(fam)
        if not blds:
            print(f"   {fam:<26s} -- NO PRODUCER --")
            continue
        print(f"   {fam:<26s} {str(sorted(blds)):<48s} "
              f"{len(members[fam]):>2d} units, e.g. {members[fam][0]}")

    missing = [f for f in UNIT_FAMILIES if f not in producers]
    print(f"\n{len(producers)}/{len(UNIT_FAMILIES)} families mapped")
    if unknown:
        print(f"headings not recognised: {unknown}")
    print(f"{len(unmatched)} labels matched no family (heroes and upgrades), "
          f"{len(ambiguous)} dropped as ambiguous")
    if missing or unknown:
        sys.exit(f"refusing to write: {missing or 'unknown headings'}")

    if args.check:
        print("--check: not written")
        return

    lines = [
        '"""Which building produces each unit family.',
        "",
        "Generated by tools/gen_producers.py from the technology_tree.pdf that",
        "ships with the game; do not edit by hand.",
        "",
        "A family is produced by ANY of the buildings listed for it, so the rule",
        "built from this is a disjunction. Without it, generation could hide a",
        "building unlock behind a check that needs that very building.",
        '"""',
        "",
        "UNIT_FAMILY_PRODUCERS: dict[str, tuple[str, ...]] = {",
    ]
    for fam in UNIT_FAMILIES:
        blds = ", ".join(f'"{b}"' for b in sorted(producers[fam]))
        lines.append(f'    "{fam}": ({blds},),')
    lines += ["}", ""]
    with open(OUT, "w", newline="\n") as f:
        f.write("\n".join(lines))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
