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

from .Addresses import EXE_NAMES, RESOURCE_NAMES, ResourceAccess, profile_for
from .Overlay import publish as overlay_publish
from .Overlay import publish_config as overlay_config
from .Epochs import EPOCH_NAMES, EpochAccess
from .Items import ITEM_ID_TO_EPOCH, ITEM_ID_TO_NAME, ITEM_ID_TO_RESOURCE
from .Locations import (
    BUILD_LOCATION_BY_DBNAME,
    LOCATION_NAME_TO_ID,
    RECRUIT_LOCATION_BY_FAMILY,
)
from .Objects import UNIT_FAMILY_BY_NAME
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
        for name, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
            loc = BUILD_LOCATION_BY_DBNAME.get(name)
            if loc is None:
                family = UNIT_FAMILY_BY_NAME.get(name)
                loc = RECRUIT_LOCATION_BY_FAMILY.get(family) if family else None
            self.output(f"  {n:3d}  {name:<32s} {loc or '(not a check)'}")

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
        self.sent_epochs: set[int] = set()
        self.sent_objects: set[str] = set()
        self.roster = None
        self.last_reached = -1
        self.goal_epoch = len(EPOCH_NAMES) - 1
        self.starting_epoch = 0
        self.settings_checked = False
        self.settings_misses = 0
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
            self.message_sound = bool(slot_data.get("message_sound", True))
            self.goal_epoch = int(slot_data.get("goal_epoch", len(EPOCH_NAMES) - 1))
            self.starting_epoch = int(slot_data.get("starting_epoch", 0))
            self.settings_checked = False
            overlay_config(sound=self.message_sound)
            logger.info(f"Goal: reach {EPOCH_NAMES[self.goal_epoch]}.")
            # seed_name may not be populated yet depending on packet ordering,
            # so the per-seed state file is resolved lazily instead.
            self.state_ready = False
            logger.info(f"Connected. Bundle size {self.bundle_size}.")

    # Server messages are richer than anything assembled locally - they name
    # the item and both players - so they are mirrored to the overlay verbatim.
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
            overlay_publish(text, kind)
        except Exception:
            pass          # the overlay is cosmetic; never break the client

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

    def _load_applied(self) -> int:
        if not self.state_file or not os.path.exists(self.state_file):
            return 0
        try:
            with open(self.state_file) as f:
                return int(json.load(f).get("applied_index", 0))
        except (OSError, ValueError, json.JSONDecodeError):
            return 0

    def _save_applied(self):
        if not self.state_file:
            return
        try:
            with open(self.state_file, "w") as f:
                json.dump({"applied_index": self.applied_index}, f)
        except OSError as e:
            logger.warning(f"Could not persist applied-item index: {e}")

    # --- game attachment -------------------------------------------------

    def ensure_attached(self) -> bool:
        if self.proc and self.proc.alive:
            return True
        if self.proc:
            self.proc.close()
            self.proc = None
            self.res = None
            self.roster = None
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
            logger.info(f"Attached to {os.path.basename(exe_path)} using profile '{prof.name}'.")
        return True

    async def apply_pending_items(self):
        """Credit every item the server has sent that we haven't applied yet."""
        if not self.res or not self._ensure_state():
            return
        while self.applied_index < len(self.items_received):
            net_item = self.items_received[self.applied_index]
            res_idx = ITEM_ID_TO_RESOURCE.get(net_item.item)
            if res_idx is None:
                # Epoch unlocks and anything else are handled elsewhere.
                epoch = ITEM_ID_TO_EPOCH.get(net_item.item)
                if epoch is not None:
                    name = ITEM_ID_TO_NAME.get(net_item.item, str(net_item.item))
                    logger.info(f"Received {name} - you may advance into it")
                    overlay_publish(f"Unlocked {EPOCH_NAMES[epoch]}", "item")
                self.applied_index += 1
                continue
            new = self.res.add(res_idx, self.bundle_size)
            if new is None:
                return  # not in a match yet - retry on the next poll
            name = ITEM_ID_TO_NAME.get(net_item.item, str(net_item.item))
            line = (
                f"Received {name}: +{self.bundle_size} "
                f"{RESOURCE_NAMES[res_idx]} (now {new:,.0f})"
            )
            logger.info(line)
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
            return
        self.settings_misses = 0
        if self.settings_checked:
            return
        self.settings_checked = True

        if reached != self.starting_epoch:
            msg = (
                f"Skirmish starts in {EPOCH_NAMES[reached]} but this seed "
                f"expects {EPOCH_NAMES[self.starting_epoch]}."
            )
            logger.warning(msg)
            logger.warning(
                "Restart the match with the correct starting epoch, or checks "
                "for the skipped epochs can never be sent."
            )
            overlay_publish(msg, "warn")

        if highest != self.goal_epoch:
            if self.epochs.set_highest(self.goal_epoch):
                logger.info(
                    f"Capped the match at {EPOCH_NAMES[self.goal_epoch]} "
                    f"(was {EPOCH_NAMES[highest]})."
                )
            else:
                logger.warning("Could not cap the match's final epoch.")

    async def sync_roster(self):
        """Send a check the first time the player owns a curated type.

        Matching is on the type name the game itself reports, so a family check
        fires for any of its members - 'Citizen' and 'Female Citizen' both
        count towards Recruit Citizen.
        """
        if not self.roster:
            return
        try:
            owned = self.roster.owned_type_names()
        except Exception:
            return
        if not owned:
            return

        new_ids = []
        for db_name in owned:
            loc = BUILD_LOCATION_BY_DBNAME.get(db_name)
            if loc is None:
                family = UNIT_FAMILY_BY_NAME.get(db_name)
                loc = RECRUIT_LOCATION_BY_FAMILY.get(family) if family else None
            if loc is None or loc in self.sent_objects:
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
            # the item and who received it. The overlay does not see server
            # messages, so it still gets told.

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
            overlay_publish(f"Entered {EPOCH_NAMES[i]}", "sent")

        if reached >= self.goal_epoch and not self.finished_game:
            overlay_publish(f"Goal complete: {EPOCH_NAMES[self.goal_epoch]}!", "item")
            await self.declare_goal()


