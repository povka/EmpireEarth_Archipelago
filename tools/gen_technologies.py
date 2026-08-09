"""Write Technologies.py: every technology, with its epoch and its building.

Two sources are joined here, because neither alone is enough.

`tools/data/technologies.tsv` carries the name, the building that researches it
and the epoch, taken from the game's wiki. The running game carries the button
texture, which is the only handle the client has for finding a technology's node
in memory — and the node is where research is detected, at `+0x04`.

So run this once with Empire Earth open, in a match. After that the generated
module is committed and generation never needs the game again.

    py tools\gen_technologies.py            # rewrite Technologies.py
    py tools\gen_technologies.py --check    # report without writing

Matching is by name against the texture, constrained to nodes within one epoch
of where the technology belongs. Names too different to trust fuzzy matching on
go in `ALIASES` below rather than getting guessed at.
"""
import difflib
import io
import os
import re
import struct
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "world", "empire_earth"))
_f = types.ModuleType("BaseClasses")


class _IC:
    progression = "p"
    filler = "f"


_f.ItemClassification = _IC
_f.Item = object
_f.Location = object
sys.modules.setdefault("BaseClasses", _f)

from eemem import Proc, find_pids                    # noqa: E402
from Addresses import profile_for, ResourceAccess    # noqa: E402
from Roster import Roster                            # noqa: E402
from Epochs import EpochAccess                       # noqa: E402

TSV = os.path.join(HERE, "data", "technologies.tsv")
OUT = os.path.join(ROOT, "world", "empire_earth", "Technologies.py")

# Wiki name -> the texture stem the game uses, where they differ enough that
# fuzzy matching can't be trusted to get it right.
ALIASES = {
    "Hafted Tools": "hafts",
    "Iron Saw": "saw",
    "Magnetic Resonance Imaging": "mri",
    "Pesticides": "chemical pesticides",
    "Mining Explosives": "explosives",
    "Gas Lamps": "gaslamp",
    "Fine-Edged Tools": "fineflakedtools",
    "Comparative Anatomy": "comparitive anatomy",
    "Wheeled Plow": "wheeled drawn plow",
    "Hammer Drilling Rigs": "hammer drilling rig",
    "Environmental Law": "environmental laws",
    "Self Sufficiency": "self sufficiency movement",
    "Strengthened Concrete": "reinforced concrete",
    "Zero-G Engineer": "zeroengineering",
    "Robotic Farm": "farm",
    "Oracle": "oracle",
}
# Every wall and tower upgrade shares one texture; only the epoch separates them.
WALL_TEXTURE = "upgrade wall and tower"

squash = lambda s: re.sub(r"[^a-z0-9]", "", s.lower())          # noqa: E731


def stem(tex):
    s = tex[4:] if tex.startswith("but_") else tex
    # Some technologies carry a tier-style suffix too. The Space Age Granary
    # tech is `but_farm_15t`, which is why the Farm building looked like it had
    # a node when it has none.
    return re.sub(r"_\d+t?$", "", s)


