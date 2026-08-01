"""A click-through overlay that shows Archipelago messages over Empire Earth.

The game's shipped GOG DirectDraw wrapper is configured with
`presentation=windowed` / `display=desktop`, i.e. borderless rather than
exclusive fullscreen, so an ordinary always-on-top window composites over it.

This deliberately avoids the game's own UI entirely: no code injection, no
vtable calls, nothing that can crash the game. The client appends lines to a
feed file; this process renders them and fades them out.

Run standalone:
    py world\\empire_earth\\Overlay.py --demo

Only tkinter and ctypes are used, so it works both inside Archipelago's
frozen Python and a plain system Python.
"""

from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes as wt
import json
import os
import sys
import time
import tkinter as tk

EXE_NAMES = ("EE-AOC.exe", "Empire Earth.exe")

# Transparent key colour: anything drawn in this exact colour becomes a hole
# in the window, and Windows also routes clicks through it.
CHROMA = "#000001"

user32 = ctypes.WinDLL("user32", use_last_error=True)
GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


def game_window(exe_names=EXE_NAMES):
    """(hwnd, rect) of the game's visible window, or (None, None)."""
    import subprocess

    try:
        out = subprocess.run(
            ["tasklist", "/fo", "csv", "/nh"], capture_output=True, text=True,
            creationflags=0x08000000,
        ).stdout
    except OSError:
        return None, None
    wanted = {n.lower() for n in exe_names}
    pids = set()
    for line in out.splitlines():
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) >= 2 and parts[0].lower() in wanted:
            pids.add(int(parts[1]))
    if not pids:
        return None, None

    found = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def cb(hwnd, _lp):
        owner = wt.DWORD(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value in pids and user32.IsWindowVisible(hwnd):
            r = RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(r))
            if r.right - r.left > 200 and r.bottom - r.top > 200:
                found.append((hwnd, (r.left, r.top, r.right, r.bottom)))
                return False
        return True

    user32.EnumWindows(cb, 0)
    return found[0] if found else (None, None)


def claim_single_instance() -> bool:
    """Return False if another overlay is already running.

    Two overlays draw on top of each other and look like one broken window, so
    a second instance refuses to start rather than stacking.
    """
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wt.BOOL, wt.LPCWSTR]
    kernel32.CreateMutexW.restype = wt.HANDLE
    handle = kernel32.CreateMutexW(None, True, "Archipelago.EmpireEarth.Overlay")
    if not handle:
        return True                      # cannot tell; allow it
    ERROR_ALREADY_EXISTS = 183
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        return False
    # Deliberately leaked: the mutex must outlive this call for the process's
    # whole lifetime.
    globals()["_INSTANCE_MUTEX"] = handle
    return True


def feed_path() -> str:
    """Where the client writes and the overlay reads."""
    try:
        import Utils  # available inside Archipelago

        folder = os.path.join(Utils.user_path("data"), "empire_earth")
    except Exception:
        folder = os.path.join(
            os.environ.get("PROGRAMDATA", os.path.expanduser("~")),
            "Archipelago", "data", "empire_earth",
        )
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, "feed.jsonl")


def publish(text: str, kind: str = "item", path: str | None = None) -> None:
    """Append one line to the feed. Safe to call from anywhere; never raises."""
    try:
        with open(path or feed_path(), "a", encoding="utf-8") as f:
            f.write(json.dumps({"t": time.time(), "kind": kind, "text": text}) + "\n")
    except OSError:
        pass


def publish_config(path: str | None = None, **settings) -> None:
    """Push overlay settings (e.g. sound=False) down the same feed.

    The overlay runs as its own process, so YAML options reach it as a control
    record rather than a command-line flag.
    """
    try:
        with open(path or feed_path(), "a", encoding="utf-8") as f:
            rec = {"t": time.time(), "kind": "config"}
            rec.update(settings)
            f.write(json.dumps(rec) + "\n")
    except OSError:
        pass


KIND_COLOURS = {
    "item": "#7ee787",
    "sent": "#79c0ff",
    "info": "#e6edf3",
    "warn": "#f0883e",
}


