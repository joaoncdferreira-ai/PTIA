import json
import subprocess
import sys
from pathlib import Path

ROOT = Path("c:/Users/joaon/ptia-content-engine")
db_path = ROOT / "data" / "linkedin_comments.jsonl"
tmp_html = ROOT / ".tmp" / "comments_report.html"
output_pdf = Path("C:/Users/joaon/.gemini/antigravity/brain/97b18b7a-bfe1-4412-bbd3-47410ebaa4bf/linkedin_comments_report.pdf")

print("=== GENERATING LINKEDIN COMMENTS REPORT ===")

# Read all comments
if not db_path.exists():
    print("Database linkedin_comments.jsonl does not exist!")
    sys.exit(1)

with open(db_path, "r", encoding="utf-8") as f:
    lines = f.readlines()

records = []
for line in lines:
    if line.strip():
        try:
            records.append(json.loads(line))
        except Exception:
            pass

# Filter and get the 15 most recent comments
recent_records = records[-15:]
recent_records.reverse()  # Show most recent first

# Generate HTML
html_content = """<!DOCTYPE html>
<html lang="pt">
<head>
    <meta charset="UTF-8">
    <title>Relatório de Simulação de Comentários LinkedIn - PTIA</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&family=Playfair+Display:ital,wght@0,600;0,800;1,600&display=swap');
        
        body {
            font-family: 'Outfit', sans-serif;
            background-color: #fcfbf9;
            color: #1a2238;
            margin: 0;
            padding
            
            <div class="section-title">Post Original do Autor</div>
            <div class="original-post">{post_body}</div>
            
            <div class="section-title">Comentário Simulado pela PTIA ("Sim, e...")</div>
            <div class="engine-comment">{comment_text}</div>
            
            <div class="timestamp">Gerado em: {time_display}</div>
        </div>
    """

html_content += """
    </main>
</body>
</html>
"""

# Write to file
tmp_html.parent.mkdir(parents=True, exist_ok=True)
tmp_html.write_text(html_content, encoding="utf-8")
print(f"HTML report written to: {tmp_html}")

# Generate PDF with Playwright via node
node_script = f"""
const {{ chromium }} = require("playwright");
async function render() {{
  const browser = await chromium.launch({{ headless: true }});
  const page = await browser.newPage();
  await page.goto("file:///{str(tmp_html).replace('\\\\', '/')}", {{ waitUntil: "networkidle" }});
  await page.pdf({{
    path: "{str(output_pdf).replace('\\\\', '/')}",
    format: "A4",
    printBackground: true,
    margin: {{ top: "20mm", right: "20mm", bottom: "20mm", left: "20mm" }}
  }});
  await browser.close();
  console.log("PDF rendered successfully.");
}}
render();
"""

tmp_node_js = ROOT / ".tmp" / "render_report.js"
tmp_node_js.write_text(node_script, encoding="utf-8")

print("Rendering PDF using Playwright...")
try:
    res = subprocess.run(["node", str(tmp_node_js)], capture_output=True, text=True, check=True)
    print(res.stdout)
    print(f"SUCCESS: PDF generated at {output_pdf}")
except Exception as e:
    print(f"Error rendering PDF: {e}")
    if hasattr(e, 'stderr'):
        print(e.stderr)
