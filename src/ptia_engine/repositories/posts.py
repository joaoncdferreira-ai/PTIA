from pathlib import Path
from ptia_engine.models import FinalPost
from ptia_engine.storage import load_final_posts, append_jsonl, write_jsonl

class FinalPostRepository:
    def __init__(self, file_path: Path):
        self.file_path = file_path

    def load_all(self) -> list[FinalPost]:
        return load_final_posts(self.file_path)

    def save_all(self, posts: list[FinalPost]) -> None:
        write_jsonl(self.file_path, posts)

    def get_by_id(self, post_id: str) -> FinalPost | None:
        for post in self.load_all():
            if post.post_id == post_id:
                return post
        return None

    def get_by_topic_id(self, topic_id: str) -> list[FinalPost]:
        return [post for post in self.load_all() if post.topic_id == topic_id]

    def add(self, post: FinalPost) -> None:
        append_jsonl(self.file_path, [post])