async def game_watcher(ctx: EmpireEarthContext):
    warned = False
    while not ctx.exit_event.is_set():
        try:
            if ctx.ensure_attached():
                warned = False
                if ctx.server and ctx.slot is not None:
                    await ctx.apply_pending_items()
                    await ctx.sync_epochs()
                    # Driven from here rather than from sync_epochs: that
                    # returns early once the epoch stops changing, which would
                    # otherwise stop these running at all.
                    ctx.check_match_settings()
                    await ctx.sync_roster()
            elif not warned:
                logger.info("Waiting for Empire Earth to start...")
                warned = True
        except Exception as e:  # keep the watcher alive across transient failures
            logger.error(f"Game watcher error: {e}")
        await asyncio.sleep(POLL_INTERVAL)


def start_overlay():
    """Bring up the on-screen overlay alongside the client.

    Runs as a daemon child so it dies with the client rather than being left
    stuck on screen. The overlay's own single-instance guard means starting one
    that is already running is harmless.
    """
    try:
        import multiprocessing

        from .Overlay import main as overlay_main

        proc = multiprocessing.Process(
            target=overlay_main,
            args=([],),          # explicit argv: the client's own args are not ours
            name="EmpireEarthOverlay",
            daemon=True,
        )
        proc.start()
        return proc
    except Exception as e:
        logger.info(f"Overlay could not be started automatically ({e}).")
        return None


def launch(*args):
    async def main():
        parser = get_base_parser(description="Empire Earth Archipelago Client")
        # Depending on the Archipelago version these may or may not already be
        # provided by get_base_parser(); adding them twice is not an error we
        # want to be fatal.
        for flag, kwargs in (
            ("--name", {"default": None, "help": "Slot name to connect as."}),
            ("--nogui", {"action": "store_true", "help": "Run without the GUI."}),
            ("--no-overlay", {"action": "store_true",
                              "help": "Do not start the on-screen overlay."}),
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
        if not getattr(ns, "no_overlay", False):
            start_overlay()
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
        ctx.game_task.cancel()
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
