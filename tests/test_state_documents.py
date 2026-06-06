import unittest

from ptia_engine.state_documents import (
    content_sha256,
    decode_content_chunks,
    encode_content_chunks,
)


class StateDocumentTests(unittest.TestCase):
    def test_chunk_round_trip_preserves_large_unicode_content(self):
        content = ("Portugal, IA e inovação.\n" * 50_000) + "fim"

        chunks = encode_content_chunks(content, chunk_bytes=100_000)

        self.assertGreater(len(chunks), 2)
        self.assertEqual(decode_content_chunks(chunks), content)

    def test_empty_content_uses_one_chunk(self):
        self.assertEqual(encode_content_chunks(""), [""])
        self.assertEqual(decode_content_chunks([""]), "")

    def test_sha_is_stable(self):
        self.assertEqual(content_sha256("PTIA"), content_sha256("PTIA"))
        self.assertNotEqual(content_sha256("PTIA"), content_sha256("ptia"))


if __name__ == "__main__":
    unittest.main()
