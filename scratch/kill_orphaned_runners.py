import subprocess
import os
import sys

# Current Python PID
my_pid = os.getpid()
print(f"Current python PID: {my_pid}")

# We will use PowerShell to query and kill processes
# Query for node.exe or python.exe containing ptia-content-engine or linkedin
ps_query = """
Get-CimInstance Win32_Process | Where-Object { 
    (($_.Name -eq "python.exe") -or ($_.Name -eq "node.exe")) -and 
    ($_.CommandLine -like "*linkedin-comments*" -or $_.CommandLine -like "*linkedin_automation.js*")
} | Format-Table ProcessId, Name, CommandLine -AutoSize
"""

try:
    res = subprocess.run(["powershell", "-Command", ps_query], capture_output=True, text=True, check=True)
    print("Orphan processes detected:")
    print(res.stdout)
except Exception as e:
    print(f"Error querying processes: {e}")

# Command to kill matching processes (excluding my_pid)
ps_kill = f"""
Get-CimInstance Win32_Process | Where-Object {{ 
    (($_.Name -eq "python.exe") -or ($_.Name -eq "node.exe")) -and 
    ($_.CommandLine -like "*linkedin-comments*" -or $_.CommandLine -like "*linkedin_automation.js*") -and
    ($_.ProcessId -ne {my_pid})
}} | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force; Write-Host "Killed PID $_.ProcessId" }}
"""

try:
    res = subprocess.run(["powershell", "-Command", ps_kill], capture_output=True, text=True, check=True)
    print("Kill results:")
    print(res.stdout)
except Exception as e:
    print(f"Error killing processes: {e}")
