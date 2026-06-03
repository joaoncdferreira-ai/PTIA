import ctypes
from ctypes import wintypes
import os
import sys

# Load DLLs
rstrtmgr = ctypes.WinDLL('rstrtmgr')
kernel32 = ctypes.WinDLL('kernel32')

CCH_RM_MAX_APP_NAME = 255
CCH_RM_MAX_SVC_NAME = 63

# Structs
class RM_UNIQUE_PROCESS(ctypes.Structure):
    _fields_ = [
        ("dwProcessId", wintypes.DWORD),
        ("ProcessStartTime", wintypes.FILETIME)
    ]

class RM_PROCESS_INFO(ctypes.Structure):
    _fields_ = [
        ("Process", RM_UNIQUE_PROCESS),
        ("strAppName", wintypes.WCHAR * (CCH_RM_MAX_APP_NAME + 1)),
        ("strServiceShortName", wintypes.WCHAR * (CCH_RM_MAX_SVC_NAME + 1)),
        ("ApplicationType", ctypes.c_int),
        ("AppStatus", wintypes.DWORD),
        ("TSSessionId", wintypes.DWORD),
        ("bGracefulShutdown", wintypes.BOOL)
    ]

def get_locking_processes(file_path):
    dwSession = wintypes.DWORD(0)
    szSessionKey = ctypes.create_unicode_buffer(32 + 1)
    
    # Start Session
    res = rstrtmgr.RmStartSession(ctypes.byref(dwSession), 0, szSessionKey)
    if res != 0:
        print(f"RmStartSession failed with error {res}")
        return []
        
    try:
        # Register resource
        path_array = (wintypes.LPCWSTR * 1)(file_path)
        res = rstrtmgr.RmRegisterResources(dwSession, 1, path_array, 0, None, 0, None)
        if res != 0:
            print(f"RmRegisterResources failed with error {res}")
            return []
            
        # Get List size
        pnProcInfoNeeded = wintypes.DWORD(0)
        pnProcInfo = wintypes.DWORD(0)
        dwRebootReasons = wintypes.DWORD(0)
        
        res = rstrtmgr.RmGetList(dwSession, ctypes.byref(pnProcInfoNeeded), ctypes.byref(pnProcInfo), None, ctypes.byref(dwRebootReasons))
        if res != 0 and res != 234:  # ERROR_MORE_DATA is 234
            print(f"RmGetList (size check) failed with error {res}")
            return []
            
        if pnProcInfoNeeded.value == 0:
            return []
            
        # Allocate and get processes
        pnProcInfo.value = pnProcInfoNeeded.value
        proc_info_array = (RM_PROCESS_INFO * pnProcInfo.value)()
        res = rstrtmgr.RmGetList(dwSession, ctypes.byref(pnProcInfoNeeded), ctypes.byref(pnProcInfo), proc_info_array, ctypes.byref(dwRebootReasons))
        if res != 0:
            print(f"RmGetList (fetch) failed with error {res}")
            return []
            
        pids = []
        for i in range(pnProcInfo.value):
            pids.append((proc_info_array[i].Process.dwProcessId, proc_info_array[i].strAppName))
        return pids
        
    finally:
        rstrtmgr.RmEndSession(dwSession)

# Target the specific files that failed to delete
lock_files = [
    r"C:\Users\joaon\ptia-content-engine\.tmp\playwright-linkedin\lockfile",
    r"C:\Users\joaon\ptia-content-engine\.tmp\playwright-linkedin\Default\Extension State\LOCK",
    r"C:\Users\joaon\ptia-content-engine\.tmp\playwright-linkedin\Default\Session Storage\LOCK",
    r"C:\Users\joaon\ptia-content-engine\.tmp\playwright-linkedin\Default\Local Storage\leveldb\LOCK",
    r"C:\Users\joaon\ptia-content-engine\.tmp\playwright-linkedin\Default\shared_proto_db\LOCK"
]

all_pids_to_kill = set()
for file_path in lock_files:
    if os.path.exists(file_path):
        print(f"\nChecking locks on: {file_path}")
        pids = get_locking_processes(file_path)
        if pids:
            for pid, name in pids:
                print(f"  Locked by process: PID={pid}, Name='{name}'")
                all_pids_to_kill.add(pid)
        else:
            print("  No locking processes found via RM.")

if all_pids_to_kill:
    print(f"\nFound PIDs locking files: {all_pids_to_kill}")
    for pid in all_pids_to_kill:
        print(f"Killing PID {pid}...")
        try:
            os.kill(pid, 9)
            print(f"  Successfully killed PID {pid}.")
        except Exception as e:
            print(f"  Failed to kill PID {pid}: {e}")
else:
    print("\nNo PIDs to kill.")
