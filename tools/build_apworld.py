"""Validate world/empire_earth and package it as empire_earth.apworld.

    python tools/build_apworld.py            # check and build
    python tools/build_apworld.py --check    # validate only

An .apworld is a zip of the world package with the package directory at the
top. Nothing about it needs an Archipelago checkout or the launcher.

The result goes to the repository root and that is all it does. That's
deliberate — where Archipelago keeps `custom_worlds` differs by platform,
install method and version, and a build that quietly writes an apworld
somewhere nothing loads it is worse than one that hands you the file.

Runs anywhere. `__init__.py` imports the client lazily, so nothing
platform-specific loads during generation, which is what lets a non-Windows
machine build this and host a multiworld.

## What gets checked

Six things, because a world that fails to import doesn't announce itself.
Archipelago just never registers the client component and the launcher opens
its own window instead. That cost an afternoon once.

1. every file compiles
2. every `from .Module import name` names something that module defines
3. the data modules import for real, with Archipelago's own modules stubbed
4. no two checks, and no two items, share an id
5. nothing needs a Python newer than 3.11, the oldest Archipelago supports
6. no name is read that nothing binds

Check 3 catches a table changing shape — adding a field to `TECHNOLOGIES`
while another module still unpacks the old arity. Check 4 exists because id
blocks silently overflow into each other. Check 5 is static only; there is no
3.11 on this machine to run against.

Check 6 closes what used to be an admitted gap: a name used inside a function
and never imported. `__init__.py` can't be imported by check 3, because it
pulls in Archipelago itself, so `LocationProgressType.EXCLUDED` compiled,
passed everything, and died at generation.

All six cover the `test` package too, even though it's deliberately left out of
the packaged apworld. Checking only what ships is how the tests came to import
a name that had been deleted with nothing to say so.
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


def all_sources() -> list[str]:
    """Every .py in the world, including the test package.

    The tests are not shipped in the apworld, but they are still part of the
    world and Archipelago expects them to run. Validating only what gets
    packaged is how `test/__init__.py` came to import a name that had been
    deleted, with nothing to say so.
    """
    out = []
    for root, dirs, files in os.walk(SRC):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        out += [os.path.join(root, f) for f in files if f.endswith(".py")]
    return sorted(out)


def rel(path: str) -> str:
    return os.path.relpath(path, SRC).replace(os.sep, "/")


def check_compiles() -> list[str]:
    bad = []
    for path in all_sources():
        try:
            compile(open(path, encoding="utf-8").read(), path, "exec")
        except SyntaxError as e:
            bad.append(f"{rel(path)}: {e}")
    return bad


# Names added to the standard library after 3.11. Archipelago supports 3.11.9
# up to (not including) 3.14, so anything here builds fine on the interpreter
# it was written on and fails for someone on the oldest supported one.
TOO_NEW = {
    "batched": "itertools.batched is 3.12+",
    "override": "typing.override is 3.12+",
    "TypeAliasType": "typing.TypeAliasType is 3.12+",
    "walk": "pathlib.Path.walk is 3.12+ (os.walk is fine)",
    "binomialvariate": "random.binomialvariate is 3.12+",
    "monitoring": "sys.monitoring is 3.12+",
    "deprecated": "warnings.deprecated is 3.13+",
    "process_cpu_count": "os.process_cpu_count is 3.13+",
    "ReadOnly": "typing.ReadOnly is 3.13+",
}


def check_python_311() -> list[str]:
    """Refuse syntax or stdlib calls that need something newer than 3.11.

    Archipelago runs on 3.11.9 or newer and below 3.14. This machine only has
    3.14, so the world is never actually executed on the oldest version it
    claims to support; this is the next best thing. `feature_version` makes the
    parser reject syntax 3.11 could not read, and the name scan catches the
    more likely mistake of calling something that simply did not exist yet.

    It is a static check, not a 3.11 run: it cannot see a changed signature or
    a behavioural difference.
    """
    bad = []
    for path in all_sources():
        src = open(path, encoding="utf-8").read()
        try:
            tree = ast.parse(src, path, feature_version=(3, 11))
        except SyntaxError as e:
            bad.append(f"{rel(path)}: not valid Python 3.11 syntax: {e}")
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in TOO_NEW:
                bad.append(f"{rel(path)}:{node.lineno}: {TOO_NEW[node.attr]}")
            elif isinstance(node, ast.ImportFrom) and node.module in (
                    "itertools", "typing", "warnings", "random", "os", "sys"):
                bad += [f"{rel(path)}:{node.lineno}: {TOO_NEW[a.name]}"
                        for a in node.names if a.name in TOO_NEW]
    return bad


def check_internal_imports() -> list[str]:
    """Every `from .Module import name` must name something Module defines.

    Covers the test package too, and its `from ..Module import name` form. That
    is not hypothetical tidiness: the tests imported `CACHE_LOCATIONS` from
    Locations long after it was deleted, and because the packaged apworld
    leaves the tests out, every check here passed while the world's own test
    suite could not be imported at all.
    """
    trees = {}
    for path in all_sources():
        dotted = rel(path)[:-3].replace("/", ".")
        trees[dotted] = ast.parse(open(path, encoding="utf-8").read(), path)

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
        # The package this module sits in: "" at the world root, "test" inside
        # the test package. One dot means that package, two means its parent.
        package = mod.rpartition(".")[0]
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or not node.level:
                continue                      # absolute: Archipelago's own
            parts = package.split(".") if package else []
            if node.level - 1 > len(parts):
                bad.append(f"{mod}.py: relative import goes above the world")
                continue
            target = parts[:len(parts) - (node.level - 1)]
            if node.module:
                target = target + node.module.split(".")
            dotted = ".".join(target)
            if dotted not in have:
                continue                      # a package, not a module here
            bad += [f"{mod}.py: {a.name!r} is not defined in {dotted}.py"
                    for a in node.names if a.name not in have[dotted]]
    return bad


def stub_archipelago() -> None:
    """Make the data modules importable outside Archipelago.

    They import names from BaseClasses at module level but no data table
    touches them, so stubs are enough. Every check that imports the world calls
    this, rather than leaning on another check having run first.
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


