import sys
import os
from pathlib import Path

ROOT = Path("c:/Users/joaon/ptia-content-engine")
sys.path.insert(0, str(ROOT / "src"))

def load_dotenv() -> None:
    env_path = ROOT / ".env.local"
    if not env_path.exists():
        print("No .env.local found!")
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ[key.strip()] = value.strip().strip('"').strip("'")

def main():
    load_dotenv()
    print("GEMINI_API_KEY in env:", "GEMINI_API_KEY" in os.environ)
    
    from ptia_engine.repositories import RadarSignalRepository, EditorialTopicRepository, FinalPostRepository
    from ptia_engine.use_cases.curation import BuildFinalPackUseCase
    from ptia_engine.dashboard import DashboardState
    
    state = DashboardState(ROOT / "data")
    
    signal_repo = RadarSignalRepository(state.radar_signals_path)
    topic_repo = EditorialTopicRepository(state.editorial_topics_path)
    post_repo = FinalPostRepository(state.final_posts_path)
    
    use_case = BuildFinalPackUseCase(
        signal_repo=signal_repo,
        topic_repo=topic_repo,
        post_repo=post_repo,
        buffer_channels_path=state.buffer_channels_path,
    )
    
    signal_id = "sig_cda7a32d647636f0f7"
    print(f"Executing curation for signal {signal_id}...")
    try:
        result = use_case.execute(signal_id)
        print("SUCCESS!")
        print("Created Topic:", result["topic"].topic_id, result["topic"].title)
        print("Created Posts:")
        for post in result["posts"]:
            print(f"  - Post ID: {post.post_id} | Channel: {post.channel} | Status: {post.status} | Title: {post.title}")
    except Exception as e:
        print("FAILED with exception:")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
