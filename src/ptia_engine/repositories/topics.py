from pathlib import Path
from ptia_engine.models import EditorialTopic
from ptia_engine.storage import load_editorial_topics, append_jsonl, write_jsonl

class EditorialTopicRepository:
    def __init__(self, file_path: Path):
        self.file_path = file_path

    def load_all(self) -> list[EditorialTopic]:
        return load_editorial_topics(self.file_path)

    def save_all(self, topics: list[EditorialTopic]) -> None:
        write_jsonl(self.file_path, topics)

    def get_by_id(self, topic_id: str) -> EditorialTopic | None:
        for topic in self.load_all():
            if topic.topic_id == topic_id:
                return topic
        return None

    def add(self, topic: EditorialTopic) -> None:
        append_jsonl(self.file_path, [topic])
