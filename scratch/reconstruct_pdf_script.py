import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

log_path = r"C:\Users\joaon\.gemini\antigravity\brain\97b18b7a-bfe1-4412-bbd3-47410ebaa4bf\.system_generated\logs\transcript.jsonl"

file_content = None
with open(log_path, 'r', encoding='utf-8') as f:
    for line in f:
        try:
            obj = json.loads(line)
            if obj.get('step_index') == 4373:
                # This step is the VIEW_FILE of generate_comments_pdf.py
                file_content = obj.get('content')
                break
        except Exception:
            pass

if file_content:
    print("Found step 4373 content! Preview:")
    print(file_content[:1000])
    
    # Save the original lines (without the "<line_number>: " prefix)
    lines = file_content.split('\n')
    cleaned_lines = []
    # Skip header lines that VIEW_FILE prints
    # Typically VIEW_FILE output looks like:
    # Created At: ...
    # File Path: ...
    # Total Lines: ...
    # Showing lines ...
    # The following code has been modified...
    # 1: code...
    # 2: code...
    for line in lines:
        if ': ' in line:
            parts = line.split(': ', 1)
            if parts[0].strip().isdigit():
                cleaned_lines.append(parts[1])
                
    reconstructed_code = '\n'.join(cleaned_lines)
    output_path = r"c:\Users\joaon\ptia-content-engine\scratch\generate_comments_pdf.py"
    with open(output_path, 'w', encoding='utf-8') as out_f:
        out_f.write(reconstructed_code)
    print(f"\nReconstructed generate_comments_pdf.py and wrote to: {output_path}")
else:
    print("Step 4373 not found or has no content.")
