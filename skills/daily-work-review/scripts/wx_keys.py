"""Only PROCESS_VM_READ | PROCESS_QUERY_INFORMATION on the selected Weixin process."""
import ctypes, struct
from ctypes import wintypes as wt
from pathlib import Path
import wcdb_runtime as wcdb

def load_keys(db, pid):
    DB = Path(db)
    paths = [DB / "contact/contact.db", DB / "session/session.db", DB / "message/message_fts.db"]
    paths += sorted((DB / "message").glob("message_[0-9]*.db"))
    db_files, salt_to_dbs = [], {}
    for p in paths:
        with p.open("rb") as f:
            page = f.read(4096)
        salt = page[:16].hex()
        rel = str(p.relative_to(DB))
        db_files.append((rel, str(p), p.stat().st_size, salt, page))
        salt_to_dbs.setdefault(salt, []).append(rel)

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
    k32.OpenProcess.restype = wt.HANDLE
    k32.ReadProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
    k32.ReadProcessMemory.restype = wt.BOOL
    k32.VirtualQueryEx.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
    k32.VirtualQueryEx.restype = ctypes.c_size_t
    k32.CloseHandle.argtypes = [wt.HANDLE]

    class MBI(ctypes.Structure):
        _fields_ = [
            ("BaseAddress", ctypes.c_uint64), ("AllocationBase", ctypes.c_uint64),
            ("AllocationProtect", wt.DWORD), ("_pad1", wt.DWORD),
            ("RegionSize", ctypes.c_uint64), ("State", wt.DWORD),
            ("Protect", wt.DWORD), ("Type", wt.DWORD), ("_pad2", wt.DWORD),
        ]

    handle = k32.OpenProcess(0x0010 | 0x0400, False, pid)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    def read_mem(addr, size):
        if size <= 0 or size > 2 * 1024 * 1024:
            return b""
        buf = ctypes.create_string_buffer(size)
        got = ctypes.c_size_t()
        k32.ReadProcessMemory(handle, ctypes.c_void_p(addr), buf, size, ctypes.byref(got))
        return buf.raw[:got.value]

    try:
        regions, addr, mbi = [], 0, MBI()
        while addr < 0x0000800000000000:
            if not k32.VirtualQueryEx(handle, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)):
                break
            if mbi.State == 0x1000 and mbi.Protect in {0x02,0x04,0x08,0x20,0x40,0x80} and 0 < mbi.RegionSize < 500 * 1024 * 1024:
                regions.append((mbi.BaseAddress, mbi.RegionSize))
            nxt = mbi.BaseAddress + mbi.RegionSize
            if nxt <= addr:
                break
            addr = nxt
        key_map = {}
        remaining = set(salt_to_dbs)
        stats = wcdb._scan_windows_v411_config_cipher(pid, regions, read_mem, read_mem, db_files, salt_to_dbs, key_map, remaining, lambda s: None)
        result = {rel:{"enc_key":key_map[salt],"salt":salt} for rel,_,_,salt,_ in db_files if salt in key_map}
        return {k.replace("\\", "/"):v for k,v in result.items()}, stats
    finally:
        k32.CloseHandle(handle)

