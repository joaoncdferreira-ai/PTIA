import shutil
import unittest
import uuid
from pathlib import Path

from ptia_engine.exports import export_sources_csv


class ExportTests(unittest.TestCase):
    def test_export_sources_csv_writes_header(self):
        root = Path.cwd() / ".test_tmp" / uuid.uuid4().hex
        try:
            root.mkdir(parents=True)
            sources = root / "sources.json"
            out = root / "sources.csv"
            sources.write_text(
                '[{"source_id":"test","name":"Test","active":true}]',
                encoding="utf-8",
            )

            export_sources_csv(sources, out)

            content = out.read_text(encoding="utf-8-sig")
            self.assertIn("active", content.splitlines()[0])
            self.assertIn("source_id", content.splitlines()[0])
        finally:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
