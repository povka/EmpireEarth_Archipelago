"""Win32 process memory access helpers for Empire Earth (32-bit, no ASLR).

Runs under 64-bit Python; the target is a 32-bit process, so every address
fits in 32 bits but the Win32 API is used with 64-bit pointer types.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import struct

k32 = ctypes.WinDLL("kernel32", use_last_error=True)

PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010
PROCESS_VM_WRITE = 0x0020
PROCESS_VM_OPERATION = 0x0008
ACCESS = (
    PROCESS_QUERY_INFORMATION | PROCESS_VM_READ | PROCESS_VM_WRITE | PROCESS_VM_OPERATION
)

MEM_COMMIT = 0x1000
MEM_IMAGE = 0x1000000
MEM_MAPPED = 0x40000
MEM_PRIVATE = 0x20000

PAGE_GUARD = 0x100
PAGE_NOACCESS = 0x01
READABLE = {0x02, 0x04, 0x08, 0x20, 0x40, 0x80}  # R, RW, WC, XR, XRW, XWC


class MEMORY_BASIC_INFORMATION64(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_ulonglong),
        ("AllocationBase", ctypes.c_ulonglong),
        ("AllocationProtect", wt.DWORD),
        ("__alignment1", wt.DWORD),
        ("RegionSize", ctypes.c_ulonglong),
        ("State", wt.DWORD),
        ("Protect", wt.DWORD),
        ("Type", wt.DWORD),
        ("__alignment2", wt.DWORD),
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
    wt.HANDLE, ctypes.c_ulonglong, ctypes.POINTER(MEMORY_BASIC_INFORMATION64),
    ctypes.c_size_t,
]
k32.VirtualQueryEx.restype = ctypes.c_size_t
k32.IsWow64Process.argtypes = [wt.HANDLE, ctypes.POINTER(wt.BOOL)]
k32.IsWow64Process.restype = wt.BOOL


psapi = ctypes.WinDLL("psapi", use_last_error=True)
LIST_MODULES_32BIT = 0x01
LIST_MODULES_ALL = 0x03


def find_pids(*names: str) -> list[tuple[int, str]]:
    """Return (pid, exe_name) for running processes whose name matches."""
    import subprocess

    out = subprocess.run(
        ["tasklist", "/fo", "csv", "/nh"], capture_output=True, text=True
    ).stdout
    hits = []
    wanted = {n.lower() for n in names}
    for line in out.splitlines():
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) < 2:
            continue
        exe, pid = parts[0], parts[1]
        if exe.lower() in wanted:
            hits.append((int(pid), exe))
    return hits


class Proc:
    """A handle onto a running process."""

    def __init__(self, pid: int):
        self.pid = pid
        self.h = k32.OpenProcess(ACCESS, False, pid)
        if not self.h:
            raise OSError(
                f"OpenProcess({pid}) failed: {ctypes.get_last_error()} "
                "(run this from an elevated shell if the game is elevated)"
            )
        # A WOW64 process is 32-bit; its user space stops at 2 GiB.
        wow = wt.BOOL(0)
        k32.IsWow64Process(self.h, ctypes.byref(wow))
        self.is32 = bool(wow.value)
        self.addr_limit = 0x7FFF_FFFF if self.is32 else 0x7FFF_FFFF_FFFF

    def close(self):
        if self.h:
            k32.CloseHandle(self.h)
            self.h = None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()

    # --- raw access -----------------------------------------------------

    def read(self, addr: int, size: int) -> bytes | None:
        buf = ctypes.create_string_buffer(size)
        got = ctypes.c_size_t(0)
        ok = k32.ReadProcessMemory(self.h, addr, buf, size, ctypes.byref(got))
        if not ok or got.value == 0:
            return None
        return buf.raw[: got.value]

    def write(self, addr: int, data: bytes) -> bool:
        buf = ctypes.create_string_buffer(data, len(data))
        put = ctypes.c_size_t(0)
        ok = k32.WriteProcessMemory(self.h, addr, buf, len(data), ctypes.byref(put))
        return bool(ok) and put.value == len(data)

    # --- typed access ---------------------------------------------------

    def read_i32(self, addr):
        b = self.read(addr, 4)
        return struct.unpack("<i", b)[0] if b and len(b) == 4 else None

    def read_u32(self, addr):
        b = self.read(addr, 4)
        return struct.unpack("<I", b)[0] if b and len(b) == 4 else None

    def read_f32(self, addr):
        b = self.read(addr, 4)
        return struct.unpack("<f", b)[0] if b and len(b) == 4 else None

    def read_f64(self, addr):
        b = self.read(addr, 8)
        return struct.unpack("<d", b)[0] if b and len(b) == 8 else None

    def write_i32(self, addr, v):
        return self.write(addr, struct.pack("<i", int(v)))

    def write_f32(self, addr, v):
        return self.write(addr, struct.pack("<f", float(v)))

    def write_f64(self, addr, v):
        return self.write(addr, struct.pack("<d", float(v)))

    def resolve(self, base: int, offsets: list[int]) -> int | None:
        """Walk a Cheat-Engine style pointer chain: [[base]+o0]+o1 ..."""
        addr = base
        for off in offsets:
            ptr = self.read_u32(addr)
            if not ptr:
                return None
            addr = ptr + off
        return addr

    # --- modules --------------------------------------------------------

    def modules(self) -> list[tuple[str, int, int]]:
        """Return [(path, base, size), ...] for modules loaded in the target."""
        arr = (ctypes.c_ulonglong * 1024)()
        need = wt.DWORD(0)
        flag = LIST_MODULES_32BIT if self.is32 else LIST_MODULES_ALL
        ok = psapi.EnumProcessModulesEx(
            self.h, ctypes.byref(arr), ctypes.sizeof(arr), ctypes.byref(need), flag
        )
        if not ok:
            return []
        out = []
        name = ctypes.create_unicode_buffer(260)

        class MODINFO(ctypes.Structure):
            _fields_ = [
                ("lpBaseOfDll", ctypes.c_ulonglong),
                ("SizeOfImage", wt.DWORD),
                ("EntryPoint", ctypes.c_ulonglong),
            ]

        mi = MODINFO()
        for i in range(min(need.value // 8, 1024)):
            hmod = arr[i]
            psapi.GetModuleFileNameExW(self.h, ctypes.c_ulonglong(hmod), name, 260)
            psapi.GetModuleInformation(
                self.h, ctypes.c_ulonglong(hmod), ctypes.byref(mi), ctypes.sizeof(mi)
            )
            out.append((name.value, mi.lpBaseOfDll, mi.SizeOfImage))
        return out

    def module_base(self, name: str) -> int | None:
        want = name.lower()
        for path, base, _size in self.modules():
            if path.lower().endswith(want):
                return base
        return None

    def main_module(self) -> tuple[str, int, int] | None:
        mods = self.modules()
        return mods[0] if mods else None

    # --- region enumeration --------------------------------------------

    def regions(self, want_image=True, want_private=True, want_mapped=False):
        """Yield (base, size, protect, type) for committed readable regions."""
        mbi = MEMORY_BASIC_INFORMATION64()
        addr = 0
        limit = self.addr_limit
        while addr < limit:
            n = k32.VirtualQueryEx(self.h, addr, ctypes.byref(mbi), ctypes.sizeof(mbi))
            if not n:
                break
            base, size = mbi.BaseAddress, mbi.RegionSize
            if size == 0:
                break
            prot = mbi.Protect
            if (
                mbi.State == MEM_COMMIT
                and (prot & 0xFF) in READABLE
                and not (prot & PAGE_GUARD)
            ):
                t = mbi.Type
                if (
                    (t == MEM_IMAGE and want_image)
                    or (t == MEM_PRIVATE and want_private)
                    or (t == MEM_MAPPED and want_mapped)
                ):
                    yield base, size, prot, t
            addr = base + size

    def snapshot(self, **kw) -> list[tuple[int, bytes]]:
        """Read every matching region into memory. Returns [(base, data), ...]."""
        out = []
        for base, size, _prot, _t in self.regions(**kw):
            data = self.read(base, size)
            if data:
                out.append((base, data))
        return out


def scan_bytes(data: bytes, base: int, needle: bytes, align: int = 4) -> list[int]:
    """Return absolute addresses of every aligned occurrence of `needle`."""
    hits = []
    i = data.find(needle)
    while i != -1:
        if (base + i) % align == 0:
            hits.append(base + i)
        i = data.find(needle, i + 1)
    return hits


def enc_i32(v):
    return struct.pack("<i", int(v))


def enc_f32(v):
    return struct.pack("<f", float(v))


def enc_f64(v):
    return struct.pack("<d", float(v))