def main():
    p = Proc(find_pids("EE-AOC.exe")[0][0])
    prof = profile_for("EE-AOC.exe")
    r = Roster(p, prof)
    tree = EpochAccess(p, ResourceAccess(p, prof)).tech_tree()

    nodes = []
    needle = struct.pack("<I", 0x00846150)
    for base, data in p.snapshot(want_image=False, want_private=True,
                                 want_mapped=False):
        off = -1
        while True:
            off = data.find(needle, off + 1)
            if off < 0:
                break
            if off % 4 or off + 0x30 > len(data):
                continue
            if struct.unpack_from("<I", data, off + 0x0C)[0] != tree:
                continue
            addr = base + off
            btn = struct.unpack_from("<I", data, off + 0x10)[0]
            tex = r.read_uwstring(btn + 4) if btn else None
            if tex:
                s = tex.split("\\")[-1].lower()
                s = s[:-4] if s.endswith(".sst") else s
                # The id the effect applier is called with, from the node's
                # state object. Static game data — (epoch+1)*1000 plus an
                # index — so it can be baked in rather than read per match.
                state = struct.unpack_from("<I", data, off + 8)[0]
                tech_id = p.read_u32(state + 0x4C) if state else None
                nodes.append((stem(s), struct.unpack_from("<i", data, off + 0x14)[0],
                              s, tech_id or 0))

    rows = [l.split("\t") for l in io.open(TSV, encoding="utf-8").read().splitlines()
            if l and not l.startswith("#")]

    matched, unmatched, ambiguous = [], [], []
    for name, bld, ep in rows:
        ep = int(ep)
        want = squash(ALIASES.get(name, name))
        if name.startswith("Upgrade to Wall & Tower"):
            want = squash(WALL_TEXTURE)
        # Epoch is a strong signal but not exact — a few nodes sit one out.
        pool = [n for n in nodes if abs(n[1] - ep) <= 1]
        exact = [n for n in pool if squash(n[0]) == want]
        if len(exact) == 1:
            matched.append((name, bld, ep, exact[0][2], exact[0][1], "exact", exact[0][3]))
            continue
        if len(exact) > 1:
            best = [n for n in exact if n[1] == ep]
            if len(best) == 1:
                matched.append((name, bld, ep, best[0][2], best[0][1], "epoch", best[0][3]))
            else:
                ambiguous.append((name, ep, [n[2] for n in exact]))
            continue
        near = difflib.get_close_matches(want, [squash(n[0]) for n in pool],
                                         n=1, cutoff=0.78)
        if near:
            n = next(n for n in pool if squash(n[0]) == near[0])
            matched.append((name, bld, ep, n[2], n[1], "fuzzy", n[3]))
        else:
            unmatched.append((name, bld, ep))

    print(f"{len(rows)} technologies: {len(matched)} matched, "
          f"{len(ambiguous)} ambiguous, {len(unmatched)} unmatched")
    kinds = {}
    for m in matched:
        kinds[m[5]] = kinds.get(m[5], 0) + 1
    print("   by method:", kinds)
    for label, items in (("ambiguous", ambiguous), ("unmatched", unmatched)):
        if items:
            print(f"\n{label}:")
            for row in items:
                print(f"   {row}")
    for n, b, e, tex, nep, k, _i in matched:
        if k == "fuzzy":
            print(f"   fuzzy: {n:<32s} ep{e:<3d} -> {tex} (node ep {nep})")

    if ambiguous or unmatched:
        sys.exit("refusing to write: every technology must resolve to one node")
    if "--check" in sys.argv:
        print("--check: not written")
        return

    lines = [
        '"""Every technology: the epoch it appears in, and where it is researched.',
        "",
        "Generated by tools/gen_technologies.py. Don't edit by hand. The names,",
        "buildings and epochs come from tools/data/technologies.tsv, the button",
        "textures from a running game.",
        "",
        "The texture is how the client finds a technology's node, and `node+0x04`",
        "is the byte the game sets when it has been researched — measured, twice,",
        "by snapshotting every node and researching exactly one thing.",
        "",
        "Only five buildings research anything and the Capitol is never locked, so",
        "a technology's building requirement only bites for the other four.",
        '"""',
        "",
        "# name -> (epoch, building, button texture, node epoch, effect id)",
        "#",
        "# The node epoch is carried because a texture isn't unique. Every wall",
        "# and tower upgrade shares `but_upgrade wall and tower`, and only the",
        "# epoch on the node tells the seven apart — keying lookups on the",
        "# texture alone silently collapsed six of them.",
        "TECHNOLOGIES: dict[str, tuple[int, str, str, int]] = {",
    ]
    for name, bld, ep, tex, nep, _k, tid in sorted(matched, key=lambda m: (m[2], m[0])):
        lines.append(f'    "{name}": ({ep}, "{bld}", "{tex}", {nep}, {tid}),')
    lines += [
        "}",
        "",
        "# The byte a node's own state uses to record that it has been researched.",
        "RESEARCHED_OFFSET = 0x04",
        "",
        "TECH_MIN_EPOCH: dict[str, int] = {",
        "    name: epoch for name, (epoch, _b, _t, _n, _i) in TECHNOLOGIES.items()",
        "}",
        "",
        "TECH_BUILDING: dict[str, str] = {",
        "    name: building for name, (_e, building, _t, _n, _i) in TECHNOLOGIES.items()",
        "}",
        "",
        "# (texture, node epoch) -> name. That pair identifies a node. The",
        "# texture alone isn't unique.",
        "TECH_BY_NODE: dict[tuple[str, int], str] = {",
        "    (texture, node_epoch): name",
        "    for name, (_e, _b, texture, node_epoch, _i) in TECHNOLOGIES.items()",
        "}",
        "",
        "# Every effect id the seed may withhold. Baked in so the client can",
        "# publish it the moment it attaches — waiting for a match to read them",
        "# lost the opening research burst every time.",
        "TECH_EFFECT_IDS: tuple[int, ...] = tuple(sorted(",
        "    effect_id for (_e, _b, _t, _n, effect_id) in TECHNOLOGIES.values()",
        "    if effect_id",
        "))",
        "",
    ]
    with open(OUT, "w", newline="\n") as f:
        f.write("\n".join(lines))
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
