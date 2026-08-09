"""Archipelago unit tests for Empire Earth.

The tests live in the `test_*.py` files beside this one, and the shared base is
in `bases.py`. Nothing is defined here on purpose. Archipelago's testing guide
calls defining anything in a world's `test/__init__.py` deprecated, and the
standard runner only discovers files named `test_*.py`, so tests written here
aren't merely untidy — they never run. Everything below used to live here, and
had gone stale enough to fail on import without anything noticing.

These need an Archipelago source checkout
(`python -m pytest worlds/empire_earth`), because a frozen install ships no test
framework. `tools/test_generation.py` covers the same ground against one.
"""
