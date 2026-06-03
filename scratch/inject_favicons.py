import re
from pathlib import Path

ROOT = Path("c:/Users/joaon/ptia-content-engine")
site_dir = ROOT / "site"
dashboard_file = ROOT / "src" / "ptia_engine" / "dashboard.py"

print("=== INJECTING FAVICON LINKS ===")

# Favicon tags to inject
favicon_tags = """<head>
  <link rel="icon" type="image/png" href="/favicon.png">
  <link rel="shortcut icon" href="/favicon.ico">
  <link rel="apple-touch-icon" href="/apple-touch-icon.png">"""

# 1. Modify static html files in the site directory
html_files = list(site_dir.glob("*.html"))
# Also search subdirectories for index.html files (like articles already generated, sobre, guias etc.)
for path in site_dir.glob("**/index.html"):
    if path.is_file():
        html_files.append(path)

print(f"Found {len(html_files)} HTML files to update.")

for path in html_files:
    try:
        content = path.read_text(encoding="utf-8")
        if 'rel="icon"' in content or 'rel="shortcut icon"' in content:
            print(f"  [Skipped] {path.relative_to(ROOT)} already has favicon tags.")
            continue
            
        # Replace <head> with <head> + tags
        # case-insensitive replacement
        new_content = re.sub(r"<head>", favicon_tags, content, flags=re.IGNORECASE, count=1)
        if new_content != content:
            path.write_text(new_content, encoding="utf-8")
            print(f"  [Updated] {path.relative_to(ROOT)}")
        else:
            print(f"  [Not Matched] {path.relative_to(ROOT)} - <head> tag not found.")
    except Exception as e:
        print(f"  [Error] Failed to process {path.relative_to(ROOT)}: {e}")

# 2. Modify src/ptia_engine/dashboard.py page header generation template
if dashboard_file.exists():
    try:
        content = dashboard_file.read_text(encoding="utf-8")
        
        # Target 1: def _get_page_header_html template
        target_1 = '<head>\n  <meta charset="utf-8">'
        replacement_1 = '<head>\n  <link rel="icon" type="image/png" href="/favicon.png">\n  <link rel="shortcut icon" href="/favicon.ico">\n  <link rel="apple-touch-icon" href="/apple-touch-icon.png">\n  <meta charset="utf-8">'
        
        # Target 2: HTML = r"""<!doctype html> ... <head>
        target_2 = 'HTML = r"""<!doctype html>\n<html lang="pt">\n<head>\n  <meta charset="utf-8">'
        # Let's write it to handle string replacements safely
        
        updated = False
        if target_1 in content:
            content = content.replace(target_1, replacement_1, 1)
            print("  [Updated] dashboard.py - Page Header Template")
            updated = True
        else:
            # Let's search with regex or standard replace
            alt_target_1 = '<head>\n  <meta charset="utf-8">'
            # Let's check with lines
            
        # Target 2 inside dashboard.py: HTML = r"""<!doctype html>...
        # Let's use simple find and replace for the exact lines
        target_lines_2 = 'HTML = r"""<!doctype html>\n<html lang="pt">\n<head>\n  <meta charset="utf-8">'
        # Let's do a generic regex search or string replace
        # Let's find:
        # <head>
        #   <meta charset="utf-8">
        # inside the HTML string
        
        # Let's search for '<head>\n  <meta charset="utf-8">' in the entire file and replace it.
        # Since target_1 matches this, it might have replaced it. But let's check if there are other occurrences.
        # Let's replace all '<head>\n  <meta charset="utf-8">' with the favicon header
        occurrences = content.count('<head>\n  <meta charset="utf-8">')
        if occurrences > 0:
            content = content.replace('<head>\n  <meta charset="utf-8">', '<head>\n  <link rel="icon" type="image/png" href="/favicon.png">\n  <link rel="shortcut icon" href="/favicon.ico">\n  <link rel="apple-touch-icon" href="/apple-touch-icon.png">\n  <meta charset="utf-8">')
            print(f"  [Updated] dashboard.py - Replaced {occurrences} instances of <head>.")
            updated = True
            
        if updated:
            dashboard_file.write_text(content, encoding="utf-8")
            print("  [Saved] dashboard.py")
        else:
            print("  [Skipped] No matches found in dashboard.py")
            
    except Exception as e:
        print(f"Error updating dashboard.py: {e}")
else:
    print(f"dashboard.py not found at {dashboard_file}")
