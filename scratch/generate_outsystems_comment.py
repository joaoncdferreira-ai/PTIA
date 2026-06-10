import os
import sys
from pathlib import Path

# Add src to python path
ROOT = Path("c:/Users/joaon/ptia-content-engine")
sys.path.insert(0, str(ROOT / "src"))

# Load environment variables
def load_dotenv():
    env_path = ROOT / ".env.local"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            sline = line.strip()
            if not sline or sline.startswith("#") or "=" not in sline:
                continue
            key, val = sline.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))

load_dotenv()

from ptia_engine.search_providers import GeminiGroundedSearchProvider
from ptia_engine.linkedin_commenter import LINKEDIN_COMMENT_PROMPT

post_body = """Big news from #ONEOutSystems 🚀

OutSystems is expanding its collaboration with Amazon Web Services (AWS) to help enterprises build and scale the next generation of #agentic systems — with more flexibility, stronger governance, and faster modernization.

Together, OutSystems and AWS are introducing:
⚡ AWS Transform for legacy modernization: Accelerate modernization with agent-led code transformation that helps unlock legacy value faster.
🤖 Native integration with Kiro: Connect spec-driven development with Mentor’s governed AI delivery to move from idea to production faster.
🧠 Amazon Bedrock for model hot swapping: Optimize for cost, performance, and flexibility with the right model for the right task.

This collaboration helps enterprises tackle some of the biggest barriers to #AI success: fragmented models, legacy technical debt, and AI-native governance.

“The shift toward agentic systems is the most significant architectural evolution of our lifetime.” — Woodson Martin, CEO of OutSystems

Read the full announcement: https://bit.ly/4uhX1UY"""

provider = GeminiGroundedSearchProvider()
prompt = LINKEDIN_COMMENT_PROMPT.format(post_body=post_body)

print("Generating comment using PTIA engine...")
raw_response = provider._generate_json_response(prompt, temperature=0.72)
candidate = (raw_response.get("candidates") or [{}])[0]
parts = ((candidate.get("content") or {}).get("parts") or [])
generated_comment = "\n".join(str(part.get("text", "")) for part in parts if isinstance(part, dict)).strip()
generated_comment = generated_comment.strip().strip('"').strip("'").replace("```json", "").replace("```", "").strip()

print("\n=== GENERATED COMMENT ===")
print(generated_comment)
print("=========================")
