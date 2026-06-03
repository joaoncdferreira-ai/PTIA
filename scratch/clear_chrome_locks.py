import os
import shutil
import subprocess
from pathlib import Path

# 1. Kill any chrome processes matching playwright-linkedin using PowerShell
print("Terminating any running Playwright Chrome instances...")
ps_cmd = 'Get-CimInstance Win32_Process -Filter "name=\'chrome.exe\'" | Where-Object { $_.CommandLine -like "*playwright-linkedin*" } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }'
try:
    subprocess.run(["powershell", "-Command", ps_cmd], capture_output=True, text=True, check=True)
    print("PowerShell cleanup complete.")
except Exception as e:
    print(f"PowerShell cleanup ran with notes/errors: {e}")

# 2. Clear Chrome lock files in the temporary profile directory
profile_dir = Path("C:/Users/joaon/ptia-content-engine/.tmp/playwright-linkedin")
if profile_dir.exists():
    print(f"Scanning for lock files in: {profile_dir}")
    
    # Files to look for and delete
    lock_names = ["SingletonLock", "Lock", "lockfile"]
    
    deleted_count = 0
    # Walk the directory
    for root, dirs, files in os.walk(profile_dir):
        for file in files:
            # Match specific lock file names or containing lock
            if file in lock_names or "lock" in file.lower():
                file_path = Path(root) / file
                try:
                    # Try to delete the lock file
                    file_path.unlink()
                    print(f"Deleted lock file: {file_path}")
                    deleted_count += 1
                except Exception as e:
                    print(f"Failed to delete {file_path}: {e}")
                    
    print(f"Lock file cleanup finished. Deleted {deleted_count} lock files.")
else:
    print(f"Profile directory {profile_dir} does not exist yet.")
