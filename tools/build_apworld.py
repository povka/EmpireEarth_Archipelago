"""Validate world/empire_earth and package it as empire_earth.apworld.

An .apworld is a plain zip of the world package with the package directory as
its top-level folder - nothing about it needs a source checkout of Archipelago
or the launcher.

    python tools/build_apworld.py     # check and build
    python tools/build_apworld.py --check   # validate only

The result is written to the repository root, and that is all it does. Where
Archipelago keeps `custom_worlds` differs by platform, install method and
version, so copying the file there is left to you rather than guessed at - a
build that silently writes an apworld somewhere nothing loads it is worse than
one that hands you the file.

Runs on any platform. The world generates anywhere - `__init__.py` imports the
client lazily, so nothing platform-specific loads during generation - which is
what lets a non-Windows machine build this and host a multiworld.

Nothing is packaged until three checks pass, because a world that fails to
import does not announce itself: Archipelago simply never registers the client
component, and the launcher silently opens its own window instead. That cost an
afternoon once.

    1. every file compiles
    2. every `from .Module import name` names something that module defines
    3. the data modules import for real, with Archipelago's own modules stubbed

Check 3 is the one that earns its keep: it catches a data table changing shape,
such as adding a field to `TECHNOLOGIES` while another module still unpacks the
old arity. What none of them catch is a name used inside a function but never
imported; that only shows up at runtime.
"""

from __future__ import annotations

import argparse
import ast
import os
import sys
import types
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "world", "empire_earth")
PACKAGE = "empire_earth"

# Tests import Archipelago's own modules, so they cannot load inside a frozen
# install; caches are noise.
SKIP_DIRS = {"__pycache__", "test", ".pytest_cache"}
SKIP_EXT = (".pyc", ".pyo")

# Modules that pull in Archipelago itself, and so cannot be imported here.
NEEDS_ARCHIPELAGO = {"__init__", "Client", "Options"}

# `Memory` calls `ctypes.WinDLL` as it loads, which only exists on Windows.
# Skipping it elsewhere is not a gap in the check: generation never imports it
# either, because `__init__` only imports the client inside `launch_client`.
NEEDS_WINDOWS = {"Memory"}


def sources() -> list[str]:
    return sorted(f for f in os.listdir(SRC) if f.endswith(".py"))


def check_compiles() -> list[str]:
    bad = []
    for name in sources():
        path = os.path.join(SRC, name)
        try:
            compile(open(path, encoding="utf-8").read(), path, "exec")
        except SyntaxError as e:
            bad.append(f"{name}: {e}")
    return bad


def check_internal_imports() -> list[str]:
    """Every `from .Module import name` must name something Module defines."""
    trees = {}
    for name in sources():
        path = os.path.join(SRC, name)
        trees[name[:-3]] = ast.parse(open(path, encoding="utf-8").read(), path)

    def defined(tree: ast.Module) -> set[str]:
        out: set[str] = set()
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                out.add(node.name)
            elif isinstance(node, ast.Assign):
                out.update(t.id for t in node.targets if isinstance(t, ast.Name))
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                out.add(node.target.id)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                out.update(a.asname or a.name.split(".")[0] for a in node.names)
            elif isinstance(node, (ast.If, ast.Try)):
                # Data modules import either as a package or standalone, so
                # their real exports live inside a try/except ImportError.
                for inner in ast.walk(node):
                    if isinstance(inner, ast.Assign):
                        out.update(t.id for t in inner.targets
                                   if isinstance(t, ast.Name))
                    elif isinstance(inner, (ast.Import, ast.ImportFrom)):
                        out.update(a.asname or a.name.split(".")[0]
                                   for a in inner.names)
        return out

    have = {mod: defined(tree) for mod, tree in trees.items()}
    bad = []
    for mod, tree in trees.items():
        for node in ast.walk(tree):
            if (isinstance(node, ast.ImportFrom) and node.level == 1
                    and node.module in have):
                bad += [f"{mod}.py: {a.name!r} is not defined in {node.module}.py"
                        for a in node.names if a.name not in have[node.module]]
    return bad


def check_data_modules() -> list[str]:
    """Import the data modules for real, with BaseClasses stubbed.

    This is what notices a table that changed shape. Adding a field to
    `TECHNOLOGIES` while `Locations.py` still unpacked the old arity broke the
    whole world, and nothing said so until the launcher quietly refused to show
    the client.
    """
    stub = types.ModuleType("BaseClasses")

    class _Classification:
        progression = "progression"
        filler = "filler"
        useful = "useful"

    stub.ItemClassification = _Classification
    stub.Item = object
    stub.Location = object
    stub.LocationProgressType = types.SimpleNamespace(EXCLUDED=0, DEFAULT=1)
    stub.Region = object
    stub.Tutorial = object
    sys.modules.setdefault("BaseClasses", stub)
    sys.path.insert(0, SRC)

    bad: list[str] = []
    skipped: list[str] = []
    for name in sources():
        mod = name[:-3]
        if mod in NEEDS_ARCHIPELAGO:
            continue
        if mod in NEEDS_WINDOWS and os.name != "nt":
            skipped.append(mod)
            continue
        try:
            __import__(mod)
        except Exception as e:            # noqa: BLE001 - report anything
            bad.append(f"{name}: {type(e).__name__}: {e}")
    if skipped:
        print(f"   (skipped {', '.join(skipped)}: needs Windows)")
    return bad


def build(target: str) -> tuple[int, int]:
    tmp = target + ".new"
    count = 0
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(SRC):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for name in sorted(files):
                if name.endswith(SKIP_EXT):
                    continue
                path = os.path.join(root, name)
                # Always forward slashes: a zip built on Windows would
                # otherwise carry backslashes in its member names, which is not
                # what the format specifies.
                arc = "/".join([PACKAGE] +
                               os.path.relpath(path, SRC).split(os.sep))
                z.write(path, arc)
                count += 1
    os.replace(tmp, target)
    return count, os.path.getsize(target)


def main():
    ap = argparse.ArgumentParser(
        description="Build empire_earth.apworld into the repository root.")
    ap.add_argument("--check", action="store_true",
                    help="validate without building")
    args = ap.parse_args()

    if not os.path.isdir(SRC):
        raise SystemExit(f"not found: {SRC}")

    for label, problems in (("syntax", check_compiles()),
                            ("imports", check_internal_imports()),
                            ("data modules", check_data_modules())):
        if problems:
            print(f"{label}:")
            for line in problems:
                print(f"   {line}")
            raise SystemExit("not built: fix the above first")
    print(f"checks passed ({len(sources())} modules)")

    if args.check:
        return

    target = os.path.join(ROOT, f"{PACKAGE}.apworld")
    count, size = build(target)
    print(f"{count} files -> {target} ({size:,} bytes)")
    print("Copy it into Archipelago's custom_worlds folder, then restart the "
          "Launcher.")


if __name__ == "__main__":
    main()