class Overlay:
    def __init__(self, path: str, hold: float, fade: float, anchor: str,
                 width: int, font_size: int, solid: bool = False,
                 always: bool = False, sound: str | None = None):
        self.path = path
        self.hold = hold
        self.fade = fade
        self.anchor = anchor
        self.width = width
        self.offset = 0
        self.solid = solid
        self.last_rect: tuple[int, int, int, int] | None = None
        self.always = always
        self.sound = sound
        # Kept so a config record can switch the sound back on again.
        self.default_sound = sound
        self.shown = True
        self.lines: list[tuple[float, str, str]] = []

        # `solid` draws an opaque panel instead of chroma-keying it away. It
        # makes the overlay obvious while positioning it, at the cost of
        # covering the game.
        bg = "#101418" if solid else CHROMA

        self.root = tk.Tk()
        self.root.title("Archipelago - Empire Earth")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.config(bg=bg)
        if not solid:
            self.root.attributes("-transparentcolor", CHROMA)
        else:
            self.root.attributes("-alpha", 0.85)
        self.root.geometry(f"{width}x400+40+40")

        self.canvas = tk.Canvas(
            self.root, bg=bg, highlightthickness=0, bd=0,
            width=width, height=400,
        )
        self.canvas.pack(fill="both", expand=True)
        self.font = ("Segoe UI", font_size, "bold")

        self.root.update_idletasks()
        self._make_click_through()
        # Start at end-of-file so a stale feed does not replay on startup.
        try:
            self.offset = os.path.getsize(path)
        except OSError:
            self.offset = 0

    def _make_click_through(self):
        hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(
            hwnd, GWL_EXSTYLE,
            style | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW,
        )

    # --- feed -----------------------------------------------------------

    def poll_feed(self):
        try:
            size = os.path.getsize(self.path)
        except OSError:
            return
        if size < self.offset:      # file was truncated or replaced
            self.offset = 0
        if size == self.offset:
            return
        # Read in binary and track the offset in bytes: calling tell() after
        # iterating a text file raises "telling position disabled by next()",
        # which silently ate every line here before.
        try:
            with open(self.path, "rb") as f:
                f.seek(self.offset)
                chunk = f.read(size - self.offset)
        except OSError:
            return
        self.offset = size
        before = len(self.lines)
        for line in chunk.decode("utf-8", "replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if rec.get("kind") == "config":
                # Control record, not something to display.
                if "sound" in rec:
                    self.sound = self.default_sound if rec["sound"] else None
                continue
            kind = str(rec.get("kind", "info"))
            text = str(rec.get("text", ""))
            # Drop an immediate repeat of the line already on screen: a client
            # that re-checks its state can publish the same warning twice.
            if self.lines and self.lines[-1][1] == kind and self.lines[-1][2] == text:
                continue
            self.lines.append((time.time(), kind, text))
        if len(self.lines) > before:
            self.play_sound()
        del self.lines[:-12]

    def play_sound(self):
        """One chime per batch of arrivals, never per line."""
        if not self.sound:
            return
        try:
            import winsound

            winsound.PlaySound(
                self.sound,
                winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT,
            )
        except Exception:
            self.sound = None  # do not keep retrying a broken device or file

    # --- drawing ---------------------------------------------------------

    def set_shown(self, shown: bool):
        if shown == self.shown:
            return
        self.shown = shown
        if shown:
            self.root.deiconify()
            self.root.attributes("-topmost", True)
        else:
            self.root.withdraw()

    def reposition(self):
        _hwnd, rect = game_window()

        # The overlay belongs to the game: hide it whenever the game is not on
        # screen. game_window() already ignores the minimised stub, so this
        # covers "not running", "minimised" and "still loading" alike.
        if not rect and not self.always:
            self.set_shown(False)
            return
        self.set_shown(True)

        if rect:
            self.last_rect = rect
        elif self.last_rect:
            # Stay put rather than snapping back to a corner of the primary
            # monitor if the game briefly disappears.
            return
        if rect:
            l, t, r, b = rect
        else:
            l, t = 40, 40
            r = l + self.width
            b = t + 400
        h = 400
        if self.anchor == "topleft":
            x, y = l + 24, t + 90
        elif self.anchor == "topright":
            x, y = r - self.width - 24, t + 90
        elif self.anchor == "bottomleft":
            x, y = l + 24, b - h - 120
        else:
            x, y = r - self.width - 24, b - h - 120
        self.root.geometry(f"{self.width}x{h}+{max(x, 0)}+{max(y, 0)}")

    def redraw(self):
        now = time.time()
        self.canvas.delete("all")
        alive = []
        y = 0
        for born, kind, text in self.lines:
            age = now - born
            if age > self.hold + self.fade:
                continue
            alive.append((born, kind, text))
        self.lines = alive

        for born, kind, text in self.lines:
            age = now - born
            # tkinter text has no per-item alpha, so fade by stepping the
            # colour toward the background instead.
            k = 1.0 if age < self.hold else max(0.0, 1.0 - (age - self.hold) / self.fade)
            base = KIND_COLOURS.get(kind, KIND_COLOURS["info"])
            rgb = tuple(int(base[i:i + 2], 16) for i in (1, 3, 5))
            faded = "#%02x%02x%02x" % tuple(max(2, int(c * k)) for c in rgb)
            # A single drop shadow, not a surrounding outline: drawing four
            # offset copies made bold text look doubled rather than outlined.
            wrap = max(80, self.width - 24)
            self.canvas.create_text(
                13, y + 1, anchor="nw", text=text,
                fill="#000000", font=self.font, width=wrap,
            )
            item = self.canvas.create_text(
                12, y, anchor="nw", text=text, fill=faded,
                font=self.font, width=wrap,
            )
            # Advance by the rendered height so wrapped lines do not overlap
            # the next message.
            box = self.canvas.bbox(item)
            y += (box[3] - box[1] if box else self.font[1] + 4) + 6

    def tick(self):
        # One bad frame must not kill the timer chain: an unhandled exception
        # in a Tk callback stops it being rescheduled, which looks exactly like
        # "the overlay is up but never shows anything".
        try:
            self.poll_feed()
            self.reposition()
            self.redraw()
        except Exception:
            import traceback

            traceback.print_exc()
        self.root.after(100, self.tick)

    def run(self):
        self.root.after(100, self.tick)
        self.root.mainloop()


def main(argv=None):
    """Entry point. `argv` is explicit so the client can start the overlay in a
    child process without argparse seeing the client's own arguments."""
    ap = argparse.ArgumentParser(description="Archipelago overlay for Empire Earth")
    ap.add_argument("--feed", default=None)
    ap.add_argument("--hold", type=float, default=10.0, help="seconds fully visible")
    ap.add_argument("--sound", help="WAV to play on each new message")
    ap.add_argument("--no-sound", action="store_true")
    ap.add_argument("--fade", type=float, default=2.5, help="seconds fading out")
    ap.add_argument("--anchor", default="topleft",
                    choices=("topleft", "topright", "bottomleft", "bottomright"))
    ap.add_argument("--width", type=int, default=520)
    ap.add_argument("--font-size", type=int, default=13)
    ap.add_argument("--demo", action="store_true",
                    help="publish sample lines and show them")
    ap.add_argument("--solid", action="store_true",
                    help="opaque panel instead of chroma-key; easier to spot while positioning")
    ap.add_argument("--always", action="store_true",
                    help="stay visible even when Empire Earth is not on screen")
    args = ap.parse_args(argv)

    if not claim_single_instance():
        print("An Empire Earth overlay is already running; not starting a second one.")
        return

    path = args.feed or feed_path()
    if args.demo:
        publish("Connected to multiworld", "info", path)
        publish("Received Food Bundle: +500 Food", "item", path)
        publish("Received Iron Bundle: +500 Iron", "item", path)
        publish("Sent Build Barracks", "sent", path)

    print(f"overlay feed: {path}")

    sound = None
    if not args.no_sound:
        sound = args.sound
        if not sound:
            # Extracted once from the player's own install; see Assets.py.
            try:
                try:
                    from .Assets import ensure_sound
                except ImportError:
                    from Assets import ensure_sound
                sound = ensure_sound(os.path.dirname(path))
            except Exception as e:
                print(f"sound unavailable: {e}")
        print(f"overlay sound: {sound or 'none'}")

    ov = Overlay(path, args.hold, args.fade, args.anchor, args.width,
                 args.font_size, args.solid, args.always, sound)
    if args.demo:
        ov.offset = 0   # replay the demo lines we just wrote
    ov.run()


if __name__ == "__main__":
    main()
