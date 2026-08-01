"""Keep Empire Earth borderless on a chosen monitor and stop it minimising.

The GOG DirectDraw wrapper already runs the game borderless-windowed
(`presentation=windowed`, `display=desktop`), but it has no monitor setting and
the game minimises itself whenever it loses focus - which makes it useless on a
second screen.

This fixes both from outside the process: it pins the window to the monitor you
choose and, whenever the game minimises, restores it *without stealing focus*
(`SW_SHOWNOACTIVATE`), so it keeps rendering on the second monitor while you
work on the first.

Nothing is injected and no game code is called, so unlike the in-game UI work
this cannot crash the game.

    py world\\empire_earth\\WindowManager.py --list
    py world\\empire_earth\\WindowManager.py --monitor 2
    py world\\empire_earth\\WindowManager.py --monitor 2 --fill --no-minimize
"""

from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes as wt
import subprocess
import sys
import time

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.SetProcessDPIAware()

EXE_NAMES = ("EE-AOC.exe", "Empire Earth.exe")

SW_SHOWNOACTIVATE = 4
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020
MONITORINFOF_PRIMARY = 1


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("rcMonitor", RECT),
                ("rcWork", RECT), ("dwFlags", wt.DWORD)]


def monitors():
    out = []
    PROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HMONITOR, wt.HDC, ctypes.POINTER(RECT), wt.LPARAM)

    def cb(hmon, _hdc, _rc, _lp):
        mi = MONITORINFO()
        mi.cbSize = ctypes.sizeof(MONITORINFO)
        user32.GetMonitorInfoW(hmon, ctypes.byref(mi))
        m = mi.rcMonitor
        out.append({"rect": (m.left, m.top, m.right, m.bottom),
                    "primary": bool(mi.dwFlags & MONITORINFOF_PRIMARY)})
        return True

    user32.EnumDisplayMonitors(None, None, PROC(cb), 0)
    return out


def game_pids():
    try:
        out = subprocess.run(["tasklist", "/fo", "csv", "/nh"], capture_output=True,
                             text=True, creationflags=0x08000000).stdout
    except OSError:
        return set()
    wanted = {n.lower() for n in EXE_NAMES}
    pids = set()
    for line in out.splitlines():
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) >= 2 and parts[0].lower() in wanted:
            pids.add(int(parts[1]))
    return pids


def game_hwnd(pids):
    """The game's main window, minimised or not."""
    found = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def cb(hwnd, _lp):
        owner = wt.DWORD(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value in pids and user32.IsWindowVisible(hwnd):
            title = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, title, 256)
            if title.value.strip():
                found.append(hwnd)
                return False
        return True

    user32.EnumWindows(cb, 0)
    return found[0] if found else None


def desired_rect(hwnd, mon, fill: bool):
    """Where the window should sit: centred on the target monitor.

    Without --fill the window keeps its own size, which matters because the
    menu runs 4:3 while the match runs at desktop resolution - stretching the
    menu to a 16:9 monitor would distort it.
    """
    ml, mt, mr, mb = mon["rect"]
    r = RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    cw, ch = (mr - ml, mb - mt) if fill else (r.right - r.left, r.bottom - r.top)
    # A minimised window reports a tiny stub size; never adopt that.
    if cw < 200 or ch < 200:
        cw, ch = mr - ml, mb - mt
    cw, ch = min(cw, mr - ml), min(ch, mb - mt)
    x = ml + max(0, ((mr - ml) - cw) // 2)
    y = mt + max(0, ((mb - mt) - ch) // 2)
    return x, y, cw, ch


def current_rect(hwnd):
    r = RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right - r.left, r.bottom - r.top


def place(hwnd, mon, fill: bool):
    x, y, cw, ch = desired_rect(hwnd, mon, fill)
    user32.SetWindowPos(hwnd, None, x, y, cw, ch,
                        SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED)
    return x, y, cw, ch


def main():
    ap = argparse.ArgumentParser(description="Empire Earth window manager")
    ap.add_argument("--monitor", type=int, default=0, help="1-based monitor to pin to")
    ap.add_argument("--fill", action="store_true", help="resize to fill that monitor")
    ap.add_argument("--no-minimize", action="store_true", default=True,
                    help="restore the window whenever it minimises (default on)")
    ap.add_argument("--allow-minimize", dest="no_minimize", action="store_false")
    ap.add_argument("--list", action="store_true", help="list monitors and exit")
    ap.add_argument("--interval", type=float, default=0.4)
    args = ap.parse_args()

    mons = monitors()
    if args.list or not args.monitor:
        for i, m in enumerate(mons, 1):
            l, t, r, b = m["rect"]
            print(f"  {i}: {r-l}x{b-t} at ({l},{t})"
                  f"{'  (primary)' if m['primary'] else ''}")
        if args.list:
            return
        if not args.monitor:
            print("\ngive --monitor N to pin the game to one of these")
            return
    if not 1 <= args.monitor <= len(mons):
        sys.exit(f"no monitor {args.monitor}")
    mon = mons[args.monitor - 1]

    print(f"pinning Empire Earth to monitor {args.monitor} "
          f"({'fill' if args.fill else 'keep size'}), "
          f"restore-on-minimise={'on' if args.no_minimize else 'off'}")
    print("Ctrl+C to stop.\n")

    hwnd = None
    last_pids = set()
    restores = 0
    moves = 0
    try:
        while True:
            pids = game_pids()
            if not pids:
                if hwnd:
                    print("game exited; waiting for it to come back")
                hwnd, last_pids = None, set()
                time.sleep(1.0)
                continue
            if hwnd is None or pids != last_pids:
                hwnd = game_hwnd(pids)
                last_pids = pids
                if hwnd:
                    x, y, w, h = place(hwnd, mon, args.fill)
                    print(f"found window 0x{hwnd:X}; placed at ({x},{y}) {w}x{h}")
            if hwnd:
                if not user32.IsWindow(hwnd):
                    hwnd = None
                elif args.no_minimize and user32.IsIconic(hwnd):
                    # SW_SHOWNOACTIVATE brings it back without taking focus, so
                    # whatever you are doing on the other monitor keeps it.
                    user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)
                    place(hwnd, mon, args.fill)
                    restores += 1
                    print(f"restored after minimise (x{restores})")
                elif not user32.IsIconic(hwnd):
                    # The game recreates/resizes its window when moving between
                    # the menu and a match, which puts it back on the primary
                    # monitor. Re-pin whenever it drifts from where we want it.
                    cx, cy, cw, ch = current_rect(hwnd)
                    dx, dy, dw, dh = desired_rect(hwnd, mon, args.fill)
                    if (abs(cx - dx) > 2 or abs(cy - dy) > 2
                            or abs(cw - dw) > 2 or abs(ch - dh) > 2):
                        place(hwnd, mon, args.fill)
                        moves += 1
                        print(f"re-pinned {cw}x{ch} -> ({dx},{dy}) {dw}x{dh} (x{moves})")
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nstopped; the game is left where it is")


if __name__ == "__main__":
    main()
