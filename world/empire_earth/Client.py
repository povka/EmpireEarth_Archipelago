"""Archipelago client for Empire Earth / Art of Conquest.

Attaches to the running game and credits the player's stockpile whenever the
multiworld sends a resource bundle. Item application is idempotent across
reconnects: the index of the last applied item is persisted per seed+slot,
because the server replays the full item list on every connect.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os

import Utils
from CommonClient import (
    ClientCommandProcessor,
    CommonContext,
    get_base_parser,
    gui_enabled,
    logger,
    server_loop,
)
from NetUtils import ClientStatus

from .Addresses import (
    EXE_NAMES,
    OUTCOME_DEFEATED,
    OUTCOME_OFFSET,
    OUTCOME_UNDECIDED,
    RESOURCE_NAMES,
    ResourceAccess,
    profile_for,
)
from .Epochs import EPOCH_NAMES, EpochAccess
from .BuildingGate import BuildingGate
from .Research import ResearchWatch
from .Obsolescence import Obsolescence
from .TechEffects import TechEffects
from .Items import (
    ITEM_ID_TO_BUILDING,
    ITEM_ID_TO_WONDER,
    ITEM_ID_TO_EPOCH,
    ITEM_ID_TO_TECH,
    ITEM_ID_TO_RESOURCE,
    LOCKABLE_BUILDINGS,
)
from .Locations import (
    BUILD_LOCATION_BY_DBNAME,
    LOCATION_NAME_TO_ID,
    LOCATION_ALSO_SENDS,
    RECRUIT_LOCATION_BY_DBNAME,
    TECH_LOCATION_BY_NODE,
    WONDER_BY_DBNAME,
)
from .Technologies import TECHNOLOGIES, TECH_EFFECT_IDS
from .Banner import Banner
from .WinHook import WinHook
from .Diplomacy import Diplomacy
from .MatchSettings import MatchSettings, clamp_unit_limit, describe
from .Roster import Roster
from .Memory import attach

GAME_NAME = "Empire Earth"
POLL_INTERVAL = 0.5


def _state_path(seed: str, slot: str) -> str:
    folder = os.path.join(Utils.user_path("data"), "empire_earth")
    os.makedirs(folder, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in f"{seed}_{slot}")
    return os.path.join(folder, f"{safe}.json")


class EmpireEarthCommandProcessor(ClientCommandProcessor):
    def _cmd_ee(self):
        """Show game attachment status and the current resource stockpile."""
        ctx: EmpireEarthContext = self.ctx
        if not ctx.proc or not ctx.proc.alive:
            self.output("Not attached to Empire Earth.")
            return
        self.output(f"Attached to {ctx.proc.exe} (pid {ctx.proc.pid}).")
        if not ctx.res:
            self.output("No memory profile for this build - run tools/find_resources.py.")
            return
        vals = ctx.res.read_all()
        if vals is None:
            self.output("Resource pointer not resolvable - are you in a match?")
            return
        self.output(
            "  ".join(f"{n}: {v:,.0f}" for n, v in zip(RESOURCE_NAMES, vals))
        )

    def _cmd_grant(self, resource: str = "Food", amount: str = "500"):
        """Debug: add <amount> of <resource> directly, bypassing the multiworld."""
        ctx: EmpireEarthContext = self.ctx
        names = [n.lower() for n in RESOURCE_NAMES]
        if resource.lower() not in names:
            self.output(f"Unknown resource. Pick one of: {', '.join(RESOURCE_NAMES)}")
            return
        if not ctx.res:
            self.output("Not attached / no memory profile.")
            return
        idx = names.index(resource.lower())
        new = ctx.res.add(idx, float(amount))
        if new is None:
            self.output("Write failed - not in a match?")
        else:
            self.output(f"{RESOURCE_NAMES[idx]} is now {new:,.0f}")

    def _cmd_roster(self):
        """Show what you currently own and which checks it satisfies."""
        ctx: EmpireEarthContext = self.ctx
        if not ctx.roster:
            self.output("Not attached / no memory profile.")
            return
        counts = ctx.roster.counts()
        if not counts:
            self.output("Nothing owned - are you in a match?")
            return
        _owned, finished = ctx.roster.survey()
        for name, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
            loc = ctx.location_for(name) or "(not a check)"
            # A type with nothing finished is still a building site, and its
            # check is held back until something of it actually stands.
            if name not in finished:
                loc += "  [under construction]"
            self.output(f"  {n:3d}  {name:<32s} {loc}")
        # Where the walk got to, so a unit missing from this list can be told
        # apart from one the walk never reached.
        total = sum(counts.values())
        self.output(f"{total} objects to slot {ctx.roster.last_slot}"
                    + (f", {ctx.roster.unnamed} with no readable type name"
                       if ctx.roster.unnamed else ""))

    def _cmd_wonders(self):
        """Show which wonders you own and how the wonder goal is progressing."""
        ctx: EmpireEarthContext = self.ctx
        if not ctx.roster:
            self.output("Not attached / no memory profile.")
            return
        owned, finished = ctx.roster.survey()
        for db_name, display in sorted(WONDER_BY_DBNAME.items()):
            if db_name in finished:
                have = "built"
            elif db_name in owned:
                have = "under construction"
            else:
                have = "-"
            # A wonder is not a check, so there is no location to ask the
            # server about. What decides whether you can raise one is the
            # unlock item, when this seed gates them at all.
            if not ctx.gates_buildings:
                note = ""
            elif display in ctx.unlocked_buildings:
                note = "  (unlocked)"
            else:
                note = "  (locked - no Wonder: item yet)"
            self.output(f"  {display:<26s} {have:<18s}{note}")
        if ctx.wonders_needed:
            self.output(
                f"{ctx.wonders_built} of {ctx.wonders_needed} needed for the goal."
            )
        else:
            self.output("Wonders are not a goal in this seed.")

    def _cmd_diplomacy(self):
        """Show who is at peace with whom."""
        ctx: EmpireEarthContext = self.ctx
        if not ctx.diplomacy:
            self.output("Not attached / no memory profile.")
            return
        matrix = ctx.diplomacy.matrix()
        if not matrix:
            self.output("No players - are you in a match?")
            return
        local = ctx.diplomacy.local_slot()
        slots = sorted(matrix)
        self.output("      " + "  ".join(f"->{s}" for s in slots))
        for src in slots:
            row = "  ".join(
                " . " if matrix[src].get(dst) == 0 else " X "
                for dst in slots
            )
            tag = "you" if src == local else ("gaia" if src == 0 else f"p{src}")
            self.output(f"  {tag:<4s}{row}")
        self.output("  . = at peace, X = hostile")
        self.output(f"opponents: {ctx.opponents}")

    def _cmd_settings(self):
        """Show the skirmish settings the client is holding in place."""
        ctx: EmpireEarthContext = self.ctx
        if not ctx.match:
            self.output("Not attached / no memory profile.")
            return
        current = ctx.match.read()
        if not current:
            self.output("Could not read the settings block.")
            return
        for name, value in current.items():
            want = ctx.desired_settings.get(name)
            mark = "" if want is None or want == value else f"  (forcing {describe(name, want)})"
            self.output(f"  {name:<16s} {describe(name, value)}{mark}")

    def _cmd_goal(self):
        """Declare the goal complete."""
        asyncio.create_task(self.ctx.declare_goal())


class EmpireEarthContext(CommonContext):
    game = GAME_NAME
    command_processor = EmpireEarthCommandProcessor
    items_handling = 0b111  # full remote item handling

    def __init__(self, server_address, password):
        super().__init__(server_address, password)
        self.proc = None
        self.res: ResourceAccess | None = None
        self.epochs: EpochAccess | None = None
        # Epoch unlocks are persistent state, not one-shot effects, so they are
        # rebuilt from the full item list rather than tracked by applied_index.
        self.unlocked_epochs: set[int] = set()
        # Same reasoning for buildings: an unlock is a state the client holds,
        # so it is rebuilt from the item list on every poll.
        self.unlocked_buildings: set[str] = set()
        self.gate: BuildingGate | None = None
        self.gates_buildings = False
        self.gated_wonders: list[str] = []
        self.gate_announced = False
        # Research is state too: the whole researched set is read each poll and
        # compared against what has been sent.
        self.research: ResearchWatch | None = None
        # Units are held permanently recruitable, so a per-unit check
        # cannot expire when an epoch passes.
        self.obsolescence: Obsolescence | None = None
        self.permanence_reported = False
        self.tech_checks = False
        self.research_announced = False
        self.sent_research: set[str] = set()
        # Technology benefits are withheld at research time and applied from
        # items instead, so which ones have been granted is tracked here.
        self.tech_effects: TechEffects | None = None
        self.granted_techs: set[str] = set()
        self.granted_key: int | None = None
        self.tech_announced = False
        self.tech_error_reported = False
        # Suppression waits for the match's opening free research
        # to finish before it goes live.
        self.suppression_live = False
        self.opening_reported = False
        # False until the client has seen the game outside a match, which is
        # what tells it a match it later finds is one that began under its eye.
        self.saw_match_begin = False
        # The in-game win is a one-shot detour, armed at most once per match.
        self.win_armed = False
        self.sent_epochs: set[int] = set()
        self.sent_objects: set[str] = set()
        self.roster = None
        self.last_reached = -1
        self.goal_epoch = len(EPOCH_NAMES) - 1
        self.starting_epoch = 0
        self.goal_kind = "reach_epoch"
        self.wonders_needed = 0
        self.wonders_built = 0
        self.in_match = False
        self.match_gone = 0
        self.defeat_reported = False
        self.settings_checked = False
        self.settings_misses = 0
        self.match: MatchSettings | None = None
        self.diplomacy: Diplomacy | None = None
        self.banner: Banner | None = None
        self.win_hook: WinHook | None = None
        self.ingame_messages = True
        self.apply_ingame_win = True
        self.opponents = "allied"
        self.peace_announced = False
        self.desired_settings: dict[str, int] = {}
        self.settings_forced = False
        self.bundle_size = 500
        self.applied_index = 0
        self.state_file: str | None = None
        self.state_ready = False
        self.seed_key = ""
        self._raw_text = None
        self.game_task: asyncio.Task | None = None

    # --- Archipelago plumbing -------------------------------------------

    async def server_auth(self, password_requested: bool = False):
        if password_requested and not self.password:
            await super().server_auth(password_requested)
        await self.get_username()
        await self.send_connect()

    def on_package(self, cmd: str, args: dict):
        if cmd == "RoomInfo":
            # Taken straight off the wire; CommonContext.seed_name is not
            # reliably populated by the time we need it.
            self.seed_key = str(args.get("seed_name") or "")
        elif cmd == "Connected":
            slot_data = args.get("slot_data") or {}
            self.bundle_size = int(slot_data.get("bundle_size", 500))
            self.goal_epoch = int(slot_data.get("goal_epoch", len(EPOCH_NAMES) - 1))
            self.starting_epoch = int(slot_data.get("starting_epoch", 0))
            self.goal_kind = str(slot_data.get("goal", "reach_epoch"))
            self.wonders_needed = int(slot_data.get("wonders_needed", 0))
            self.gates_buildings = bool(slot_data.get("building_unlocks", False))
            self.gated_wonders = list(slot_data.get("gated_wonders", []))
            self.tech_checks = bool(slot_data.get("technology_checks", False))
            self.defeat_reported = False
            self.ingame_messages = bool(
                slot_data.get("ingame_messages", True)
            )
            self.apply_ingame_win = bool(
                slot_data.get("apply_ingame_win", True)
            )
            self.opponents = str(
                slot_data.get("opponents")
                or ("allied" if slot_data.get("force_peace", True) else "hostile")
            )
            self.peace_announced = False
            self.settings_checked = False
            self.desired_settings = self._match_settings_from(slot_data)
            self.settings_forced = False
            logger.info(f"Goal: {self.goal_description()}.")
            # seed_name may not be populated yet depending on packet ordering,
            # so the per-seed state file is resolved lazily instead.
            self.state_ready = False
            logger.info(f"Connected. Bundle size {self.bundle_size}.")

    def _match_settings_from(self, slot_data: dict) -> dict[str, int]:
        """The setup screen this seed requires.

        Seeds rolled before the settings options existed only carry the two
        epochs, so those are still enforced; cheat codes are forced off either
        way, since a seed played with cheats is not a seed anybody can compare.
        """
        wanted = dict(slot_data.get("match_settings") or {})
        wanted.setdefault("starting_epoch", self.starting_epoch)
        wanted.setdefault("ending_epoch", self.goal_epoch)
        if "unit_limit" in wanted:
            wanted["unit_limit"] = clamp_unit_limit(wanted["unit_limit"])
        wanted["cheat_codes"] = 0
        return {k: int(v) for k, v in wanted.items()}

    # Server messages are richer than anything assembled locally - they name
    # the item and both players - so they are shown verbatim.
    # Only things the server never reports (epoch entry, setting mismatches)
    # are published by this client directly.
    SKIP_MESSAGE_TYPES = {"Tutorial"}

    def on_print_json(self, args: dict):
        super().on_print_json(args)
        try:
            if args.get("type") in self.SKIP_MESSAGE_TYPES:
                return
            if self._raw_text is None:
                from NetUtils import RawJSONtoTextParser

                self._raw_text = RawJSONtoTextParser(self)
            text = self._raw_text(args["data"]).strip()
            if not text:
                return
            if args.get("type") == "ItemSend":
                # Green when it is coming to us, blue when we are the source.
                kind = "item" if args.get("receiving") == self.slot else "sent"
            else:
                kind = "info"
            self.notify(text, kind)
        except Exception:
            pass          # notifications are cosmetic; never break the client

    def notify(self, text: str, kind: str = "info"):
        """Announce something on the game's own message line.

        `kind` is kept because callers distinguish an item from a warning, and
        the game's message line does not - if a future surface wants to colour
        them differently, the information is already here.
        """
        if self.ingame_messages and self.banner:
            self.banner.show(text)

    def make_gui(self):
        ui = super().make_gui()
        ui.base_title = "Archipelago Empire Earth Client"
        return ui

    async def declare_goal(self):
        await self.send_msgs(
            [{"cmd": "StatusUpdate", "status": ClientStatus.CLIENT_GOAL}]
        )
        self.finished_game = True
        logger.info("Goal declared.")
        self.end_match_as_win()

    def match_decided(self) -> bool:
        """Has this match already ended, one way or the other?"""
        if not self.proc or not self.diplomacy:
            return False
        obj = self.diplomacy.players().get(self.diplomacy.local_slot())
        if obj is None:
            return False
        outcome = self.proc.read_i32(obj + OUTCOME_OFFSET)
        return outcome is not None and outcome != OUTCOME_UNDECIDED

    def end_match_as_win(self):
        """Have the game end the match as a win, now the seed is finished.

        Fires once per match. Declaring the goal is what triggers it, and a
        client reconnecting to a finished seed declares it again, so without
        this a reconnect re-ran the detour against a match that had already
        ended. The armed flag covers the frame or two between arming the hook
        and the game recording an outcome, which a poll can otherwise land in.
        """
        if not self.apply_ingame_win or not self.win_hook:
            return
        if self.win_armed or self.match_decided():
            return
        if not self.win_hook.usable():
            logger.info(
                "Not ending the match in game: this build's victory code is "
                "not where this world expects it."
            )
            return
        if self.win_hook.arm(won=True):
            self.win_armed = True
            logger.info("Ending the match in game - you are victorious.")
        else:
            logger.warning("Could not end the match in game; it will keep running.")

    # --- applied-item bookkeeping ---------------------------------------

    def _ensure_state(self) -> bool:
        """Resolve the per-seed state file once the slot name is known.

        Falls back to a shared key if the server never told us a seed name, so
        that a missing seed can never block item delivery.
        """
        if self.state_ready:
            return True
        if not self.auth:
            return False
        seed = self.seed_key or getattr(self, "seed_name", "") or "default"
        self.state_file = _state_path(seed, self.auth)
        self.applied_index = self._load_applied()
        self.state_ready = True
        logger.info(
            f"Progress file: {os.path.basename(self.state_file)} "
            f"({self.applied_index} item(s) already applied)."
        )
        return True

    def _read_state(self) -> dict:
        if not self.state_file or not os.path.exists(self.state_file):
            return {}
        try:
            with open(self.state_file) as f:
                got = json.load(f)
            return got if isinstance(got, dict) else {}
        except (OSError, ValueError, json.JSONDecodeError):
            return {}

    def _load_applied(self) -> int:
        return int(self._read_state().get("applied_index", 0))

    def _save_applied(self):
        """Persist the applied index and which technologies are already granted.

        Granting is cumulative, not idempotent - applying a technology twice
        gives its bonus twice, which a reconnect would do for every technology
        received so far. The granted set is therefore keyed by the match's tech
        tree: a new match legitimately needs them all applied again, because the
        game starts that match with none of them.
        """
        if not self.state_file:
            return
        state = self._read_state()
        state["applied_index"] = self.applied_index
        if self.granted_key:
            state["granted_key"] = self.granted_key
            state["granted_techs"] = sorted(self.granted_techs)
        try:
            with open(self.state_file, "w") as f:
                json.dump(state, f)
        except OSError as e:
            logger.warning(f"Could not persist client progress: {e}")

    def _restore_granted(self, key: int):
        """Pick the granted set back up when reattaching to the same match."""
        if self.granted_key == key:
            return
        self.granted_key = key
        state = self._read_state()
        if state.get("granted_key") == key:
            self.granted_techs = set(state.get("granted_techs", []))
            if self.granted_techs:
                logger.info(
                    f"Reattached mid-match; {len(self.granted_techs)} "
                    "technolog(ies) already applied, not reapplying."
                )
        else:
            self.granted_techs = set()

    # --- game attachment -------------------------------------------------

    def ensure_attached(self) -> bool:
        if self.proc and self.proc.alive:
            return True
        if self.proc:
            self.proc.close()
            self.proc = None
            self.res = None
            self.roster = None
            self.match = None
            self.diplomacy = None
            self.banner = None
            self.win_hook = None
        proc = attach(*EXE_NAMES)
        if not proc:
            return False
        self.proc = proc
        mods = proc.modules()
        exe_path = mods[0][0] if mods else proc.exe
        prof = profile_for(exe_path)
        if prof is None:
            logger.warning(
                f"Attached to {os.path.basename(exe_path)} but no memory profile "
                "matches this build. Run tools/find_resources.py to create one."
            )
            self.res = None
        else:
            self.res = ResourceAccess(proc, prof)
            self.epochs = EpochAccess(proc, self.res)
            self.roster = Roster(proc, prof)
            self.match = MatchSettings(proc)
            self.diplomacy = Diplomacy(proc, prof)
            self.banner = Banner(proc)
            self.win_hook = WinHook(proc)
            self.gate = BuildingGate(proc, self.roster, self.epochs)
            self.research = ResearchWatch(proc, self.roster, self.epochs)
            self.obsolescence = Obsolescence(proc, self.epochs)
            self.tech_effects = TechEffects(proc, prof)
            self.settings_forced = False
            self.peace_announced = False
            logger.info(f"Attached to {os.path.basename(exe_path)} using profile '{prof.name}'.")
        return True

    def release_game(self):
        """Undo everything that outlives this client, on the way out.

        Three of the client's writes do not heal by themselves, and each leaves
        the game in a state the player cannot get out of without restarting it:

        * the effect-call detour at `0x005CFAAF`, which keeps withholding
          technology benefits with nothing left to grant them
        * the win detour, if it was armed and the match ended before it fired
        * every building held out of the build menu, which the engine only ever
          re-opens on the epoch transition that would have opened it anyway

        Best-effort by design. A client killed outright never gets here, which
        is what `TechEffects.adopt()` and `BuildingGate`'s "ask the node" rule
        are for - both let the next client pick up a game left mid-patch.

        The allocated pages are deliberately *not* freed. They are 4 KB apiece
        and the process is about to keep running without us; freeing one a game
        thread happens to be executing would crash it, and the code patches are
        already gone by then, so nothing new can enter them.
        """
        if not self.proc or not self.proc.alive:
            return
        for what, undo in (
            ("technology suppression", getattr(self.tech_effects, "restore", None)),
            ("the in-game win hook", getattr(self.win_hook, "restore", None)),
            ("building locks", getattr(self.gate, "restore", None)),
        ):
            if undo is None:
                continue
            try:
                undo()
            except Exception as e:
                logger.warning(f"Could not undo {what}: {e!r}")

    async def apply_pending_items(self):
        """Credit every item the server has sent that we haven't applied yet.

        Nothing is announced here. The server already prints a line naming the
        item and where it came from, and that line is what reaches the game, so
        a second one from the client only says the same thing twice.
        """
        if not self.res or not self._ensure_state():
            return
        while self.applied_index < len(self.items_received):
            net_item = self.items_received[self.applied_index]
            res_idx = ITEM_ID_TO_RESOURCE.get(net_item.item)
            if res_idx is None:
                # Epoch and building unlocks are state, applied by their own
                # gates from the full item list rather than one at a time.
                self.applied_index += 1
                continue
            if self.res.add(res_idx, self.bundle_size) is None:
                return  # not in a match yet - retry on the next poll
            self.applied_index += 1
            self._save_applied()


    # --- epochs -----------------------------------------------------------

    def refresh_epoch_unlocks(self):
        """Rebuild the unlocked set from every item the server has sent.

        Idempotent by design: the server replays the whole list on reconnect,
        and an unlock is a state, not an event.
        """
        self.unlocked_epochs = {
            ITEM_ID_TO_EPOCH[i.item]
            for i in self.items_received
            if i.item in ITEM_ID_TO_EPOCH
        }

    def sync_permanence(self):
        """Keep every unit recruitable, so no check can expire.

        Without this a unit is withdrawn when a later tier replaces it, and a
        check for one you never built becomes impossible to send - which now
        matters, because these checks can hold progression.
        """
        if not self.obsolescence:
            return
        try:
            changed = self.obsolescence.apply()
        except Exception as e:
            if not self.permanence_reported:
                self.permanence_reported = True
                logger.warning(f"Could not keep units recruitable: {e!r}")
            return
        if changed:
            logger.info(
                f"{changed} unit(s) and building(s) held available "
                "through this epoch."
            )

    async def sync_research(self):
        """Send a check for every technology the player has researched.

        Idempotent: it reports the whole researched set each poll and sends
        only what has not gone yet, so a reconnect mid-match catches up rather
        than missing everything that happened while it was away.
        """
        if not (self.tech_checks and self.research):
            return
        try:
            done = self.research.researched(TECH_LOCATION_BY_NODE)
        except Exception:
            return          # between matches, or the tree is not resolvable
        if not self.research_announced and done:
            missing = self.research.missing(TECH_LOCATION_BY_NODE)
            if missing:
                logger.warning(
                    f"Technology checks: no node found for {len(missing)} "
                    f"technolog{'y' if len(missing) == 1 else 'ies'} "
                    f"({', '.join(missing[:4])}) - those cannot be sent."
                )
            self.research_announced = True

        new = []
        for key in done:
            name = TECH_LOCATION_BY_NODE.get(key)
            if not name or name in self.sent_research:
                continue
            loc_id = LOCATION_NAME_TO_ID.get(name)
            if loc_id is None or loc_id not in self.missing_locations:
                self.sent_research.add(name)
                continue
            self.sent_research.add(name)
            new.append(loc_id)
        if new:
            await self.check_locations(new)

    def sync_tech_effects(self):
        """Withhold researched benefits, and apply the ones items have sent.

        Two halves of one idea. The detour stops the game applying a technology
        the moment you research it - the check still fires, because the game
        still records the research - and every `Tech:` item received applies
        that technology's effect instead.

        Suppression is aimed at this player's tech tree only. The AI research
        constantly and must be left alone, or the match stops being a game.
        """
        if not (self.tech_checks and self.tech_effects and self.research):
            return
        try:
            if not self.tech_effects.arm():
                if not self.tech_announced:
                    logger.warning(
                        "Technology benefits cannot be held back on this build: "
                        "the effect call is not where this world expects it. "
                        "Researching will give its usual benefit as well as a check."
                    )
                    self.tech_announced = True
                return
            # Publish the ids the moment we attach, before any match exists.
            #
            # The stub resolves the local player's tech tree by itself, so this
            # table is the only thing it waits for - and having it in place
            # early is what catches the research the game does while a match
            # loads. Reading the ids from a live match instead lost that burst
            # every time, and an applied benefit cannot be taken back.
            if not self.suppression_live:
                if not self.tech_effects.set_suppressible(TECH_EFFECT_IDS):
                    if not self.tech_error_reported:
                        self.tech_error_reported = True
                        logger.warning(
                            "Could not enable technology suppression; "
                            "researching will give its usual benefit."
                        )
                    return
                self.suppression_live = True
                logger.info(
                    f"Technology effects are being held back "
                    f"({len(TECH_EFFECT_IDS)} technologies)."
                )

            tree = self.epochs.tech_tree() if self.epochs else None
            if not tree:
                return          # between matches; nothing to grant into
            self._restore_granted(tree)
            nodes = self.research.scan(TECH_LOCATION_BY_NODE)

            # How much of the opening burst we actually caught. The game may
            # grant some of it before a tech tree is even resolvable, and a
            # benefit already applied cannot be taken back - so this is
            # reported rather than assumed.
            researched = len(self.research.researched(TECH_LOCATION_BY_NODE))
            if researched and not self.opening_reported:
                self.opening_reported = True
                caught = self.tech_effects.suppressed()
                if caught < researched:
                    logger.warning(
                        f"{researched} technolog(ies) were already researched "
                        f"at match start but only {caught} had their benefit "
                        "withheld; the rest were applied before the client "
                        "could see the match."
                    )
            for net_item in self.items_received:
                tech = ITEM_ID_TO_TECH.get(net_item.item)
                if tech is None or tech in self.granted_techs:
                    continue
                entry = TECHNOLOGIES.get(tech)
                if entry is None:
                    continue
                node = nodes.get((entry[2], entry[3]))
                if node is None:
                    continue    # not in this match's tree; try again next poll
                if self.tech_effects.grant(node):
                    self.granted_techs.add(tech)
                    self._save_applied()
                    logger.info(f"Applied {tech}.")
        except Exception as e:
            # Reported once, not swallowed. A bare `except: return` here hid a
            # grant that never fired for a whole session.
            if not self.tech_error_reported:
                self.tech_error_reported = True
                logger.warning(f"Technology effects stopped: {e!r}")

    def sync_buildings(self):
        """Hold locked buildings out of the build menu.

        Run every poll, like the epoch gate: the game rebuilds its tech tree
        for each match, and a node's availability is otherwise the engine's to
        set. Nothing here touches the epoch requirement, which the same
        predicate tests separately.
        """
        if not (self.gates_buildings and self.gate):
            return
        # Wonders go through the same gate: the engine holds them behind the
        # same `available` flag on the same kind of node, so the only
        # difference is which item frees which. They are not checks, so nothing
        # here reports one.
        gated = tuple(LOCKABLE_BUILDINGS) + tuple(self.gated_wonders)
        self.unlocked_buildings = {
            (ITEM_ID_TO_BUILDING.get(i.item) or ITEM_ID_TO_WONDER.get(i.item))
            for i in self.items_received
            if i.item in ITEM_ID_TO_BUILDING or i.item in ITEM_ID_TO_WONDER
        }
        locked, freed = self.gate.apply(self.unlocked_buildings, gated)
        if not self.gate_announced and (locked or freed):
            missing = self.gate.missing(gated)
            if missing:
                logger.warning(
                    "Building unlocks: no tech tree node found for "
                    + ", ".join(missing)
                    + " - those stay buildable."
                )
            self.gate_announced = True

    def enforce_match_settings(self):
        """Hold the skirmish setup screen at the settings the seed was rolled for.

        Run on every poll rather than once, so changing a dropdown in game is
        undone before it can reach a match. The values are live in memory, so a
        correction takes effect immediately - there is nothing to reload.
        """
        if not self.match or not self.desired_settings:
            return
        changed = self.match.apply(self.desired_settings)
        if not changed:
            return
        if not self.settings_forced:
            # First pass after attaching: the whole screen is being brought in
            # line at once, which is expected rather than something the player
            # did, so it is reported as a block and not flagged as a reversion.
            self.settings_forced = True
            logger.info("Skirmish settings set from your YAML:")
            for line in changed:
                logger.info(f"  {line}")
            self.notify("Skirmish settings set by Archipelago", "info")
            return
        for line in changed:
            logger.info(f"Reverted - {line}")
        self.notify("Reverted: " + "; ".join(changed), "warn")

    def check_match_settings(self):
        """Warn if the skirmish does not match the seed, and cap the end epoch.

        The player configures the skirmish before this client can intervene, so
        a wrong starting epoch can only be reported - but the end epoch is a
        value in the tech tree, so it is corrected outright.
        """
        if not self.epochs:
            return
        reached = self.epochs.reached()
        highest = self.epochs.highest()
        if reached is None or highest is None:
            # Not in a match (menu, loading). Re-arm only after a sustained
            # absence: a single failed read would otherwise re-issue the
            # warning every time it happened.
            self.settings_misses += 1
            if self.settings_misses >= 6:      # ~3s at the current poll rate
                self.settings_checked = False
                # Outside a match, so the next one begins where we can see it.
                self.saw_match_begin = True
            return
        self.settings_misses = 0
        if self.settings_checked:
            return
        self.settings_checked = True

        if reached != self.starting_epoch:
            if not self.saw_match_begin:
                # Attached to a match that was already running, so the epoch
                # read is wherever the player has got to - it says nothing
                # about where the match started. Warning here claimed a skirmish
                # had started in the wrong epoch every time the client was
                # restarted mid-game.
                logger.info(
                    f"Attached to a match already in progress "
                    f"({EPOCH_NAMES[reached]})."
                )
            else:
                msg = (
                    f"Skirmish starts in {EPOCH_NAMES[reached]} but this seed "
                    f"expects {EPOCH_NAMES[self.starting_epoch]}."
                )
                logger.warning(msg)
                logger.warning(
                    "Restart the match with the correct starting epoch, or "
                    "checks for the skipped epochs can never be sent."
                )
                self.notify(msg, "warn")

        if highest != self.goal_epoch:
            if self.epochs.set_highest(self.goal_epoch):
                logger.info(
                    f"Capped the match at {EPOCH_NAMES[self.goal_epoch]} "
                    f"(was {EPOCH_NAMES[highest]})."
                )
            else:
                logger.warning("Could not cap the match's final epoch.")

    def locations_for(self, db_name: str) -> list[str]:
        """Every check this type name satisfies.

        Matching is on the type name the game itself reports, so a unit always
        satisfies its own check. Some also satisfy others, because the game
        makes a unit unbuildable in two ways that a per-unit check cannot
        survive on its own:

        * The two heroes of a tier are mutually exclusive - build Sargon of
          Akkad and Gilgamesh can never exist in that match - so recruiting
          either sends both.
        * A unit is retired when a later tier replaces it, so a Slinger stops
          being offered once Simple Bowmen arrive. The replacement carries the
          replaced unit's check: a Simple Bowman sends Slinger's too, and a
          Long Bow sends all four below it.

        Both relations only ever *add* checks, which is what makes them safe:
        an extra send costs a free check, while a missing one can leave a seed
        unwinnable.
        """
        loc = BUILD_LOCATION_BY_DBNAME.get(db_name)
        if loc is not None:
            # Buildings cascade too: a `Planets` map has a Space Dock where
            # every other map has a Dock, so each sends the other's check.
            return [loc, *LOCATION_ALSO_SENDS.get(loc, ())]
        recruit = RECRUIT_LOCATION_BY_DBNAME.get(db_name)
        if not recruit:
            return []
        return [recruit, *LOCATION_ALSO_SENDS.get(recruit, ())]

    def location_for(self, db_name: str) -> str | None:
        """The first check a type name satisfies, for the /roster display."""
        found = self.locations_for(db_name)
        return found[0] if found else None

    async def sync_roster(self):
        """Send a check the first time the player owns a curated type."""
        if not self.roster:
            return
        try:
            owned, finished = self.roster.survey()
        except Exception:
            return
        if not owned:
            return

        self.wonders_built = sum(
            1 for n in finished if n in WONDER_BY_DBNAME
        )

        # Everything is gated on completion. The roster lists an object from the
        # moment its foundation is placed, so matching on what is merely owned
        # sends "Build House" before the house exists - and would finish a
        # wonder goal as the last wonder *starts*.
        new_ids = []
        for db_name in finished:
            for loc in self.locations_for(db_name):
                if loc in self.sent_objects:
                    continue
                loc_id = LOCATION_NAME_TO_ID.get(loc)
                # Locations outside this seed are simply not present.
                if loc_id is None or loc_id not in self.missing_locations:
                    self.sent_objects.add(loc)
                    continue
                self.sent_objects.add(loc)
                new_ids.append((loc, loc_id))

        for loc, loc_id in new_ids:
            await self.check_locations([loc_id])
            # No log line here: the server already prints a better one naming
            # the item and who received it, and that is what reaches the game.

    async def sync_epochs(self):
        """Gate future epochs, and report any the player has just entered."""
        if not self.epochs:
            return
        self.refresh_epoch_unlocks()
        self.epochs.apply(self.unlocked_epochs)

        reached = self.epochs.reached()
        if reached is None:
            return          # not in a match yet
        if reached == self.last_reached:
            return
        self.last_reached = reached
        # Only epochs after the starting one and up to the goal exist as checks
        # in this seed. Starting in Copper Age means there is no "Reach Stone
        # Age" to send, and claiming it would be wrong as well as useless.
        first = self.starting_epoch + 1
        for i in range(first, min(reached, self.goal_epoch) + 1):
            if i in self.sent_epochs:
                continue
            name = f"Reach {EPOCH_NAMES[i]}"
            loc_id = LOCATION_NAME_TO_ID.get(name)
            if loc_id is None:
                continue
            self.sent_epochs.add(i)
            await self.check_locations([loc_id])
            # Entering an epoch is worth noting; the check itself is announced
            # by the server, so it is not repeated here.
            logger.info(f"Entered {EPOCH_NAMES[i]}.")
            self.notify(f"Entered {EPOCH_NAMES[i]}", "sent")

    # Roughly three seconds at the current poll rate. Long enough that loading
    # screens and a momentarily unresolvable roster do not read as an ending.
    MATCH_GONE_POLLS = 6

    def track_match_state(self):
        """Notice a match starting or ending, and say the seed is unaffected.

        Even with the game's own victory conditions held off, a run can still
        stop: wiped down to nothing, quit to the menu, or a crash. None of that
        costs checks - they are on the server - so the useful thing is to say so
        rather than leave the player wondering.
        """
        self.check_defeat()
        alive = bool(self.roster and self.roster.owned_type_names())
        if alive:
            self.match_gone = 0
            if not self.in_match:
                self.in_match = True
                logger.info("Match detected.")
            return

        if not self.in_match:
            return
        self.match_gone += 1
        if self.match_gone < self.MATCH_GONE_POLLS:
            return

        self.in_match = False
        self.match_gone = 0
        sent = len(self.checked_locations)
        total = sent + len(self.missing_locations)
        logger.info(
            f"Match ended. Your seed is intact - {sent} of {total} checks sent "
            f"and every item you received is kept."
        )
        logger.info("Start another skirmish and the client picks up where it left off.")
        self.notify(f"Match ended - seed intact ({sent}/{total} checks)", "warn")
        # The next match starts at the seed's own starting epoch, so epoch
        # detection has to be allowed to run again from scratch.
        self.last_reached = -1
        # A new match builds a new tech tree at new addresses, so the cached
        # nodes belong to a game that no longer exists.
        if self.gate:
            self.gate.forget()
        if self.research:
            self.research.forget()
        if self.obsolescence:
            self.obsolescence.forget()
        self.permanence_reported = False
        # The suppression stub needs no telling: it resolves the local player's
        # tech tree on every call, and outside a match that resolves to null and
        # everything passes through.
        self.granted_techs.clear()
        self.granted_key = None
        self.tech_announced = False
        self.suppression_live = False
        self.opening_reported = False
        self.gate_announced = False
        self.research_announced = False
        # A new match can be won on its own terms.
        self.win_armed = False

    def enforce_peace(self):
        """Hold every computer player at peace with us.

        Run every poll rather than once: an AI that re-declares war is put back
        within half a second, and a new match is covered without any special
        handling.
        """
        if self.opponents != "allied" or not self.diplomacy:
            return
        try:
            changed = self.diplomacy.force_peace()
        except Exception:
            return
        if not changed:
            return
        if not self.peace_announced:
            self.peace_announced = True
            logger.info("Opponents held at peace: " + ", ".join(changed))
            self.notify("Opponents are at peace with you", "info")

    def check_defeat(self):
        """Report a defeat that the match itself never acts on.

        Holding victory off stops the match ending, not the defeat: a defeated
        player is left unable to do anything in a match that keeps running, with
        their units still in the roster. Nothing else here would notice, so the
        outcome field is read directly.
        """
        if self.defeat_reported or not self.proc or not self.diplomacy:
            return
        slot = self.diplomacy.local_slot()
        obj = self.diplomacy.players().get(slot)
        if obj is None:
            return
        if self.proc.read_i32(obj + OUTCOME_OFFSET) != OUTCOME_DEFEATED:
            return
        self.defeat_reported = True
        sent = len(self.checked_locations)
        total = sent + len(self.missing_locations)
        logger.warning(
            f"You have been defeated. Your seed is intact - {sent} of {total} "
            f"checks sent and every item you received is kept."
        )
        logger.warning(
            "The match will not end on its own while prevent_match_end is on, "
            "so quit to the menu and start another skirmish."
        )
        self.notify("Defeated - quit to the menu, your seed is safe", "warn")

    # --- goal -------------------------------------------------------------

    def goal_description(self) -> str:
        parts = []
        if self.goal_kind in ("reach_epoch", "either"):
            parts.append(f"reach {EPOCH_NAMES[self.goal_epoch]}")
        if self.goal_kind in ("wonder_victory", "either"):
            n = self.wonders_needed
            parts.append(f"build {n} wonder{'s' if n != 1 else ''}")
        return " or ".join(parts) if parts else "unknown"

    async def check_goal(self):
        """Complete the seed as soon as any of its goals is met."""
        if self.finished_game:
            return

        if self.goal_kind in ("reach_epoch", "either") and self.epochs:
            reached = self.epochs.reached()
            if reached is not None and reached >= self.goal_epoch:
                self.notify(
                    f"Goal complete: {EPOCH_NAMES[self.goal_epoch]}!", "item"
                )
                await self.declare_goal()
                return

        if self.goal_kind in ("wonder_victory", "either"):
            if self.wonders_needed and self.wonders_built >= self.wonders_needed:
                self.notify(
                    f"Goal complete: {self.wonders_built} wonders!", "item"
                )
                await self.declare_goal()


async def game_watcher(ctx: EmpireEarthContext):
    warned = False
    while not ctx.exit_event.is_set():
        try:
            if ctx.ensure_attached():
                warned = False
                if ctx.server and ctx.slot is not None:
                    # First, so a setup screen is corrected even if something
                    # further down fails this poll.
                    ctx.enforce_match_settings()
                    await ctx.apply_pending_items()
                    await ctx.sync_epochs()
                    ctx.sync_permanence()
                    ctx.sync_buildings()
                    await ctx.sync_research()
                    ctx.sync_tech_effects()
                    # Driven from here rather than from sync_epochs: that
                    # returns early once the epoch stops changing, which would
                    # otherwise stop these running at all.
                    ctx.check_match_settings()
                    await ctx.sync_roster()
                    ctx.track_match_state()
                    ctx.enforce_peace()
                    # After sync_roster, so the wonder count it produces is
                    # this poll's rather than the previous one's.
                    await ctx.check_goal()
            elif not warned:
                # "Not running" and "running but we cannot open it" look the
                # same from here, and the second is far more confusing to hit:
                # an elevated game refuses a non-elevated client every right,
                # including the most basic query.
                from .Memory import find_pids

                if find_pids(*EXE_NAMES):
                    logger.warning(
                        "Empire Earth is running but Windows will not let this "
                        "client open it, which means the game is running as "
                        "administrator and Archipelago is not."
                    )
                    logger.warning(
                        "The Steam release does this by default: it ships a "
                        "RUNASADMIN compatibility setting. Run Archipelago as "
                        "administrator too, or clear that setting on the game."
                    )
                else:
                    logger.info("Waiting for Empire Earth to start...")
                warned = True
        except Exception as e:  # keep the watcher alive across transient failures
            logger.error(f"Game watcher error: {e}")
        await asyncio.sleep(POLL_INTERVAL)


def launch(*args):
    async def main():
        parser = get_base_parser(description="Empire Earth Archipelago Client")
        # Depending on the Archipelago version these may or may not already be
        # provided by get_base_parser(); adding them twice is not an error we
        # want to be fatal.
        for flag, kwargs in (
            ("--name", {"default": None, "help": "Slot name to connect as."}),
            ("--nogui", {"action": "store_true", "help": "Run without the GUI."}),
        ):
            try:
                parser.add_argument(flag, **kwargs)
            except argparse.ArgumentError:
                pass
        ns = parser.parse_args(args)
        logger.info(f"Starting Empire Earth client (connect={ns.connect!r})")

        ctx = EmpireEarthContext(ns.connect, ns.password)
        if getattr(ns, "name", None):
            ctx.auth = ns.name
        ctx.server_task = asyncio.create_task(server_loop(ctx), name="ServerLoop")
        if gui_enabled and not getattr(ns, "nogui", False):
            ctx.run_gui()
        # Launched from the Launcher GUI (or any non-interactive parent) there is
        # no usable stdin; the console reader must not take the client down.
        try:
            ctx.run_cli()
        except Exception as e:
            logger.info(f"No interactive console available ({e}); continuing.")
        ctx.game_task = asyncio.create_task(game_watcher(ctx), name="GameWatcher")

        await ctx.exit_event.wait()
        # Stop the watcher before undoing anything, or a poll already in flight
        # re-arms what release_game has just taken back out.
        ctx.game_task.cancel()
        try:
            await ctx.game_task
        except asyncio.CancelledError:
            pass
        ctx.release_game()
        if ctx.proc:
            ctx.proc.close()
        await ctx.shutdown()

    Utils.init_logging("EmpireEarthClient", exception_logger="Client")
    logger.debug(f"launch() received args: {args!r}")
    import colorama

    colorama.just_fix_windows_console()
    try:
        asyncio.run(main())
    except SystemExit as e:
        logger.error(f"Argument parsing failed / exited early: code={e.code}")
        raise
    except BaseException:
        logger.exception("Empire Earth client terminated with an exception")
        raise
    finally:
        colorama.deinit()


if __name__ == "__main__":
    launch()
