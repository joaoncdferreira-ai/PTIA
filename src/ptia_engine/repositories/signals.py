from pathlib import Path
from ptia_engine.models import RadarSignal
from ptia_engine.storage import load_radar_signals, append_jsonl, write_jsonl

class RadarSignalRepository:
    def __init__(self, file_path: Path):
        self.file_path = file_path

    def load_all(self) -> list[RadarSignal]:
        return load_radar_signals(self.file_path)

    def save_all(self, signals: list[RadarSignal]) -> None:
        write_jsonl(self.file_path, signals)

    def get_by_id(self, signal_id: str) -> RadarSignal | None:
        for signal in self.load_all():
            if signal.signal_id == signal_id:
                return signal
        return None

    def add(self, signal: RadarSignal) -> None:
        append_jsonl(self.file_path, [signal])
