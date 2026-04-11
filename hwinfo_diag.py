"""
HWiNFO shared memory diagnostic.
Run: python hwinfo_diag.py
"""
import ctypes
import ctypes.wintypes
import struct

k32 = ctypes.windll.kernel32
k32.OpenFileMappingW.restype  = ctypes.wintypes.HANDLE
k32.OpenFileMappingW.argtypes = [ctypes.wintypes.DWORD, ctypes.wintypes.BOOL, ctypes.wintypes.LPCWSTR]
k32.MapViewOfFile.restype     = ctypes.c_void_p
k32.MapViewOfFile.argtypes    = [ctypes.wintypes.HANDLE, ctypes.wintypes.DWORD,
                                  ctypes.wintypes.DWORD, ctypes.wintypes.DWORD, ctypes.c_size_t]
k32.UnmapViewOfFile.restype   = ctypes.wintypes.BOOL
k32.UnmapViewOfFile.argtypes  = [ctypes.c_void_p]
k32.CloseHandle.restype       = ctypes.wintypes.BOOL
k32.CloseHandle.argtypes      = [ctypes.wintypes.HANDLE]
k32.GetLastError.restype      = ctypes.wintypes.DWORD

FILE_MAP_READ = 0x0004

# Error code reference
ERRORS = {
    2:   "ERROR_FILE_NOT_FOUND — mapping does not exist (HWiNFO sensor window not open?)",
    5:   "ERROR_ACCESS_DENIED — mapping exists but this process can't open it",
    6:   "ERROR_INVALID_HANDLE",
    87:  "ERROR_INVALID_PARAMETER",
    183: "ERROR_ALREADY_EXISTS — mapping exists (this would actually be OK in CreateFileMapping)",
}

names_to_try = [
    "Global\\HWiNFO_SENS_SM2",
    "Local\\HWiNFO_SENS_SM2",
    "HWiNFO_SENS_SM2",
    "Global\\HWiNFO_SENS_SM",
]

print("=" * 60)
print("HWiNFO Shared Memory Diagnostic")
print("=" * 60)

for name in names_to_try:
    h = k32.OpenFileMappingW(FILE_MAP_READ, False, name)
    err = k32.GetLastError()
    if h:
        print(f"\n[FOUND] Name: {name!r}")
        print(f"  HANDLE: {h}")

        addr = k32.MapViewOfFile(h, FILE_MAP_READ, 0, 0, 0)
        if addr:
            # Read first 44 bytes (header)
            raw = ctypes.string_at(addr, 44)
            sig, ver, rev = struct.unpack_from("<III", raw, 0)
            print(f"  Signature: 0x{sig:08X}  (expected 0x53695748 = 'HWiS')")
            print(f"  Version: {ver}  Revision: {rev}")
            if sig == 0x53695748:
                print(f"  ✓ Valid HWiNFO shared memory!")
                # Read full header
                (sig2, version, revision, poll_time,
                 off_sensor, sz_sensor, num_sensor,
                 off_reading, sz_reading, num_reading) = struct.unpack("<IIIqIIIIII", raw)
                print(f"  Sensors: {num_sensor}  Readings: {num_reading}")
                print(f"  sz_sensor={sz_sensor}  sz_reading={sz_reading}")
                print(f"  Total size needed: {off_reading + sz_reading * num_reading} bytes")
            else:
                print(f"  ✗ Wrong signature — not HWiNFO data")
            k32.UnmapViewOfFile(ctypes.c_void_p(addr))
        else:
            map_err = k32.GetLastError()
            print(f"  MapViewOfFile FAILED — error {map_err}: {ERRORS.get(map_err, 'unknown')}")
        k32.CloseHandle(h)
    else:
        desc = ERRORS.get(err, "unknown error")
        print(f"[MISS]  Name: {name!r} — error {err}: {desc}")

print("\n" + "=" * 60)
print("If all names show ERROR_FILE_NOT_FOUND (error 2):")
print("  → HWiNFO sensor monitoring window is NOT open.")
print("  → Open HWiNFO64, then open the Sensors window (F6 or Sensors button).")
print("  → Shared memory is only populated while the sensor window is active.")
print("=" * 60)
