"""Minimal Win32 process-memory access for the Empire Earth client.

Self-contained (ctypes only) so the apworld has no extra dependencies.
Empire Earth is a 32-bit executable with a fixed image base (no ASLR), so
static addresses taken from one run stay valid on the next.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import struct
import subprocess

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
psapi = ctypes.WinDLL("psapi", use_last_error=True)

# QUERY_INFO | VM_READ | VM_WRITE | VM_OPERATION | CREATE_THREAD
ACCESS = 0x0400 | 0x0010 | 0x0020 | 0x0008 | 0x0002
MEM_COMMIT = 0x1000
MEM_PRIVATE = 0x20000
MEM_MAPPED = 0x40000
MEM_IMAGE = 0x1000000
PAGE_GUARD = 0x100
READABLE = {0x02, 0x04, 0x08, 0x20, 0x40, 0x80}
LIST_MODULES_32BIT = 0x01


class MBI64(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_ulonglong),
        ("AllocationBase", ctypes.c_ulonglong),
        ("AllocationProtect", wt.DWORD),
        ("__a1", wt.DWORD),
        ("RegionSize", ctypes.c_ulonglong),
        ("State", wt.DWORD),
        ("Protect", wt.DWORD),
        ("Type", wt.DWORD),
        ("__a2", wt.DWORD),
    ]


k32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
k32.OpenProcess.restype = wt.HANDLE
k32.CloseHandle.argtypes = [wt.HANDLE]
k32.CloseHandle.restype = wt.BOOL
k32.ReadProcessMemory.argtypes = [
    wt.HANDLE, ctypes.c_ulonglong, ctypes.c_void_p, ctypes.c_size_t,
    ctypes.POINTER(ctypes.c_size_t),
]
k32.ReadProcessMemory.restype = wt.BOOL
k32.WriteProcessMemory.argtypes = [
    wt.HANDLE, ctypes.c_ulonglong, ctypes.c_void_p, ctypes.c_size_t,
    ctypes.POINTER(ctypes.c_size_t),
]
k32.WriteProcessMemory.restype = wt.BOOL
k32.VirtualQueryEx.argtypes = [
    wt.HANDLE, ctypes.c_ulonglong, ctypes.POINTER(MBI64), ctypes.c_size_t,
]
k32.VirtualQueryEx.restype = ctypes.c_size_t
k32.VirtualAllocEx.argtypes = [
    wt.HANDLE, ctypes.c_ulonglong, ctypes.c_size_t, wt.DWORD, wt.DWORD,
]
k32.VirtualAllocEx.restype = ctypes.c_ulonglong
k32.VirtualProtectEx.argtypes = [
    wt.HANDLE, ctypes.c_ulonglong, ctypes.c_size_t, wt.DWORD,
    ctypes.POINTER(wt.DWORD),
]
k32.VirtualProtectEx.restype = wt.BOOL
k32.VirtualFreeEx.argtypes = [
    wt.HANDLE, ctypes.c_ulonglong, ctypes.c_size_t, wt.DWORD,
]
k32.VirtualFreeEx.restype = wt.BOOL
k32.CreateRemoteThread.argtypes = [
    wt.HANDLE, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_ulonglong,
    ctypes.c_ulonglong, wt.DWORD, ctypes.POINTER(wt.DWORD),
]
k32.CreateRemoteThread.restype = wt.HANDLE
k32.WaitForSingleObject.argtypes = [wt.HANDLE, wt.DWORD]
k32.WaitForSingleObject.restype = wt.DWORD
k32.GetExitCodeThread.argtypes = [wt.HANDLE, ctypes.POINTER(wt.DWORD)]
k32.GetExitCodeThread.restype = wt.BOOL

MEM_COMMIT_RESERVE = 0x1000 | 0x2000
MEM_RELEASE = 0x8000
PAGE_EXECUTE_READWRITE = 0x40
PROCESS_CREATE_THREAD = 0x0002
WAIT_OBJECT_0 = 0x0


def find_pids(*names: str) -> list[tuple[int, str]]:
    """[(pid, exe_name)] for running processes matching any of `names`."""
    try:
        out = subprocess.run(
            ["tasklist", "/fo", "csv", "/nh"],
            capture_output=True,
            text=True,
            creationflags=0x08000000,  # CREATE_NO_WINDOW
        ).stdout
    except OSError:
        return []
    wanted = {n.lower() for n in names}
    hits = []
    for line in out.splitlines():
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) >= 2 and parts[0].lower() in wanted:
            hits.append((int(parts[1]), parts[0]))
    return hits


class ProcessClosed(Exception):
    pass


class GameProcess:
    def __init__(self, pid: int, exe: str = ""):
        self.pid = pid
        self.exe = exe
        self.h = k32.OpenProcess(ACCESS, False, pid)
        if not self.h:
            raise ProcessClosed(
                f"OpenProcess({pid}) failed with error {ctypes.get_last_error()}"
            )

    def close(self):
        if self.h:
            k32.CloseHandle(self.h)
            self.h = None

    @property
    def alive(self) -> bool:
        if not self.h:
            return False
        code = wt.DWORD(0)
        k32.GetExitCodeProcess(self.h, ctypes.byref(code))
        return code.value == 259  # STILL_ACTIVE

    # --- raw ------------------------------------------------------------

    def read(self, addr: int, size: int) -> bytes | None:
        if not self.h or addr <= 0 or addr > 0x7FFFFFFF:
            return None
        buf = ctypes.create_string_buffer(size)
        got = ctypes.c_size_t(0)
        if not k32.ReadProcessMemory(self.h, addr, buf, size, ctypes.byref(got)):
            return None
        return buf.raw[: got.value] if got.value == size else None

    def write(self, addr: int, data: bytes) -> bool:
        if not self.h:
            return False
        buf = ctypes.create_string_buffer(data, len(data))
        put = ctypes.c_size_t(0)
        ok = k32.WriteProcessMemory(self.h, addr, buf, len(data), ctypes.byref(put))
        return bool(ok) and put.value == len(data)

    # --- typed ----------------------------------------------------------

    def read_u32(self, addr):
        b = self.read(addr, 4)
        return struct.unpack("<I", b)[0] if b else None

    def read_i32(self, addr):
        b = self.read(addr, 4)
        return struct.unpack("<i", b)[0] if b else None

    def read_f32(self, addr):
        b = self.read(addr, 4)
        return struct.unpack("<f", b)[0] if b else None

    def read_f64(self, addr):
        b = self.read(addr, 8)
        return struct.unpack("<d", b)[0] if b else None

    def read_value(self, addr, kind: str):
        return {
            "i32": self.read_i32,
            "u32": self.read_u32,
            "f32": self.read_f32,
            "f64": self.read_f64,
        }[kind](addr)

    def write_value(self, addr, kind: str, value) -> bool:
        fmt = {"i32": "<i", "u32": "<I", "f32": "<f", "f64": "<d"}[kind]
        cast = int if kind in ("i32", "u32") else float
        return self.write(addr, struct.pack(fmt, cast(value)))

    # --- pointer chains --------------------------------------------------

    def resolve(self, base: int, offsets: list[int]) -> int | None:
        """Walk a Cheat-Engine style pointer chain: [[base]+o0]+o1 ..."""
        addr = base
        for i, off in enumerate(offsets):
            ptr = self.read_u32(addr)
            if not ptr:
                return None
            addr = ptr + off
        return addr

    # --- remote allocation and execution ---------------------------------

    def alloc(self, size: int) -> int | None:
        """Reserve+commit RWX memory inside the target."""
        addr = k32.VirtualAllocEx(
            self.h, 0, size, MEM_COMMIT_RESERVE, PAGE_EXECUTE_READWRITE
        )
        return addr or None

    def free(self, addr: int) -> bool:
        return bool(k32.VirtualFreeEx(self.h, addr, 0, MEM_RELEASE))

    def protect(self, addr: int, size: int,
                flags: int = PAGE_EXECUTE_READWRITE) -> int | None:
        """Change page protection in the target. Returns the previous flags.

        Needed to write to the game's code section, which is read-only. The
        change is to this process's pages only and disappears with it.
        """
        old = wt.DWORD(0)
        if not k32.VirtualProtectEx(self.h, addr, size, flags, ctypes.byref(old)):
            return None
        return old.value

    def run_thread(self, entry: int, arg: int = 0, timeout_ms: int = 5000):
        """Run `entry` on a new thread in the target. Returns its exit code.

        Returns None if the thread could not be created or did not finish in
        time; the caller must not free the code page in that case.
        """
        tid = wt.DWORD(0)
        th = k32.CreateRemoteThread(
            self.h, None, 0, entry, arg, 0, ctypes.byref(tid)
        )
        if not th:
            return None
        try:
            if k32.WaitForSingleObject(th, timeout_ms) != WAIT_OBJECT_0:
                return None
            code = wt.DWORD(0)
            k32.GetExitCodeThread(th, ctypes.byref(code))
            return code.value
        finally:
            k32.CloseHandle(th)

    def module_base(self, name: str) -> int | None:
        want = name.lower()
        for path, base, _size in self.modules():
            if path.lower().endswith(want):
                return base
        return None

    # --- modules / regions ------------------------------------------------

    def modules(self) -> list[tuple[str, int, int]]:
        arr = (ctypes.c_ulonglong * 512)()
        need = wt.DWORD(0)
        if not psapi.EnumProcessModulesEx(
            self.h, ctypes.byref(arr), ctypes.sizeof(arr),
            ctypes.byref(need), LIST_MODULES_32BIT,
        ):
            return []

        class MODINFO(ctypes.Structure):
            _fields_ = [
                ("lpBaseOfDll", ctypes.c_ulonglong),
                ("SizeOfImage", wt.DWORD),
                ("EntryPoint", ctypes.c_ulonglong),
            ]

        out, name, mi = [], ctypes.create_unicode_buffer(260), MODINFO()
        for i in range(min(need.value // 8, 512)):
            hm = ctypes.c_ulonglong(arr[i])
            psapi.GetModuleFileNameExW(self.h, hm, name, 260)
            psapi.GetModuleInformation(self.h, hm, ctypes.byref(mi), ctypes.sizeof(mi))
            out.append((name.value, mi.lpBaseOfDll, mi.SizeOfImage))
        return out

    def regions(self, want_image=True, want_private=True, want_mapped=True):
        mbi = MBI64()
        addr = 0
        while addr < 0x7FFFFFFF:
            if not k32.VirtualQueryEx(self.h, addr, ctypes.byref(mbi), ctypes.sizeof(mbi)):
                break
            if mbi.RegionSize == 0:
                break
            wanted = {
                MEM_IMAGE: want_image,
                MEM_PRIVATE: want_private,
                MEM_MAPPED: want_mapped,
            }.get(mbi.Type, False)
            if (
                wanted
                and mbi.State == MEM_COMMIT
                and (mbi.Protect & 0xFF) in READABLE
                and not (mbi.Protect & PAGE_GUARD)
            ):
                yield mbi.BaseAddress, mbi.RegionSize
            addr = mbi.BaseAddress + mbi.RegionSize

    def snapshot(self, **kw) -> list[tuple[int, bytes]]:
        """Read matching regions in bulk, as [(base, data), ...].

        Heap objects the game allocates - tech tree nodes among them - live in
        MEM_PRIVATE, so a scan for one can skip the image and mapped files.
        """
        out = []
        for base, size in self.regions(**kw):
            data = self.read(base, size)
            if data:
                out.append((base, data))
        return out


def attach(*exe_names: str) -> GameProcess | None:
    for pid, exe in find_pids(*exe_names):
        try:
            return GameProcess(pid, exe)
        except ProcessClosed:
            continue
    return None
