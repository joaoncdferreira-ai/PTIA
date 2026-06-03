import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ptia_engine.dashboard import _final_post_text

class MockPost:
    def __init__(self, title, body, channel="linkedin", hashtags="", source_urls=None):
        self.title = title
        self.body = body
        self.channel = channel
        self.hashtags = hashtags
        self.source_urls = source_urls or []

post1 = MockPost(title="Test Title", body="chips de inteligência artificial da @NVIDIA e da @AMD.")
print("=== CASO 1 ===")
print(_final_post_text(post1))

post2 = MockPost(title="Test Title", body="A @nvidia lançou o novo chip Blackwell com a @amd.")
print("=== CASO 2 ===")
print(_final_post_text(post2))