def check_data_modules() -> list[str]:
    """Import the data modules for real, with BaseClasses stubbed.

    This is what notices a table that changed shape. Adding a field to
    `TECHNOLOGIES` while `Locations.py` still unpacked the old arity broke the
    whole world, and nothing said so until the launcher quietly refused to show
    the client.
    """
    stub_archipelago()

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


def check_ids() -> list[str]:
    """No two checks, and no two items, may share an id.

    Ids are handed out in blocks with a base per kind, so a kind that outgrows
    its block starts issuing ids that already mean something else — and nothing
    complains, it simply resolves to the wrong check. The technology block held
    exactly 100 technologies against 100 slots when this was written.
    """
    stub_archipelago()
    bad = []
    for module, table, what in (("Locations", "LOCATION_NAME_TO_ID", "location"),
                                ("Items", "ITEM_NAME_TO_ID", "item")):
        try:
            ids = getattr(__import__(module), table)
        except (ImportError, AttributeError) as e:
            bad.append(f"{module}.{table}: {e}")
            continue
        seen: dict[int, str] = {}
        for name, value in ids.items():
            if value in seen:
                bad.append(f"{what} id {value}: {seen[value]!r} and {name!r}")
            seen[value] = name
    return bad


def check_undefined_names() -> list[str]:
    """Names read but never bound anywhere that could reach them.

    This is the gap the other checks admit to leaving. `__init__.py` cannot be
    imported here - it pulls in Archipelago itself - so a name used in it and
    never imported compiles, passes every check, and fails at generation:

        location.progress_type = LocationProgressType.EXCLUDED
        NameError: name 'LocationProgressType' is not defined

    It is a scope walk rather than a real type check: collect what each scope
    binds, then flag loads that no enclosing scope, the module, or builtins can
    satisfy. Attributes are not followed, so `Foo.bar` only ever asks about
    `Foo`, which keeps it to the one question it can answer honestly.
    """
    import builtins

    bad: list[str] = []

    def bound_by(node: ast.AST) -> set[str]:
        """Every name this statement binds, wherever it appears in it."""
        out: set[str] = set()
        for sub in ast.walk(node):
            if isinstance(sub, (ast.Import, ast.ImportFrom)):
                out.update(a.asname or a.name.split(".")[0] for a in sub.names)
            elif isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef,
                                  ast.ClassDef)):
                out.add(sub.name)
            elif isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Store):
                out.add(sub.id)
            elif isinstance(sub, ast.arg):
                out.add(sub.arg)
            elif isinstance(sub, ast.ExceptHandler) and sub.name:
                out.add(sub.name)
            elif isinstance(sub, ast.Global):
                out.update(sub.names)
        return out

    for path in all_sources():
        tree = ast.parse(open(path, encoding="utf-8").read(), path)
        module_scope = bound_by(tree) | set(dir(builtins)) | {
            "__file__", "__name__", "__doc__", "__package__",
        }

        def visit(node: ast.AST, scope: set[str]) -> None:
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef,
                                      ast.ClassDef, ast.Lambda)):
                    visit(child, scope | bound_by(child))
                elif isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load):
                    if child.id not in scope:
                        bad.append(f"{rel(path)}:{child.lineno}: "
                                   f"{child.id!r} is not defined or imported")
                else:
                    visit(child, scope)

        visit(tree, module_scope)
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
                            ("data modules", check_data_modules()),
                            ("ids", check_ids()),
                            ("python 3.11", check_python_311()),
                            ("undefined names", check_undefined_names())):
        if problems:
            print(f"{label}:")
            for line in problems:
                print(f"   {line}")
            raise SystemExit("not built: fix the above first")
    print(f"checks passed ({len(all_sources())} modules, including the test package)")

    if args.check:
        return

    target = os.path.join(ROOT, f"{PACKAGE}.apworld")
    count, size = build(target)
    print(f"{count} files -> {target} ({size:,} bytes)")
    print("Copy it into Archipelago's custom_worlds folder, then restart the "
          "Launcher.")


if __name__ == "__main__":
    main()
