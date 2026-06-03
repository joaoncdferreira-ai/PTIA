import os
from pathlib import Path

profile_dir = Path("C:/Users/joaon/ptia-content-engine/.tmp/playwright-linkedin")
cookies_file = profile_dir / "Default" / "Network" / "Cookies"

if not cookies_file.exists():
    # Chrome older versions might store it in Default/Cookies
    cookies_file = profile_dir / "Default" / "Cookies"

if cookies_file.exists():
    size_kb = cookies_file.stat().st_size / 1024
    print(f"Cookies file found at {cookies_file}. Size: {size_kb:.2f} KB")
else:
    print(f"No Cookies file found in {profile_dir} Default folder.")
    
# Let's list files in the Default folder to see what is there
default_dir = profile_dir / "Default"
if default_dir.exists():
    print("\nFiles in Default directory:")
    for f in default_dir.iterdir():
        if f.is_file():
            print(f"  {f.name} ({f.stat().st_size / 1024:.2f} KB)")
